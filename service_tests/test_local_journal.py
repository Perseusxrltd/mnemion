"""App host enrollment cannot publish, grant access, or erase an existing queue."""

import json
import os
import subprocess
import sys
from uuid import UUID, uuid4

import pytest

from mnemion import local_journal as journal, local_state as state
from mnemion.journal.config import Configuration
from mnemion.journal.spool import Spool
from mnemion.local_workspace import SetupOptions, inspect
from mnemion.private_output import private_output
from mnemion.service.errors import ServiceError
from mnemion.service.models import MemoryInput
from mnemion.service.writeback import WritebackService
from mnemion.service.writeback_models import WritebackPolicyInput


def workspace(tmp_path):
    root = state.directory(tmp_path / "Journal Équipe")
    settings = {
        "format": 1,
        "workspace_id": str(uuid4()),
        "created_at": "2026-10-19T00:00:00Z",
        **SetupOptions(workspace_name="Journal workspace", owner_name="Owner").model_dump(),
        "database_port": 17893,
    }
    state.write(root / "configuration.json", settings)
    state.write(root / "credentials.json", {"fixture": "Existing credentials stay unchanged"})
    return root, settings


def destination(space=None, **values):
    return {
        "space_id": str(space or uuid4()),
        "label": "Team continuity",
        "remote": "https://git.example.test/team/memory.git",
        "branch": "main",
        "prefix": "memory/native-buffer",
        "personal_data_scan": True,
        **values,
    }


def change(settings, **values):
    return journal.JournalChange.model_validate_json(
        json.dumps(
            {
                "workspace_id": settings["workspace_id"],
                "expected_revision": "not-configured",
                **values,
            }
        )
    )


def test_enrollment_keeps_identity_private_state_and_separate_space_approval(tmp_path):
    root, settings = workspace(tmp_path)
    originals = {
        name: (root / name).read_bytes() for name in ("configuration.json", "credentials.json")
    }
    selected = destination()
    view = journal.configure(root, change(settings, action="save", destination=selected))
    assert view["state"] == "configured" and view["destinations"] == [selected]
    assert view == inspect(root)["journal_access"]
    tenant = str(uuid4())
    registered = journal.configuration(root, settings["workspace_id"], tenant_id=tenant)
    assert len(registered.destinations) == 1
    value = registered.destinations[0]
    assert str(value.tenant_id) == tenant and str(value.space_id) == selected["space_id"]
    assert value.state_directory == root / ("journal-" + selected["space_id"])
    assert value.scanner == () and value.local_repository is None
    assert not value.state_directory.exists()  # Registration does not activate the journal.
    assert all((root / name).read_bytes() == raw for name, raw in originals.items())
    assert "state_directory" not in json.dumps(view) and "scanner" not in json.dumps(view)
    assert "state_directory" not in (root / "journal-access.json").read_text()
    if os.name != "nt":
        assert (root / "journal-access.json").stat().st_mode & 0o077 == 0


def test_app_ssh_registration_keeps_only_private_references_and_preserves_config_on_failure(
    tmp_path,
):
    root, settings = workspace(tmp_path)
    key, pins = root / "deploy-key", root / "host-pins"
    for path, content in ((key, b"synthetic private key"), (pins, b"synthetic verified host pins")):
        with private_output(path) as output:
            output.write(content)
    selected = destination(
        remote="ssh://git@git.example.test/team/memory.git",
        ssh={"identity_file": str(key), "known_hosts_file": str(pins)},
    )
    view = journal.configure(root, change(settings, action="save", destination=selected))
    assert view["destinations"] == [selected]
    saved = (root / "journal-access.json").read_bytes()
    assert b"synthetic private key" not in saved
    registered = journal.configuration(
        root, settings["workspace_id"], tenant_id=str(uuid4())
    ).destinations[0]
    assert registered.ssh.identity_file == key and registered.kind == "ssh_repository"
    key.unlink()
    with pytest.raises(state.LocalSetupError, match="existing SSH key"):
        journal.configure(
            root,
            change(
                settings,
                action="save",
                expected_revision=view["revision"],
                destination={**selected, "label": "Changed label"},
            ),
        )
    assert (root / "journal-access.json").read_bytes() == saved


