"""Classic CLI ownership; private arguments, output and results stay in the CLI."""

from functools import cache
from importlib.resources import files
import json

from . import product_telemetry as availability


@cache
def _origins():
    # Only immutable release definitions are reused, never privacy permission.
    return json.loads(files("mnemion.product_telemetry").joinpath("cli-origins.json").read_text())


def invoke(command, action, *, owned, preview=False):
    active, spec = None, None
    if owned is True and availability.COLLECTION_AVAILABLE and availability.COLLECTOR_URL:
        try:
            spec = _origins()["operations"].get(command) if type(command) is str else None
            if spec and "exclusion" not in spec:
                name = (
                    spec["variants"].get("preview" if preview else "apply")
                    if "variants" in spec
                    else spec.get("workflow")
                )
                if name:
                    from .product_telemetry import workflow

                    active = workflow.begin(name, "headless")
        except Exception:
            active = None
    if active is None:
        return action()

    def finish(outcome, reason="none"):
        try:
            active.finish(outcome, reason)
        except Exception:
            pass

    try:
        result = action()
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            finish("cancelled")
        elif type(error) is SystemExit and (
            error.code is None or type(error.code) is int and error.code == 0
        ):
            finish(spec.get("completion", "unconfirmed"))
        else:
            finish("failed" if spec.get("read_only") is True else "unconfirmed", "other_failure")
        raise
    finish(spec.get("completion", "unconfirmed"))
    return result
