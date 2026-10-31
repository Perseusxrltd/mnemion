"""Owned CLI journeys with real local policy/queues and synthetic API replies."""

import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import httpx
import pytest

from mnemion import agent_control, control_cli, control_measurement
from mnemion.product_telemetry import aggregate, catalog, delivery, policy, workflow
from mnemion.sdk import Client


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "private choice"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    policy.configure(
        root,
        {"enabled": True, "expected_revision": 0, "disclosure_version": policy.DISCLOSURE_VERSION},
    )
    monkeypatch.setenv("MNEMION_API_KEY", "fixture-only-key")
    monkeypatch.setenv("MNEMION_API_URL", "http://127.0.0.1:7892")
    return root


def cells(root):
    return [
        {**catalog.describe(item["cell"]), "count": item["count"]}
        for item in aggregate.preview(root)
    ]


@pytest.mark.parametrize("selected", [False, True])
def test_action_latency_includes_optional_authority_reads(installation, monkeypatch, selected):
    now = [10.0]
    monkeypatch.setattr(workflow.time, "monotonic", lambda: now[0])
    permission = policy._measurement_permission
    full_status = policy.status
    disclosed = policy.disclosure
    budget = delivery.budget_status
    exhausted = aggregate.workflow_exhausted
    avoided = {"status": 0, "disclosure": 0, "budget": 0}

    def contribution_read(*args, **kwargs):
        now[0] += 0.400
        return exhausted(*args, **kwargs)

    def authority_read(*args, **kwargs):
        now[0] += 0.250
        return permission(*args, **kwargs)

    def count_status(*args, **kwargs):
        avoided["status"] += 1
        return full_status(*args, **kwargs)

    def count_disclosure():
        avoided["disclosure"] += 1
        return disclosed()

    def count_budget(*args, **kwargs):
        avoided["budget"] += 1
        return budget(*args, **kwargs)

    monkeypatch.setattr(aggregate, "workflow_exhausted", contribution_read)
    monkeypatch.setattr(policy, "_measurement_permission", authority_read)
    monkeypatch.setattr(policy, "status", count_status)
    monkeypatch.setattr(policy, "disclosure", count_disclosure)
    monkeypatch.setattr(delivery, "budget_status", count_budget)
    active = (
        workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
        if selected
        else workflow.begin("memory.recall", "headless")
    )
    assert active is not None
    now[0] += 0.010
    if selected:
        active.finish_choice("capture.deliver", "success")
    else:
        active.finish("success")
    assert avoided == {"status": 0, "disclosure": 0, "budget": 0}
    rows = cells(installation)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    # The user waited 660 ms. Reporting only the final 10 ms conceals the
    # optional telemetry overhead. Inspect the real persisted aggregate.
    assert next(row["bucket"] for row in rows if row["metric"] == "latency_ms") == 3


@pytest.mark.parametrize("completed", [float("nan"), float("inf"), float("-inf"), 9.0])
def test_invalid_elapsed_clock_cannot_be_reported_as_zero_or_retried(
    installation, monkeypatch, completed
):
    now = [10.0]
    monkeypatch.setattr(workflow.time, "monotonic", lambda: now[0])
    active = workflow.begin("memory.recall", "headless")
    assert active is not None
    now[0] = completed
    active.finish("success")
    now[0] = 20.0
    active.finish("success")
    assert cells(installation) == []


def test_fixed_choices_keep_one_original_clock_and_complete_at_most_once(installation, monkeypatch):
    now = [10.0]
    monkeypatch.setattr(workflow.time, "monotonic", lambda: now[0])
    reads = []
    status_reads = []
    permission = policy._measurement_permission
    full_status = policy.status

    def observed(*args, **kwargs):
        reads.append(True)
        return permission(*args, **kwargs)

    def counted_status(*args, **kwargs):
        status_reads.append(True)
        return full_status(*args, **kwargs)

    monkeypatch.setattr(policy, "_measurement_permission", observed)
    monkeypatch.setattr(policy, "status", counted_status)
    active = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    assert active is not None and len(reads) == 1 and status_reads == []
    now[0] += 0.250
    active.finish_choice("capture.deliver", "success", work_items=0, result_items=3)
    active.finish_choice("capture.collect", "failed")
    active.finish("failed")
    assert len(reads) == 1, "Finishing cannot acquire a new policy snapshot"
    assert status_reads == []
    rows = cells(installation)
    assert {row["workflow"] for row in rows} == {"capture.deliver"}
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert next(row["bucket"] for row in rows if row["metric"] == "latency_ms") == 3


