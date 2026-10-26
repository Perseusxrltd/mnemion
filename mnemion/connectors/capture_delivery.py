"""Bounded delivery of already committed selected evidence to current custody."""

import time
from dataclasses import dataclass

import httpx

from ..sdk import MnemionError, RequestReceipt
from ..service.capture_models import CaptureGrant, CapturePageReceipt
from .conversation_inbox import InboxError


@dataclass(slots=True)
class DeliveryProgress:
    """Only this call's acknowledged pages; never reconstructed from history."""

    remote_committed_events: int = 0
    newly_stored_events: int | None = 0

    def acknowledged(self, count: int, newly_stored: int | None):
        self.remote_committed_events += count
        if newly_stored is None:
            self.newly_stored_events = None
        elif self.newly_stored_events is not None:
            self.newly_stored_events += newly_stored


def _newly_stored(receipt, metadata):
    if type(metadata) is not RequestReceipt:
        return None
    if metadata.disposition == "replayed":
        return 0
    count = metadata.capture_stored_events
    stored = sum(item["outcome"] == "stored" for item in receipt["items"])
    return (
        count
        if metadata.disposition == "new" and type(count) is int and 0 <= count <= stored
        else None
    )


def verify_grant(inbox, client):
    capabilities = client.request("GET", "/health/live")
    if capabilities.get("durable_capture") != "v1" or (
        (inbox.binding.get("capture_policy") or {}).get("retention") == "expire_after"
        and capabilities.get("capture_retention") != "v1"
    ):
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


def deliver(
    inbox, client, *, maximum_pages=4, maximum_seconds=20, progress: DeliveryProgress | None = None
):
    """Use exact saved pages; unknown replies never reset or rename evidence.

    The caller has already completed local capture. No SQLite transaction spans
    HTTP. All outgoing pages are checked again by the service against current
    source, key, grant, audience and negative fences in its commit transaction.
    """
    if not 1 <= maximum_pages <= 100 or not 1 <= maximum_seconds <= 600:
        raise ValueError("Choose bounded capture delivery limits")
    progress = DeliveryProgress() if progress is None else progress
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
        posted = receipt is None
        metadata = None
        try:
            if posted:
                request = getattr(client, "request_with_receipt", None)
                options = {"body": page, "key": "capture:" + page["page_id"]}
                if callable(request):
                    receipt, metadata = request("POST", base + "/pages", **options)
                else:
                    # Older/custom clients keep their original delivery path.
                    # Their unverified fresh-effect count stays unavailable.
                    receipt = client.request("POST", base + "/pages", **options)
            value = CapturePageReceipt.model_validate(receipt).model_dump(mode="json")
            inbox.acknowledge(value)
        except BaseException:
            if posted:
                progress.newly_stored_events = None
            raise
        fresh = _newly_stored(value, metadata) if posted else 0
        progress.acknowledged(len(value["items"]), fresh)
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
        "remote_committed_events": progress.remote_committed_events,
        "newly_stored_events": progress.newly_stored_events,
        "fence_sweep_pending": inbox.fence_cursor() is not None or inbox.fence_history_blocked(),
        **inbox.status(),
    }
