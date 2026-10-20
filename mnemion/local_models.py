"""Private model enrollment for the host's OS account, with no inference on save."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from . import local_state as state
from .local_company import ca_context
from .service.librarian_config import LibrarianConfiguration, LibrarianProfile
from .service.model_config import EmbeddingConfiguration, RemoteEmbeddingProfile
from .service.oauth import _json_object


def _desktop_profile(profile):
    if profile.api_key_env or profile.ca_bundle_env or profile.tokenizer.kind != "utf8":
        raise ValueError("Desktop profiles use private credentials and conservative UTF-8 budgets")
    return profile


class EmbeddingSettings(RemoteEmbeddingProfile):
    @model_validator(mode="after")
    def private_settings(self):
        return _desktop_profile(self)


class LibrarianSettings(LibrarianProfile):
    @model_validator(mode="after")
    def private_settings(self):
        return _desktop_profile(self)


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmbeddingDefinition(Definition):
    kind: Literal["embedding"]
    profile: EmbeddingSettings


class LibrarianDefinition(Definition):
    kind: Literal["librarian"]
    profile: LibrarianSettings


ProviderDefinition = Annotated[
    EmbeddingDefinition | LibrarianDefinition, Field(discriminator="kind")
]


class PrivateValues(Definition):
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    ca_pem: str | None = Field(default=None, max_length=8192)

    @field_validator("api_key")
    @classmethod
    def credential(cls, value):
        if value is not None and not (
            value.get_secret_value() and all(33 <= ord(c) <= 126 for c in value.get_secret_value())
        ):
            raise ValueError("Use a nonempty API key without spaces or control characters")
        return value

    @field_validator("ca_pem")
    @classmethod
    def certificate(cls, value):
        ca_context(value)
        return value


class SavedProvider(PrivateValues):
    provider: ProviderDefinition


class ModelsRecord(Definition):
    format: Literal[1] = 1
    workspace_id: UUID
    revision: UUID
    updated_at: str
    providers: list[SavedProvider] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def profiles(self):
        EmbeddingConfiguration(
            local_profiles=["e5-small", "bge-small-en"],
            remote_profiles=[
                p.provider.profile for p in self.providers if p.provider.kind == "embedding"
            ],
        )
        LibrarianConfiguration(
            profiles=[p.provider.profile for p in self.providers if p.provider.kind == "librarian"]
        )
        return self


class ModelsRequest(Definition):
    workspace_id: UUID
    expected_revision: str = Field(pattern=r"^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$")


class ModelsChange(ModelsRequest, PrivateValues):
    action: Literal["save", "remove", "reset"]
    provider: ProviderDefinition | None = None
    kind: Literal["embedding", "librarian"] | None = None
    profile_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,63}$")
    clear_api_key: bool = False

    @model_validator(mode="after")
    def operation(self):
        if self.action == "save":
            if not self.provider or self.kind is not None or self.profile_id is not None:
                raise ValueError("Choose a model profile to save")
            if self.api_key is not None and self.clear_api_key:
                raise ValueError("Replace or remove the API key, not both")
        elif (
            self.provider is not None
            or self.api_key is not None
            or self.clear_api_key
            or "ca_pem" in self.model_fields_set
            or (self.action == "remove") != (self.kind is not None and self.profile_id is not None)
            or (self.action == "reset" and (self.kind is not None or self.profile_id is not None))
        ):
            raise ValueError("Choose a profile removal or damaged-settings reset")
        return self


def _record(root: Path, workspace_id: str):
    try:
        content = state.read_bytes(root / "model-providers.json")
    except FileNotFoundError:
        return None, None, "not-configured"
    try:
        if len(content) > 131072:
            raise ValueError("Model settings exceed 128 KiB")
        json.loads(content, object_pairs_hook=_json_object)
        record = ModelsRecord.model_validate_json(content)
        if str(record.workspace_id) != workspace_id:
            raise ValueError("Different workspace")
        return record, content, str(record.revision)
    except (ValueError, RecursionError):
        return None, content, hashlib.sha256(content).hexdigest()


def _external():
    return any(
        os.environ.get(key) for key in ("MNEMION_EMBEDDING_CONFIG", "MNEMION_LIBRARIAN_CONFIG")
    )


def inspection(root: Path, workspace_id: str) -> dict:
    view = {
        "revision": "unreadable",
        "repairable": False,
        "state": "configuration_error",
        "message": "Model settings could not be read safely. Built-in memory models remain available.",
        "providers": [],
    }
    try:
        saved, content, revision = _record(root, workspace_id)
    except (OSError, state.LocalSetupError):
        return view
    view.update(revision=revision, repairable=True)
    if saved is None and content is None and _external():
        view.update(
            state="external",
            repairable=False,
            message="Model providers are managed by this host's environment configuration. Review it before using desktop setup.",
        )
        return view
    if saved is None and content is not None:
        view["message"] = (
            "Model settings need repair. Reset preserves a private copy before clearing these profiles. Built-in memory models remain available."
        )
        return view
    for item in saved.providers if saved else ():
        definition = item.provider
        profile = definition.profile
        view["providers"].append(
            {
                **definition.model_dump(mode="json"),
                "has_api_key": bool(item.api_key),
                "has_custom_ca": bool(item.ca_pem),
                "network_egress": profile.network_egress,
                "fingerprint": profile.generation.id
                if definition.kind == "embedding"
                else profile.fingerprint,
            }
        )
    view.update(
        state="configured" if view["providers"] else "not_configured",
        message="Model profiles are saved. Choose and approve them per space before use. Saving does not contact a provider."
        if view["providers"]
        else "Built-in CPU embedding models are available. Add a provider to use your own embedding or librarian model.",
    )
    return view


def configure(root: Path, change: ModelsChange) -> dict:
    from .local_workspace import configuration

    with state.lock(root):
        settings = configuration(root)
        if settings["workspace_id"] != str(change.workspace_id):
            raise state.LocalSetupError("settings_changed", "Choose the current local workspace.")
        saved, content, revision = _record(root, settings["workspace_id"])
        if revision != change.expected_revision:
            raise state.LocalSetupError(
                "settings_changed", "Model settings changed. Refresh and review them again."
            )
        if content is None and _external():
            raise state.LocalSetupError(
                "models_external_configuration",
                "Review and remove this host's model environment configuration before using desktop setup.",
            )
        damaged = saved is None and content is not None
        if damaged != (change.action == "reset"):
            raise state.LocalSetupError(
                "models_repair_required",
                "Reset damaged model settings before editing profiles. Reset is only available for damaged settings.",
            )
        providers = (
            {(p.provider.kind, p.provider.profile.id): p for p in saved.providers} if saved else {}
        )
        if change.action == "save":
            definition = change.provider
            key = (definition.kind, definition.profile.id)
            previous = providers.get(key)
            credential = change.api_key
            if credential is None and previous and not change.clear_api_key:
                credential = previous.api_key
                if credential and any(
                    getattr(previous.provider.profile, field) != getattr(definition.profile, field)
                    for field in ("endpoint", "protocol", "api_key_header")
                ):
                    raise state.LocalSetupError(
                        "model_key_review",
                        "The endpoint or authentication method changed. Enter a key for the new provider or explicitly remove the saved key.",
                    )
            providers[key] = SavedProvider(
                provider=definition,
                api_key=credential,
                ca_pem=change.ca_pem
                if "ca_pem" in change.model_fields_set
                else previous.ca_pem
                if previous
                else None,
            )
        elif change.action == "remove":
            if providers.pop((change.kind, change.profile_id), None) is None:
                raise state.LocalSetupError(
                    "settings_changed",
                    "This profile has already been removed. Refresh model settings.",
                )
        record = ModelsRecord(
            workspace_id=change.workspace_id,
            revision=uuid4(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            providers=list(providers.values()),
        )
        value = record.model_dump(mode="json")
        # SecretStr masks diagnostics; only this private, ACL-checked record stores values.
        for data, item in zip(value["providers"], record.providers, strict=True):
            data["api_key"] = item.api_key.get_secret_value() if item.api_key else None
        if len(json.dumps(value).encode()) > 131072:
            raise state.LocalSetupError(
                "models_capacity",
                "Model settings exceed 128 KiB. Reduce the number or size of profiles.",
            )
        path = root / "model-providers.json"
        if damaged:
            state.replace_damaged(path, value, expected=content, kind="models")
        else:
            state.write(path, value, replace=content is not None)
        return inspection(root, str(change.workspace_id))


def _saved(root: Path, workspace_id: str):
    try:
        saved, content, _ = _record(root, workspace_id)
        return saved.providers if saved else [], content is None
    except (OSError, state.LocalSetupError):
        return [], False


def embedding_providers(root: Path, workspace_id: str, cache: Path):
    from .service.http_embeddings import HttpEmbedder

    providers, absent = _saved(root, workspace_id)
    if absent and os.environ.get("MNEMION_EMBEDDING_CONFIG"):
        config = EmbeddingConfiguration.from_file(Path(os.environ["MNEMION_EMBEDDING_CONFIG"]))
        return {p.id: HttpEmbedder(p, cache) for p in config.remote_profiles}
    return {
        p.provider.profile.id: HttpEmbedder(
            p.provider.profile,
            cache,
            api_key=p.api_key.get_secret_value() if p.api_key else None,
            tls=ca_context(p.ca_pem) if p.ca_pem else None,
        )
        for p in providers
        if p.provider.kind == "embedding"
    }


def librarian_registry(root: Path, workspace_id: str):
    from .service.librarian_provider import LibrarianProvider, LibrarianRegistry

    providers, absent = _saved(root, workspace_id)
    if absent:
        return LibrarianRegistry.from_environment()
    return LibrarianRegistry(
        {
            p.provider.profile.id: LibrarianProvider(
                p.provider.profile,
                cache_dir=root / "models",
                api_key=p.api_key.get_secret_value() if p.api_key else None,
                tls=ca_context(p.ca_pem) if p.ca_pem else None,
            )
            for p in providers
            if p.provider.kind == "librarian"
        }
    )
