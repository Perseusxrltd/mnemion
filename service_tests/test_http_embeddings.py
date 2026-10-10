"""Protocol/security tests use in-process HTTP transports, never paid inference."""

import hashlib
import json
import math

import httpx
import pytest
from pydantic import ValidationError

from mnemion.service.embedding_tokens import EmbeddingTokenizer
from mnemion.service.embeddings import DEFAULT_GENERATION, Generation, vector_literal
from mnemion.service.errors import ServiceError
from mnemion.service.http_embeddings import HttpEmbedder, ProviderUnavailable
from mnemion.service.model_config import (
    EmbeddingConfiguration,
    RemoteEmbeddingProfile,
    TokenizerSpec,
)


def profile(**changes):
    return RemoteEmbeddingProfile(
        **{
            "id": "test-server",
            "label": "Test server",
            "protocol": "openai",
            "endpoint": "http://127.0.0.1:11434/v1/embeddings",
            "model": "test-model",
            "revision": "immutable-test-weights-1",
            "dimensions": 2,
            **changes,
        }
    )


def answer(inputs, *, model="test-model"):
    return {
        "model": model,
        "data": [{"index": i, "embedding": [3.0, 4.0]} for i, _ in enumerate(inputs)],
    }


def test_openai_batches_preserve_unicode_offsets_and_reorder_vectors(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMION_TEST_EMBED_KEY", "private-fixture-key")
    calls = []

    def handle(request):
        assert request.headers["authorization"] == "Bearer private-fixture-key"
        assert request.headers["accept-encoding"] == "identity"
        data = json.loads(request.content)
        calls.append(data)
        assert data["dimensions"] == 2 and data["encoding_format"] == "float"
        result = answer(data["input"])
        result["data"] = list(reversed(result["data"]))
        if len(result["data"]) > 1:
            result["data"][0]["embedding"] = [0.0, 2.0]
        return httpx.Response(200, json=result)

    model = HttpEmbedder(
        profile(
            chunk_tokens=32,
            overlap_tokens=8,
            batch_size=2,
            send_dimensions=True,
            api_key_env="MNEMION_TEST_EMBED_KEY",
            document_prefix="passage: ",
            query_prefix="query: ",
        ),
        tmp_path,
        transport=httpx.MockTransport(handle),
    )
    source = "é🧭漢字 memory\n" * 12
    try:
        model.prepare()
        assert calls == []
        chunks = model.document(source)
        assert chunks[0].start == 0 and chunks[-1].end == len(source)
        assert all(first.end >= second.start for first, second in zip(chunks, chunks[1:]))
        sent = [value for call in calls for value in call["input"]]
        assert sent == ["passage: " + source[c.start : c.end] for c in chunks]
        assert all(len(call["input"]) <= 2 for call in calls)
        assert chunks[0].vector == [0.6, 0.8] and chunks[1].vector == [0.0, 1.0]
        assert model.query("test") == [0.6, 0.8]
        assert calls[-1]["input"] == ["query: test"]
        stats = model.snapshot()
        assert stats["requests"] == len(calls) and stats["failed_requests"] == 0
        assert stats["request_bytes"] > 0 and stats["response_bytes"] > 0
        assert stats["token_count_unit"] == "utf8_bytes"
    finally:
        model.close()


def test_ollama_never_silently_truncates_or_pulls_models(tmp_path):
    calls = []

    def handle(request):
        assert request.url.path == "/api/embed"
        data = json.loads(request.content)
        calls.append(data)
        assert data["truncate"] is False
        assert data["keep_alive"] == "0s"
        assert data["options"] == {"num_thread": 2, "num_ctx": 4096}
        assert "encoding_format" not in data and "dimensions" not in data
        return httpx.Response(200, json={"model": "test-model", "embeddings": [[0, 2]]})

    model = HttpEmbedder(
        profile(
            protocol="ollama",
            endpoint="http://localhost:11434/api/embed",
            keep_alive_seconds=0,
        ),
        tmp_path,
        transport=httpx.MockTransport(handle),
    )
    try:
        model.prepare()
        assert calls == []
        assert model.query("hello") == [0.0, 1.0]
    finally:
        model.close()


@pytest.mark.parametrize(
    "result",
    [
        {"model": "changed-model", "data": [{"index": 0, "embedding": [1, 2]}]},
        {"model": "test-model", "data": []},
        {"model": "test-model", "data": [{"index": True, "embedding": [1, 2]}]},
        {"model": "test-model", "data": [{"index": -1, "embedding": [1, 2]}]},
        {"model": "test-model", "data": [{"index": 0, "embedding": [1]}]},
        {"model": "test-model", "data": [{"index": 0, "embedding": [True, 1]}]},
        {"model": "test-model", "data": [{"index": 0, "embedding": ["1", 2]}]},
        {"model": "test-model", "data": [{"index": 0, "embedding": [0, 0]}]},
        [],
    ],
)
def test_bad_vectors_or_model_identity_never_enter_the_index(tmp_path, result):
    model = HttpEmbedder(
        profile(),
        tmp_path,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=result)),
    )
    try:
        with pytest.raises(ProviderUnavailable):
            model.query("private document")
        assert model._inference_gate.snapshot()["active"] == 0
        assert model.snapshot()["failed_requests"] == 1
    finally:
        model.close()


