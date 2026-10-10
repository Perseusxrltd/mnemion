"""Verified, repeatable v3 import into an explicitly owned, paused private space.

The archive is the preserved original. Only validated canonical evidence enters
the service; exceptions are counted and must be explicitly reconciled at cutover.
Derived Chroma vectors are rebuilt by the ordinary service worker.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..archives import canonical_json, file_hash, verified_archive
from ..legacy_archive import FORMAT, read_legacy_ledger
from ..legacy_freeze import MARKER
from .db import Database, Identity, migrate
from .embeddings import Generation
from .fences import exclusive_boundary
from .lifecycle import purge_memory
from .memory import MemoryService
from .models import MemoryInput, SourceInput, json_value
from .repository import audit


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def memory_id(space: UUID, collection: str, legacy_id: str) -> UUID:
    return uuid5(space, json.dumps([collection, legacy_id], ensure_ascii=False))


def _time(value, exceptions: list, reference: str, field: str):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            exceptions.append({"record": reference, "code": "naive_timestamp", "field": field})
            result = result.replace(tzinfo=timezone.utc)
        return result
    except ValueError:
        exceptions.append({"record": reference, "code": "invalid_timestamp", "field": field})
        return None


def _archived_path(root: Path, manifest: dict, original: str | None) -> Path | None:
    if not original:
        return None
    normalized = original.replace("\\", "/")
    for key, base in sorted(
        manifest["original_paths"].items(), key=lambda p: len(p[1]), reverse=True
    ):
        base = base.replace("\\", "/").rstrip("/")
        if normalized == base or normalized.startswith(base + "/"):
            path = root / manifest["layout"][key] / normalized[len(base) :].lstrip("/")
            if path.resolve().is_relative_to(root.resolve()) and path.is_file():
                return path
    return None


def _prepare(root: Path, manifest: dict, ledger: dict) -> tuple[list, dict, list, set]:
    lifecycle = json.loads((root / "logical/lifecycle.json").read_text(encoding="utf-8"))
    collections = json.loads((root / "logical/collections.json").read_text(encoding="utf-8"))
    names = {str(row["id"]): row["name"] for row in collections}
    exceptions, records = [], {}
    # Parse all rows before any database write. The archive inventory already
    # verifies complete bytes, including raw files and the lifecycle sidecar.
    with (root / "logical/drawers.jsonl").open(encoding="utf-8") as source:
        for line in source:
            if len(line.encode()) > 32 * 1024**2:
                raise ValueError("A legacy record exceeds the 32 MiB import limit")
            row = json.loads(line)
            key = (str(row["collection_id"]), row["id"])
            if key in records or key[0] not in names or not isinstance(key[1], str) or not key[1]:
                raise ValueError("Invalid or duplicate legacy record identity")
            records[key] = row
    physical_counts = Counter(key[0] for key in records)
    if any(physical_counts[str(c["id"])] != c["count"] for c in collections):
        raise ValueError("Legacy collection counts do not reconcile")
    for job in sorted(lifecycle.get("drawer_ingest_jobs", []), key=lambda r: r["write_id"]):
        if job["state"] not in ("pending", "failed"):
            continue
        key = (str(job["collection_id"]), job["drawer_id"])
        if key[0] not in names:
            raise ValueError("A durable legacy write references an unknown collection")
        payload = json.loads(job["payload_json"])
        records[key] = {
            "collection_id": key[0],
            "collection_name": names[key[0]],
            "id": key[1],
            "content": payload["content"],
            "meta": payload["metadata"],
            "pending_write_id": job["write_id"],
        }
    denials = {(str(r["collection_id"]), r["drawer_id"]) for r in ledger["deletions"]}
    for collection_id, name in names.items():
        denials.update(
            (collection_id, id_) for collection, id_ in list(denials) if collection == name
        )

    trust = {r["drawer_id"]: r for r in lifecycle.get("drawer_trust", [])}
    histories, conflicts = defaultdict(list), defaultdict(list)
    for row in lifecycle.get("drawer_trust_history", []):
        histories[row["drawer_id"]].append(row)
    for row in lifecycle.get("drawer_conflicts", []):
        for id_ in {row["drawer_id_a"], row["drawer_id_b"]}:
            conflicts[id_].append(row)
    sources = {r["id"]: r for r in lifecycle.get("raw_sources", [])}
    chunks = {
        r["embedding_id"]: r for r in lifecycle.get("source_chunks", []) if r.get("embedding_id")
    }
    referenced = {str(r.get("meta", {}).get("source_id")) for r in records.values()}
    # Raw sources without a vector chunk remain discoverable as source notes;
    # their original bytes and extracted text are still downloadable evidence.
    for source_id, source in sources.items():
        if source_id in referenced:
            continue
        text_path = _archived_path(root, manifest, source.get("raw_text_path"))
        text = text_path.read_text(encoding="utf-8") if text_path else ""
        missing_text = not text.strip()
        if missing_text:
            exceptions.append(
                {"record": "raw-source/" + source_id, "code": "source_without_extracted_text"}
            )
            text = "Imported source awaiting text extraction: " + (source.get("title") or source_id)
        for index, start in enumerate(range(0, len(text), 65000)):
            id_ = source_id if index == 0 else f"{source_id}:part:{index}"
            records[("raw-sources", id_)] = {
                "collection_id": "raw-sources",
                "collection_name": "raw-sources",
                "id": id_,
                "content": text[start : start + 65000],
                "meta": {"source_id": source_id},
                "source_record": True,
                "missing_text": missing_text,
            }

    prepared = []
    for (collection, id_), record in sorted(records.items()):
        if (collection, id_) in denials:
            continue
        reference = collection + "/" + id_
        metadata = record.get("meta") or {}
        if not isinstance(metadata, dict):
            raise ValueError("Legacy metadata must be an object")
        source = sources.get(str(metadata.get("source_id")))
        lifecycle_row = trust.get(id_) or (source if source else {})
        status = lifecycle_row.get("status", lifecycle_row.get("trust_status"))
        quarantine = bool(record.get("missing_text")) or status not in {
            "current",
            "contested",
            "superseded",
            "historical",
        }
        if metadata.get("source_id") and not source:
            exceptions.append({"record": reference, "code": "source_record_missing"})
            quarantine = True
        if not status:
            exceptions.append({"record": reference, "code": "missing_trust_quarantined"})
        elif status not in {"current", "contested", "superseded", "historical", "quarantined"}:
            exceptions.append({"record": reference, "code": "unknown_trust_quarantined"})
        related = {
            "record": record,
            "trust": lifecycle_row,
            "history": histories[id_],
            "conflicts": conflicts[id_],
            "source": source,
            "source_chunk": chunks.get(id_),
        }
        attachments = [("legacy-evidence.json", "application/json", canonical_json(related))]
        if source:
            for field in ("file_path", "raw_text_path"):
                path = _archived_path(root, manifest, source.get(field))
                if not path:
                    exceptions.append(
                        {"record": reference, "code": "source_file_missing", "field": field}
                    )
                    quarantine = True
                elif path.stat().st_size > 64 * 1024**2:
                    exceptions.append(
                        {"record": reference, "code": "source_file_over_64_mib", "field": field}
                    )
                    quarantine = True
                else:
                    expected_hash = source.get("content_hash")
                    if (
                        field == "file_path"
                        and expected_hash
                        and file_hash(path) != expected_hash.removeprefix("sha256:")
                    ):
                        exceptions.append(
                            {"record": reference, "code": "source_hash_mismatch_quarantined"}
                        )
                        quarantine = True
                    attachments.append(
                        (
                            field + "-" + path.name,
                            mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                            path,
                        )
                    )
        legacy = {
            "profile_id": manifest["profile_id"],
            "collection_id": collection,
            "collection_name": record["collection_name"],
            "id": id_,
            "trust_status": status,
            "superseded_by": lifecycle_row.get("superseded_by"),
        }
        content_metadata = {**metadata, "legacy": legacy}
        try:
            MemoryInput.small_json(content_metadata)
        except (ValueError, TypeError):
            content_metadata = {"legacy": legacy}
            exceptions.append({"record": reference, "code": "metadata_preserved_in_evidence"})
        start = _time(lifecycle_row.get("valid_from"), exceptions, reference, "valid_from")
        end = _time(lifecycle_row.get("valid_to"), exceptions, reference, "valid_to")
        if start and end and end <= start:
            exceptions.append({"record": reference, "code": "invalid_validity_interval"})
            start = end = None
            quarantine = True
        try:
            command = MemoryInput(
                content=record["content"],
                kind="note",
                metadata=content_metadata,
                subject=str(source["title"])[:500] if source and source.get("title") else None,
                claim_status={
                    "contested": "contested",
                    "superseded": "superseded",
                    "historical": "superseded",
                }.get(status, "observed"),
                valid_from=start,
                valid_to=end,
                source=SourceInput(
                    title=(
                        str(source.get("title") or "Legacy source")[:300]
                        if source
                        else "Legacy memory evidence"
                    )
                ),
            )
        except (ValueError, TypeError):
            exceptions.append({"record": reference, "code": "invalid_content_preserved_in_archive"})
            continue
        fingerprint = digest(
            {
                "record": related,
                "attachments": [
                    file_hash(a[2]) if isinstance(a[2], Path) else hashlib.sha256(a[2]).hexdigest()
                    for a in attachments
                ],
            }
        )
        prepared.append(
            {
                "collection": collection,
                "name": record["collection_name"],
                "id": id_,
                "command": command,
                "review": "quarantined" if quarantine else "ordinary",
                "attachments": attachments,
                "fingerprint": fingerprint,
                "created_at": _time(
                    lifecycle_row.get("created_at"), exceptions, reference, "created_at"
                ),
            }
        )
    return prepared, lifecycle, exceptions, denials


def import_v3(
    dsn: str,
    archive: Path,
    *,
    tenant: UUID,
    owner: UUID,
    generation: Generation,
    deletion_ledger: Path | None = None,
    final: bool = False,
    accept_exceptions: str | None = None,
    report_sink: Callable[[dict], None] | None = None,
) -> dict:
    with verified_archive(archive, FORMAT) as (manifest, root):
        snapshot = datetime.fromisoformat(manifest["snapshot_at"])
        ledger = read_legacy_ledger(deletion_ledger or root / "logical/deletions.json")
        if (
            ledger["profile_id"] != manifest["profile_id"]
            or datetime.fromisoformat(ledger["snapshot_at"]) < snapshot
        ):
            raise ValueError("Use a current deletion ledger for this legacy profile")
        paused_source = (root / "profile" / MARKER).is_file()
        if final and not paused_source:
            raise ValueError(
                "A final import requires an archive of a persistently paused legacy profile"
            )
        records, lifecycle, exceptions, denials = _prepare(root, manifest, ledger)
        migrate(dsn)
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            identity = Identity(tenant, owner, UUID(int=0))
            Database._scope(conn, tenant, owner)
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"legacy:{tenant}:{manifest['profile_id']}",),
            )
            if not conn.execute(
                "SELECT 1 FROM mnemion.principals WHERE tenant_id=%s AND id=%s AND disabled_at IS NULL",
                (tenant, owner),
            ).fetchone():
                raise ValueError("Choose an existing active owner in the destination organization")
            profile = conn.execute(
                "SELECT * FROM mnemion.legacy_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE",
                (tenant, manifest["profile_id"]),
            ).fetchone()
            if profile and (profile["owner_id"] != owner or profile["state"] != "importing"):
                raise ValueError(
                    "This profile is already mapped to another owner or has completed cutover"
                )
            if profile and profile["last_snapshot_at"] > snapshot:
                raise ValueError("An older snapshot cannot replace a later legacy import")
            space = profile["space_id"] if profile else uuid4()
            exclusive_boundary(conn, tenant, space)
            if not profile:
                conn.execute(
                    "INSERT INTO mnemion.spaces(tenant_id,id,name,description) VALUES(%s,%s,%s,%s)",
                    (
                        tenant,
                        space,
                        "Imported legacy memory",
                        "Private migration space; review the reconciliation report before cutover.",
                    ),
                )
                conn.execute(
                    "INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role) VALUES(%s,%s,%s,'administrator')",
                    (tenant, space, owner),
                )
                conn.execute(
                    "INSERT INTO mnemion.legacy_profiles(tenant_id,profile_id,space_id,owner_id) VALUES(%s,%s,%s,%s)",
                    (tenant, manifest["profile_id"], space, owner),
                )
                conn.execute(
                    "INSERT INTO mnemion.space_fences(tenant_id,space_id,token,reason) VALUES(%s,%s,%s,'legacy-import')",
                    (tenant, space, uuid4()),
                )
            conn.execute(
                "INSERT INTO mnemion.embedding_generations(id,model,configuration,dimensions) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    generation.id,
                    generation.model,
                    Jsonb(generation.configuration),
                    generation.dimensions,
                ),
            )
            service = MemoryService(None, generation)
            counts = Counter()
            seen = set()
            for collection, legacy_id in denials:
                id_ = memory_id(space, collection, legacy_id)
                conn.execute(
                    "INSERT INTO mnemion.recovery_denials(tenant_id,space_id,memory_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    (tenant, space, id_),
                )
                current = conn.execute(
                    "SELECT * FROM mnemion.memories WHERE tenant_id=%s AND id=%s FOR UPDATE",
                    (tenant, id_),
                ).fetchone()
                if current and not current["deleted_at"]:
                    conn.execute(
                        "UPDATE mnemion.memories SET deleted_at=now(),updated_at=now(),version=version+1 WHERE tenant_id=%s AND id=%s",
                        (tenant, id_),
                    )
                    conn.execute(
                        "UPDATE mnemion.jobs SET state='cancelled',lease_id=NULL,lease_until=NULL WHERE tenant_id=%s AND space_id=%s AND operation_id IN (SELECT id FROM mnemion.operations WHERE tenant_id=%s AND memory_id=%s)",
                        (tenant, space, tenant, id_),
                    )
                    conn.execute(
                        "UPDATE mnemion.operations SET state='cancelled',updated_at=now() WHERE tenant_id=%s AND memory_id=%s",
                        (tenant, id_),
                    )
                    receipt = service._operation(conn, identity, space, id_, None, "delete")
                    conn.execute(
                        "INSERT INTO mnemion.deletion_receipts(tenant_id,space_id,memory_id,operation_id,requested_by) VALUES(%s,%s,%s,%s,%s)",
                        (tenant, space, id_, receipt["operation_id"], owner),
                    )
                    purge_memory(conn, tenant, space, id_)
                    counts["withdrawn"] += 1
            alias_counts = Counter(r["id"] for r in records)
            for record in records:
                collection, legacy_id = record["collection"], record["id"]
                seen.add((collection, legacy_id))
                id_ = memory_id(space, collection, legacy_id)
                if conn.execute(
                    "SELECT 1 FROM mnemion.recovery_denials WHERE tenant_id=%s AND memory_id=%s",
                    (tenant, id_),
                ).fetchone():
                    counts["denied"] += 1
                    continue
                previous = conn.execute(
                    "SELECT * FROM mnemion.legacy_records WHERE tenant_id=%s AND space_id=%s AND collection_id=%s AND legacy_id=%s",
                    (tenant, space, collection, legacy_id),
                ).fetchone()
                current = conn.execute(
                    "SELECT * FROM mnemion.memories WHERE tenant_id=%s AND id=%s FOR UPDATE",
                    (tenant, id_),
                ).fetchone()
                if current and (not previous or current["version"] != previous["imported_version"]):
                    exceptions.append(
                        {"record": collection + "/" + legacy_id, "code": "destination_changed"}
                    )
                    continue
                if alias_counts[legacy_id] != 1:
                    exceptions.append(
                        {"record": collection + "/" + legacy_id, "code": "ambiguous_legacy_alias"}
                    )
                alias_conflict = conn.execute(
                    "SELECT memory_id FROM mnemion.legacy_aliases WHERE tenant_id=%s AND space_id=%s AND legacy_id=%s",
                    (tenant, space, legacy_id),
                ).fetchone()
                if alias_conflict and alias_conflict["memory_id"] != id_:
                    exceptions.append(
                        {"record": collection + "/" + legacy_id, "code": "existing_alias_conflict"}
                    )
                if previous and previous["fingerprint"] == record["fingerprint"]:
                    counts["unchanged"] += 1
                    continue
                version = current["version"] + 1 if current else 1
                command = record["command"]
                if not current:
                    conn.execute(
                        "INSERT INTO mnemion.memories(tenant_id,space_id,id,subject,kind,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,coalesce(%s,now()))",
                        (
                            tenant,
                            space,
                            id_,
                            command.subject,
                            command.kind,
                            owner,
                            record["created_at"],
                        ),
                    )
                revision = service._revision(conn, identity, space, id_, version, command)
                conn.execute(
                    "UPDATE mnemion.memories SET current_revision_id=%s,version=%s,review_state=%s,subject=%s,kind=%s,updated_at=now() WHERE tenant_id=%s AND id=%s",
                    (
                        revision,
                        version,
                        record["review"],
                        command.subject,
                        command.kind,
                        tenant,
                        id_,
                    ),
                )
                service._operation(
                    conn, identity, space, id_, revision, "revise" if current else "ingest"
                )
                source_revision = conn.execute(
                    "SELECT source_revision_id FROM mnemion.memory_revisions WHERE tenant_id=%s AND space_id=%s AND id=%s",
                    (tenant, space, revision),
                ).fetchone()["source_revision_id"]
                for name, media_type, content in record["attachments"]:
                    if isinstance(content, Path):
                        content = content.read_bytes()
                    conn.execute(
                        "INSERT INTO mnemion.source_attachments(tenant_id,space_id,id,source_revision_id,name,media_type,content,content_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            tenant,
                            space,
                            uuid4(),
                            source_revision,
                            name,
                            media_type,
                            content,
                            hashlib.sha256(content).hexdigest(),
                        ),
                    )
                conn.execute(
                    "INSERT INTO mnemion.legacy_records(tenant_id,space_id,collection_id,collection_name,legacy_id,memory_id,fingerprint,imported_version) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,space_id,collection_id,legacy_id) DO UPDATE SET fingerprint=excluded.fingerprint,imported_version=excluded.imported_version",
                    (
                        tenant,
                        space,
                        collection,
                        record["name"],
                        legacy_id,
                        id_,
                        record["fingerprint"],
                        version,
                    ),
                )
                aliases = [collection + ":" + legacy_id]
                if alias_counts[legacy_id] == 1:
                    aliases.append(legacy_id)
                else:
                    exceptions.append(
                        {"record": collection + "/" + legacy_id, "code": "ambiguous_legacy_alias"}
                    )
                for alias in aliases:
                    conflict = conn.execute(
                        "SELECT memory_id FROM mnemion.legacy_aliases WHERE tenant_id=%s AND space_id=%s AND legacy_id=%s",
                        (tenant, space, alias),
                    ).fetchone()
                    if conflict and conflict["memory_id"] != id_:
                        exceptions.append(
                            {
                                "record": collection + "/" + legacy_id,
                                "code": "existing_alias_conflict",
                            }
                        )
                    else:
                        conn.execute(
                            "INSERT INTO mnemion.legacy_aliases(tenant_id,space_id,legacy_id,memory_id) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (tenant, space, alias, id_),
                        )
                audit(
                    conn,
                    identity,
                    "memory.legacy_imported",
                    id_,
                    space_id=space,
                    details={"backup_id": manifest["backup_id"], "version": version},
                )
                counts["revised" if current else "created"] += 1
            for row in conn.execute(
                "SELECT r.collection_id,r.legacy_id FROM mnemion.legacy_records r JOIN mnemion.memories m ON m.tenant_id=r.tenant_id AND m.space_id=r.space_id AND m.id=r.memory_id WHERE r.tenant_id=%s AND r.space_id=%s AND m.deleted_at IS NULL",
                (tenant, space),
            ):
                if (row["collection_id"], row["legacy_id"]) not in seen:
                    exceptions.append(
                        {
                            "record": row["collection_id"] + "/" + row["legacy_id"],
                            "code": "missing_without_deletion_record",
                        }
                    )
            _import_blocks(conn, identity, space, lifecycle, exceptions, counts)
            exceptions = sorted(
                {canonical_json(e).decode(): e for e in exceptions}.values(),
                key=lambda e: canonical_json(e),
            )
            exception_hash = digest(exceptions)
            complete = final and (not exceptions or accept_exceptions == exception_hash)
            report = {
                "profile_id": manifest["profile_id"],
                "space_id": str(space),
                "owner_id": str(owner),
                "backup_id": manifest["backup_id"],
                "snapshot_at": manifest["snapshot_at"],
                "counts": dict(counts),
                "canonical_records": len(records),
                "deletion_records": len(denials),
                "exceptions": exceptions,
                "exception_sha256": exception_hash,
                "exceptions_accepted": bool(exceptions and complete),
                "cutover_complete": complete,
                "paused": not complete,
                "archive_sha256": file_hash(archive),
                "preserved_derived_tables": {
                    name: len(rows)
                    for name, rows in lifecycle.items()
                    if name.startswith(("wiki_", "cognitive_")) or name in ("triples", "entities")
                },
            }
            conn.execute(
                "UPDATE mnemion.legacy_profiles SET last_snapshot_at=%s,backup_id=%s,report=%s,state=%s,cutover_at=CASE WHEN %s THEN now() ELSE cutover_at END WHERE tenant_id=%s AND profile_id=%s",
                (
                    snapshot,
                    manifest["backup_id"],
                    Jsonb(report),
                    "active" if complete else "importing",
                    complete,
                    tenant,
                    manifest["profile_id"],
                ),
            )
            if complete:
                conn.execute(
                    "DELETE FROM mnemion.space_fences WHERE tenant_id=%s AND space_id=%s",
                    (tenant, space),
                )
            audit(
                conn,
                identity,
                "migration.cutover" if complete else "migration.imported",
                manifest["profile_id"],
                space_id=space,
                details={
                    "backup_id": manifest["backup_id"],
                    "counts": dict(counts),
                    "exception_sha256": exception_hash,
                },
            )
            if report_sink:
                report_sink(json_value(report))
            return json_value(report)


def _import_blocks(
    conn, identity: Identity, space: UUID, lifecycle: dict, exceptions: list, counts: Counter
):
    present = {str(block["key"]) for block in lifecycle.get("core_memories", [])}
    for previous in conn.execute(
        "SELECT key FROM mnemion.legacy_blocks WHERE tenant_id=%s AND space_id=%s",
        (identity.tenant_id, space),
    ):
        if previous["key"] not in present:
            exceptions.append(
                {"record": "core/" + previous["key"], "code": "source_core_block_missing"}
            )
    for block in lifecycle.get("core_memories", []):
        key, content = block["key"], block["content"]
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[\w-]{1,100}", key)
            or not isinstance(content, str)
            or len(content) > 16000
            or "\0" in content
        ):
            exceptions.append(
                {"record": "core/" + str(key), "code": "invalid_core_block_preserved_in_archive"}
            )
            continue
        fingerprint = digest(block)
        previous = conn.execute(
            "SELECT * FROM mnemion.legacy_blocks WHERE tenant_id=%s AND space_id=%s AND key=%s",
            (identity.tenant_id, space, key),
        ).fetchone()
        current = conn.execute(
            "SELECT version FROM mnemion.core_blocks WHERE tenant_id=%s AND space_id=%s AND key=%s FOR UPDATE",
            (identity.tenant_id, space, key),
        ).fetchone()
        if current and (not previous or current["version"] != previous["imported_version"]):
            exceptions.append({"record": "core/" + key, "code": "destination_changed"})
            continue
        if previous and previous["fingerprint"] == fingerprint:
            continue
        version = current["version"] + 1 if current else 1
        conn.execute(
            "INSERT INTO mnemion.core_blocks(tenant_id,space_id,key,version,content,updated_by) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,space_id,key) DO UPDATE SET version=excluded.version,content=excluded.content,updated_at=now()",
            (identity.tenant_id, space, key, version, content, identity.principal_id),
        )
        conn.execute(
            "INSERT INTO mnemion.core_block_revisions(tenant_id,space_id,key,version,content,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
            (identity.tenant_id, space, key, version, content, identity.principal_id),
        )
        conn.execute(
            "INSERT INTO mnemion.legacy_blocks(tenant_id,space_id,key,fingerprint,imported_version) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,space_id,key) DO UPDATE SET fingerprint=excluded.fingerprint,imported_version=excluded.imported_version",
            (identity.tenant_id, space, key, fingerprint, version),
        )
        counts["core_blocks"] += 1
