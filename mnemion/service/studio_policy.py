"""Optional company browser policy, configured by the service operator."""

import ipaddress
import json
import os
import re
from urllib.parse import urlsplit

VARIABLE = "MNEMION_STUDIO_CONNECT_ORIGINS"
PRODUCT_TELEMETRY_POLICY_PATH = "/studio/telemetry-policy"
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


def product_telemetry_page(index: str) -> str:
    """Embed only the operator's fixed, restrictive browser policy.

    Reading the page needs no telemetry request, cookie, workspace login or
    third-party connection. Existing connect-src restrictions remain unchanged.
    """
    from html import escape
    from ..product_telemetry.policy import company_policy

    value = escape(json.dumps(company_policy(), separators=(",", ":")), quote=True)
    markup = f'<meta name="mnemion-product-telemetry-policy" content="{value}">'
    if "</head>" in index:
        return index.replace("</head>", markup + "</head>", 1)
    return markup + index


def product_telemetry_policy():
    """Fresh public restrictions, without identity, session or workspace reads.

    The browser reads this only within a reserved delivery attempt. No account
    authorization, cookie, token, analytics body or cache validator is used.
    Operators must also exclude this path from proxy/access/trace logging before
    enabling production telemetry; these application headers cannot do that.
    """
    from starlette.responses import JSONResponse
    from ..product_telemetry.policy import company_policy

    return JSONResponse(
        company_policy(),
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )
