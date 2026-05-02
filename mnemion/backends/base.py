"""Backend protocol and typed result shims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BackendError(RuntimeError):
    """Base storage backend error."""


class AnaktoronNotFoundError(BackendError):
    """The configured Anaktoron does not exist."""


PalaceNotFoundError = AnaktoronNotFoundError


class BackendClosedError(BackendError):
    """The backend was used after being closed."""


class UnsupportedFilterError(BackendError, ValueError):
    """A caller used a filter expression this backend will not execute."""


class DimensionMismatchError(BackendError):
    """Embedding dimensions are incompatible with the target collection."""


class EmbedderIdentityMismatchError(BackendError):
    """Embedding function identity is incompatible with the target collection."""


@dataclass(frozen=True)
class AnaktoronRef:
    path: str
    collection_name: str
    backend: str = "chroma"


PalaceRef = AnaktoronRef


@dataclass(frozen=True)
class HealthStatus:
    ok: bool
    detail: str = ""
    metadata: dict[str, Any] | None = None


class _DictBackedResult(dict):
    """Dictionary-compatible result object with attribute accessors."""

    _fields: tuple[str, ...] = ()

    def __getattr__(self, name: str) -> Any:
        if name in self._fields:
            return self.get(name)
        raise AttributeError(name)


class QueryResult(_DictBackedResult):
    _fields = ("ids", "documents", "metadatas", "distances", "embeddings")

    def __init__(
        self,
        ids=None,
        documents=None,
        metadatas=None,
        distances=None,
        embeddings=None,
        **extra,
    ):
        super().__init__(
            ids=ids or [],
            documents=documents or [],
            metadatas=metadatas or [],
            distances=distances or [],
            embeddings=embeddings,
            **extra,
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "QueryResult":
        return cls(
            ids=data.get("ids"),
            documents=data.get("documents"),
            metadatas=data.get("metadatas"),
            distances=data.get("distances"),
            embeddings=data.get("embeddings"),
            **{k: v for k, v in data.items() if k not in cls._fields},
        )


class GetResult(_DictBackedResult):
    _fields = ("ids", "documents", "metadatas", "embeddings")

    def __init__(self, ids=None, documents=None, metadatas=None, embeddings=None, **extra):
        super().__init__(
            ids=ids or [],
            documents=documents or [],
            metadatas=metadatas or [],
            embeddings=embeddings,
            **extra,
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "GetResult":
        return cls(
            ids=data.get("ids"),
            documents=data.get("documents"),
            metadatas=data.get("metadatas"),
            embeddings=data.get("embeddings"),
            **{k: v for k, v in data.items() if k not in cls._fields},
        )


class BaseCollection:
    """Thin collection interface implemented by storage backends."""

    def add(self, **kwargs):
        raise NotImplementedError

    def upsert(self, **kwargs):
        raise NotImplementedError

    def update(self, **kwargs):
        raise NotImplementedError

    def query(self, **kwargs) -> QueryResult:
        raise NotImplementedError

    def get(self, **kwargs) -> GetResult:
        raise NotImplementedError

    def delete(self, **kwargs):
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def estimated_count(self) -> int:
        return self.count()

    def close(self) -> None:
        return None

    def health(self) -> HealthStatus:
        return HealthStatus(ok=True)


class BaseBackend:
    name = "base"

    def get_collection(self, name: str, create: bool = False) -> BaseCollection:
        raise NotImplementedError

    def close(self) -> None:
        return None
