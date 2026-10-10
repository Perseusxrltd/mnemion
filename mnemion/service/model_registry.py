"""Lazy operator-approved models shared by API, indexing and evaluations."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from .embeddings import Embedder, LocalEmbedder
from .errors import ServiceError
from .http_embeddings import HttpEmbedder
from .inference_limits import InferenceGate
from .model_catalog import LOCAL_GENERATIONS, MODEL_CATALOG
from .model_config import EmbeddingConfiguration


class ModelRegistry:
    def __init__(self, default: Embedder, profiles: dict[str, Embedder] | None = None):
        self.default = default
        self.profiles = profiles or {"e5-small": default}
        self._by_generation = {model.generation.id: model for model in self.profiles.values()}
        self._by_generation.setdefault(default.generation.id, default)
        # Switching models must not multiply simultaneous tensor allocations.
        gate = InferenceGate()
        for model in self._by_generation.values():
            if hasattr(model, "_inference_gate"):
                model._inference_gate = gate

    @classmethod
    def from_environment(cls) -> "ModelRegistry":
        path = os.environ.get("MNEMION_EMBEDDING_CONFIG")
        config = EmbeddingConfiguration.from_file(Path(path)) if path else EmbeddingConfiguration()
        cache = os.environ.get("MNEMION_MODEL_CACHE", str(Path.home() / ".cache/mnemion/models"))
        offline = os.environ.get("MNEMION_MODEL_OFFLINE") == "1"
        models = {
            name: LocalEmbedder(
                cache,
                threads=int(os.environ.get("MNEMION_MODEL_THREADS", "2")),
                offline=offline,
                generation=LOCAL_GENERATIONS[name],
            )
            for name in config.local_profiles
        }
        models.update(
            {p.id: HttpEmbedder(p, cache, offline=offline) for p in config.remote_profiles}
        )
        return cls(models["e5-small"], models)

    @property
    def generation_ids(self) -> list[str]:
        return list(self._by_generation)

    def get(self, generation: str) -> Embedder:
        model = self._by_generation.get(generation)
        if model is None:
            raise ServiceError(
                503,
                "embedding_profile_unavailable",
                "This space's embedding profile is unavailable on this server.",
            )
        return model

    def profile(self, identifier: str) -> Embedder:
        if identifier not in self.profiles:
            raise ServiceError(
                422, "unknown_embedding_profile", "Choose an operator-approved embedding profile."
            )
        return self.profiles[identifier]

    def network_egress(self, generation: str) -> bool:
        model = self.get(generation)
        return isinstance(model, HttpEmbedder) and model.profile.network_egress

    def describe(self) -> list[dict]:
        catalog = {row["id"]: row for row in MODEL_CATALOG}
        result = []
        for identifier, model in self.profiles.items():
            remote = isinstance(model, HttpEmbedder)
            generation = model.generation
            endpoint = urlsplit(model.profile.endpoint) if remote else None
            result.append(
                {
                    "id": identifier,
                    "label": model.profile.label
                    if remote
                    else catalog.get(identifier, {}).get("label", generation.model),
                    "model": generation.model,
                    "generation_id": generation.id,
                    "dimensions": generation.dimensions,
                    "execution": model.profile.protocol if remote else "local_cpu",
                    "network_egress": model.profile.network_egress if remote else False,
                    "endpoint_origin": f"{endpoint.scheme}://{endpoint.netloc}"
                    if endpoint
                    else None,
                    "token_count_unit": generation.configuration.get(
                        "token_count_unit", "model_tokens"
                    ),
                    "configuration": generation.configuration,
                }
            )
        return result

    def close(self) -> None:
        for model in self._by_generation.values():
            close = getattr(model, "close", None)
            if close:
                close()
