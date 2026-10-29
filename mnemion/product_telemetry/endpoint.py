"""Offline validation of the release-owned collector route. No sockets or DNS."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_address
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def valid_certificate_authorities(value) -> bool:
    """Bound one or two public PEM roots without loading TLS or ambient trust."""
    if type(value) not in (tuple, list) or not 1 <= len(value) <= 2:
        return False
    seen = set()
    for certificate in value:
        if type(certificate) is not str or not certificate.isascii() or len(certificate) > 4096:
            return False
        lines = certificate.replace("\r\n", "\n").removesuffix("\n").split("\n")
        if (
            len(lines) < 3
            or lines[0] != "-----BEGIN CERTIFICATE-----"
            or lines[-1] != "-----END CERTIFICATE-----"
            or any(not re.fullmatch(r"[A-Za-z0-9+/=]{1,64}", line) for line in lines[1:-1])
        ):
            return False
        try:
            encoded = "".join(lines[1:-1])
            decoded = base64.b64decode(encoded, validate=True)
            if (
                not decoded
                or base64.b64encode(decoded).decode("ascii") != encoded
                or decoded in seen
            ):
                return False
            seen.add(decoded)
        except (ValueError, binascii.Error):
            return False
    return True


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Release-owned address, certificate name and roots, never workspace trust."""

    host: str
    address: str
    port: int = 443
    certificate_authorities: tuple[str, ...] = ()

    def __post_init__(self):
        # Caller-owned lists must not be able to change trust after validation.
        if type(self.certificate_authorities) is list:
            object.__setattr__(self, "certificate_authorities", tuple(self.certificate_authorities))

    def validate(self) -> bool:
        from . import policy

        try:
            address = ip_address(self.address)
            if str(address) != self.address or "%" in self.address:
                return False
            if (
                type(self.host) is not str
                or len(self.host) > 253
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", self.host)
                or ".." in self.host
                or type(self.port) is not int
                or not 1 <= self.port <= 65535
                or not valid_certificate_authorities(self.certificate_authorities)
            ):
                return False
            authority = self.host if self.port == 443 else f"{self.host}:{self.port}"
            return policy.COLLECTOR_URL == f"https://{authority}/v3/report"
        except (TypeError, ValueError):
            return False

    def headers(self) -> bytes:
        authority = self.host if self.port == 443 else f"{self.host}:{self.port}"
        from .wire_v3 import PACKET_BYTES

        return (
            f"POST /v3/report HTTP/1.1\r\nHost: {authority}\r\n"
            f"Content-Type: application/octet-stream\r\nContent-Length: {PACKET_BYTES}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")


@lru_cache(maxsize=1)
def _release_route() -> tuple[str, tuple[str, ...]] | None:
    # This is an immutable package input, not a user's setting. Read it once
    # per process; frequent status/measurement reads must not add file I/O.
    try:
        with Path(__file__).with_name("transport-route.json").open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            return None
        route = json.loads(raw)
        if (
            isinstance(route, dict)
            and set(route) == {"version", "address", "certificate_authorities"}
            and type(route["version"]) is int
            and route["version"] == 2
            and type(route["address"]) is str
            and len(route["address"]) <= 45
            and valid_certificate_authorities(route["certificate_authorities"])
        ):
            return route["address"], tuple(route["certificate_authorities"])
    except (OSError, ValueError, TypeError):
        pass
    return None


def release_address() -> str | None:
    route = _release_route()
    return route[0] if route else None


def release_certificate_authorities() -> tuple[str, ...]:
    route = _release_route()
    return route[1] if route else ()


def release_endpoint() -> Endpoint | None:
    from . import policy

    if not policy.COLLECTION_AVAILABLE or not policy.COLLECTOR_URL:
        return None
    try:
        address = release_address()
        if address is None:
            return None
        url = urlsplit(policy.COLLECTOR_URL)
        candidate = Endpoint(
            url.hostname, address, url.port or 443, release_certificate_authorities()
        )
        return candidate if candidate.validate() else None
    except (ValueError, TypeError):
        return None
