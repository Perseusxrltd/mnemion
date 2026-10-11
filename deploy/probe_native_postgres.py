"""Exercise a relocated native database archive using a disposable private cluster."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import secrets
import shutil
import socket
import stat
import struct
import subprocess
import tempfile
import zipfile


def expand(archive_path: Path, directory: Path) -> dict:
    directory.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(e.file_size for e in entries) > 768 * 1024**2:
            raise ValueError("Native archive exceeds its expanded budget")
        seen = set()
        for item in entries:
            path = PurePosixPath(item.filename)
            if (
                not path.parts
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in item.filename
                or ":" in item.filename
                or item.is_dir()
                or stat.S_ISLNK(item.external_attr >> 16)
                or item.filename.casefold() in seen
            ):
                raise ValueError("Unsafe or duplicate native archive entry")
            seen.add(item.filename.casefold())
            target = directory.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("xb") as out:
                shutil.copyfileobj(source, out)
            target.chmod(0o755 if (item.external_attr >> 16) & 0o111 else 0o644)
    metadata = json.loads((directory / "mnemion-runtime.json").read_text())
    if metadata.get("format") != 1 or metadata.get("component") != "postgresql":
        raise ValueError("Invalid native runtime metadata")
    files = metadata["files"]
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual != set(files) | {"mnemion-runtime.json"}:
        raise ValueError("Native runtime file inventory is incomplete")
    for name, expected in files.items():
        path = directory / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            path.stat().st_size != expected["size"]
            or digest != expected["sha256"]
            or bool(path.stat().st_mode & 0o111) != expected["executable"]
        ):
            raise ValueError("Native runtime file differs from its inventory")
    return metadata


def executable_architecture(path: Path) -> str:
    with path.open("rb") as stream:
        header = stream.read(64)
        if header[:2] == b"MZ":
            stream.seek(struct.unpack_from("<I", header, 0x3C)[0])
            pe = stream.read(6)
            if pe[:4] != b"PE\0\0":
                raise ValueError("Invalid PE runtime")
            code = struct.unpack_from("<H", pe, 4)[0]
            result = {0x8664: "x64", 0xAA64: "arm64"}.get(code)
        elif header[:4] == b"\x7fELF":
            code = struct.unpack_from("<H", header, 18)[0]
            result = {62: "x64", 183: "arm64"}.get(code)
        elif header[:4] == b"\xcf\xfa\xed\xfe":
            code = struct.unpack_from("<I", header, 4)[0]
            result = {0x01000007: "x64", 0x0100000C: "arm64"}.get(code)
        else:
            result = None
    if not result:
        raise ValueError("Unsupported native executable architecture")
    return result


def probe(archive: Path, output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="mnemion-pg-validation-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        install = root / "Memory runtime with spaces"
        metadata = expand(archive, install)
        suffix = ".exe" if platform.system() == "Windows" else ""
        binaries = install / "bin"
        architecture = executable_architecture(binaries / ("postgres" + suffix))
        if architecture != metadata["architecture"]:
            raise ValueError("Actual executable architecture differs from its manifest")
        expected_os = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}[platform.system()]
        if metadata["platform"] != expected_os:
            raise ValueError("Native database archive is for a different operating system")
        host_arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}[
            platform.machine().lower()
        ]
        if architecture != host_arch and not (
            expected_os == "windows" and architecture == "x64" and host_arch == "arm64"
        ):
            raise ValueError("Unsupported host/runtime architecture combination")
        environment = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("PG")
            and k
            not in {
                "LD_LIBRARY_PATH",
                "DYLD_LIBRARY_PATH",
                "DYLD_FALLBACK_LIBRARY_PATH",
                "OPENSSL_MODULES",
                "OPENSSL_CONF",
            }
        }
        environment["LC_ALL"] = "C"
        password, reader_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)

        def run(name, args=(), *, input=None, check=True, env=None, timeout=60):
            command = (
                binaries / (name + suffix)
                if name != "openssl"
                else install / "tools" / (name + suffix)
            )
            result = subprocess.run(
                [str(command), *map(str, args)],
                input=input,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env or environment,
                timeout=timeout,
            )
            if check and result.returncode:
                message = (
                    (result.stdout + result.stderr)
                    .replace(password, "[redacted]")
                    .replace(reader_password, "[redacted]")
                )
                raise RuntimeError(f"{name} failed ({result.returncode}): {message[-3000:]}")
            return result

        pg_version = run("postgres", ["--version"]).stdout.strip()
        ssl_version = run("openssl", ["version"]).stdout.strip()
        if not pg_version.endswith(metadata["sources"]["postgresql"]["version"]):
            raise ValueError("Native PostgreSQL version differs from its pinned source")
        if not ssl_version.startswith("OpenSSL " + metadata["sources"]["openssl"]["version"] + " "):
            raise ValueError("Native OpenSSL version differs from its pinned source")
        data = root / "Workspace data Équipe"
        pwfile = root / "initial-password"
        pwfile.write_text(password + "\n")
        pwfile.chmod(0o600)
        run(
            "initdb",
            [
                "-D",
                data,
                "-U",
                "runtime_owner",
                "--pwfile=" + str(pwfile),
                "--auth-host=scram-sha-256",
                "--auth-local=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
                "--locale-provider=builtin",
                "--builtin-locale=C.UTF-8",
            ],
        )
        pwfile.unlink()
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
        cert, key = root / "server.crt", root / "server.key"
        ssl_config = root / "openssl.cnf"
        ssl_config.write_text("[req]\ndistinguished_name=req_dn\n[req_dn]\n")
        run(
            "openssl",
            [
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=IP:127.0.0.1,DNS:localhost",
                "-config",
                ssl_config,
                "-out",
                cert,
                "-keyout",
                key,
            ],
        )
        key.chmod(0o600)

        def conf_path(path):
            return "'" + path.as_posix().replace("'", "''") + "'"

        with (data / "postgresql.conf").open("a") as stream:
            stream.write(
                f"\nlisten_addresses='127.0.0.1'\nport={port}\nunix_socket_directories=''\n"
                "shared_buffers='16MB'\nmax_connections=10\nmax_wal_size='128MB'\nmin_wal_size='32MB'\n"
                f"ssl=on\nssl_cert_file={conf_path(cert)}\nssl_key_file={conf_path(key)}\n"
            )
        passfile = root / "connection-passwords"
        passfile.write_text(
            f"127.0.0.1:{port}:*:runtime_owner:{password}\n127.0.0.1:{port}:*:runtime_reader:{reader_password}\n"
        )
        passfile.chmod(0o600)
        environment.update(
            {
                "PGHOST": "127.0.0.1",
                "PGPORT": str(port),
                "PGUSER": "runtime_owner",
                "PGDATABASE": "postgres",
                "PGPASSFILE": str(passfile),
                "PGSSLMODE": "verify-full",
                "PGSSLROOTCERT": str(cert),
                "PGCLIENTENCODING": "UTF8",
            }
        )
        started = False
        try:
            run("pg_ctl", ["start", "-D", data, "-l", root / "postgres.log", "-w", "-t", "30"])
            started = True

            def sql(statement, *, database="postgres", reader=False, check=True):
                return run(
                    "psql",
                    ["-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                    input=statement,
                    env={
                        **environment,
                        "PGDATABASE": database,
                        "PGUSER": "runtime_reader" if reader else "runtime_owner",
                    },
                    check=check,
                )

            sql(f"""
