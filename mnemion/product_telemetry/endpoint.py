"""Offline validation of the release-owned collector route. No sockets or DNS."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_address
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Release-owned address and certificate name, never a workspace address."""

    host: str
    address: str
    port: int = 443

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
            ):
                return False
            authority = self.host if self.port == 443 else f"{self.host}:{self.port}"
            return policy.COLLECTOR_URL == f"https://{authority}/v1/report"
        except (TypeError, ValueError):
            return False

    def headers(self) -> bytes:
        authority = self.host if self.port == 443 else f"{self.host}:{self.port}"
        return (
            f"POST /v1/report HTTP/1.1\r\nHost: {authority}\r\n"
            "Content-Type: application/octet-stream\r\nContent-Length: 4\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")


@lru_cache(maxsize=1)
def release_address() -> str | None:
    # This is an immutable package input, not a user's setting. Read it once
    # per process; frequent status/measurement reads must not add file I/O.
    try:
        with Path(__file__).with_name("transport-route.json").open("rb") as stream:
            raw = stream.read(257)
        if len(raw) > 256:
            return None
        route = json.loads(raw)
        if (
            isinstance(route, dict)
            and set(route) == {"version", "address"}
            and type(route["version"]) is int
            and route["version"] == 1
            and type(route["address"]) is str
            and len(route["address"]) <= 45
        ):
            return route["address"]
    except (OSError, ValueError, TypeError):
        pass
    return None


def release_endpoint() -> Endpoint | None:
    from . import policy

    if not policy.COLLECTION_AVAILABLE or not policy.COLLECTOR_URL:
        return None
    try:
        address = release_address()
        if address is None:
            return None
        url = urlsplit(policy.COLLECTOR_URL)
        candidate = Endpoint(url.hostname, address, url.port or 443)
        return candidate if candidate.validate() else None
    except (ValueError, TypeError):
        return None
