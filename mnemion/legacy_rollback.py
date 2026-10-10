"""Reconcile a v4 tail into a new, paused legacy profile; never reopen an old copy."""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

from .archives import canonical_json, verified_archive
from .legacy_archive import (
    FORMAT as LEGACY_FORMAT,
    LEDGER_FORMAT,
    layout,
    relocate_profile,
    restore_legacy_backup,
)
from .legacy_freeze import MARKER, freeze_profile

FORMAT = "mnemion-v4-rollback"


def restore_rollback(legacy_archive: Path, tail_archive: Path, destination: Path) -> dict:
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError("Rollback destination must be a new profile directory")
    with (
        verified_archive(legacy_archive, LEGACY_FORMAT) as (base, old),
        verified_archive(tail_archive, FORMAT) as (tail, state),
    ):
        if tail["profile_id"] != base["profile_id"] or tail["base_backup_id"] != base["backup_id"]:
            raise ValueError("Use the exact legacy archive recorded by the completed cutover")
        mapping = {r["memory_id"]: r for r in json.loads((state / "mapping.json").read_text())}
        records = [json.loads(line) for line in (state / "memories.jsonl").read_text().splitlines()]
        if len(records) != tail["memory_count"] or len({r["memory_id"] for r in records}) != len(
            records
        ):
            raise ValueError("Rollback memory counts or identities do not reconcile")
        ledger = json.loads((old / "logical/deletions.json").read_text())
        additions = json.loads((state / "deletions.json").read_text())
        config_path = old / "profile/config.json"
        config = json.loads(config_path.read_text()) if config_path.exists() else {}
        primary = config.get("collection_name", "mnemion_drawers")
        for row in additions:
            original = mapping.get(row["memory_id"])
            ledger["deletions"].append(
                {
                    "collection_id": original["collection_id"] if original else primary,
                    "drawer_id": original["legacy_id"] if original else "v4:" + row["memory_id"],
                    "requested_at": row["requested_at"],
                }
            )
        ledger.pop("sha256", None)
        ledger["format"], ledger["snapshot_at"] = LEDGER_FORMAT, tail["snapshot_at"]
        ledger["sha256"] = hashlib.sha256(canonical_json(ledger)).hexdigest()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".mnemion-rollback-", dir=destination.parent
        ) as temporary:
            temporary = Path(temporary)
            ledger_path = temporary / "deletions.json"
            ledger_path.write_bytes(canonical_json(ledger))
            staged = temporary / "profile"
            restore_legacy_backup(legacy_archive, staged, deletion_ledger=ledger_path)
            # Only this unpublished staging copy is thawed for replay. The
            # original v3 profile and the v4 space both remain paused.
            (staged / MARKER).unlink()
            result_path = temporary / "result.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mnemion.legacy_rollback",
                    "apply",
                    str(staged),
                    str(state),
                    str(result_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode or not result_path.is_file():
                raise RuntimeError(
                    "Rollback replay failed; the original profiles remain paused and no destination was published. Check that the matching legacy model and dependencies are available."
                )
            outcome = json.loads(result_path.read_text())
            if outcome["verified_records"] != len(records):
                raise ValueError("Rollback canonical content verification failed")
            recovery = staged / "recovery"
            recovery.mkdir(exist_ok=True)
            shutil.copyfile(tail_archive, recovery / (tail["snapshot_id"] + ".mnemion"))
            # The full tail retains v4 revisions, sources, metadata, and team
            # scope that a single-user v3 profile cannot represent natively.
            locations = layout(staged)
            relocated = {
                **base,
                "original_paths": {key: str(value) for key, value in locations.items()},
            }
            relocate_profile(staged, destination, relocated)
            paused = freeze_profile(staged)
            if destination.exists():
                raise FileExistsError("Rollback destination appeared during preparation")
            staged.rename(destination)
    return {
        "profile": str(destination),
        "paused": True,
        "freeze_id": paused["freeze_id"],
        "snapshot_id": tail["snapshot_id"],
        "verified_records": outcome["verified_records"],
        "deletions_reconciled": len(ledger["deletions"]),
        "core_blocks": outcome["core_blocks"],
        "v4_pause_token": tail["pause_token"],
        "projections": outcome["projections"],
    }


def _apply(profile: Path, state: Path, result_path: Path):
    import chromadb

    from .embedding import get_embedding_function
    from .ingestion import LegacyMemoryWriter
    from .knowledge_graph import KnowledgeGraph
    from .trust_lifecycle import DrawerTrust

    locations = layout(profile)
    config_path = profile / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    primary = config.get("collection_name", "mnemion_drawers")
    # Select the legacy profile's own embedding pipeline. Reusing v4 E5 vectors
    # in a MiniLM collection would produce misleading search despite equal size.
    embedding = get_embedding_function(config.get("embedding_device", "cpu"))
    if embedding is None:
        raise RuntimeError("The legacy embedding function is unavailable")
    client = chromadb.PersistentClient(path=str(locations["anaktoron"]))
    mapping = {r["memory_id"]: r for r in json.loads((state / "mapping.json").read_text())}
    trust = DrawerTrust(str(locations["sidecar"]))
    writers, verified = {}, 0
    replayed = []
    with (state / "memories.jsonl").open() as source:
        for line in source:
            record = json.loads(line)
            old = mapping.get(record["memory_id"])
            name = (
                old["collection_name"]
                if old and old["collection_name"] != "raw-sources"
                else primary
            )
            id_ = (
                old["legacy_id"]
                if old and old["collection_name"] != "raw-sources"
                else "v4:" + record["memory_id"]
            )
            if name not in writers:
                collection = client.get_or_create_collection(
                    name, embedding_function=embedding, metadata={"hnsw:space": "cosine"}
                )
                writers[name] = (collection, LegacyMemoryWriter(collection, locations["sidecar"]))
            collection, writer = writers[name]
            metadata = {
                key: value
                for key, value in record["metadata"].items()
                if isinstance(value, (str, int, float, bool))
            }
            metadata.update(
                {
                    "v4_memory_id": record["memory_id"],
                    "v4_revision_id": record["revision_id"],
                    "v4_metadata_json": json.dumps(record["metadata"], ensure_ascii=False),
                    "wing": metadata.get("wing", "imported"),
                    "room": metadata.get("room", "v4-rollback"),
                }
            )
            writer.save(id_, record["content"], metadata, embedding([record["content"]])[0])
            status = (
                "quarantined"
                if record["review_state"] == "quarantined" or record["claim_status"] == "retracted"
                else {"contested": "contested", "superseded": "superseded"}.get(
                    record["claim_status"], "current"
                )
            )
            trust.update_status(
                id_, status, reason="Verified v4 rollback replay", changed_by="migration"
            )
            with sqlite3.connect(locations["sidecar"]) as conn:
                conn.execute(
                    "UPDATE drawer_trust SET valid_from=?,valid_to=? WHERE drawer_id=?",
                    (record["valid_from"], record["valid_to"], id_),
                )
            current = collection.get(ids=[id_], include=["documents"])
            if (
                not current["ids"]
                or hashlib.sha256(current["documents"][0].encode()).hexdigest()
                != record["content_hash"]
            ):
                raise ValueError("Replayed memory did not match its canonical content hash")
            verified += 1
            replayed.append({"record": record, "drawer_id": id_, "collection": name})
    blocks = json.loads((state / "blocks.json").read_text())
    graph = KnowledgeGraph(str(locations["sidecar"]))
    for block in blocks:
        graph.update_core_memory(block["key"], block["content"])
        if graph.get_core_memory(block["key"]) != block["content"]:
            raise ValueError("Replayed core block did not match")
    # Materialize original source bytes separately, with ID-based filenames to
    # avoid executing paths stored in archive metadata. The tail retains names.
    attachments_dir = locations["sources"] / "v4-rollback"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    for attachment in json.loads((state / "attachments.json").read_text()):
        source = state / attachment["path"]
        if not source.resolve().is_relative_to(state.resolve()):
            raise ValueError("Invalid rollback attachment path")
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != attachment["content_hash"]:
            raise ValueError("Rollback attachment hash does not match")
        (attachments_dir / (str(UUID(attachment["id"])) + ".bin")).write_bytes(data)
    from .legacy_projection import rebuild_projections

    projections = rebuild_projections(locations, state, replayed)
    result_path.write_bytes(
        canonical_json(
            {"verified_records": verified, "core_blocks": len(blocks), "projections": projections}
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "apply":
        raise SystemExit("Internal legacy rollback command")
    _apply(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
