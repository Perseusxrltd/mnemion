"""Obsidian owned-mirror export for Mnemion.

Mnemion remains canonical storage. This module renders a one-way Markdown
mirror that Obsidian can browse, search, and graph without changing Chroma,
SQLite trust state, or the cognitive graph.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import webbrowser
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from .vault_refresh import VaultRefreshError, bundle, refresh
from .version import __version__

MANIFEST_NAME = ".mnemion-obsidian-manifest.json"
OBSIDIAN_VAULT_ID = "mnemion-owned-mirror"
DEFAULT_PAGE_SIZE = 500


class ObsidianSafetyError(RuntimeError):
    """Raised when a mirror operation would risk user-owned files."""


@dataclass(frozen=True)
class DrawerExport:
    drawer_id: str
    document: str
    metadata: dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_segment(value: Any, fallback: str = "unknown", max_len: int = 90) -> str:
    """Return a Windows-safe and Obsidian-friendly path segment."""
    raw = str(value or "").strip()
    if not raw:
        raw = fallback
    out = []
    for char in raw:
        if char.isalnum() or char in {"-", "_", "."}:
            out.append(char)
        elif char.isspace():
            out.append("_")
        else:
            out.append("_")
    segment = "".join(out).strip(" ._")
    while "__" in segment:
        segment = segment.replace("__", "_")
    if not segment:
        segment = fallback
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
    if segment.upper() in reserved:
        segment = f"{segment}_"
    return segment[:max_len]


def wiki_link(note_path: str, alias: str | None = None) -> str:
    safe_alias = (alias or note_path).replace("|", "/").replace("[", "(").replace("]", ")")
    return f"[[{note_path}|{safe_alias}]]"


def wing_note_path(wing: str) -> str:
    return f"Wings/{safe_segment(wing)}/index"


def room_note_path(wing: str, room: str) -> str:
    return f"Wings/{safe_segment(wing)}/{safe_segment(room)}/index"


def trust_note_path(status: str) -> str:
    return f"Trust/{safe_segment(status)}"


def entity_note_path(entity: str) -> str:
    return f"Entities/{safe_segment(entity)}"


def drawer_note_path(drawer_id: str, metadata: dict[str, Any]) -> str:
    wing = str(metadata.get("wing") or "unknown")
    room = str(metadata.get("room") or "misc")
    return f"Wings/{safe_segment(wing)}/{safe_segment(room)}/{safe_segment(drawer_id)}.md"


def _flat_frontmatter(data: dict[str, Any]) -> str:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        if value is None or value == "":
            continue
        if isinstance(value, dict):
            flat[key] = json.dumps(value, sort_keys=True)
        elif isinstance(value, (list, tuple)):
            flat[key] = [str(item) for item in value]
        else:
            flat[key] = value
    return "---\n" + yaml.safe_dump(flat, sort_keys=False, allow_unicode=True).strip() + "\n---\n"


def _metadata_entities(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get("entities") or metadata.get("entity") or ""
    if isinstance(raw, str):
        parts = raw.replace(";", ",").split(",")
    elif isinstance(raw, (list, tuple, set)):
        parts = list(raw)
    else:
        parts = []
    seen: list[str] = []
    for part in parts:
        entity = str(part).strip()
        if entity and entity not in seen:
            seen.append(entity)
    return seen


def render_drawer_note(
    drawer_id: str,
    document: str,
    metadata: dict[str, Any] | None = None,
    entities: list[str] | None = None,
    cognitive_units: list[dict[str, Any]] | None = None,
    cognitive_edges: list[dict[str, Any]] | None = None,
    memory_findings: list[dict[str, Any]] | None = None,
) -> str:
    """Render one drawer as an Obsidian Markdown note."""
    metadata = metadata or {}
    wing = str(metadata.get("wing") or "unknown")
    room = str(metadata.get("room") or "misc")
    status = str(metadata.get("trust_status") or metadata.get("status") or "current")
    entities = entities if entities is not None else _metadata_entities(metadata)
    cognitive_units = cognitive_units or []
    cognitive_edges = cognitive_edges or []
    memory_findings = memory_findings or []

    frontmatter = _flat_frontmatter(
        {
            "mnemion_type": "drawer",
            "mnemion_managed": True,
            "id": drawer_id,
            "wing": wing,
            "room": room,
            "trust_status": status,
            "confidence": metadata.get("confidence"),
            "source_file": metadata.get("source_file") or metadata.get("source"),
            "agent": metadata.get("agent") or metadata.get("added_by"),
            "session_id": metadata.get("session_id"),
            "message_uuid": metadata.get("message_uuid"),
            "created_at": metadata.get("created_at"),
            "filed_at": metadata.get("filed_at"),
            "timestamp": metadata.get("timestamp"),
            "entity_count": len(entities),
            "cognitive_unit_count": len(cognitive_units),
            "memory_guard_finding_count": len(memory_findings),
            "tags": ["mnemion/drawer", f"mnemion/wing/{safe_segment(wing)}"],
        }
    )

    lines = [
        frontmatter,
        f"# {drawer_id}",
        "",
        f"- Wing: {wiki_link(wing_note_path(wing), wing)}",
        f"- Room: {wiki_link(room_note_path(wing, room), room)}",
        f"- Trust: {wiki_link(trust_note_path(status), status)}",
    ]
    if entities:
        links = ", ".join(wiki_link(entity_note_path(entity), entity) for entity in entities)
        lines.append(f"- Entities: {links}")
    if metadata.get("source_file") or metadata.get("source"):
        lines.append(f"- Source: `{metadata.get('source_file') or metadata.get('source')}`")

    if cognitive_units:
        lines.extend(["", "## Cognitive Evidence", ""])
        for unit in cognitive_units[:30]:
            unit_type = str(unit.get("unit_type") or "unit")
            text = str(unit.get("text") or "").strip()
            if text:
                lines.append(f"- **{unit_type}**: {text}")
    if cognitive_edges:
        lines.extend(["", "## Cognitive Edges", ""])
        for edge in cognitive_edges[:30]:
            edge_type = str(edge.get("edge_type") or "edge")
            source = str(edge.get("source_text") or "").strip()
            target = str(edge.get("target_text") or "").strip()
            if source or target:
                lines.append(f"- **{edge_type}**: {source} -> {target}")
    if memory_findings:
        lines.extend(["", "## Memory Guard Findings", ""])
        for finding in memory_findings[:20]:
            risk_type = str(finding.get("risk_type") or "risk")
            score = finding.get("score")
            reason = str(finding.get("reason") or "").strip()
            lines.append(f"- **{risk_type}** ({score}): {reason}")

    lines.extend(["", "## Content", "", document or "", ""])
    return "\n".join(lines)


def _iter_collection_drawers(
    collection, wing: str | None = None, page_size: int = DEFAULT_PAGE_SIZE
):
    offset = 0
    where = {"wing": wing} if wing else None
    while True:
        kwargs = {
            "limit": page_size,
            "offset": offset,
            "include": ["documents", "metadatas"],
        }
        if where:
            kwargs["where"] = where
        result = collection.get(**kwargs)
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        if not ids:
            break
        for drawer_id, doc, meta in zip(ids, docs, metas):
            yield DrawerExport(str(drawer_id), doc or "", meta or {})
        if len(ids) < page_size:
            break
        offset += page_size


def _connect_readonly(db_path: Path):
    if not db_path or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _db_rows(
    db_path: Path, table: str, query: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        if not _table_exists(conn, table):
            return []
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _load_sidecars(kg_db_path: Path) -> dict[str, Any]:
    triples = _db_rows(
        kg_db_path,
        "triples",
        "SELECT * FROM triples",
    )
    for triple in triples:
        triple["source_drawer"] = triple.get("source_drawer") or triple.get("source_closet")
    entities = _db_rows(
        kg_db_path,
        "entities",
        "SELECT name, type, aliases, created_at, updated_at FROM entities ORDER BY name",
    )
    cognitive_units = _db_rows(
        kg_db_path,
        "cognitive_units",
        "SELECT unit_id, drawer_id, unit_type, text, cues, source_file, timestamp, trust_status, created_at FROM cognitive_units ORDER BY unit_id",
    )
    cognitive_edges = _db_rows(
        kg_db_path,
        "cognitive_edges",
        "SELECT edge_id, drawer_id, edge_type, source_text, target_text, created_at FROM cognitive_edges ORDER BY edge_id",
    )
    memory_findings = _db_rows(
        kg_db_path,
        "memory_guard_findings",
        "SELECT drawer_id, risk_type, score, reason, created_at FROM memory_guard_findings ORDER BY created_at DESC",
    )
    trust = _db_rows(
        kg_db_path,
        "drawer_trust",
        "SELECT drawer_id, status, confidence, wing, room, updated_at FROM drawer_trust",
    )
    return {
        "triples": triples,
        "entities": entities,
        "cognitive_units": cognitive_units,
        "cognitive_edges": cognitive_edges,
        "memory_findings": memory_findings,
        "trust": {row["drawer_id"]: row for row in trust if row.get("drawer_id")},
    }


def _group_by_drawer(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        drawer_id = row.get("drawer_id") or row.get("source_drawer")
        if drawer_id:
            grouped[str(drawer_id)].append(row)
    return grouped


def _drawer_entities(
    drawer: DrawerExport,
    triples_by_drawer: dict[str, list[dict[str, Any]]],
) -> list[str]:
    seen = _metadata_entities(drawer.metadata)
    for triple in triples_by_drawer.get(drawer.drawer_id, []):
        for key in ("subject", "object"):
            entity = str(triple.get(key) or "").strip()
            if entity and entity not in seen:
                seen.append(entity)
    return seen


def _markdown_index(title: str, frontmatter: dict[str, Any], lines: list[str]) -> str:
    return _flat_frontmatter(frontmatter) + "\n".join([f"# {title}", "", *lines, ""])


def _render_vault_files(
    collection, kg_db_path: str | Path, wing: str | None = None
) -> tuple[dict[str, str], dict[str, Any]]:
    db_path = Path(kg_db_path).expanduser()
    sidecars = _load_sidecars(db_path)
    drawers = list(_iter_collection_drawers(collection, wing=wing))
    deleted = {
        row["drawer_id"]
        for row in _db_rows(db_path, "drawer_deletions", "SELECT drawer_id FROM drawer_deletions")
    }
    drawers = [drawer for drawer in drawers if drawer.drawer_id not in deleted]
    allowed = {drawer.drawer_id for drawer in drawers}
    sidecars["triples"] = [
        row
        for row in sidecars["triples"]
        if row.get("source_drawer") in allowed and not row.get("valid_to")
    ]
    for key in ("cognitive_units", "cognitive_edges", "memory_findings"):
        sidecars[key] = [row for row in sidecars[key] if row.get("drawer_id") in allowed]
    visible_entities = {
        entity for drawer in drawers for entity in _metadata_entities(drawer.metadata)
    } | {row.get(key) for row in sidecars["triples"] for key in ("subject", "object")}
    sidecars["entities"] = [
        row for row in sidecars["entities"] if row.get("name") in visible_entities
    ]
    trust_records = sidecars["trust"]
    triples_by_drawer = _group_by_drawer(sidecars["triples"])
    units_by_drawer = _group_by_drawer(sidecars["cognitive_units"])
    edges_by_drawer = _group_by_drawer(sidecars["cognitive_edges"])
    findings_by_drawer = _group_by_drawer(sidecars["memory_findings"])
    files: dict[str, str] = {}
    wings: dict[str, Counter[str]] = defaultdict(Counter)
    trust_counts: Counter[str] = Counter()
    drawer_paths_by_status: dict[str, list[tuple[str, str]]] = defaultdict(list)
    drawer_paths_by_room: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    entity_drawers: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def add_file(path: str, content: str) -> str:
        if path.casefold() in {key.casefold() for key in files}:
            stem, suffix = path.rsplit(".", 1) if "." in path else (path, "md")
            i = 2
            candidate = f"{stem}-{i}.{suffix}"
            while candidate.casefold() in {key.casefold() for key in files}:
                i += 1
                candidate = f"{stem}-{i}.{suffix}"
            path = candidate
        files[path] = content
        return path

    for drawer in sorted(
        drawers,
        key=lambda d: (
            str(d.metadata.get("wing") or "unknown").lower(),
            str(d.metadata.get("room") or "misc").lower(),
            d.drawer_id,
        ),
    ):
        metadata = dict(drawer.metadata)
        trust_row = trust_records.get(drawer.drawer_id)
        if trust_row:
            metadata["trust_status"] = trust_row.get("status")
            metadata["confidence"] = trust_row.get("confidence")
        wing_name = str(metadata.get("wing") or "unknown")
        room_name = str(metadata.get("room") or "misc")
        status = str(metadata.get("trust_status") or "current")
        entities = _drawer_entities(drawer, triples_by_drawer)
        note_path = drawer_note_path(drawer.drawer_id, metadata)
        note_path = add_file(
            note_path,
            render_drawer_note(
                drawer.drawer_id,
                drawer.document,
                metadata,
                entities=entities,
                cognitive_units=units_by_drawer.get(drawer.drawer_id, []),
                cognitive_edges=edges_by_drawer.get(drawer.drawer_id, []),
                memory_findings=findings_by_drawer.get(drawer.drawer_id, []),
            ),
        )
        note_ref = note_path.removesuffix(".md")
        wings[wing_name][room_name] += 1
        trust_counts[status] += 1
        drawer_paths_by_status[status].append((drawer.drawer_id, note_ref))
        drawer_paths_by_room[(wing_name, room_name)].append((drawer.drawer_id, note_ref))
        for entity in entities:
            entity_drawers[entity].append((drawer.drawer_id, note_ref))

    home_lines = [
        f"- Version: `{__version__}`",
        f"- Drawers: {len(drawers)}",
        f"- Wings: {len(wings)}",
        f"- Trust states: {len(trust_counts)}",
        f"- Last sync: {now_iso()}",
        "",
        "## Wings",
        "",
    ]
    for wing_name in sorted(wings):
        count = sum(wings[wing_name].values())
        home_lines.append(f"- {wiki_link(wing_note_path(wing_name), wing_name)}: {count}")
    home_lines.extend(["", "## Architecture", ""])
    home_lines.append(f"- {wiki_link('_Mnemion/Cognitive Graph', 'Cognitive Graph')}")
    home_lines.append(f"- {wiki_link('_Mnemion/Memory Guard', 'Memory Guard')}")
    home_lines.append(f"- {wiki_link('_Mnemion/Manifest', 'Manifest')}")
    files["Mnemion.md"] = _markdown_index(
        "Mnemion",
        {
            "mnemion_type": "home",
            "mnemion_managed": True,
            "drawer_count": len(drawers),
            "wing_count": len(wings),
        },
        home_lines,
    )

    for wing_name, rooms in sorted(wings.items()):
        lines = [f"- Home: {wiki_link('Mnemion')}", "", "## Rooms", ""]
        for room_name, count in sorted(rooms.items()):
            lines.append(f"- {wiki_link(room_note_path(wing_name, room_name), room_name)}: {count}")
        files[f"Wings/{safe_segment(wing_name)}/index.md"] = _markdown_index(
            wing_name,
            {
                "mnemion_type": "wing",
                "mnemion_managed": True,
                "wing": wing_name,
                "drawer_count": sum(rooms.values()),
            },
            lines,
        )
        for room_name in sorted(rooms):
            drawer_lines = [
                f"- Wing: {wiki_link(wing_note_path(wing_name), wing_name)}",
                f"- Drawers: {rooms[room_name]}",
                "",
                "## Drawers",
                "",
            ]
            for drawer_id, note_ref in sorted(drawer_paths_by_room[(wing_name, room_name)]):
                drawer_lines.append(f"- {wiki_link(note_ref, drawer_id)}")
            files[f"Wings/{safe_segment(wing_name)}/{safe_segment(room_name)}/index.md"] = (
                _markdown_index(
                    room_name,
                    {
                        "mnemion_type": "room",
                        "mnemion_managed": True,
                        "wing": wing_name,
                        "room": room_name,
                        "drawer_count": rooms[room_name],
                    },
                    drawer_lines,
                )
            )

    for status, drawer_refs in sorted(drawer_paths_by_status.items()):
        lines = [f"- Drawers: {len(drawer_refs)}", "", "## Drawers", ""]
        for drawer_id, note_ref in sorted(drawer_refs):
            lines.append(f"- {wiki_link(note_ref, drawer_id)}")
        files[f"Trust/{safe_segment(status)}.md"] = _markdown_index(
            status,
            {
                "mnemion_type": "trust",
                "mnemion_managed": True,
                "trust_status": status,
                "drawer_count": len(drawer_refs),
            },
            lines,
        )

    for entity in sorted(
        {row.get("name") for row in sidecars["entities"] if row.get("name")} | set(entity_drawers)
    ):
        entity_rows = [row for row in sidecars["entities"] if row.get("name") == entity]
        entity_type = entity_rows[0].get("type") if entity_rows else ""
        triples = [
            row
            for row in sidecars["triples"]
            if row.get("subject") == entity or row.get("object") == entity
        ]
        lines = []
        if entity_type:
            lines.append(f"- Type: `{entity_type}`")
        lines.extend(["", "## Drawers", ""])
        for drawer_id, note_ref in sorted(entity_drawers.get(str(entity), [])):
            lines.append(f"- {wiki_link(note_ref, drawer_id)}")
        if triples:
            lines.extend(["", "## Triples", ""])
            for triple in triples[:100]:
                lines.append(
                    f"- {triple.get('subject')} -> `{triple.get('predicate')}` -> {triple.get('object')}"
                )
        files[f"Entities/{safe_segment(entity)}.md"] = _markdown_index(
            str(entity),
            {
                "mnemion_type": "entity",
                "mnemion_managed": True,
                "entity": str(entity),
                "entity_type": entity_type,
                "drawer_count": len(entity_drawers.get(str(entity), [])),
                "triple_count": len(triples),
            },
            lines,
        )

    cog_lines = [
        f"- Cognitive units: {len(sidecars['cognitive_units'])}",
        f"- Cognitive edges: {len(sidecars['cognitive_edges'])}",
        "",
        "## Recent Units",
        "",
    ]
    for unit in sidecars["cognitive_units"][:200]:
        drawer_id = str(unit.get("drawer_id") or "")
        drawer_ref = next(
            (
                note_ref
                for refs in drawer_paths_by_room.values()
                for ref_id, note_ref in refs
                if ref_id == drawer_id
            ),
            "",
        )
        prefix = wiki_link(drawer_ref, drawer_id) if drawer_ref else f"`{drawer_id}`"
        cog_lines.append(f"- {prefix} **{unit.get('unit_type')}**: {unit.get('text')}")
    files["_Mnemion/Cognitive Graph.md"] = _markdown_index(
        "Cognitive Graph",
        {
            "mnemion_type": "cognitive_graph",
            "mnemion_managed": True,
            "unit_count": len(sidecars["cognitive_units"]),
            "edge_count": len(sidecars["cognitive_edges"]),
        },
        cog_lines,
    )

    risk_counts = Counter(
        str(row.get("risk_type") or "risk") for row in sidecars["memory_findings"]
    )
    guard_lines = [
        f"- Findings: {len(sidecars['memory_findings'])}",
        f"- Affected drawers: {len(findings_by_drawer)}",
        "",
        "## Risk Types",
        "",
    ]
    for risk_type, count in risk_counts.most_common():
        guard_lines.append(f"- `{risk_type}`: {count}")
    guard_lines.extend(["", "## Findings", ""])
    for finding in sidecars["memory_findings"][:200]:
        drawer_id = str(finding.get("drawer_id") or "")
        guard_lines.append(
            f"- `{drawer_id}` `{finding.get('risk_type')}` ({finding.get('score')}): {finding.get('reason')}"
        )
    files["_Mnemion/Memory Guard.md"] = _markdown_index(
        "Memory Guard",
        {
            "mnemion_type": "memory_guard",
            "mnemion_managed": True,
            "finding_count": len(sidecars["memory_findings"]),
            "affected_drawer_count": len(findings_by_drawer),
        },
        guard_lines,
    )

    manifest_lines = [
        f"- Generated by: Mnemion {__version__}",
        f"- Files: {len(files)}",
        f"- Drawers: {len(drawers)}",
        f"- Collection wing filter: `{wing or 'all'}`",
    ]
    files["_Mnemion/Manifest.md"] = _markdown_index(
        "Manifest",
        {
            "mnemion_type": "manifest",
            "mnemion_managed": True,
            "file_count": len(files),
            "drawer_count": len(drawers),
        },
        manifest_lines,
    )

    summary = {
        "drawer_count": len(drawers),
        "wing_count": len(wings),
        "room_count": sum(len(rooms) for rooms in wings.values()),
        "trust_counts": dict(trust_counts),
        "entity_count": len([row for row in sidecars["entities"] if row.get("name")]),
        "cognitive_unit_count": len(sidecars["cognitive_units"]),
        "memory_guard_finding_count": len(sidecars["memory_findings"]),
    }
    return dict(sorted(files.items())), summary


def _load_manifest(vault_path: Path) -> dict[str, Any] | None:
    manifest_path = vault_path / MANIFEST_NAME
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _ensure_inside(root: Path, rel_path: str) -> Path:
    rel = Path(rel_path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise ObsidianSafetyError(f"Unsafe managed path in manifest: {rel_path}")
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ObsidianSafetyError(f"Managed path escapes vault root: {rel_path}")
    return target


def _is_non_empty_without_manifest(vault_path: Path) -> bool:
    if not vault_path.exists():
        return False
    return any(vault_path.iterdir()) and not (vault_path / MANIFEST_NAME).exists()


def _is_non_empty_with_unreadable_manifest(
    vault_path: Path, manifest: dict[str, Any] | None
) -> bool:
    if not vault_path.exists() or manifest is not None:
        return False
    return (vault_path / MANIFEST_NAME).exists() and any(vault_path.iterdir())


def _inside_existing_obsidian_vault(vault_path: Path) -> Path | None:
    resolved = vault_path.expanduser().resolve()
    for parent in resolved.parents:
        if (parent / ".obsidian").exists():
            return parent
    return None


def _manifest_payload(
    vault_path: Path, files: dict[str, str], summary: dict[str, Any], wing: str | None
) -> dict[str, Any]:
    return {
        "generated_by": "mnemion",
        "version": __version__,
        "vault_path": str(vault_path),
        "synced_at": now_iso(),
        "wing": wing,
        "scope": {"type": "legacy-owner-review", "wing": wing},
        "files": sorted(files),
        **summary,
    }


def sync_obsidian_vault(
    vault_path: str | Path,
    collection,
    kg_db_path: str | Path,
    wing: str | None = None,
    force_existing: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create or refresh the managed Obsidian mirror."""
    vault = Path(vault_path).expanduser()
    previous_manifest = _load_manifest(vault)
    parent_vault = _inside_existing_obsidian_vault(vault)
    if parent_vault is not None:
        raise ObsidianSafetyError(
            f"Refusing to create an Obsidian mirror inside existing vault: {parent_vault}"
        )
    if (
        _is_non_empty_without_manifest(vault)
        or _is_non_empty_with_unreadable_manifest(vault, previous_manifest)
    ) and not force_existing:
        raise ObsidianSafetyError(
            f"Refusing to sync into non-managed non-empty folder: {vault}. "
            "Choose an empty folder, the default Mnemion vault, or pass --force-existing."
        )

    files, summary = _render_vault_files(collection, kg_db_path, wing=wing)
    manifest = _manifest_payload(vault, files, summary, wing)
    try:
        result = refresh(vault, files, manifest, MANIFEST_NAME, dry_run=dry_run)
    except VaultRefreshError as exc:
        raise ObsidianSafetyError(str(exc)) from exc
    return {
        **result,
        "vault_path": str(vault),
        "manifest_path": str(vault / MANIFEST_NAME),
        **summary,
    }


