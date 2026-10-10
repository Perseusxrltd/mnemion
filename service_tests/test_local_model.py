"""Opt-in integration with the shipped real model; no quality claims from fakes."""

import os
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from mnemion.service.admin import register_generation
from mnemion.service.embeddings import LocalEmbedder
from mnemion.service.model_catalog import BGE_SMALL_GENERATION
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
