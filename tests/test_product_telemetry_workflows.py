"""Owned CLI journeys with real local policy/queues and synthetic API replies."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from mnemion import agent_control, control_cli, control_measurement
from mnemion.product_telemetry import aggregate, catalog, policy, workflow
from mnemion.sdk import Client


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "private choice"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    policy.configure(root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1})
    monkeypatch.setenv("MNEMION_API_KEY", "fixture-only-key")
    monkeypatch.setenv("MNEMION_API_URL", "http://127.0.0.1:7892")
    return root


def cells(root):
    return [
        {**catalog.describe(item["cell"]), "count": item["count"]}
        for item in aggregate.preview(root)
    ]


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
        assert bool(spec.get("fresh_receipt")) == (item["retry"] == "idempotency_key")
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
    assert control_measurement.begin("retrieval.search", {}) is None
