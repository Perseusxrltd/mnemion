"""Source adapter contract for Mnemion ingest plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Iterator, Literal, Optional

if TYPE_CHECKING:
    from .context import AnaktoronContext


class SourceAdapterError(Exception):
    """Base class for source-adapter errors."""


class SourceNotFoundError(SourceAdapterError):
    """Raised when a source cannot be read."""


class AuthRequiredError(SourceAdapterError):
    """Raised when an adapter requires credentials that are not configured."""


class AdapterClosedError(SourceAdapterError):
    """Raised when an adapter is used after close."""


class SchemaConformanceError(SourceAdapterError):
    """Raised when adapter metadata violates its declared schema."""


@dataclass(frozen=True)
class SourceRef:
    local_path: Optional[str] = None
    uri: Optional[str] = None
    options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RouteHint:
    wing: Optional[str] = None
    room: Optional[str] = None
    hall: Optional[str] = None


@dataclass(frozen=True)
class SourceItemMetadata:
    source_file: str
    version: str
    size_hint: Optional[int] = None
    route_hint: Optional[RouteHint] = None


@dataclass(frozen=True)
class DrawerRecord:
    content: str
    source_file: str
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)
    route_hint: Optional[RouteHint] = None


@dataclass(frozen=True)
class SourceSummary:
    description: str
    item_count: Optional[int] = None


IngestMode = Literal["chunked_content", "whole_record", "metadata_only"]


@dataclass(frozen=True)
class FieldSpec:
    type: Literal["string", "int", "float", "bool", "delimiter_joined_string", "json_string"]
    required: bool
    description: str
    indexed: bool = False
    delimiter: str = ";"
    json_schema: Optional[dict] = None


@dataclass(frozen=True)
class AdapterSchema:
    fields: dict[str, FieldSpec]
    version: str


IngestResult = object


class BaseSourceAdapter(ABC):
    """Base contract for lightweight Mnemion source adapters."""

    name: ClassVar[str]
    spec_version: ClassVar[str] = "1.0"
    adapter_version: ClassVar[str] = "0.0.0"
    capabilities: ClassVar[frozenset[str]] = frozenset()
    supported_modes: ClassVar[frozenset[str]] = frozenset({"chunked_content"})
    declared_transformations: ClassVar[frozenset[str]] = frozenset()
    default_privacy_class: ClassVar[str] = "pii_potential"

    @abstractmethod
    def ingest(self, *, source: SourceRef, anaktoron: "AnaktoronContext") -> Iterator[IngestResult]:
        """Enumerate and extract content from a source."""

    @abstractmethod
    def describe_schema(self) -> AdapterSchema:
        """Declare flat metadata fields emitted by this adapter."""

    def is_current(self, *, item: SourceItemMetadata, existing_metadata: Optional[dict]) -> bool:
        return False

    def source_summary(self, *, source: SourceRef) -> SourceSummary:
        return SourceSummary(description=self.name)

    def close(self) -> None:
        return None


def _is_flat_scalar(value) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def validate_drawer_record(record: DrawerRecord, schema: AdapterSchema) -> None:
    if not record.content:
        raise SchemaConformanceError("DrawerRecord.content must not be empty")
    if not record.source_file:
        raise SchemaConformanceError("DrawerRecord.source_file must not be empty")
    for key, value in record.metadata.items():
        if not _is_flat_scalar(value):
            raise SchemaConformanceError(f"metadata field {key!r} must be a flat scalar")
    for field_name, spec in schema.fields.items():
        if spec.required and field_name not in record.metadata:
            raise SchemaConformanceError(f"required metadata field missing: {field_name}")
