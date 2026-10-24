"""Versioned private test sets, durable run controls and comparable evidence."""

from __future__ import annotations

import csv
import base64
import hashlib
import io
import json
from datetime import datetime
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from mnemion.version import __version__

from .db import Database, Identity, require_space
from .embeddings import Embedder
from .errors import ServiceError, not_found
from .evaluation_metrics import SCORER_VERSION, bootstrap_mean
from .evaluation_models import AssessmentInput, DatasetInput, EvaluationInput
from .models import json_value
from .repository import audit, hydrate
from .request_replay import observed
from .retrieval import RETRIEVAL_IMPLEMENTATION


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


RUN_FIELDS = (
    "id",
    "space_id",
    "dataset_id",
    "generation_id",
    "state",
    "progress",
    "total",
    "configuration",
    "manifest",
    "summary",
    "error_code",
    "created_at",
    "started_at",
    "finished_at",
)
RESULT_COLUMNS = "position,case_id,mode,result,human_assessment,assessed_by,assessed_at,assessment_version,recorded_at"
DATASET_METADATA = """id,name,description,version,content_hash,state,created_at,
    jsonb_array_length(cases) AS case_count,
    (SELECT count(*) FROM jsonb_array_elements(cases) c WHERE c->>'split'='development') AS development_count"""
COMPACT_RUN_COLUMNS = ",".join(
    "manifest-'selected_cases' AS manifest"
    if field == "manifest"
    else "summary-'categories'-'definitions' AS summary"
    if field == "summary"
    else field
    for field in RUN_FIELDS
)


def history_page(space: UUID, cursor: str | None, limit: int, maximum: int) -> dict:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise ServiceError(422, "invalid_page", f"Choose a page of 1 to {maximum} entries.")
    at = after = None
    if cursor:
        try:
            if not isinstance(cursor, str) or len(cursor) > 512:
                raise ValueError()
            value = json.loads(
                base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
            )
            if (
                not isinstance(value, dict)
                or set(value) != {"at", "id", "space"}
                or any(not isinstance(field, str) for field in value.values())
            ):
                raise ValueError()
            at, after = datetime.fromisoformat(value["at"]), UUID(value["id"])
            if value["space"] != str(space) or at.tzinfo is None:
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ServiceError(
                422, "invalid_cursor", "The history cursor is invalid for this space."
            ) from None
    return {"space": space, "at": at, "after": after, "limit": limit + 1}


def history_cursor(space: UUID, rows: list[dict], limit: int) -> str | None:
    if len(rows) <= limit:
        return None
    row = rows[limit - 1]
    return base64.urlsafe_b64encode(
        json.dumps(
            {"space": str(space), "at": row["created_at"].isoformat(), "id": str(row["id"])}
        ).encode()
    ).decode()


def unavailable_references(conn, space: UUID, dataset: UUID) -> bool:
    return conn.execute(
        """SELECT EXISTS(SELECT FROM mnemion.evaluation_dependencies d
           LEFT JOIN mnemion.memories m ON m.tenant_id=d.tenant_id AND m.space_id=d.space_id AND m.id=d.memory_id
           LEFT JOIN mnemion.memory_revisions r ON r.tenant_id=d.tenant_id AND r.space_id=d.space_id AND r.id=d.revision_id
           LEFT JOIN mnemion.source_revisions sr ON sr.tenant_id=r.tenant_id AND sr.space_id=r.space_id AND sr.id=r.source_revision_id
           LEFT JOIN mnemion.sources s ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
           WHERE d.space_id=%s AND d.dataset_id=%s AND
             (m.id IS NULL OR m.deleted_at IS NOT NULL OR m.review_state<>'ordinary'
              OR r.id IS NULL OR s.id IS NULL OR s.deleted_at IS NOT NULL)) AS unavailable""",
        (space, dataset),
    ).fetchone()["unavailable"]


