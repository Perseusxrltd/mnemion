"""Independent native restoration uses the bundled PostgreSQL runtime."""

import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import ValidationError

from mnemion import backup_encryption as encryption, local_backup, local_recovery, local_state
from mnemion.local_database import LocalDatabase, prepare_credentials
from mnemion.local_workspace import SetupOptions, configuration, initialize, inspect
from mnemion.service import recovery
from mnemion.service.models import MemoryInput
from service_tests.conftest import FixtureEmbedder


@pytest.fixture
def native_runtime():
    selected = os.environ.get("MNEMION_TEST_NATIVE_RECOVERY_RUNTIME")
    if not selected:
        pytest.skip("Requires bundled PostgreSQL with TLS and pgvector")
    runtime = Path(selected)
    assert (runtime / "bin" / ("postgres.exe" if os.name == "nt" else "postgres")).is_file()
    return runtime


@pytest.fixture
def encrypted_recovery(env, pg_bin, tmp_path):
    root = local_state.directory(tmp_path / "Original host")
    original = {"operator": "original workspace remains unchanged"}
    local_state.write(root / "configuration.json", original)
    kept = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="native recovery retained anchor"),
        "recovery-kept",
    )
    removed = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="deleted after native snapshot"),
        "recovery-deleted",
    )
    snapshot = tmp_path / "snapshot.zip"
    recovery.create_backup(
        env.admin_dsn,
        snapshot,
        pg_bin=pg_bin,
        context={
            "local_workspace": {
                "format": 1,
                "workspace_id": str(uuid4()),
                "primary_tenant_id": str(env.owner.tenant_id),
                "workspace_name": "Source équipe",
                "owner_name": "Independent operator",
                "embedding_profile": "bge-small-en",
                "threads": 1,
                "application_version": "4.4.0",
            }
        },
    )
    env.memory.forget(
        env.owner, UUID(removed["memory_id"]), expected_version=1, key="after-snapshot"
    )
    ledger = tmp_path / "ledger.json"
    recovery.export_ledger(env.admin_dsn, ledger)
    snapshot_key, ledger_key = encryption.new_key(), encryption.new_key()
    encrypted_snapshot, encrypted_ledger = tmp_path / "snapshot.enc", tmp_path / "ledger.enc"
    encrypted = encryption.encrypt_file(snapshot, encrypted_snapshot, snapshot_key, kind="snapshot")
    current = encryption.encrypt_file(ledger, encrypted_ledger, ledger_key, kind="ledger")
    values = {
        "source": str(encrypted_snapshot),
        "recovery_key": snapshot_key,
        "ledger_source": str(encrypted_ledger),
        "ledger_key": ledger_key,
        "snapshot_sha256": encrypted.encrypted_sha256,
        "ledger_sha256": current.encrypted_sha256,
        "destination": str(tmp_path / "Recovered équipe"),
        "primary_tenant_id": str(env.owner.tenant_id),
        "trusted_backup_confirmed": True,
    }
    return root, values, kept, removed, original


def test_native_recovery_reopens_with_fresh_credentials_and_preserves_original(
    env, native_runtime, encrypted_recovery, monkeypatch
):
    root, values, kept, removed, original = encrypted_recovery
    request = local_recovery.RecoveryRequest.model_validate_json(json.dumps(values))
    progress = []
    with psycopg.connect(env.admin_dsn) as source:
        original_zone = source.execute("SHOW TimeZone").fetchone()[0]
    with monkeypatch.context() as region:
        region.setenv("PGTZ", "UTC")
        result = local_recovery.restore(root, native_runtime, request, emit=progress.append)
    target = Path(request.destination)
    assert result["state"] == "restored" and result["keys_rotated"]
    assert result["external_connections_require_review"]
    assert result["tenant_id"] == str(env.owner.tenant_id)
    assert inspect(target)["configured"]
    credentials = prepare_credentials(target)
    assert credentials["api_key"] != env.token
    database = LocalDatabase(target, native_runtime, configuration(target), credentials)
    try:
        database.start()
        provisioned = database.provision(FixtureEmbedder.generation)
        assert provisioned["tenant_id"] == str(env.owner.tenant_id)
        with psycopg.connect(database.dsn()) as connection:
            assert connection.execute("SHOW TimeZone").fetchone()[0] == original_zone
            assert (
                connection.execute(
                    "SELECT r.content FROM mnemion.memories m JOIN mnemion.memory_revisions r ON r.tenant_id=m.tenant_id AND r.id=m.current_revision_id WHERE m.id=%s",
                    (kept["memory_id"],),
                ).fetchone()[0]
                == "native recovery retained anchor"
            )
            assert connection.execute(
                "SELECT deleted_at IS NOT NULL FROM mnemion.memories WHERE id=%s",
                (removed["memory_id"],),
            ).fetchone()[0]
            assert (
                connection.execute(
                    "SELECT count(*) FROM mnemion.memory_revisions WHERE memory_id=%s",
                    (removed["memory_id"],),
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT role FROM mnemion.space_grants WHERE tenant_id=%s AND space_id=%s AND principal_id=%s",
                    (env.owner.tenant_id, env.space, env.owner.principal_id),
                ).fetchone()[0]
                == "administrator"
            )
            assert connection.execute(
                "SELECT revoked_at IS NULL FROM mnemion.api_keys WHERE id=%s",
                (credentials["key_id"],),
            ).fetchone()[0]
        with psycopg.connect(database.dsn("api")) as connection:
            assert connection.execute("SELECT current_user").fetchone()[0] == "mnemion_api_login"
    finally:
        database.stop()
    assert local_state.read(root / "configuration.json") == original
    assert progress[-1]["stage"] == "complete"
    public = json.dumps([result, progress])
    assert all(
        key not in public
        for key in [values["recovery_key"], values["ledger_key"], credentials["api_key"], env.token]
    )
    assert not list((root / "backup-operations").glob("restore-*"))
    assert not (target / "remote-access.json").exists()


