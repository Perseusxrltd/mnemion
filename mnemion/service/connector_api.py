"""Connector transport registration; authentication is shared with the core API."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query

from . import connector_contracts as c
from .connector_models import (
    BatchInput,
    BindingInput,
    ConnectorInput,
    FinishInput,
    ResolveInput,
    RunInput,
    ScopeInput,
    SuspensionInput,
    SyncRequestInput,
    SyncReportInput,
)
from .contracts import Page
from .db import Identity


def install_routes(app, authenticated, service):
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.get("/v1/health/sources", tags=["Operations"], response_model=c.SourceHealth)
    def source_health(identity: Auth):
        return service.health(identity)

    @app.get("/v1/connectors", tags=["Connectors"], response_model=Page[c.Connector])
    def connectors(identity: Auth):
        return service.list(identity)

    @app.post("/v1/connectors", tags=["Connectors"], response_model=c.Connector, status_code=201)
    def create_connector(command: ConnectorInput, identity: Auth):
        return service.create(identity, command)

    @app.delete("/v1/connectors/{connector_id}", tags=["Connectors"], response_model=c.Connector)
    def disable_connector(connector_id: UUID, identity: Auth):
        return service.disable(identity, connector_id)

    @app.post(
        "/v1/connectors/{connector_id}/enable", tags=["Connectors"], response_model=c.Connector
    )
    def enable_connector(connector_id: UUID, identity: Auth):
        return service.enable(identity, connector_id)

    @app.get("/v1/connectors/{connector_id}/sync", tags=["Connectors"], response_model=c.SyncStatus)
    def connector_sync_status(connector_id: UUID, identity: Auth):
        return service.sync_status(identity, connector_id)

    @app.post(
        "/v1/connectors/{connector_id}/sync",
        tags=["Connectors"],
        response_model=c.SyncStatus,
        status_code=202,
    )
    def request_connector_sync(connector_id: UUID, command: SyncRequestInput, identity: Auth):
        return service.request_sync(identity, connector_id, command)

    @app.post(
        "/v1/connectors/{connector_id}/sync/report",
        tags=["Connectors"],
        response_model=c.SyncStatus,
    )
    def report_connector_sync(connector_id: UUID, command: SyncReportInput, identity: Auth):
        return service.report_sync(identity, connector_id, command)

    @app.get(
        "/v1/connectors/{connector_id}/bindings",
        tags=["Connectors"],
        response_model=Page[c.Binding],
    )
    def bindings(connector_id: UUID, identity: Auth):
        return service.bindings(identity, connector_id)

    @app.put(
        "/v1/connectors/{connector_id}/bindings",
        tags=["Connectors"],
        response_model=c.BindingResult,
    )
    def bind(connector_id: UUID, command: BindingInput, identity: Auth):
        return service.binding(identity, connector_id, command)

    @app.delete(
        "/v1/connectors/{connector_id}/bindings",
        tags=["Connectors"],
        response_model=c.BindingResult,
    )
    def unbind(connector_id: UUID, command: BindingInput, identity: Auth):
        return service.binding(identity, connector_id, command, remove=True)

    @app.get(
        "/v1/connectors/{connector_id}/scopes", tags=["Connectors"], response_model=c.ScopePage
    )
    def scopes(
        connector_id: UUID,
        identity: Auth,
        after: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    ):
        return service.scopes(identity, connector_id, after=after, limit=limit)

    @app.post(
        "/v1/connectors/{connector_id}/scopes", tags=["Connectors"], response_model=c.ConnectorScope
    )
    def refresh_scope(connector_id: UUID, command: ScopeInput, identity: Auth):
        return service.refresh_scope(identity, connector_id, command)

    @app.post(
        "/v1/connector-scopes/{space_id}/suspend",
        tags=["Connectors"],
        response_model=c.SuspendedScope,
    )
    def suspend_scope(space_id: UUID, command: SuspensionInput, identity: Auth):
        return service.suspend(identity, space_id, command.reason)

    @app.post(
        "/v1/connector-scopes/{space_id}/resume",
        tags=["Connectors"],
        response_model=c.SuspendedScope,
    )
    def resume_scope(space_id: UUID, identity: Auth):
        return service.resume(identity, space_id)

    @app.post(
        "/v1/connector-scopes/{space_id}/runs", tags=["Connectors"], response_model=c.ConnectorRun
    )
    def begin_run(space_id: UUID, command: RunInput, identity: Auth):
        return service.begin(identity, space_id, command)

    @app.post(
        "/v1/connector-scopes/{space_id}/runs/{run_id}/pages",
        tags=["Connectors"],
        response_model=c.PageResult,
    )
    def commit_page(space_id: UUID, run_id: UUID, command: BatchInput, identity: Auth):
        return service.page(identity, space_id, run_id, command)

    @app.post(
        "/v1/connector-scopes/{space_id}/runs/{run_id}/finish",
        tags=["Connectors"],
        response_model=c.SyncResult,
    )
    def finish_run(space_id: UUID, run_id: UUID, command: FinishInput, identity: Auth):
        return service.finish(identity, space_id, run_id, command)

    @app.get(
        "/v1/spaces/{space_id}/connector-proposals",
        tags=["Connectors"],
        response_model=Page[c.Proposal],
    )
    def proposals(space_id: UUID, identity: Auth):
        return service.proposals(identity, space_id)

    @app.post(
        "/v1/memories/{memory_id}/connector-proposal",
        tags=["Connectors"],
        response_model=c.ProposalResult,
    )
    def resolve_proposal(memory_id: UUID, command: ResolveInput, identity: Auth):
        return service.resolve(identity, memory_id, command)
