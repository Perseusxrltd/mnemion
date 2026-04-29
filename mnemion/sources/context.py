"""Anaktoron context object passed to source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AnaktoronContext:
    anaktoron_path: str
    collection_name: str
    kg_path: Optional[str] = None
