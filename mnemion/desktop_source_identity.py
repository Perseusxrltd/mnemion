"""Verify a conversation folder before enrolling its existing memory identities."""

import hashlib
import os
from pathlib import Path
import re
import time

from . import local_state
from .connectors.live_conversations import (
    ConversationProvider,
    checkpoint_identity,
    file_mark,
    stat_value,
)
from .connectors.source_files import open_selected


def verify_conversation_identity(source, root, client, saved_sources):
    namespace = source.scope_id or "selected-source"
    folder = Path(source.path)
    info = folder.stat()
    identity = {
        "format": 1,
        "source_id": str(source.id),
        "endpoint": source.endpoint,
        "tenant_id": str(source.tenant_id),
        "connector_id": str(source.connector_id),
        "principal_id": str(source.principal_id),
        "path": str(folder),
        "scope_id": namespace,
        "device": info.st_dev,
        "inode": info.st_ino,
    }
    marker = root / f"conversation-identity-{source.id}.json"
    try:
        previous = local_state.read(marker)
    except FileNotFoundError:
        previous = None
    if previous == identity:
        return
    # Existing private app settings establish the original selection on upgrade.
    # This also preserves ordinary removal of every file in an enrolled folder.
    established = previous is None and any(
        all(
            getattr(saved, field) == getattr(source, field)
            for field in (
                "id",
                "endpoint",
                "tenant_id",
                "connector_id",
                "principal_id",
                "provider",
                "path",
            )
        )
        and (saved.scope_id or "selected-source") == namespace
        for saved in saved_sources
    )
    if not established:
        _verify_catalog(source, root, client)
    local_state.write(marker, identity)


def _verify_catalog(source, root, client):
    adapter = ConversationProvider(source.connector(root / f"capture-{source.id}").provider)
    adapter.scopes()
    deadline = time.monotonic() + 45
    cursor, seen, recorded, matched, missing = None, set(), False, False, False
    while True:
        if time.monotonic() >= deadline or len(seen) >= 1000:
            raise local_state.LocalSetupError(
                "source_scope_ambiguous", "The existing conversation catalog could not be verified."
            )
        page = client.request(
            "GET",
            f"/v1/connectors/{source.connector_id}/scopes",
            params={"limit": 100, **({"cursor": cursor} if cursor else {})},
        )
        scopes = page.get("items")
        if not isinstance(scopes, list):
            raise local_state.LocalSetupError("source_scope_ambiguous", "Invalid source catalog.")
        for scope in scopes:
            external = scope.get("external_id") if isinstance(scope, dict) else None
            if (
                not isinstance(external, str)
                or not re.fullmatch(r"conversation:[a-f0-9]{64}", external)
                or scope.get("connector_id") != str(source.connector_id)
            ):
                raise local_state.LocalSetupError(
                    "source_scope_ambiguous", "Invalid source identity."
                )
            recorded = True
            relative = adapter.paths.get(external)
            if relative is not None:
                _verify_copy(adapter.root, relative, scope.get("checkpoint"), deadline)
                matched = True
            elif scope.get("suspension_reason") != "access_lost":
                # Expired permission leases are expected during recovery; only
                # an already absent scope can be omitted on first enrollment.
                missing = True
        cursor = page.get("next_cursor")
        if not cursor:
            break
        if not isinstance(cursor, str) or len(cursor) > 8192 or cursor in seen:
            raise local_state.LocalSetupError(
                "source_scope_ambiguous", "Invalid source catalog cursor."
            )
        seen.add(cursor)
    if recorded and not matched:
        raise local_state.LocalSetupError(
            "source_conversation_identity_required",
            "Use the original conversation identity and a folder retaining its original relative file paths.",
        )
    if missing:
        raise local_state.LocalSetupError(
            "source_conversation_incomplete_copy",
            "The replacement is missing original conversation files. Copy the complete source with its relative paths before reconnecting.",
        )


def _verify_copy(folder, relative, checkpoint, deadline):
    if checkpoint is None:
        return  # An enrolled file with no committed capture has no prior evidence.
    original = checkpoint_identity(checkpoint)
    failure = local_state.LocalSetupError(
        "source_conversation_copy_unverified",
        "This copy cannot yet prove its original capture. Refresh the original source with this version before copying it again.",
    )
    if original is None:
        raise failure
    with open_selected(folder, relative) as stream:
        before = stat_value(os.fstat(stream.fileno()))
        if file_mark(before) == original["file"]:
            return
        if not original.get("captured_sha256") or before["size"] < original["captured"]:
            raise failure
        digest, remaining = hashlib.sha256(), original["captured"]
        while remaining:
            if time.monotonic() >= deadline:
                raise failure
            chunk = stream.read(min(65536, remaining))
            if not chunk:
                raise failure
            digest.update(chunk)
            remaining -= len(chunk)
        if (
            digest.hexdigest() != original["captured_sha256"]
            or stat_value(os.fstat(stream.fileno())) != before
        ):
            raise failure