def test_choice_validation_rejects_unknown_or_unbounded_input_before_privacy_io(
    installation, monkeypatch
):
    monkeypatch.setattr(
        policy, "status", lambda *_a, **_k: pytest.fail("Invalid choice read policy")
    )
    monkeypatch.setattr(
        policy,
        "_measurement_permission",
        lambda *_a, **_k: pytest.fail("Invalid choice read policy"),
    )
    for choices in (
        (),
        ("capture.collect",),
        ("capture.collect", "capture.collect"),
        ("capture.collect", "PRIVATE_CHOICE"),
        ("capture.collect", "capture.deliver", "sources.scan", "memory.read", "memory.save"),
        ["capture.collect", "capture.deliver"],
    ):
        assert workflow.begin_choices(choices, "headless") is None
    assert (
        workflow.begin_choices(("capture.collect", "capture.deliver"), ["PRIVATE_SURFACE"]) is None
    )


def test_an_undeclared_choice_cannot_be_retried_under_a_different_workflow(installation):
    active = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    active.finish_choice("memory.save", "success")
    active.finish_choice("capture.deliver", "success")
    assert cells(installation) == []


def test_final_choice_keeps_the_original_opt_out_and_reenable_fence(installation):
    active = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    off = policy.configure(installation, {"enabled": False, "expected_revision": 0})
    policy.configure(
        installation,
        {
            "enabled": True,
            "expected_revision": off["revision"],
            "expected_generation": off["store_generation"],
            "disclosure_version": policy.DISCLOSURE_VERSION,
        },
    )
    active.finish_choice("capture.deliver", "success")
    assert cells(installation) == []
    fresh = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    fresh.finish_choice("capture.deliver", "success")
    assert sum(row["count"] for row in cells(installation) if row["metric"] == "submissions") == 1


def test_collection_saturation_does_not_hide_a_separately_bounded_delivery(installation):
    current = policy.status(installation)
    for _ in range(64):
        assert aggregate.record(
            installation,
            {"kind": "submission", "workflow": "capture.collect", "surface": "headless"},
            expected_revision=current["revision"],
            expected_generation=current["store_generation"],
        )
    blocked = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    assert blocked is not None
    blocked.finish_choice("capture.collect", "success")
    active = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    assert active is not None
    active.finish_choice("capture.deliver", "success")
    submissions = {
        row["workflow"]: row["count"]
        for row in cells(installation)
        if row["metric"] == "submissions"
    }
    assert submissions == {"capture.collect": 64, "capture.deliver": 1}


def cli(monkeypatch, tmp_path, operation, request, handler, *, retries=2):
    input_file = tmp_path / (uuid4().hex + ".json")
    input_file.write_text(json.dumps(request))
    monkeypatch.setattr(
        control_cli,
        "Client",
        lambda url, key, **kw: Client(url, key, transport=httpx.MockTransport(handler), **kw),
    )
    return control_cli.main(
        ["call", operation, "--input", str(input_file), "--retries", str(retries)]
    )


def test_every_control_operation_has_reviewed_owner_mapping_or_visible_exclusion():
    contract = json.loads(Path("mnemion/service/agent_contract.json").read_text())
    origins = control_measurement.ORIGINS
    assert set(origins["operations"]) == {item["name"] for item in contract["operations"]}
    for item in contract["operations"]:
        spec = origins["operations"][item["name"]]
        if "exclusion" in spec:
            assert set(spec) == {"exclusion"}
            assert spec["exclusion"] in origins["exclusions"]
            continue
        names = list(spec["variants"].values()) if "variants" in spec else [spec["workflow"]]
        assert all(name in catalog.WORKFLOW_IDS for name in names)
        assert spec["completion"] in {"success", "accepted"}
        if item["retry"] == "idempotency_key":
            assert spec.get("fresh_receipt") is True
        # Resource-bound capture mutations also publish fresh/replayed metadata
        # without an Idempotency-Key. Their actual HTTP behavior is tested over
        # PostgreSQL; retry policy alone cannot decide receipt availability.
        if "fresh_receipt" in spec:
            assert spec["fresh_receipt"] is True
        if "variants" in spec:
            section, field = spec["selector"]
            schema = item["input_schema"]["properties"][section]
            if "$ref" in schema:
                reference = schema["$ref"].removeprefix("#/").split("/")
                schema = item["input_schema"]
                for part in reference:
                    schema = schema[part]
            schema = schema["properties"][field]
            assert set(spec["variants"]) == set(schema["enum"])


