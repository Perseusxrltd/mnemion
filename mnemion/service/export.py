"""Authorized, source-backed Obsidian artifacts; no desktop filesystem access."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from ..vault_refresh import bundle
from ..portable_paths import path_key
from .db import Database, Identity, require_space, resolve_spaces
from .errors import ServiceError
from .models import ExportInput, json_value
from .markdown import inline, literal, note
from .repository import audit, hydrate, memory_row


def segment(value: str, identifier: str, length: int = 45, suffix: int = 12) -> str:
    text = re.sub(r"[^\w -]", "_", value, flags=re.UNICODE).strip(" ._")[:length] or "Memory"
    return text + "-" + identifier.replace("-", "")[:suffix]


class NotePaths:
    """Readable graph labels, with identity-based collision handling.

    Existing vaults keep their manifest paths when the title changes. The
    allocator is for fresh artifacts; it must never overwrite a same-title note
    whose identifier happens to share a prefix (including on Windows).
    """

    def __init__(self):
        self.identities: dict[tuple[str, str], str] = {}
        self.occupied: set[str] = set()

    def path(self, folder: str, title: str, identifier: str, extension: str = ".md") -> str:
        key = folder, identifier
        if key not in self.identities:
            suffix = 12
            while True:
                candidate = folder + "/" + segment(title, identifier, suffix=suffix) + extension
                if path_key(candidate) not in self.occupied:
                    self.occupied.add(path_key(candidate))
                    self.identities[key] = candidate
                    break
                suffix += 4
                if suffix > len(identifier.replace("-", "")):
                    raise ValueError("Duplicate Obsidian note path")
        return self.identities[key]


def memory_title(record: dict) -> str:
    return str(
        record["metadata"].get("title")
        or record["subject"]
        or record["content"].splitlines()[0][:100]
    )


def wikilink(path: str, label: str = "") -> str:
    # Obsidian treats an alias as text: Markdown escapes and HTML entities
    # become visible characters. Replace only link delimiters and raw HTML /
    # template openers; the original title remains exact in YAML metadata.
    label = " ".join(label.splitlines()).translate(
        str.maketrans({"|": "/", "[": "(", "]": ")", "<": "‹", ">": "›"})
    )
    return "[[" + path.removesuffix(".md") + ("|" + label if label else "") + "]]"


class RenderedFiles(dict):
    """Keep generated wiki expansion inside the native vault client's limits."""

    def __init__(self):
        super().__init__()
        self.size = 0

    def __setitem__(self, path, content):
        size = self.size + len(content.encode()) - len(self.get(path, "").encode())
        if size > 200_000_000 or (path not in self and len(self) >= 90000):
            raise ServiceError(
                413,
                "export_render_limit",
                "The generated vault is too large; select fewer spaces or memories.",
            )
        super().__setitem__(path, content)
        self.size = size


