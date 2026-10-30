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
LOOPBACK_PORT = 48763


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def assert_production_inactive(disclosure: dict, route: dict) -> None:
    if (
        disclosure.get("collection_available") is not False
        or disclosure.get("destination") is not None
    ):
        raise ValueError("Production disclosure is not inactive")
    if (
        route.get("version") != 2
        or route.get("address") is not None
        or route.get("certificate_authorities") != []
    ):
        raise ValueError("Production route is not inactive")


def loopback_destination() -> str:
    return f"https://localhost:{LOOPBACK_PORT}/v3/report"


def assert_public_certificate(certificate: str) -> None:
    if "PRIVATE KEY" in certificate or "BEGIN CERTIFICATE" not in certificate:
        raise ValueError("Telemetry fixture requires one public test certificate")


def validate_loopback_target(destination: str, address: str, certificate: str) -> None:
    assert_public_certificate(certificate)
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


def baked_documents(
    disclosure: dict, route: dict, destination: str, address: str, certificate: str
) -> tuple[dict, dict]:
    assert_production_inactive(disclosure, route)
    validate_loopback_target(destination, address, certificate)
    updated = dict(disclosure)
    updated["collection_available"] = True
    updated["destination"] = destination
    baked_route = {"version": 2, "address": address, "certificate_authorities": [certificate]}
    return updated, baked_route


def _package_entry(copy: Path) -> None:
    package = json.loads((copy / "studio/electron/package.json").read_text(encoding="utf-8"))
    if package.get("main") != "dist/main.js" or "--publish never" not in package["scripts"]["dist"]:
        raise ValueError(
            "Refusing a diagnostic package that changes the app entry or publish script"
        )


def record_inactive(copy: Path) -> dict:
    """Leave collection off, including the disclosure the engine build will copy."""
    disclosure = (copy / DISCLOSURE).read_bytes()
    route = (copy / ROUTE).read_bytes()
    assert_production_inactive(json.loads(disclosure), json.loads(route))
    _package_entry(copy)
    digest = _sha256(disclosure)
    route_digest = _sha256(route)
    return {
        "condition": "inactive",
        "baked_files": [],
        "production_disclosure_sha256": digest,
        "production_route_sha256": route_digest,
        "diagnostic_disclosure_sha256": digest,
        "diagnostic_route_sha256": route_digest,
        "diagnostic_collection_available": False,
        "production_collection_available": False,
        "packaged_main": "dist/main.js",
        "excluded_from_publication": True,
        "update_feed_globs": list(UPDATE_FEEDS),
    }


def prepare_resource_profile(profile: Path, *, available: bool, enabled: bool) -> dict:
    """Write the active package's choice before launch. Unavailable stays unconfigured."""
    if type(available) is not bool or type(enabled) is not bool:
        raise ValueError("Resource profile choice must be boolean")
    if not available:
        if enabled:
            raise ValueError("An inactive package cannot be enabled")
        return {"configured": False, "available": False, "enabled": False}
    from mnemion.product_telemetry import policy

    saved = (policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL)
    try:
        # The orchestrator imports production disclosure. This flag matches the
        # active package that is about to launch. It is not an unavailable bypass.
        policy.COLLECTION_AVAILABLE = True
        policy.COLLECTOR_URL = loopback_destination()
        configured = policy.configure(
            profile / "mnemion-product-telemetry",
            {
                "enabled": enabled,
                "expected_revision": 0,
                "disclosure_version": policy.DISCLOSURE_VERSION,
                "connection_mode": "unmetered",
            },
            policy_path=profile / "company-absent.json",
        )
    finally:
        policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL = saved
    if configured.get("effective_enabled") is not enabled:
        raise RuntimeError("Resource profile did not keep the requested choice")
    return {
        "configured": True,
        "available": True,
        "enabled": enabled,
        "effective_enabled": configured["effective_enabled"] is True,
    }


def write_bake(copy: Path, destination: str, address: str, certificate: str) -> dict:
    original_disclosure = (copy / DISCLOSURE).read_bytes()
    original_route = (copy / ROUTE).read_bytes()
    baked_disclosure, baked_route = baked_documents(
        json.loads(original_disclosure),
        json.loads(original_route),
        destination,
        address,
        certificate,
    )
    disclosure_bytes = (json.dumps(baked_disclosure, indent=2) + "\n").encode()
    route_bytes = (json.dumps(baked_route, indent=2) + "\n").encode()
    (copy / DISCLOSURE).write_bytes(disclosure_bytes)
    (copy / ROUTE).write_bytes(route_bytes)
    _package_entry(copy)
    return {
        "baked_files": [path.as_posix() for path in BAKED],
        "production_disclosure_sha256": _sha256(original_disclosure),
        "production_route_sha256": _sha256(original_route),
        "diagnostic_disclosure_sha256": _sha256(disclosure_bytes),
        "diagnostic_route_sha256": _sha256(route_bytes),
        "destination_host": "localhost",
        "destination_path": "/v3/report",
        "route_address": "127.0.0.1",
        "condition": "active",
        "diagnostic_collection_available": True,
        "production_collection_available": False,
        "packaged_main": "dist/main.js",
        "excluded_from_publication": True,
        "update_feed_globs": list(UPDATE_FEEDS),
    }


def issue_loopback(output: Path) -> None:
    """Write disposable localhost TLS material outside the source tree."""
    from tests.test_product_telemetry_transport import _certificates

    output.mkdir(parents=True, mode=0o700)

    class Factory:
        def mktemp(self, name: str) -> Path:
            path = output / name
            path.mkdir()
            return path

    certificate, _context = _certificates(Factory(), "localhost")
    public = output / "certificate.pem"
    private = output / "key.pem"
    public.write_bytes(certificate.read_bytes())
    key = certificate.parent / "key.pem"
    private.write_bytes(key.read_bytes())
    private.chmod(0o600)
    validate_loopback_target(
        loopback_destination(), "127.0.0.1", public.read_text(encoding="utf-8")
    )


def bake_checkout(checkout: Path, certificate: Path) -> None:
    """Bake one shared public certificate into a disposable checkout. The private key stays out."""
    text = certificate.read_text(encoding="utf-8")
    assert_public_certificate(text)
    write_bake(checkout, loopback_destination(), "127.0.0.1", text)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-loopback", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bake-checkout", type=Path)
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--prepare-profile", type=Path)
    parser.add_argument("--available", choices=("0", "1"))
    parser.add_argument("--enabled", choices=("0", "1"))
    args = parser.parse_args()
    if args.prepare_profile:
        if args.available is None or args.enabled is None:
            parser.error("--available and --enabled are required")
        prepare_resource_profile(
            args.prepare_profile,
            available=args.available == "1",
            enabled=args.enabled == "1",
        )
        return
    if args.issue_loopback:
        if not args.output:
            parser.error("--output is required")
        issue_loopback(args.output)
        return
    if args.bake_checkout:
        if not args.certificate:
            parser.error("--certificate is required")
        bake_checkout(args.bake_checkout, args.certificate)
        return
    parser.error("Choose --issue-loopback or --bake-checkout")


if __name__ == "__main__":
    main()
