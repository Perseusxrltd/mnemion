"""Pause a migrated space and export its complete post-cutover state for rollback."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from ..archives import canonical_json, write_archive
from .db import Database
from .fences import exclusive_boundary, pause_space
from .models import json_value
from .repository import hydrate

FORMAT = "mnemion-v4-rollback"


def export_rollback(dsn: str, *, tenant: UUID, space: UUID, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Rollback archive output already exists")
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        profile = conn.execute(
            "SELECT * FROM mnemion.legacy_profiles WHERE tenant_id=%s AND space_id=%s",
            (tenant, space),
        ).fetchone()
        if not profile or profile["state"] not in ("active", "rollback"):
            raise ValueError("Rollback requires a migrated space with a completed cutover")
    # The committed fence waits for every acknowledged application writer. If
    # disk publication fails, leave the space paused and allow an explicit retry.
    pause = pause_space(dsn, tenant, space, reason="v3-rollback")
    with tempfile.TemporaryDirectory(prefix="mnemion-rollback-") as temporary:
        root = Path(temporary)
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            Database._scope(conn, tenant, profile["owner_id"])
            exclusive_boundary(conn, tenant, space)
            fence = conn.execute(
                "SELECT token FROM mnemion.space_fences WHERE tenant_id=%s AND space_id=%s",
                (tenant, space),
            ).fetchone()
            if not fence or str(fence["token"]) != pause["token"]:
                raise ValueError(
                    "The space was resumed during rollback preparation; pause and export again"
                )
            rows = conn.execute(
                "SELECT * FROM mnemion.memories WHERE tenant_id=%s AND space_id=%s AND deleted_at IS NULL ORDER BY id",
                (tenant, space),
            ).fetchall()
            mapping = conn.execute(
                "SELECT * FROM mnemion.legacy_records WHERE tenant_id=%s AND space_id=%s ORDER BY collection_id,legacy_id",
                (tenant, space),
            ).fetchall()
            aliases = conn.execute(
                "SELECT memory_id,legacy_id FROM mnemion.legacy_aliases WHERE tenant_id=%s AND space_id=%s ORDER BY length(legacy_id),legacy_id",
                (tenant, space),
            ).fetchall()
            aliases_by_memory = {}
            for alias in aliases:
                aliases_by_memory.setdefault(alias["memory_id"], []).append(alias["legacy_id"])
            with (root / "memories.jsonl").open("wb") as target:
                for row in rows:
                    record = hydrate(conn, row)
                    record["legacy_aliases"] = aliases_by_memory.get(row["id"], [])
                    record["history"] = [
                        hydrate(conn, row, r["id"])
                        for r in conn.execute(
                            "SELECT id FROM mnemion.memory_revisions WHERE tenant_id=%s AND memory_id=%s ORDER BY version",
                            (tenant, row["id"]),
                        )
                    ]
                    target.write(canonical_json(record) + b"\n")
            source_rows = conn.execute(
                """SELECT sr.*,s.title,s.uri FROM mnemion.source_revisions sr
                JOIN mnemion.sources s ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
                WHERE sr.tenant_id=%s AND sr.space_id=%s AND EXISTS (
                  SELECT FROM mnemion.memory_revisions r JOIN mnemion.memories m
                  ON m.tenant_id=r.tenant_id AND m.space_id=r.space_id AND m.id=r.memory_id
                  WHERE r.tenant_id=sr.tenant_id AND r.space_id=sr.space_id AND r.source_revision_id=sr.id AND m.deleted_at IS NULL)
                ORDER BY sr.id""",
                (tenant, space),
            ).fetchall()
            attachments = []
            (root / "attachments").mkdir()
            for source in source_rows:
                for attachment in conn.execute(
                    "SELECT * FROM mnemion.source_attachments WHERE tenant_id=%s AND space_id=%s AND source_revision_id=%s ORDER BY id",
                    (tenant, space, source["id"]),
                ):
                    content = bytes(attachment.pop("content"))
                    path = "attachments/" + str(attachment["id"]) + ".bin"
                    (root / path).write_bytes(content)
                    attachments.append({**json_value(attachment), "path": path})
            denials = conn.execute(
                "SELECT memory_id,requested_at FROM mnemion.recovery_denials WHERE tenant_id=%s AND space_id=%s ORDER BY memory_id",
                (tenant, space),
            ).fetchall()
            blocks = conn.execute(
                "SELECT * FROM mnemion.core_blocks WHERE tenant_id=%s AND space_id=%s ORDER BY key",
                (tenant, space),
            ).fetchall()
            space_row = conn.execute(
                "SELECT id,name FROM mnemion.spaces WHERE tenant_id=%s AND id=%s", (tenant, space)
            ).fetchone()
            block_history = conn.execute(
                "SELECT * FROM mnemion.core_block_revisions WHERE tenant_id=%s AND space_id=%s ORDER BY key,version",
                (tenant, space),
            ).fetchall()
            change_notes = conn.execute(
                """SELECT n.*,a.action,a.principal_id,a.created_at,a.details
                   FROM mnemion.memory_change_notes n JOIN mnemion.audit_events a
                     ON a.tenant_id=n.tenant_id AND a.id=n.event_id
                   JOIN mnemion.memories m ON m.tenant_id=n.tenant_id
                     AND m.space_id=n.space_id AND m.id=n.memory_id
                   WHERE n.tenant_id=%s AND n.space_id=%s AND m.deleted_at IS NULL
                   ORDER BY a.created_at,a.id""",
                (tenant, space),
            ).fetchall()
            for name, value in (
                ("mapping.json", mapping),
                ("sources.json", source_rows),
                ("attachments.json", attachments),
                ("deletions.json", denials),
                ("blocks.json", blocks),
                ("block-history.json", block_history),
                ("change-notes.json", change_notes),
                ("spaces.json", [space_row]),
            ):
                (root / name).write_bytes(canonical_json(json_value(value)))
            metadata = {
                "format": FORMAT,
                "version": 1,
                "snapshot_id": str(uuid4()),
                "snapshot_at": datetime.now(timezone.utc).isoformat(),
                "tenant_id": str(tenant),
                "space_id": str(space),
                "profile_id": profile["profile_id"],
                "base_backup_id": profile["backup_id"],
                "cutover_at": profile["cutover_at"].isoformat(),
                "pause_token": pause["token"],
                "memory_count": len(rows),
                "deletion_count": len(denials),
                "core_block_count": len(blocks),
                "attachment_count": len(attachments),
            }
            manifest = write_archive(
                output,
                {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()},
                metadata,
            )
            conn.execute(
                "UPDATE mnemion.legacy_profiles SET state='rollback' WHERE tenant_id=%s AND space_id=%s",
                (tenant, space),
            )
    return {key: value for key, value in manifest.items() if key != "files"} | {
        "archive_file": str(output),
        "paused": True,
    }
