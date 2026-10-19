"""Measure synthetic issue regressions with the shipped model and real PostgreSQL.

This is a bounded quality probe, not a representative production benchmark.
Requires the development pgserver package and a previously prepared model cache.
Run as ``python -m deploy.retrieval_regression --cache PATH --output PATH``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import statistics
import subprocess
import tempfile
import time
from uuid import UUID, uuid4

import pgserver
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.db import Database, migrate
from mnemion.service.embeddings import LocalEmbedder
from mnemion.service.memory import MemoryService
from mnemion.service.models import MemoryInput, RecallInput
from mnemion.service.retrieval import RetrievalService
from mnemion.service.worker import Worker


def evaluate(cache: Path, corpus: Path) -> dict:
    raw = corpus.read_bytes()
    fixture = json.loads(raw)
    source_root = Path(__file__).resolve().parent.parent
    implementation = hashlib.sha256()
    for path in sorted((source_root / "mnemion" / "service").rglob("*.py")):
        implementation.update(path.relative_to(source_root).as_posix().encode() + b"\0")
        implementation.update(path.read_bytes())
    embedder = LocalEmbedder(cache, threads=2, offline=True)
    embedder.query("Prepare the pinned local model before measuring queries.")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mnemion-retrieval-probe-") as directory:
        server = pgserver.get_server(Path(directory) / "postgres", cleanup_mode="stop")
        db = worker_db = None
        try:
            admin_dsn = server.get_uri()
            migrate(admin_dsn)
            roles = []
            with psycopg.connect(admin_dsn) as conn:
                for membership in ("mnemion_app", "mnemion_worker"):
                    role, password = "probe_" + uuid4().hex, secrets.token_urlsafe(32)
                    conn.execute(
                        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE {}").format(
                            sql.Identifier(role), sql.Literal(password), sql.Identifier(membership)
                        )
                    )
                    roles.append(make_conninfo(admin_dsn, user=role, password=password))
            setup = bootstrap_tenant(
                admin_dsn,
                tenant_name="Synthetic retrieval regression",
                administrator_name="Probe owner",
                generation=embedder.generation,
            )
            db, worker_db = Database(roles[0]), Database(roles[1], worker=True)
            db.open()
            worker_db.open()
            owner = db.authenticate(setup["api_key"])
            space = UUID(setup["space_id"])
            memories = MemoryService(db, embedder.generation)
            worker = Worker(worker_db, embedder)
            retrieval = RetrievalService(db, embedder)
            reference = datetime.now(timezone.utc)
            identifiers = {}
            for document in fixture["documents"]:
                saved = memories.save(
                    owner,
                    space,
                    MemoryInput(
                        content=document["content"],
                        subject=document.get("subject"),
                        metadata={
                            "path": document["path"],
                            "source_modified_at": (
                                reference - timedelta(minutes=document["age_minutes"])
                            ).isoformat(),
                        },
                    ),
                    document["id"],
                )
                identifiers[str(saved["memory_id"])] = document["id"]
            measurements = []
            for phase in ("unindexed", "indexed"):
                if phase == "indexed":
                    for _ in range(len(fixture["documents"]) * 2 + 1):
                        if not worker.run_once():
                            break
                    else:
                        raise RuntimeError("Indexing exceeded the bounded job count")
                    with psycopg.connect(admin_dsn) as conn:
                        unfinished = conn.execute(
                            "SELECT count(*) FROM mnemion.jobs WHERE state NOT IN ('ready','cancelled')"
                        ).fetchone()[0]
                    if unfinished:
                        raise RuntimeError(f"Indexing left {unfinished} unfinished jobs")
                for query in fixture["queries"]:
                    for sort in ("relevance", "recent"):
                        result = retrieval.recall(
                            owner,
                            RecallInput(
                                query=query["query"], space_ids=[space], limit=10, sort=sort
                            ),
                        )
                        if phase == "indexed" and result["index"]["pending_records"]:
                            raise RuntimeError("Measured an incomplete semantic index as complete")
                        hits = [identifiers[hit["memory_id"]] for hit in result["hits"]]
                        expected = query["expected"]
                        measurements.append(
                            {
                                "case": query["id"],
                                "phase": phase,
                                "sort": sort,
                                "query": query["query"],
                                "expected": expected,
                                "rank": hits.index(expected) + 1 if expected in hits else None,
                                "hits": [
                                    {"id": identifiers[hit["memory_id"]], "ranking": hit["ranking"]}
                                    for hit in result["hits"]
                                ],
                                "warnings": result["warnings"],
                                "pending_records": result["index"]["pending_records"],
                                "timing_ms": result["timing_ms"],
                            }
                        )
            groups = []
            for phase in ("unindexed", "indexed"):
                for sort in ("relevance", "recent"):
                    rows = [r for r in measurements if r["phase"] == phase and r["sort"] == sort]
                    groups.append(
                        {
                            "phase": phase,
                            "sort": sort,
                            "queries": len(rows),
                            "hit_at_1": sum(r["rank"] == 1 for r in rows),
                            "hit_at_4": sum(r["rank"] is not None and r["rank"] <= 4 for r in rows),
                            "mrr_at_10": round(
                                sum(1 / r["rank"] if r["rank"] else 0 for r in rows) / len(rows), 4
                            ),
                            "p50_ms": round(statistics.median(r["timing_ms"] for r in rows), 2),
                        }
                    )
            return {
                "format": 1,
                "measured_at": datetime.now(timezone.utc).isoformat(),
                "source_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
                "implementation_sha256": implementation.hexdigest(),
                "source_tree_dirty": bool(
                    subprocess.check_output(["git", "status", "--porcelain"], text=True)
                ),
                "scope": "Synthetic issue cases; real PostgreSQL, non-owner API/worker roles, pinned offline local model. Direct retrieval service, not HTTP or a production quality claim.",
                "corpus_sha256": hashlib.sha256(raw).hexdigest(),
                "documents": len(fixture["documents"]),
                "generation": embedder.generation.id,
                "model": embedder.generation.model,
                "threads": 2,
                "duration_seconds": round(time.monotonic() - started, 2),
                "summary": groups,
                "measurements": measurements,
            }
        finally:
            if worker_db:
                worker_db.close()
            if db:
                db.close()
            server.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument(
        "--corpus", type=Path, default=Path(__file__).with_name("retrieval-cases.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.cache, args.corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "summary": result["summary"]}, indent=2))


if __name__ == "__main__":
    main()