class EvaluationService:
    def __init__(self, database: Database, embedder: Embedder, *, registry=None):
        self.db, self.embedder = database, embedder
        from .model_registry import ModelRegistry

        self.registry = registry or ModelRegistry(embedder)

    @staticmethod
    def _dataset(conn, space: UUID, dataset: UUID, *, include_cases: bool = True) -> dict:
        row = conn.execute(
            f"SELECT {'*' if include_cases else DATASET_METADATA} FROM mnemion.evaluation_datasets WHERE space_id=%s AND id=%s",
            (space, dataset),
        ).fetchone()
        if not row:
            raise not_found()
        return EvaluationService._visible_dataset(conn, space, row)

    @staticmethod
    def _visible_dataset(conn, space: UUID, row: dict) -> dict:
        if row["state"] == "active" and unavailable_references(conn, space, row["id"]):
            row = {**row, "state": "invalidated"}
        if row["state"] != "active":
            row = {
                **row,
                "name": "Removed evaluation data",
                "description": "",
                "cases": [],
                "case_count": 0,
                "development_count": 0,
            }
        return row

    @staticmethod
    def _dataset_output(row: dict, *, include_cases: bool = False) -> dict:
        cases = row.get("cases", [])
        count = row.get("case_count", len(cases))
        development = row.get(
            "development_count", sum(case["split"] == "development" for case in cases)
        )
        return json_value(
            {
                **{
                    field: row[field]
                    for field in (
                        "id",
                        "name",
                        "description",
                        "version",
                        "content_hash",
                        "state",
                        "created_at",
                    )
                },
                "case_count": count,
                "development_count": development,
                "held_out_count": count - development,
                "cases": cases if include_cases else None,
            }
        )

    def datasets(
        self, identity: Identity, space: UUID, *, cursor: str | None = None, limit: int = 200
    ) -> dict:
        params = history_page(space, cursor, limit, 200)
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            rows = conn.execute(
                f"""SELECT {DATASET_METADATA} FROM mnemion.evaluation_datasets WHERE space_id=%(space)s
                    AND (%(at)s::timestamptz IS NULL OR (created_at,id)<(%(at)s::timestamptz,%(after)s::uuid))
                    ORDER BY created_at DESC,id DESC LIMIT %(limit)s""",
                params,
            ).fetchall()
            return {
                "items": [
                    self._dataset_output(self._visible_dataset(conn, space, row))
                    for row in rows[:limit]
                ],
                "next_cursor": history_cursor(space, rows, limit),
            }

    def dataset(self, identity: Identity, space: UUID, dataset: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            return self._dataset_output(self._dataset(conn, space, dataset), include_cases=True)

    def create_dataset(self, identity: Identity, space: UUID, command: DatasetInput) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"evaluation-datasets:{identity.tenant_id}:{space}",),
            )
            payload = command.model_dump(mode="json")
            dependencies = set()
            reference_ids = sorted(
                {
                    UUID(reference["memory_id"])
                    for case in payload["cases"]
                    for reference in case["references"]
                }
            )
            if len(reference_ids) > 5000:
                raise ServiceError(
                    422, "reference_limit", "A test set can reference at most 5,000 memories."
                )
            # Lock in a stable order so a concurrent deletion/purge cannot finish
            # between source validation and recording the erasure dependency.
            locked = {
                row["id"]: row
                for row in conn.execute(
                    "SELECT * FROM mnemion.memories WHERE space_id=%s AND id=ANY(%s::uuid[]) ORDER BY id FOR UPDATE",
                    (space, reference_ids),
                )
            }
            if len(locked) != len(reference_ids) or any(
                row["deleted_at"] or row["review_state"] != "ordinary" for row in locked.values()
            ):
                raise not_found()
            for case in payload["cases"]:
                resolved = set()
                for reference in case["references"]:
                    row = locked[UUID(reference["memory_id"])]
                    if row["space_id"] != space:
                        raise not_found()
                    revision = (
                        UUID(reference["revision_id"])
                        if reference["revision_id"]
                        else row["current_revision_id"]
                    )
                    hydrate(conn, row, revision)
                    reference["revision_id"] = str(revision)
                    pair = row["id"], revision
                    if pair in resolved:
                        raise ServiceError(
                            422,
                            "duplicate_reference",
                            "Reference labels resolve to the same revision.",
                        )
                    resolved.add(pair)
                    dependencies.add(pair)
            content_hash = digest(payload)
            previous = conn.execute(
                "SELECT * FROM mnemion.evaluation_datasets WHERE space_id=%s AND name=%s ORDER BY version DESC LIMIT 1",
                (space, command.name),
            ).fetchone()
            if (
                previous
                and previous["content_hash"] == content_hash
                and previous["state"] == "active"
            ):
                return self._dataset_output(previous, include_cases=True)
            if (
                conn.execute(
                    "SELECT count(*) AS n FROM mnemion.evaluation_datasets WHERE space_id=%s AND state='active'",
                    (space,),
                ).fetchone()["n"]
                >= 200
            ):
                raise ServiceError(
                    409,
                    "dataset_capacity",
                    "This space has reached its 200 retained dataset-version limit.",
                )
            dataset = uuid4()
            row = conn.execute(
                """INSERT INTO mnemion.evaluation_datasets
                   (tenant_id,space_id,id,name,description,version,content_hash,cases,created_by)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (
                    identity.tenant_id,
                    space,
                    dataset,
                    command.name,
                    command.description,
                    previous["version"] + 1 if previous else 1,
                    content_hash,
                    Jsonb(payload["cases"]),
                    identity.principal_id,
                ),
            ).fetchone()
            for memory, revision in sorted(dependencies):
                conn.execute(
                    """INSERT INTO mnemion.evaluation_dependencies
                    (tenant_id,space_id,dataset_id,memory_id,revision_id) VALUES(%s,%s,%s,%s,%s)""",
                    (identity.tenant_id, space, dataset, memory, revision),
                )
            audit(
                conn,
                identity,
                "evaluation.dataset_created",
                dataset,
                space_id=space,
                details={
                    "version": row["version"],
                    "case_count": len(payload["cases"]),
                    "content_hash": content_hash,
                },
            )
            return self._dataset_output(row, include_cases=True)

    def remove_dataset(self, identity: Identity, space: UUID, dataset: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            self._dataset(conn, space, dataset)
            erase_dataset(conn, identity.tenant_id, space, dataset, state="deleted")
            audit(conn, identity, "evaluation.dataset_deleted", dataset, space_id=space)
            return {"id": str(dataset), "state": "deleted"}

    @staticmethod
    def _run(conn, space: UUID, run: UUID, *, compact: bool = False) -> dict:
        row = conn.execute(
            f"SELECT {COMPACT_RUN_COLUMNS if compact else '*'} FROM mnemion.evaluation_runs WHERE space_id=%s AND id=%s",
            (space, run),
        ).fetchone()
        if not row:
            raise not_found()
        return row

    def _run_output(self, conn, row: dict, *, compact: bool = False) -> dict:
        dataset = self._dataset(conn, row["space_id"], row["dataset_id"], include_cases=False)
        result = {field: row[field] for field in RUN_FIELDS}
        if dataset["state"] != "active":
            result.update(
                state="invalidated",
                error_code="reference_unavailable",
                summary=None,
                manifest={k: v for k, v in result["manifest"].items() if k != "selected_cases"},
            )
        if compact:
            result["manifest"] = {
                k: v for k, v in result["manifest"].items() if k != "selected_cases"
            }
            if result["summary"]:
                result["summary"] = {**result["summary"], "categories": [], "definitions": {}}
        return json_value(result)

    def create_run(
        self, identity: Identity, space: UUID, command: EvaluationInput, key: str
    ) -> dict:
        if not key or len(key) > 200 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ServiceError(
                422, "idempotency_key_required", "Use a 1–200 character Idempotency-Key."
            )
        payload = command.model_dump(mode="json")
        request_hash = digest(payload)
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"evaluation-run:{identity.tenant_id}:{space}",),
            )
            previous = conn.execute(
                """SELECT * FROM mnemion.evaluation_runs WHERE space_id=%s
                AND created_by=%s AND idempotency_key=%s""",
                (space, identity.principal_id, key),
            ).fetchone()
            if previous:
                if previous["request_hash"] != request_hash:
                    raise ServiceError(
                        409,
                        "idempotency_conflict",
                        "This key was used with a different run configuration.",
                    )
                observed(True)
                return self._run_output(conn, previous)
            observed(False)
            dataset = self._dataset(conn, space, command.dataset_id)
            if dataset["state"] != "active":
                raise ServiceError(
                    409,
                    "dataset_unavailable",
                    "Create a new test-set version with current evidence.",
                )
            selected = [case for case in dataset["cases"] if case["split"] == command.split]
            if not selected:
                raise ServiceError(
                    422, "empty_split", "This test set has no cases in the selected split."
                )
            if conn.execute(
                "SELECT id FROM mnemion.evaluation_runs WHERE space_id=%s AND state IN ('queued','running')",
                (space,),
            ).fetchone():
                raise ServiceError(
                    409,
                    "evaluation_active",
                    "This space already has a queued or running evaluation.",
                )
            run = uuid4()
            from .model_state import selected_generations

            generation = selected_generations(
                conn, [space], self.embedder.generation.id, command.embedding_generation
            )[space]
            model = self.registry.get(generation)
            payload["embedding_generation"] = generation
            manifest = {
                "version": 1,
                "scorer_version": SCORER_VERSION,
                "dataset_hash": dataset["content_hash"],
                "dataset_version": dataset["version"],
                "generation": {
                    "id": model.generation.id,
                    "model": model.generation.model,
                    "dimensions": model.generation.dimensions,
                    "configuration": model.generation.configuration,
                },
                "retrieval": RETRIEVAL_IMPLEMENTATION,
                "queued_service_version": __version__,
                "selected_cases": [case["id"] for case in selected],
                "configuration": payload,
                "corpus_start": None,
                "corpus_end": None,
                "corpus_changed": None,
                "execution": {
                    "concurrency": 1,
                    "automatic_model_download": False,
                    "input_labels_indexed": False,
                },
            }
            row = conn.execute(
                """INSERT INTO mnemion.evaluation_runs
                   (tenant_id,space_id,id,dataset_id,created_by,key_id,idempotency_key,request_hash,
                    generation_id,configuration,manifest,total)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (
                    identity.tenant_id,
                    space,
                    run,
                    command.dataset_id,
                    identity.principal_id,
                    identity.key_id,
                    key,
                    request_hash,
                    model.generation.id,
                    Jsonb(payload),
                    Jsonb(manifest),
                    len(selected) * len(command.modes),
                ),
            ).fetchone()
            audit(
                conn,
                identity,
                "evaluation.queued",
                run,
                space_id=space,
                details={
                    "dataset_id": command.dataset_id,
                    "split": command.split,
                    "total": row["total"],
                },
            )
            return self._run_output(conn, row)

    def runs(
        self, identity: Identity, space: UUID, *, cursor: str | None = None, limit: int = 100
    ) -> dict:
        params = history_page(space, cursor, limit, 100)
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            rows = conn.execute(
                f"""SELECT {COMPACT_RUN_COLUMNS} FROM mnemion.evaluation_runs WHERE space_id=%(space)s
                    AND (%(at)s::timestamptz IS NULL OR (created_at,id)<(%(at)s::timestamptz,%(after)s::uuid))
                    ORDER BY created_at DESC,id DESC LIMIT %(limit)s""",
                params,
            ).fetchall()
            return {
                "items": [self._run_output(conn, row, compact=True) for row in rows[:limit]],
                "next_cursor": history_cursor(space, rows, limit),
            }

    def run(self, identity: Identity, space: UUID, run: UUID, *, compact: bool = False) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            return self._run_output(
                conn, self._run(conn, space, run, compact=compact), compact=compact
            )

    def results(
        self, identity: Identity, space: UUID, run: UUID, *, cursor: int = 0, limit: int = 50
    ) -> dict:
        if not 0 <= cursor <= 3000 or not 1 <= limit <= 100:
            raise ServiceError(
                422, "invalid_page", "Choose an evaluation result page of at most 100 cases."
            )
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            row = self._run(conn, space, run)
            if (
                self._dataset(conn, space, row["dataset_id"], include_cases=False)["state"]
                != "active"
            ):
                return {"items": [], "next_cursor": None}
            rows = conn.execute(
                f"""SELECT {RESULT_COLUMNS} FROM mnemion.evaluation_results
                WHERE space_id=%s AND run_id=%s AND position>=%s ORDER BY position LIMIT %s""",
                (space, run, cursor, limit + 1),
            ).fetchall()
            return json_value(
                {
                    "items": rows[:limit],
                    "next_cursor": rows[limit]["position"] if len(rows) > limit else None,
                }
            )

    def cancel(self, identity: Identity, space: UUID, run: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            self._run(conn, space, run)
            cancelled = conn.execute(
                """UPDATE mnemion.evaluation_runs SET state='cancelled',finished_at=now(),
                lease_id=NULL,lease_until=NULL WHERE space_id=%s AND id=%s AND state IN ('queued','running')""",
                (space, run),
            )
            if cancelled.rowcount:
                audit(conn, identity, "evaluation.cancelled", run, space_id=space)
            return self._run_output(conn, self._run(conn, space, run))

    def assess(
        self, identity: Identity, space: UUID, run: UUID, position: int, command: AssessmentInput
    ) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            row = self._run(conn, space, run)
            if (
                self._dataset(conn, space, row["dataset_id"], include_cases=False)["state"]
                != "active"
            ):
                raise not_found()
            result = conn.execute(
                f"""UPDATE mnemion.evaluation_results
                SET human_assessment=%s,assessed_by=%s,assessed_at=now(),assessment_version=assessment_version+1
                WHERE space_id=%s AND run_id=%s AND position=%s AND recorded_at=%s AND assessment_version=%s
                RETURNING {RESULT_COLUMNS}""",
                (
                    Jsonb({"label": command.label, "note": command.note}),
                    identity.principal_id,
                    space,
                    run,
                    position,
                    command.expected_recorded_at,
                    command.expected_assessment_version,
                ),
            ).fetchone()
            if not result:
                raise ServiceError(
                    409, "assessment_changed", "Reload this result before reviewing it again."
                )
            audit(
                conn,
                identity,
                "evaluation.assessed",
                run,
                space_id=space,
                details={
                    "position": position,
                    "label": command.label,
                    "version": result["assessment_version"],
                },
            )
            return json_value(result)

    def compare(self, identity: Identity, space: UUID, baseline: UUID, candidate: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            before = self._run_output(conn, self._run(conn, space, baseline))
            after = self._run_output(conn, self._run(conn, space, candidate))
            reasons = []
            if before["state"] != "completed" or after["state"] != "completed":
                reasons.append("Both runs must complete with available reference evidence.")
            for field in ("dataset_hash", "scorer_version", "corpus_start"):
                if not before["manifest"].get(field) or before["manifest"].get(field) != after[
                    "manifest"
                ].get(field):
                    reasons.append(f"The runs have different {field.replace('_', ' ')} values.")
            if before["manifest"].get("corpus_changed") or after["manifest"].get("corpus_changed"):
                reasons.append("The corpus or index changed during at least one run.")
            if before["manifest"].get("index_changed") or after["manifest"].get("index_changed"):
                reasons.append("Index coverage changed during at least one run.")
            if before["manifest"].get("index_start", {}).get("indexed_records") != after[
                "manifest"
            ].get("index_start", {}).get("indexed_records"):
                reasons.append("The runs started with different index coverage.")
            for field in ("split", "cutoffs", "context", "token_budget", "modes"):
                if before["configuration"][field] != after["configuration"][field]:
                    reasons.append(f"The {field.replace('_', ' ')} settings differ.")
            deltas = []
            if not reasons:
                entries = {}
                for name, identifier in (("baseline", baseline), ("candidate", candidate)):
                    entries[name] = {
                        (r["case_id"], r["mode"]): r["result"]
                        for r in conn.execute(
                            "SELECT case_id,mode,result FROM mnemion.evaluation_results WHERE space_id=%s AND run_id=%s ORDER BY position",
                            (space, identifier),
                        )
                    }
                for mode in before["configuration"]["modes"]:
                    for k in before["configuration"]["cutoffs"]:
                        for metric in ("recall", "precision", "ndcg", "mrr"):
                            differences = []
                            for key, a in entries["baseline"].items():
                                b = entries["candidate"].get(key)
                                if (
                                    key[1] != mode
                                    or not b
                                    or a["unanswerable"]
                                    or a["status"] != "completed"
                                    or b["status"] != "completed"
                                ):
                                    continue
                                differences.append(
                                    b["metrics"][str(k)][metric] - a["metrics"][str(k)][metric]
                                )
                            deltas.append(
                                {
                                    "mode": mode,
                                    "cutoff": k,
                                    "metric": metric,
                                    "paired_cases": len(differences),
                                    "delta": sum(differences) / len(differences)
                                    if differences
                                    else None,
                                    "paired_bootstrap95": bootstrap_mean(differences),
                                }
                            )
            return {
                "baseline": before,
                "candidate": after,
                "comparable": not reasons,
                "reasons": reasons,
                "deltas": deltas,
            }

    def export(self, identity: Identity, space: UUID, run: UUID, *, format: str) -> bytes:
        if format not in {"json", "csv"}:
            raise ServiceError(422, "invalid_export", "Choose JSON or CSV.")
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            row = self._run(conn, space, run)
            dataset = self._dataset(conn, space, row["dataset_id"])
            if dataset["state"] != "active":
                raise ServiceError(
                    409,
                    "dataset_unavailable",
                    "Evaluation data was removed or its evidence is unavailable.",
                )
            rows = conn.execute(
                f"SELECT {RESULT_COLUMNS} FROM mnemion.evaluation_results WHERE space_id=%s AND run_id=%s ORDER BY position",
                (space, run),
            ).fetchall()
            payload = json_value(
                {
                    "schema_version": 1,
                    "run": self._run_output(conn, row),
                    "dataset": self._dataset_output(dataset, include_cases=True),
                    "results": rows,
                }
            )
        if format == "json":
            data = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False).encode()
        else:
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(
                [
                    "case_id",
                    "mode",
                    "category",
                    "status",
                    "unanswerable",
                    "cutoff",
                    "recall",
                    "precision",
                    "ndcg",
                    "mrr",
                    "complete",
                    "recall_ms",
                    "context_recall",
                    "human_assessment",
                ]
            )
            for entry in payload["results"]:
                result = entry["result"]
                for cutoff, metrics in result.get("metrics", {}).items():
                    cells = [
                        entry["case_id"],
                        entry["mode"],
                        result["category"],
                        result["status"],
                        result["unanswerable"],
                        cutoff,
                        *(
                            metrics.get(field)
                            for field in ("recall", "precision", "ndcg", "mrr", "complete")
                        ),
                        result.get("recall_ms"),
                        result.get("context_recall"),
                        (entry["human_assessment"] or {}).get("label"),
                    ]
                    writer.writerow(
                        [
                            (
                                "'" + c
                                if isinstance(c, str)
                                and c.lstrip().startswith(("=", "+", "-", "@"))
                                else c
                            )
                            for c in cells
                        ]
                    )
            data = output.getvalue().encode("utf-8-sig")
        if len(data) > 32 * 1024 * 1024:
            raise ServiceError(
                413, "export_limit", "Use the paginated results API for exports larger than 32 MiB."
            )
        return data


def erase_dataset(
    conn, tenant: UUID, space: UUID, dataset: UUID, *, state: str = "invalidated"
) -> None:
    scope = tenant, space, dataset
    conn.execute(
        """UPDATE mnemion.evaluation_datasets SET state=%s,cases='[]',description='',
        name='Removed dataset '||id::text WHERE tenant_id=%s AND space_id=%s AND id=%s""",
        (state, *scope),
    )
    conn.execute(
        """DELETE FROM mnemion.evaluation_results WHERE tenant_id=%s AND space_id=%s AND run_id IN
        (SELECT id FROM mnemion.evaluation_runs WHERE tenant_id=%s AND space_id=%s AND dataset_id=%s)""",
        (tenant, space, *scope),
    )
    conn.execute(
        """UPDATE mnemion.evaluation_runs SET state='invalidated',lease_id=NULL,lease_until=NULL,
        error_code='reference_unavailable',finished_at=coalesce(finished_at,now()),summary=NULL,
        manifest=manifest-'selected_cases'
        WHERE tenant_id=%s AND space_id=%s AND dataset_id=%s""",
        scope,
    )
    conn.execute(
        "DELETE FROM mnemion.evaluation_dependencies WHERE tenant_id=%s AND space_id=%s AND dataset_id=%s",
        scope,
    )


def purge_evaluation_dependencies(conn, tenant: UUID, space: UUID, memory: UUID) -> None:
    datasets = conn.execute(
        "SELECT DISTINCT dataset_id FROM mnemion.evaluation_dependencies WHERE tenant_id=%s AND space_id=%s AND memory_id=%s",
        (tenant, space, memory),
    ).fetchall()
    for dataset in datasets:
        erase_dataset(conn, tenant, space, dataset["dataset_id"])
