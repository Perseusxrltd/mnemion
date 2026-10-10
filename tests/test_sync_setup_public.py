import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


PUBLIC_SYNC_FILES = [
    ROOT / "README.md",
    ROOT / "sync" / "README.md",
    ROOT / "sync" / "install_windows.ps1",
    ROOT / "sync" / "SyncMemories.ps1",
    ROOT / "sync" / "SyncMemories.sh",
    ROOT / "sync" / "backfill_trust.py",
    ROOT / "hooks" / "mnemion_save_hook.py",
    ROOT / ".mcp.json",
    ROOT / "studio" / "electron" / "package.json",
]

SHELL_HOOK_FILES = [
    ROOT / ".codex-plugin" / "hooks" / "mnemion-hook.sh",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_public_sync_docs_and_scripts_do_not_ship_personal_memory_repo_details():
    personal_user = "jo" + "rqu"
    sample_agent = "open" + "claw-prod"
    sample_repo = "personal-ai-" + "memories"
    personal_name = "Quen" + "tin " + "Jor" + "quera"
    forbidden = [
        personal_user,
        sample_agent,
        sample_repo,
        "Perseusxrltd/" + sample_repo,
        "C:/Users/" + personal_user,
        "C:\\Users\\" + personal_user,
        personal_name,
    ]

    for path in PUBLIC_SYNC_FILES:
        text = _read(path).lower()
        for token in forbidden:
            assert token.lower() not in text, f"{token!r} leaked in {path.relative_to(ROOT)}"


def test_codex_shell_hooks_use_lf_line_endings():
    for path in SHELL_HOOK_FILES:
        assert b"\r\n" not in path.read_bytes(), (
            f"{path.relative_to(ROOT)} must use LF line endings"
        )


@pytest.mark.skipif(shutil.which("bash") is None, reason="Bash wrapper is tested on Linux")
def test_old_sync_without_service_configuration_stops_before_touching_data(tmp_path):
    environment = os.environ.copy()
    environment.pop("MNEMION_VAULT_CONFIG", None)
    environment["MNEMION_REPO_DIR"] = str(tmp_path)
    original = tmp_path / "personal.md"
    original.write_text("Keep my personal memory")
    result = subprocess.run(
        ["bash", str(ROOT / "sync/SyncMemories.sh")],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "retired" in result.stderr
    assert list(tmp_path.iterdir()) == [original]
    assert original.read_text() == "Keep my personal memory"


def test_retired_union_merge_never_overwrites_a_memory_export(tmp_path):
    ours, theirs, output = (tmp_path / name for name in ("ours.json", "theirs.json", "out.json"))
    ours.write_text("[]")
    theirs.write_text('[{"id":"withdrawn","content":"Old copy"}]')
    output.write_text("Existing reviewed export")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "sync/merge_exports.py"),
            "--ours",
            str(ours),
            "--theirs",
            str(theirs),
            "--out",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "resurrect" in result.stderr
    assert output.read_text() == "Existing reviewed export"
