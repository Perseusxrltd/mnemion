"""Read-only source adapters and the public connector protocol client."""

from .protocol import ConnectorClient, Document, Scope

__all__ = ["ConnectorClient", "Document", "Scope"]
