"""Disclosed local connector work; reusable sync and remote jobs stay unowned."""

from contextlib import contextmanager
import time

from .control_measurement import _optional
from .product_telemetry import workflow
from .product_telemetry.catalog import maintenance_specification


class LocalActionMeasurement:
    def __init__(self, active, completion):
        self.active = active
        self.completion = completion

    @_optional
    def succeeded(self):
        # A successful local acknowledgement is not an inferred remote job,
        # delivered-item total or replay of private recovery history.
        self.active.finish(self.completion)

    @_optional
    def failed(self, *, cancelled=False):
        # A mutation may have taken effect before its caller lost confirmation.
        # Do not infer a confirmed failure from an arbitrary exception.
        self.active.finish(
            "cancelled" if cancelled else "unconfirmed",
            "none" if cancelled else "other_failure",
        )


@_optional
def begin_capture_control(action: str, *, owned: bool):
    if not owned or type(action) is not str:
        return None
    spec = maintenance_specification()["capture_controls"].get(action)
    if spec is None or "exclusion" in spec:
        return None
    active = workflow.begin(spec["workflow"], "headless")
    return LocalActionMeasurement(active, spec["completion"]) if active else None


@contextmanager
def observed_preparation(kind: str, *, owned: bool):
    measurement = None
    try:
        if owned is True and type(kind) is str:
            spec = maintenance_specification()["model_preparation"].get(kind)
            if spec:
                active = workflow.begin(spec["workflow"], "headless")
                if active:
                    measurement = LocalActionMeasurement(active, spec["completion"])
    except Exception:
        pass
    try:
        yield
    except BaseException as error:
        if measurement is not None:
            measurement.failed(cancelled=isinstance(error, KeyboardInterrupt))
        raise
    else:
        if measurement is not None:
            measurement.succeeded()


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
            if not isinstance(self.active, workflow.WorkflowChoice):
                self.active.discard()
                return
            fresh = capture.get("newly_stored_events")
            if type(fresh) is not int or not 0 <= fresh <= capture["remote_committed_events"]:
                fresh = None
            worked = capture["locally_accepted"] + (fresh or 0)
            metrics = {
                "work_items": capture["locally_accepted"],
                "queue_items": capture["pending_events"],
                "stored_bytes": capture["database_bytes"],
                **({"result_items": fresh} if fresh is not None else {}),
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
        if type(capture) is dict:
            choice = (
                "capture.deliver"
                if capture["locally_accepted"] == 0 and fresh is not None and fresh > 0
                else "capture.collect"
            )
            self.active.finish_choice(choice, outcome, reason, **metrics)
        else:
            self.active.finish(outcome, reason, **metrics)


@_optional
def begin_source(*, capture: bool, owned: bool, memory_limit=None):
    if not owned:
        return None
    active = (
        workflow.begin_choices(("capture.collect", "capture.deliver"), "headless")
        if capture
        else workflow.begin("sources.scan", "headless")
    )
    return SourceMeasurement(active, memory_limit) if active else None
