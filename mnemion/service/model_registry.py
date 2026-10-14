"""Lazy operator-approved models shared by API, indexing and evaluations."""

from __future__ import annotations

import gc
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

from .embeddings import Embedder, LocalEmbedder
from .errors import ServiceError
from .heap_memory import release_unused_heap
from .http_embeddings import HttpEmbedder
from .inference_limits import InferenceGate
from .model_catalog import LOCAL_GENERATIONS, MODEL_CATALOG
from .model_config import EmbeddingConfiguration


def idle_policy(seconds: int) -> int:
    if type(seconds) is not int or not (seconds == 0 or 10 <= seconds <= 86400):
        raise ValueError("Model idle cleanup must be disabled with 0 or use 10–86400 seconds")
    return seconds


class ModelRegistry:
    def __init__(
        self,
        default: Embedder,
        profiles: dict[str, Embedder] | None = None,
        *,
        idle_seconds: int = 300,
    ):
        idle_seconds = idle_policy(idle_seconds)
        self.default = default
        self.profiles = profiles or {"e5-small": default}
        self._by_generation = {model.generation.id: model for model in self.profiles.values()}
        self._by_generation.setdefault(default.generation.id, default)
        # Switching models must not multiply simultaneous tensor allocations.
        gate = InferenceGate.from_environment()
        self.inference_gate = gate
        self.memory_budget = None
        self.idle_seconds = idle_seconds
        self._idle_stop = threading.Event()
        self._idle_thread: threading.Thread | None = None
        self._idle_lock = threading.Lock()
        self._idle_evictions = 0
        self._idle_failures = 0
        for model in self._by_generation.values():
            if hasattr(model, "_inference_gate"):
                model._inference_gate = gate

    @classmethod
    def from_environment(cls, *, shared_models=True) -> "ModelRegistry":
        raw_idle = os.environ.get("MNEMION_MODEL_IDLE_SECONDS", "300")
        if not raw_idle.isascii() or not raw_idle.isdigit() or len(raw_idle) > 5:
            raise ValueError("Model idle cleanup must be disabled with 0 or use 10–86400 seconds")
        idle_seconds = idle_policy(int(raw_idle))
        path = os.environ.get("MNEMION_EMBEDDING_CONFIG")
        config = EmbeddingConfiguration.from_file(Path(path)) if path else EmbeddingConfiguration()
        cache = os.environ.get("MNEMION_MODEL_CACHE", str(Path.home() / ".cache/mnemion/models"))
        offline = os.environ.get("MNEMION_MODEL_OFFLINE") == "1"
        broker = os.environ.get("MNEMION_MODEL_BROKER") if shared_models else None
        factory, arguments = LocalEmbedder, [cache]
        if broker:
            from .model_broker import SharedLocalEmbedder

            factory, arguments = SharedLocalEmbedder, [Path(broker), cache]
        models = {
            name: factory(
                *arguments,
                threads=int(os.environ.get("MNEMION_MODEL_THREADS", "2")),
                offline=offline,
                generation=LOCAL_GENERATIONS[name],
            )
            for name in config.local_profiles
        }
        models.update(
            {p.id: HttpEmbedder(p, cache, offline=offline) for p in config.remote_profiles}
        )
        return cls(models["e5-small"], models, idle_seconds=idle_seconds)

    def release_idle(self) -> int:
        """Discard only inactive local sessions, retaining approved model files.

        The process that owns each local session releases it. Managed APIs
        proxy inference to their worker, whose idle policy governs that cache.
        """
        if not self.idle_seconds:
            return 0
        released = 0
        with self.inference_gate.maintenance(minimum_idle_seconds=self.idle_seconds) as acquired:
            if not acquired:
                return 0
            try:
                for model in self._by_generation.values():
                    if isinstance(model, LocalEmbedder) and model._model is not None:
                        model._unload()
                        released += 1
            finally:
                # Preserve successful release observations if a later model's
                # cleanup needs another attempt.
                if released:
                    try:
                        gc.collect()
                        release_unused_heap()
                    finally:
                        # Publish completion after allocator cleanup, so memory
                        # observations cannot race ahead of the actual release.
                        with self._idle_lock:
                            self._idle_evictions += released
        return released

    def cache_status(self) -> dict:
        with self._idle_lock:
            return {
                "scope": "this_process",
                "local_model_owner": "worker"
                if any(
                    getattr(model, "shared_model", False) for model in self._by_generation.values()
                )
                else "this_process",
                "idle_seconds": self.idle_seconds,
                "idle_cleanup_enabled": self.idle_seconds > 0,
                "idle_cleanup_running": bool(self._idle_thread and self._idle_thread.is_alive()),
                "idle_model_evictions": self._idle_evictions,
                "cleanup_failures": self._idle_failures,
                "loaded_local_models": sum(
                    isinstance(model, LocalEmbedder) and model._model is not None
                    for model in self._by_generation.values()
                ),
            }

    def _idle_interval(self) -> float:
        return min(15, self.idle_seconds / 4)

    def shared_worker_status(self) -> dict | None:
        model = next(
            (
                model
                for model in self._by_generation.values()
                if getattr(model, "shared_model", False)
            ),
            None,
        )
        return model.worker_status() if model is not None else None

    def start_idle_cleanup(self) -> None:
        if not self.idle_seconds:
            return
        with self._idle_lock:
            if self._idle_thread and self._idle_thread.is_alive():
                return
            self._idle_stop.clear()

            def run():
                while not self._idle_stop.wait(self._idle_interval()):
                    try:
                        self.release_idle()
                    except Exception:
                        # Keep cleanup retryable without logging native/provider
                        # text. Current work and canonical data remain untouched.
                        with self._idle_lock:
                            self._idle_failures += 1

            self._idle_thread = threading.Thread(target=run, name="mnemion-model-idle", daemon=True)
            self._idle_thread.start()

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
        self._idle_stop.set()
        thread = self._idle_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        for model in self._by_generation.values():
            close = getattr(model, "close", None)
            if close:
                close()
