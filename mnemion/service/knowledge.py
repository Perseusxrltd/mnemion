"""Current, evidence-linked wiki/graph views and non-destructive curation findings."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import Field

from .contracts import Memory, ResponseModel
from .db import require_space, resolve_spaces
from .errors import ServiceError
from .models import SpaceSelection, json_value
from .markdown import inline, literal
from .repository import audit, hydrate, memory_row


class KnowledgeInput(SpaceSelection):
    subject: str | None = Field(default=None, max_length=500)
    limit: int = Field(default=250, ge=1, le=1000)
    include_historical: bool = False


class Node(ResponseModel):
    id: str
    kind: Literal["space", "memory", "source", "entity"]
    label: str
    space_id: str
    memory_id: str | None = None


class Edge(ResponseModel):
    source: str
    target: str
    relation: Literal["in_space", "cites", "about"]


class Topic(ResponseModel):
    id: str
    title: str
    space_id: str
    memory_ids: list[str]


class Finding(ResponseModel):
    kind: Literal["exact_duplicate", "contested", "unassigned_subject"]
    message: str
    memory_ids: list[str]


class Knowledge(ResponseModel):
    generated_at: str
    fingerprint: str
    truncated: bool
    memories: list[Memory]
    nodes: list[Node]
    edges: list[Edge]
    topics: list[Topic]
    findings: list[Finding]
    markdown: str


def entities(record):
    values = record["metadata"].get("entities", [])
    if isinstance(values, str):
        values = values.split(",")
    if not isinstance(values, list):
        values = []
    names = [
        str(value).strip()[:200]
        for value in values[:30]
        if isinstance(value, str) and value.strip()
    ]
    if record["subject"]:
        names.insert(0, record["subject"][:200])
    return list(dict.fromkeys(names))


def render(records: list[dict], spaces: list[dict], truncated: bool) -> dict:
    nodes, edges, topics = {}, [], {}
    findings, duplicates = [], defaultdict(list)
    space_names = {str(space["id"]): space["name"] for space in spaces}
    for record in records:
        memory, space = record["memory_id"], record["space_id"]
        space_node, memory_node = "space:" + space, "memory:" + memory
        source_node = "source:" + record["evidence"]["source_revision_id"]
        nodes[space_node] = {
            "id": space_node,
            "kind": "space",
            "label": space_names.get(space, "Space"),
            "space_id": space,
        }
        nodes[memory_node] = {
            "id": memory_node,
            "kind": "memory",
            "label": record["subject"] or record["content"].splitlines()[0][:100],
            "space_id": space,
            "memory_id": memory,
        }
        nodes[source_node] = {
            "id": source_node,
            "kind": "source",
            "label": record["evidence"]["title"],
            "space_id": space,
            "memory_id": memory,
        }
        edges.extend(
            [
                {"source": memory_node, "target": space_node, "relation": "in_space"},
                {"source": memory_node, "target": source_node, "relation": "cites"},
            ]
        )
        for name in entities(record):
            entity = "entity:" + hashlib.sha256((space + ":" + name).encode()).hexdigest()
            nodes[entity] = {"id": entity, "kind": "entity", "label": name, "space_id": space}
            edges.append({"source": memory_node, "target": entity, "relation": "about"})
        title = record["subject"] or "Unassigned · " + record["kind"]
        topic = hashlib.sha256((space + ":" + title).encode()).hexdigest()
        topics.setdefault(
            topic, {"id": topic, "title": title, "space_id": space, "memory_ids": []}
        )["memory_ids"].append(memory)
        duplicates[
            (space, hashlib.sha256(" ".join(record["content"].split()).encode()).hexdigest())
        ].append(memory)
        if record["claim_status"] == "contested":
            findings.append(
                {
                    "kind": "contested",
                    "message": "This evidence is contested. Review its current sources before using it as a decision.",
                    "memory_ids": [memory],
                }
            )
        if not record["subject"]:
            findings.append(
                {
                    "kind": "unassigned_subject",
                    "message": "A subject would make this memory easier to organize and navigate.",
                    "memory_ids": [memory],
                }
            )
    for group in duplicates.values():
        if len(group) > 1:
            findings.append(
                {
                    "kind": "exact_duplicate",
                    "message": "These memories contain the same text in this space. Check their independent sources before deciding whether to consolidate them.",
                    "memory_ids": group,
                }
            )
    ordered_topics = sorted(
        topics.values(),
        key=lambda topic: (
            space_names.get(topic["space_id"], ""),
            topic["title"].casefold(),
            topic["id"],
        ),
    )
    by_id = {record["memory_id"]: record for record in records}
    lines = [
        "# Mnemion evidence wiki",
        "",
        "Generated from current authorized revisions. Claims retain their review status; this view does not verify them.",
        "",
    ]
    if truncated:
        lines.extend(
            ["This view is partial. Select a smaller space or subject for a complete view.", ""]
        )
    for topic in ordered_topics:
        title = topic["title"].replace("\n", " ").replace("\r", " ")
        lines.extend(
            [
                "## " + inline(title),
                "",
                "Space: " + inline(space_names.get(topic["space_id"], "Space")),
                "",
            ]
        )
        for identifier in topic["memory_ids"]:
            record = by_id[identifier]
            lines.extend(
                [
                    literal(record["content"]),
                    "",
                    f"Status: {record['claim_status']} · Revision {record['version']} · [Memory](/workspace/memory/{identifier}) · [Source](/workspace/sources/{record['evidence']['source_revision_id']})",
                    "",
                ]
            )
    fingerprint = hashlib.sha256(
        json.dumps(
            [(r["memory_id"], r["version"], r["revision_id"]) for r in records], sort_keys=True
        ).encode()
    ).hexdigest()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": fingerprint,
        "truncated": truncated,
        "memories": records,
        "nodes": list(nodes.values()),
        "edges": edges,
        "topics": ordered_topics,
        "findings": findings,
        "markdown": "\n".join(lines),
    }


class KnowledgeService:
    def __init__(self, database):
        self.db = database

    def build(self, identity, command: KnowledgeInput) -> dict:
        with self.db.transaction(identity) as conn:
            spaces = resolve_spaces(conn, command)
            names = json_value(
                conn.execute(
                    "SELECT id,name FROM mnemion.spaces WHERE id=ANY(%s::uuid[])", (spaces,)
                ).fetchall()
            )
            subject = (
                command.subject.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                if command.subject
                else None
            )
            rows = conn.execute(
                """SELECT m.id FROM mnemion.memories m JOIN mnemion.memory_revisions r ON r.tenant_id=m.tenant_id
                AND r.space_id=m.space_id AND r.id=m.current_revision_id
                WHERE m.space_id=ANY(%s::uuid[]) AND m.deleted_at IS NULL AND m.review_state='ordinary'
                AND (%s::text IS NULL OR r.subject ILIKE %s)
                AND (%s OR (r.claim_status NOT IN ('retracted','superseded') AND (r.valid_from IS NULL OR r.valid_from<=now())
                  AND (r.valid_to IS NULL OR r.valid_to>now())))
                ORDER BY m.space_id,m.id LIMIT %s""",
                (
                    spaces,
                    subject,
                    f"%{subject}%" if subject else None,
                    command.include_historical,
                    command.limit + 1,
                ),
            ).fetchall()
            records, size = [], 0
            for row in rows[: command.limit]:
                try:
                    record = hydrate(conn, memory_row(conn, row["id"]))
                except ServiceError as exc:
                    if exc.status != 404:
                        raise
                    continue
                size += len(json.dumps(record, ensure_ascii=False).encode())
                if size > 25_000_000:
                    raise ServiceError(
                        413,
                        "knowledge_size_limit",
                        "Select fewer memories or a narrower subject; this view exceeds 25 MB.",
                    )
                records.append(record)
        result = render(records, names, len(rows) > command.limit)
        # Rendering must never turn a revoked/deleted revision into a cached wiki.
        with self.db.transaction(identity) as conn:
            if not command.all_accessible:
                for space in spaces:
                    require_space(conn, space)
            current = conn.execute(
                """SELECT m.id,m.version FROM mnemion.memories m JOIN mnemion.memory_revisions r
                ON r.tenant_id=m.tenant_id AND r.space_id=m.space_id AND r.id=m.current_revision_id
                WHERE m.id=ANY(%s::uuid[]) AND m.deleted_at IS NULL AND m.review_state='ordinary'
                AND (%s OR ((r.valid_from IS NULL OR r.valid_from<=now()) AND (r.valid_to IS NULL OR r.valid_to>now())))""",
                ([r["memory_id"] for r in records], command.include_historical),
            ).fetchall()
            if {(str(row["id"]), row["version"]) for row in current} != {
                (row["memory_id"], row["version"]) for row in records
            }:
                raise ServiceError(
                    409,
                    "knowledge_changed",
                    "Memory or access changed while building the view. Refresh to use current evidence.",
                )
            audit(
                conn,
                identity,
                "knowledge.viewed",
                uuid4(),
                details={"memories": len(records), "truncated": result["truncated"]},
            )
        return result
