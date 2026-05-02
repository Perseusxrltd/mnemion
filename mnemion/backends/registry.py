"""Backend registry and entry-point loader."""

from __future__ import annotations

from importlib import metadata
from typing import Type

from ..config import MnemionConfig
from .base import BaseBackend, BackendError

_BACKENDS: dict[str, Type[BaseBackend]] = {}
_ENTRYPOINTS_LOADED = False
ENTRY_POINT_GROUP = "mnemion.backends"


def register(name: str, backend_class: Type[BaseBackend]) -> None:
    _BACKENDS[name] = backend_class


def unregister(name: str) -> None:
    _BACKENDS.pop(name, None)


def _load_entrypoints() -> None:
    global _ENTRYPOINTS_LOADED
    if _ENTRYPOINTS_LOADED:
        return
    _ENTRYPOINTS_LOADED = True
    try:
        eps = metadata.entry_points()
        selected = eps.select(group=ENTRY_POINT_GROUP) if hasattr(eps, "select") else eps.get(ENTRY_POINT_GROUP, [])
        for ep in selected:
            if ep.name not in _BACKENDS:
                _BACKENDS[ep.name] = ep.load()
    except Exception:
        return


def _ensure_builtin() -> None:
    if "chroma" not in _BACKENDS:
        from .chroma import ChromaBackend

        register("chroma", ChromaBackend)


def available_backends() -> list[str]:
    _ensure_builtin()
    _load_entrypoints()
    return sorted(_BACKENDS)


def get_backend_class(name: str | None = None) -> Type[BaseBackend]:
    _ensure_builtin()
    _load_entrypoints()
    cfg = MnemionConfig()
    backend_name = name or cfg.backend
    try:
        return _BACKENDS[backend_name]
    except KeyError as e:
        raise BackendError(f"Unknown Mnemion backend: {backend_name}") from e


def get_backend(
    name: str | None = None,
    anaktoron_path: str | None = None,
    embedding_device: str | None = None,
) -> BaseBackend:
    cfg = MnemionConfig()
    backend_class = get_backend_class(name or cfg.backend)
    return backend_class(
        anaktoron_path=anaktoron_path or cfg.anaktoron_path,
        embedding_device=embedding_device or cfg.embedding_device,
    )


def reset_backends() -> None:
    _BACKENDS.clear()
    _ensure_builtin()


def resolve_backend_for_anaktoron(anaktoron_path: str | None = None) -> BaseBackend:
    return get_backend(anaktoron_path=anaktoron_path)


resolve_backend_for_palace = resolve_backend_for_anaktoron
