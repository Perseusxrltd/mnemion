"""Rebuild legacy derived views from the verified current v4 rollback state.

Original files remain in the verified base/tail archives. A reconstructed source
view contains only current surviving memory text, so old source FTS, compiled
wiki pages, and cached graph facts cannot undo a correction or deletion.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .archives import file_hash
from .service.export import render
from .sources.chunking import sha256_hex
from .sources.store import SourceStore
from .vault_refresh import refresh


def rebuild_projections(locations: dict[str, Path], state: Path, replayed: list[dict]) -> dict:
    store = SourceStore(locations["sidecar"], locations["sources"])
    now = datetime.now(timezone.utc).isoformat()
    groups = defaultdict(list)
    for item in replayed:
        source_id = item["record"]["metadata"].get("source_id")
        if isinstance(source_id, str) and source_id:
            groups[source_id].append(item)
    stats = {
        "sources_rebuilt": 0,
        "source_chunks_rebuilt": 0,
        "source_groups_quarantined": 0,
        "wiki_pages_invalidated": 0,
        "managed_source_files_removed": 0,
        "manual_file_conflicts": [],
    }
    with store._connect() as conn:
        previous = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM raw_sources")}
        old_chunks = {
            row["embedding_id"] or row["id"]: dict(row)
            for row in conn.execute("SELECT * FROM source_chunks")
        }
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        wiki_files = (
            list(conn.execute("SELECT path,content_hash FROM wiki_pages"))
            if "wiki_pages" in tables
            else []
        )
        stats["wiki_pages_invalidated"] = len(wiki_files)
        # These are derived, rebuildable views. Canonical drawer/source evidence,
        # core context, and the complete archives are kept separately.
        for table in (
            "wiki_links",
            "wiki_claims",
            "wiki_jobs",
            "wiki_pages",
            "cognitive_edges",
            "cognitive_units",
            "cognitive_consolidated_drawers",
            "triples",
            "entities",
            "memory_guard_findings",
        ):
            if table in tables:
                conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM source_chunks_fts")
        conn.execute("DELETE FROM source_chunks")
        conn.execute("DELETE FROM raw_sources")
        for row in previous.values():
            for field in ("file_path", "raw_text_path"):
                if not row.get(field):
                    continue
                path = Path(row[field])
                # SourceStore owns copies under its source directory. Original
                # user uploads elsewhere are not managed files to erase.
                if (
                    path.is_file()
                    and path.resolve().is_relative_to(locations["sources"].resolve())
                    and not path.is_symlink()
                ):
                    path.unlink()
                    stats["managed_source_files_removed"] += 1
        for row in wiki_files:
            path = Path(row["path"])
            if not path.is_absolute():
                path = locations["wiki"] / path
            if not path.exists():
                continue
            owned = (
                path.resolve().is_relative_to(locations["wiki"].resolve())
                and not path.is_symlink()
                and path.is_file()
            )
            if (
                owned
                and row["content_hash"]
                and file_hash(path) == row["content_hash"].removeprefix("sha256:")
            ):
                path.unlink()
            else:
                stats["manual_file_conflicts"].append(
                    {"kind": "wiki", "path": str(path), "reason": "edited_or_unmanaged_file"}
                )
        for source_id, items in sorted(groups.items()):
            old = previous.get(source_id, {})
            items.sort(
                key=lambda item: (
                    old_chunks.get(item["drawer_id"], {}).get("chunk_index", 0),
                    item["drawer_id"],
                )
            )
            title = old.get("title") or items[0]["record"]["evidence"]["title"]
            body = f"# {title}\n\nRecovered source: {source_id}\n\n"
            chunks = []
            for index, item in enumerate(items):
                record = item["record"]
                start = len(body)
                body += record["content"] + "\n\n"
                old_chunk = old_chunks.get(item["drawer_id"], {})
                chunk_id = old_chunk.get("id") or "rollback-" + record["memory_id"]
                chunks.append(
                    (
                        chunk_id,
                        source_id,
                        index,
                        record["content"],
                        start,
                        start + len(record["content"]),
                        max(1, len(record["content"]) // 4),
                        sha256_hex(record["content"]),
                        item["drawer_id"],
                        json.dumps(
                            {"v4_memory_id": record["memory_id"], "collection": item["collection"]}
                        ),
                        now,
                    )
                )
            digest = sha256_hex(body)
            path = locations["sources"] / "v4-current" / (digest.removeprefix("sha256:") + ".txt")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body.encode())
            # V3 source truth applies to the whole source. A mixed group stays
            # in review rather than making one quarantined chunk ordinary.
            review = any(
                item["record"]["review_state"] != "ordinary"
                or item["record"]["claim_status"] not in {"observed", "verified"}
                for item in items
            )
            metadata = {
                "generated_by": "mnemion-v4-rollback",
                "view": "current_surviving_memories",
                "memory_ids": [item["record"]["memory_id"] for item in items],
                "original_evidence": "The verified v4 tail in the profile recovery directory",
            }
            conn.execute(
                """INSERT INTO raw_sources(id,uri,file_path,source_type,title,author,captured_at,
              content_hash,raw_text_path,metadata_json,trust_status,privacy_class,extraction_status,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source_id,
                    old.get("uri"),
                    str(path),
                    "v4-rollback",
                    title,
                    old.get("author"),
                    now,
                    digest,
                    str(path),
                    json.dumps(metadata),
                    "quarantined" if review else "current",
                    "private",
                    "ready",
                    old.get("created_at", now),
                    now,
                ),
            )
            conn.executemany(
                """INSERT INTO source_chunks(id,source_id,chunk_index,text,start_offset,end_offset,
                token_estimate,content_hash,embedding_id,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                chunks,
            )
            conn.executemany(
                "INSERT INTO source_chunks_fts(id,source_id,text) VALUES(?,?,?)",
                [(row[0], source_id, row[3]) for row in chunks],
            )
            stats["sources_rebuilt"] += 1
            stats["source_chunks_rebuilt"] += len(chunks)
            stats["source_groups_quarantined"] += int(review)

    blocks = json.loads((state / "blocks.json").read_text())
    spaces_path = state / "spaces.json"
    spaces = (
        json.loads(spaces_path.read_text())
        if spaces_path.exists()
        else [
            {"id": space, "name": "Recovered memory"}
            for space in sorted(
                {item["record"]["space_id"] for item in replayed} | {b["space_id"] for b in blocks}
            )
        ]
    )
    visible = []
    for item in replayed:
        record = item["record"]
        if record["review_state"] == "ordinary":
            visible.append(
                {
                    **record,
                    "history": [
                        r
                        for r in record.get("history", [])
                        if r["revision_id"] != record["revision_id"]
                    ],
                }
            )
    files = render(
        {
            "spaces": spaces,
            "space_names": {s["id"]: s["name"] for s in spaces},
            "exported_at": now,
            "review": False,
            "memories": visible,
            "blocks": blocks,
        }
    )
    vault = refresh(
        locations["vault"],
        files,
        {"generated_by": "mnemion-v4-rollback", "synced_at": now, "memory_count": len(visible)},
        ".mnemion-obsidian-manifest.json",
    )
    stats["vault_completed"] = vault["completed"]
    stats["vault_conflicts"] = vault["conflicts"]
    stats["ready_to_resume"] = vault["completed"] and not stats["manual_file_conflicts"]
    return stats