def render(snapshot: dict) -> dict[str, str]:
    files, indexes, entities, trust = (
        RenderedFiles(),
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    names = NotePaths()
    space_paths = {
        s["id"]: names.path("Wings", s["name"], s["id"], extension="") for s in snapshot["spaces"]
    }
    space_indexes = {
        s["id"]: names.path(space_paths[s["id"]], s["name"], s["id"]) for s in snapshot["spaces"]
    }
    paths = {}
    for record in snapshot["memories"]:
        root = space_paths[record["space_id"]]
        paths[record["memory_id"]] = names.path(
            root + "/Memories", memory_title(record), record["memory_id"]
        )
    for record in snapshot["memories"]:
        memory_id, space = record["memory_id"], record["space_id"]
        path, evidence = paths[memory_id], record["evidence"]
        source_path = names.path(
            "_Mnemion/Sources", "Source - " + evidence["title"], evidence["source_revision_id"]
        )
        title = memory_title(record)
        status = (
            "quarantined" if record["review_state"] == "quarantined" else record["claim_status"]
        )
        body = f"# {inline(title)}\n\n{literal(record['content'])}\n\n## Evidence\n\n"
        body += (
            "- Source: "
            + wikilink(source_path.removesuffix(".md") + "#^evidence", evidence["title"])
            + "\n"
        )
        body += f"- Space: {wikilink(space_indexes[space], snapshot['space_names'][space])}\n"
        body += f"- Status: {wikilink('Trust/' + status, status)}\n"
        related_entities = record["metadata"].get("entities", [])
        if isinstance(related_entities, str):
            related_entities = [
                item.strip() for item in related_entities.split(",") if item.strip()
            ]
        if not isinstance(related_entities, list):
            related_entities = []
        related_entities = [str(value)[:200] for value in related_entities[:30]]
        if record["subject"]:
            related_entities = [record["subject"], *related_entities]
        for entity in sorted(set(related_entities)):
            entity_id = hashlib.sha256((space + ":" + entity).encode()).hexdigest()
            entity_path = names.path("Entities", entity, entity_id)
            entities[(entity_path, entity, space)].append((path, title))
            body += f"- Entity: {wikilink(entity_path, entity)}\n"
        history_paths = []
        for revision in record.get("history", []):
            revision_path = names.path(
                "_Mnemion/Revisions",
                "Revision " + str(revision["revision_version"]) + " - " + memory_title(revision),
                revision["revision_id"],
            )
            old_evidence = revision["evidence"]
            old_source_path = names.path(
                "_Mnemion/Sources",
                "Source - " + old_evidence["title"],
                old_evidence["source_revision_id"],
            )
            history_paths.append(
                wikilink(revision_path, "Revision " + str(revision["revision_version"]))
            )
            files[revision_path] = note(
                {
                    "mnemion_type": "revision",
                    "memory_id": memory_id,
                    "revision_id": revision["revision_id"],
                    "version": revision["revision_version"],
                    "recorded_at": revision["recorded_at"],
                    "claim_status": revision["claim_status"],
                },
                f"# Revision {revision['revision_version']}\n\n{literal(revision['content'])}\n\nCurrent memory: {wikilink(path, title)}\n\nSource: {wikilink(old_source_path, old_evidence['title'])}",
            )
            files[old_source_path] = note(
                {
                    "mnemion_type": "source",
                    "source_revision_id": old_evidence["source_revision_id"],
                    "content_hash": old_evidence["content_hash"],
                    "space_id": space,
                    "start": old_evidence["start"],
                    "end": old_evidence["end"],
                },
                f"# {inline(old_evidence['title'])}\n\n{literal(old_evidence['excerpt'])}\n\n^evidence\n\nRevision: {wikilink(revision_path)}",
            )
        if history_paths:
            body += (
                "\n## Revision history\n\n"
                + "\n".join("- " + link for link in history_paths)
                + "\n"
            )
        # The canonical identity and v3 alias are both present. A copied legacy
        # vault can retain the earlier path when its manifest maps the alias.
        files[path] = note(
            {
                "mnemion_type": "memory",
                "mnemion_managed": True,
                "id": next(
                    iter(record.get("legacy_aliases", [])),
                    record["metadata"].get("legacy_id", memory_id),
                ),
                "legacy_ids": record.get("legacy_aliases", []),
                "memory_id": memory_id,
                "revision_id": record["revision_id"],
                "space_id": space,
                "kind": record["kind"],
                "subject": record["subject"],
                "aliases": [title],
                "version": record["version"],
                "claim_status": record["claim_status"],
                "review_state": record["review_state"],
                "valid_from": record["valid_from"],
                "valid_to": record["valid_to"],
                "recorded_at": record["recorded_at"],
                "tags": ["mnemion/memory", "mnemion/" + record["kind"]],
            },
            body,
        )
        files[source_path] = note(
            {
                "mnemion_type": "source",
                "source_revision_id": evidence["source_revision_id"],
                "content_hash": evidence["content_hash"],
                "space_id": space,
                "uri": evidence["uri"],
                "start": evidence["start"],
                "end": evidence["end"],
                "offset_unit": "unicode_codepoints",
            },
            f"# {inline(evidence['title'])}\n\n{literal(evidence['excerpt'])}\n\n^evidence\n\nMemory: {wikilink(path, title)}",
        )
        indexes[space].append((path, title))
        trust[status].append((path, title))
    home = ["# Mnemion", "", "Shared memory and source evidence.", "", "## Spaces", ""]
    for space in snapshot["spaces"]:
        home.append("- " + wikilink(space_indexes[space["id"]], space["name"]))
        lines = [
            "# " + inline(space["name"]),
            "",
            wikilink("Mnemion", "Home"),
            "",
            "## Memories",
            "",
        ]
        lines += ["- " + wikilink(path, title) for path, title in indexes[space["id"]]]
        blocks = [b for b in snapshot["blocks"] if b["space_id"] == space["id"]]
        if blocks:
            lines += ["", "## Core context", ""]
            for block in blocks:
                lines += ["### " + inline(block["key"]), "", literal(block["content"]), ""]
        files[space_indexes[space["id"]]] = note(
            {"mnemion_type": "space", "space_id": space["id"]}, "\n".join(lines)
        )
    records_by_path = {paths[record["memory_id"]]: record for record in snapshot["memories"]}
    for (path, name, space), links in entities.items():
        lines = [
            "# " + inline(name),
            "",
            "## Evidence-linked overview",
            "",
            "This generated page groups evidence by its recorded subject or entity. Review status remains attached to each memory.",
            "",
        ]
        for memory_path, title in links[:100]:
            record = records_by_path[memory_path]
            excerpt = record["content"][:500]
            lines.extend(
                [
                    "### " + inline(title),
                    "",
                    literal(excerpt + ("\n…" if len(record["content"]) > 500 else "")),
                    "",
                    f"{wikilink(memory_path, 'Memory and source')} · {record['claim_status']} · revision {record['version']}",
                    "",
                ]
            )
        if len(links) > 100:
            lines.extend(
                ["## Further evidence", ""]
                + ["- " + wikilink(p, title) for p, title in links[100:]]
            )
        files[path] = note(
            {
                "mnemion_type": "entity",
                "entity": name,
                "space_id": space,
                "compiler": "mnemion-evidence-wiki-v1",
                "depends_on_revisions": [records_by_path[p]["revision_id"] for p, _ in links],
            },
            "\n".join(lines),
        )
    for status, links in trust.items():
        files["Trust/" + status + ".md"] = note(
            {"mnemion_type": "status", "claim_status": status},
            "# " + status + "\n\n" + "\n".join("- " + wikilink(p, title) for p, title in links),
        )
    files["Mnemion.md"] = note(
        {
            "mnemion_type": "home",
            "exported_at": snapshot["exported_at"],
            "memory_count": len(snapshot["memories"]),
        },
        "\n".join(home),
    )
    files["_Mnemion/Cognitive Graph.md"] = note(
        {"mnemion_type": "graph_index"},
        "# Memory graph\n\nOpen Obsidian's Graph view to follow links between spaces, memories, entities, sources, and revisions.\n\n"
        + wikilink("Mnemion", "Memory index"),
    )
    files["_Mnemion/Memory Guard.md"] = note(
        {"mnemion_type": "review_policy"},
        "# Review policy\n\n"
        + (
            "This is a reviewer export and may include quarantined evidence."
            if snapshot["review"]
            else "This export contains ordinary, authorized memories. Quarantined and deleted records are excluded."
        )
        + "\n\nThe manifest records the export scope and time. Offline copies update on their next successful refresh.",
    )
    return dict(sorted(files.items()))


class ExportService:
    def __init__(self, database: Database):
        self.db = database

    def export(self, identity: Identity, command: ExportInput) -> bytes:
        with self.db.transaction(identity) as conn:
            spaces = resolve_spaces(conn, command, 30 if command.review else 10)
            space_rows = json_value(
                conn.execute(
                    "SELECT id, name FROM mnemion.spaces WHERE id=ANY(%s::uuid[]) ORDER BY id",
                    (spaces,),
                ).fetchall()
            )
            rows = conn.execute(
                """SELECT id FROM mnemion.memories WHERE space_id=ANY(%s::uuid[])
                   AND deleted_at IS NULL AND (review_state='ordinary' OR %s) ORDER BY space_id, id LIMIT 10001""",
                (spaces, command.review),
            ).fetchall()
            if len(rows) > 10000:
                raise ServiceError(
                    413,
                    "export_limit",
                    "Export at most 10,000 memories per artifact; select smaller spaces.",
                )
            records, size = [], 0
            for row in rows:
                try:
                    live = memory_row(conn, row["id"], review=command.review)
                    record = hydrate(conn, live)
                    record["legacy_aliases"] = [
                        r["legacy_id"]
                        for r in conn.execute(
                            "SELECT legacy_id FROM mnemion.legacy_aliases WHERE memory_id=%s ORDER BY length(legacy_id),legacy_id",
                            (row["id"],),
                        ).fetchall()
                    ]
                    revisions = conn.execute(
                        "SELECT id FROM mnemion.memory_revisions WHERE memory_id=%s AND id<>%s ORDER BY version",
                        (row["id"], live["current_revision_id"]),
                    ).fetchall()
                    record["history"] = [
                        hydrate(conn, live, revision["id"]) for revision in revisions
                    ]
                except ServiceError as exc:
                    if exc.status != 404:
                        raise
                    continue
                size += len(json.dumps(record, ensure_ascii=False).encode())
                if size > 100_000_000:
                    raise ServiceError(
                        413,
                        "export_size_limit",
                        "This export exceeds 100 MB; select smaller spaces.",
                    )
                records.append(record)
            blocks = json_value(
                conn.execute(
                    "SELECT space_id, key, content, version FROM mnemion.core_blocks WHERE space_id=ANY(%s::uuid[]) ORDER BY space_id, key",
                    (spaces,),
                ).fetchall()
            )
            for space in spaces:
                require_space(conn, space, 30 if command.review else 10)
            exported_at = datetime.now(timezone.utc).isoformat()
            export_id = str(uuid4())
            snapshot = {
                "export_id": export_id,
                "exported_at": exported_at,
                "spaces": space_rows,
                "space_names": {s["id"]: s["name"] for s in space_rows},
                "review": command.review,
                "memories": records,
                "blocks": blocks,
            }
            audit(
                conn,
                identity,
                "obsidian.export_prepared",
                export_id,
                details={"spaces": spaces, "review": command.review, "memories": len(records)},
            )
        files = render(snapshot)
        files, manifest = bundle(
            files,
            {
                "generated_by": "mnemion-service",
                "api_version": "v1",
                "export_id": export_id,
                "synced_at": exported_at,
                "memory_count": len(records),
                "scope": {
                    "tenant_id": str(identity.tenant_id),
                    **(
                        {"all_accessible": True, "principal_id": str(identity.principal_id)}
                        if command.all_accessible
                        else {"space_ids": sorted(str(s) for s in spaces)}
                    ),
                    "view": "review" if command.review else "ordinary",
                },
            },
        )
        output = io.BytesIO()
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True)
        if (
            sum(len(text.encode()) for text in files.values()) + len(manifest_text.encode())
            > 250_000_000
        ):
            raise ServiceError(
                413,
                "export_render_limit",
                "The generated vault exceeds the desktop limit; select fewer spaces.",
            )
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, text in files.items():
                archive.writestr(path, text)
            archive.writestr(".mnemion-obsidian-manifest.json", manifest_text)
        with self.db.transaction(identity) as conn:
            current_spaces = conn.execute(
                "SELECT id FROM mnemion.spaces WHERE id=ANY(%s::uuid[]) AND mnemion.authorized(id,%s)",
                (spaces, 30 if command.review else 10),
            ).fetchall()
            current = conn.execute(
                "SELECT id,version FROM mnemion.memories WHERE id=ANY(%s::uuid[]) AND deleted_at IS NULL AND (review_state='ordinary' OR %s)",
                ([record["memory_id"] for record in records], command.review),
            ).fetchall()
            if {row["id"] for row in current_spaces} != set(spaces) or {
                (str(row["id"]), row["version"]) for row in current
            } != {(row["memory_id"], row["version"]) for row in records}:
                raise ServiceError(
                    409,
                    "export_changed",
                    "Memory or access changed while preparing this export. Refresh to use current evidence.",
                )
            audit(
                conn,
                identity,
                "obsidian.exported",
                export_id,
                details={"spaces": spaces, "review": command.review, "memories": len(records)},
            )
        return output.getvalue()