def test_native_restore_cancellation_stops_owned_database_and_keeps_original(
    native_runtime, encrypted_recovery
):
    root, values, _, _, original = encrypted_recovery
    stop = threading.Event()
    request = local_recovery.RecoveryRequest.model_validate_json(json.dumps(values))

    def cancel_before_restore(event):
        if event["stage"] == "restoring":
            stop.set()

    with pytest.raises(recovery.RecoveryCancelled):
        local_recovery.restore(
            root, native_runtime, request, cancelled=stop.is_set, emit=cancel_before_restore
        )
    target = Path(request.destination)
    database = LocalDatabase(
        target, native_runtime, configuration(target), prepare_credentials(target)
    )
    assert database.run("pg_ctl", ["status", "-D", database.data], check=False).returncode != 0
    assert local_state.read(target / "recovery.json")["state"] == "incomplete"
    assert local_state.read(root / "configuration.json") == original
    assert not list((root / "backup-operations").glob("restore-*"))


def test_restore_requires_confirmed_trust_and_both_valid_keys(encrypted_recovery):
    _, values, _, _, _ = encrypted_recovery
    for field, bad in (
        ("trusted_backup_confirmed", False),
        ("recovery_key", "bad"),
        ("ledger_key", "bad"),
    ):
        with pytest.raises(ValidationError):
            local_recovery.RecoveryRequest.model_validate_json(json.dumps({**values, field: bad}))


def test_restore_refuses_changed_selected_bytes_before_creating_a_host(
    encrypted_recovery, tmp_path
):
    root, values, _, _, original = encrypted_recovery
    request = local_recovery.RecoveryRequest.model_validate_json(
        json.dumps({**values, "snapshot_sha256": "0" * 64})
    )
    with pytest.raises(local_state.LocalSetupError, match="changed"):
        local_recovery.restore(root, tmp_path, request)
    assert not Path(request.destination).exists()
    assert local_state.read(root / "configuration.json") == original


def test_inspection_verifies_plaintext_inside_private_control_root(encrypted_recovery, monkeypatch):
    root, values, _, _, _ = encrypted_recovery
    original = local_backup.verified_archive
    inspected = []

    def verified(*args, **kwargs):
        inspected.append(kwargs["temporary_directory"])
        return original(*args, **kwargs)

    monkeypatch.setattr(local_backup, "verified_archive", verified)
    local_backup.inspect_file(
        root,
        local_backup.BackupInspection(source=values["source"], recovery_key=values["recovery_key"]),
    )
    assert inspected and all(path.is_relative_to(root / "backup-operations") for path in inspected)
    assert not list((root / "backup-operations").glob("inspect-*"))


def test_welcome_inspection_allows_first_setup_but_preserves_incomplete_work(
    encrypted_recovery, tmp_path
):
    _, values, _, _, _ = encrypted_recovery
    fresh = local_state.directory(tmp_path / "Fresh computer")
    local_backup.inspect_file(
        fresh,
        local_backup.BackupInspection(source=values["source"], recovery_key=values["recovery_key"]),
    )
    retained = fresh / "backup-operations" / "unfinished-recovery"
    retained.mkdir()
    (retained / "keep.txt").write_text("retained private recovery work")
    options = SetupOptions(workspace_name="New workspace", owner_name="Owner")
    with pytest.raises(local_state.LocalSetupError, match="already contains data"):
        initialize(fresh, options)
    assert (retained / "keep.txt").read_text() == "retained private recovery work"
    (retained / "keep.txt").unlink()
    retained.rmdir()
    assert initialize(fresh, options)["workspace_name"] == "New workspace"
    assert inspect(fresh)["configured"]


def test_recovery_refuses_full_private_staging_before_decrypting(encrypted_recovery, monkeypatch):
    root, values, _, _, original = encrypted_recovery
    monkeypatch.setattr(local_backup.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))

    def unexpected(*args, **kwargs):
        pytest.fail("Insufficient private disk space must be rejected before decryption")

    monkeypatch.setattr(encryption, "decrypt_file", unexpected)
    with pytest.raises(local_state.LocalSetupError, match="disk space"):
        local_recovery.restore(
            root, root, local_recovery.RecoveryRequest.model_validate_json(json.dumps(values))
        )
    assert local_state.read(root / "configuration.json") == original
    assert not Path(values["destination"]).exists()
