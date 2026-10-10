"""Pinned local multilingual embeddings with explicit generations and spans.

No production hash-vector fallback exists. Model failures leave durable jobs
retryable and lexical retrieval available. The ONNX conversion and tokenizer
are pinned and checked before inference; changing any pipeline setting creates
a different generation, never a mixture of vector spaces.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import ServiceError
from .inference_limits import InferenceGate


@dataclass(frozen=True)
class Generation:
    model: str
    dimensions: int
    configuration: dict

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not 1 <= len(self.model) <= 300:
            raise ValueError("Embedding model identity must contain 1–300 characters")
        if type(self.dimensions) is not int or not 1 <= self.dimensions <= 4096:
            raise ValueError("Embedding dimensions must be an integer from 1 to 4096")
        if (
            not isinstance(self.configuration, dict)
            or {"model", "dimensions"} & self.configuration.keys()
        ):
            raise ValueError("Embedding configuration cannot override its model or dimensions")
        json.dumps(self.configuration, allow_nan=False)

    @property
    def id(self) -> str:
        value = {"model": self.model, "dimensions": self.dimensions, **self.configuration}
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


DEFAULT_GENERATION = Generation(
    model="intfloat/multilingual-e5-small",
    dimensions=384,
    configuration={
        "repository": "Xenova/multilingual-e5-small",
        "revision": "761b726dd34fb83930e26aab4e9ac3899aa1fa78",
        "model_file": "onnx/model_quantized.onnx",
        "model_sha256": "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193",
        "tokenizer_sha256": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
        "runtime": "fastembed",
        "runtime_version": "0.9.0",
        "pooling": "mean",
        "normalization": "l2",
        "query_prefix": "query: ",
        "document_prefix": "passage: ",
        "chunk_tokens": 384,
        "overlap_tokens": 48,
        "max_query_tokens": 480,
        "offset_unit": "unicode_codepoints",
    },
)


@dataclass(frozen=True)
class EmbeddedChunk:
    start: int
    end: int
    vector: list[float]


class Embedder(Protocol):
    generation: Generation

    def query(self, text: str) -> list[float]: ...

    def document(self, text: str) -> list[EmbeddedChunk]: ...

    def token_count(self, text: str) -> int: ...


def vector_literal(vector: list[float], dimensions: int) -> str:
    if len(vector) != dimensions or not all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in vector
    ):
        raise ValueError("Embedding dimensions or finite-value check failed")
    if sum(x * x for x in vector) < 1e-12:
        raise ValueError("Zero embeddings cannot be indexed or queried")
    return json.dumps(vector, allow_nan=False, separators=(",", ":"))


class LocalEmbedder:
    generation = DEFAULT_GENERATION
    _registration_lock = threading.Lock()

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        threads: int = 2,
        offline: bool = False,
        max_queued: int = 16,
        wait_seconds: float = 2,
        generation: Generation | None = None,
    ):
        if generation is not None:
            if generation.configuration.get("runtime") != "fastembed":
                raise ValueError("Local ONNX inference requires a fastembed generation")
            self.generation = generation
        if type(threads) is not int or not 1 <= threads <= 64:
            raise ValueError("Model threads must be an integer from 1 to 64")
        self.cache_dir = Path(cache_dir)
        self.threads = threads
        self.offline = offline
        self._model = None
        self._tokenizer = None
        self._load_lock = threading.Lock()
        self._inference_gate = InferenceGate(max_queued=max_queued, wait_seconds=wait_seconds)

    def prepare(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
            from huggingface_hub import snapshot_download
            from tokenizers import Tokenizer

            config = self.generation.configuration
            if importlib.metadata.version("fastembed") != config["runtime_version"]:
                raise RuntimeError("Embedding runtime changed; a new generation must be registered")
            model_path = Path(
                snapshot_download(
                    repo_id=config["repository"],
                    revision=config["revision"],
                    cache_dir=str(self.cache_dir),
                    allow_patterns=[config["model_file"], "*.json"],
                    local_files_only=self.offline,
                    token=False,
                )
            )
            for filename, expected in (
                (config["model_file"], config["model_sha256"]),
                ("tokenizer.json", config["tokenizer_sha256"]),
            ):
                with (model_path / filename).open("rb") as handle:
                    actual = hashlib.file_digest(handle, "sha256").hexdigest()
                if actual != expected:
                    raise RuntimeError("Embedding model or tokenizer checksum failed")
            registered_name = "mnemion/" + self.generation.id
            with self._registration_lock:
                if not any(
                    item["model"] == registered_name
                    for item in TextEmbedding.list_supported_models()
                ):
                    TextEmbedding.add_custom_model(
                        model=registered_name,
                        pooling=PoolingType(config["pooling"].upper()),
                        normalization=True,
                        sources=ModelSource(hf=config["repository"]),
                        dim=self.generation.dimensions,
                        model_file=config["model_file"],
                    )
            model = TextEmbedding(
                model_name=registered_name,
                specific_model_path=str(model_path),
                threads=self.threads,
                providers=["CPUExecutionProvider"],
                local_files_only=True,
            )
            tokenizer = Tokenizer.from_file(str(model_path / "tokenizer.json"))
            tokenizer.no_truncation()
            tokenizer.no_padding()
            self._tokenizer = tokenizer
            self._model = model

    def token_count(self, text: str) -> int:
        self.prepare()
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)

    def query(self, text: str) -> list[float]:
        with self._inference_gate.acquire():
            return self._query(text)

    def _query(self, text: str) -> list[float]:
        self.prepare()
        if self.token_count(text) > self.generation.configuration["max_query_tokens"]:
            raise ServiceError(
                422, "query_too_long", "The semantic query exceeds this model's query budget."
            )
        vector = next(
            iter(self._model.embed([self.generation.configuration["query_prefix"] + text]))
        ).tolist()
        vector_literal(vector, self.generation.dimensions)
        return vector

    def document(self, text: str) -> list[EmbeddedChunk]:
        with self._inference_gate.acquire():
            return self._document(text)

    def _document(self, text: str) -> list[EmbeddedChunk]:
        self.prepare()
        offsets = self._tokenizer.encode(text, add_special_tokens=False).offsets
        if not offsets:
            raise ValueError("Document has no encodable tokens")
        config = self.generation.configuration
        step = config["chunk_tokens"] - config["overlap_tokens"]
        spans = []
        for index in range(0, len(offsets), step):
            stop = min(index + config["chunk_tokens"], len(offsets))
            start = offsets[index][0] if index else 0
            end = len(text) if stop == len(offsets) else offsets[stop - 1][1]
            if end > start:
                spans.append((start, end))
            if stop == len(offsets):
                break
        if len(spans) > 512:
            raise ValueError("Document exceeds the 512 chunk indexing limit")
        vectors = self._model.embed(
            [config["document_prefix"] + text[start:end] for start, end in spans], batch_size=16
        )
        chunks = []
        for (start, end), vector in zip(spans, vectors, strict=True):
            values = vector.tolist()
            vector_literal(values, self.generation.dimensions)
            chunks.append(EmbeddedChunk(start, end, values))
        return chunks
