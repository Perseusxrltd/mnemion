"""Heuristic corpus-origin detection for first-run onboarding."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".cs", ".cpp", ".h"}
CHAT_HINTS = {"chat", "conversation", "transcript", "slack", "claude", "codex", "gemini"}
SLACK_KEYS = {"type", "user", "text"}


def _sample_files(root: Path, limit: int = 200) -> list[Path]:
    from .miner import scan_project

    return list(scan_project(str(root)))[:limit]


def detect_corpus_origin(path) -> dict:
    root = Path(path).expanduser().resolve()
    files = _sample_files(root)
    suffixes = {p.suffix.lower() for p in files}
    names = " ".join(p.name.lower() for p in files[:50])

    code_count = sum(1 for p in files if p.suffix.lower() in CODE_SUFFIXES)
    json_count = sum(1 for p in files if p.suffix.lower() in {".json", ".jsonl"})
    chat_hint = any(hint in names for hint in CHAT_HINTS)

    origin_type = "mixed"
    if suffixes <= {".json"} and _looks_slack_like(files[:3]):
        origin_type = "slack_like_chat"
    elif files and code_count / max(len(files), 1) >= 0.35:
        origin_type = "project_files"
    elif chat_hint or json_count / max(len(files), 1) >= 0.5:
        origin_type = "ai_conversation_logs"

    return {
        "origin_type": origin_type,
        "source_dir": str(root),
        "file_count": len(files),
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "signals": {
            "code_files": code_count,
            "json_or_jsonl_files": json_count,
            "chat_name_hint": chat_hint,
        },
    }


def _looks_slack_like(files: list[Path]) -> bool:
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace")[:50_000])
        except Exception:
            continue
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if SLACK_KEYS <= set(data[0]):
                return True
    return False


def save_origin_metadata(path, metadata: dict) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, **metadata}
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target
