"""One disclosed local workflow, with no request/result objects or network I/O."""

from __future__ import annotations

from pathlib import Path
import time

from . import aggregate, policy
from .catalog import METRICS, SURFACES, WORKFLOW_IDS, observation


class Workflow:
    def __init__(self, workflow: str, surface: str, root: Path | None, current: dict):
        self._workflow = workflow
        self._surface = surface
        self._root = root
        self._revision = current["revision"]
        self._generation = current["store_generation"]
        self._started = time.monotonic()
        self._finished = False

    def discard(self) -> None:
        """A replay or unknown origin contributes nothing, including no submission."""
        self._finished = True

    def resources(self, **values: int | float) -> None:
        """Optional process-only sensors share this workflow's original fence."""
        if self._finished:
            return
        try:
            samples = [
                {"kind": "resource", "metric": name, "value": value}
                for name, value in values.items()
            ]
            aggregate.record_many(
                self._root,
                samples,
                expected_revision=self._revision,
                expected_generation=self._generation,
            )
        except Exception:
            return

    def finish(self, outcome: str, reason: str = "none", **measurements: int | float) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            if set(measurements) - (set(METRICS) - {"latency_ms"}):
                return
            value = {
                "kind": "outcome",
                "workflow": self._workflow,
                "surface": self._surface,
                "outcome": outcome,
                "reason": reason,
                "latency_ms": max(0, (time.monotonic() - self._started) * 1000),
                **measurements,
            }
            # Validate everything before admitting even the submission counter.
            # Only fixed names and numeric primitives reach this boundary.
            observation(value)
            submission = {
                "kind": "submission",
                "workflow": self._workflow,
                "surface": self._surface,
            }
            aggregate.record_many(
                self._root,
                [submission, value],
                expected_revision=self._revision,
                expected_generation=self._generation,
            )
        except Exception:
            # Optional measurement never changes the user's operation or output.
            return


def begin(workflow: str, surface: str, *, root: Path | None = None) -> Workflow | None:
    # Unavailable builds do no policy/disk work from an application workflow.
    if not policy.COLLECTION_AVAILABLE or policy.COLLECTOR_URL is None:
        return None
    if type(workflow) is not str or workflow not in WORKFLOW_IDS or surface not in SURFACES:
        return None
    try:
        current = policy.status(root)
        if not current["effective_enabled"]:
            return None
        return Workflow(workflow, surface, root, current)
    except Exception:
        return None
