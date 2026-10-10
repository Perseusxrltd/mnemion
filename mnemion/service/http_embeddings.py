"""Bounded embedding requests to an operator-approved local or cloud endpoint.

No discovery, model pull, daemon startup, automatic retry, or credential download
occurs here. Queue admission and whole-document validation precede inference.
"""

from __future__ import annotations

import json
import math
import os
import ssl
import threading
import time
from pathlib import Path

import httpx

from .embedding_tokens import EmbeddingTokenizer
from .embeddings import EmbeddedChunk
from .errors import ServiceError
from .inference_limits import InferenceGate
from .model_config import RemoteEmbeddingProfile


class ProviderUnavailable(RuntimeError):
    def __init__(self):
        # Provider bodies, URLs and exception strings can contain secrets or text.
        super().__init__("Embedding provider is unavailable or returned an invalid response")


class HttpEmbedder:
    def __init__(
        self,
        profile: RemoteEmbeddingProfile,
        cache_dir: str | Path,
        *,
        offline: bool = False,
        transport: httpx.BaseTransport | None = None,
    ):
        self.profile = profile
        self.generation = profile.generation
        self._tokenizer = EmbeddingTokenizer(profile.tokenizer, Path(cache_dir), offline=offline)
        self._inference_gate = InferenceGate(max_queued=profile.max_queued)
        self._transport = transport
        self._client = None
        self._client_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._stats = {"requests": 0, "failed_requests": 0, "request_bytes": 0, "response_bytes": 0}

    @property
    def token_count_unit(self) -> str:
        return self._tokenizer.unit

    def prepare(self) -> None:
        """Prepare only a pinned tokenizer; never send text or start a model."""
        try:
            self._tokenizer.prepare()
        except Exception:
            raise ProviderUnavailable() from None

    def token_count(self, text: str) -> int:
        self.prepare()
        return self._tokenizer.count(text)

    def snapshot(self) -> dict:
        with self._stats_lock:
            return {**self._stats, "token_count_unit": self.token_count_unit}

    def close(self) -> None:
        with self._client_lock:
            if self._client is not None:
                self._client.close()
                self._client = None

    def _get_client(self) -> httpx.Client:
        with self._client_lock:
            if self._client is None:
                profile, headers = self.profile, {}
                if profile.api_key_env:
                    key = os.environ.get(profile.api_key_env)
                    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
                        raise ProviderUnavailable()
                    headers[profile.api_key_header] = (
                        f"Bearer {key}" if profile.api_key_header == "Authorization" else key
                    )
                verification: ssl.SSLContext | bool = True
                if profile.ca_bundle_env:
                    path = os.environ.get(profile.ca_bundle_env)
                    if not path:
                        raise ProviderUnavailable()
                    verification = ssl.create_default_context(cafile=path)
                self._client = httpx.Client(
                    headers=headers,
                    verify=verification,
                    timeout=profile.timeout_seconds,
                    trust_env=False,
                    follow_redirects=False,
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
                    transport=self._transport,
                )
            return self._client

    def _validate_input(self, text: str, *, query=False) -> None:
        if not text or len(text.encode("utf-8")) > self.profile.max_document_bytes:
            raise ValueError("Embedding input is empty or exceeds the configured byte limit")
        limit = self.profile.max_query_tokens if query else self.profile.max_input_tokens
        if self.token_count(text) > limit:
            if query:
                raise ServiceError(
                    422, "query_too_long", "The semantic query exceeds this model's query budget."
                )
            raise ValueError("A prefixed document chunk exceeds the provider input budget")

    def query(self, text: str) -> list[float]:
        with self._inference_gate.acquire():
            value = self.profile.query_prefix + text
            self._validate_input(value, query=True)
            return self._request([value], time.monotonic() + self.profile.timeout_seconds)[0]

    def document(self, text: str) -> list[EmbeddedChunk]:
        with self._inference_gate.acquire():
            if len(text.encode("utf-8")) > self.profile.max_document_bytes:
                raise ValueError("Document exceeds the configured byte limit")
            self.prepare()
            profile = self.profile
            spans = self._tokenizer.spans(text, profile.chunk_tokens, profile.overlap_tokens)
            inputs = [profile.document_prefix + text[start:end] for start, end in spans]
            # Validate the complete document before any potentially metered call.
            for value in inputs:
                self._validate_input(value)
            deadline = time.monotonic() + profile.document_timeout_seconds
            vectors = []
            for start in range(0, len(inputs), profile.batch_size):
                vectors.extend(self._request(inputs[start : start + profile.batch_size], deadline))
            return [
                EmbeddedChunk(start, end, vector)
                for (start, end), vector in zip(spans, vectors, strict=True)
            ]

    def _request(self, inputs: list[str], deadline: float) -> list[list[float]]:
        profile = self.profile
        payload = {"model": profile.model, "input": inputs}
        if profile.protocol == "openai":
            payload["encoding_format"] = "float"
        else:
            payload.update(
                {
                    "truncate": False,
                    "keep_alive": f"{profile.keep_alive_seconds}s",
                    "options": {
                        "num_thread": profile.server_threads,
                        "num_ctx": profile.max_input_tokens,
                    },
                }
            )
        if profile.send_dimensions:
            payload["dimensions"] = profile.dimensions
        body = json.dumps(
            payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        sent, received, failed = False, 0, True
        try:
            timeout = min(profile.timeout_seconds, deadline - time.monotonic())
            if timeout <= 0:
                raise ProviderUnavailable()
            client = self._get_client()
            sent = True
            with client.stream(
                "POST",
                profile.endpoint,
                content=body,
                headers={"Content-Type": "application/json", "Accept-Encoding": "identity"},
                timeout=timeout,
            ) as response:
                if response.status_code != 200:
                    raise ProviderUnavailable()
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ProviderUnavailable()
                content_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                )
                if content_type != "application/json":
                    raise ProviderUnavailable()
                content_length = response.headers.get("content-length")
                if content_length and not 0 <= int(content_length) <= profile.max_response_bytes:
                    raise ProviderUnavailable()
                chunks = []
                for chunk in response.iter_bytes(chunk_size=16384):
                    received += len(chunk)
                    if received > profile.max_response_bytes or time.monotonic() > deadline:
                        raise ProviderUnavailable()
                    chunks.append(chunk)
            if time.monotonic() > deadline:
                raise ProviderUnavailable()
            result = json.loads(b"".join(chunks))
            if not isinstance(result, dict) or result.get("model") != (
                profile.response_model or profile.model
            ):
                raise ProviderUnavailable()
            if profile.protocol == "openai":
                data = result.get("data")
                if not isinstance(data, list) or len(data) != len(inputs):
                    raise ProviderUnavailable()
                indexed = {}
                for item in data:
                    if not isinstance(item, dict) or type(item.get("index")) is not int:
                        raise ProviderUnavailable()
                    index = item["index"]
                    if index in indexed or not 0 <= index < len(inputs):
                        raise ProviderUnavailable()
                    indexed[index] = item.get("embedding")
                values = [indexed[index] for index in range(len(inputs))]
            else:
                values = result.get("embeddings")
            if not isinstance(values, list) or len(values) != len(inputs):
                raise ProviderUnavailable()
            vectors = [self._normalize(vector) for vector in values]
            failed = False
            return vectors
        except Exception:
            raise ProviderUnavailable() from None
        finally:
            with self._stats_lock:
                self._stats["requests"] += int(sent)
                self._stats["failed_requests"] += int(sent and failed)
                self._stats["request_bytes"] += len(body) if sent else 0
                self._stats["response_bytes"] += received

    def _normalize(self, vector) -> list[float]:
        if (
            not isinstance(vector, list)
            or len(vector) != self.generation.dimensions
            or not all(type(value) in (int, float) and math.isfinite(value) for value in vector)
        ):
            raise ProviderUnavailable()
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm < 1e-12:
            raise ProviderUnavailable()
        return [value / norm for value in vector]
