"""Document diversity uses real scoped retrieval and the published adapter format."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import json
import psycopg
import pytest
from pydantic import ValidationError

from mnemion.connectors.protocol import Document
from mnemion.sdk import Client, MnemionError
from mnemion.service.contracts import ContextPack, Recall
from mnemion.service.errors import ServiceError
from mnemion.service.models import (
    ContextInput,
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RecallInput,
    SpaceInput,
    SourceInput,
)
from mnemion.service.retrieval import RetrievalService


def import_document(env, external, *, parts=1, identity=None, space=None, date=None):
    text = "".join(
        f"billing TASK-7312 approved part {part}\n".ljust(48000) for part in range(parts)
    )
    document = Document(
        external_id=external,
        revision="fixture-v1",
        title="Shared title",
        text=text,
        metadata={"source_modified_at": (date or datetime.now(timezone.utc)).isoformat()},
    )
    return [
        env.memory.save(
            identity or env.owner,
            space or env.space,
            item.memory,
            f"source-{uuid4()}",
        )["memory_id"]
        for item in document.items()
    ]


def source_counts(result):
    return Counter(hit["metadata"]["source_external_id"] for hit in result["hits"])


def test_newest_document_cannot_fill_the_candidate_window_before_other_sources(env):
    now = datetime.now(timezone.utc)
    import_document(env, "large-ledger.md", parts=35, date=now)
    for index in range(3):
        import_document(env, f"decision-{index}.md", date=now - timedelta(days=1))
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(
        query="billing", space_ids=[env.space], mode="lexical", sort="recent", limit=4
    )
    legacy = service.recall(env.owner, command.model_copy(update={"max_per_source": 0}))
    assert source_counts(legacy) == {"large-ledger.md": 4}
    result = service.recall(env.owner, command)
    assert source_counts(result) == {
        "large-ledger.md": 1,
        **{f"decision-{index}.md": 1 for index in range(3)},
    }
    assert result["hits"][0]["metadata"]["source_external_id"] == "large-ledger.md"
    assert result["index"]["eligible_records"] == 38
    Recall.model_validate(result)


@pytest.mark.parametrize("mode", ["lexical", "hybrid", "semantic"])
@pytest.mark.parametrize("query", ["billing", "TASK-7312 billing"])
def test_limits_and_context_keep_distinct_documents_with_the_same_title(env, mode, query):
    import_document(env, "ledger.md", parts=3)
    import_document(env, "decisions.md")
    import_document(env, "handbook.md")
    while env.worker.run_once():
        pass
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query=query, space_ids=[env.space], mode=mode, limit=10)
    for maximum, expected in ((1, 3), (2, 4), (0, 5)):
        result = service.recall(env.owner, command.model_copy(update={"max_per_source": maximum}))
        assert len(result["hits"]) == expected
        assert source_counts(result)["ledger.md"] == (maximum or 3)
        assert result["source_grouping"]["max_per_source"] == maximum
        assert result["source_grouping"]["grouped_candidates"] == 5 - expected
    context = service.context(env.owner, ContextInput(**command.model_dump(), token_budget=16000))
    assert len(context["citations"]) == 3
    assert context["source_grouping"]["max_per_source"] == 1
    ContextPack.model_validate(context)


def test_groups_do_not_cross_spaces_authors_or_unlinked_memories(env):
    second = UUID(env.identities.create_space(env.owner, SpaceInput(name="Second"))["id"])
    principal = UUID(
        env.identities.create_principal(
            env.owner, PrincipalInput(name="Another author", kind="application")
        )["id"]
    )
    env.identities.grant(env.owner, env.space, principal, GrantInput(role="contributor"))
    key = env.identities.create_key(env.owner, principal, KeyInput(name="Source author"))
    other = env.db.authenticate(key["api_key"])
    expected = {
        import_document(env, "same-path.md")[0],
        import_document(env, "same-path.md", space=second)[0],
        import_document(env, "same-path.md", identity=other)[0],
    }
    for index in range(2):
        expected.add(
            env.memory.save(
                env.owner,
                env.space,
                MemoryInput(
                    content="billing TASK-7312",
                    subject="Shared title",
                    metadata={"source_external_id": "same-path.md"},
                ),
                f"unlinked-{index}",
            )["memory_id"]
        )
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="billing", all_accessible=True, mode="lexical")
    assert {hit["memory_id"] for hit in service.recall(env.owner, command)["hits"]} == expected
    env.identities.revoke_grant(env.owner, second, env.owner.principal_id)
    current = service.recall(env.owner, command)
    assert len(current["hits"]) == 4
    assert all(hit["space_id"] != str(second) for hit in current["hits"])


def test_threshold_rejection_does_not_consume_a_document_slot(env):
    imported = import_document(env, "ledger.md", parts=2)
    while env.worker.run_once():
        pass
    # Force one real indexed part below the requested similarity floor. The
    # other part remains eligible through the ordinary vector query.
    with psycopg.connect(env.admin_dsn) as connection:
        changed = connection.execute(
            """UPDATE mnemion.embeddings SET embedding='[0,0,1,0]'::vector
               WHERE revision_id=(SELECT current_revision_id FROM mnemion.memories WHERE id=%s)""",
            (UUID(imported[0]),),
        )
        assert changed.rowcount == 1
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(query="billing", space_ids=[env.space], mode="semantic", min_similarity=0.8),
    )
    assert [hit["memory_id"] for hit in result["hits"]] == [imported[1]]
    assert result["source_grouping"]["grouped_candidates"] == 0
    assert result["filtered_candidates"] == 1


def test_evaluations_preserve_and_compare_document_limits(env):
    from mnemion.service.evaluation_models import DatasetInput, EvaluationInput
    from mnemion.service.evaluation_runner import EvaluationRunner
    from mnemion.service.evaluations import EvaluationService

    imported = import_document(env, "ledger.md", parts=2)
    while env.worker.run_once():
        pass
    service = EvaluationService(env.db, env.embedder)
    dataset = service.create_dataset(
        env.owner,
        env.space,
        DatasetInput(
            name="Source-part coverage",
            cases=[
                {
                    "id": "both-parts",
                    "query": "billing",
                    "references": [{"memory_id": memory} for memory in imported],
                }
            ],
        ),
    )
    runs = []
    for maximum in (1, 0):
        run = service.create_run(
            env.owner,
            env.space,
            EvaluationInput(
                dataset_id=UUID(dataset["id"]),
                modes=["lexical"],
                cutoffs=[2],
                max_per_source=maximum,
            ),
            f"document-eval-{maximum}",
        )
        assert EvaluationRunner(env.db, RetrievalService(env.db, env.embedder)).run_once()
        run = service.run(env.owner, env.space, UUID(run["id"]))
        assert run["state"] == "completed"
        assert run["configuration"]["max_per_source"] == maximum
        assert run["manifest"]["configuration"]["max_per_source"] == maximum
        result = service.results(env.owner, env.space, UUID(run["id"]))["items"][0]["result"]
        assert result["source_grouping"]["max_per_source"] == maximum
        assert result["metrics"]["2"]["recall"] == (0.5 if maximum else 1)
        assert result["context_recall"] == (0.5 if maximum else 1)
        runs.append(run)
    comparison = service.compare(env.owner, env.space, UUID(runs[0]["id"]), UUID(runs[1]["id"]))
    assert comparison["comparable"]
    assert next(row for row in comparison["deltas"] if row["metric"] == "recall")["delta"] == 0.5


@pytest.mark.parametrize("derived", [False, True])
def test_evaluation_verifies_narrowed_unicode_evidence_without_accepting_forged_spans(env, derived):
    from mnemion.service.evaluation_runner import EvaluationRunner

    prefix, suffix = "Outside the cited range. ", " Outside the cited range."
    quoted = "Préparation Ω. " * 400 + "billing accepted ⚙. " + "Historical notes. " * 400
    source = prefix + quoted + suffix
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="The billing decision was accepted." if derived else quoted,
            source=SourceInput(content=source, start=len(prefix), end=len(prefix) + len(quoted)),
        ),
        "unicode-evaluation-source",
    )
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="billing", space_ids=[env.space], mode="lexical")
    result = service.recall(env.owner, command)
    context = service.context(env.owner, ContextInput(**command.model_dump(), token_budget=16000))
    hit = result["hits"][0]
    assert (
        len(prefix) < hit["evidence"]["start"] < hit["evidence"]["end"] < len(source) - len(suffix)
    )
    assert source[hit["evidence"]["start"] : hit["evidence"]["end"]] == hit["evidence"]["excerpt"]
    runner = EvaluationRunner(env.db, service)
    assert runner._verify(env.owner, env.space, result["hits"], context["citations"]) == 2
    for field, value in (
        ("excerpt", "Invented source text"),
        ("start", len(prefix) - 1),
        ("end", len(source)),
        ("content_hash", "0" * 64),
    ):
        changed = deepcopy(hit)
        changed["evidence"][field] = value
        with pytest.raises(ServiceError, match="source hash or Unicode citation span"):
            runner._verify(env.owner, env.space, [changed], [])
    citation = deepcopy(context["citations"][0])
    citation["source_start"] = 0
    with pytest.raises(ServiceError, match="source hash or Unicode citation span"):
        runner._verify(env.owner, env.space, [], [citation])
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            "UPDATE mnemion.source_revisions SET content_hash=%s WHERE id=%s",
            ("0" * 64, UUID(hit["evidence"]["source_revision_id"])),
        )
    with pytest.raises(ServiceError, match="source hash or Unicode citation span"):
        runner._verify(env.owner, env.space, [], context["citations"])


@pytest.mark.parametrize("value", [-1, 51, True, 1.5, "1", None])
def test_document_limit_is_a_bounded_integer(value):
    with pytest.raises(ValidationError):
        RecallInput(query="billing", all_accessible=True, max_per_source=value)


@pytest.mark.parametrize("method", ["search", "context"])
def test_sdk_sends_the_document_limit_only_when_explicitly_requested(method):
    bodies = []

    def unavailable(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            422, json={"error": {"code": "fixture_rejected", "message": "Rejected"}}
        )

    with Client(
        "https://example.invalid", "fixture-key", transport=httpx.MockTransport(unavailable)
    ) as client:
        for options in ({}, {"max_per_source": 0}, {"max_per_source": 2}):
            with pytest.raises(MnemionError):
                getattr(client, method)("billing", all_accessible=True, **options)
    assert "max_per_source" not in bodies[0]
    assert bodies[1]["max_per_source"] == 0
    assert bodies[2]["max_per_source"] == 2