@pytest.mark.parametrize(
    "body",
    [
        b'{"model":"test-model","data":[{"index":0,"embedding":[NaN,1]}]}',
        b'{"model":"test-model","data":[{"index":0,"embedding":[1e999,1]}]}',
        b"not-json private-document provider-key",
    ],
)
def test_nonfinite_values_and_invalid_json_are_redacted(tmp_path, body):
    model = HttpEmbedder(
        profile(),
        tmp_path,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
        ),
    )
    try:
        with pytest.raises(ProviderUnavailable) as caught:
            model.query("private document")
        assert "private" not in str(caught.value) and "provider-key" not in str(caught.value)
    finally:
        model.close()


def test_redirect_cannot_forward_credentials_and_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMION_TEST_EMBED_KEY", "private-fixture-key")
    calls = []

    def handle(request):
        calls.append(request.url.host)
        return httpx.Response(307, headers={"location": "https://unapproved.example/steal"})

    model = HttpEmbedder(
        profile(api_key_env="MNEMION_TEST_EMBED_KEY"),
        tmp_path,
        transport=httpx.MockTransport(handle),
    )
    try:
        with pytest.raises(ProviderUnavailable):
            model.query("private document")
        assert calls == ["127.0.0.1"]
    finally:
        model.close()


def test_whole_document_and_prefixed_queries_validate_before_network(tmp_path):
    calls = []
    model = HttpEmbedder(
        profile(
            chunk_tokens=64,
            overlap_tokens=0,
            max_input_tokens=64,
            max_query_tokens=32,
            document_prefix="long instruction: ",
            query_prefix="query instruction: ",
        ),
        tmp_path,
        transport=httpx.MockTransport(lambda request: calls.append(request)),
    )
    with pytest.raises(ValueError, match="prefixed"):
        model.document("a" * 120)
    with pytest.raises(ServiceError) as caught:
        model.query("a" * 32)
    assert caught.value.code == "query_too_long"
    assert calls == []


@pytest.mark.parametrize(
    "headers,body",
    [
        ({"content-length": "9000", "content-type": "application/json"}, b"{}"),
        ({"content-length": "bogus", "content-type": "application/json"}, b"{}"),
        ({"content-type": "application/json"}, b"x" * 4097),
        ({"content-type": "text/html"}, b"login page"),
        ({"content-type": "application/json", "content-encoding": "gzip"}, b"compressed"),
    ],
)
def test_response_bound_and_content_checks(tmp_path, headers, body):
    model = HttpEmbedder(
        profile(max_response_bytes=4096),
        tmp_path,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=httpx.ByteStream(body), headers=headers)
        ),
    )
    try:
        with pytest.raises(ProviderUnavailable):
            model.query("test")
    finally:
        model.close()


