"""Real database/host loss with encrypted off-host copies and stable identities."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import venv
from uuid import UUID, uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

from mnemion import backup_encryption
from mnemion.archives import canonical_json, private_json, write_archive
from mnemion.service import host_package, host_recovery, service_updates, supervision
from mnemion.service.connector_models import BindingInput, ConnectorInput
from mnemion.service.connectors import ConnectorService
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.host_package import HostRecoveryError
from mnemion.service.memory import MemoryService
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput

pytestmark = pytest.mark.skipif(os.name != "posix", reason="This host uses Unix supervision")


def application(env, name):
    principal = env.identities.create_principal(env.owner, PrincipalInput(name=name))
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name=name))
    return UUID(principal["id"]), key


@pytest.fixture
def host_fixture(env, postgres, pg_bin, tmp_path):
    origin = tmp_path / "source-host"
    origin.mkdir(mode=0o700)
    roles = origin / "roles.json"
    private_json(
        roles,
        {
            "database_url": postgres[1],
            "worker_database_url": postgres[2],
            "admin_database_url": postgres[0],
        },
    )
    settings_file = origin / "provider-secrets.json"
    private_json(settings_file, {"api_key_env": "HOST_FIXTURE_SECRET"})
    environment = origin / "environment.json"
    private_json(
        environment,
        {
            "MNEMION_MODEL_OFFLINE": "1",
            "MNEMION_EVALUATIONS_DISABLED": "1",
            "MNEMION_LIBRARIAN_DISABLED": "1",
            "MNEMION_FIXTURE_CONFIG": str(settings_file),
            "HOST_FIXTURE_SECRET": "synthetic-provider-secret-never-public",
        },
    )
    principal, key = application(env, "Retained assistant")
    env.identities.grant(env.owner, env.space, principal, GrantInput(role="contributor"))
    source_principal, source_key = application(env, "Filesystem source")
    service = ConnectorService(env.memory)
    connector = service.create(
        env.owner,
        ConnectorInput(
            name="Portable source",
            provider="filesystem",
            access_mode="published",
            principal_id=source_principal,
        ),
    )
    service.binding(
        env.owner,
        UUID(connector["id"]),
        BindingInput(external_id="staff:fixture", principal_id=principal, role="reader"),
    )
    notes = tmp_path / "independent-notes"
    notes.mkdir()
    (notes / "office.md").write_text("# Office\nThe source survived on independent storage.\n")
    token_file = origin / "source.key"
    token_file.write_text(source_key["api_key"])
    token_file.chmod(0o600)
    config = origin / "connector.json"
    private_json(
        config,
        {
            "service_url": "http://127.0.0.1",
            "service_token": {"file": str(token_file)},
            "connector_id": connector["id"],
            "poll_seconds": 30,
            "provider": {
                "type": "filesystem",
                "path": str(notes),
                "scope_id": "office-files",
                "name": "Office files",
                "members": ["staff:fixture"],
                "publish_to_mapped_members": True,
            },
        },
    )
    state = origin / "state"
    supervision.prepare(
        state,
        roles,
        roles,
        environment=environment,
        public_url="https://memory.example.com",
        connector_configs=(config,),
    )
    copies = tmp_path / "independent-recovery"
    copies.mkdir(mode=0o700)
    key_file = copies / "recovery.key"
    host_package.create_key(key_file)
    saved = env.memory.save(
        env.owner, env.space, MemoryInput(content="Kept native office memory"), "native-host-memory"
    )
    package = copies / "office.mnemion-host"
    report = host_package.snapshot(
        state, package, key_file, admin=roles, pg_bin=pg_bin, plan_output=copies / "plan.json"
    )
    destination = tmp_path / "restored-host"
    database_name = "host_recovery_" + uuid4().hex
    value = {
        "origin": origin,
        "state": state,
        "roles": roles,
        "package": package,
        "key_file": key_file,
        "report": report,
        "destination": destination,
        "database": database_name,
        "key": key,
        "principal": principal,
        "source_key": source_key,
        "source_principal": source_principal,
        "connector_id": connector["id"],
        "memory_id": saved["memory_id"],
        "notes": notes,
    }
    try:
        yield value
    finally:
        target = destination / "service"
        if (target / "settings.json").exists():
            assert supervision.stop(target)["stopped"]
        with psycopg.connect(postgres[0], autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
            if (destination / "database-credentials.json").exists():
                for dsn in json.loads(
                    (destination / "database-credentials.json").read_text()
                ).values():
                    connection.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(
                            sql.Identifier(conninfo_to_dict(dsn)["user"])
                        )
                    )


def apply(host, postgres, pg_bin, **options):
    return host_recovery.restore(
        host["package"],
        host["key_file"],
        host["destination"],
        operator_dsn=postgres[0],
        database_name=host["database"],
        expected_sha256=host["report"]["sha256"],
        pg_bin=pg_bin,
        **options,
    )


def test_production_host_package_can_be_inspected_by_a_native_desktop(host_fixture, tmp_path):
    from mnemion.local_backup import BackupInspection, inspect_file

    host = host_fixture
    result = inspect_file(
        tmp_path / "desktop-inspection",
        BackupInspection(
            source=str(host["package"]), recovery_key=host_package.key_file(host["key_file"])
        ),
    )
    assert result["kind"] == "host" and result["authenticated"] and result["archive_verified"]
    assert result["sha256"] == host["report"]["sha256"]
    assert result["host_package"]["source_connectors"] == 1
    assert result["host_package"]["private_files"] >= 1
    assert result["host_package"]["host_configuration_restored"] is False
    serialized = json.dumps(result)
    assert "synthetic-provider-secret-never-public" not in serialized
    assert host["key"]["api_key"] not in serialized
    assert host["source_key"]["api_key"] not in serialized


def test_encrypted_host_loss_restores_source_runners_and_survives_second_database_loss(
    env,
    host_fixture,
    postgres,
    pg_bin,
):
    host = host_fixture
    public = json.dumps(host["report"])
    inspected = host_package.inspect(host["package"], host["key_file"])
    assert inspected["authenticated"] and not inspected["database_restore_verified"]
    assert inspected["plan"]["connectors"] == [
        {"id": host["connector_id"], "provider": "filesystem"}
    ]
    for secret in (
        env.token,
        host["key"]["api_key"],
        host["source_key"]["api_key"],
        "synthetic-provider-secret-never-public",
        postgres[0],
    ):
        assert secret not in public
        assert secret.encode() not in host["package"].read_bytes()
    assert "https://memory.example.com" not in public
    shutil.rmtree(host["origin"])
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    uv_command = shutil.which("uv")
    assert uv_command, "Install the pinned free uv package manager for host recovery tests"
    uv = Path(uv_command)
    result = apply(host, postgres, pg_bin, access_policy="preserve_applications", port=port, uv=uv)
    assert result["restored"] and result["supervised_connectors"] == 1
    assert result["status"]["updates"] == {"mode": "managed", "enabled": True}
    assert result["status"]["remote_access"]["public_origin_configured"]
    assert not result["external_transport_restored"]
    roles = json.loads((host["destination"] / "database-credentials.json").read_text())
    database = Database(roles["database_url"])
    try:
        database.open()
        restored = database.authenticate(host["key"]["api_key"])
        assert restored.principal_id == host["principal"]
        assert restored.tenant_id == env.owner.tenant_id
        memory = MemoryService(database, env.embedder.generation)
        assert (
            memory.fetch(restored, UUID(host["memory_id"]))["content"]
            == "Kept native office memory"
        )
        with pytest.raises(ServiceError):
            database.authenticate(env.token)
    finally:
        database.close()
    state = host["destination"] / "service"
    service_updates.preferences(state, False)  # No external updater requests in this fixture.
    started = supervision.start(state)
    assert started["ready"], started
    current = supervision.status(state)
    assert len(current["processes"]) == 4
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        trust_env=False,
        headers={"Authorization": "Bearer " + host["key"]["api_key"]},
    ) as client:
        assert client.get("/v1/spaces").status_code == 200
        deadline = time.monotonic() + 25
        source_ingested = False
        while time.monotonic() < deadline:
            with psycopg.connect(roles["admin_database_url"]) as connection:
                source_ingested = (
                    connection.execute(
                        """SELECT 1 FROM mnemion.connector_scopes s JOIN mnemion.connector_runs r
                    ON r.tenant_id=s.tenant_id AND r.space_id=s.space_id
                    WHERE s.connector_id=%s AND r.state='completed'""",
                        (host["connector_id"],),
                    ).fetchone()
                    is not None
                )
            if source_ingested:
                break
            time.sleep(0.25)
        assert source_ingested
    assert supervision.stop(state)["stopped"]
    repeated = apply(
        host, postgres, pg_bin, access_policy="preserve_applications", port=port, uv=uv
    )
    assert repeated["already_restored"]
    with psycopg.connect(postgres[0], autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(host["database"]))
        )
        for dsn in roles.values():
            connection.execute(
                sql.SQL("DROP ROLE {}").format(sql.Identifier(conninfo_to_dict(dsn)["user"]))
            )
    repaired = apply(
        host, postgres, pg_bin, access_policy="preserve_applications", port=port, uv=uv
    )
    assert repaired["restored"] and not repaired["already_restored"]
    assert repaired["status"]["updates"] == {"mode": "managed", "enabled": False}
    database = Database(roles["database_url"])
    try:
        database.open()
        assert database.authenticate(host["key"]["api_key"]).principal_id == host["principal"]
    finally:
        database.close()


def test_restore_rotation_rekeys_included_connector_and_resumes_after_setup_failure(
    host_fixture, postgres, pg_bin, monkeypatch
):
    host = host_fixture
    real_prepare = supervision.prepare

    def interrupted(*args, **kwargs):
        real_prepare(*args, **kwargs)
        raise RuntimeError("injected setup interruption")

    monkeypatch.setenv("MNEMION_LIBRARIAN_UNEXPECTED", "operator-only-setting")
    monkeypatch.setattr(supervision, "prepare", interrupted)
    with pytest.raises(RuntimeError, match="injected setup"):
        apply(host, postgres, pg_bin, managed=False)
    assert host_recovery.status(host["destination"])["phase"] == "database_restored"
    monkeypatch.setattr(supervision, "prepare", real_prepare)
    worker = host["destination"] / "service/worker.json"
    original = worker.read_bytes()
    worker.write_text(json.dumps({"worker_database_url": "changed outside the recovery"}))
    with pytest.raises(HostRecoveryError, match="settings differ"):
        apply(host, postgres, pg_bin, managed=False)
    assert "changed outside the recovery" in worker.read_text()
    worker.write_bytes(original)
    result = apply(host, postgres, pg_bin, managed=False)
    assert result["supervised_connectors"] == 1
    roles = json.loads((host["destination"] / "database-credentials.json").read_text())
    token = (
        (host["destination"] / "connectors" / (host["connector_id"] + ".key")).read_text().strip()
    )
    database = Database(roles["database_url"])
    try:
        database.open()
        assert database.authenticate(token).principal_id == host["source_principal"]
        for old in (host["key"]["api_key"], host["source_key"]["api_key"]):
            with pytest.raises(ServiceError):
                database.authenticate(old)
    finally:
        database.close()
    assert result["status"]["updates"] == {"mode": "manual", "enabled": False}
    settings = supervision.settings(host["destination"] / "service")[1]
    assert "MNEMION_LIBRARIAN_UNEXPECTED" not in settings["environment"]


def test_cli_recovers_again_after_its_installed_environment_is_lost(
    host_fixture, postgres, pg_bin, tmp_path
):
    host = host_fixture
    command = ["-m", "mnemion.service.cli", "host"]
    generated = tmp_path / "separate-recovery.key"
    created = subprocess.run(
        [sys.executable, *command, "key", "--output", str(generated)],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["created"]
    assert generated.read_text().strip() not in created.stdout + created.stderr
    inspected = subprocess.run(
        [
            sys.executable,
            *command,
            "inspect",
            "--package",
            str(host["package"]),
            "--key-file",
            str(host["key_file"]),
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["sha256"] == host["report"]["sha256"]

    # A real separate interpreter, with the already installed dependencies so
    # this acceptance test needs no network/package downloads.
    installed = tmp_path / "lost-installation"
    venv.EnvBuilder(with_pip=False).create(installed)
    packages = (
        installed
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    (packages / "fixture-dependencies.pth").write_text(
        "\n".join(path for path in sys.path if path.endswith("site-packages")) + "\n"
    )
    operator = tmp_path / "operator-credentials.json"
    private_json(operator, {"admin_database_url": postgres[0]})
    arguments = [
        *command,
        "restore",
        "--package",
        str(host["package"]),
        "--key-file",
        str(host["key_file"]),
        "--destination",
        str(host["destination"]),
        "--database",
        host["database"],
        "--database-locale",
        "C",
        "--expect-sha256",
        host["report"]["sha256"],
        "--operator-credentials",
        str(operator),
        "--pg-bin",
        str(pg_bin),
        "--manual-updates",
    ]
    first = subprocess.run(
        [str(installed / "bin/python"), *arguments],
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["restored"]
    assert (
        json.loads((host["destination"] / "restore.json").read_text())["selection"][
            "database_locale"
        ]
        == "C"
    )
    with pytest.raises(HostRecoveryError, match="different reviewed recovery"):
        apply(host, postgres, pg_bin, managed=False, database_locale="C.UTF-8")
    state = host["destination"] / "service"
    assert supervision.settings(state)[1]["python"] == str(installed / "bin/python")
    receipt = (host["destination"] / "recovery-credentials.json").read_bytes()
    shutil.rmtree(installed)
    repaired = subprocess.run(
        [sys.executable, *arguments],
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert repaired.returncode == 0, repaired.stderr
    result = json.loads(repaired.stdout)
    assert result["restored"] and not result["already_restored"]
    assert "--state-dir" in result["startup"]["boot_command"]
    assert not result["startup_registration_restored"]
    assert (host["destination"] / "recovery-credentials.json").read_bytes() == receipt
    assert supervision.settings(state)[1]["python"] == sys.executable
    for secret in (host["key"]["api_key"], host["source_key"]["api_key"], postgres[0]):
        assert secret not in created.stdout + inspected.stdout + first.stdout + repaired.stdout


def test_authenticated_package_cannot_supply_shell_execution_overrides(
    host_fixture, postgres, pg_bin, tmp_path
):
    host = host_fixture
    marker = tmp_path / "executed"
    script = tmp_path / "shell-override.sh"
    script.write_text(f"touch '{marker}'\n")
    plaintext, encrypted = tmp_path / "altered.zip", tmp_path / "altered.mnemion-host"
    with host_package.opened(host["package"], host["key_file"]) as (saved, root, _):
        saved["environment"]["BASH_ENV"] = str(script)
        (root / "host.json").write_bytes(canonical_json(saved))
        members = {name: root / name for name in ("host.json", "database.mnemion", "ledger.json")}
        members.update(
            {"assets/" + item["id"]: root / "assets" / item["id"] for item in saved["assets"]}
        )
        write_archive(
            plaintext,
            members,
            {
                "format": host_package.FORMAT,
                "version": 1,
                "package_id": saved["plan"]["package_id"],
            },
        )
    receipt = backup_encryption.encrypt_file(
        plaintext,
        encrypted,
        host["key_file"].read_text().strip(),
        kind="bundle",
    )
    altered = {**host, "package": encrypted, "report": {"sha256": receipt.encrypted_sha256}}
    with pytest.raises(HostRecoveryError, match="shell overrides"):
        apply(altered, postgres, pg_bin, managed=False)
    assert not host["destination"].exists() and not marker.exists()
    with psycopg.connect(postgres[0]) as connection:
        assert not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (host["database"],)
        ).fetchone()


def test_runtime_database_endpoint_retains_server_trust_without_operator_credentials():
    operator = make_conninfo(
        host="/var/run/postgresql",
        hostaddr="192.0.2.1",
        port="5432",
        dbname="postgres",
        user="cluster-operator",
        password="operator-password",
        passfile="/private/operator.pgpass",
        sslcert="/private/operator.crt",
        sslkey="/private/operator.key",
        sslpassword="key-password",
        sslrootcert="/company/database-ca.pem",
        sslmode="verify-full",
        options="-c role=postgres",
    )
    result = conninfo_to_dict(
        host_recovery._runtime_connection(
            operator,
            "restored_office",
            "database.example.com",
            6543,
        )
    )
    assert result["host"] == "database.example.com" and result["port"] == "6543"
    assert result["dbname"] == "restored_office" and result["sslmode"] == "verify-full"
    assert result["sslrootcert"] == "/company/database-ca.pem"
    assert (
        not {
            "hostaddr",
            "user",
            "password",
            "passfile",
            "sslcert",
            "sslkey",
            "sslpassword",
            "options",
        }
        & result.keys()
    )


def test_unreviewed_package_and_existing_directory_do_not_mutate_database(
    host_fixture, postgres, pg_bin, tmp_path
):
    host = host_fixture
    wrong_key = tmp_path / "wrong.key"
    host_package.create_key(wrong_key)
    with pytest.raises(ValueError):
        host_package.inspect(host["package"], wrong_key)
    with pytest.raises(HostRecoveryError, match="differs"):
        host_recovery.restore(
            host["package"],
            host["key_file"],
            host["destination"],
            operator_dsn=postgres[0],
            database_name=host["database"],
            expected_sha256="0" * 64,
            managed=False,
            pg_bin=pg_bin,
        )
    assert not host["destination"].exists()
    host["destination"].mkdir(mode=0o700)
    (host["destination"] / "keep.txt").write_text("existing host data")
    with pytest.raises(HostRecoveryError, match="empty"):
        apply(host, postgres, pg_bin, managed=False)
    with psycopg.connect(postgres[0]) as connection:
        assert not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (host["database"],)
        ).fetchone()
    assert (host["destination"] / "keep.txt").read_text() == "existing host data"


def test_newer_encrypted_ledger_preserves_deletions_and_does_not_rekey_revoked_sources(
    env,
    host_fixture,
    postgres,
    pg_bin,
    tmp_path,
):
    host = host_fixture
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            "UPDATE mnemion.api_keys SET revoked_at=clock_timestamp() WHERE id IN (%s,%s)",
            (host["key"]["id"], host["source_key"]["id"]),
        )
    env.memory.forget(
        env.owner, UUID(host["memory_id"]), expected_version=1, key="deleted-after-host-package"
    )
    ledger = tmp_path / "newer.mnemion-ledger"
    receipt = host_package.export_ledger(
        host["state"], ledger, host["key_file"], admin=host["roles"]
    )
    result = apply(
        host,
        postgres,
        pg_bin,
        managed=False,
        access_policy="preserve_applications",
        latest_ledger=ledger,
        ledger_sha256=receipt["sha256"],
    )
    assert result["ledger_at"] == receipt["snapshot_at"]
    assert result["supervised_connectors"] == 0
    assert result["inactive_connector_ids"] == [host["connector_id"]]
    roles = json.loads((host["destination"] / "database-credentials.json").read_text())
    database = Database(roles["database_url"])
    try:
        database.open()
        for rejected in (host["key"]["api_key"], host["source_key"]["api_key"]):
            with pytest.raises(ServiceError):
                database.authenticate(rejected)
        owner_data = json.loads(Path(result["recovery_credentials_file"]).read_text())
        owner = database.authenticate(
            next(
                item["api_key"]
                for item in owner_data["organizations"]
                if item["tenant_id"] == str(env.owner.tenant_id)
            )
        )
        with pytest.raises(ServiceError):
            MemoryService(database, env.embedder.generation).fetch(owner, UUID(host["memory_id"]))
        with psycopg.connect(roles["admin_database_url"]) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM mnemion.api_keys WHERE tenant_id=%s AND principal_id=%s AND revoked_at IS NULL",
                    (env.owner.tenant_id, host["source_principal"]),
                ).fetchone()[0]
                == 0
            )
    finally:
        database.close()


KEPT_REMOTE = "https://example.invalid/kept.git"
OTHER_REMOTE = "https://example.invalid/other.git"


def _private_git_home(monkeypatch, home: Path) -> None:
    """Isolate Git through HOME. Inspection drops GIT_CONFIG_GLOBAL and GIT_CONFIG_NOSYSTEM."""
    (home / ".config" / "git").mkdir(parents=True)
    (home / ".gitconfig").write_text("")
    (home / ".config" / "git" / "config").write_text("")
    monkeypatch.setenv("HOME", str(home))
    for name in (
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_NOSYSTEM",
        "XDG_CONFIG_HOME",
        "GIT_DIR",
        "GIT_WORK_TREE",
    ):
        monkeypatch.delenv(name, raising=False)


def _git(*args) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True, timeout=30)


def _bare_cache(path: Path, origin: str) -> None:
    template = path.parent / "empty-template"
    template.mkdir(exist_ok=True)
    _git("init", "--bare", "--template", str(template), str(path))
    _git(
        "-c",
        "core.hooksPath=" + os.devnull,
        "-C",
        str(path),
        "remote",
        "add",
        "origin",
        origin,
    )


def _git_connector(origin, service, principal, key, root, directory, remote, ref):
    created = service.create(
        origin,
        ConnectorInput(
            name=directory,
            provider="git",
            access_mode="published",
            principal_id=principal,
        ),
    )
    token_file = root / (directory + ".key")
    token_file.write_text(key["api_key"])
    token_file.chmod(0o600)
    config = root / (directory + ".json")
    private_json(
        config,
        {
            "service_url": "http://127.0.0.1",
            "service_token": {"file": str(token_file)},
            "connector_id": created["id"],
            "poll_seconds": 30,
            "provider": {
                "type": "git",
                "path": str(root / "saved-caches" / (directory + ".git")),
                "remote": remote,
                "ref": ref,
                "scope_id": directory,
                "name": directory,
                "members": ["staff:" + directory],
                "publish_to_mapped_members": True,
            },
        },
    )
    return created["id"], config


@pytest.mark.parametrize("access_policy", ["preserve_applications", "rotate_all"])
def test_newer_ledger_omits_ineligible_git_caches_and_keeps_the_pinned_restore(
    env, postgres, pg_bin, tmp_path, monkeypatch, access_policy
):
    """Extend the newer-ledger rule with real keys, not a mocked eligibility flag.

    An enabled connection whose saved key is absent from the newer key ledger,
    and a saved connection absent from the newer connection ledger, each have an
    unusable remote Git cache. An unrelated active key stays in that ledger.
    The eligible cache fails before any source key; repairing that same path
    resumes the original selection.
    """
    if shutil.which("git") is None:
        pytest.skip("Install Git to exercise native Git cache inspection")
    _private_git_home(monkeypatch, tmp_path / "git-home")
    source = tmp_path / "source-host"
    source.mkdir(mode=0o700)
    saved_root = source / "saved-caches"
    live_root = tmp_path / "live-caches"
    live_root.mkdir()
    for name in ("kept", "unlisted", "absent"):
        _bare_cache(live_root / (name + ".git"), OTHER_REMOTE)
    roles = source / "roles.json"
    private_json(
        roles,
        {
            "database_url": postgres[1],
            "worker_database_url": postgres[2],
            "admin_database_url": postgres[0],
        },
    )
    environment = source / "environment.json"
    private_json(
        environment,
        {
            "MNEMION_MODEL_OFFLINE": "1",
            "MNEMION_EVALUATIONS_DISABLED": "1",
            "MNEMION_LIBRARIAN_DISABLED": "1",
        },
    )
    service = ConnectorService(env.memory)
    kept_principal, kept_key = application(env, "Kept git source")
    unlisted_principal, unlisted_key = application(env, "Unlisted git key")
    absent_principal, absent_key = application(env, "Absent git connection")
    _, unrelated_key = application(env, "Unrelated application")
    kept_id, kept_config = _git_connector(
        env.owner, service, kept_principal, kept_key, source, "kept", KEPT_REMOTE, "main"
    )
    unlisted_id, unlisted_config = _git_connector(
        env.owner,
        service,
        unlisted_principal,
        unlisted_key,
        source,
        "unlisted",
        KEPT_REMOTE,
        "main",
    )
    absent_id, absent_config = _git_connector(
        env.owner, service, absent_principal, absent_key, source, "absent", KEPT_REMOTE, "main"
    )
    state = source / "state"
    supervision.prepare(
        state,
        roles,
        roles,
        environment=environment,
        public_url="https://memory.example.com",
        connector_configs=(kept_config, unlisted_config, absent_config),
    )
    copies = tmp_path / "copies"
    copies.mkdir(mode=0o700)
    key_file = copies / "recovery.key"
    host_package.create_key(key_file)
    package = copies / "office.mnemion-host"
    report = host_package.snapshot(
        state, package, key_file, admin=roles, pg_bin=pg_bin, plan_output=copies / "plan.json"
    )
    plain = copies / "ledger.json"
    host_recovery.recovery.export_ledger(postgres[0], plain)
    payload = json.loads(plain.read_text(encoding="utf-8"))
    payload.pop("sha256", None)
    payload["application_key_state"]["keys"] = [
        row for row in payload["application_key_state"]["keys"] if row["id"] != unlisted_key["id"]
    ]
    payload["connector_state"]["connections"] = [
        row for row in payload["connector_state"]["connections"] if row["id"] != absent_id
    ]
    payload["sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    # private_json publishes exclusively, so the exported ledger.json stays intact.
    newer_plain = copies / "newer-ledger.json"
    private_json(newer_plain, payload)
    encrypted = copies / "newer.mnemion-ledger"
    receipt = backup_encryption.encrypt_file(
        newer_plain, encrypted, key_file.read_text(encoding="utf-8").strip(), kind="ledger"
    )
    with host_package.opened_ledger(encrypted, key_file, receipt.encrypted_sha256) as (_, loaded):
        key_ids = {row["id"] for row in loaded["application_key_state"]["keys"]}
        assert unrelated_key["id"] in key_ids
        assert kept_key["id"] in key_ids
        assert absent_key["id"] in key_ids
        assert unlisted_key["id"] not in key_ids
        assert len(key_ids) >= 3
        listed = {row["id"]: row["disabled_at"] for row in loaded["connector_state"]["connections"]}
        assert absent_id not in listed
        assert listed[kept_id] is None and listed[unlisted_id] is None
    destination = tmp_path / "restored-host"
    database_name = "host_eligibility_" + uuid4().hex
    mapping = (str(saved_root), str(live_root))

    def restore_with(path_mapping):
        return host_recovery.restore(
            package,
            key_file,
            destination,
            operator_dsn=postgres[0],
            database_name=database_name,
            expected_sha256=report["sha256"],
            pg_bin=pg_bin,
            managed=False,
            access_policy=access_policy,
            latest_ledger=encrypted,
            ledger_sha256=receipt.encrypted_sha256,
            path_mappings=[path_mapping],
        )

    try:
        with pytest.raises(HostRecoveryError) as caught:
            restore_with(mapping)
        assert str(caught.value) == "provider.path: git_cache_remote_mismatch"
        assert KEPT_REMOTE not in str(caught.value)
        assert OTHER_REMOTE not in str(caught.value)
        assert str(live_root) not in str(caught.value)
        journal = json.loads((destination / "restore.json").read_text(encoding="utf-8"))
        assert journal["phase"] == "database_restored"
        assert journal["selection"]["mappings"] == [list(mapping)]
        assert journal["selection"]["access_policy"] == access_policy
        assert not (destination / "connectors").exists()
        assert not (destination / "service").exists()
        assert list(destination.rglob("*.key")) == []
        assert list(destination.rglob("connector-*-credentials.json")) == []
        elsewhere = tmp_path / "other-cache-root"
        elsewhere.mkdir()
        with pytest.raises(HostRecoveryError, match="different reviewed recovery"):
            restore_with((str(saved_root), str(elsewhere)))
        unchanged = json.loads((destination / "restore.json").read_text(encoding="utf-8"))
        assert unchanged["restore_id"] == journal["restore_id"]
        assert unchanged["phase"] == "database_restored"
        assert unchanged["selection"] == journal["selection"]
        _git(
            "-c",
            "core.hooksPath=" + os.devnull,
            "-C",
            str(live_root / "kept.git"),
            "remote",
            "set-url",
            "origin",
            KEPT_REMOTE,
        )
        result = restore_with(mapping)
        finished = json.loads((destination / "restore.json").read_text(encoding="utf-8"))
        assert finished["restore_id"] == journal["restore_id"]
        assert finished["selection"] == journal["selection"]
        assert finished["phase"] == "complete"
        assert result["inactive_connector_ids"] == [unlisted_id, absent_id]
        assert result["supervised_connectors"] == 1
        assert finished["connector_ids"] == [kept_id]
        restored = json.loads((destination / "connectors" / (kept_id + ".json")).read_text())
        assert restored["connector_id"] == kept_id
        assert restored["provider"]["ref"] == "main"
        assert restored["provider"]["remote"] == KEPT_REMOTE
        assert restored["provider"]["path"] == str(live_root / "kept.git")
        sources = destination / "connectors"
        assert (sources / (kept_id + ".key")).is_file()
        for omitted in (unlisted_id, absent_id):
            assert not (sources / (omitted + ".json")).exists()
            assert not (sources / (omitted + ".key")).exists()
            assert not (sources / ("connector-" + omitted + "-credentials.json")).exists()
        roles_out = json.loads((destination / "database-credentials.json").read_text())
        with psycopg.connect(roles_out["admin_database_url"]) as connection:
            kept_active = connection.execute(
                """SELECT count(*) FROM mnemion.api_keys
                WHERE principal_id=%s AND revoked_at IS NULL""",
                (kept_principal,),
            ).fetchone()[0]
            unlisted_active = connection.execute(
                """SELECT count(*) FROM mnemion.api_keys
                WHERE principal_id=%s AND revoked_at IS NULL""",
                (unlisted_principal,),
            ).fetchone()[0]
            unrelated_active = connection.execute(
                """SELECT count(*) FROM mnemion.api_keys
                WHERE principal_id=%s AND revoked_at IS NULL""",
                (unrelated_key["principal_id"],),
            ).fetchone()[0]
        assert kept_active == 1
        assert unlisted_active == 0
        if access_policy == "preserve_applications":
            assert unrelated_active == 1
        else:
            assert unrelated_active == 0
        kept_key_bytes = (sources / (kept_id + ".key")).read_bytes()
        again = restore_with(mapping)
        assert again["already_restored"] is True
        assert (sources / (kept_id + ".key")).read_bytes() == kept_key_bytes
        repeated = json.loads((destination / "restore.json").read_text(encoding="utf-8"))
        assert repeated["selection"] == journal["selection"]
        assert repeated["inactive_connector_ids"] == [unlisted_id, absent_id]
    finally:
        target = destination / "service"
        if (target / "settings.json").exists():
            assert supervision.stop(target)["stopped"]
        with psycopg.connect(postgres[0], autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
            credentials = destination / "database-credentials.json"
            if credentials.exists():
                for dsn in json.loads(credentials.read_text(encoding="utf-8")).values():
                    connection.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(
                            sql.Identifier(conninfo_to_dict(dsn)["user"])
                        )
                    )
