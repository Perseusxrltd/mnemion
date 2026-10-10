"""Authenticated discovery of the installed, reviewed operation contract."""

from typing import Annotated

from fastapi import Depends, Path, Query

from ..agent_control import ControlError, catalog, describe
from .db import Identity
from .errors import ServiceError


def attach_agents(app, authenticated):
    Auth = Annotated[Identity, Depends(authenticated)]

    @app.get("/v1/agent/operations", tags=["Agents"], response_model=dict)
    def operations(
        identity: Auth,
        group: Annotated[str | None, Query(max_length=200)] = None,
        query: Annotated[str | None, Query(max_length=200)] = None,
        offset: Annotated[int, Query(ge=0, le=10000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        """Discover capabilities; each actual operation still enforces current permissions."""
        return catalog(group=group, query=query, offset=offset, limit=limit)

    @app.get("/v1/agent/operations/{operation_name}", tags=["Agents"], response_model=dict)
    def operation(
        operation_name: Annotated[str, Path(min_length=1, max_length=100)], identity: Auth
    ):
        """Get one operation's validation schema, read/write effect and retry contract."""
        try:
            return describe(operation_name)
        except ControlError as error:
            raise ServiceError(error.status, error.code, str(error)) from None
