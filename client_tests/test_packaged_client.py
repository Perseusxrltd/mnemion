"""Run the same file protocol against Python or the native packaged executable."""

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from mnemion.vault_refresh import BEGIN, bundle

MANIFEST = ".mnemion-obsidian-manifest.json"


def test_native_client_refresh_conflict_withdrawal_and_invalid_archive(tmp_path):
    executable = os.environ.get("MNEMION_PACKAGED_CLIENT")
    command = (
        [executable]
        if executable
        else [sys.executable, str(Path(__file__).resolve().parents[1] / "studio/bridge/main.py")]
    )
    vault = tmp_path / "Équipe 漢字" / "Personal vault"
    vault.mkdir(parents=True)
    (vault / "Personal.md").write_bytes(b"My personal note.\r\n")
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian/app.json").write_bytes(b'{"alwaysUpdateLinks":true}\n')
    archive = tmp_path / "export with spaces.zip"

    def refresh(files, stamp):
        rendered, manifest = bundle(files, {"synced_at": stamp})
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as output:
            for name, content in rendered.items():
                output.writestr(name, content)
            output.writestr(MANIFEST, json.dumps(manifest))
        archive.write_bytes(buffer.getvalue())
        result = subprocess.run(
            [*command, "--archive", str(archive), "--vault", str(vault)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    original = "---\nid: stable-memory\n---\n# Project decision\nOriginal evidence.\n"
    assert refresh({"Notes/Decision.md": original}, "one")["completed"]
    path = vault / "Notes/Decision.md"
    personal = "\r\nPersonal annotation: café, 漢字, [[Personal]].\r\n".encode()
    path.write_bytes(path.read_bytes() + personal)
    corrected = original.replace("Original", "Corrected")
    assert refresh({"Notes/Renamed.md": corrected}, "two")["completed"]
    assert path.read_bytes().endswith(personal)
    assert "Corrected evidence" in path.read_text(encoding="utf-8")
    assert not (vault / "Notes/Renamed.md").exists()
    clean = path.read_bytes()
    path.write_bytes(clean.replace(BEGIN.encode(), BEGIN.encode() + b"\nHuman edit."))
    edited = path.read_bytes()
    result = refresh({"Notes/Renamed.md": corrected}, "three")
    assert not result["completed"] and len(result["conflicts"]) == 1
    assert path.read_bytes() == edited
    assert json.loads((vault / MANIFEST).read_text())["synced_at"] == "two"
    assert list((vault / ".mnemion-conflicts").glob("*.proposed.md"))
    path.write_bytes(clean)
    assert refresh({}, "four")["completed"]
    assert path.read_bytes().endswith(personal) and b"Corrected evidence" not in path.read_bytes()
    assert (vault / "Personal.md").read_bytes() == b"My personal note.\r\n"
    assert (vault / ".obsidian/app.json").read_bytes() == b'{"alwaysUpdateLinks":true}\n'
    archive.write_bytes(b"truncated zip")
    missing = tmp_path / "not published"
    invalid = subprocess.run(
        [*command, "--archive", str(archive), "--vault", str(missing)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert invalid.returncode == 1 and json.loads(invalid.stdout)["error"]
    assert not missing.exists()
