"""Bounded setup diagnostics without exception messages, locals or private paths."""

from __future__ import annotations

import re


def _database_reason(error: Exception, sqlstate: str | None) -> str:
    """Classify driver failures without retaining any provider text."""
    if sqlstate and sqlstate.startswith("28"):
        return "authentication"
    if type(error).__name__ == "ConnectionTimeout":
        return "timeout"
    # Driver arguments can contain DSNs, certificate paths and server messages.
    # Do not call an arbitrary __str__, and never copy a fragment to the result.
    message = error.args[0] if error.args else None
    if type(message) is not str or len(message) > 8192:
        return "other"
    message = message.lower()
    for reason, fragments in (
        ("authentication", ("password authentication failed", "no pg_hba.conf entry")),
        ("timeout", ("timeout expired", "timed out")),
        ("connection_refused", ("connection refused", "actively refused")),
        (
            "tls",
            (
                "ssl error",
                "tls error",
                "ssl connection",
                "ssl syscall",
                "certificate verify failed",
                "root certificate",
                "server certificate",
                "tls handshake",
            ),
        ),
        (
            "connection_closed",
            (
                "server closed the connection",
                "server closed connection",
                "connection reset",
                "connection was closed",
            ),
        ),
    ):
        if any(fragment in message for fragment in fragments):
            return reason
    return "other"


def failure_diagnostic(error: Exception) -> dict:
    # Exception strings from database/model providers can contain credentials or
    # source text. Report only a fixed category, numeric codes and our own code
    # locations. Never serialize traceback source lines, arguments or locals.
    category = "unexpected"
    for kind, name in (
        (MemoryError, "memory"),
        (ImportError, "dependency"),
        (TimeoutError, "timeout"),
        (OSError, "operating_system"),
    ):
        if isinstance(error, kind):
            category = name
            break
    if type(error).__module__.startswith("psycopg.") or type(error).__module__ == "psycopg":
        category = "database"
    result = {"category": category, "locations": []}
    if isinstance(error, OSError):
        for name in ("errno", "winerror"):
            value = getattr(error, name, None)
            if type(value) is int and 0 <= value <= 2**32 - 1:
                result[name] = value
    if category == "database":
        sqlstate = getattr(error, "sqlstate", None)
        if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
            result["sqlstate"] = sqlstate
        result["database_reason"] = _database_reason(error, result.get("sqlstate"))
    traceback = error.__traceback__
    while traceback:
        module = traceback.tb_frame.f_globals.get("__name__", "")
        function = traceback.tb_frame.f_code.co_name
        if (
            isinstance(module, str)
            and re.fullmatch(r"mnemion(?:\.[a-z_][a-z0-9_]{0,63}){1,4}", module)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", function)
            and 1 <= traceback.tb_lineno <= 1_000_000
        ):
            result["locations"].append(
                {"module": module, "function": function, "line": traceback.tb_lineno}
            )
            result["locations"] = result["locations"][-8:]
        traceback = traceback.tb_next
    return result
