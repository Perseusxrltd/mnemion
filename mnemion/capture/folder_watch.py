"""Small polling folder capture helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..sources.store import SourceStore


def capture_folder_once(
    folder: str | Path,
    pattern: str = "*.md",
    privacy_class: str = "private",
) -> dict[str, Any]:
    root = Path(folder).expanduser()
    store = SourceStore()
    added = 0
    existing = 0
    for path in sorted(root.rglob(pattern)):
        if ".mnemion" in path.parts or "wiki" in path.parts:
            continue
        result = store.add_path(path, privacy_class=privacy_class)
        if result["status"] == "created":
            added += 1
        elif result["status"] == "existing":
            existing += 1
    return {"scanned": added + existing, "added": added, "existing": existing}
