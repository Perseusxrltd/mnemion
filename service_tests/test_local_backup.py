"""Real snapshot/ledger encryption with an isolated native-owner adapter."""

import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from mnemion import backup_encryption as encryption, local_backup as backup, local_state as state
from mnemion.local_workspace import SetupOptions
from mnemion.service import recovery
from mnemion.service.models import MemoryInput


def owner_adapter(env, tmp_path, monkeypatch):
    root = state.directory(tmp_path / "Workspace équipe")
    destination = tmp_path / "Synchronized backups"
    destination.mkdir()
    settings = {
        "format": 1,
        "workspace_id": str(uuid4()),
        "created_at": "2026-10-15T00:00:00Z",
        **SetupOptions(
            workspace_name="Recovery fixture", owner_name="Independent owner"
        ).model_dump(),
        "database_port": 17893,
    }
    credentials = {
        "tenant_id": str(env.owner.tenant_id),
        "api_key": env.token,
        "owner_password": "private fixture database password",
    }
    state.write(root / "configuration.json", settings)
    state.write(root / "credentials.json", credentials)
    # The PostgreSQL fixture has its own real owner login. Native TLS/process
    # identity is exercised by the local-database and installed-hosting gates.
    native = SimpleNamespace(dsn=lambda: env.admin_dsn)
    monkeypatch.setattr(backup, "_database", lambda *args: (native, settings, credentials))
    request = backup.BackupRequest.model_validate_json(
        json.dumps(
            {
                "workspace_id": settings["workspace_id"],
                "destination": str(destination),
                "recovery_key": encryption.new_key(),
            }
        )
    )
    return root, destination, settings, credentials, request


def test_encrypted_snapshot_and_newer_ledger_restore_deleted_state_without_source_mutation(
    env, pg_bin, tmp_path, monkeypatch
):
    root, destination, settings, credentials, request = owner_adapter(env, tmp_path, monkeypatch)
    memory = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Recover this synthetic project memory"),
        "native-backup-memory",
    )
    # Hosted CI shares one database between tenant fixtures. A native-owner
    # snapshot intentionally contains that complete database, including other
    # fixtures' memories and deletion history.
    with psycopg.connect(env.admin_dsn) as connection:
        source_memories = {
            (str(tenant), str(identifier))
            for tenant, identifier in connection.execute(
                "SELECT tenant_id,id FROM mnemion.memories"
            )
        }
    original_configuration = (root / "configuration.json").read_bytes()
    original_credentials = (root / "credentials.json").read_bytes()
    progress = []
    snapshot = backup.capture(root, pg_bin.parent, request, emit=progress.append)
    key = request.recovery_key.get_secret_value()
    selected = backup.BackupInspection(source=snapshot["snapshot"]["file"], recovery_key=key)
    inspected = backup.inspect_file(root, selected)
    assert inspected["archive_verified"] and inspected["memory_count"] == len(source_memories)
    assert inspected["context"]["local_workspace"]["workspace_id"] == settings["workspace_id"]
    assert inspected["context"]["local_workspace"]["primary_tenant_id"] == str(env.owner.tenant_id)
    assert progress[-1]["stage"] == "complete"
    env.memory.forget(
        env.owner,
        UUID(memory["memory_id"]),
        expected_version=1,
        key="deleted-after-native-snapshot",
    )
    latest = backup.capture(root, pg_bin.parent, request, ledger_only=True)
    with psycopg.connect(env.admin_dsn, row_factory=psycopg.rows.dict_row) as connection:
        current_ledger = recovery._ledger(connection)
    assert "snapshot" not in latest
    assert state.read(root / "last-backup.json") == snapshot
    assert state.read(root / "last-ledger.json") == latest
    assert backup.inspect_file(
        root, backup.BackupInspection(source=latest["ledger"]["file"], recovery_key=key)
    )["deletion_count"] == len(current_ledger["deletions"])
    raw_snapshot, raw_ledger = tmp_path / "unlocked-snapshot", tmp_path / "unlocked-ledger"
    encryption.decrypt_file(
        Path(snapshot["snapshot"]["file"]), raw_snapshot, key, expected_kind="snapshot"
    )
    encryption.decrypt_file(Path(latest["ledger"]["file"]), raw_ledger, key, expected_kind="ledger")
    database = "native_recovered_" + uuid4().hex
    try:
        restored = recovery.restore_backup(
            env.admin_dsn,
            raw_snapshot,
            database_name=database,
            deletion_ledger=raw_ledger,
            credentials_output=tmp_path / "new-owner.json",
            pg_bin=pg_bin,
        )
        assert restored["keys_rotated"]
        assert restored["deletions_reconciled"] == sum(
            (entry["tenant_id"], entry["memory_id"]) in source_memories
            for entry in current_ledger["deletions"]
        )
        with psycopg.connect(make_conninfo(env.admin_dsn, dbname=database)) as connection:
            assert connection.execute(
                "SELECT deleted_at IS NOT NULL FROM mnemion.memories WHERE id=%s",
                (memory["memory_id"],),
            ).fetchone()[0]
            assert (
                connection.execute(
                    "SELECT count(*) FROM mnemion.memory_revisions WHERE memory_id=%s",
                    (memory["memory_id"],),
                ).fetchone()[0]
                == 0
            )
    finally:
        with psycopg.connect(env.admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
            )
    public = json.dumps([snapshot, latest, inspected, progress])
    assert all(secret not in public for secret in (key, env.token, credentials["owner_password"]))
    assert (root / "configuration.json").read_bytes() == original_configuration
    assert (root / "credentials.json").read_bytes() == original_credentials
    files = [path for path in destination.rglob("*") if path.is_file()]
    assert len(files) == 3 and all(path.name.endswith(".mnemion.enc") for path in files)
    assert not list((root / "backup-operations").glob("capture-*"))
    assert not list((root / "backup-operations").glob("inspect-*"))


