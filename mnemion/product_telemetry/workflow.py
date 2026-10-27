"""One disclosed local workflow, with no request/result objects or network I/O."""

from __future__ import annotations

import math
from pathlib import Path
import time

from . import aggregate, policy
from .catalog import METRICS, SURFACES, WORKFLOW_IDS, observation


class Workflow:
    def __init__(
        self,
        workflow: str,
        surface: str,
        root: Path | None,
        current: dict,
        *,
        started: float | None = None,
    ):
        self._workflow = workflow
        self._surface = surface
        self._root = root
        self._revision = current["revision"]
        self._generation = current["store_generation"]
        self._started = time.monotonic() if started is None else started
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
            recorded = aggregate.record_many(
                self._root,
                samples,
                expected_revision=self._revision,
                expected_generation=self._generation,
            )
            if recorded:
                self._offer_delivery()
        except Exception:
            return

    def finish(self, outcome: str, reason: str = "none", **measurements: int | float) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            if set(measurements) - (set(METRICS) - {"latency_ms"}):
                return
            elapsed = time.monotonic() - self._started
            if not math.isfinite(elapsed) or elapsed < 0:
                return
            value = {
                "kind": "outcome",
                "workflow": self._workflow,
                "surface": self._surface,
                "outcome": outcome,
                "reason": reason,
                "latency_ms": elapsed * 1000,
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
            recorded = aggregate.record_many(
                self._root,
                [submission, value],
                expected_revision=self._revision,
                expected_generation=self._generation,
            )
            if recorded:
                self._offer_delivery()
        except Exception:
            # Optional measurement never changes the user's operation or output.
            return

    def _offer_delivery(self) -> None:
        from .activity import offer_recorded

        offer_recorded(self._root, self._revision, self._generation)


class WorkflowChoice(Workflow):
    """One owned operation whose fixed category is known only after its work."""

    def __init__(
        self,
        choices: tuple[str, ...],
        surface: str,
        root: Path | None,
        current: dict,
        *,
        started: float | None = None,
    ):
        super().__init__(choices[0], surface, root, current, started=started)
        self._choices = choices

    def finish_choice(
        self, choice: str, outcome: str, reason: str = "none", **measurements: int | float
    ) -> None:
        if self._finished:
            return
        if type(choice) is not str or choice not in self._choices:
            self.discard()
            return
        # Preserve the original time and privacy fence. Never begin a workflow
        # after observing the result, or record the same work under both names.
        self._workflow = choice
        self.finish(outcome, reason, **measurements)


def begin_choices(
    choices: tuple[str, ...], surface: str, *, root: Path | None = None
) -> WorkflowChoice | None:
    if not policy.COLLECTION_AVAILABLE or policy.COLLECTOR_URL is None:
        return None
    if (
        type(choices) is not tuple
        or not 2 <= len(choices) <= 4
        or any(type(name) is not str or name not in WORKFLOW_IDS for name in choices)
        or len(set(choices)) != len(choices)
        or type(surface) is not str
        or surface not in SURFACES
    ):
        return None
    try:
        # Optional policy/contribution reads delay this same action. Keep its
        # start before that work so the latency cannot conceal our own cost.
        started = time.monotonic()
        if not math.isfinite(started):
            return None
        # Exhausting collection cannot hide a later delivery-only cycle. The
        # final selected workflow still has its own atomic contribution limit.
        if all(aggregate.workflow_exhausted(root, name, surface) for name in choices):
            return None
        current = policy.status(root)
        if not current["effective_enabled"]:
            if current["reason"] == "user_disabled":
                aggregate.remember_disabled(root)
            return None
        return WorkflowChoice(choices, surface, root, current, started=started)
    except Exception:
        return None


def begin(workflow: str, surface: str, *, root: Path | None = None) -> Workflow | None:
    # Unavailable builds do no policy/disk work from an application workflow.
    if not policy.COLLECTION_AVAILABLE or policy.COLLECTOR_URL is None:
        return None
    if type(workflow) is not str or workflow not in WORKFLOW_IDS or surface not in SURFACES:
        return None
    try:
        started = time.monotonic()
        if not math.isfinite(started):
            return None
        if aggregate.workflow_exhausted(root, workflow, surface):
            return None
        current = policy.status(root)
        if not current["effective_enabled"]:
            if current["reason"] == "user_disabled":
                aggregate.remember_disabled(root)
            return None
        return Workflow(workflow, surface, root, current, started=started)
    except Exception:
        return None
