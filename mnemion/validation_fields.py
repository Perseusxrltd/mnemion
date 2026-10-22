"""Small diagnostics made only from trusted schema names and fixed error codes."""

from typing import get_args

from pydantic_core import ErrorType

ERROR_TYPES = frozenset(get_args(ErrorType)) | {"memory_scope", "connector_provider"}
LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})


def schema_names(schema: dict) -> frozenset[str]:
    """Read a program-owned JSON schema, never a request or provider document."""
    names = set()
    pending = [schema]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                names.update(
                    name for name in properties if isinstance(name, str) and len(name) <= 100
                )
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return frozenset(names)


def safe_fields(errors: list[dict], names: frozenset[str]) -> list[dict[str, str]]:
    """Unknown mapping keys, discriminator values and extras must not be echoed."""
    known = names | LOCATIONS
    result = []
    # Duplicate unknown keys must not crowd out a useful, registered field.
    # Bound both the inspection work and the number of returned diagnostics.
    for error in errors[:256]:
        parts = []
        for part in error.get("loc", ())[:8]:
            if isinstance(part, str) and part in known:
                parts.append(part)
            elif type(part) is int and 0 <= part <= 999999:
                parts.append(str(part))
            else:
                parts.append("unknown")
        kind = error.get("type")
        field = {
            "field": ".".join(parts)[:160],
            "type": kind if isinstance(kind, str) and kind in ERROR_TYPES else "validation_error",
        }
        if field not in result:
            result.append(field)
            if len(result) == 20:
                break
    return result