@pytest.mark.parametrize(
    "operation",
    [
        "capture.grant.configure",
        "capture.grant.revoke",
        "capture.policy.change",
        "capture.source.configure",
        "capture.source.revoke",
    ],
)
@pytest.mark.parametrize("disposition", ["new", "replayed", None])
def test_capture_controls_require_the_original_fresh_resource_receipt(
    installation, tmp_path, monkeypatch, capsys, operation, disposition
):
    ids = {
        name: str(uuid4()) for name in ("connector_id", "source_id", "grant_id", "transition_id")
    }
    if operation == "capture.grant.revoke":
        request = {"parameters": {"grant_id": ids["grant_id"]}}
    elif operation == "capture.grant.configure":
        request = {
            "parameters": {name: ids[name] for name in ("source_id", "grant_id")},
            "body": {"device_key_id": str(uuid4())},
        }
    else:
        request = {"parameters": {name: ids[name] for name in ("connector_id", "source_id")}}
        if operation == "capture.source.configure":
            request["body"] = {
                "name": "PRIVATE_SOURCE",
                "namespace": "PRIVATE_NAMESPACE",
                "members": ["PRIVATE_MEMBER"],
                "capture_mode": "messages",
                "keep_accepted": True,
            }
        elif operation == "capture.policy.change":
            request["parameters"]["transition_id"] = ids["transition_id"]
            request["body"] = {
                "expected_version": 1,
                "review_token": "a" * 64,
                "capture_policy": {
                    "format": "mnemion-capture-policy-v1",
                    "preset": "conversation",
                    "capture_mode": "messages",
                    "include": ["PRIVATE_PATH/*.jsonl"],
                    "exclude": [],
                    "retention": "until_deleted",
                    "max_file_bytes": 1000000,
                    "max_record_bytes": 10000,
                },
                "previous_grants": "retain",
                "confirm": True,
            }
    calls = []

    def reply(sent):
        calls.append(sent)
        return httpx.Response(
            200,
            headers={"X-Mnemion-Idempotency": disposition} if disposition else {},
            json={"private": "PRIVATE_RESPONSE"},
        )

    assert cli(monkeypatch, tmp_path, operation, request, reply) == 0
    assert "PRIVATE_RESPONSE" in capsys.readouterr().out
    assert len(calls) == 1
    rows = cells(installation)
    submissions = sum(row["count"] for row in rows if row["metric"] == "submissions")
    assert submissions == (1 if disposition == "new" else 0)
    assert "PRIVATE" not in json.dumps(rows)
    assert b"PRIVATE" not in (installation / policy.DATABASE_NAME).read_bytes()


