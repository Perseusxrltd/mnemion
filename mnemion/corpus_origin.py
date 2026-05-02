"""Heuristic source-origin detection for init-time corpus handling."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusOriginResult:
    likely_ai_dialogue: bool
    confidence: float
    primary_platform: str | None
    user_name: str | None
    agent_persona_names: list[str]
    evidence: list[str]


def detect_origin_heuristic(samples: list[str]) -> CorpusOriginResult:
    text = "\n".join(samples)
    lower = text.lower()
    evidence: list[str] = []
    score = 0.0
    platform = None
    personas: list[str] = []

    if "claude" in lower:
        score += 0.35
        platform = "claude"
        personas.append("Claude")
        evidence.append("claude marker")
    if "codex" in lower:
        score += 0.25
        platform = platform or "codex"
        personas.append("Codex")
        evidence.append("codex marker")
    if re.search(r"\b(user|human)\s*:", lower):
        score += 0.2
        evidence.append("user turn marker")
    if re.search(r"\b(assistant|ai)\s*:", lower):
        score += 0.25
        evidence.append("assistant turn marker")
    if "session_id" in lower or "sessionid" in lower:
        score += 0.1
        evidence.append("session id marker")

    seen = []
    for name in personas:
        if name not in seen:
            seen.append(name)

    return CorpusOriginResult(
        likely_ai_dialogue=score >= 0.45,
        confidence=round(min(score, 0.99), 2),
        primary_platform=platform,
        user_name=None,
        agent_persona_names=seen,
        evidence=evidence,
    )


def sample_files(root: str | Path, limit: int = 8, max_chars: int = 4000) -> list[str]:
    path = Path(root).expanduser().resolve()
    samples = []
    for file_path in sorted(path.rglob("*")):
        if len(samples) >= limit:
            break
        if not file_path.is_file() or file_path.suffix.lower() not in {".txt", ".md", ".jsonl"}:
            continue
        try:
            samples.append(file_path.read_text(encoding="utf-8", errors="replace")[:max_chars])
        except OSError:
            continue
    return samples


def detect_origin_for_path(root: str | Path) -> CorpusOriginResult:
    return detect_origin_heuristic(sample_files(root))


def persist_origin(root: str | Path, result: CorpusOriginResult) -> Path:
    target = Path(root).expanduser().resolve() / ".mnemion" / "origin.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(result), indent=2, sort_keys=True))
    return target
