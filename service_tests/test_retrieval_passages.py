from uuid import UUID

import pytest

from mnemion.service.embeddings import EmbeddedChunk
from mnemion.service.models import ContextInput, MemoryInput, RecallInput, SourceInput
from mnemion.service.passages import passage_span
from mnemion.service.retrieval import RetrievalService


@pytest.mark.parametrize("mode", ["lexical", "hybrid", "semantic"])
def test_search_shows_matching_passage_near_end_of_large_git_part(env, mode):
    answer = "T-0045 D1 CLOS — relance envoyée, réponse avocate reçue."
    content = "# Earlier rounds\n" + "Archive without the answer.\n" * 1600 + answer
    saved = env.memory.save(env.owner, env.space, MemoryInput(content=content), "matched-git-part")
    while env.worker.run_once():
        pass
    service = RetrievalService(env.db, env.embedder)
    result = service.recall(
        env.owner,
        RecallInput(query="T-0045 D1 relance avocate", space_ids=[env.space], mode=mode),
    )
    hit = result["hits"][0]
    assert hit["memory_id"] == saved["memory_id"]
    assert answer in hit["text"] and answer in hit["evidence"]["excerpt"]
    for snippet, span in (
        (hit["text"], hit["memory_span"]),
        (hit["evidence"]["excerpt"], hit["evidence"]),
    ):
        assert 0 < span["start"] < span["end"] <= len(content)
        assert snippet == content[span["start"] : span["end"]]
        assert len(snippet) <= 4000
    assert hit["text_truncated"] and hit["evidence"]["excerpt_truncated"]
    # Fetch/export keep the complete revision and original citation.
    full = env.memory.fetch(env.owner, UUID(saved["memory_id"]))
    assert full["content"] == content
    assert full["evidence"]["excerpt"] == content
    assert full["evidence"]["start"] == 0 and full["evidence"]["end"] == len(content)


def test_source_passage_uses_original_offsets_not_derived_memory_or_casefold_offsets(env):
    prefix = "Outside cited span: private context.\n"
    cited = "Straße İ 😀 ancien historique.\n" * 1800 + "Réponse avocate : T-0045 CLOS."
    source = prefix + cited + "\nOutside cited span: unrelated conclusion."
    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="The avocate confirmed T-0045 is CLOS.",
            source=SourceInput(content=source, start=len(prefix), end=len(prefix) + len(cited)),
        ),
        "derived-with-source",
    )
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="avocate T-0045 CLOS", space_ids=[env.space], mode="lexical")
    hit = service.recall(env.owner, command)["hits"][0]
    evidence = hit["evidence"]
    assert evidence["start"] > len(prefix)
    assert evidence["end"] <= len(prefix) + len(cited)
    assert evidence["excerpt"] == source[evidence["start"] : evidence["end"]]
    assert "Réponse avocate : T-0045 CLOS." in evidence["excerpt"]
    assert "Outside cited span" not in evidence["excerpt"]
    assert hit["memory_span"]["start"] == 0
    packed = service.context(env.owner, ContextInput(**command.model_dump(), token_budget=4000))
    citation = packed["citations"][0]
    assert citation["memory_id"] == saved["memory_id"]
    assert citation["source_start"] == evidence["start"]
    assert citation["source_end"] == evidence["end"]


def test_passage_prefers_joint_query_coverage_over_first_common_word():
    answer = "avocate T-0045 D1 CLOS"
    content = "avocate\n" + "old unrelated material.\n" * 1000 + answer + "\n" * 200
    start, end = passage_span(content, "avocate T-0045 D1 CLOS")
    assert start > 0
    assert answer in content[start:end]
    assert end - start <= 4000


def test_unicode_folding_cannot_shift_citation_offsets():
    answer = "STRASSE target"
    content = "Straße İ 😀\n" * 1500 + answer + "\n" * 5000
    start, end = passage_span(content, "strasse target")
    assert start <= content.index(answer) < end
    assert answer in content[start:end]
    assert end - start <= 4000


def test_semantic_only_match_keeps_the_selected_embedding_passage(env, monkeypatch):
    while env.worker.run_once():
        pass
    content = "Older context.\n" * 1000 + "The current decision was approved."
    first = len(content) - len("The current decision was approved.")
    monkeypatch.setattr(
        env.embedder,
        "document",
        lambda text: [EmbeddedChunk(first, len(text), env.embedder.query(text))],
    )
    env.memory.save(env.owner, env.space, MemoryInput(content=content), "semantic-passage")
    while env.worker.run_once():
        pass
    hit = RetrievalService(env.db, env.embedder).recall(
        env.owner, RecallInput(query="authorisation", space_ids=[env.space], mode="semantic")
    )["hits"][0]
    assert hit["text"] == "The current decision was approved."
    assert hit["evidence"]["excerpt"] == hit["text"]
    assert hit["evidence"]["start"] == first


def test_a_matched_passage_does_not_expand_the_semantic_chunk_budget(env, monkeypatch):
    while env.worker.run_once():
        pass
    answer = "T-0045 received the avocate response."
    content = "Earlier unrelated context.\n" * 100 + answer
    monkeypatch.setattr(
        env.embedder,
        "document",
        lambda text: [EmbeddedChunk(0, 800, env.embedder.query(text))],
    )
    env.memory.save(env.owner, env.space, MemoryInput(content=content), "bounded-semantic-passage")
    while env.worker.run_once():
        pass
    hit = RetrievalService(env.db, env.embedder).recall(
        env.owner, RecallInput(query="T-0045 avocate", space_ids=[env.space])
    )["hits"][0]
    assert answer in hit["text"]
    assert len(hit["text"]) <= 800
    assert hit["evidence"]["excerpt"] == hit["text"]
