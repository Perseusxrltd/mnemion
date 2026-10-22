"""Optional company browser policy, configured by the service operator."""

import ipaddress
import json
import os
import re
from urllib.parse import urlsplit

VARIABLE = "MNEMION_STUDIO_CONNECT_ORIGINS"
DEFAULT_ORIGINS = ["https:", "http://127.0.0.1:*", "http://localhost:*"]
INVALID = (
    "MNEMION_STUDIO_CONNECT_ORIGINS must be a JSON list of up to 16 HTTPS or loopback HTTP origins"
)


def origin(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 300
        or re.search(r"[\s\\%'\";]", value)
    ):
        raise ValueError(INVALID)
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (
            parsed.scheme not in {"https", "http"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or port is not None
            and not 1 <= port <= 65535
        ):
            raise ValueError(INVALID)
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
            host = host.encode("idna").decode("ascii").lower().removesuffix(".")
            if len(host) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            ):
                raise ValueError(INVALID)
        if (
            parsed.scheme == "http"
            and host != "localhost"
            and not (address and address.is_loopback)
        ):
            raise ValueError(INVALID)
        if address:
            host = f"[{address.compressed}]" if address.version == 6 else address.compressed
        return f"{parsed.scheme}://{host}" + (f":{port}" if port is not None else "")
    except (ValueError, UnicodeError):
        raise ValueError(INVALID) from None


def configuration():
    raw = os.environ.get(VARIABLE)
    if raw is None:
        return {"profile": "multi_workspace", "origins": list(DEFAULT_ORIGINS)}
    try:
        if len(raw) > 4096:
            raise ValueError(INVALID)
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) > 16:
            raise ValueError(INVALID)
        return {
            "profile": "restricted",
            "origins": list(dict.fromkeys(origin(value) for value in values)),
        }
    except (ValueError, TypeError):
        raise ValueError(INVALID) from None


def content_security_policy():
    origins = configuration()["origins"]
    connections = "'self'" + (" " + " ".join(origins) if origins else "")
    return (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data:; connect-src {connections}; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
