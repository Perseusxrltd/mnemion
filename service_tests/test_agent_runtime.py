"""Real runtime copies, launcher processes and update retention without a model."""

import hashlib
import json
import os
import subprocess

import pytest

from mnemion import agent_runtime as runtime, local_state


def bundle(tmp_path, version):
    root = tmp_path / ("bundle-" + version)
    root.mkdir()
    name = "mnemion-engine.exe" if os.name == "nt" else "mnemion-engine"
    executable = root / name
    content = (
        '#!/bin/sh\nprintf "ready:'
        + version
        + '\\n"\nIFS= read -r input\nprintf "'
        + version
        + ':%s\\n" "$input"\n'
    ).encode()
    executable.write_bytes(content)
    executable.chmod(0o700)
    metadata = {
        "format": 1,
        "component": "service",
        "version": version,
        "files": {
            name: {
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "executable": True,
            }
        },
    }
    (root / "mnemion-runtime.json").write_text(json.dumps(metadata))
    return executable


def prepare(root, executable):
    with local_state.lock(root):
        return runtime.prepare(root, executable)


@pytest.mark.skipif(
    os.name == "nt",
    reason="Actual Windows native launcher is exercised by the installed application gate",
)
def test_live_agent_keeps_old_runtime_and_new_sessions_follow_updates_after_bundle_is_gone(
    tmp_path,
):
    root = local_state.directory(tmp_path / "private")
    first, second, third = [bundle(tmp_path, version) for version in ("1.0.0", "1.0.1", "1.0.2")]
    prepare(root, first)
    name = (root / "runtime-current").read_text().strip()
    command = runtime.command(root, root / "unused-fixture-credentials.json")
    process = subprocess.Popen(
        [command["command"], *command["args"]],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "ready:1.0.0"
        prepare(root, second)
        prepare(root, third)
        assert (root / "runtimes" / name).is_dir(), (
            "An active runtime must survive two subsequent updates"
        )
        third.parent.rename(tmp_path / "removed-appimage-mount")
        current = subprocess.run(
            [command["command"], *command["args"]],
            input="new session\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert current.returncode == 0 and current.stdout.splitlines() == [
            "ready:1.0.2",
            "1.0.2:new session",
        ]
        output, error = process.communicate("existing session\n", timeout=15)
        assert process.returncode == 0 and output.strip() == "1.0.0:existing session" and not error
        prepare(root, tmp_path / "removed-appimage-mount" / third.name)
        assert not (root / "runtimes" / name).exists(), "Exited runtime copies must not accumulate"
        assert runtime.current_version(root) == "1.0.2"
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_failed_inventory_copy_preserves_working_runtime_and_cleans_interrupted_stages(tmp_path):
    root = local_state.directory(tmp_path / "private")
    original = bundle(tmp_path, "1.0.0")
    prepare(root, original)
    pointer = (root / "runtime-current").read_bytes()
    broken = bundle(tmp_path, "1.0.1")
    broken.write_bytes(b"changed after packaging")
    abandoned = root / ("runtime-stage-" + "a" * 32)
    abandoned.mkdir()
    (abandoned / "partial").write_bytes(b"partial copy")
    with pytest.raises(ValueError, match="differs from its inventory"):
        prepare(root, broken)
    assert (root / "runtime-current").read_bytes() == pointer
    assert not list(root.glob("runtime-stage-*"))
    assert runtime.current_version(root) == "1.0.0"
    manifest = broken.parent / "mnemion-runtime.json"
    value = json.loads(manifest.read_text())
    value["files"]["../escape"] = next(iter(value["files"].values()))
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="Unsafe bundled runtime path"):
        prepare(root, broken)
    assert not (tmp_path / "escape").exists()


def test_runtime_publish_recovers_an_interrupted_launcher_lock(tmp_path):
    root = local_state.directory(tmp_path / "private")
    lock = root / "runtime-lock"
    lock.mkdir()
    (lock / "owner").write_text("2147483647")
    with runtime.runtime_lock(root):
        assert (lock / "owner").read_text() == str(os.getpid())
    assert not lock.exists()
