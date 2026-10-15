"""Company-provider setup for the owning OS account, never memory credentials."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import ssl
from typing import Literal
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from . import local_remote, local_state as state
from .service.company_identity import CompanyIdentity, CompanyProvider
from .service.errors import ServiceError
from .service.oauth import _json_object, https_url


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=100)
    issuer: str = Field(max_length=2048)
    authorization_url: str = Field(max_length=2048)
    token_url: str = Field(max_length=2048)
    jwks_url: str = Field(max_length=2048)
    client_id: str = Field(min_length=1, max_length=512)
    session_seconds: int = Field(default=28800, ge=900, le=86400)

    @model_validator(mode="after")
    def approved_values(self):
        CompanyProvider(workspace_id=UUID(int=0), **self.model_dump())
        return self


class SavedProvider(ProviderSettings):
    client_secret: SecretStr | None = None

    @model_validator(mode="after")
    def approved_values(self):
        CompanyProvider(
            workspace_id=UUID(int=0),
            **self.model_dump(exclude={"client_secret"}),
            client_secret=self.client_secret.get_secret_value() if self.client_secret else None,
        )
        return self


def ca_context(value: str | None):
    if value is None:
        return True
    if not value or len(value) > 8192 or "PRIVATE KEY" in value:
        raise ValueError("Use PEM certificates without a private key, up to 8 KiB")
    try:
        return ssl.create_default_context(cadata=value)
    except (ValueError, ssl.SSLError):
        raise ValueError("Use valid PEM certificates without a private key") from None


class CompanyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal[1] = 1
    workspace_id: UUID
    revision: UUID
    updated_at: str
    providers: list[SavedProvider] = Field(default_factory=list, max_length=32)
    ca_pem: str | None = Field(default=None, max_length=8192)

    @model_validator(mode="after")
    def directory(self):
        if len({item.id for item in self.providers}) != len(self.providers):
            raise ValueError("Company provider identifiers must be distinct")
        ca_context(self.ca_pem)
        return self


class CompanyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workspace_id: UUID
    expected_revision: str = Field(pattern=r"^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$")
    expected_remote_revision: str = Field(
        pattern=r"^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$"
    )


class CompanyChange(CompanyRequest):
    action: Literal["save", "remove", "reset"]
    provider: ProviderSettings | None = None
    provider_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,63}$")
    client_secret: SecretStr | None = None
    clear_client_secret: bool = False
    # Omitted retains the current trust roots; null returns to system trust.
    ca_pem: str | None = Field(default=None, max_length=8192)

    @model_validator(mode="after")
    def operation(self):
        if self.action == "save":
            if self.provider is None or self.provider_id is not None:
                raise ValueError("Choose the company provider to save")
            if self.client_secret is not None and self.clear_client_secret:
                raise ValueError("Choose replacement or removal of the client secret")
            if self.client_secret is not None:
                SavedProvider(**self.provider.model_dump(), client_secret=self.client_secret)
        elif (
            self.provider is not None
            or self.client_secret is not None
            or self.clear_client_secret
            or "ca_pem" in self.model_fields_set
            or (self.action == "remove") != (self.provider_id is not None)
        ):
            raise ValueError("Choose the provider to remove or reset damaged settings")
        if "ca_pem" in self.model_fields_set:
            ca_context(self.ca_pem)
        return self


class CompanyDiscovery(CompanyRequest):
    issuer: str = Field(max_length=2048)
    ca_pem: str | None = Field(default=None, max_length=8192)

    @field_validator("issuer")
    @classmethod
    def issuer_url(cls, value):
        return https_url(value)

    @field_validator("ca_pem")
    @classmethod
    def certificate(cls, value):
        ca_context(value)
        return value


def _record(root: Path, workspace_id: str):
    try:
        content = state.read_bytes(root / "company-access.json")
    except FileNotFoundError:
        return None, None, "not-configured"
    try:
        if len(content) > 65536:
            raise ValueError("Company provider settings exceed 64 KiB")
        json.loads(content, object_pairs_hook=_json_object)
        saved = CompanyRecord.model_validate_json(content)
        if str(saved.workspace_id) != workspace_id:
            raise ValueError("Different workspace")
        return saved, content, str(saved.revision)
    except (ValueError, RecursionError):
        return None, content, hashlib.sha256(content).hexdigest()


def inspection(root: Path, workspace_id: str) -> dict:
    remote = local_remote.inspection(root, workspace_id)
    origin = remote["public_url"]
    view = {
        "revision": "unreadable",
        "repairable": False,
        "state": "configuration_error",
        "message": "Company settings could not be read safely. Other local access is retained.",
        "providers": [],
        "has_custom_ca": False,
        "callback_uri": origin + "/company/callback" if origin else None,
    }
    try:
        saved, content, revision = _record(root, workspace_id)
    except (OSError, state.LocalSetupError):
        return view
    view.update(revision=revision, repairable=True)
    if saved is None and content is None and os.environ.get("MNEMION_COMPANY_SIGN_IN_FILE"):
        view.update(
            state="external",
            repairable=False,
            message="Company sign-in is managed by this host's environment file. Maintain that configuration or remove its environment setting before using local setup.",
        )
        return view
    if saved is None and content is not None:
        view["message"] = (
            "Company settings need repair. Reset preserves the damaged file before clearing only these settings."
        )
        return view
    view.update(
        providers=[
            {
                **item.model_dump(exclude={"client_secret"}),
                "has_client_secret": bool(item.client_secret),
            }
            for item in (saved.providers if saved else ())
        ],
        has_custom_ca=bool(saved and saved.ca_pem),
    )
    if not view["providers"]:
        view.update(state="disabled", message="No company sign-in provider is configured.")
    elif not origin:
        view.update(
            state="needs_remote",
            message="Enable an HTTPS address in Remote access to use company sign-in.",
        )
    else:
        view.update(
            state="configured",
            message="Company providers are configured. Complete a real sign-in to verify your provider registration.",
        )
    return view


def _current(root: Path, command: CompanyRequest):
    from .local_workspace import configuration

    workspace = configuration(root)
    if str(command.workspace_id) != workspace["workspace_id"]:
        raise state.LocalSetupError("settings_changed", "Choose the current local workspace.")
    saved, content, revision = _record(root, workspace["workspace_id"])
    remote = local_remote.inspection(root, workspace["workspace_id"])
    if (
        command.expected_revision != revision
        or command.expected_remote_revision != remote["revision"]
    ):
        raise state.LocalSetupError(
            "settings_changed", "Company or remote settings changed. Refresh and review them again."
        )
    return saved, content, remote


def configure(root: Path, change: CompanyChange) -> dict:
    with state.lock(root):
        saved, content, remote = _current(root, change)
        if saved is None and content is None and os.environ.get("MNEMION_COMPANY_SIGN_IN_FILE"):
            raise state.LocalSetupError(
                "company_external_configuration",
                "This host uses an existing company environment file. Review and remove that environment setting before using local setup.",
            )
        damaged = saved is None and content is not None
        if damaged != (change.action == "reset"):
            if damaged:
                raise state.LocalSetupError(
                    "company_repair_required",
                    "Reset the damaged company settings before adding a provider.",
                )
            if change.action == "reset":
                raise state.LocalSetupError(
                    "settings_changed", "These company settings do not need repair."
                )
        providers = {item.id: item for item in saved.providers} if saved else {}
        ca_pem = saved.ca_pem if saved else None
        if change.action == "save":
            if not remote["public_url"]:
                raise state.LocalSetupError(
                    "remote_required", "Set up the workspace HTTPS address in Remote access first."
                )
            provider = change.provider
            previous = providers.get(provider.id)
            secret = change.client_secret
            if secret is None and not change.clear_client_secret and previous:
                secret = previous.client_secret
                if secret and any(
                    getattr(previous, field) != getattr(provider, field)
                    for field in (
                        "issuer",
                        "authorization_url",
                        "token_url",
                        "jwks_url",
                        "client_id",
                    )
                ):
                    raise state.LocalSetupError(
                        "company_secret_review",
                        "The provider or client changed. Replace or explicitly remove its client secret before saving.",
                    )
            providers[provider.id] = SavedProvider(**provider.model_dump(), client_secret=secret)
            if "ca_pem" in change.model_fields_set:
                ca_pem = change.ca_pem
        elif change.action == "remove":
            if change.provider_id not in providers:
                raise state.LocalSetupError(
                    "settings_changed",
                    "This provider is no longer configured. Refresh its settings.",
                )
            del providers[change.provider_id]
        updated = CompanyRecord(
            workspace_id=change.workspace_id,
            revision=uuid4(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            providers=list(providers.values()),
            ca_pem=ca_pem,
        )
        value = updated.model_dump(mode="json")
        for entry, item in zip(value["providers"], updated.providers):
            entry["client_secret"] = (
                item.client_secret.get_secret_value() if item.client_secret else None
            )
        if len(json.dumps(value).encode()) > 65536:
            raise state.LocalSetupError(
                "company_capacity",
                "Company settings exceed the 64 KiB limit. Reduce the number or size of providers.",
            )
        path = root / "company-access.json"
        if damaged:
            state.replace_damaged(path, value, expected=content, kind="company")
        else:
            state.write(path, value, replace=content is not None)
        return inspection(root, str(change.workspace_id))


async def discover(root: Path, command: CompanyDiscovery, *, transport=None) -> dict:
    saved, _, _ = _current(root, command)
    ca_pem = (
        command.ca_pem
        if "ca_pem" in command.model_fields_set
        else (saved.ca_pem if saved else None)
    )
    identity = CompanyIdentity(ca_pem=ca_pem)
    try:
        async with (
            asyncio.timeout(12),
            httpx.AsyncClient(
                verify=identity.tls,
                trust_env=False,
                follow_redirects=False,
                timeout=8,
                transport=transport,
            ) as client,
        ):
            metadata = await identity._json(
                client, "GET", command.issuer.rstrip("/") + "/.well-known/openid-configuration"
            )
        advertised = {
            "response_types_supported": metadata.get("response_types_supported", []),
            "scopes_supported": metadata.get("scopes_supported", ["openid"]),
            "id_token_signing_alg_values_supported": metadata.get(
                "id_token_signing_alg_values_supported", []
            ),
            "code_challenge_methods_supported": metadata.get(
                "code_challenge_methods_supported", ["S256"]
            ),
            "token_endpoint_auth_methods_supported": metadata.get(
                "token_endpoint_auth_methods_supported", ["client_secret_basic"]
            ),
        }
        if any(
            not isinstance(values, list) or not all(isinstance(item, str) for item in values)
            for values in advertised.values()
        ):
            raise ValueError("Invalid provider metadata")
        if (
            metadata.get("issuer") != command.issuer
            or "code" not in advertised["response_types_supported"]
            or "openid" not in advertised["scopes_supported"]
            or not {"RS256", "ES256"}.intersection(
                advertised["id_token_signing_alg_values_supported"]
            )
            or "S256" not in advertised["code_challenge_methods_supported"]
            or not {"client_secret_basic", "none"}.intersection(
                advertised["token_endpoint_auth_methods_supported"]
            )
        ):
            raise ValueError("Unsupported issuer or authorization flow")
        endpoints = {
            "issuer": command.issuer,
            "authorization_url": https_url(metadata["authorization_endpoint"]),
            "token_url": https_url(metadata["token_endpoint"]),
            "jwks_url": https_url(metadata["jwks_uri"]),
        }
    except (
        httpx.HTTPError,
        ServiceError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        TimeoutError,
        RecursionError,
    ):
        # Never propagate provider bodies, URLs with private query material, or TLS internals.
        raise state.LocalSetupError(
            "company_discovery_failed",
            "Provider discovery failed. Check the exact HTTPS issuer, its certificate and OpenID Connect authorization-code support.",
        ) from None
    _current(root, command)
    return {**command.model_dump(mode="json", exclude={"ca_pem"}), **endpoints}


def identity(
    root: Path, workspace_id: str, *, tenant_id: str, public_url: str | None
) -> CompanyIdentity:
    try:
        saved, content, _ = _record(root, workspace_id)
    except (OSError, state.LocalSetupError):
        return CompanyIdentity()
    if saved is None and content is None:
        # Preserve explicitly supplied CLI/server configuration. The normal
        # desktop environment does not inherit these provider variables.
        return CompanyIdentity.from_environment()
    if saved is None or not public_url:
        return CompanyIdentity()
    return CompanyIdentity(
        [
            CompanyProvider(
                workspace_id=UUID(tenant_id),
                **item.model_dump(exclude={"client_secret"}),
                client_secret=item.client_secret.get_secret_value() if item.client_secret else None,
            )
            for item in saved.providers
        ],
        ca_pem=saved.ca_pem,
    )
