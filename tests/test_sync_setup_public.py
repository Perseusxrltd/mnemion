from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


PUBLIC_SYNC_FILES = [
    ROOT / "README.md",
    ROOT / "sync" / "README.md",
    ROOT / "sync" / "install_windows.ps1",
    ROOT / "sync" / "SyncMemories.ps1",
    ROOT / "sync" / "SyncMemories.sh",
    ROOT / "sync" / "backfill_trust.py",
    ROOT / "hooks" / "mnemion_save_hook.py",
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
    forbidden = [
        personal_user,
        sample_agent,
        sample_repo,
        "Perseusxrltd/" + sample_repo,
        "C:/Users/" + personal_user,
        "C:\\Users\\" + personal_user,
    ]

    for path in PUBLIC_SYNC_FILES:
        text = _read(path).lower()
        for token in forbidden:
            assert token.lower() not in text, f"{token!r} leaked in {path.relative_to(ROOT)}"


def test_windows_installer_exposes_programmable_sync_setup():
    text = _read(ROOT / "sync" / "install_windows.ps1")

    required_params = [
        "[string]$MnemionDir",
        "[string]$MemoryRepoUrl",
        "[string]$MemoryBranch",
        "[string]$AgentId",
        "[string]$SyncTaskName",
        "[int]$SyncIntervalHours",
        "[switch]$SkipSync",
    ]
    for param in required_params:
        assert param in text

    assert "git remote add origin $MemoryRepoUrl" in text
    assert "git remote set-url origin $MemoryRepoUrl" in text
    assert '-Branch `"$MemoryBranch`"' in text
    assert '-AgentId `"$AgentId`"' in text


def test_windows_installer_removes_legacy_mempalace_hook_entries():
    text = _read(ROOT / "sync" / "install_windows.ps1")

    assert "mempalace" in text.lower()
    assert "mempal_save_hook" in text.lower()
    assert '$settings["hooks"]["Stop"] = $filteredStopHooks' in text


def test_sync_scripts_only_stage_portable_sync_artifacts():
    powershell = _read(ROOT / "sync" / "SyncMemories.ps1")
    bash = _read(ROOT / "sync" / "SyncMemories.sh")

    assert "git add ." not in powershell
    assert "git add ." not in bash

    for text in (powershell, bash):
        assert "archive/drawers_export.json" in text
        assert "MNEMION_SYNC_KG" in text

    assert '$SyncKnowledgeGraph = $env:MNEMION_SYNC_KG -in @("1", "true", "yes")' in powershell
    assert (
        'if ($SyncKnowledgeGraph) { $syncArtifacts += "archive/knowledge_graph.sql" }' in powershell
    )
    assert 'SYNC_KG="${MNEMION_SYNC_KG:-0}"' in bash


def test_powershell_sync_avoids_native_argument_quote_loss_in_inline_python():
    powershell = _read(ROOT / "sync" / "SyncMemories.ps1")

    assert 'f.write(f"{line}\\n")' not in powershell
    assert "f.write(line + '\\n')" in powershell


def test_codex_shell_hooks_use_lf_line_endings():
    for path in SHELL_HOOK_FILES:
        assert b"\r\n" not in path.read_bytes(), (
            f"{path.relative_to(ROOT)} must use LF line endings"
        )
