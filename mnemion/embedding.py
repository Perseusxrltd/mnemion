"""Embedding device selection for Chroma collections."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import MnemionConfig

logger = logging.getLogger("mnemion.embedding")


@dataclass(frozen=True)
class ResolvedEmbeddingDevice:
    device: str
    providers: list[str]
    reason: str


_PROVIDERS_BY_DEVICE = {
    "cpu": ["CPUExecutionProvider"],
    "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "dml": ["DmlExecutionProvider", "CPUExecutionProvider"],
    "coreml": ["CoreMLExecutionProvider", "CPUExecutionProvider"],
}


def _available_providers() -> list[str]:
    try:
        import onnxruntime as ort

        return list(ort.get_available_providers())
    except Exception:
        return ["CPUExecutionProvider"]


def _requested_device(device: str | None = None) -> str:
    requested = (device or MnemionConfig().embedding_device or "auto").lower()
    return requested if requested in {"auto", "cpu", "cuda", "dml", "coreml"} else "auto"


def resolve_embedding_device(device: str | None = None) -> ResolvedEmbeddingDevice:
    """Resolve a requested embedding device into ONNX Runtime providers."""
    requested = _requested_device(device)
    available = set(_available_providers())

    if requested == "auto":
        for candidate in ("cuda", "dml", "coreml"):
            providers = _PROVIDERS_BY_DEVICE[candidate]
            if providers[0] in available:
                return ResolvedEmbeddingDevice(
                    device=candidate,
                    providers=providers,
                    reason=f"auto selected {candidate}",
                )
        return ResolvedEmbeddingDevice(
            device="cpu",
            providers=_PROVIDERS_BY_DEVICE["cpu"],
            reason="auto selected cpu",
        )

    providers = _PROVIDERS_BY_DEVICE[requested]
    if providers[0] in available:
        return ResolvedEmbeddingDevice(
            device=requested,
            providers=providers,
            reason=f"requested {requested}",
        )

    return ResolvedEmbeddingDevice(
        device="cpu",
        providers=_PROVIDERS_BY_DEVICE["cpu"],
        reason=f"fallback from {requested} to cpu; provider unavailable",
    )


def get_embedding_function(device: str | None = None):
    """Return Chroma's local ONNX embedding function for the resolved device."""
    resolved = resolve_embedding_device(device)
    try:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        class MnemionONNXMiniLM(ONNXMiniLM_L6_V2):
            @staticmethod
            def name() -> str:
                # Keep identity compatible with collections created by Chroma's
                # default embedding function while still allowing provider choice.
                return "default"

        return MnemionONNXMiniLM(preferred_providers=resolved.providers)
    except Exception as e:
        logger.warning("Falling back to Chroma default embedding function: %s", e)
        return None


def describe_device(device: str | None = None) -> str:
    resolved = resolve_embedding_device(device)
    return f"{resolved.device} ({', '.join(resolved.providers)}; {resolved.reason})"
