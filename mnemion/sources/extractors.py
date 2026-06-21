"""Safe local source text extractors.

Source content is untrusted data. These extractors only read and normalize
bytes; they never execute content or interpret instructions embedded in it.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SourceExtractionError(RuntimeError):
    """Raised when a source cannot be extracted safely."""


@dataclass(frozen=True)
class ExtractedText:
    text: str
    source_type: str
    metadata: dict[str, Any]


_TYPE_BY_SUFFIX = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".json": "json",
    ".jsonl": "jsonl",
    ".csv": "csv",
}


def detect_source_type(path: str | Path, override: str | None = None) -> str:
    if override:
        return override
    value = str(path)
    if value.startswith("http://") or value.startswith("https://"):
        return "url"
    return _TYPE_BY_SUFFIX.get(Path(value).suffix.lower(), "unknown")


def _stringify_json(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if isinstance(item, (str, int, float, bool)) or item is None:
                parts.append(f"{key}: {item}")
            else:
                parts.append(f"{key}: {_stringify_json(item)}")
        return "\n".join(parts)
    if isinstance(value, list):
        return "\n".join(_stringify_json(item) for item in value)
    return str(value)


def extract_text(path: str | Path, source_type: str | None = None) -> ExtractedText:
    source = Path(path).expanduser()
    kind = detect_source_type(source, source_type)
    if kind == "url":
        raise SourceExtractionError("URL extraction is not enabled in this MVP")
    if kind == "pdf":
        raise SourceExtractionError("PDF extraction requires an optional PDF dependency")
    if source.suffix.lower() == ".pdf":
        raise SourceExtractionError("PDF extraction requires an optional PDF dependency")
    if not source.is_file():
        raise FileNotFoundError(str(source))

    if kind in {"markdown", "text", "unknown"}:
        return ExtractedText(
            text=source.read_text(encoding="utf-8", errors="replace"),
            source_type=kind,
            metadata={"filename": source.name},
        )

    if kind == "json":
        data = json.loads(source.read_text(encoding="utf-8", errors="replace"))
        return ExtractedText(
            text=_stringify_json(data),
            source_type=kind,
            metadata={"filename": source.name},
        )

    if kind == "jsonl":
        lines = []
        skipped_invalid = 0
        with source.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    skipped_invalid += 1
                    continue
                lines.append(_stringify_json(data))
        return ExtractedText(
            text="\n\n".join(part for part in lines if part),
            source_type=kind,
            metadata={"filename": source.name, "skipped_invalid": skipped_invalid},
        )

    if kind == "csv":
        rows = []
        with source.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                for row in reader:
                    rows.append(" | ".join(f"{k}: {v}" for k, v in row.items()))
            else:
                f.seek(0)
                simple = csv.reader(f)
                rows.extend(" | ".join(row) for row in simple)
        return ExtractedText(
            text="\n".join(rows),
            source_type=kind,
            metadata={"filename": source.name},
        )

    raise SourceExtractionError(f"Unsupported source type: {kind}")
