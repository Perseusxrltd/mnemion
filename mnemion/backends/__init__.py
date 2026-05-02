"""Storage backend facade for Mnemion."""

from .registry import (
    available_backends,
    get_backend,
    register,
    resolve_backend_for_anaktoron,
    resolve_backend_for_palace,
    unregister,
)

__all__ = [
    "available_backends",
    "get_backend",
    "register",
    "resolve_backend_for_anaktoron",
    "resolve_backend_for_palace",
    "unregister",
]
