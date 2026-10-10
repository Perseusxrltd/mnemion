"""Typed Python client for the versioned Mnemion service.

Retries retain one idempotency key. A transport timeout never becomes a new
write. Callers can distinguish durable acceptance from indexing completion.
"""

from __future__ import annotations

import time
import re
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

import httpx

from .service.contracts import (
    AuditEvent,
    ContextPack,
    Evidence,
    Memory,
    Page,
    Receipt,
    Recall,
    RecallHit,
    ResponseModel,
    Source,
)
from .service.models import ContextInput, MemoryInput, RecallInput, RevisionInput

if TYPE_CHECKING:
    from .service.librarian_models import (
        LibrarianChoice,
        LibrarianSettings,
        LibrarianSettingsInput,
        LibrarianRun,
        LibrarianRunItem,
        LibrarianProposal,
        LibrarianDecisionReceipt,
    )
    from .service.embedding_models import EmbeddingSettings
    from .service.knowledge import Knowledge
    from .service.insights_models import Insights, RuntimeInsights
    from .service.evaluation_models import (
        AssessmentInput,
        Comparison,
        Dataset,
        DatasetInput,
        EvaluationPage,
        EvaluationResult,
        EvaluationRun,
    )

__all__ = [
    "Client",
    "MnemionError",
    "Receipt",
    "Evidence",
    "Memory",
    "RecallHit",
    "Recall",
    "ContextPack",
    "ResponseModel",
    "Source",
    "AuditEvent",
]


class MnemionError(RuntimeError):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        request_id: str | None = None,
        *,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.status in {408, 429, 502, 503, 504}


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "").strip()
    if not value or len(value) > 128:
        return None
    if re.fullmatch(r"[0-9]{1,5}(?:\.[0-9]{1,3})?", value):
        return min(30.0, float(value))
    try:
        return min(30.0, max(0.0, parsedate_to_datetime(value).timestamp() - time.time()))
    except (TypeError, ValueError, OverflowError):
        return None


