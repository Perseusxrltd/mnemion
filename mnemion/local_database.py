"""App-owned PostgreSQL lifecycle with separate owner, API and worker identities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from . import local_state as state
from .private_output import private_output
from .service.admin import register_generation
from .service.db import migrate, new_token, token_hash
from .service.embeddings import Generation


def available_port(preferred: int = 0) -> int:
    with socket.socket() as connection:
        if os.name == "nt":
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            connection.bind(("127.0.0.1", preferred))
        except OSError:
            if not preferred:
                raise
            connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def prepare_credentials(root: Path) -> dict:
    path = root / "credentials.json"
    if path.exists():
        value = state.read(path)
        expected = {
            "format",
            "owner_password",
            "api_password",
            "worker_password",
            "tenant_id",
            "principal_id",
            "space_id",
            "key_id",
            "api_key",
        }
        if set(value) != expected or value["format"] != 1:
            raise state.LocalSetupError(
                "damaged_credentials",
                "Local credentials need recovery. Existing data has been retained.",
            )
        from uuid import UUID

        for name in ("tenant_id", "principal_id", "space_id", "key_id"):
            UUID(value[name])
        for name in ("owner_password", "api_password", "worker_password", "api_key"):
            if not isinstance(value[name], str) or not 40 <= len(value[name]) <= 200:
                raise state.LocalSetupError(
                    "damaged_credentials",
                    "Local credentials need recovery. Existing data has been retained.",
                )
        return value
    if (root / "database").exists() or (root / "database.pending").exists():
        raise state.LocalSetupError(
            "missing_credentials",
            "The database already exists but its credentials are missing. Restore its setup records before continuing.",
        )
    value = {
        "format": 1,
        **{name + "_password": secrets.token_urlsafe(32) for name in ("owner", "api", "worker")},
        **{name + "_id": str(uuid4()) for name in ("tenant", "principal", "space", "key")},
        "api_key": new_token()[0],
    }
    state.write(path, value, replace=False)
    return value


def _tls(root: Path) -> Path:
    target = root / "tls"
    if target.exists():
        state.directory(target)
        if not (target / "certificate.pem").is_file() or not (target / "key.pem").is_file():
            raise state.LocalSetupError(
                "damaged_certificate",
                "The local database certificate needs recovery. No data has been replaced.",
            )
        return target
    staging = root / (".tls-" + uuid4().hex)
    state.directory(staging)
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mnemion local workspace")])
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256())
        )
        with private_output(staging / "key.pem") as stream:
            stream.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        with private_output(staging / "certificate.pem") as stream:
            stream.write(certificate.public_bytes(serialization.Encoding.PEM))
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


class LocalDatabase:
    def __init__(self, root: Path, runtime: Path, configuration: dict, credentials: dict):
        self.root, self.runtime = root, runtime.resolve()
        self.configuration, self.credentials = configuration, credentials
        self.data = root / "database"
        self.suffix = ".exe" if os.name == "nt" else ""
        self.started = False
        self.process_identity: tuple[int, float] | None = None
        self.environment = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("PG", "MNEMION_", "PYTHON", "HF_"))
            and k
            not in {
                "LD_LIBRARY_PATH",
                "LD_PRELOAD",
                "DYLD_LIBRARY_PATH",
                "DYLD_INSERT_LIBRARIES",
                "DYLD_FALLBACK_LIBRARY_PATH",
                "OPENSSL_CONF",
                "OPENSSL_MODULES",
            }
        }
        self.environment.update(LC_ALL="C", PGCLIENTENCODING="UTF8")

    def tool(self, name: str) -> Path:
        return self.runtime / "bin" / (name + self.suffix)

    def run(
        self, name: str, arguments: list, *, timeout: int = 60, check: bool = True
    ) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                [str(self.tool(name)), *map(str, arguments)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.environment,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            raise state.LocalSetupError(
                "database_tool",
                f"The local database could not finish {name}. Close other setup sessions and retry.",
            ) from None
        if check and result.returncode:
            raise state.LocalSetupError(
                "database_tool",
                f"The local database could not finish {name}. Check available disk space and folder permissions, then retry.",
            )
        return result

    def dsn(self, role: str = "owner", *, database: str = "mnemion") -> str:
        if role not in {"owner", "api", "worker"}:
            raise ValueError("Unknown local database role")
        return make_conninfo(
            host="127.0.0.1",
            port=self.configuration["database_port"],
            dbname=database,
            user="mnemion_" + role + ("" if role == "owner" else "_login"),
            password=self.credentials[role + "_password"],
            sslmode="verify-full",
            sslrootcert=str(self.root / "tls/certificate.pem"),
            connect_timeout=5,
            client_encoding="UTF8",
            application_name="mnemion-local-" + role,
        )

    def initialize(self) -> None:
        state.directory(self.root)
        _tls(self.root)
        if self.data.exists():
            state.directory(self.data)
            if (self.data / "PG_VERSION").read_text().strip() != "18":
                raise state.LocalSetupError(
                    "database_version",
                    "This database needs an explicit major-version migration. Its files have been retained.",
                )
            return
        staging = self.root / "database.pending"
        if staging.exists():
            state.directory(staging)
            # A previous operator may have been killed while initdb was still
            # running. Never remove its output underneath a surviving process.
            import psutil

            for process in psutil.process_iter(["exe", "cmdline"]):
                try:
                    if (
                        process.info["exe"]
                        and Path(process.info["exe"]).parent == self.runtime / "bin"
                        and str(staging) in (process.info["cmdline"] or [])
                    ):
                        raise state.LocalSetupError(
                            "setup_finishing",
                            "The previous database setup is still finishing. Wait a moment and retry.",
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            shutil.rmtree(staging)
        state.directory(staging)
        password_file = self.root / (".init-password-" + uuid4().hex)
        try:
            with private_output(password_file) as stream:
                stream.write((self.credentials["owner_password"] + "\n").encode())
            self.run(
                "initdb",
                [
                    "-D",
                    staging,
                    "--username=mnemion_owner",
                    "--pwfile",
                    password_file,
                    "--auth=scram-sha-256",
                    "--encoding=UTF8",
                    "--locale-provider=builtin",
                    "--builtin-locale=C.UTF-8",
                    "--data-checksums",
                ],
                timeout=120,
            )
            self.run("pg_controldata", [staging])
            staging.rename(self.data)
        finally:
            password_file.unlink(missing_ok=True)

    def _verify_server(self) -> None:
        import psutil

        with psycopg.connect(self.dsn(database="postgres")) as connection:
            directory, tls = connection.execute(
                "SELECT current_setting('data_directory'), (SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())"
            ).fetchone()
            if Path(directory).resolve() != self.data.resolve() or tls is not True:
                raise state.LocalSetupError(
                    "database_identity", "The local database identity did not match this workspace."
                )
        pid = int((self.data / "postmaster.pid").read_text().splitlines()[0])
        process = psutil.Process(pid)
        arguments = process.cmdline()
        if str(self.data) not in arguments or Path(process.exe()).name not in {
            "postgres",
            "postgres.exe",
        }:
            raise state.LocalSetupError(
                "database_identity", "The local database process did not match this workspace."
            )
        self.process_identity = (pid, process.create_time())
        self.started = True

    def start(self) -> None:
        self.initialize()
        if self.run("pg_ctl", ["status", "-D", self.data], check=False).returncode == 0:
            self._verify_server()
            return
        logs = state.directory(self.root / "logs")

        def path(value: Path) -> str:
            return "'" + value.as_posix().replace("'", "''") + "'"

        # This private cluster never accepts a LAN listener or trust auth.
        configuration = (
            "listen_addresses='127.0.0.1'\n"
            f"port={self.configuration['database_port']}\n"
            "unix_socket_directories=''\nshared_buffers='32MB'\nmax_connections=24\n"
            "max_wal_size='256MB'\nmin_wal_size='32MB'\nwork_mem='4MB'\n"
            "maintenance_work_mem='16MB'\nautovacuum_work_mem='16MB'\nautovacuum_max_workers=1\n"
            "password_encryption='scram-sha-256'\nssl=on\nssl_min_protocol_version='TLSv1.2'\n"
            f"ssl_cert_file={path(self.root / 'tls/certificate.pem')}\nssl_key_file={path(self.root / 'tls/key.pem')}\n"
            "log_statement='none'\nlog_min_error_statement='panic'\nlog_parameter_max_length_on_error=0\n"
            "logging_collector=on\n"
            f"log_directory={path(logs)}\nlog_filename='postgres-%a.log'\nlog_rotation_age='1d'\n"
            "log_rotation_size='10MB'\nlog_truncate_on_rotation=on\n"
        )
        configuration_path = self.data / "postgresql.conf"
        if configuration_path.is_symlink():
            raise state.LocalSetupError(
                "unsafe_location", "The database configuration cannot be a link."
            )
        # No live process reads this file during replacement.
        temporary = self.data / (".configuration-" + uuid4().hex)
        with private_output(temporary) as stream:
            stream.write(configuration.encode("utf-8"))
        os.replace(temporary, configuration_path)
        # Requiring hostssl also refuses an unencrypted loopback connection.
        hba = self.data / "pg_hba.conf"
        temporary = self.data / (".authentication-" + uuid4().hex)
        with private_output(temporary) as stream:
            stream.write(b"hostssl all all 127.0.0.1/32 scram-sha-256\n")
        if hba.is_symlink():
            temporary.unlink()
            raise state.LocalSetupError(
                "unsafe_location", "The database authentication file cannot be a link."
            )
        os.replace(temporary, hba)
        self.run("pg_ctl", ["start", "-D", self.data, "-l", logs / "startup.log", "-w", "-t", "30"])
        self._verify_server()

    def provision(self, generation: Generation) -> dict:
        with psycopg.connect(self.dsn(database="postgres"), autocommit=True) as connection:
            if not connection.execute(
                "SELECT 1 FROM pg_database WHERE datname='mnemion'"
            ).fetchone():
                connection.execute("CREATE DATABASE mnemion")
        applied = migrate(self.dsn())
        with psycopg.connect(self.dsn()) as connection:
            for role, group in (("api", "mnemion_app"), ("worker", "mnemion_worker")):
                name = "mnemion_" + role + "_login"
                existing = connection.execute(
                    "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=%s",
                    (name,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {} IN ROLE {}"
                        ).format(
                            sql.Identifier(name),
                            sql.Literal(self.credentials[role + "_password"]),
                            sql.Identifier(group),
                        )
                    )
                elif any(existing):
                    raise state.LocalSetupError(
                        "database_roles",
                        "A local service login has unexpected privileges. Repair its access before continuing.",
                    )
            register_generation(connection, generation)
            setup = self.credentials
            tenant, principal, space, key = [
                setup[name + "_id"] for name in ("tenant", "principal", "space", "key")
            ]
            existing = connection.execute(
                "SELECT 1 FROM mnemion.tenants WHERE id=%s", (tenant,)
            ).fetchone()
            if existing:
                valid = connection.execute(
                    "SELECT 1 FROM mnemion.api_keys WHERE tenant_id=%s AND id=%s AND principal_id=%s AND token_hash=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())",
                    (tenant, key, principal, token_hash(setup["api_key"])),
                ).fetchone()
                if not valid:
                    raise state.LocalSetupError(
                        "owner_access",
                        "The saved local owner key is no longer active. Recover administrator access before continuing.",
                    )
            else:
                # All identities were durably written before this transaction.
                # A retry after any interruption creates the same workspace.
                connection.execute(
                    "INSERT INTO mnemion.tenants(id, name) VALUES (%s,%s)",
                    (tenant, self.configuration["workspace_name"]),
                )
                connection.execute(
                    "INSERT INTO mnemion.principals(tenant_id,id,name,kind,administrator) VALUES (%s,%s,%s,'human',true)",
                    (tenant, principal, self.configuration["owner_name"]),
                )
                connection.execute(
                    "INSERT INTO mnemion.spaces(tenant_id,id,name) VALUES (%s,%s,%s)",
                    (tenant, space, "Private memory"),
                )
                connection.execute(
                    "INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role) VALUES (%s,%s,%s,'administrator')",
                    (tenant, space, principal),
                )
                connection.execute(
                    "INSERT INTO mnemion.api_keys(tenant_id,id,principal_id,name,token_hash,prefix) VALUES (%s,%s,%s,'Local workspace owner',%s,%s)",
                    (tenant, key, principal, token_hash(setup["api_key"]), setup["api_key"][:12]),
                )
                connection.execute(
                    "INSERT INTO mnemion.audit_events(tenant_id,id,principal_id,action,resource_id) VALUES (%s,%s,%s,'tenant.created',%s)",
                    (tenant, str(uuid4()), principal, tenant),
                )
        return {"applied_migrations": applied, "tenant_id": tenant, "space_id": space}

    def stop(self) -> None:
        if self.process_identity is None:
            return
        import psutil

        pid, created = self.process_identity
        try:
            process = psutil.Process(pid)
            if process.create_time() != created or str(self.data) not in process.cmdline():
                raise state.LocalSetupError(
                    "database_identity", "The database process changed; it was not stopped."
                )
        except psutil.NoSuchProcess:
            self.started = False
            return
        self.run("pg_ctl", ["stop", "-D", self.data, "-m", "fast", "-w", "-t", "30"], timeout=40)
        self.started = False
