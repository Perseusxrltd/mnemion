"""The same journal policy and delivery controls for Studio, SDKs and agents."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends

from .db import Identity
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