def test_stale_changes_and_foreign_workspaces_do_not_overwrite_registrations(tmp_path):
    root, settings = workspace(tmp_path)
    command = change(settings, action="save", destination=destination())
    journal.configure(root, command)
    before = (root / "journal-access.json").read_bytes()
    with pytest.raises(state.LocalSetupError, match="changed"):
        journal.configure(root, command)
    with pytest.raises(state.LocalSetupError, match="current local workspace"):
        journal.configure(root, command.model_copy(update={"workspace_id": uuid4()}))
    assert (root / "journal-access.json").read_bytes() == before


@pytest.mark.parametrize(
    "patch",
    [
        {"remote": "https://operator:private-sentinel@git.example.test/team.git"},
        {"remote": "https://git.example.test/team.git?credential=private-sentinel"},
        {"remote": "http://git.example.test/team.git"},
        {"remote": "ext::unreviewed-command"},
        {"branch": "--upload-pack=unreviewed-command"},
        {"prefix": "../outside"},
        {"prefix": "memory/NUL/records"},
        {"scanner": ["/unreviewed/program"]},
        {"state_directory": "/arbitrary/host/path"},
    ],
)
def test_only_safe_repository_choices_are_accepted(tmp_path, patch):
    root, settings = workspace(tmp_path)
    with pytest.raises(ValueError):
        change(settings, action="save", destination=destination(**patch))
    assert not (root / "journal-access.json").exists()


def test_multiple_spaces_need_distinct_folders_and_removal_keeps_private_receipts(tmp_path):
    root, settings = workspace(tmp_path)
    first, second = destination(), destination()
    view = journal.configure(root, change(settings, action="save", destination=first))
    before = (root / "journal-access.json").read_bytes()
    with pytest.raises(ValueError, match="own repository folder"):
        journal.configure(
            root,
            change(settings, expected_revision=view["revision"], action="save", destination=second),
        )
    assert (root / "journal-access.json").read_bytes() == before
    second["prefix"] += "/separate"
    view = journal.configure(
        root,
        change(settings, expected_revision=view["revision"], action="save", destination=second),
    )
    private = state.directory(root / ("journal-" + first["space_id"]))
    state.write(private / "retained.json", {"fixture": "retained queue receipt"})
    removed = journal.configure(
        root,
        change(
            settings,
            expected_revision=view["revision"],
            action="remove",
            space_id=first["space_id"],
        ),
    )
    assert removed["destinations"] == [second]
    assert state.read(private / "retained.json") == {"fixture": "retained queue receipt"}


def test_external_environment_configuration_is_preserved(tmp_path, monkeypatch):
    root, settings = workspace(tmp_path)
    external = root / "operator-registry.json"
    state.write(external, Configuration().model_dump(mode="json"))
    monkeypatch.setenv("MNEMION_WRITEBACK_CONFIG", str(external))
    view = journal.inspection(root, settings["workspace_id"])
    assert view["state"] == "external" and not view["repairable"]
    assert (
        journal.configuration(root, settings["workspace_id"], tenant_id=str(uuid4()))
        == Configuration()
    )
    with pytest.raises(state.LocalSetupError, match="environment"):
        journal.configure(root, change(settings, action="save", destination=destination()))
    assert not (root / "journal-access.json").exists()


