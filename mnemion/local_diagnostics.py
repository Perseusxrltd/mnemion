"""Bounded setup diagnostics without exception messages, locals or private paths."""

from __future__ import annotations

import re


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
