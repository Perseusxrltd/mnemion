"""The same journal policy and delivery controls for Studio, SDKs and agents."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from .db import Identity
from .backfill_models import BackfillControlInput, BackfillStartInput, BackfillStatus
from .writeback_models import WritebackPolicyInput, WritebackPushInput, WritebackStatus


def attach_writeback(app, service, authenticated):
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.get(
        "/v1/spaces/{space_id}/writeback", tags=["Git journal"], response_model=WritebackStatus
    )
    def journal_status(space_id: UUID, identity: Auth):
        return service.status(identity, space_id)

    @app.put(
        "/v1/spaces/{space_id}/writeback", tags=["Git journal"], response_model=WritebackStatus
    )
    def journal_policy(space_id: UUID, command: WritebackPolicyInput, identity: Auth):
        """Approve capture and Git publication for future native changes; Git history retains published text."""
        return service.configure(identity, space_id, command)

    @app.post(
        "/v1/spaces/{space_id}/writeback/push", tags=["Git journal"], response_model=WritebackStatus
    )
    def journal_push(space_id: UUID, command: WritebackPushInput, identity: Auth):
        service.push(identity, space_id, expected_version=command.expected_version)
        return service.status(identity, space_id)

    @app.post(
        "/v1/spaces/{space_id}/writeback/organize",
        tags=["Git journal"],
        response_model=WritebackStatus,
    )
    def journal_organize(space_id: UUID, command: WritebackPushInput, identity: Auth):
        """File current journal memories into Markdown and move old records intact to the archive."""
        service.organize(identity, space_id, expected_version=command.expected_version)
        return service.status(identity, space_id)

    @app.get(
        "/v1/spaces/{space_id}/writeback/backfill",
        tags=["Git journal"],
        response_model=BackfillStatus,
    )
    def journal_backfill_status(space_id: UUID, identity: Auth):
        """Preview unjournaled current native revisions and inspect the resumable backfill."""
        return service.backfill_status(identity, space_id)

    @app.post(
        "/v1/spaces/{space_id}/writeback/backfill",
        tags=["Git journal"],
        response_model=BackfillStatus,
    )
    def journal_backfill_start(
        space_id: UUID,
        command: BackfillStartInput,
        identity: Auth,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ):
        """Approve a background scan of older native memories. A queued event is not a Git delivery receipt."""
        return service.start_backfill(identity, space_id, command, idempotency_key)

    @app.post(
        "/v1/spaces/{space_id}/writeback/backfill/control",
        tags=["Git journal"],
        response_model=BackfillStatus,
    )
    def journal_backfill_control(space_id: UUID, command: BackfillControlInput, identity: Auth):
        """Pause or cancel further scanning. Captured entries retain their separate publication policy."""
        return service.control_backfill(identity, space_id, command)
