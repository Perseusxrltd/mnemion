"""Private resumable journal recovery for the app and authenticated agents."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Path, Query

from .db import Identity
from .journal_upload import JournalUploadService
from .journal_upload_models import (
    JournalUploadAdvance,
    JournalUploadChunk,
    JournalUploadChunkReceipt,
    JournalUploadDecisions,
    JournalUploadFiles,
    JournalUploadInput,
    JournalUploadList,
    JournalUploadStatus,
)


def attach_journal_uploads(app, memory, authenticated):
    service = JournalUploadService(memory)
    Auth = Annotated[Identity, Depends(authenticated)]
    base = "/v1/spaces/{space_id}/journal-recovery/uploads"
    tags = ["Memory recovery"]

    @app.post(base, tags=tags, response_model=JournalUploadStatus)
    def journal_upload_begin(
        space_id: UUID,
        command: JournalUploadInput,
        identity: Auth,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=120),
    ):
        """Declare a complete inventory without reading journal files into memory."""
        return service.begin(identity, space_id, command, idempotency_key)

    @app.get(base, tags=tags, response_model=JournalUploadList)
    def journal_upload_list(space_id: UUID, identity: Auth):
        """List this administrator's retained uploads in this private space."""
        return service.list(identity, space_id)

    @app.get(base + "/{upload_id}", tags=tags, response_model=JournalUploadStatus)
    def journal_upload_status(space_id: UUID, upload_id: UUID, identity: Auth):
        """Inspect durable progress after interruption or a lost response."""
        return service.get(identity, space_id, upload_id)

    @app.get(base + "/{upload_id}/files", tags=tags, response_model=JournalUploadFiles)
    def journal_upload_files(
        space_id: UUID,
        upload_id: UUID,
        identity: Auth,
        cursor: int = Query(default=0, ge=0, le=8192),
    ):
        """Read bounded file receipts to verify and resume original bytes."""
        return service.files(identity, space_id, upload_id, cursor)

    @app.put(
        base + "/{upload_id}/files/{file_index}",
        tags=tags,
        response_model=JournalUploadChunkReceipt,
    )
    def journal_upload_chunk(
        space_id: UUID,
        upload_id: UUID,
        command: JournalUploadChunk,
        identity: Auth,
        file_index: int = Path(ge=0, lt=8192),
    ):
        """Append one binary chunk; exact retries never duplicate events."""
        return service.chunk(identity, space_id, upload_id, file_index, command)

    @app.get(base + "/{upload_id}/decisions", tags=tags, response_model=JournalUploadDecisions)
    def journal_upload_decisions(
        space_id: UUID,
        upload_id: UUID,
        identity: Auth,
        cursor: int = Query(default=0, ge=0, le=100000),
    ):
        """Page through the reviewed decisions without returning memory bodies."""
        return service.decisions(identity, space_id, upload_id, cursor)

    @app.post(base + "/{upload_id}/advance", tags=tags, response_model=JournalUploadStatus)
    def journal_upload_advance(
        space_id: UUID, upload_id: UUID, command: JournalUploadAdvance, identity: Auth
    ):
        """Seal, review, approve, restore, or cancel one durable bounded step."""
        return service.advance(identity, space_id, upload_id, command)
