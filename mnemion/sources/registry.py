"""Entry-point registry for Mnemion source adapters."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Type

from .base import BaseSourceAdapter

ENTRY_POINT_GROUP = "mnemion.sources"


def discover_adapters() -> dict[str, Type[BaseSourceAdapter]]:
    adapters: dict[str, Type[BaseSourceAdapter]] = {}
    eps = entry_points()
    group = (
        eps.select(group=ENTRY_POINT_GROUP)
        if hasattr(eps, "select")
        else eps.get(ENTRY_POINT_GROUP, [])
    )
    for ep in group:
        adapter_cls = ep.load()
        if not issubclass(adapter_cls, BaseSourceAdapter):
            continue
        adapters[adapter_cls.name] = adapter_cls
    return adapters
