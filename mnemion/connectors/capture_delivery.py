"""Bounded delivery of already committed selected evidence to current custody."""

import time

import httpx

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
    if any(value[field] != expected for field, expected in inbox.binding.items()) or (
        value.get("capture_policy") != inbox.binding.get("capture_policy")
    ):
        raise InboxError("capture_binding_mismatch")
    if not grant.active or grant.revoked_at or grant.source_revoked_at:
        raise InboxError("capture_authorization_revoked")
    return grant


def retire_grant(binding, client):
    """Reconcile an uncertain retirement by reading its irreversible state first."""
    base = f"/v1/capture-grants/{binding['grant_id']}"
    try:
        grant = CaptureGrant.model_validate(client.request("GET", base))
        value = grant.model_dump(mode="json")
        if any(value.get(key) != expected for key, expected in binding.items()) or (
            value.get("capture_policy") != binding.get("capture_policy")
        ):
            raise InboxError("capture_binding_mismatch")
        if not grant.revoked_at and not grant.source_revoked_at:
            grant = CaptureGrant.model_validate(client.request("DELETE", base))
        value = grant.model_dump(mode="json")
        if (
            not (grant.revoked_at or grant.source_revoked_at)
            or grant.active
            or any(value.get(key) != expected for key, expected in binding.items())
            or value.get("capture_policy") != binding.get("capture_policy")
        ):
            raise InboxError("capture_retire_required")
    except MnemionError as error:
        if error.status in {401, 403}:
            raise InboxError("capture_retirement_credentials") from None
        raise


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
    inbox.observations.contacted()
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
        retained = inbox.apply_fences(value)
        if not retained or value["next_cursor"] is None:
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
    # A successful write is not evidence of indexing. Observe bounded source
    # pages after delivery; a transient statistics outage must not erase the
    # confirmed receipts or turn them into unconfirmed delivery.
    for _ in range(2):
        if time.monotonic() >= deadline:
            break
        cursor = inbox.observations.index_cursor()
        try:
            value = client.request(
                "GET",
                base + "/index-progress",
                params={"limit": 1000, **({"after": cursor} if cursor else {})},
            )
            if inbox.observations.indexed(value):
                break
        except (MnemionError, httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            if isinstance(error, MnemionError) and error.status in (401, 403):
                raise InboxError("capture_authorization_revoked") from None
            inbox.observations.index_unavailable(
                unsupported=isinstance(error, MnemionError) and error.status == 404
            )
            break
    return {
        "remote_committed_events": delivered,
        "fence_sweep_pending": inbox.fence_cursor() is not None or inbox.fence_history_blocked(),
        **inbox.status(),
    }
