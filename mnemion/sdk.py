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
    from .service.journal_recovery_models import (
        JournalRecoveryInput,
        JournalRecoveryApply,
        JournalRecoveryPreview,
        JournalRecoveryReceipt,
    )
    from .service.buffer_import_models import (
        BufferPreviewInput,
        BufferImportInput,
        BufferPreview,
        BufferImported,
    )
    from .service.keepass_models import (
        KeepassPreviewInput,
        KeepassImportInput,
        KeepassExportInput,
        KeepassPreview,
        KeepassImported,
        KeepassExported,
    )
    from .service.writeback_models import WritebackPolicyInput, WritebackStatus
    from .service.backfill_models import BackfillControlInput, BackfillStartInput, BackfillStatus
    from .service.connector_contracts import SourceHealth, SyncStatus
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


def _ranking_compatibility(body: dict, options: dict) -> dict:
    """A new nested default must not become an unsolicited old-server option."""
    policy = options.get("ranking_policy", {})
    specified = policy if isinstance(policy, dict) else getattr(policy, "model_fields_set", set())
    if "ranking_policy" in body and "recent_relevance_ratio" not in specified:
        body["ranking_policy"].pop("recent_relevance_ratio", None)
    return body


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
    def vault_status(self) -> dict:
        return self.request("GET", "/v1/vault/status")

    def vault_list(self, *, offset: int = 0, limit: int = 100) -> dict:
        return self.request("GET", "/v1/vault/entries", params={"offset": offset, "limit": limit})

    def vault_get(self, entry_id: str) -> dict:
        """Explicit sensitive read. Do not log the returned value or save it as memory."""
        return self.request("GET", f"/v1/vault/entries/{UUID(entry_id)}")

    def vault_put(self, entry_id: str, *, name: str, value: str, expected_version: int) -> dict:
        return self.request(
            "PUT",
            f"/v1/vault/entries/{UUID(entry_id)}",
            body={"name": name, "value": value, "expected_version": expected_version},
        )

    def vault_grants(self, entry_id: str) -> dict:
        return self.request("GET", f"/v1/vault/entries/{UUID(entry_id)}/grants")

    def vault_grant(
        self,
        entry_id: str,
        *,
        subject_kind: str,
        subject_id: str,
        expected_access_version: int,
        read: bool = False,
        write: bool = False,
        remove: bool = False,
    ) -> dict:
        return self.request(
            "PUT",
            f"/v1/vault/entries/{UUID(entry_id)}/grants",
            body={
                "subject_kind": subject_kind,
                "subject_id": str(UUID(subject_id)),
                "expected_access_version": expected_access_version,
                "read": read,
                "write": write,
                "remove": remove,
            },
        )

    def vault_delete(self, entry_id: str, *, expected_version: int) -> dict:
        return self.request(
            "POST",
            f"/v1/vault/entries/{UUID(entry_id)}/delete",
            body={"expected_version": expected_version},
        )

    def vault_export(self, entry_ids: list[str], *, recovery_key: str) -> dict:
        return self.request(
            "POST",
            "/v1/vault/export",
            body={
                "entry_ids": [str(UUID(value)) for value in entry_ids],
                "recovery_key": recovery_key,
            },
        )

    def vault_import(self, archive: dict, *, recovery_key: str) -> dict:
        return self.request(
            "POST", "/v1/vault/import", body={"archive": archive, "recovery_key": recovery_key}
        )

    def vault_audit(self, *, offset: int = 0, limit: int = 100) -> dict:
        return self.request("GET", "/v1/vault/audit", params={"offset": offset, "limit": limit})

    @staticmethod
    def _keepass_body(command):
        body = command.model_dump(mode="json")
        for name in ("file", "password", "key_file"):
            value = getattr(command, name, None)
            if value is not None:
                body[name] = value.get_secret_value()
        return body

    def vault_keepass_preview(self, command: KeepassPreviewInput) -> KeepassPreview:
        from .service.keepass_models import KeepassPreview

        return KeepassPreview.model_validate(
            self.request("POST", "/v1/vault/keepass/preview", body=self._keepass_body(command))
        )

    def vault_keepass_import(self, command: KeepassImportInput) -> KeepassImported:
        from .service.keepass_models import KeepassImported

        return KeepassImported.model_validate(
            self.request("POST", "/v1/vault/keepass/import", body=self._keepass_body(command))
        )

    def vault_keepass_export(self, command: KeepassExportInput) -> KeepassExported:
        from .service.keepass_models import KeepassExported

        return KeepassExported.model_validate(
            self.request("POST", "/v1/vault/keepass/export", body=self._keepass_body(command))
        )

    def company_configuration(self, workspace_id: str) -> dict:
        return self.request(
            "GET",
            "/v1/sign-in/company/configuration",
            params={"workspace_id": str(UUID(workspace_id))},
        )

    def company_links(self) -> dict:
        return self.request("GET", "/v1/sign-in/company/links")

    def link_company_identity(self, principal_id: str, provider_id: str, subject: str) -> dict:
        from .service.company_sign_in import CompanyLinkInput

        command = CompanyLinkInput(
            principal_id=principal_id, provider_id=provider_id, subject=subject
        )
        return self.request(
            "POST", "/v1/sign-in/company/links", body=command.model_dump(mode="json")
        )

    def revoke_company_identity(self, link_id: str) -> dict:
        return self.request("DELETE", f"/v1/sign-in/company/links/{UUID(link_id)}")

    def source_health(self) -> SourceHealth:
        from .service.connector_contracts import SourceHealth

        return SourceHealth.model_validate(self.request("GET", "/v1/health/sources"))

    def connector_sync_status(self, connector_id: str) -> SyncStatus:
        from .service.connector_contracts import SyncStatus

        return SyncStatus.model_validate(
            self.request("GET", f"/v1/connectors/{UUID(connector_id)}/sync")
        )

    def request_connector_sync(self, connector_id: str, *, expected_generation: int) -> SyncStatus:
        from .service.connector_contracts import SyncStatus
        from .service.connector_models import SyncRequestInput

        command = SyncRequestInput(expected_generation=expected_generation)
        return SyncStatus.model_validate(
            self.request(
                "POST",
                f"/v1/connectors/{UUID(connector_id)}/sync",
                body=command.model_dump(mode="json"),
            )
        )

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

    def journal_status(self, space_id: str) -> WritebackStatus:
        from .service.writeback_models import WritebackStatus

        return WritebackStatus.model_validate(
            self.request("GET", f"/v1/spaces/{UUID(space_id)}/writeback")
        )

    def configure_journal(self, space_id: str, command: WritebackPolicyInput) -> WritebackStatus:
        from .service.writeback_models import WritebackPolicyInput, WritebackStatus

        command = WritebackPolicyInput.model_validate(command)
        return WritebackStatus.model_validate(
            self.request(
                "PUT",
                f"/v1/spaces/{UUID(space_id)}/writeback",
                body=command.model_dump(mode="json", exclude_none=True),
            )
        )

    def push_journal(self, space_id: str, *, expected_version: int) -> WritebackStatus:
        from .service.writeback_models import WritebackPushInput, WritebackStatus

        command = WritebackPushInput(expected_version=expected_version)
        return WritebackStatus.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/writeback/push",
                body=command.model_dump(mode="json"),
            )
        )

    def organize_journal(self, space_id: str, *, expected_version: int) -> WritebackStatus:
        from .service.writeback_models import WritebackPushInput, WritebackStatus

        command = WritebackPushInput(expected_version=expected_version)
        return WritebackStatus.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/writeback/organize",
                body=command.model_dump(mode="json"),
            )
        )

    def journal_backfill_status(self, space_id: str) -> BackfillStatus:
        from .service.backfill_models import BackfillStatus

        return BackfillStatus.model_validate(
            self.request("GET", f"/v1/spaces/{UUID(space_id)}/writeback/backfill")
        )

    def start_journal_backfill(
        self, space_id: str, command: BackfillStartInput, *, idempotency_key: str | None = None
    ) -> BackfillStatus:
        from .service.backfill_models import BackfillStartInput, BackfillStatus

        command = BackfillStartInput.model_validate(command)
        return BackfillStatus.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/writeback/backfill",
                body=command.model_dump(mode="json", exclude_none=True),
                key=idempotency_key or str(uuid4()),
            )
        )

    def control_journal_backfill(
        self, space_id: str, command: BackfillControlInput
    ) -> BackfillStatus:
        from .service.backfill_models import BackfillControlInput, BackfillStatus

        command = BackfillControlInput.model_validate(command)
        return BackfillStatus.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/writeback/backfill/control",
                body=command.model_dump(mode="json"),
            )
        )

    def preview_journal_recovery(
        self, space_id: str, command: JournalRecoveryInput
    ) -> JournalRecoveryPreview:
        from .service.journal_recovery_models import JournalRecoveryInput, JournalRecoveryPreview

        command = JournalRecoveryInput.model_validate(command)
        body = command.model_dump(mode="json")
        body["catalog"] = command.catalog.get_secret_value()
        body["files"] = [
            {"path": file.path, "text": file.text.get_secret_value()} for file in command.files
        ]
        return JournalRecoveryPreview.model_validate(
            self.request("POST", f"/v1/spaces/{UUID(space_id)}/journal-recovery/preview", body=body)
        )

    def restore_journal(
        self, space_id: str, command: JournalRecoveryApply, *, idempotency_key: str | None = None
    ) -> JournalRecoveryReceipt:
        from .service.journal_recovery_models import JournalRecoveryApply, JournalRecoveryReceipt

        command = JournalRecoveryApply.model_validate(command)
        body = command.model_dump(mode="json")
        body["catalog"] = command.catalog.get_secret_value()
        body["files"] = [
            {"path": file.path, "text": file.text.get_secret_value()} for file in command.files
        ]
        return JournalRecoveryReceipt.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/journal-recovery",
                body=body,
                key=idempotency_key or str(uuid4()),
            )
        )

    def preview_legacy_buffer(self, space_id: str, command: BufferPreviewInput) -> BufferPreview:
        from .service.buffer_import_models import BufferPreviewInput, BufferPreview

        command = BufferPreviewInput.model_validate(command)
        body = command.model_dump(mode="json")
        body["jsonl"] = command.jsonl.get_secret_value()
        return BufferPreview.model_validate(
            self.request("POST", f"/v1/spaces/{UUID(space_id)}/buffer-import/preview", body=body)
        )

    def import_legacy_buffer(
        self, space_id: str, command: BufferImportInput, *, idempotency_key: str | None = None
    ) -> BufferImported:
        from .service.buffer_import_models import BufferImportInput, BufferImported

        command = BufferImportInput.model_validate(command)
        body = command.model_dump(mode="json")
        body["jsonl"] = command.jsonl.get_secret_value()
        return BufferImported.model_validate(
            self.request(
                "POST",
                f"/v1/spaces/{UUID(space_id)}/buffer-import",
                body=body,
                key=idempotency_key or str(uuid4()),
            )
        )

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
        self,
        base_url: str,
        api_key: str | None,
        *,
        timeout: float = 30,
        retries: int = 2,
        transport=None,
    ):
        if not 0 <= retries <= 5:
            raise ValueError("Retries must be between 0 and 5")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": "Bearer " + api_key} if api_key is not None else {},
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
                if response.headers.get("ngrok-error-code") == "ERR_NGROK_3200":
                    raise MnemionError(
                        response.status_code,
                        "tunnel_offline",
                        "The workspace tunnel is offline. Restart its connection through the host's operator controls; changing the workspace key will not reconnect the host.",
                        None,
                    )
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
                body=_ranking_compatibility(
                    command.model_dump(
                        mode="json",
                        exclude={
                            field
                            for field in (
                                "keyword_fallback",
                                "ranking_policy",
                                "max_per_source",
                                "sort",
                            )
                            if field not in options
                        },
                    ),
                    options,
                ),
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
            self.request(
                "POST",
                "/v1/recall",
                body=_ranking_compatibility(
                    command.model_dump(
                        mode="json",
                        exclude=(
                            {"on_inference_busy"} if command.on_inference_busy == "error" else set()
                        )
                        | ({"ranking_policy"} if "ranking_policy" not in options else set())
                        | ({"keyword_fallback"} if "keyword_fallback" not in options else set())
                        | ({"max_per_source"} if "max_per_source" not in options else set()),
                    ),
                    options,
                ),
            )
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
            self.request(
                "POST",
                "/v1/context",
                body=_ranking_compatibility(
                    command.model_dump(
                        mode="json",
                        exclude=(
                            {"on_inference_busy"} if command.on_inference_busy == "error" else set()
                        )
                        | ({"ranking_policy"} if "ranking_policy" not in options else set())
                        | ({"keyword_fallback"} if "keyword_fallback" not in options else set())
                        | ({"max_per_source"} if "max_per_source" not in options else set()),
                    ),
                    options,
                ),
            )
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
