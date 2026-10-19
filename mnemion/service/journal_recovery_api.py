"""Private app and agent access to the same native journal reconstruction."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from .db import Identity
from .journal_recovery import JournalRecoveryService
from .journal_recovery_models import (
    JournalRecoveryApply,
    JournalRecoveryInput,
    JournalRecoveryPreview,
    JournalRecoveryReceipt,
)


def attach_journal_recovery(app, memory, authenticated):
    service = JournalRecoveryService(memory)
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.post(
        "/v1/spaces/{space_id}/journal-recovery/preview",
        tags=["Memory recovery"],
        response_model=JournalRecoveryPreview,
    )
    def journal_recovery_preview(space_id: UUID, command: JournalRecoveryInput, identity: Auth):
        """Review a complete native catalog and journal in a private destination."""
        return service.preview(identity, space_id, command)

    @app.post(
        "/v1/spaces/{space_id}/journal-recovery",
        tags=["Memory recovery"],
        response_model=JournalRecoveryReceipt,
    )
    def journal_recovery_apply(
        space_id: UUID,
        command: JournalRecoveryApply,
        identity: Auth,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=120),
    ):
        """Restore reviewed current content with stable IDs and retained denials."""
        return service.apply(identity, space_id, command, idempotency_key)
