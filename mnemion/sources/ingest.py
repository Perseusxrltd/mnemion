"""Source ingestion entrypoints used by CLI, MCP, and tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import SourceStore


def ingest_source(
    store: SourceStore,
    path: str | Path,
    source_type: str | None = None,
    title: str | None = None,
    author: str | None = None,
    privacy_class: str | None = None,
    dry_run: bool = False,
    index_embeddings: bool = False,
) -> dict[str, Any]:
    return store.add_path(
        path,
        source_type=source_type,
        title=title,
        author=author,
        privacy_class=privacy_class,
        dry_run=dry_run,
        index_embeddings=index_embeddings,
    )
