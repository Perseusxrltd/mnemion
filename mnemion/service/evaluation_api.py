"""Authenticated evaluation routes share the same space boundary as memory."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Header, Query, Response

from .contracts import Page
from .db import Identity
from .evaluation_models import (
    AssessmentInput,
    Comparison,
    Dataset,
    DatasetInput,
    EvaluationInput,
    EvaluationPage,
    EvaluationResult,
    EvaluationRun,
    RunComparison,
)
from .evaluations import EvaluationService


def attach_evaluations(app, database, embedder, authenticated):
    service = EvaluationService(database, embedder)
    Auth = Annotated[Identity, Depends(authenticated)]
    base = "/v1/spaces/{space_id}/evaluations"

    @app.get(base + "/datasets", tags=["Evaluations"], response_model=Page[Dataset])
    def datasets(
        space_id: UUID,
        identity: Auth,
        cursor: str | None = Query(default=None, max_length=512),
        limit: int = Query(default=200, ge=1, le=200),
    ):
        return service.datasets(identity, space_id, cursor=cursor, limit=limit)

    @app.post(base + "/datasets", tags=["Evaluations"], status_code=201, response_model=Dataset)
    def create_dataset(space_id: UUID, command: DatasetInput, identity: Auth):
        return service.create_dataset(identity, space_id, command)

    @app.get(base + "/datasets/{dataset_id}", tags=["Evaluations"], response_model=Dataset)
    def dataset(space_id: UUID, dataset_id: UUID, identity: Auth):
        return service.dataset(identity, space_id, dataset_id)

    @app.delete(base + "/datasets/{dataset_id}", tags=["Evaluations"], status_code=204)
    def remove_dataset(space_id: UUID, dataset_id: UUID, identity: Auth):
        service.remove_dataset(identity, space_id, dataset_id)
        return Response(status_code=204)

    @app.get(base + "/runs", tags=["Evaluations"], response_model=Page[EvaluationRun])
    def runs(
        space_id: UUID,
        identity: Auth,
        cursor: str | None = Query(default=None, max_length=512),
        limit: int = Query(default=100, ge=1, le=100),
    ):
        return service.runs(identity, space_id, cursor=cursor, limit=limit)

    @app.post(base + "/runs", tags=["Evaluations"], status_code=202, response_model=EvaluationRun)
    def create_run(
        space_id: UUID,
        command: EvaluationInput,
        identity: Auth,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ):
        return service.create_run(identity, space_id, command, idempotency_key)

    @app.get(base + "/runs/{run_id}", tags=["Evaluations"], response_model=EvaluationRun)
    def run(space_id: UUID, run_id: UUID, identity: Auth, compact: bool = False):
        return service.run(identity, space_id, run_id, compact=compact)

    @app.get(base + "/runs/{run_id}/results", tags=["Evaluations"], response_model=EvaluationPage)
    def results(
        space_id: UUID,
        run_id: UUID,
        identity: Auth,
        cursor: int = Query(default=0, ge=0, le=3000),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        return service.results(identity, space_id, run_id, cursor=cursor, limit=limit)

    @app.post(base + "/runs/{run_id}/cancel", tags=["Evaluations"], response_model=EvaluationRun)
    def cancel(space_id: UUID, run_id: UUID, identity: Auth):
        return service.cancel(identity, space_id, run_id)

    @app.put(
        base + "/runs/{run_id}/results/{position}/assessment",
        tags=["Evaluations"],
        response_model=EvaluationResult,
    )
    def assess(
        space_id: UUID, run_id: UUID, position: int, command: AssessmentInput, identity: Auth
    ):
        return service.assess(identity, space_id, run_id, position, command)

    @app.post(base + "/compare", tags=["Evaluations"], response_model=Comparison)
    def compare(space_id: UUID, command: RunComparison, identity: Auth):
        return service.compare(identity, space_id, command.baseline_id, command.candidate_id)

    @app.get(base + "/runs/{run_id}/export", tags=["Evaluations"], response_class=Response)
    def export(
        space_id: UUID, run_id: UUID, identity: Auth, format: Literal["json", "csv"] = "json"
    ):
        return Response(
            service.export(identity, space_id, run_id, format=format),
            media_type="application/json" if format == "json" else "text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="mnemion-evaluation-{run_id}.{format}"'
            },
        )
