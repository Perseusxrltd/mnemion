"""Pure capture status decisions shared with lightweight connector clients."""

BACKFILL_POLL_SECONDS = 5
BACKFILL_REASONS = frozenset({"capture_scan_pending", "capture_delivery_pending"})


def backfill_pending(report):
    if not isinstance(report, dict):
        return False
    capture = report.get("capture")
    return (
        report.get("completed") is False
        and report.get("remote_sync_available") is True
        and report.get("control_reported") is not False
        and isinstance(capture, dict)
        and (
            capture.get("capture_complete") is False
            and capture.get("reason_code") == "capture_scan_pending"
            or capture.get("capture_complete") is True
            and capture.get("delivery_complete") is False
            and capture.get("reason_code") == "capture_delivery_pending"
        )
    )
