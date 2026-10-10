import json
import struct

import pytest

from deploy.public_update_probe import asar_json, installer_name, profile_process_id, select_pairs


def published(tag, pairs):
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [{"name": installer_name(tag, system, arch)} for system, arch in pairs],
    }


def test_public_rehearsal_selects_an_actual_previous_installer_per_architecture():
    target = published("v4.0.2", [("windows", "x64"), ("windows", "arm64"), ("macos", "arm64")])
    previous = [
        published("v4.0.0", [("macos", "arm64")]),
        published("v4.0.1", [("windows", "x64"), ("macos", "arm64")]),
        {**target, "draft": True},
    ]
    selected, skipped = select_pairs(target, previous)
    assert {(row["platform"], row["arch"], row["from"], row["to"]) for row in selected} == {
        ("windows", "x64", "v4.0.1", "v4.0.2"),
        ("macos", "arm64", "v4.0.1", "v4.0.2"),
    }
    assert skipped == ["windows/arm64: no earlier public installer"]


def test_asar_metadata_rejects_truncation_oversize_and_external_entries(tmp_path):
    # Chromium Pickle framing, with a normal packed JSON file following the header.
    content = b'{"version":"4.0.1","name":"mnemion-studio"}'
    archive = tmp_path / "app.asar"

    def write(entry):
        body = json.dumps({"files": {"package.json": entry}}).encode()
        payload = struct.pack("<I", len(body)) + body
        payload += b"\0" * (-len(payload) % 4)
        header = struct.pack("<I", len(payload)) + payload
        archive.write_bytes(struct.pack("<II", 4, len(header)) + header + content)

    write({"offset": "0", "size": len(content)})
    assert asar_json(archive)["version"] == "4.0.1"
    for entry in (
        {"offset": "0", "size": 2**30},
        {"offset": "9" * 100, "size": len(content)},
        {"offset": "0", "size": len(content), "unpacked": True},
    ):
        write(entry)
        with pytest.raises(ValueError):
            asar_json(archive)
    archive.write_bytes(struct.pack("<II", 4, 2**30))
    with pytest.raises(ValueError):
        asar_json(archive)
    archive.write_bytes(b"\0")
    with pytest.raises(ValueError):
        asar_json(archive)


def test_linux_main_process_is_taken_from_the_new_default_profile_lock(tmp_path):
    import os

    if os.name == "nt":
        pytest.skip("Chromium uses SingletonLock symlinks on Linux")
    lock = tmp_path / "SingletonLock"
    assert profile_process_id(tmp_path) is None
    lock.symlink_to("runner-with-hyphens-12345")
    assert profile_process_id(tmp_path) == 12345
    for invalid in ("runner-0", "runner-01", "../runner-12345", "runner-" + "9" * 100):
        lock.unlink()
        lock.symlink_to(invalid)
        assert profile_process_id(tmp_path) is None


def test_linux_archive_comes_from_the_running_mount_after_launcher_exec(tmp_path):
    from types import SimpleNamespace

    from deploy.public_update_probe import app_archive

    archive = tmp_path / ".mount_Mnemion1/resources/app.asar"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"running package")
    process = SimpleNamespace(
        exe=lambda: str(tmp_path / "installed/Mnemion.AppImage"),
        cmdline=lambda: ["Mnemion Studio", "--background"],
        children=lambda: [
            SimpleNamespace(exe=lambda: str(archive.parent.parent / "mnemion-studio"))
        ],
    )
    assert app_archive(process, "linux") == archive
    archive.unlink()
    with pytest.raises(FileNotFoundError):
        app_archive(process, "linux")
