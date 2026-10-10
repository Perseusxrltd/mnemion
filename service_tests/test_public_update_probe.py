import json
import struct

import pytest

from deploy.public_update_probe import asar_json, installer_name, select_pairs


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
