"""One leased evaluation at a time; bounded cases, live access and no gold ingestion."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from mnemion.version import __version__

from .db import Database, Identity, require_space
from .errors import ServiceError
from .evaluation_metrics import ranking_metrics, summarize_results
from .evaluations import EvaluationService, digest
from .models import ContextInput, RecallInput, json_value
from .model_state import selected_generations
from .repository import hydrate, memory_row
from .retrieval import RETRIEVAL_IMPLEMENTATION, RetrievalService

logger = logging.getLogger(__name__)


def corpus_snapshot(conn, space: UUID, generation: str) -> dict:
    """Stream identifiers, versions and readiness, never the corpus text."""
    content = hashlib.sha256()
    count = indexed = 0
    with conn.cursor(name="evaluation_corpus_" + uuid4().hex) as cursor:
        cursor.execute(
            """SELECT m.id,m.current_revision_id,m.version,m.review_state,m.deleted_at,
                EXISTS(SELECT FROM mnemion.embeddings e WHERE e.tenant_id=m.tenant_id
                  AND e.space_id=m.space_id AND e.revision_id=m.current_revision_id AND e.generation_id=%s) AS indexed
                FROM mnemion.memories m WHERE m.space_id=%s ORDER BY m.id LIMIT 100001""",
            (generation, space),
        )
        for row in cursor:
            count += 1
            if count > 100000:
                raise ServiceError(
                    413,
                    "corpus_limit",
                    "Use a selected evaluation space with at most 100,000 records.",
                )
            indexed += int(row.pop("indexed"))
            content.update(
                (json.dumps(json_value(row), sort_keys=True, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            )
    for row in conn.execute(
        "SELECT key,version FROM mnemion.core_blocks WHERE space_id=%s ORDER BY key", (space,)
    ):
        content.update(
            (json.dumps(json_value(row), sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )
    return {"sha256": content.hexdigest(), "records": count, "indexed_records": indexed}


class EvaluationRunner:
    def __init__(self, database: Database, retrieval: RetrievalService):
        if database.worker:
            raise ValueError(
                "Evaluation requires the restricted API login and the initiating caller's identity"
            )
        self.db, self.retrieval = database, retrieval
        self.service = EvaluationService(database, retrieval.embedder, registry=retrieval.registry)
        self._job: dict | None = None
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self._step_lock = threading.Lock()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._loop, name="mnemion-evaluations", daemon=True
            )
            self._thread.start()

    def stop(self):
        self._stopped.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while not self._stopped.is_set():
            try:
                worked = self.run_once()
            except Exception as exc:
                logger.warning("Evaluation runner deferred (%s)", type(exc).__name__)
                worked = False
            interval = self._job["configuration"]["interval_seconds"] if self._job else 1
            self._stopped.wait(interval if worked else 2)

    @staticmethod
    def _identity(job):
        return Identity(job["tenant_id"], job["created_by"], job["key_id"])

    def _live(self, conn, job):
        require_space(conn, job["space_id"], 30)
        row = conn.execute(
            """SELECT * FROM mnemion.evaluation_runs WHERE space_id=%s AND id=%s
            AND state='running' AND lease_id=%s AND lease_until>now() FOR UPDATE""",
            (job["space_id"], job["id"], job["lease_id"]),
        ).fetchone()
        if (
            row
            and (datetime.now(timezone.utc) - row["started_at"]).total_seconds()
            > row["configuration"]["max_seconds"]
        ):
            raise ServiceError(
                409, "time_budget_exhausted", "The evaluation exhausted its time budget."
            )
        return row

    def _heartbeat(self, job, stopped):
        while not stopped.wait(20):
            try:
                with self.db.transaction(self._identity(job)) as conn:
                    if not self._live(conn, job):
                        return
                    conn.execute(
                        "UPDATE mnemion.evaluation_runs SET lease_until=now()+interval '120 seconds' WHERE space_id=%s AND id=%s",
                        (job["space_id"], job["id"]),
                    )
            except Exception:
                return

    def run_once(self) -> bool:
        if not self._step_lock.acquire(blocking=False):
            return False
        try:
            if self._job is None:
                budget = self.retrieval.registry.memory_budget
                if budget and not budget.can_start_background():
                    return False
                with self.db.pool.connection() as conn:
                    for generation in self.retrieval.registry.generation_ids:
                        self._job = conn.execute(
                            "SELECT * FROM mnemion.claim_evaluation(%s,%s)",
                            (uuid4(), generation),
                        ).fetchone()
                        if self._job:
                            break
            if not self._job:
                return False
            job = self._job
            try:
                self._step(job)
            except Exception as exc:
                reason = "evaluation_error"
                if isinstance(exc, ServiceError):
                    reason = "access_revoked" if exc.status in (401, 403, 404) else exc.code
                    if reason not in {
                        "access_revoked",
                        "reference_unavailable",
                        "time_budget_exhausted",
                        "generation_changed",
                        "corpus_limit",
                        "inference_busy",
                        "model_not_ready",
                        "evidence_validation_failed",
                    }:
                        reason = "evaluation_error"
                with self.db.pool.connection() as conn:
                    conn.execute(
                        "SELECT mnemion.fail_evaluation(%s,%s,%s)",
                        (job["id"], job["lease_id"], reason),
                    )
                self._job = None
                logger.warning("Evaluation ended (%s)", reason)
            return True
        finally:
            self._step_lock.release()

    def _step(self, job):
        identity = self._identity(job)
        with self.db.transaction(identity) as conn:
            current = self._live(conn, job)
            if not current:
                self._job = None
                return
            job.update(current)
            dataset = self.service._dataset(conn, job["space_id"], job["dataset_id"])
            if dataset["state"] != "active":
                raise ServiceError(
                    409, "reference_unavailable", "Evaluation references are no longer available."
                )
            config = job["configuration"]
            execution_version = job["manifest"].get("execution", {}).get("service_version")
            if execution_version is not None and execution_version != __version__:
                raise ServiceError(
                    409,
                    "evaluation_error",
                    "The service changed during this evaluation. Start a new run to compare one version at a time.",
                )
            selected_generations(
                conn, [job["space_id"]], self.retrieval.embedder.generation.id, job["generation_id"]
            )
            model = self.retrieval.registry.get(job["generation_id"])
            if any(mode != "lexical" for mode in config["modes"]) or config["context"]:
                if hasattr(model, "_model") and model._model is None:
                    raise ServiceError(
                        409,
                        "model_not_ready",
                        "Prepare the configured model before running evaluations.",
                    )
            if job["manifest"]["corpus_start"] is None:
                manifest = dict(job["manifest"])
                manifest["queued_retrieval"] = manifest["retrieval"]
                manifest["retrieval"] = RETRIEVAL_IMPLEMENTATION
                snapshot = corpus_snapshot(conn, job["space_id"], job["generation_id"])
                manifest["corpus_start"] = snapshot["sha256"]
                manifest["index_start"] = snapshot
                manifest["started_at"] = datetime.now(timezone.utc).isoformat()
                manifest["execution"] = {
                    **manifest.get("execution", {}),
                    "service_version": __version__,
                }
                manifest["frozen_manifest_hash"] = digest(manifest)
                conn.execute(
                    "UPDATE mnemion.evaluation_runs SET manifest=%s WHERE space_id=%s AND id=%s",
                    (Jsonb(manifest), job["space_id"], job["id"]),
                )
                job["manifest"] = manifest
            cases = [case for case in dataset["cases"] if case["split"] == config["split"]]
            position = job["progress"]
            case, mode = (
                cases[position // len(config["modes"])],
                config["modes"][position % len(config["modes"])],
            )
            conn.execute(
                "UPDATE mnemion.evaluation_runs SET lease_until=now()+interval '120 seconds' WHERE space_id=%s AND id=%s",
                (job["space_id"], job["id"]),
            )
        stopped = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(job, stopped), daemon=True)
        heartbeat.start()
        try:
            result = self._case(
                identity,
                job["space_id"],
                case,
                mode,
                {**config, "embedding_generation": job["generation_id"]},
            )
        finally:
            stopped.set()
            heartbeat.join(timeout=1)
        with self.db.transaction(identity) as conn:
            if not self._live(conn, job):
                self._job = None
                return
            selected_generations(
                conn, [job["space_id"]], self.retrieval.embedder.generation.id, job["generation_id"]
            )
            if self.service._dataset(conn, job["space_id"], job["dataset_id"])["state"] != "active":
                raise ServiceError(
                    409, "reference_unavailable", "Evaluation references changed during retrieval."
                )
            conn.execute(
                """INSERT INTO mnemion.evaluation_results(tenant_id,space_id,run_id,position,case_id,mode,result)
                VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,space_id,run_id,position) DO NOTHING""",
                (
                    job["tenant_id"],
                    job["space_id"],
                    job["id"],
                    position,
                    case["id"],
                    mode,
                    Jsonb(result),
                ),
            )
            conn.execute(
                "UPDATE mnemion.evaluation_runs SET progress=%s WHERE space_id=%s AND id=%s",
                (position + 1, job["space_id"], job["id"]),
            )
            job["progress"] = position + 1
            if job["progress"] == job["total"]:
                snapshot = corpus_snapshot(conn, job["space_id"], job["generation_id"])
                manifest = dict(job["manifest"])
                manifest["corpus_end"] = snapshot["sha256"]
                manifest["index_end"] = snapshot
                manifest["corpus_changed"] = manifest["corpus_start"] != snapshot["sha256"]
                manifest["index_changed"] = (
                    manifest["index_start"]["indexed_records"] != snapshot["indexed_records"]
                )
                results = [
                    row["result"]
                    for row in conn.execute(
                        "SELECT result FROM mnemion.evaluation_results WHERE space_id=%s AND run_id=%s ORDER BY position",
                        (job["space_id"], job["id"]),
                    )
                ]
                summary = summarize_results(results, config["cutoffs"])
                conn.execute(
                    """UPDATE mnemion.evaluation_runs SET state='completed',finished_at=now(),
                    lease_id=NULL,lease_until=NULL,manifest=%s,summary=%s WHERE space_id=%s AND id=%s""",
                    (Jsonb(manifest), Jsonb(summary), job["space_id"], job["id"]),
                )
                self._job = None

    def _case(self, identity, space, case, mode, config):
        command = dict(
            query=case["query"],
            space_ids=[space],
            mode=mode,
            limit=max(config["cutoffs"]),
            valid_at=case["valid_at"],
            known_at=case["known_at"],
            embedding_generation=config.get("embedding_generation"),
            # Runs queued before this option existed retain their original channels.
            keyword_fallback=config.get("keyword_fallback", False),
            sort=config.get("sort", "relevance"),
            max_per_source=config.get("max_per_source", 0),
            ranking_policy=config.get("ranking_policy", {}),
        )
        started = time.monotonic()
        try:
            recall = self.retrieval.recall(identity, RecallInput(**command), origin="evaluation")
            recall_ms = (time.monotonic() - started) * 1000
            context_started = time.monotonic()
            context = (
                self.retrieval.context(
                    identity,
                    ContextInput(**command, token_budget=config["token_budget"]),
                    origin="evaluation",
                )
                if config["context"]
                else None
            )
            context_ms = (time.monotonic() - context_started) * 1000 if context else None
        except ServiceError as exc:
            if exc.status in (401, 403, 404) or exc.code == "inference_busy":
                raise
            return {
                "case_id": case["id"],
                "mode": mode,
                "category": case["category"],
                "unanswerable": case["unanswerable"],
                "status": "failed",
                "error_code": exc.code,
                "metrics": {
                    str(k): dict.fromkeys(("recall", "precision", "ndcg", "mrr", "complete"))
                    for k in config["cutoffs"]
                },
            }
        ranked = [hit["memory_id"] + ":" + hit["revision_id"] for hit in recall["hits"]]
        relevant = {
            ref["memory_id"] + ":" + ref["revision_id"]: ref["grade"] for ref in case["references"]
        }
        cited = (
            {c["memory_id"] + ":" + c["revision_id"] for c in context["citations"]}
            if context
            else set()
        )
        checked = self._verify(
            identity, space, recall["hits"], context["citations"] if context else []
        )
        return {
            "case_id": case["id"],
            "mode": mode,
            "category": case["category"],
            "unanswerable": case["unanswerable"],
            "status": "completed",
            "error_code": None,
            "metrics": {str(k): ranking_metrics(ranked, relevant, k) for k in config["cutoffs"]},
            "recall_ms": round(recall_ms, 3),
            "context_ms": round(context_ms, 3) if context_ms is not None else None,
            "ranking": [
                {
                    "memory_id": h["memory_id"],
                    "revision_id": h["revision_id"],
                    "relevance_score": h["relevance_score"],
                    "ranking": h["ranking"],
                    "memory_span": h["memory_span"],
                    "source_revision_id": h["evidence"]["source_revision_id"],
                }
                for h in recall["hits"]
            ],
            "ranking_reference_time": recall.get("ranking_reference_time"),
            "source_grouping": recall.get("source_grouping"),
            "retrieval_service_version": __version__,
            "context_recall": len(cited & relevant.keys()) / len(relevant)
            if context and relevant
            else None,
            "context_complete": relevant.keys() <= cited if context and relevant else None,
            "context_tokens": context["token_count"]
            if context and context.get("token_count_unit", "model_tokens") == "model_tokens"
            else 0,
            "context_budget_used": context["token_count"] if context else 0,
            "context_budget_unit": context.get("token_count_unit", "model_tokens")
            if context
            else None,
            "context_citations": context["citations"] if context else [],
            "citations_checked": checked,
            "citations_invalid": 0,
            "index": recall["index"],
            "warnings": sorted(set(recall["warnings"] + (context["warnings"] if context else []))),
        }

    def _verify(self, identity, space, hits, citations):
        checked = 0
        sources = {}
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            for item in [*hits, *citations]:
                if item["space_id"] != str(space):
                    raise ServiceError(
                        409, "evidence_validation_failed", "A retrieval scope check failed."
                    )
                memory = memory_row(conn, UUID(item["memory_id"]))
                fresh = hydrate(conn, memory, UUID(item["revision_id"]))
                span = item["memory_span"]
                valid = 0 <= span["start"] < span["end"] <= len(fresh["content"])
                valid = (
                    valid
                    and hashlib.sha256(fresh["content"].encode()).hexdigest()
                    == fresh["content_hash"]
                )
                if "text" in item:
                    valid = valid and item["text"] == fresh["content"][span["start"] : span["end"]]
                    valid = valid and all(
                        item["evidence"][key] == fresh["evidence"][key]
                        for key in ("source_revision_id", "content_hash")
                    )
                    start, end = item["evidence"]["start"], item["evidence"]["end"]
                    origin = fresh["evidence"]["start"]
                    valid = (
                        valid
                        and item["evidence"]["excerpt"]
                        == fresh["evidence"]["excerpt"][start - origin : end - origin]
                    )
                else:
                    valid = (
                        valid
                        and item["source_revision_id"] == fresh["evidence"]["source_revision_id"]
                    )
                    start, end = item["source_start"], item["source_end"]
                valid = (
                    valid and fresh["evidence"]["start"] <= start < end <= fresh["evidence"]["end"]
                )
                if fresh["evidence"]["excerpt"] == fresh["content"]:
                    valid = valid and (start, end) == (
                        fresh["evidence"]["start"] + span["start"],
                        fresh["evidence"]["start"] + span["end"],
                    )
                source_id = fresh["evidence"]["source_revision_id"]
                if source_id not in sources:
                    source = conn.execute(
                        "SELECT content,content_hash FROM mnemion.source_revisions WHERE space_id=%s AND id=%s",
                        (space, UUID(source_id)),
                    ).fetchone()
                    sources[source_id] = (
                        (
                            hashlib.sha256(source["content"].encode()).hexdigest(),
                            source["content_hash"],
                            len(source["content"]),
                        )
                        if source is not None
                        else (None, None, 0)
                    )
                digest, recorded_digest, length = sources[source_id]
                valid = valid and digest == recorded_digest == fresh["evidence"]["content_hash"]
                valid = (
                    valid and 0 <= fresh["evidence"]["start"] < fresh["evidence"]["end"] <= length
                )
                if not valid:
                    raise ServiceError(
                        409,
                        "evidence_validation_failed",
                        "A source hash or Unicode citation span check failed.",
                    )
                checked += 1
        return checked