class Client:
    @staticmethod
    def _librarian_path(space_id: str) -> str:
        return f"/v1/spaces/{UUID(space_id)}/librarian"

    def librarian_choices(self, space_id: str) -> Page[LibrarianChoice]:
        from .service.librarian_models import LibrarianChoice

        return Page[LibrarianChoice].model_validate(
            self.request("GET", self._librarian_path(space_id) + "/models")
        )

    def librarian_settings(self, space_id: str) -> LibrarianSettings:
        from .service.librarian_models import LibrarianSettings

        return LibrarianSettings.model_validate(self.request("GET", self._librarian_path(space_id)))

    def configure_librarian(
        self, space_id: str, command: LibrarianSettingsInput
    ) -> LibrarianSettings:
        from .service.librarian_models import LibrarianSettings, LibrarianSettingsInput

        command = LibrarianSettingsInput.model_validate(command)
        return LibrarianSettings.model_validate(
            self.request(
                "PUT", self._librarian_path(space_id), body=command.model_dump(mode="json")
            )
        )

    def start_librarian(
        self,
        space_id: str,
        *,
        mode: Literal["organize", "review"] = "organize",
        memory_ids: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> LibrarianRun:
        from .service.librarian_models import LibrarianRun, LibrarianRunInput

        command = LibrarianRunInput(mode=mode, memory_ids=memory_ids or [])
        return LibrarianRun.model_validate(
            self.request(
                "POST",
                self._librarian_path(space_id) + "/runs",
                body=command.model_dump(mode="json"),
                key=idempotency_key or str(uuid4()),
            )
        )

    def librarian_runs(
        self, space_id: str, *, cursor: str | None = None, limit: int = 50
    ) -> Page[LibrarianRun]:
        from .service.librarian_models import LibrarianRun

        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return Page[LibrarianRun].model_validate(
            self.request("GET", self._librarian_path(space_id) + "/runs", params=params)
        )

    def librarian_run_items(self, space_id: str, run_id: str) -> Page[LibrarianRunItem]:
        from .service.librarian_models import LibrarianRunItem

        return Page[LibrarianRunItem].model_validate(
            self.request("GET", self._librarian_path(space_id) + f"/runs/{UUID(run_id)}/items")
        )

    def cancel_librarian(self, space_id: str, run_id: str) -> LibrarianRun:
        from .service.librarian_models import LibrarianRun

        return LibrarianRun.model_validate(
            self.request("POST", self._librarian_path(space_id) + f"/runs/{UUID(run_id)}/cancel")
        )

    def librarian_proposals(
        self, space_id: str, *, state: str | None = None, cursor: str | None = None, limit: int = 20
    ) -> Page[LibrarianProposal]:
        from .service.librarian_models import LibrarianProposal

        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if state:
            params["state"] = state
        return Page[LibrarianProposal].model_validate(
            self.request("GET", self._librarian_path(space_id) + "/proposals", params=params)
        )

    def decide_librarian(
        self,
        space_id: str,
        proposal_id: str,
        *,
        action: Literal["accept", "reject", "undo"],
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> LibrarianDecisionReceipt:
        from .service.librarian_models import LibrarianDecision, LibrarianDecisionReceipt

        command = LibrarianDecision(action=action, expected_version=expected_version)
        return LibrarianDecisionReceipt.model_validate(
            self.request(
                "POST",
                self._librarian_path(space_id) + f"/proposals/{UUID(proposal_id)}/decision",
                body=command.model_dump(mode="json"),
                key=idempotency_key or str(uuid4()),
            )
        )

    def embedding_settings(self, space_id: str) -> EmbeddingSettings:
        from .service.embedding_models import EmbeddingSettings

        return EmbeddingSettings.model_validate(
            self.request("GET", f"/v1/spaces/{UUID(space_id)}/embedding")
        )

    def start_reindex(
        self,
        space_id: str,
        profile_id: str,
        *,
        expected_version: int,
        approve_network_egress: bool = False,
        idempotency_key: str | None = None,
    ) -> EmbeddingSettings:
        from .service.embedding_models import EmbeddingSettings, ReindexInput

        command = ReindexInput(
            profile_id=profile_id,
            expected_version=expected_version,
            approve_network_egress=approve_network_egress,
        )
        return EmbeddingSettings.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/embedding/reindex",
                body=command.model_dump(mode="json"),
                key=idempotency_key or str(uuid4()),
            )
        )

    def control_reindex(
        self,
        space_id: str,
        run_id: str,
        action: Literal["pause", "resume", "retry", "cancel", "activate"],
        *,
        expected_version: int,
        approve_network_egress: bool = False,
    ) -> EmbeddingSettings:
        from .service.embedding_models import EmbeddingSettings, ReindexControl

        if action not in {"pause", "resume", "retry", "cancel", "activate"}:
            raise ValueError("Unknown reindex action")
        command = ReindexControl(
            expected_version=expected_version, approve_network_egress=approve_network_egress
        )
        return EmbeddingSettings.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/embedding/reindex/{UUID(run_id)}/{action}",
                body=command.model_dump(mode="json"),
            )
        )

    def resume_embedding_processing(
        self, space_id: str, *, expected_version: int, approve_network_egress: bool = False
    ) -> EmbeddingSettings:
        from .service.embedding_models import EmbeddingSettings, ReindexControl

        command = ReindexControl(
            expected_version=expected_version, approve_network_egress=approve_network_egress
        )
        return EmbeddingSettings.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/embedding/resume",
                body=command.model_dump(mode="json"),
            )
        )

    def __init__(
        self, base_url: str, api_key: str, *, timeout: float = 30, retries: int = 2, transport=None
    ):
        if not 0 <= retries <= 5:
            raise ValueError("Retries must be between 0 and 5")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": "Bearer " + api_key},
            transport=transport,
            follow_redirects=False,
        )
        self.retries = retries

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        key: str | None = None,
        params: dict | None = None,
        binary: bool = False,
    ):
        safe_retry = (
            method == "GET"
            or key is not None
            or path in ("/v1/recall", "/v1/context", "/v1/knowledge")
        )
        for attempt in range(self.retries + 1):
            delay = min(2, 0.2 * 2**attempt)
            try:
                response = self._http.request(
                    method,
                    path,
                    json=body,
                    params=params,
                    headers={"Idempotency-Key": key} if key else None,
                )
            except (httpx.TimeoutException, httpx.NetworkError):
                if not safe_retry or attempt == self.retries:
                    raise
            else:
                if response.is_success:
                    if response.status_code == 204:
                        return None
                    return response.content if binary else response.json()
                if not (
                    safe_retry
                    and response.status_code in (429, 502, 503, 504)
                    and attempt < self.retries
                ):
                    try:
                        data = response.json()
                        if not isinstance(data, dict):
                            data = {}
                        error = data.get("error", {})
                        if not isinstance(error, dict):
                            error = {}
                    except ValueError:
                        data, error = {}, {}
                    raise MnemionError(
                        response.status_code,
                        error.get("code", "http_error"),
                        error.get("message", f"Mnemion returned HTTP {response.status_code}"),
                        data.get("request_id") or response.headers.get("X-Request-ID"),
                        retry_after=_retry_after(response),
                    )
                delay = max(delay, _retry_after(response) or 0)
            time.sleep(delay)
        raise RuntimeError("Request retry loop exhausted")

    def insights(self, space_id: str, *, hours: int = 24, origin: str = "all") -> Insights:
        from .service.insights_models import Insights

        return Insights.model_validate(
            self.request(
                "GET",
                f"/v1/spaces/{UUID(space_id)}/insights",
                params={"hours": hours, "origin": origin},
            )
        )

    def runtime_insights(self) -> RuntimeInsights:
        from .service.insights_models import RuntimeInsights

        return RuntimeInsights.model_validate(self.request("GET", "/v1/insights/runtime"))

    @staticmethod
    def _evaluation_path(space_id: str) -> str:
        return f"/v1/spaces/{UUID(space_id)}/evaluations"

    def evaluation_datasets(self, space_id: str) -> list[Dataset]:
        return self.evaluation_dataset_page(space_id).items

    def evaluation_dataset_page(
        self, space_id: str, *, cursor: str | None = None, limit: int = 200
    ) -> Page[Dataset]:
        from .service.evaluation_models import Dataset

        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return Page[Dataset].model_validate(
            self.request("GET", self._evaluation_path(space_id) + "/datasets", params=params)
        )

    def evaluation_dataset(self, space_id: str, dataset_id: str) -> Dataset:
        from .service.evaluation_models import Dataset

        return Dataset.model_validate(
            self.request("GET", self._evaluation_path(space_id) + f"/datasets/{UUID(dataset_id)}")
        )

    def create_evaluation_dataset(self, space_id: str, dataset: DatasetInput | dict) -> Dataset:
        from .service.evaluation_models import Dataset, DatasetInput

        command = (
            dataset if isinstance(dataset, DatasetInput) else DatasetInput.model_validate(dataset)
        )
        return Dataset.model_validate(
            self.request(
                "POST",
                self._evaluation_path(space_id) + "/datasets",
                body=command.model_dump(mode="json"),
            )
        )

    def remove_evaluation_dataset(self, space_id: str, dataset_id: str) -> None:
        self.request("DELETE", self._evaluation_path(space_id) + f"/datasets/{UUID(dataset_id)}")

    def start_evaluation(
        self, space_id: str, dataset_id: str, *, idempotency_key: str | None = None, **options
    ) -> EvaluationRun:
        from .service.evaluation_models import EvaluationInput, EvaluationRun

        command = EvaluationInput(dataset_id=UUID(dataset_id), **options)
        return EvaluationRun.model_validate(
            self.request(
                "POST",
                self._evaluation_path(space_id) + "/runs",
                body=command.model_dump(mode="json"),
                key=idempotency_key or str(uuid4()),
            )
        )

    def evaluation_runs(self, space_id: str) -> list[EvaluationRun]:
        return self.evaluation_run_page(space_id).items

    def evaluation_run_page(
        self, space_id: str, *, cursor: str | None = None, limit: int = 100
    ) -> Page[EvaluationRun]:
        from .service.evaluation_models import EvaluationRun

        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return Page[EvaluationRun].model_validate(
            self.request("GET", self._evaluation_path(space_id) + "/runs", params=params)
        )

    def evaluation_run(self, space_id: str, run_id: str, *, compact: bool = False) -> EvaluationRun:
        from .service.evaluation_models import EvaluationRun

        return EvaluationRun.model_validate(
            self.request(
                "GET",
                self._evaluation_path(space_id) + f"/runs/{UUID(run_id)}",
                params={"compact": str(compact).lower()},
            )
        )

    def evaluation_results(
        self, space_id: str, run_id: str, *, cursor: int = 0, limit: int = 50
    ) -> EvaluationPage:
        from .service.evaluation_models import EvaluationPage

        return EvaluationPage.model_validate(
            self.request(
                "GET",
                self._evaluation_path(space_id) + f"/runs/{UUID(run_id)}/results",
                params={"cursor": cursor, "limit": limit},
            )
        )

    def cancel_evaluation(self, space_id: str, run_id: str) -> EvaluationRun:
        from .service.evaluation_models import EvaluationRun

        return EvaluationRun.model_validate(
            self.request("POST", self._evaluation_path(space_id) + f"/runs/{UUID(run_id)}/cancel")
        )

    def assess_evaluation(
        self, space_id: str, run_id: str, position: int, assessment: AssessmentInput | dict
    ) -> EvaluationResult:
        from .service.evaluation_models import AssessmentInput, EvaluationResult

        command = (
            assessment
            if isinstance(assessment, AssessmentInput)
            else AssessmentInput.model_validate(assessment)
        )
        return EvaluationResult.model_validate(
            self.request(
                "PUT",
                self._evaluation_path(space_id)
                + f"/runs/{UUID(run_id)}/results/{position}/assessment",
                body=command.model_dump(mode="json"),
            )
        )

    def compare_evaluations(self, space_id: str, baseline_id: str, candidate_id: str) -> Comparison:
        from .service.evaluation_models import Comparison

        return Comparison.model_validate(
            self.request(
                "POST",
                self._evaluation_path(space_id) + "/compare",
                body={
                    "baseline_id": str(UUID(baseline_id)),
                    "candidate_id": str(UUID(candidate_id)),
                },
            )
        )

    def export_evaluation(
        self, space_id: str, run_id: str, *, format: Literal["json", "csv"] = "json"
    ) -> bytes:
        return self.request(
            "GET",
            self._evaluation_path(space_id) + f"/runs/{UUID(run_id)}/export",
            params={"format": format},
            binary=True,
        )

    def knowledge(
        self,
        space_ids: list[str] | None = None,
        *,
        all_accessible=False,
        subject: str | None = None,
        limit=250,
        include_historical=False,
    ) -> Knowledge:
        """Build the current authorized wiki, graph and non-destructive review findings."""
        from .service.knowledge import Knowledge, KnowledgeInput

        command = KnowledgeInput(
            space_ids=space_ids or [],
            all_accessible=all_accessible,
            subject=subject,
            limit=limit,
            include_historical=include_historical,
        )
        return Knowledge.model_validate(
            self.request("POST", "/v1/knowledge", body=command.model_dump(mode="json"))
        )

    def save(
        self, space_id: str, content: str, *, idempotency_key: str | None = None, **fields
    ) -> Receipt:
        command = MemoryInput(content=content, **fields)
        return Receipt.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{space_id}/memories",
                body=command.model_dump(mode="json"),
                key=idempotency_key or str(uuid4()),
            )
        )

    def fetch(
        self, memory_id: str, *, revision_id: str | None = None, review: bool = False
    ) -> Memory:
        params = {"review": str(review).lower()}
        if revision_id:
            params["revision_id"] = revision_id
        return Memory.model_validate(
            self.request("GET", f"/v1/memories/{memory_id}", params=params)
        )

    def search(self, query: str, space_ids: list[str] | None = None, **options) -> Recall:
        command = RecallInput(query=query, space_ids=space_ids or [], **options)
        return Recall.model_validate(
            self.request("POST", "/v1/recall", body=command.model_dump(mode="json"))
        )

    def source(self, source_revision_id: str, *, review: bool = False) -> Source:
        revision = str(UUID(source_revision_id))
        return Source.model_validate(
            self.request("GET", f"/v1/sources/{revision}", params={"review": str(review).lower()})
        )

    def resolve_alias(self, space_id: str, legacy_id: str, *, review: bool = False) -> Memory:
        return Memory.model_validate(
            self.request(
                "GET",
                f"/v1/spaces/{UUID(space_id)}/resolve",
                params={"legacy_id": legacy_id, "review": str(review).lower()},
            )
        )

    def attachment(
        self, source_revision_id: str, attachment_id: str, *, review: bool = False
    ) -> bytes:
        revision, attachment = str(UUID(source_revision_id)), str(UUID(attachment_id))
        return self.request(
            "GET",
            f"/v1/sources/{revision}/attachments/{attachment}",
            params={"review": str(review).lower()},
            binary=True,
        )

    def context(
        self, query: str, space_ids: list[str] | None = None, *, token_budget: int = 2048, **options
    ) -> ContextPack:
        command = ContextInput(
            query=query, space_ids=space_ids or [], token_budget=token_budget, **options
        )
        return ContextPack.model_validate(
            self.request("POST", "/v1/context", body=command.model_dump(mode="json"))
        )

    def revise(
        self,
        memory_id: str,
        content: str,
        *,
        expected_version: int,
        reason: str,
        idempotency_key: str | None = None,
        **fields,
    ) -> Receipt:
        command = RevisionInput(
            content=content, expected_version=expected_version, reason=reason, **fields
        )
        return Receipt.model_validate(
            self.request(
                "POST",
                f"/v1/memories/{memory_id}/revisions",
                body=command.model_dump(mode="json", exclude_unset=True),
                key=idempotency_key or str(uuid4()),
            )
        )

    def forget(
        self, memory_id: str, *, expected_version: int, idempotency_key: str | None = None
    ) -> Receipt:
        return Receipt.model_validate(
            self.request(
                "DELETE",
                f"/v1/memories/{memory_id}",
                params={"expected_version": expected_version},
                key=idempotency_key or str(uuid4()),
            )
        )

    def review(
        self,
        memory_id: str,
        *,
        expected_version: int,
        state: Literal["ordinary", "quarantined"],
        reason: str,
    ) -> dict:
        return self.request(
            "PUT",
            f"/v1/memories/{memory_id}/review",
            body={"expected_version": expected_version, "state": state, "reason": reason},
        )

    def operation(self, operation_id: str) -> dict:
        return self.request("GET", f"/v1/operations/{operation_id}")

    def activity(
        self, space_id: str, *, memory_id: str | None = None, limit: int = 100
    ) -> list[AuditEvent]:
        params = {"limit": limit}
        if memory_id:
            params["memory_id"] = str(UUID(memory_id))
        page = self.request("GET", f"/v1/spaces/{UUID(space_id)}/activity", params=params)
        return [AuditEvent.model_validate(item) for item in page["items"]]

    def wait(self, operation_id: str, *, timeout: float = 30) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            operation = self.operation(operation_id)
            if operation["state"] in ("ready", "failed", "cancelled"):
                return operation
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Operation {operation_id} is still {operation['state']}")
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))

    def export_obsidian(
        self, space_ids: list[str] | None = None, *, review: bool = False, all_accessible=False
    ) -> bytes:
        from .service.models import ExportInput

        command = ExportInput(
            space_ids=space_ids or [], review=review, all_accessible=all_accessible
        )
        return self.request(
            "POST", "/v1/exports", body=command.model_dump(mode="json"), binary=True
        )

    def sync_obsidian(
        self,
        vault_path: str,
        space_ids: list[str] | None = None,
        *,
        review: bool = False,
        dry_run: bool = False,
        all_accessible=False,
    ) -> dict:
        from .vault_client import sync_bundle

        return sync_bundle(
            self.export_obsidian(space_ids, review=review, all_accessible=all_accessible),
            vault_path,
            dry_run=dry_run,
        )
