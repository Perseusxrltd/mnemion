"""Space administrators select approved providers; secrets remain on the server."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Header

from .db import Identity
from .embedding_models import EmbeddingChoice, EmbeddingSettings, ReindexControl, ReindexInput
from .contracts import Page
from .reindex import ReindexService


def attach_embeddings(app, database, registry, authenticated):
    service = ReindexService(database, registry)
    Auth = Annotated[Identity, Depends(authenticated)]
    base = "/v1/spaces/{space_id}/embedding"

    @app.get(base + "/choices", tags=["Embedding models"], response_model=Page[EmbeddingChoice])
    def choices(space_id: UUID, identity: Auth):
        return service.choices(identity, space_id)

    @app.get(base, tags=["Embedding models"], response_model=EmbeddingSettings)
    def read(space_id: UUID, identity: Auth):
        return service.read(identity, space_id)

    @app.post(base + "/resume", tags=["Embedding models"], response_model=EmbeddingSettings)
    def resume_processing(space_id: UUID, command: ReindexControl, identity: Auth):
        return service.resume_processing(identity, space_id, command)

    @app.post(
        base + "/reindex",
        tags=["Embedding models"],
        status_code=202,
        response_model=EmbeddingSettings,
    )
    def start(
        space_id: UUID,
        command: ReindexInput,
        identity: Auth,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ):
        return service.start(identity, space_id, command, idempotency_key)

    @app.post(
        base + "/reindex/{run_id}/{action}",
        tags=["Embedding models"],
        response_model=EmbeddingSettings,
    )
    def control(
        space_id: UUID,
        run_id: UUID,
        action: Literal["pause", "resume", "retry", "cancel", "activate"],
        command: ReindexControl,
        identity: Auth,
    ):
        return service.control(
            identity,
            space_id,
            run_id,
            action,
            command.expected_version,
            approve_network_egress=command.approve_network_egress,
        )
