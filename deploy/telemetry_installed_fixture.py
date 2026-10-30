"""Loopback-only disclosure staging for one unpublished diagnostic package.

Production disclosure and route files stay false/null/null with empty CA roots.
This module checks that fence and writes the fixture only into a copied tree.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


DISCLOSURE = Path("mnemion/product_telemetry/disclosure.json")
ROUTE = Path("mnemion/product_telemetry/transport-route.json")
BAKED = (DISCLOSURE, ROUTE)
UPDATE_FEEDS = ("latest*.yml", "latest*.yaml", "latest*.xml", "latest*-windows.json", "*.blockmap")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def assert_production_inactive(disclosure: dict, route: dict) -> None:
    if disclosure.get("collection_available") is not False or disclosure.get("destination") is not None:
        raise ValueError("Production disclosure is not inactive")
    if route.get("version") != 2 or route.get("address") is not None or route.get("certificate_authorities") != []:
        raise ValueError("Production route is not inactive")


def validate_loopback_target(destination: str, address: str, certificate: str) -> None:
    parsed = urlsplit(destination)
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or host != "localhost"
        or parsed.path != "/v3/report"
        or parsed.port is None
        or not 1 <= parsed.port <= 65535
        or destination != f"https://localhost:{parsed.port}/v3/report"
    ):
        raise ValueError("Telemetry fixture destination must be loopback HTTPS /v3/report")
    if address != "127.0.0.1":
        raise ValueError("Telemetry fixture route must bind the IPv4 loopback address")
    lines = certificate.replace("\r\n", "\n").replace("\n", "\n")
    body = lines[:-1] if lines.endswith("\n") else lines
    rows = body.split("\n")
    if (
        len(certificate) > 4096
        or len(rows) < 3
        or rows[0] != "-----BEGIN CERTIFICATE-----"
        or rows[-1] != "-----END CERTIFICATE-----"
        or any(not row or len(row) > 64 for row in rows[1:-1])
    ):
        raise ValueError("Telemetry fixture requires one public test certificate")


def baked_documents(disclosure: dict, route: dict, destination: str, address: str, certificate: str) -> tuple[dict, dict]:
    assert_production_inactive(disclosure, route)
    validate_loopback_target(destination, address, certificate)
    updated = dict(disclosure)
    updated["collection_available"] = True
    updated["destination"] = destination
    baked_route = {"version": 2, "address": address, "certificate_authorities": [certificate]}
    return updated, baked_route


def write_bake(copy: Path, destination: str, address: str, certificate: str) -> dict:
    original_disclosure = (copy / DISCLOSURE).read_bytes()
    original_route = (copy / ROUTE).read_bytes()
    baked_disclosure, baked_route = baked_documents(
        json.loads(original_disclosure), json.loads(original_route), destination, address, certificate
    )
    disclosure_bytes = (json.dumps(baked_disclosure, indent=2) + "\n").encode()
    route_bytes = (json.dumps(baked_route, indent=2) + "\n").encode()
    (copy / DISCLOSURE).write_bytes(disclosure_bytes)
    (copy / ROUTE).write_bytes(route_bytes)
    package = json.loads((copy / "studio/electron/package.json").read_text(encoding="utf-8"))
    if package.get("main") != "dist/main.js" or "--publish never" not in package["scripts"]["dist"]:
        raise ValueError("Refusing a diagnostic package that changes the app entry or publish script")
    return {
        "baked_files": [path.as_posix() for path in BAKED],
        "production_disclosure_sha256": _sha256(original_disclosure),
        "production_route_sha256": _sha256(original_route),
        "diagnostic_disclosure_sha256": _sha256(disclosure_bytes),
        "diagnostic_route_sha256": _sha256(route_bytes),
        "destination_host": "localhost",
        "destination_path": "/v3/report",
        "route_address": "127.0.0.1",
        "diagnostic_collection_available": True,
        "production_collection_available": False,
        "packaged_main": "dist/main.js",
        "excluded_from_publication": True,
        "update_feed_globs": list(UPDATE_FEEDS),
    }
