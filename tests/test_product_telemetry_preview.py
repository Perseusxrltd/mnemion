"""Offline format inspection never reserves a report or changes private state."""

import base64
import json
from pathlib import Path
import socket

import pytest

from mnemion.product_telemetry import aggregate, cli, delivery, endpoint, policy, wire, wire_v3
from tests import test_product_telemetry_transport as tls_fixtures


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    return tls_fixtures.certificates.__wrapped__(tmp_path_factory)


@pytest.fixture(autouse=True)
def released_trust(monkeypatch, certificates):
    monkeypatch.setattr(
        endpoint,
        "release_certificate_authorities",
        lambda: certificates[1].telemetry_test_authorities,
    )


@pytest.mark.parametrize(
    "condition", ["new", "enabled", "disabled", "restricted", "damaged", "in_flight", "cooldown"]
)
def test_format_preview_is_synthetic_and_read_only(tmp_path, monkeypatch, condition):
    root, company = tmp_path / "private", tmp_path / "company.json"
    monkeypatch.setattr(policy, "company_policy_file", lambda: company)
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v3/report")
    monkeypatch.setattr(endpoint, "release_address", lambda: "127.0.0.1")
    report = None
    budget = delivery.DeliveryBudget(root)
    if condition != "new":
        current = policy.configure(
            root,
            {
                "enabled": True,
                "expected_revision": 0,
                "disclosure_version": policy.DISCLOSURE_VERSION,
            },
        )
        assert aggregate.record(
            root,
            {"kind": "submission", "workflow": "memory.recall", "surface": "native_agent"},
            expected_revision=current["revision"],
            expected_generation=current["store_generation"],
        )
        if condition == "disabled":
            policy.configure(root, {"enabled": False, "expected_revision": 0})
        elif condition == "restricted":
            company.write_text('{"schema_version":1,"enabled":false,"metric_groups":[]}')
        elif condition == "damaged":
            (root / policy.DATABASE_NAME).write_bytes(b"PRIVATE_SENTINEL")
        elif condition in {"in_flight", "cooldown"}:
            report = budget.reserve(
                expected_revision=current["revision"],
                expected_generation=current["store_generation"],
                network="unmetered",
                constrained=False,
            )
            assert report is not None
            if condition == "cooldown":
                budget.cancel(report)

    def forbidden(*args, **kwargs):
        pytest.fail("A read-only format preview attempted collection, randomness or networking")

    monkeypatch.setattr(wire, "prepare", forbidden)
    monkeypatch.setattr(wire_v3, "prepare", forbidden)
    monkeypatch.setattr(delivery, "prepare_summary", forbidden)
    monkeypatch.setattr(delivery.DeliveryBudget, "reserve", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }
    previous_packet = report.preview() if report else None
    value = cli.execute(root, {"action": "preview"})
    again = cli.execute(root, {"action": "preview"})
    assert value == again
    assert value["outbound_state"] == "not_inspected"
    assert value["outbound_body"] is None and value["outbound_bytes"] == 0
    example = value["illustrative_packet"]
    packet = base64.b64decode(example["body_base64"], validate=True)
    assert example == wire_v3.format_example()
    assert example["kind"] == "synthetic_example" and example["body_encoding"] == "base64"
    assert len(packet) == example["body_bytes"] == 25 and packet[0] == 3
    assert example["view"] == "bounded_summary"
    assert example["randomized_sign"] is None
    assert example["aggregation"] == "bounded_summary_publication_noise"
    assert "not unique people" in example["protected_unit"]
    assert "locally randomized" not in json.dumps(example)
    assert "PRIVATE_SENTINEL" not in json.dumps(value)
    assert value["transport_available"] is True
    assert value["status"]["delivery_budget"]["transport_available"] is True
    assert cli.execute(root, {"action": "schema"})["transport_available"] is True
    coverage = value["workflow_coverage"]
    assert coverage == cli.execute(root, {"action": "schema"})["workflow_coverage"]
    source = (
        Path(__file__).resolve().parents[1] / "mnemion/product_telemetry/workflow-coverage.json"
    )
    assert coverage == json.loads(source.read_text())
    if condition != "enabled":
        assert value["local_aggregates"] == []
    if condition in {"in_flight", "cooldown"}:
        assert value["status"]["delivery_budget"]["state"] == condition
        assert report.preview() == previous_packet
    assert before == {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }
    if condition == "new":
        assert not root.exists()
    if condition == "in_flight":
        budget.cancel(report)


@pytest.mark.parametrize(
    "destination,address,available,expected",
    [
        ("https://example.invalid/v3/report", "127.0.0.1", True, True),
        ("https://example.invalid/v3/report", "::1", True, True),
        ("https://example.invalid/v3/report", None, True, False),
        ("https://example.invalid/v3/report", "hostname.invalid", True, False),
        ("https://example.invalid/v3/report", "127.0.0.1", False, False),
        ("http://example.invalid/v3/report", "127.0.0.1", True, False),
        ("https://secret@example.invalid/v3/report", "127.0.0.1", True, False),
        ("https://example.invalid/v1/report", "127.0.0.1", True, False),
        ("https://example.invalid/other", "127.0.0.1", True, False),
    ],
)
def test_status_schema_and_preview_share_release_route_capability(
    tmp_path, monkeypatch, destination, address, available, expected
):
    root = tmp_path / "absent"
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", available)
    monkeypatch.setattr(policy, "COLLECTOR_URL", destination)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "absent-policy")
    monkeypatch.setattr(endpoint, "release_address", lambda: address)
    assert policy.status(root)["delivery_budget"]["transport_available"] is expected
    assert cli.execute(root, {"action": "schema"})["transport_available"] is expected
    assert policy.preview(root)["transport_available"] is expected
    assert not root.exists()
