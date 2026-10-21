"""Native agent/app custody transport; no producer credentials or file fetching."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query

from . import capture_models as c
from .db import Identity


def install_routes(app, authenticated, service):
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.get(
        "/v1/connectors/{connector_id}/capture-sources/{source_id}",
        tags=["Connectors"],
        response_model=c.CaptureSource,
    )
    def source_status(connector_id: UUID, source_id: UUID, identity: Auth):
        return service.source_status(identity, connector_id, source_id)

    @app.put(
        "/v1/connectors/{connector_id}/capture-sources/{source_id}",
        tags=["Connectors"],
        response_model=c.CaptureSource,
    )
    def configure_source(
        connector_id: UUID, source_id: UUID, command: c.CaptureSourceInput, identity: Auth
    ):
        return service.source(identity, connector_id, source_id, command)

    @app.delete(
        "/v1/connectors/{connector_id}/capture-sources/{source_id}",
        tags=["Connectors"],
        response_model=c.CaptureSource,
    )
    def revoke_source(connector_id: UUID, source_id: UUID, identity: Auth):
        return service.revoke_source(identity, connector_id, source_id)

    @app.put(
        "/v1/capture-sources/{source_id}/grants/{grant_id}",
        tags=["Connectors"],
        response_model=c.CaptureGrant,
    )
    def authorize_device(
        source_id: UUID, grant_id: UUID, command: c.CaptureGrantInput, identity: Auth
    ):
        return service.grant(identity, source_id, grant_id, command)

    @app.get("/v1/capture-grants/{grant_id}", tags=["Connectors"], response_model=c.CaptureGrant)
    def grant_status(grant_id: UUID, identity: Auth):
        return service.status(identity, grant_id)

    @app.get(
        "/v1/capture-grants/{grant_id}/index-progress",
        tags=["Connectors"],
        response_model=c.CaptureIndexPage,
    )
    def index_progress(
        grant_id: UUID,
        identity: Auth,
        after: Annotated[str | None, Query(pattern=r"^[a-f0-9]{64}$")] = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
    ):
        return service.index_progress(identity, grant_id, after=after, limit=limit)

    @app.delete("/v1/capture-grants/{grant_id}", tags=["Connectors"], response_model=c.CaptureGrant)
    def revoke_device(grant_id: UUID, identity: Auth):
        return service.status(identity, grant_id, revoke=True)

    @app.post(
        "/v1/capture-grants/{grant_id}/pages",
        tags=["Connectors"],
        response_model=c.CapturePageReceipt,
    )
    def accept_page(grant_id: UUID, command: c.CapturePageInput, identity: Auth):
        return service.page(identity, grant_id, command)

    @app.get(
        "/v1/capture-grants/{grant_id}/pages/{page_id}",
        tags=["Connectors"],
        response_model=c.CapturePageReceipt,
    )
    def page_receipt(grant_id: UUID, page_id: UUID, identity: Auth):
        return service.page(identity, grant_id, page_id=page_id)

    @app.get(
        "/v1/capture-grants/{grant_id}/fences",
        tags=["Connectors"],
        response_model=c.CaptureFencePage,
    )
    def forgotten_lineages(
        grant_id: UUID,
        identity: Auth,
        after: Annotated[str | None, Query(pattern=r"^[a-f0-9]{64}$")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ):
        return service.fences(identity, grant_id, after=after, limit=limit)
