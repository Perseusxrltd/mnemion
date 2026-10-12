"""Opt-in integration with the shipped real model; no quality claims from fakes."""

import os
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from mnemion.service.admin import register_generation
from mnemion.service.embeddings import DEFAULT_GENERATION, LocalEmbedder
from mnemion.service.model_catalog import BGE_SMALL_GENERATION
from mnemion.service.model_registry import ModelRegistry
from mnemion.service.memory import MemoryService
from mnemion.service.models import MemoryInput, RecallInput
from mnemion.service.retrieval import RetrievalService
from mnemion.service.worker import Worker

pytestmark = pytest.mark.skipif(
    os.environ.get("MNEMION_TEST_LOCAL_MODEL") != "1",
    reason="Set MNEMION_TEST_LOCAL_MODEL=1 to run the pinned ONNX integration",
)


def assert_shared_tokenizer_preserves_pinned_source_semantics(model):
    import json

    from tokenizers import Tokenizer

    model.prepare()
    raw = Tokenizer.from_file(str(model._model.model._model_dir / "tokenizer.json"))
    original = json.loads(raw.to_str())
    shared = json.loads(model._model.model.tokenizer.to_str())
    for settings in (original, shared):
        settings.pop("padding", None)
        settings.pop("truncation", None)
    assert original == shared
    raw.no_truncation()
    raw.no_padding()
    for text in (
        "Le café coûte cinq euros. PostgreSQL stores invoices. 中文笔记。",
        "<s><mask></s><pad>[CLS][MASK][SEP]",
        "Long document with source spans and no silent truncation. " * 180,
    ):
        expected = raw.encode(text, add_special_tokens=False)
        actual = model._tokenizer.encode(text, add_special_tokens=False)
        assert actual.ids == expected.ids
        assert actual.offsets == expected.offsets
        assert model.token_count(text) == len(expected.ids)


def test_real_multilingual_retrieval_and_long_document_chunks(env):
    model = LocalEmbedder(Path(os.environ["MNEMION_MODEL_CACHE"]))
    assert_shared_tokenizer_preserves_pinned_source_semantics(model)
    with psycopg.connect(env.admin_dsn) as conn:
        register_generation(conn, model.generation)
    memories = MemoryService(env.db, model.generation)
    relevant = memories.save(
        env.owner,
        env.space,
        MemoryInput(
            content="Le service de facturation utilise PostgreSQL et conserve ses sauvegardes pendant trente jours."
        ),
        "french",
    )
    memories.save(
        env.owner,
        env.space,
        MemoryInput(content="The office bicycle rack is beside the garden."),
        "english-distractor",
    )
    worker = Worker(env.worker_db, model)
    while worker.run_once():
        pass
    result = RetrievalService(env.db, model).recall(
        env.owner,
        RecallInput(
            query="What database does the billing service use?",
            space_ids=[env.space],
            mode="semantic",
        ),
    )
    assert result["index"]["indexed_records"] == 2
    assert result["hits"][0]["memory_id"] == relevant["memory_id"]
    assert (
        result["hits"][0]["ranking"]["cosine_similarity"]
        > result["hits"][1]["ranking"]["cosine_similarity"]
    )
    long_text = "La tasse est sur le bureau. " * 150 + "La rétention légale est de trente jours."
    chunks = model.document(long_text)
    assert len(chunks) > 1 and chunks[0].start == 0 and chunks[-1].end == len(long_text)
    assert all(len(chunk.vector) == 384 for chunk in chunks)
    assert "trente jours" in long_text[chunks[-1].start : chunks[-1].end]
    assert model.token_count(long_text) > 512
    assert memories.fetch(env.owner, UUID(relevant["memory_id"]))["content"].startswith(
        "Le service"
    )


def test_real_small_english_cpu_model_and_source_spans():
    import math

    model = LocalEmbedder(Path(os.environ["MNEMION_MODEL_CACHE"]), generation=BGE_SMALL_GENERATION)
    assert_shared_tokenizer_preserves_pinned_source_semantics(model)
    query = model.query("Which database stores billing records?")
    relevant = model.document("Billing records are stored in PostgreSQL with daily backups.")[0]
    unrelated = model.document("The office garden has roses beside the bicycle rack.")[0]
    assert sum(a * b for a, b in zip(query, relevant.vector)) > sum(
        a * b for a, b in zip(query, unrelated.vector)
    )
    assert len(query) == 384 and math.isclose(math.hypot(*query), 1.0, rel_tol=1e-5)
    source = "PostgreSQL billing backups protect customer invoices. " * 180
    chunks = model.document(source)
    assert len(chunks) > 1 and chunks[0].start == 0 and chunks[-1].end == len(source)
    assert all(a.end >= b.start for a, b in zip(chunks, chunks[1:]))


@pytest.mark.parametrize(
    "profile,generation", [("e5-small", DEFAULT_GENERATION), ("bge-small", BGE_SMALL_GENERATION)]
)
def test_real_idle_cleanup_and_reload_preserve_vectors_and_source_spans(profile, generation):
    import json
    import platform
    import time
    from datetime import datetime, timezone

    import psutil

    model = LocalEmbedder(Path(os.environ["MNEMION_MODEL_CACHE"]), generation=generation)
    models = ModelRegistry(model, {profile: model}, idle_seconds=10)
    process = psutil.Process()
    query = "Which database stores the team's billing records?"
    source = "PostgreSQL stores billing records. Le café coûte cinq euros. 中文笔记。"
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.system(),
        "architecture": platform.machine(),
        "profile": profile,
        "generation_id": generation.id,
        "scope": "Current test process; excludes separate workers and database processes",
        "idle_seconds": 10,
        "rss_before_model_bytes": process.memory_info().rss,
    }
    try:
        original_query = model.query(query)
        original_chunks = model.document(source)
        report["rss_loaded_bytes"] = process.memory_info().rss
        models.start_idle_cleanup()
        deadline = time.monotonic() + 30
        while models.cache_status()["idle_model_evictions"] == 0 and time.monotonic() < deadline:
            time.sleep(0.1)
        assert models.cache_status()["idle_model_evictions"] == 1
        assert model._model is None and model._tokenizer is None
        report["rss_after_idle_bytes"] = process.memory_info().rss
        assert model.generation.id == generation.id

        # Network-free reload proves that the approved on-disk model survived.
        model.offline = True
        started = time.monotonic()
        assert model.query(query) == pytest.approx(original_query, abs=1e-6)
        report["reload_query_ms"] = round((time.monotonic() - started) * 1000, 2)
        reloaded_chunks = model.document(source)
        assert [(c.start, c.end) for c in reloaded_chunks] == [
            (c.start, c.end) for c in original_chunks
        ]
        for original, reloaded in zip(original_chunks, reloaded_chunks, strict=True):
            assert reloaded.vector == pytest.approx(original.vector, abs=1e-6)
        report["rss_reloaded_bytes"] = process.memory_info().rss
        report["background_eviction_and_offline_reload_verified"] = True
    finally:
        models.close()
    assert not models.cache_status()["idle_cleanup_running"]
    report["monitor_stopped"] = True
    directory = os.environ.get("MNEMION_TEST_MODEL_REPORT_DIR")
    if directory:
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{profile}.json").write_text(json.dumps(report, indent=2) + "\n")
