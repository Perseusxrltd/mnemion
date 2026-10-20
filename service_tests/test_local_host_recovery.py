"""Server backup inspection and isolated desktop recovery with real databases."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from pydantic import ValidationError

from deploy.native_host_backup_fixture import create
from mnemion import backup_encryption as encryption, local_backup, local_recovery, local_state
from mnemion.archives import canonical_json, file_hash
from mnemion.local_database import LocalDatabase, prepare_credentials
from mnemion.local_workspace import configuration
from mnemion.service import recovery
from service_tests.test_local_recovery import encrypted_recovery, native_runtime  # noqa: F401


@pytest.fixture
def host_copy(encrypted_recovery, tmp_path):  # noqa: F811
    root, values, kept, removed, original = encrypted_recovery
    ledger = tmp_path / "host-current-ledger.json"
    encryption.decrypt_file(
        Path(values["ledger_source"]), ledger, values["ledger_key"], expected_kind="ledger"
    )
    output = tmp_path / "Server équipe.mnemion-host"
    report = create(Path(values["source"]), values["recovery_key"], output, embedded_ledger=ledger)
    request = {
        **values,
        "source": str(output),
        "snapshot_sha256": report["sha256"],
        "source_kind": "host",
        "host_data_only_confirmed": True,
    }
    return root, request, kept, removed, original, report


def inspect(root, values):
    return local_backup.inspect_file(
        root,
        local_backup.BackupInspection(source=values["source"], recovery_key=values["recovery_key"]),
    )


def test_server_inspection_verifies_nested_inventory_and_excludes_host_secrets(host_copy):
    root, values, _, _, _, report = host_copy
    view = inspect(root, values)
    assert view["kind"] == "host" and view["archive_verified"] and view["authenticated"]
    assert view["sha256"] == report["sha256"]
    assert view["host_package"] == {
        "package_id": report["package_id"],
        "service_version": view["application_version"],
        "source_connectors": 0,
        "private_files": 1,
        "host_configuration_restored": False,
    }
    assert view["tenant_ids"] == [values["primary_tenant_id"]]
    assert view["memory_count"] == 2
    assert len(view["embedded_ledger_sha256"]) == 64
    assert all(
        secret not in json.dumps(view)
        for secret in (values["recovery_key"], "private-host-import-fixture-sentinel", "/old-host/")
    )
    assert not list((root / "backup-operations").glob("inspect-*"))


@pytest.mark.parametrize("embedded", [False, True])
def test_host_database_opens_natively_with_current_denials_and_fresh_access(
    env,
    native_runtime,  # noqa: F811
    host_copy,
    embedded,
):
    root, values, kept, removed, original, report = host_copy
    view = inspect(root, values)
    if embedded:
        values = {
            **values,
            "ledger_source": None,
            "ledger_key": None,
            "ledger_sha256": view["embedded_ledger_sha256"],
        }
    request = local_recovery.RecoveryRequest.model_validate_json(json.dumps(values))
    result = local_recovery.restore(root, native_runtime, request)
    assert result["host_package"] == {
        **view["host_package"],
        "ledger_source": "embedded" if embedded else "separate",
    }
    assert result["keys_rotated"] and result["external_connections_require_review"]
    target = Path(request.destination)
    credentials = prepare_credentials(target)
    database = LocalDatabase(target, native_runtime, configuration(target), credentials)
    try:
        database.start()
        with psycopg.connect(database.dsn()) as connection:
            assert (
                connection.execute(
                    "SELECT r.content FROM mnemion.memories m JOIN mnemion.memory_revisions r "
                    "ON r.tenant_id=m.tenant_id AND r.id=m.current_revision_id WHERE m.id=%s",
                    (UUID(kept["memory_id"]),),
                ).fetchone()[0]
                == "native recovery retained anchor"
            )
            assert connection.execute(
                "SELECT deleted_at IS NOT NULL FROM mnemion.memories WHERE id=%s",
                (UUID(removed["memory_id"]),),
            ).fetchone()[0]
            assert (
                connection.execute(
                    "SELECT count(*) FROM mnemion.memory_revisions WHERE memory_id=%s",
                    (UUID(removed["memory_id"]),),
                ).fetchone()[0]
                == 0
            )
            assert connection.execute(
                "SELECT revoked_at IS NOT NULL FROM mnemion.api_keys WHERE id=%s",
                (env.owner.key_id,),
            ).fetchone()[0]
            assert connection.execute(
                "SELECT revoked_at IS NULL FROM mnemion.api_keys WHERE id=%s",
                (credentials["key_id"],),
            ).fetchone()[0]
    finally:
        database.stop()
    assert file_hash(Path(values["source"])) == report["sha256"]
    assert local_state.read(root / "configuration.json") == original
    assert not (target / "remote-access.json").exists()
    assert not (target / "host-secrets.json").exists()
    assert not list((root / "backup-operations").glob("restore-*"))
    public = json.dumps(result)
    assert all(
        secret not in public
        for secret in (
            values["recovery_key"],
            env.token,
            credentials["api_key"],
            "private-host-import-fixture-sentinel",
        )
    )


def test_host_import_requires_explicit_database_only_and_exact_reviewed_files(host_copy, tmp_path):
    root, values, _, _, original, _ = host_copy
    for changes in (
        {"host_data_only_confirmed": None},
        {"host_data_only_confirmed": False},
        {"ledger_source": None, "ledger_key": values["ledger_key"]},
    ):
        with pytest.raises(ValidationError):
            local_recovery.RecoveryRequest.model_validate_json(json.dumps({**values, **changes}))
    for changes in (
        {"snapshot_sha256": "0" * 64},
        {"ledger_sha256": "0" * 64},
        {"ledger_source": None, "ledger_key": None, "ledger_sha256": "0" * 64},
    ):
        request = local_recovery.RecoveryRequest.model_validate_json(
            json.dumps({**values, **changes})
        )
        with pytest.raises(local_state.LocalSetupError, match="changed"):
            local_recovery.restore(root, tmp_path, request)
        assert not Path(request.destination).exists()
    assert local_state.read(root / "configuration.json") == original


def test_external_ledger_cannot_roll_back_the_access_state_already_included(host_copy, tmp_path):
    root, values, _, _, _, _ = host_copy
    view = inspect(root, values)
    older = tmp_path / "old-ledger.json"
    encryption.decrypt_file(
        Path(values["ledger_source"]), older, values["ledger_key"], expected_kind="ledger"
    )
    payload = recovery.read_ledger(older)
    payload["snapshot_at"] = view["snapshot_at"]
    assert recovery._time(payload["snapshot_at"]) < recovery._time(view["ledger_at"])
    payload.pop("sha256")
    payload["sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    local_state.write(older, payload)
    encrypted = tmp_path / "old-ledger.enc"
    record = encryption.encrypt_file(older, encrypted, values["ledger_key"], kind="ledger")
    request = local_recovery.RecoveryRequest.model_validate_json(
        json.dumps(
            {**values, "ledger_source": str(encrypted), "ledger_sha256": record.encrypted_sha256}
        )
    )
    with pytest.raises(local_state.LocalSetupError, match="at least as recent"):
        local_recovery.restore(root, tmp_path, request)
    assert not Path(request.destination).exists()


def test_host_inspection_cancellation_leaves_no_plaintext(host_copy):
    root, values, _, _, _, _ = host_copy
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 7

    with pytest.raises((encryption.EncryptionCancelled, recovery.RecoveryCancelled)):
        local_backup.inspect_file(
            root,
            local_backup.BackupInspection(
                source=values["source"], recovery_key=values["recovery_key"]
            ),
            cancelled=cancel,
        )
    assert not list((root / "backup-operations").glob("inspect-*"))
