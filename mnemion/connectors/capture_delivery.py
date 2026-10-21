"""Bounded delivery of already committed selected evidence to current custody."""

import time

from ..sdk import MnemionError
from ..service.capture_models import CaptureGrant, CapturePageReceipt
from .conversation_inbox import InboxError


def verify_grant(inbox, client):
    if client.request("GET", "/health/live").get("durable_capture") != "v1":
        raise InboxError("capture_server_upgrade_required")
    grant = CaptureGrant.model_validate(
        client.request("GET", f"/v1/capture-grants/{inbox.binding['grant_id']}")
    )
    value = grant.model_dump(mode="json")
    if any(value[field] != expected for field, expected in inbox.binding.items()):
        raise InboxError("capture_binding_mismatch")
    if not grant.active or grant.revoked_at or grant.source_revoked_at:
        raise InboxError("capture_authorization_revoked")
    return grant


def deliver(inbox, client, *, maximum_pages=4, maximum_seconds=20):
    """Use exact saved pages; unknown replies never reset or rename evidence.

    The caller has already completed local capture. No SQLite transaction spans
    HTTP. All outgoing pages are checked again by the service against current
    source, key, grant, audience and negative fences in its commit transaction.
    """
    if not 1 <= maximum_pages <= 100 or not 1 <= maximum_seconds <= 600:
        raise ValueError("Choose bounded capture delivery limits")
    deadline = time.monotonic() + maximum_seconds
    grant = verify_grant(inbox, client)
    base = f"/v1/capture-grants/{grant.grant_id}"
    # This is an ID-ordered sweep, not a persistent chronological watermark.
    # Applying its final page resets the cursor, so newly added earlier IDs
    # are covered by the next sweep. Pending-page receipts also apply fences.
    for _ in range(2):
        if time.monotonic() >= deadline:
            break
        cursor = inbox.fence_cursor()
        value = client.request(
            "GET", base + "/fences", params={"limit": 100, **({"after": cursor} if cursor else {})}
        )
        inbox.apply_fences(value)
        if value["next_cursor"] is None:
            break
    delivered = 0
    for _ in range(maximum_pages):
        if time.monotonic() >= deadline:
            break
        pending = inbox.page()
        if pending is None:
            break
        page = pending["page"]
        receipt = None
        if pending["reconcile"]:
            try:
                receipt = client.request("GET", base + "/pages/" + page["page_id"])
            except MnemionError as error:
                if error.status != 404:
                    raise
                # An absent receipt permits the SAME idempotent page only.
                # POST still enforces the current grant and source permissions.
        if receipt is None:
            receipt = client.request(
                "POST", base + "/pages", body=page, key="capture:" + page["page_id"]
            )
        value = CapturePageReceipt.model_validate(receipt).model_dump(mode="json")
        inbox.acknowledge(value)
        delivered += len(value["items"])
    return {
        "remote_committed_events": delivered,
        "fence_sweep_pending": inbox.fence_cursor() is not None,
        **inbox.status(),
    }