def test_deadline_stops_later_batches(tmp_path, monkeypatch):
    import mnemion.service.http_embeddings as module

    now, calls = [1.0], []
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])

    def handle(request):
        calls.append(1)
        now[0] += 121
        return httpx.Response(200, json=answer(json.loads(request.content)["input"]))

    model = HttpEmbedder(
        profile(chunk_tokens=32, overlap_tokens=0, batch_size=1),
        tmp_path,
        transport=httpx.MockTransport(handle),
    )
    try:
        with pytest.raises(ProviderUnavailable):
            model.document("x" * 100)
        assert len(calls) == 1
    finally:
        model.close()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://server.company/v1/embeddings",
        "https://key@server/v1/embeddings",
        "https://server/v1/embeddings?key=private",
        "https://server/v1/embeddings#key",
        "ftp://server/model",
        "https://server/",
        "https://server:99999/embed",
        "https://server/embed\n",
        "https://server/embed\x00",
    ],
)
def test_unprotected_or_credential_bearing_endpoints_rejected(endpoint):
    with pytest.raises(ValidationError):
        profile(endpoint=endpoint)


def test_generation_identity_distinguishes_vector_spaces_but_not_credentials():
    original = profile()
    credentials = profile(api_key_env="NEW_KEY_REFERENCE", label="New label")
    assert original.generation.id == credentials.generation.id
    assert original.generation.id != profile(query_prefix="new instruction: ").generation.id
    assert (
        original.generation.id != profile(endpoint="https://elsewhere.example/embed").generation.id
    )
    assert original.generation.id != profile(revision="new weights").generation.id
    assert original.generation.id != profile(dimensions=3).generation.id
    assert original.generation.id != profile(send_dimensions=True).generation.id
    assert original.network_egress is False
    assert profile(endpoint="https://server.company/embed").network_egress is True
    dumped = json.dumps(original.generation.configuration)
    assert "127.0.0.1" not in dumped and "api_key_env" not in dumped
    assert (
        DEFAULT_GENERATION.id == "ce98fcc87e3bb78d0dc8976eaa9592e0025a7021bff866515923f40ebb39aea0"
    )


def test_config_errors_never_echo_operator_values(tmp_path):
    path = tmp_path / "models.json"
    path.write_text('{"api_key":"do-not-log-this"}')
    with pytest.raises(ValueError) as caught:
        EmbeddingConfiguration.from_file(path)
    assert "do-not-log" not in str(caught.value)
    with pytest.raises(ValidationError):
        EmbeddingConfiguration(local_profiles=[])
    with pytest.raises(ValidationError):
        EmbeddingConfiguration(remote_profiles=[profile(), profile(id="another-name")])


def test_pinned_file_tokenizer_checks_integrity_and_source_spans(tmp_path, monkeypatch):
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace

    path = tmp_path / "tokenizer.json"
    actual = Tokenizer(WordLevel({"[UNK]": 0, "hello": 1, "world": 2}, unk_token="[UNK]"))
    actual.pre_tokenizer = Whitespace()
    actual.save(str(path))
    monkeypatch.setenv("MNEMION_TEST_TOKENIZER", str(path))
    spec = TokenizerSpec(
        kind="file",
        file_env="MNEMION_TEST_TOKENIZER",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    tokenizer = EmbeddingTokenizer(spec, tmp_path, offline=True)
    source = "  hello world hello world  "
    spans = tokenizer.spans(source, 2, 1)
    assert spans[0][0] == 0 and spans[-1][1] == len(source)
    assert tokenizer.count(source) == 4 and tokenizer.unit == "model_tokens"
    assert all(a[1] >= b[0] for a, b in zip(spans, spans[1:]))
    path.write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        EmbeddingTokenizer(spec, tmp_path).prepare()


@pytest.mark.parametrize("value", [[True, 1], [float("inf"), 1], [0, 0], ["1", 2]])
def test_vector_storage_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        vector_literal(value, 2)


def test_generation_cannot_override_identity_or_dimensions():
    for dimensions in (True, 0, 4097):
        with pytest.raises(ValueError):
            Generation("model", dimensions, {})
    with pytest.raises(ValueError):
        Generation("model", 2, {"model": "different"})
    assert math.isfinite(float(json.loads(vector_literal([0.6, 0.8], 2))[0]))
