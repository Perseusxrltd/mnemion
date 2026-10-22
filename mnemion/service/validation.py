"""Derive diagnostic names from registered API inputs, not incoming values."""

from pydantic import TypeAdapter

from ..validation_fields import schema_names


def route_names(route) -> frozenset[str]:
    if route is None or not hasattr(route, "dependant"):
        return frozenset()
    cached = getattr(route, "_mnemion_validation_names", None)
    if cached is not None:
        return cached
    names, seen = set(), set()
    pending = [route.dependant]
    while pending:
        dependant = pending.pop()
        if id(dependant) in seen:
            continue
        seen.add(id(dependant))
        pending.extend(dependant.dependencies)
        for group in (
            "body_params",
            "query_params",
            "path_params",
            "header_params",
            "cookie_params",
        ):
            for field in getattr(dependant, group):
                names.update(
                    value
                    for value in (field.name, field.alias)
                    if isinstance(value, str) and len(value) <= 100
                )
                try:
                    names.update(
                        schema_names(TypeAdapter(field.field_info.annotation).json_schema())
                    )
                except (TypeError, ValueError):
                    # Custom runtime-only types may not expose JSON schema.
                    # Keep their registered parameter name and redact the rest.
                    continue
    result = frozenset(names)
    route._mnemion_validation_names = result
    return result
