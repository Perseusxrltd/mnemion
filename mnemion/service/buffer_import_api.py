"""The same reviewed legacy-buffer import for Studio and authorized agents."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from .buffer_import import BufferImportService
from .buffer_import_models import (
    BufferImported,
    BufferImportInput,
    BufferPreview,
    BufferPreviewInput,
)
from .db import Identity


def attach_buffer_import(app, memory, authenticated):
    service = BufferImportService(memory)
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.post(
        "/v1/spaces/{space_id}/buffer-import/preview",
        tags=["Memory recovery"],
        response_model=BufferPreview,
    )
    def buffer_preview(space_id: UUID, command: BufferPreviewInput, identity: Auth):
        """Review complete legacy JSONL plus reconciled withdrawals in a private native space."""
        return service.preview(identity, space_id, command)

    @app.post(
        "/v1/spaces/{space_id}/buffer-import",
        tags=["Memory recovery"],
        response_model=BufferImported,
    )
    def buffer_import(
        space_id: UUID,
        command: BufferImportInput,
        identity: Auth,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=120),
    ):
        """Import the exact reviewed batch. Historical writers do not gain access; Git delivery is not inferred."""
        return service.apply(identity, space_id, command, idempotency_key)