CREATE EXTENSION vector;
CREATE ROLE runtime_reader LOGIN PASSWORD '{reader_password}';
CREATE TABLE memories (owner text NOT NULL, embedding vector(3), content text);
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories FORCE ROW LEVEL SECURITY;
CREATE POLICY own_memories ON memories USING (owner = current_user) WITH CHECK (owner = current_user);
GRANT SELECT, INSERT ON memories TO runtime_reader;
INSERT INTO memories VALUES ('runtime_reader', '[1,0,0]', 'café memory'), ('another_team', '[0,1,0]', 'private other team');
CREATE INDEX memories_vectors ON memories USING hnsw (embedding vector_cosine_ops);
""")
            identity = json.loads(
                sql(
                    "SELECT json_build_object('directory', current_setting('data_directory'), 'vector', (SELECT extversion FROM pg_extension WHERE extname='vector'), 'tls', (SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()), 'checksums', current_setting('data_checksums'));"
                ).stdout
            )
            if (
                Path(identity["directory"]).resolve() != data.resolve()
                or not identity["tls"]
                or identity["checksums"] != "on"
            ):
                raise ValueError("Database identity, verified TLS or checksums are incorrect")
            if identity["vector"] != metadata["sources"]["pgvector"]["version"]:
                raise ValueError("Loaded vector extension differs from the pinned source")

            def verify_reader(database="postgres"):
                value = json.loads(
                    sql(
                        "SELECT json_build_object('count', count(*), 'distance', min(embedding <=> '[1,0,0]')) FROM memories;",
                        database=database,
                        reader=True,
                    ).stdout
                )
                if value != {"count": 1, "distance": 0}:
                    raise ValueError("Native vector query or organization isolation failed")
                rejected = sql(
                    "INSERT INTO memories VALUES ('another_team', '[1,1,0]', 'unauthorized');",
                    database=database,
                    reader=True,
                    check=False,
                )
                if rejected.returncode != 3 or "row-level security" not in rejected.stderr:
                    raise ValueError(
                        "An unauthorized native database write was not rejected by RLS"
                    )

            verify_reader()
            backup = root / "Verified memory backup.dump"
            run("pg_dump", ["--format=custom", "--compress=gzip:6", "--file", backup])
            run("createdb", ["restored_workspace"])
            run("pg_restore", ["--exit-on-error", "--dbname=restored_workspace", backup])
            verify_reader("restored_workspace")
            run("pg_ctl", ["stop", "-D", data, "-m", "immediate", "-w", "-t", "30"])
            started = False
            run("pg_ctl", ["start", "-D", data, "-l", root / "postgres.log", "-w", "-t", "30"])
            started = True
            verify_reader()
            verify_reader("restored_workspace")
            result = {
                "passed": True,
                "postgresql": pg_version,
                "pgvector": identity["vector"],
                "openssl": ssl_version,
                "platform": expected_os,
                "host_architecture": host_arch,
                "runtime_architecture": architecture,
                "emulated": architecture != host_arch,
                "relocated_path_with_spaces": True,
                "unicode_data_path": True,
                "file_inventory_verified": True,
                "tls_certificate_verified": True,
                "data_checksums": True,
                "vector_search": True,
                "rls_read_isolation": True,
                "rls_write_rejected": True,
                "gzip_backup_restored": True,
                "immediate_shutdown_recovery": True,
                "scope": "Disposable local database; app installation and complete service/model setup are separate gates.",
            }
        finally:
            # Even a failed start may have created the postmaster; stop only our
            # disposable data directory, never a PID discovered outside it.
            if started or (data / "postmaster.pid").exists():
                run("pg_ctl", ["stop", "-D", data, "-m", "fast", "-w", "-t", "30"], check=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.archive.resolve(), args.output.resolve())))


if __name__ == "__main__":
    main()