def test_capture_refuses_busy_or_cancelled_work_without_changing_last_success(
    env, pg_bin, tmp_path, monkeypatch
):
    root, destination, _, _, request = owner_adapter(env, tmp_path, monkeypatch)
    before = {"previous": "verified backup remains available"}
    state.write(root / "last-backup.json", before)
    with state.lock(backup._control(root)), pytest.raises(state.LocalSetupError, match="session"):
        backup.capture(root, pg_bin.parent, request)
    with pytest.raises(recovery.RecoveryCancelled):
        backup.capture(root, pg_bin.parent, request, cancelled=lambda: True)
    assert state.read(root / "last-backup.json") == before
    assert not list(destination.iterdir())


def test_automatic_retention_preserves_a_restorable_snapshot_and_newest_ledger(
    env, pg_bin, tmp_path, monkeypatch
):
    from mnemion.backup_retention import RetentionPolicy

    root, _, _, _, request = owner_adapter(env, tmp_path, monkeypatch)
    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Retained recovery point from the retention acceptance fixture"),
        "retention-recovery-memory",
    )
    original = [backup.capture(root, pg_bin.parent, request) for _ in range(3)]
    limited = request.model_copy(
        update={"retention": RetentionPolicy(mode="limited", snapshots=2, ledgers=2)}
    )
    ledger = backup.capture(root, pg_bin.parent, limited, ledger_only=True)
    assert "retention" not in ledger
    assert all(Path(record["snapshot"]["file"]).exists() for record in original)
    latest = backup.capture(root, pg_bin.parent, limited)
    assert latest["retention"]["state"] == "complete"
    assert latest["retention"]["deleted_files"] == 4
    assert state.read(root / "last-backup.json") == latest
    assert not Path(original[0]["snapshot"]["file"]).exists()
    assert not Path(original[1]["snapshot"]["file"]).exists()
    assert Path(original[2]["snapshot"]["file"]).exists()
    key = request.recovery_key.get_secret_value()
    snapshot_file, ledger_file = tmp_path / "retained.snapshot", tmp_path / "retained.ledger"
    encryption.decrypt_file(
        Path(latest["snapshot"]["file"]), snapshot_file, key, expected_kind="snapshot"
    )
    encryption.decrypt_file(
        Path(latest["ledger"]["file"]), ledger_file, key, expected_kind="ledger"
    )
    database = "retention_restored_" + uuid4().hex
    try:
        restored = recovery.restore_backup(
            env.admin_dsn,
            snapshot_file,
            database_name=database,
            deletion_ledger=ledger_file,
            credentials_output=tmp_path / "retained-owner.json",
            pg_bin=pg_bin,
        )
        assert restored["keys_rotated"]
        with psycopg.connect(make_conninfo(env.admin_dsn, dbname=database)) as connection:
            assert (
                connection.execute(
                    "SELECT r.content FROM mnemion.memories m JOIN mnemion.memory_revisions r "
                    "ON r.tenant_id=m.tenant_id AND r.id=m.current_revision_id WHERE m.id=%s",
                    (saved["memory_id"],),
                ).fetchone()[0]
                == "Retained recovery point from the retention acceptance fixture"
            )
    finally:
        with psycopg.connect(env.admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
            )