def test_read_retries_count_one_logical_use_and_never_store_private_values(
    installation, tmp_path, monkeypatch, capsys
):
    calls = []
    monkeypatch.setattr(agent_control.time, "sleep", lambda _: None)

    def reply(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": {"code": "inference_busy"}})
        return httpx.Response(
            200,
            headers={"X-Request-ID": str(uuid4())},
            json={"items": [{"content": "PRIVATE_SENTINEL", "space_id": str(uuid4())}]},
        )

    assert (
        cli(monkeypatch, tmp_path, "retrieval.search", {"body": {"query": "PRIVATE_QUERY"}}, reply)
        == 0
    )
    assert len(calls) == 2
    assert "PRIVATE_SENTINEL" in capsys.readouterr().out
    measured = cells(installation)
    assert sum(c["count"] for c in measured if c["metric"] == "submissions") == 1
    assert [c["bucket"] for c in measured if c["metric"] == "outcomes"] == ["success"]
    assert all(c.get("workflow") == "memory.recall" for c in measured)
    assert "PRIVATE" not in json.dumps(measured)
    assert b"PRIVATE" not in (installation / policy.DATABASE_NAME).read_bytes()


@pytest.mark.parametrize("freshness", ["replayed", None, "untrusted-value"])
def test_cached_or_legacy_write_without_fresh_receipt_is_not_counted(
    installation, tmp_path, monkeypatch, capsys, freshness
):
    def reply(_):
        return httpx.Response(
            202,
            headers={"X-Mnemion-Idempotency": freshness} if freshness else {},
            json={"state": "accepted", "operation_id": str(uuid4())},
        )

    assert (
        cli(
            monkeypatch,
            tmp_path,
            "memories.save",
            {
                "parameters": {"space_id": str(uuid4())},
                "body": {"content": "PRIVATE_MEMORY"},
                "idempotency_key": "PRIVATE_REQUEST_KEY",
            },
            reply,
        )
        == 0
    )
    capsys.readouterr()
    assert cells(installation) == []


def test_new_write_is_only_accepted_and_generic_sdk_is_not_an_owner(
    installation, tmp_path, monkeypatch, capsys
):
    def reply(_):
        return httpx.Response(
            202, headers={"X-Mnemion-Idempotency": "new"}, json={"state": "accepted"}
        )

    request = {
        "parameters": {"space_id": str(uuid4())},
        "body": {"content": "PRIVATE_MEMORY"},
        "idempotency_key": "PRIVATE_REQUEST_KEY",
    }
    with Client(
        "http://mnemion.test", "fixture-key", transport=httpx.MockTransport(reply)
    ) as client:
        agent_control.execute(client, "memories.save", request)
    assert cells(installation) == []
    assert cli(monkeypatch, tmp_path, "memories.save", request, reply) == 0
    capsys.readouterr()
    assert [c["bucket"] for c in cells(installation) if c["metric"] == "outcomes"] == ["accepted"]


def test_opt_out_during_a_request_discards_its_later_completion(
    installation, tmp_path, monkeypatch, capsys
):
    def reply(_):
        policy.configure(installation, {"enabled": False, "expected_revision": 0})
        return httpx.Response(200, json={"items": []})

    assert cli(monkeypatch, tmp_path, "retrieval.search", {"body": {"query": "test"}}, reply) == 0
    capsys.readouterr()
    assert policy.status(installation)["reason"] == "user_disabled"
    assert cells(installation) == []


def test_telemetry_failure_never_changes_cli_success(installation, tmp_path, monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise RuntimeError("private telemetry failure")

    monkeypatch.setattr(aggregate, "record_many", unavailable)
    assert (
        cli(
            monkeypatch,
            tmp_path,
            "retrieval.search",
            {"body": {"query": "test"}},
            lambda _: httpx.Response(200, json={"items": []}),
        )
        == 0
    )
    assert "private telemetry failure" not in capsys.readouterr().out


def test_rejected_read_uses_fixed_failure_category_and_inspection_has_no_use(
    installation, tmp_path, monkeypatch, capsys
):
    assert (
        cli(
            monkeypatch,
            tmp_path,
            "retrieval.search",
            {"body": {"query": "test"}},
            lambda _: httpx.Response(403, json={"error": {"code": "untrusted_private_code"}}),
        )
        == 1
    )
    capsys.readouterr()
    before = cells(installation)
    assert [c["bucket"] for c in before if c["metric"] == "reasons"] == ["authorization"]
    assert [c["bucket"] for c in before if c["metric"] == "outcomes"] == ["denied"]
    assert (
        cli(
            monkeypatch,
            tmp_path,
            "health.live",
            {},
            lambda _: httpx.Response(200, json={"live": True}),
        )
        == 0
    )
    capsys.readouterr()
    assert cells(installation) == before


def test_workflow_discards_invalid_primitives_and_finishes_at_most_once(installation):
    active = workflow.begin("memory.recall", "headless")
    active.finish("success", payload_bytes_received={"content": "PRIVATE"})
    assert cells(installation) == []
    active = workflow.begin("memory.recall", "headless")
    active.finish("success", workflow="memory.save")
    assert cells(installation) == []
    active = workflow.begin("memory.recall", "headless")
    active.finish("success")
    before = cells(installation)
    active.finish("success")
    assert cells(installation) == before


def test_unavailable_build_does_not_read_policy(monkeypatch):
    assert not policy.COLLECTION_AVAILABLE
    monkeypatch.setattr(policy, "status", lambda *_: pytest.fail("unexpected policy read"))
    monkeypatch.setattr(
        policy, "_measurement_permission", lambda *_: pytest.fail("unexpected policy read")
    )
    monkeypatch.setattr(workflow.time, "monotonic", lambda: pytest.fail("unexpected clock read"))
    assert control_measurement.begin("retrieval.search", {}) is None
    assert workflow.begin("memory.recall", "headless") is None
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None


def _avoided_reads(monkeypatch):
    avoided = {"status": 0, "disclosure": 0, "budget": 0}
    full_status = policy.status
    disclosed = policy.disclosure
    budget = delivery.budget_status

    def count_status(*args, **kwargs):
        avoided["status"] += 1
        return full_status(*args, **kwargs)

    def count_disclosure():
        avoided["disclosure"] += 1
        return disclosed()

    def count_budget(*args, **kwargs):
        avoided["budget"] += 1
        return budget(*args, **kwargs)

    monkeypatch.setattr(policy, "status", count_status)
    monkeypatch.setattr(policy, "disclosure", count_disclosure)
    monkeypatch.setattr(delivery, "budget_status", count_budget)
    return avoided


def _pending(root):
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        return connection.execute("SELECT count(*) FROM pending").fetchone()[0]


def test_begin_and_begin_choice_skip_queue_ledger_and_disclosure(installation, monkeypatch):
    statements = []
    original = policy._connect

    def connected(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(policy, "_connect", connected)
    avoided = _avoided_reads(monkeypatch)
    starters = (
        lambda: workflow.begin("memory.recall", "headless"),
        lambda: workflow.begin_choices(("capture.collect", "capture.deliver"), "headless"),
    )
    for starter in starters:
        statements.clear()
        avoided["status"] = avoided["disclosure"] = avoided["budget"] = 0
        active = starter()
        assert active is not None
        text = "\n".join(statements)
        assert "preferences" in text
        assert "pending" not in text
        assert "delivery_" not in text
        assert avoided == {"status": 0, "disclosure": 0, "budget": 0}
        before = len(statements)
        again = starter()
        assert again is not None and len(statements) > before
        assert "pending" not in "\n".join(statements)
        active.discard()
        again.discard()


def test_opt_out_reenable_and_replaced_generation_fence_old_writes(installation, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(aggregate.time, "monotonic", lambda: now[0])
    avoided = _avoided_reads(monkeypatch)
    started = workflow.begin("memory.recall", "headless")
    chosen = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    assert started is not None and chosen is not None and avoided["status"] == 0
    off = policy.configure(installation, {"enabled": False, "expected_revision": 0})
    started.finish("success")
    chosen.finish_choice("capture.deliver", "success")
    assert _pending(installation) == 0
    avoided["status"] = 0
    assert workflow.begin("memory.recall", "headless") is None
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None
    assert avoided["status"] == 0
    opened = {"count": 0}
    original = policy._connect

    def connected(*args, **kwargs):
        opened["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(policy, "_connect", connected)
    assert workflow.begin("memory.recall", "headless") is None
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None
    assert opened["count"] == 0
    policy.configure(
        installation,
        {
            "enabled": True,
            "expected_revision": off["revision"],
            "expected_generation": off["store_generation"],
            "disclosure_version": policy.DISCLOSURE_VERSION,
        },
    )
    opened["count"] = 0
    assert workflow.begin("memory.recall", "headless") is None
    assert opened["count"] == 0
    now[0] = 0.25
    fresh = workflow.begin("memory.recall", "headless")
    fresh_choice = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    assert fresh is not None and fresh_choice is not None and opened["count"] > 0
    started.finish("success")
    chosen.finish_choice("capture.deliver", "success")
    fresh.discard()
    fresh_choice.discard()
    assert _pending(installation) == 0
    held = workflow.begin("memory.recall", "headless")
    held_choice = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    with sqlite3.connect(installation / policy.DATABASE_NAME) as connection:
        connection.execute(
            "UPDATE preferences SET store_generation=? WHERE singleton=1", ("cd" * 16,)
        )
    held.finish("success")
    held_choice.finish_choice("capture.collect", "success")
    assert _pending(installation) == 0
    replaced = workflow.begin("memory.recall", "headless")
    assert replaced is not None
    replaced.finish("success")
    assert sum(row["count"] for row in cells(installation) if row["metric"] == "submissions") == 1


def test_company_denial_observes_opt_out_and_lifts_without_a_cached_grant(
    installation, monkeypatch
):
    company = installation.parent / "company.json"
    restricted = {
        "schema_version": policy.SCHEMA_VERSION,
        "enabled": False,
        "metric_groups": ["usage"],
    }
    company.write_text(json.dumps(restricted))
    opened = {"count": 0}
    original = policy._connect

    def connected(*args, **kwargs):
        opened["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(policy, "_connect", connected)
    assert workflow.begin("memory.recall", "headless") is None
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None
    assert opened["count"] == 2
    company.write_text(json.dumps({**restricted, "enabled": True, "metric_groups": []}))
    assert workflow.begin("memory.recall", "headless") is None
    company.write_text("{")
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None
    assert _pending(installation) == 0
    company.unlink()
    restored = workflow.begin("memory.recall", "headless")
    assert restored is not None
    restored.finish("success")
    assert sum(row["count"] for row in cells(installation) if row["metric"] == "submissions") == 1
    monkeypatch.setattr(aggregate.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(aggregate, "_exhaustion", None)
    policy.configure(installation, {"enabled": False, "expected_revision": 0})
    company.write_text(json.dumps(restricted))
    opened["count"] = 0
    assert workflow.begin("memory.recall", "headless") is None
    assert opened["count"] == 1
    opened["count"] = 0
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None
    assert opened["count"] == 0
    assert policy.status(installation)["reason"] == "user_disabled"


def test_missing_corrupt_and_legacy_stores_suppress_without_repair(
    installation, tmp_path, monkeypatch
):
    absent = tmp_path / "no-store"
    monkeypatch.setattr(policy, "default_directory", lambda: absent)
    assert workflow.begin("memory.recall", "headless") is None
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None
    assert not absent.exists()
    monkeypatch.setattr(policy, "default_directory", lambda: installation)
    path = installation / policy.DATABASE_NAME
    original = path.read_bytes()
    path.write_bytes(b"corrupt-telemetry-store")
    assert workflow.begin("memory.recall", "headless") is None
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None
    assert path.read_bytes() == b"corrupt-telemetry-store"
    assert policy.status(installation)["reason"] == "storage_unavailable"
    path.write_bytes(original)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=2")
    assert policy._measurement_permission(installation)["reason"] == "disclosure_required"
    assert workflow.begin("memory.recall", "headless") is None
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        connection.execute("PRAGMA user_version=6")
        connection.execute("UPDATE preferences SET disclosure_version=1000000")
    assert policy._measurement_permission(installation)["reason"] == "storage_unavailable"
    assert workflow.begin_choices(("capture.collect", "capture.deliver"), "headless") is None
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert (
            connection.execute("SELECT disclosure_version FROM preferences").fetchone()[0]
            == 1000000
        )


def _usage_cells(count):
    cells = []
    for name in catalog.WORKFLOWS:
        for surface in catalog.SURFACES:
            for outcome in catalog.OUTCOMES:
                _, encoded = catalog.observation(
                    {
                        "kind": "outcome",
                        "workflow": name,
                        "surface": surface,
                        "outcome": outcome,
                    }
                )
                cells.append(encoded[0])
                if len(cells) == count:
                    return cells
    raise AssertionError("catalog does not contain enough surviving cells")


def test_oversized_surviving_pending_rows_prevent_a_new_write(installation, monkeypatch):
    path = installation / policy.DATABASE_NAME
    day = aggregate._day()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER pending_bound")
        connection.executemany(
            "INSERT INTO pending VALUES (?, 1, ?)",
            [(cell, day) for cell in _usage_cells(513)],
        )
    assert policy.status(installation)["reason"] == "storage_unavailable"
    assert policy.status(installation)["pending_records"] is None
    avoided = _avoided_reads(monkeypatch)
    assert policy._measurement_permission(installation)["admitted"] is True
    assert avoided == {"status": 0, "disclosure": 0, "budget": 0}
    active = workflow.begin("memory.recall", "headless")
    assert active is not None
    active.finish("success")
    assert avoided == {"status": 0, "disclosure": 0, "budget": 0}
    # Expiry keeps today's usage cells. The surviving bound then rejects the write.
    assert _pending(installation) == 513


def test_damaged_delivery_ledger_saves_a_local_aggregate_and_refuses_delivery(
    installation, monkeypatch
):
    path = installation / policy.DATABASE_NAME
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE delivery_state SET clock_ms=5, next_ms=1 WHERE singleton=1")
    assert policy.status(installation)["reason"] == "storage_unavailable"
    assert policy.status(installation)["effective_enabled"] is False
    avoided = _avoided_reads(monkeypatch)
    stamp = policy._measurement_permission(installation)
    assert stamp["admitted"] is True
    assert avoided == {"status": 0, "disclosure": 0, "budget": 0}
    chosen = workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
    assert chosen is not None
    chosen.finish_choice("capture.deliver", "success")
    assert avoided == {"status": 0, "disclosure": 0, "budget": 0}
    assert _pending(installation) >= 1
    # Full status hides the queue from preview. That is not an empty database.
    assert aggregate.preview(installation) == []
    with sqlite3.connect(path) as connection:
        with pytest.raises(delivery.WireError):
            delivery.budget_status(connection)
    assert (
        delivery.DeliveryBudget(installation).eligible(
            expected_revision=stamp["revision"],
            expected_generation=stamp["store_generation"],
        )
        is False
    )
    assert policy.status(installation)["effective_enabled"] is False
