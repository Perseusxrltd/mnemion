"""Disclosed local connector work; reusable sync and remote jobs stay unowned."""

import time

from .control_measurement import _optional
from .product_telemetry import workflow


class SourceMeasurement:
    def __init__(self, active, memory_limit=None):
        self.active = active
        self.memory_limit = memory_limit
        self.started = time.monotonic()
        self.process = None
        self.cpu = None
        try:
            import psutil

            self.process = psutil.Process()
            cpu = self.process.cpu_times()
            self.cpu = cpu.user + cpu.system
        except Exception:
            pass

    @_optional
    def failed(self, *, cancelled=False):
        self.active.finish(
            "cancelled" if cancelled else "failed", "none" if cancelled else "other_failure"
        )

    @_optional
    def finish(self, report):
        if type(report) is not dict or report.get("paused") is True:
            self.active.discard()
            return
        capture = report.get("capture")
        if type(capture) is dict:
            worked = capture["locally_accepted"] + capture["remote_committed_events"]
            metrics = {
                "work_items": capture["locally_accepted"],
                "queue_items": capture["pending_events"],
                "stored_bytes": capture["database_bytes"],
            }
        else:
            worked = report["changed"] + report["removed"] + report["conflicts"]
            metrics = {
                "work_items": report["changed"] + report["removed"],
                "result_items": report["changed"],
            }
        if report["completed"] is True and worked == 0:
            self.active.discard()
            return
        denied = (
            type(capture) is dict and capture.get("reason_code") == "capture_authorization_revoked"
        )
        outcome = "success" if report["completed"] is True else "denied" if denied else "deferred"
        reason = (
            "none"
            if report["completed"] is True
            else "authorization"
            if denied
            else "offline"
            if report.get("remote_sync_available") is False
            else "other_failure"
        )
        try:
            if self.process is not None:
                rss = self.process.memory_info().rss
                self.active.resources(
                    rss_bytes=rss,
                    **({"resource_budget_bytes": self.memory_limit} if self.memory_limit else {}),
                )
                if self.cpu is not None:
                    cpu = self.process.cpu_times()
                    elapsed = time.monotonic() - self.started
                    if elapsed > 0:
                        self.active.resources(
                            cpu_millicores=max(
                                0, (cpu.user + cpu.system - self.cpu) * 1000 / elapsed
                            )
                        )
        except Exception:
            pass
        self.active.finish(outcome, reason, **metrics)


@_optional
def begin_source(*, capture: bool, owned: bool, memory_limit=None):
    if not owned:
        return None
    active = workflow.begin("capture.collect" if capture else "sources.scan", "headless")
    return SourceMeasurement(active, memory_limit) if active else None
