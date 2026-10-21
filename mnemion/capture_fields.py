"""Bounded, literal JSON field exclusions before selected content is retained."""

import json

MAX_DEPTH = 64
MAX_NODES = 250_000


class FieldSelectionLimit(ValueError):
    pass


def select_fields(value, excluded):
    """Copy a decoded record, omitting matching keys at every object depth.

    Names are case-insensitive literals. String contents are never interpreted
    as JSON, patterns or secrets. The producer's original value is untouched.
    """
    names = frozenset(name.casefold() for name in excluded)
    remaining = MAX_NODES

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            raise FieldSelectionLimit("conversation_field_selection_limit")
        if isinstance(item, dict):
            return {
                key: visit(child, depth + 1)
                for key, child in item.items()
                if key.casefold() not in names
            }
        if isinstance(item, list):
            return [visit(child, depth + 1) for child in item]
        return item

    return visit(value, 0)


def selected_jsonl(text, excluded):
    """Keep record boundaries while replacing records with selected JSON fields."""
    return "\n".join(
        json.dumps(
            select_fields(json.loads(line), excluded), ensure_ascii=False, separators=(",", ":")
        )
        if line.strip()
        else line
        for line in text.split("\n")
    )