def export_obsidian_zip(
    zip_path: str | Path,
    collection,
    kg_db_path: str | Path,
    wing: str | None = None,
) -> dict[str, Any]:
    """Write an Obsidian-compatible ZIP using the same renderer as the mirror."""
    target = Path(zip_path)
    files, summary = _render_vault_files(collection, kg_db_path, wing=wing)
    manifest = _manifest_payload(Path("mnemion_vault"), files, summary, wing)
    files, manifest = bundle(files, manifest)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in files.items():
            zf.writestr(rel_path, content)
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"zip_path": str(target), "file_count": len(files), **summary}


def detect_obsidian_config_dir() -> Path | None:
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.extend([Path(appdata) / "Obsidian", Path(appdata) / "obsidian"])
    if os.name == "posix":
        candidates.extend(
            [
                Path.home() / "Library" / "Application Support" / "obsidian",
                Path.home() / ".config" / "obsidian",
                Path.home() / ".var" / "app" / "md.obsidian.Obsidian" / "config" / "obsidian",
            ]
        )
    for candidate in candidates:
        if (candidate / "obsidian.json").exists():
            return candidate
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_obsidian_config(config_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    config_path = config_dir / "obsidian.json"
    if not config_path.exists():
        return None, "Obsidian config not found"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, f"Malformed Obsidian config preserved: {config_path}"
    except OSError as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, f"Malformed Obsidian config preserved: {config_path}"
    return data, None


def register_obsidian_vault(
    vault_path: str | Path,
    obsidian_config_dir: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Best-effort register the managed mirror in Obsidian's global config."""
    config_dir = Path(obsidian_config_dir) if obsidian_config_dir else detect_obsidian_config_dir()
    if config_dir is None:
        return {"registered": False, "error": "Obsidian config directory not found"}
    config_dir = config_dir.expanduser()
    config_path = config_dir / "obsidian.json"
    data, error = _read_obsidian_config(config_dir)
    if data is None:
        return {
            "registered": False,
            "config_path": str(config_path),
            "error": error or "config unreadable",
        }

    vault = Path(vault_path).expanduser().resolve()
    if dry_run:
        return {
            "registered": False,
            "would_register": True,
            "config_path": str(config_path),
            "vault_path": str(vault),
        }

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = config_path.with_name(f"obsidian.json.{stamp}.bak")
    shutil.copy2(config_path, backup_path)
    vaults = data.setdefault("vaults", {})
    if not isinstance(vaults, dict):
        return {
            "registered": False,
            "config_path": str(config_path),
            "backup_path": str(backup_path),
            "error": "Obsidian vaults field is not an object; backup written, config preserved",
        }
    vaults[OBSIDIAN_VAULT_ID] = {
        "path": str(vault),
        "ts": int(time.time() * 1000),
        "open": True,
    }
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "registered": True,
        "config_path": str(config_path),
        "backup_path": str(backup_path),
        "vault_id": OBSIDIAN_VAULT_ID,
        "vault_path": str(vault),
    }


def obsidian_open_uri(vault_path: str | Path) -> str:
    return f"obsidian://open?path={quote(str(Path(vault_path).expanduser().resolve()))}"


def open_obsidian_vault(vault_path: str | Path, dry_run: bool = False) -> dict[str, Any]:
    uri = obsidian_open_uri(vault_path)
    if dry_run:
        return {
            "opened": False,
            "dry_run": True,
            "uri": uri,
            "vault_path": str(Path(vault_path).expanduser()),
        }
    opened = webbrowser.open(uri)
    return {"opened": bool(opened), "uri": uri, "vault_path": str(Path(vault_path).expanduser())}


def vault_status(
    vault_path: str | Path,
    obsidian_config_dir: str | Path | None = None,
) -> dict[str, Any]:
    vault = Path(vault_path).expanduser()
    manifest = _load_manifest(vault) or {}
    config_dir = Path(obsidian_config_dir) if obsidian_config_dir else detect_obsidian_config_dir()
    config_path = config_dir / "obsidian.json" if config_dir else None
    registered = False
    config_error = None
    if config_dir:
        data, config_error = _read_obsidian_config(config_dir)
        if data and isinstance(data.get("vaults"), dict):
            entry = data["vaults"].get(OBSIDIAN_VAULT_ID)
            if isinstance(entry, dict):
                registered = Path(str(entry.get("path") or "")).expanduser() == vault.expanduser()

    md_count = 0
    if vault.exists():
        md_count = sum(1 for path in vault.rglob("*.md") if path.is_file())
    return {
        "vault_path": str(vault),
        "exists": vault.exists(),
        "manifest_path": str(vault / MANIFEST_NAME),
        "managed": bool(manifest),
        "last_sync": manifest.get("synced_at"),
        "file_count": md_count,
        "drawer_count": manifest.get("drawer_count", 0),
        "wing_count": manifest.get("wing_count", 0),
        "room_count": manifest.get("room_count", 0),
        "obsidian_config_path": str(config_path) if config_path else None,
        "obsidian_config_detected": bool(config_path and config_path.exists()),
        "registered": registered,
        "config_error": config_error,
    }
