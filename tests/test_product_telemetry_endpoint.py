"""Release trust is bounded and separate from user/ambient certificate stores."""

import json

import pytest

from mnemion.product_telemetry import endpoint, policy
from tests import test_product_telemetry_transport as tls_fixtures


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    return tls_fixtures.certificates.__wrapped__(tmp_path_factory)


@pytest.fixture
def route_file(tmp_path, monkeypatch):
    monkeypatch.setattr(endpoint, "__file__", str(tmp_path / "endpoint.py"))
    endpoint._release_route.cache_clear()
    yield tmp_path / "transport-route.json"
    endpoint._release_route.cache_clear()


def test_release_route_freezes_only_its_reviewed_authorities(route_file, certificates, monkeypatch):
    certificate = certificates[0].read_text()
    route_file.write_text(
        json.dumps({"version": 2, "address": "127.0.0.1", "certificate_authorities": [certificate]})
    )
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v1/report")
    selected = endpoint.release_endpoint()
    assert selected is not None and selected.validate()
    assert selected.certificate_authorities == (certificate,)
    # This immutable package file is read once, unlike current user consent.
    route_file.unlink()
    assert endpoint.release_endpoint() == selected
    original = [certificate]
    copied = endpoint.Endpoint(selected.host, selected.address, certificate_authorities=original)
    original.clear()
    assert copied.validate() and copied.certificate_authorities == (certificate,)


@pytest.mark.parametrize(
    "kind",
    [
        "legacy",
        "missing",
        "empty",
        "duplicate",
        "excessive",
        "extra",
        "wrong_version",
        "oversized",
        "bundled",
        "invalid_base64",
        "unicode",
    ],
)
def test_unqualified_release_trust_is_unavailable(route_file, certificates, monkeypatch, kind):
    certificate = certificates[0].read_text()
    value = {"version": 2, "address": "127.0.0.1", "certificate_authorities": [certificate]}
    if kind == "legacy":
        value = {"version": 1, "address": "127.0.0.1"}
    elif kind == "missing":
        value.pop("certificate_authorities")
    elif kind == "empty":
        value["certificate_authorities"] = []
    elif kind in {"duplicate", "excessive"}:
        value["certificate_authorities"] *= 2 if kind == "duplicate" else 3
    elif kind == "extra":
        value["ambient_fallback"] = True
    elif kind == "wrong_version":
        value["version"] = True
    elif kind == "oversized":
        value["certificate_authorities"] = ["x" * 16385]
    elif kind == "bundled":
        value["certificate_authorities"] = [certificate + certificate]
    elif kind == "invalid_base64":
        value["certificate_authorities"] = [
            "-----BEGIN CERTIFICATE-----\nA===\n-----END CERTIFICATE-----\n"
        ]
    else:
        value["certificate_authorities"] = [certificate.replace("\n", "\u2028")]
    route_file.write_text(json.dumps(value))
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v1/report")
    assert endpoint.release_endpoint() is None
    assert endpoint.release_address() is None and endpoint.release_certificate_authorities() == ()
