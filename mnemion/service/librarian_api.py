"""Authenticated librarian controls share ordinary space and review boundaries."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Query

from .contracts import Page
from .db import Identity
from .librarian_models import (
    LibrarianChoice,
    LibrarianCoverage,
    LibrarianDecision,
    LibrarianDecisionReceipt,
    LibrarianProposal,
    LibrarianRun,
    LibrarianRunInput,
    LibrarianRunItem,
    LibrarianSettings,
    LibrarianSettingsInput,
    ProposalState,
)


def attach_librarian(app, service, authenticated, *, on_run_queued=None):
    Auth = Annotated[Identity, Depends(authenticated)]
    base = "/v1/spaces/{space_id}/librarian"

    @app.get(base + "/models", tags=["Librarian"], response_model=Page[LibrarianChoice])
    def models(space_id: UUID, identity: Auth):
        return service.choices(identity, space_id)

    @app.get(base, tags=["Librarian"], response_model=LibrarianSettings)
    def settings(space_id: UUID, identity: Auth):
        return service.settings(identity, space_id)

    @app.get(base + "/coverage", tags=["Librarian"], response_model=LibrarianCoverage)
    def coverage(space_id: UUID, identity: Auth):
        return service.coverage(identity, space_id)

    @app.put(base, tags=["Librarian"], response_model=LibrarianSettings)
    def configure(space_id: UUID, command: LibrarianSettingsInput, identity: Auth):
        return service.configure(identity, space_id, command)

    @app.get(base + "/runs", tags=["Librarian"], response_model=Page[LibrarianRun])
    def runs(
        space_id: UUID,
        identity: Auth,
        cursor: str | None = Query(default=None, max_length=512),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        return service.runs(identity, space_id, cursor=cursor, limit=limit)

    @app.post(base + "/runs", tags=["Librarian"], status_code=202, response_model=LibrarianRun)
    def create_run(
        space_id: UUID,
        command: LibrarianRunInput,
        identity: Auth,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ):
        run = service.create_run(identity, space_id, command, idempotency_key)
        # create_run returns only after its transaction commits. Wake is a
        # process-local hint; the queued row remains the source of truth.
        if on_run_queued is not None and run["state"] == "queued":
            on_run_queued()
        return run

    @app.get(base + "/runs/{run_id}", tags=["Librarian"], response_model=LibrarianRun)
    def run(space_id: UUID, run_id: UUID, identity: Auth):
        return service.run(identity, space_id, run_id)

    @app.get(
        base + "/runs/{run_id}/items", tags=["Librarian"], response_model=Page[LibrarianRunItem]
    )
    def run_items(space_id: UUID, run_id: UUID, identity: Auth):
        return service.run_items(identity, space_id, run_id)

    @app.post(base + "/runs/{run_id}/cancel", tags=["Librarian"], response_model=LibrarianRun)
    def cancel(space_id: UUID, run_id: UUID, identity: Auth):
        return service.cancel(identity, space_id, run_id)

    @app.get(base + "/proposals", tags=["Librarian"], response_model=Page[LibrarianProposal])
    def proposals(
        space_id: UUID,
        identity: Auth,
        state: ProposalState | None = None,
        cursor: str | None = Query(default=None, max_length=512),
        limit: int = Query(default=20, ge=1, le=50),
    ):
        return service.proposals(identity, space_id, state=state, cursor=cursor, limit=limit)

    @app.post(
        base + "/proposals/{proposal_id}/decision",
        tags=["Librarian"],
        response_model=LibrarianDecisionReceipt,
    )
    def decide(
        space_id: UUID,
        proposal_id: UUID,
        command: LibrarianDecision,
        identity: Auth,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ):
        return service.decide(identity, space_id, proposal_id, command, idempotency_key)
