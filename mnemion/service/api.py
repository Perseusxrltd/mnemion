"""Versioned HTTP boundary for applications, Studio, SDKs, and MCP."""

import asyncio
import logging
import os
import re
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
import anyio
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from psycopg_pool import PoolTimeout
from starlette.routing import Route

from mnemion.version import __version__

from . import contracts as c
from .db import Database, Identity
from .embeddings import Embedder
from .model_registry import ModelRegistry
from .embedding_api import attach_embeddings
from .errors import ServiceError
from .export import ExportService
from .identity import IdentityService
from .knowledge import Knowledge, KnowledgeInput, KnowledgeService
from .memory import MemoryService
from .models import (
    SCOPE_SELECTION_MESSAGE,
    BlockInput,
    ContextInput,
    ExportInput,
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RecallInput,
    RevisionInput,
    ReviewInput,
    SpaceInput,
)
from .retrieval import RetrievalService
from .telemetry import Telemetry
from .insights import Insights, InsightsService, RuntimeInsights, runtime_insights
from .evaluation_api import attach_evaluations
from .evaluation_runner import EvaluationRunner
from .librarian import LibrarianService
from .librarian_api import attach_librarian
from .librarian_provider import LibrarianRegistry
from .librarian_runner import LibrarianRunner
from .agent_api import attach_agents
from .oauth import OAuthSettings, OAuthVerifier, unauthorized
from .oauth_api import attach_oauth
from .hosted_oauth import HostedOAuth, HostedOAuthSettings
from .company_identity import CompanyIdentity
from .company_sign_in import CompanySignIn, attach_company_sign_in
from .sign_in_api import BrowserPolicy
from .hosted_oauth_api import (
    PROTOCOL_PATHS,
    attach_hosted_connections,
    attach_hosted_oauth,
    oauth_error,
)
from .sign_in_api import attach_sign_in
from .recovery_directory import attach_recovery_directory
from .vault import VaultService
from .vault_api import attach_vault
from .vault_crypto import VaultSettings
from ..journal.config import Configuration as WritebackConfiguration
from .writeback import WritebackService
from .writeback_api import attach_writeback

logger = logging.getLogger(__name__)


