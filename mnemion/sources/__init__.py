"""Source adapter plugin API for Mnemion."""

from .base import (
    AdapterClosedError,
    AdapterSchema,
    AuthRequiredError,
    BaseSourceAdapter,
    DrawerRecord,
    FieldSpec,
    RouteHint,
    SchemaConformanceError,
    SourceAdapterError,
    SourceItemMetadata,
    SourceNotFoundError,
    SourceRef,
    SourceSummary,
    validate_drawer_record,
)
from .context import AnaktoronContext
from .registry import ENTRY_POINT_GROUP, discover_adapters

__all__ = [
    "AdapterClosedError",
    "AdapterSchema",
    "AnaktoronContext",
    "AuthRequiredError",
    "BaseSourceAdapter",
    "DrawerRecord",
    "ENTRY_POINT_GROUP",
    "FieldSpec",
    "RouteHint",
    "SchemaConformanceError",
    "SourceAdapterError",
    "SourceItemMetadata",
    "SourceNotFoundError",
    "SourceRef",
    "SourceSummary",
    "discover_adapters",
    "validate_drawer_record",
]