def test_damaged_registry_is_preserved_on_explicit_repair_and_links_are_refused(tmp_path):
    root, settings = workspace(tmp_path)
    path = root / "journal-access.json"
    state.write(path, {"invalid": "original private settings"})
    original = path.read_bytes()
    broken = journal.inspection(root, settings["workspace_id"])
    assert broken["state"] == "configuration_error" and broken["repairable"]
    assert not journal.configuration(
        root, settings["workspace_id"], tenant_id=str(uuid4())
    ).destinations
    with pytest.raises(state.LocalSetupError, match="Reset damaged"):
        journal.configure(
            root,
            change(
                settings,
                expected_revision=broken["revision"],
                action="save",
                destination=destination(),
            ),
        )
    restored = journal.configure(
        root, change(settings, expected_revision=broken["revision"], action="reset")
    )
    assert restored["state"] == "not_configured"
    assert any(
        candidate.read_bytes() == original
        for candidate in (root / "recovery").glob("journal-*.bin")
    )
    if os.name != "nt":
        path.unlink()
        path.symlink_to(root / "credentials.json")
        assert journal.inspection(root, settings["workspace_id"])["repairable"] is False
        with pytest.raises(state.LocalSetupError):
            journal.configure(root, change(settings, action="save", destination=destination()))


def test_private_cli_rejects_credential_urls_without_reflecting_input(tmp_path):
    root, settings = workspace(tmp_path)
    body = {
        "workspace_id": settings["workspace_id"],
        "expected_revision": "not-configured",
        "action": "save",
        "destination": destination(
            remote="https://operator:private-sentinel@git.example.test/team.git"
        ),
    }
    result = subprocess.run(
        [sys.executable, "-m", "mnemion.service.cli", "local", "journal", "--root", str(root)],
        input=json.dumps(body) + "\n",
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["code"] == "invalid_journal_options"
    assert "private-sentinel" not in result.stdout + result.stderr
    assert not (root / "journal-access.json").exists()


def test_service_requires_new_approval_when_host_destination_changes(env, tmp_path):
    root, settings = workspace(tmp_path)
    selected = destination(env.space)
    view = journal.configure(root, change(settings, action="save", destination=selected))
    config = journal.configuration(
        root, settings["workspace_id"], tenant_id=str(env.owner.tenant_id)
    )
    service = WritebackService(env.db, config)
    env.memory.writeback = service
    initial = service.status(env.owner, env.space)
    assert not initial["configured"] and initial["can_configure"]
    approved = service.configure(
        env.owner,
        env.space,
        WritebackPolicyInput(
            expected_version=0,
            destination_id=config.destinations[0].id,
            publish_to_repository=True,
            acknowledge_retained_git_history=True,
            paused=True,
        ),
    )
    first = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Durable local journal example"),
        "journal-host-first",
    )
    assert first["writeback"]["durability"] == "local_journal"
    assert len(list(Spool(config.destinations[0]).records())) == 1
    changed = {**selected, "prefix": "memory/new-native-buffer"}
    journal.configure(
        root,
        change(settings, expected_revision=view["revision"], action="save", destination=changed),
    )
    next_config = journal.configuration(
        root, settings["workspace_id"], tenant_id=str(env.owner.tenant_id)
    )
    service = WritebackService(env.db, next_config)
    env.memory.writeback = service
    assert service.status(env.owner, env.space)["state"] == "destination_changed"
    with pytest.raises(ServiceError) as refused:
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content="Requires current approval"),
            "journal-host-unapproved",
        )
    assert refused.value.code == "journal_destination_unavailable"
    service.configure(
        env.owner,
        env.space,
        WritebackPolicyInput(
            expected_version=approved["version"],
            destination_id=next_config.destinations[0].id,
            publish_to_repository=True,
            acknowledge_retained_git_history=True,
            paused=True,
        ),
    )
    second = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Approved destination is durable"),
        "journal-host-second",
    )
    assert second["writeback"]["durability"] == "local_journal"
    assert (
        env.memory.fetch(env.owner, UUID(first["memory_id"]))["content"]
        == "Durable local journal example"
    )
    assert len(list(Spool(next_config.destinations[0]).records())) == 2
