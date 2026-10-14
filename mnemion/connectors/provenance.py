"""Bounded source snapshot identities, separate from per-document revisions."""

import re


def git_commit(checkpoint: object) -> str | None:
    if isinstance(checkpoint, str) and re.fullmatch(
        r"git:(?:[0-9a-f]{40}|[0-9a-f]{64})", checkpoint
    ):
        return checkpoint[4:]
    return None
