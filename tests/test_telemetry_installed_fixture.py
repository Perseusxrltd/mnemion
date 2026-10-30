"""The diagnostic bake refuses every destination that is not the loopback fixture."""

import json
from pathlib import Path

import pytest

from deploy.telemetry_installed_fixture import baked_documents, validate_loopback_target


DISCLOSURE = {
    "version": 2,
    "collection_available": False,
    "destination": None,
}
ROUTE = {"version": 2, "address": None, "certificate_authorities": []}
CERTIFICATE = "-----BEGIN CERTIFICATE-----\nQUJD\n-----END CERTIFICATE-----\n"


def test_loopback_bake_changes_only_availability_and_route():
    disclosure, route = baked_documents(
        DISCLOSURE, ROUTE, "https://localhost:8443/v3/report", "127.0.0.1", CERTIFICATE
    )
    assert disclosure["collection_available"] is True
    assert disclosure["destination"] == "https://localhost:8443/v3/report"
    assert disclosure["version"] == 2
    assert route == {
        "version": 2,
        "address": "127.0.0.1",
        "certificate_authorities": [CERTIFICATE],
    }


@pytest.mark.parametrize(
    "destination,address",
    [
        ("https://example.com/v3/report", "127.0.0.1"),
        ("https://127.0.0.1:8443/v3/report", "127.0.0.1"),
        ("http://localhost:8443/v3/report", "127.0.0.1"),
        ("https://localhost/v3/report", "127.0.0.1"),
        ("https://localhost:8443/v1/report", "127.0.0.1"),
        ("https://user:pass@localhost:8443/v3/report", "127.0.0.1"),
        ("https://localhost:8443/v3/report?x=1", "127.0.0.1"),
        ("https://localhost:8443/v3/report", "8.8.8.8"),
        ("https://localhost:8443/v3/report", "::1"),
    ],
)
def test_non_loopback_targets_fail_closed(destination, address):
    with pytest.raises(ValueError):
        validate_loopback_target(destination, address, CERTIFICATE)


def test_active_production_disclosure_is_refused(tmp_path: Path):
    copy = tmp_path / "copy"
    target = copy / "mnemion/product_telemetry"
    target.mkdir(parents=True)
    (target / "disclosure.json").write_text(json.dumps({**DISCLOSURE, "collection_available": True}), encoding="utf-8")
    (target / "transport-route.json").write_text(json.dumps(ROUTE), encoding="utf-8")
    package = copy / "studio/electron"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"main": "dist/main.js", "scripts": {"dist": "electron-builder --publish never"}}),
        encoding="utf-8",
    )
    from deploy.telemetry_installed_fixture import write_bake

    with pytest.raises(ValueError, match="Production disclosure"):
        write_bake(copy, "https://localhost:8443/v3/report", "127.0.0.1", CERTIFICATE)
