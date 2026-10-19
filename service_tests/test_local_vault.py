"""Host-only vault configuration keeps encryption keys out of ordinary status."""

import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest

from mnemion import local_state as state, local_vault
from mnemion.service.vault_crypto import new_vault_key
from service_tests.test_local_company import workspace


def change(settings, *, revision="not-configured", key=None, **values):
    data = {
        "workspace_id": settings["workspace_id"],
        "expected_revision": revision,
        "enabled": True,
        "mcp_enabled": False,
        "action": "configure",
        **values,
    }
    if key is not None:
        data.update(recovery_key=key, key_saved=True)
    return local_vault.VaultChange.model_validate_json(json.dumps(data))


def test_private_key_setup_status_disable_and_explicit_recovery_copy(tmp_path):
    root, settings, _ = workspace(tmp_path)
    key = new_vault_key()
    before = (root / "credentials.json").read_bytes()
    saved = local_vault.configure(root, change(settings, key=key))
    assert saved["state"] == "configured" and key not in json.dumps(saved)
    assert (root / "credentials.json").read_bytes() == before
    assert local_vault.settings(root, settings["workspace_id"]).key.get_secret_value() == key
    if os.name != "nt":
        assert (root / "vault-access.json").stat().st_mode & 0o777 == 0o600
    request = local_vault.VaultRequest.model_validate_json(
        json.dumps(
            {"workspace_id": settings["workspace_id"], "expected_revision": saved["revision"]}
        )
    )
    assert local_vault.reveal_key(root, request)["recovery_key"] == key
    disabled = local_vault.configure(
        root, change(settings, revision=saved["revision"], enabled=False)
    )
    assert (
        disabled["state"] == "disabled"
        and not local_vault.settings(root, settings["workspace_id"]).enabled
    )
    assert key not in json.dumps(local_vault.inspection(root, settings["workspace_id"]))


def test_configuration_requires_current_host_revision_and_stopped_workspace(tmp_path):
    root, settings, _ = workspace(tmp_path)
    key = new_vault_key()
    with state.lock(root), pytest.raises(state.LocalSetupError):
        local_vault.configure(root, change(settings, key=key))
    with pytest.raises(state.LocalSetupError) as wrong:
        local_vault.configure(root, change({**settings, "workspace_id": str(uuid4())}, key=key))
    assert wrong.value.code == "settings_changed"
    local_vault.configure(root, change(settings, key=key))
    with pytest.raises(state.LocalSetupError) as stale:
        local_vault.configure(root, change(settings, key=key))
    assert stale.value.code == "settings_changed"


def test_repair_requires_recovery_key_and_preserves_all_prior_private_keys(tmp_path):
    root, settings, _ = workspace(tmp_path)
    local_vault.configure(root, change(settings, key=new_vault_key()))
    damaged = b'{"broken-vault-record":true}'
    with state.private_output(root / "damage.tmp") as stream:
        stream.write(damaged)
    (root / "damage.tmp").replace(root / "vault-access.json")
    view = local_vault.inspection(root, settings["workspace_id"])
    assert view["state"] == "configuration_error" and view["repairable"]
    with pytest.raises(state.LocalSetupError):
        local_vault.configure(
            root, change(settings, revision=view["revision"], key=new_vault_key())
        )
    for _ in range(10):
        local_vault.configure(
            root, change(settings, revision=view["revision"], key=new_vault_key(), action="restore")
        )
        view = local_vault.inspection(root, settings["workspace_id"])
    copies = list((root / "recovery").glob("vault-*.bin"))
    assert len(copies) == 10 and any(path.read_bytes() == damaged for path in copies)


def test_missing_recovery_copy_and_implicit_rekey_are_refused(tmp_path):
    root, settings, _ = workspace(tmp_path)
    with pytest.raises(state.LocalSetupError) as refused:
        local_vault.configure(root, change(settings))
    assert refused.value.code == "vault_key_required"
    saved = local_vault.configure(root, change(settings, key=new_vault_key()))
    with pytest.raises(state.LocalSetupError) as refused:
        local_vault.configure(
            root, change(settings, revision=saved["revision"], key=new_vault_key())
        )
    assert refused.value.code == "vault_key_changed"


def test_environment_ownership_and_unsafe_files_are_preserved(tmp_path, monkeypatch):
    root, settings, _ = workspace(tmp_path)
    key = new_vault_key()
    monkeypatch.setenv("MNEMION_VAULT_KEY", key)
    monkeypatch.setenv("MNEMION_VAULT_ENABLED", "1")
    assert local_vault.inspection(root, settings["workspace_id"])["state"] == "external"
    assert local_vault.settings(root, settings["workspace_id"]).enabled
    with pytest.raises(state.LocalSetupError) as refused:
        local_vault.configure(root, change(settings, key=key))
    assert refused.value.code == "vault_external_configuration"
    monkeypatch.delenv("MNEMION_VAULT_KEY")
    outside = tmp_path / "outside.json"
    outside.write_text("private-outside-fixture")
    (root / "vault-access.json").symlink_to(outside)
    view = local_vault.inspection(root, settings["workspace_id"])
    assert (
        not view["repairable"] and not local_vault.settings(root, settings["workspace_id"]).enabled
    )
    assert outside.read_text() == "private-outside-fixture"


def test_native_cli_handoff_is_bounded_and_key_retrieval_is_explicit(tmp_path):
    root, settings, _ = workspace(tmp_path)
    key = new_vault_key()
    data = change(settings, key=key).model_dump(mode="json")
    data["recovery_key"] = key
    command = [sys.executable, "-m", "mnemion.service.cli", "local", "vault", "--root", str(root)]
    environment = {**os.environ, "MNEMION_VAULT_KEY": ""}
    saved = subprocess.run(
        command, input=json.dumps(data), text=True, capture_output=True, env=environment, timeout=20
    )
    assert saved.returncode == 0, saved.stderr
    assert key not in saved.stdout and key not in saved.stderr
    view = json.loads(saved.stdout)["vault_access"]
    request = {"workspace_id": settings["workspace_id"], "expected_revision": view["revision"]}
    read = subprocess.run(
        [*command[:4], "vault-key", *command[5:]],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        env=environment,
        timeout=20,
    )
    assert read.returncode == 0 and json.loads(read.stdout)["key"]["recovery_key"] == key
    invalid = subprocess.run(
        command,
        input=json.dumps({**data, "unreviewed": key}),
        text=True,
        capture_output=True,
        env=environment,
        timeout=20,
    )
    assert invalid.returncode != 0 and key not in invalid.stdout + invalid.stderr


def test_connectors_never_import_host_keys_or_encrypted_vault_exports():
    from mnemion.connectors.config import FileSelection
    from mnemion.connectors.providers import document, selected

    selection = FileSelection(exclude=[])
    assert not selected(selection, "nested/vault-access.json")
    for content in (
        json.dumps({"key": new_vault_key()}),
        '{"format":"mnemion-vault-export","ciphertext":"fixture"}',
    ):
        assert document(selection, "renamed.txt", content.encode(), "fixture") is None
    assert (
        document(
            selection, "notes.md", b"A normal note about using a credentials vault.", "fixture"
        )
        is not None
    )
