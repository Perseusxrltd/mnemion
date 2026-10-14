"""An old bootstrap can hand off only to its authenticated, exact candidate."""

from pathlib import Path
import os
from types import SimpleNamespace
import sys

import pytest

from deploy import upgrade_managed as bridge
from mnemion.service import service_updates as updates
from mnemion.service import update_state as state_io
from mnemion.service.update_manifest import ManifestError

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Managed Supervisor upgrades run on Unix"
)


@pytest.fixture
def host(tmp_path, monkeypatch):
    state = state_io.directory(tmp_path / "managed state")
    root = state_io.directory(state / "updates")
    package = tmp_path / "verified package"
    (package / "service").mkdir(parents=True)
    (package / "service/managed_upgrade.py").write_text("# protocol fixture\n")
    release = SimpleNamespace(version="4.2.4", commit="a" * 40)
    runtime = {
        "version": release.version,
        "package": str(package),
        "python": sys.executable,
        "directory": str(tmp_path),
    }
    slot = state_io.directory(updates._slot(root, release))
    state_io.write(slot / "ready.json", {"runtime": runtime})
    monkeypatch.setattr(updates, "_root", lambda _: (state, root, {}))
    monkeypatch.setattr(updates, "_check", lambda _: {"available_version": release.version})
    monkeypatch.setattr(updates, "_release", lambda _: release)
    monkeypatch.setattr(updates, "_stage", lambda *_: None)
    monkeypatch.setattr(updates, "resolved_runtime", lambda _, runtime: runtime)
    calls = []
    monkeypatch.setattr(
        bridge.subprocess, "call", lambda args, **kwargs: calls.append((args, kwargs)) or 0
    )
    return SimpleNamespace(state=state, root=root, runtime=runtime, calls=calls)


@pytest.mark.parametrize("apply", [False, True])
def test_old_environment_handoff_preserves_exact_arguments_and_filters_secrets(
    host, monkeypatch, apply
):
    monkeypatch.setenv("MNEMION_ADMIN_DATABASE_URL", "must-not-inherit-this-value")
    arguments = ["--state-dir", str(host.state), "--version", "4.2.4"]
    if apply:
        arguments.append("--allow-migration")
    assert bridge.main(arguments) == 0
    command, options = host.calls[0]
    assert command[:5] == [sys.executable, "-I", "-m", "mnemion.service.cli", "updates"]
    assert command[5] == ("upgrade" if apply else "plan")
    assert command[7] == str(host.state)
    assert "--allow-migration" in command if apply else "--allow-migration" not in command
    assert "MNEMION_ADMIN_DATABASE_URL" not in options["env"]
    assert Path(options["cwd"]) == Path(host.runtime["directory"])


@pytest.mark.parametrize("failure", ["version_changed", "package_rejected"])
def test_changed_or_unverified_candidate_never_executes(host, monkeypatch, failure):
    if failure == "version_changed":
        monkeypatch.setattr(updates, "_check", lambda _: {"available_version": "4.2.5"})
    else:

        def rejected(*args, **kwargs):
            raise ManifestError("Installed byte verification failed")

        monkeypatch.setattr(updates, "resolved_runtime", rejected)
    assert (
        bridge.main(["--state-dir", str(host.state), "--version", "4.2.4", "--allow-migration"])
        == 2
    )
    assert host.calls == []