def test_destination_is_outside_local_data_and_never_follows_managed_links(tmp_path):
    root = state.directory(tmp_path / "host")
    identifier = str(uuid4())
    with pytest.raises(state.LocalSetupError, match="outside"):
        backup._destination(root, str(root), identifier)
    destination = tmp_path / "backups"
    destination.mkdir()
    foreign = tmp_path / "unrelated"
    foreign.mkdir()
    try:
        (destination / "Mnemion backups").symlink_to(foreign, target_is_directory=True)
    except OSError:
        pytest.skip("Creating a directory link requires unavailable OS permission")
    with pytest.raises(state.LocalSetupError, match="link"):
        backup._destination(root, str(destination), identifier)
    assert not list(foreign.iterdir())


def test_private_cli_inspection_accepts_one_shot_stdin_and_masks_bad_keys(
    env, pg_bin, tmp_path, monkeypatch
):
    root, _, _, _, request = owner_adapter(env, tmp_path, monkeypatch)
    record = backup.capture(root, pg_bin.parent, request, ledger_only=True)
    command = [
        sys.executable,
        "-m",
        "mnemion.service.cli",
        "local",
        "backup-inspect",
        "--root",
        str(root),
    ]
    key = request.recovery_key.get_secret_value()
    result = subprocess.run(
        command,
        input=json.dumps({"source": record["ledger"]["file"], "recovery_key": key}) + "\n",
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["inspection"]["authenticated"]
    assert key not in result.stdout + result.stderr
    malformed = "private-key-input-that-must-not-be-returned"
    failed = subprocess.run(
        command,
        input=json.dumps({"source": record["ledger"]["file"], "recovery_key": malformed}) + "\n",
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["code"] == "backup_options"
    assert malformed not in failed.stdout + failed.stderr


def test_snapshot_context_contains_only_explicit_nonsecret_setup_fields():
    value = backup.LocalBackupContext.model_validate_json(
        json.dumps(
            {
                "workspace_id": str(uuid4()),
                "primary_tenant_id": str(uuid4()),
                "workspace_name": "Example",
                "owner_name": "Owner",
                "embedding_profile": "bge-small-en",
                "threads": 2,
                "application_version": "4.4.0",
                "provider_token": "not part of a recovery preview",
            }
        )
    )
    assert "provider_token" not in value.model_dump()


@pytest.mark.parametrize("reason", ["cancelled", "deadline"])
def test_database_tool_cancellation_reaps_its_owned_child(tmp_path, monkeypatch, reason):
    import time

    processes = []
    original = recovery.subprocess.Popen

    def start(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(recovery.subprocess, "Popen", start)
    monkeypatch.setattr(recovery, "_pg_tool", lambda *args: sys.executable)
    monkeypatch.setattr(recovery, "_pg_environment", lambda *args: None)
    started = time.monotonic()
    expected = recovery.RecoveryCancelled if reason == "cancelled" else TimeoutError
    with pytest.raises(expected):
        recovery._run_pg(
            "pg_dump",
            "fixture",
            ["-c", "import time; time.sleep(60)"],
            None,
            cancelled=(lambda: time.monotonic() - started > 0.05)
            if reason == "cancelled"
            else None,
            maximum_seconds=0.05 if reason == "deadline" else 5,
        )
    assert len(processes) == 1 and processes[0].poll() is not None


def test_cancellation_interrupts_only_the_backup_query(env):
    stop = threading.Event()
    timer = threading.Timer(0.1, stop.set)
    timer.start()
    try:
        with (
            psycopg.connect(env.admin_dsn) as connection,
            pytest.raises(recovery.RecoveryCancelled),
        ):
            with recovery._cancel_queries(connection, stop.is_set):
                connection.execute("SELECT pg_sleep(10)")
    finally:
        timer.join(timeout=2)
    with psycopg.connect(env.admin_dsn) as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