class BodyLimitMiddleware:
    """Bound both Content-Length and chunked request bodies before JSON parsing."""

    def __init__(self, app, limit: int = 2_000_000, timeout: float = 30):
        self.app = app
        self.limit = limit
        self.timeout = timeout

    async def reject(self, scope, receive, send, status, code, message):
        if scope.get("path") in PROTOCOL_PATHS:
            return await oauth_error("invalid_request", message, status)(scope, receive, send)
        response = JSONResponse(
            {
                "error": {"code": code, "message": message},
                "request_id": scope.get("state", {}).get("request_id", str(uuid4())),
            },
            status_code=status,
        )
        return await response(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = (
            min(self.limit, 32768) if scope.get("path", "").startswith("/oauth/") else self.limit
        )
        lengths = [
            value for name, value in scope.get("headers", []) if name.lower() == b"content-length"
        ]
        if lengths:
            if len(lengths) != 1 or len(lengths[0]) > 10 or not lengths[0].isdigit():
                return await self.reject(
                    scope, receive, send, 400, "invalid_content_length", "Invalid request length."
                )
            if int(lengths[0]) > limit:
                return await self.reject(
                    scope,
                    receive,
                    send,
                    413,
                    "body_too_large",
                    "Request body exceeds its size limit.",
                )
        # A size cap alone does not stop slow clients holding every connection.
        # A single bounded buffer also avoids per-chunk memory overhead.
        body = bytearray()
        try:
            async with asyncio.timeout(self.timeout):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > limit:
                        return await self.reject(
                            scope,
                            receive,
                            send,
                            413,
                            "body_too_large",
                            "Request body exceeds its size limit.",
                        )
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await self.reject(
                scope, receive, send, 408, "body_timeout", "Request body did not complete in time."
            )
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(
    database: Database | None = None,
    embedder: Embedder | None = None,
    *,
    registry: ModelRegistry | None = None,
    librarian_registry: LibrarianRegistry | None = None,
    mcp_enabled: bool | None = None,
    studio_enabled: bool = True,
    oauth: OAuthVerifier | None = None,
    hosted_oauth_settings: HostedOAuthSettings | None = None,
    public_url: str | None = None,
    company_identity: CompanyIdentity | None = None,
    vault_settings: VaultSettings | None = None,
    writeback_configuration: WritebackConfiguration | None = None,
) -> FastAPI:
    builtin_settings = hosted_oauth_settings or HostedOAuthSettings.from_environment()
    if builtin_settings and oauth is not None:
        raise ValueError("Choose the built-in or external authorization server")
    if oauth is None and builtin_settings is None:
        settings = OAuthSettings.from_environment()
        oauth = OAuthVerifier(settings) if settings else None
    oauth_settings = builtin_settings or (oauth.settings if oauth else None)
    gateway_enabled = (
        mcp_enabled
        if mcp_enabled is not None
        else os.environ.get("MNEMION_MCP_ENABLED", "1") == "1"
    )
    owned = database is None
    if database is None:
        dsn = os.environ.get("MNEMION_DATABASE_URL")
        if not dsn:
            raise RuntimeError(
                "Set MNEMION_DATABASE_URL to the non-owner application database login"
            )
        database = Database(dsn, max_size=int(os.environ.get("MNEMION_DB_POOL_SIZE", "10")))
    company_identity = company_identity or CompanyIdentity.from_environment()
    hosted_oauth = (
        HostedOAuth(database, builtin_settings, company_policies=company_identity.policies)
        if builtin_settings
        else None
    )
    company_origin = BrowserPolicy(
        oauth_settings.resource
        if oauth_settings
        else public_url or os.environ.get("MNEMION_PUBLIC_URL")
    ).public_origin
    company_sign_in = CompanySignIn(database, company_identity, company_origin)
    registry = registry or (
        ModelRegistry(embedder) if embedder is not None else ModelRegistry.from_environment()
    )
    embedder = registry.default
    identity_service = IdentityService(database)
    memory = MemoryService(database, embedder.generation)
    writeback = WritebackService(database, writeback_configuration)
    memory.writeback = writeback
    telemetry = Telemetry(database)
    retrieval = RetrievalService(database, embedder, telemetry, registry=registry)
    insights = InsightsService(database, embedder)
    evaluations = EvaluationRunner(database, retrieval)
    librarian_registry = librarian_registry or LibrarianRegistry.from_environment()
    librarian = LibrarianService(database, librarian_registry, memory)
    librarian_runner = LibrarianRunner(
        librarian,
        can_start=registry.memory_budget.can_start_background if registry.memory_budget else None,
    )
    exports = ExportService(database)
    vault = VaultService(database, vault_settings or VaultSettings.from_environment())
    mcp_app = None

    @asynccontextmanager
    async def lifespan(app):
        if owned:
            database.open()
        telemetry.start()
        writeback.start()
        if os.environ.get("MNEMION_EVALUATIONS_DISABLED") != "1":
            evaluations.start()
        if os.environ.get("MNEMION_LIBRARIAN_DISABLED") != "1":
            librarian_runner.start()
        try:
            registry.start_idle_cleanup()
            async with AsyncExitStack() as stack:
                from .sign_in_maintenance import maintain_history
                from mnemion.product_telemetry.activity import application_delivery

                product_delivery = await stack.enter_async_context(
                    application_delivery(
                        can_start=registry.memory_budget.can_start_background
                        if registry.memory_budget
                        else None,
                    )
                )

                maintenance = await stack.enter_async_context(anyio.create_task_group())
                stack.callback(maintenance.cancel_scope.cancel)
                maintenance.start_soon(maintain_history, database)
                if mcp_app is not None:
                    await stack.enter_async_context(mcp_app.router.lifespan_context(mcp_app))
                from .supervision import process_ready

                stack.enter_context(process_ready("api", registry.generation_ids))
                try:
                    yield
                finally:
                    # Fence new optional work before other service owners stop.
                    if product_delivery is not None:
                        product_delivery.stop()
        finally:
            writeback.stop()
            librarian_runner.stop()
            evaluations.stop()
            telemetry.stop()
            librarian_registry.close()
            registry.close()
            if owned:
                database.close()

    app = FastAPI(
        title="Mnemion Memory Service",
        version=__version__,
        docs_url="/docs" if os.environ.get("MNEMION_API_DOCS", "1") == "1" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if os.environ.get("MNEMION_API_DOCS", "1") == "1" else None,
        lifespan=lifespan,
        responses={
            status: {"model": c.ErrorResponse, "description": description}
            for status, description in {
                400: "Bad Request",
                401: "Unauthorized",
                403: "Forbidden",
                404: "Not Found",
                408: "Request Timeout",
                409: "Conflict",
                413: "Content Too Large",
                422: "Unprocessable Content",
                429: "Too Many Requests",
                503: "Service Unavailable",
            }.items()
        },
        description="Shared, scoped memory and evidence for apps, teams, and assistants. Saves acknowledge canonical durability; operations report semantic indexing readiness.",
    )
    app.add_middleware(BodyLimitMiddleware)
    origins = [
        value.strip()
        for value in os.environ.get("MNEMION_CORS_ORIGINS", "").split(",")
        if value.strip()
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
            expose_headers=["X-Request-ID", "X-Mnemion-Idempotency"],
        )
    app.state.database = database
    app.state.oauth_settings = oauth_settings
    app.state.embedder = embedder
    app.state.model_registry = registry
    app.state.telemetry = telemetry
    app.state.evaluations = evaluations
    app.state.librarian = librarian
    app.state.writeback = writeback
    app.state.librarian_runner = librarian_runner
    app.state.vault = vault

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        from .request_replay import HEADER, request_replay
        from .studio_policy import PRODUCT_TELEMETRY_POLICY_PATH

        if request.method == "GET" and request.url.path == PRODUCT_TELEMETRY_POLICY_PATH:
            # The fixed public policy read has no operational identity or
            # request correlation. Deployment access/trace logs need their own
            # exclusion; do not weaken authenticated workspace audit records.
            return await call_next(request)
        request.state.request_id = str(uuid4())
        with request_replay() as replay:
            response = await call_next(request)
        if replay.value is not None:
            response.headers[HEADER] = replay.value
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        if request.url.path in PROTOCOL_PATHS:
            response = oauth_error(
                "temporarily_unavailable" if exc.status in {429, 503} else "invalid_request",
                exc.message,
                exc.status,
            )
            if exc.status == 429:
                response.headers["Retry-After"] = "60"
            return response
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else {}
        if oauth_settings and (exc.status == 401 or exc.code == "insufficient_scope"):
            headers["WWW-Authenticate"] = oauth_settings.challenge(exc.code)
        if exc.status in {429, 503}:
            headers["Retry-After"] = "1" if exc.code == "inference_busy" else "2"
        return JSONResponse(
            {
                "error": {"code": exc.code, "message": exc.message},
                "request_id": request.state.request_id,
            },
            status_code=exc.status,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        from .connector_models import CONNECTOR_PROVIDER_MESSAGE
        from .validation import route_names
        from ..validation_fields import safe_fields

        # Object keys can contain credentials or source text, just like values.
        errors = exc.errors()
        fields = safe_fields(errors, route_names(request.scope.get("route")))
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": SCOPE_SELECTION_MESSAGE
                    if any(error["type"] == "memory_scope" for error in errors)
                    else CONNECTOR_PROVIDER_MESSAGE
                    if any(error["type"] == "connector_provider" for error in errors)
                    else "Check the request fields against the API schema.",
                    "fields": fields,
                },
                "request_id": request.state.request_id,
            },
            status_code=422,
        )

    async def unavailable(request: Request, exc):
        logger.warning(
            "Database request %s failed (%s)", request.state.request_id, type(exc).__name__
        )
        if request.url.path in PROTOCOL_PATHS:
            return oauth_error(
                "temporarily_unavailable", "Authorization is temporarily unavailable.", 503
            )
        return JSONResponse(
            {
                "error": {
                    "code": "database_unavailable",
                    "message": "The database is temporarily unavailable; retry with the same idempotency key.",
                },
                "request_id": request.state.request_id,
            },
            status_code=503,
            headers={"Retry-After": "2"},
        )

    app.add_exception_handler(PoolTimeout, unavailable)
    app.add_exception_handler(psycopg.OperationalError, unavailable)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        logger.error("Request %s failed (%s)", request.state.request_id, type(exc).__name__)
        if request.url.path in PROTOCOL_PATHS:
            return oauth_error("server_error", "Authorization could not be completed.", 500)
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "The request could not be completed.",
                },
                "request_id": request.state.request_id,
            },
            status_code=500,
        )

    bearer = HTTPBearer(auto_error=False)

    async def authenticated(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> Identity:
        if (
            len(request.headers.getlist("authorization")) != 1
            or not credentials
            or credentials.scheme.lower() != "bearer"
            or not 1 <= len(credentials.credentials) <= 4096
            or any(not 33 <= ord(c) <= 126 for c in credentials.credentials)
        ):
            raise unauthorized()
        token = credentials.credentials
        if hosted_oauth and token.startswith("mnmo_"):
            return await hosted_oauth.authenticate(token)
        # Reserve the local key prefix. Never send a Mnemion API key to an issuer.
        if token.startswith("mnm_") or oauth is None:
            return await anyio.to_thread.run_sync(
                lambda: database.authenticate(token, company_policies=company_identity.policies)
            )
        claims = await oauth.verify(token)
        return await anyio.to_thread.run_sync(database.authenticate_oauth, claims)

    Auth = Annotated[Identity, Depends(authenticated)]

    async def optional_authenticated(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> Identity | None:
        if not request.headers.getlist("authorization"):
            return None
        return await authenticated(request, credentials)

    OptionalAuth = Annotated[Identity | None, Depends(optional_authenticated)]
    Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]

    from .connector_api import install_routes
    from .connectors import ConnectorService

    install_routes(app, authenticated, ConnectorService(memory))

    from .capture_api import install_routes as install_capture_routes
    from .capture_custody import CaptureCustody

    install_capture_routes(app, authenticated, CaptureCustody(memory))
    attach_evaluations(app, database, embedder, authenticated, registry=registry)
    attach_embeddings(app, database, registry, authenticated)
    attach_librarian(app, librarian, authenticated)
    attach_writeback(app, writeback, authenticated)
    from .buffer_import_api import attach_buffer_import

    attach_buffer_import(app, memory, authenticated)
    from .journal_recovery_api import attach_journal_recovery

    attach_journal_recovery(app, memory, authenticated)
    from .journal_upload_api import attach_journal_uploads

    attach_journal_uploads(app, memory, authenticated)
    attach_agents(app, authenticated)
    attach_recovery_directory(app, database, authenticated)
    attach_vault(app, vault, authenticated)
    attach_oauth(app, database, authenticated, oauth.settings if oauth else None)
    attach_hosted_connections(
        app,
        database,
        authenticated,
        oauth_settings,
        personal=hosted_oauth is not None,
        mcp_enabled=gateway_enabled,
    )
    if hosted_oauth:
        attach_hosted_oauth(app, hosted_oauth, authenticated, company_sign_in)
    attach_sign_in(
        app,
        database,
        authenticated,
        public_url=oauth_settings.resource if oauth_settings else public_url,
        company_policies=company_identity.policies,
    )
    attach_company_sign_in(app, company_sign_in, authenticated)

    if oauth_settings:

        @app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
        @app.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
        def oauth_metadata():
            return oauth_settings.metadata()

    @app.get("/health/live", tags=["Operations"], response_model=c.LiveStatus)
    def live():
        return {
            "status": "alive",
            "api_version": "v1",
            "service_version": __version__,
            "connector_partial_inventory": True,
            "durable_capture": "v1",
            "capture_policy_versions": "v1",
            "capture_retention": "v1",
        }

    @app.get("/health/ready", tags=["Operations"], response_model=c.ReadyStatus)
    def ready(response: Response, identity: OptionalAuth):
        with database.pool.connection() as conn:
            registered = conn.execute(
                "SELECT id FROM mnemion.embedding_generations WHERE id=%s",
                (embedder.generation.id,),
            ).fetchone()
        if not registered:
            raise ServiceError(
                503,
                "generation_not_registered",
                "Run the administration setup for this model generation.",
            )
        instance = os.environ.get("MNEMION_SUPERVISED_INSTANCE", "")
        if re.fullmatch(r"mnemion-[a-f0-9]{24}", instance):
            response.headers["X-Mnemion-Instance"] = instance
            response.headers["X-Mnemion-Process"] = str(os.getpid())
        attention = []
        if identity is not None:
            from .source_health import source_health

            with database.transaction(identity) as conn:
                attention = source_health(conn)["attention"]
        return {
            "status": "ready",
            "generation_id": embedder.generation.id,
            "service_version": __version__,
            "source_health_checked": identity is not None,
            "attention": attention,
        }

    @app.get("/v1/me", tags=["Identity"], response_model=c.IdentityInfo)
    def me(identity: Auth):
        return identity_service.me(identity)

    @app.get("/v1/spaces", tags=["Spaces"], response_model=c.Page[c.Space])
    def spaces(identity: Auth):
        return {"items": identity_service.spaces(identity)}

    @app.post("/v1/spaces", status_code=201, tags=["Spaces"], response_model=c.Space)
    def create_space(command: SpaceInput, identity: Auth):
        return identity_service.create_space(identity, command)

    @app.get("/v1/spaces/{space_id}", tags=["Spaces"], response_model=c.Space)
    def get_space(space_id: UUID, identity: Auth):
        return identity_service.space(identity, space_id)

    @app.get("/v1/principals", tags=["Identity"], response_model=c.Page[c.Principal])
    def principals(identity: Auth):
        return {"items": identity_service.principals(identity)}

    @app.post("/v1/principals", status_code=201, tags=["Identity"], response_model=c.Principal)
    def create_principal(command: PrincipalInput, identity: Auth):
        return identity_service.create_principal(identity, command)

    @app.post(
        "/v1/principals/{principal_id}/disable",
        tags=["Identity"],
        response_model=c.DisabledPrincipal,
    )
    def disable_principal(principal_id: UUID, identity: Auth):
        return identity_service.disable_principal(identity, principal_id)

    @app.post(
        "/v1/principals/{principal_id}/keys",
        status_code=201,
        tags=["Identity"],
        response_model=c.CreatedKey,
    )
    def create_key(principal_id: UUID, command: KeyInput, identity: Auth):
        return identity_service.create_key(identity, principal_id, command)

    @app.get("/v1/keys", tags=["Identity"], response_model=c.Page[c.ApiKey])
    def keys(identity: Auth):
        return {"items": identity_service.keys(identity)}

    @app.delete("/v1/keys/{key_id}", tags=["Identity"], response_model=c.RevokedKey)
    def revoke_key(key_id: UUID, identity: Auth):
        return identity_service.revoke_key(identity, key_id)

    @app.get("/v1/spaces/{space_id}/grants", tags=["Spaces"], response_model=c.Page[c.Grant])
    def grants(space_id: UUID, identity: Auth):
        return {"items": identity_service.grants(identity, space_id)}

    @app.put(
        "/v1/spaces/{space_id}/grants/{principal_id}", tags=["Spaces"], response_model=c.GrantResult
    )
    def grant(space_id: UUID, principal_id: UUID, command: GrantInput, identity: Auth):
        return identity_service.grant(identity, space_id, principal_id, command)

    @app.delete(
        "/v1/spaces/{space_id}/grants/{principal_id}",
        tags=["Spaces"],
        response_model=c.RevokedGrant,
    )
    def revoke_grant(space_id: UUID, principal_id: UUID, identity: Auth):
        return identity_service.revoke_grant(identity, space_id, principal_id)

    @app.post(
        "/v1/spaces/{space_id}/memories", status_code=202, tags=["Memory"], response_model=c.Receipt
    )
    def save(space_id: UUID, command: MemoryInput, identity: Auth, idempotency_key: Key):
        return memory.save(identity, space_id, command, idempotency_key)

    @app.get("/v1/spaces/{space_id}/memories", tags=["Memory"], response_model=c.MemoryPage)
    def list_memories(
        space_id: UUID,
        identity: Auth,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=1000),
        review: bool = False,
    ):
        return memory.list(identity, space_id, limit=limit, cursor=cursor, review=review)

    @app.get("/v1/spaces/{space_id}/resolve", tags=["Memory"], response_model=c.Memory)
    def resolve_alias(
        space_id: UUID,
        identity: Auth,
        legacy_id: str = Query(min_length=1, max_length=1024),
        review: bool = False,
    ):
        return memory.resolve_alias(identity, space_id, legacy_id, review=review)

    @app.get("/v1/memories/{memory_id}", tags=["Memory"], response_model=c.Memory)
    def fetch(
        memory_id: UUID, identity: Auth, revision_id: UUID | None = None, review: bool = False
    ):
        return memory.fetch(identity, memory_id, revision=revision_id, review=review)

    @app.get("/v1/memories/{memory_id}/revisions", tags=["Memory"], response_model=c.Page[c.Memory])
    def history(memory_id: UUID, identity: Auth, review: bool = False):
        return {"items": memory.history(identity, memory_id, review=review)}

    @app.post(
        "/v1/memories/{memory_id}/revisions",
        status_code=202,
        tags=["Memory"],
        response_model=c.Receipt,
    )
    def revise(memory_id: UUID, command: RevisionInput, identity: Auth, idempotency_key: Key):
        return memory.revise(identity, memory_id, command, idempotency_key)

    @app.put("/v1/memories/{memory_id}/review", tags=["Memory"], response_model=c.ReviewResult)
    def review(memory_id: UUID, command: ReviewInput, identity: Auth):
        return memory.review(identity, memory_id, command)

    @app.delete(
        "/v1/memories/{memory_id}",
        status_code=202,
        tags=["Memory"],
        response_model=c.Receipt,
        summary="Forget a memory; inspect capture_forget before deleting an entire captured fragment",
    )
    def forget(
        memory_id: UUID, identity: Auth, idempotency_key: Key, expected_version: int = Query(ge=1)
    ):
        """Withdraw a memory with reviewer authority or eligible authorship.

        Contributors may withdraw their own ordinary, unverified memory only
        when every revision belongs to them. Otherwise returns requires_reviewer.
        Authorization and expected_version are checked at the write boundary;
        can_forget on memory details is an observation, not a reusable grant.
        Read capture_forget on current memory details and explain its scope to
        the user before confirmation. A captured fragment deletion includes its
        raw evidence, conversation projections and older revisions, and may
        include adjacent messages. Later deliveries of that fragment remain
        forgotten; this is not semantic deletion across producer generations.
        """
        return memory.forget(
            identity, memory_id, expected_version=expected_version, key=idempotency_key
        )

    @app.get("/v1/sources/{source_revision_id}", tags=["Evidence"], response_model=c.Source)
    def source(source_revision_id: UUID, identity: Auth, review: bool = False):
        return memory.source(identity, source_revision_id, review=review)

    @app.get(
        "/v1/sources/{source_revision_id}/attachments/{attachment_id}",
        tags=["Evidence"],
        response_class=Response,
    )
    def attachment(
        source_revision_id: UUID, attachment_id: UUID, identity: Auth, review: bool = False
    ):
        from urllib.parse import quote

        result = memory.attachment(identity, source_revision_id, attachment_id, review=review)
        return Response(
            result["content"],
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''"
                + quote(result["name"], safe=""),
                "X-Content-SHA256": result["content_hash"],
            },
        )

    @app.get("/v1/operations/{operation_id}", tags=["Operations"], response_model=c.Operation)
    def operation(operation_id: UUID, identity: Auth):
        return memory.operation(identity, operation_id)

    @app.get(
        "/v1/spaces/{space_id}/operations", tags=["Operations"], response_model=c.Page[c.Operation]
    )
    def list_operations(
        space_id: UUID,
        identity: Auth,
        state: c.OperationState | None = None,
        limit: int = Query(default=100, ge=1, le=100),
    ):
        return memory.operations(identity, space_id, state=state, limit=limit)

    @app.post(
        "/v1/operations/{operation_id}/retry",
        status_code=202,
        tags=["Operations"],
        response_model=c.RetryResult,
    )
    def retry_operation(operation_id: UUID, identity: Auth):
        return memory.retry_operation(identity, operation_id)

    @app.post("/v1/recall", tags=["Retrieval"], response_model=c.Recall)
    def recall(command: RecallInput, identity: Auth, request: Request):
        return {**retrieval.recall(identity, command), "request_id": request.state.request_id}

    @app.post("/v1/context", tags=["Retrieval"], response_model=c.ContextPack)
    def context(command: ContextInput, identity: Auth, request: Request):
        return {**retrieval.context(identity, command), "request_id": request.state.request_id}

    @app.post("/v1/knowledge", tags=["Knowledge"], response_model=Knowledge)
    def knowledge(command: KnowledgeInput, identity: Auth):
        return KnowledgeService(database).build(identity, command)

    @app.get(
        "/v1/spaces/{space_id}/blocks", tags=["Core context"], response_model=c.Page[c.CoreBlock]
    )
    def blocks(space_id: UUID, identity: Auth):
        return {"items": memory.blocks(identity, space_id)}

    @app.put(
        "/v1/spaces/{space_id}/blocks/{key}", tags=["Core context"], response_model=c.BlockResult
    )
    def put_block(space_id: UUID, key: str, command: BlockInput, identity: Auth):
        return memory.put_block(identity, space_id, key, command)

    @app.get("/v1/spaces/{space_id}/status", tags=["Operations"], response_model=c.SpaceStatus)
    def space_status(space_id: UUID, identity: Auth):
        return memory.status(identity, space_id)

    @app.get("/v1/spaces/{space_id}/insights", tags=["Insights"], response_model=Insights)
    def space_insights(
        space_id: UUID,
        identity: Auth,
        hours: int = Query(default=24, ge=1, le=744),
        origin: str = Query(default="all", pattern="^(all|interactive|evaluation|background)$"),
    ):
        return insights.read(identity, space_id, hours=hours, origin=origin)

    @app.get("/v1/insights/runtime", tags=["Insights"], response_model=RuntimeInsights)
    def runtime_statistics(identity: Auth):
        return runtime_insights(database, identity, embedder, telemetry, registry=registry)

    @app.get(
        "/v1/spaces/{space_id}/activity", tags=["Operations"], response_model=c.Page[c.AuditEvent]
    )
    def activity(
        space_id: UUID,
        identity: Auth,
        limit: int = Query(default=100, ge=1, le=100),
        memory_id: UUID | None = None,
    ):
        return memory.activity(identity, space_id, limit=limit, memory=memory_id)

    @app.post(
        "/v1/exports",
        tags=["Obsidian"],
        response_class=Response,
        responses={
            200: {
                "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}
            }
        },
    )
    def export(command: ExportInput, identity: Auth):
        return Response(
            exports.export(identity, command),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="mnemion-obsidian.zip"'},
        )

    if gateway_enabled:
        from .mcp import create_mcp

        gateway = create_mcp(
            "http://mnemion.internal",
            api_app=app,
            public_url=oauth_settings.resource
            if oauth_settings
            else public_url or os.environ.get("MNEMION_PUBLIC_URL"),
        )
        mcp_app = gateway.streamable_http_app(stateless_http=True, json_response=True)
        # Preserve the exact /mcp URL without Mount's trailing-slash redirect.
        # Internal tool requests use ASGI, so they cannot exhaust the listening
        # server's concurrency slots while waiting for their own loopback HTTP.
        app.router.routes.append(Route("/mcp", mcp_app, methods=["GET", "POST", "DELETE"]))
        app.state.mcp = gateway

    from .studio import resolve_studio

    studio, _ = resolve_studio() if studio_enabled else (None, "disabled")
    if studio is not None:
        from .studio_policy import (
            PRODUCT_TELEMETRY_POLICY_PATH,
            content_security_policy,
            product_telemetry_page,
            product_telemetry_policy,
        )

        studio_policy = content_security_policy()
        app.mount("/assets", StaticFiles(directory=studio / "assets"), name="studio-assets")
        app.add_api_route(
            PRODUCT_TELEMETRY_POLICY_PATH,
            product_telemetry_policy,
            methods=["GET"],
            include_in_schema=False,
        )

        @app.get("/", include_in_schema=False)
        @app.get("/help", include_in_schema=False)
        @app.get("/privacy", include_in_schema=False)
        @app.get("/oauth/consent", include_in_schema=False)
        @app.get("/workspace", include_in_schema=False)
        @app.get("/workspace/{route:path}", include_in_schema=False)
        def studio_page(route: str = ""):
            return Response(
                product_telemetry_page((studio / "index.html").read_text(encoding="utf-8")),
                media_type="text/html",
                headers={
                    "Content-Security-Policy": studio_policy,
                    "Referrer-Policy": "no-referrer",
                },
            )

        @app.get("/icon.png", include_in_schema=False)
        @app.get("/icon.ico", include_in_schema=False)
        @app.get("/mnemion.svg", include_in_schema=False)
        @app.get("/mnemion-symbol.svg", include_in_schema=False)
        @app.get("/icon-16.png", include_in_schema=False)
        @app.get("/icon-32.png", include_in_schema=False)
        @app.get("/icon-180.png", include_in_schema=False)
        def studio_icon(request: Request):
            path = studio / request.url.path.removeprefix("/")
            if not path.is_file():
                return Response(status_code=404)
            return FileResponse(path)

    return app
