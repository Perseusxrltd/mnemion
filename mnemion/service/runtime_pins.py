"""Keep an independently adopted control service executable during host updates."""

from pathlib import Path
from uuid import UUID

from . import update_state as state_io
from .update_manifest import ManifestError

FILE = "host-control-runtime.json"


def read(root: Path):
    path = root / FILE
    if not path.exists() and not path.is_symlink():
        return None
    value = state_io.read(path)
    try:
        if (
            set(value)
            != {
                "format",
                "host_id",
                "state",
                "current",
                "previous",
                "pending",
                "attempts",
                "revision",
                "fallback",
                "rejected_slot",
            }
            or type(value["format"]) is not int
            or value["format"] != 1
            or str(UUID(value["host_id"])) != value["host_id"]
            or str(UUID(value["revision"])) != value["revision"]
            or not isinstance(value["state"], str)
            or len(value["state"]) > 4096
            or not Path(value["state"]).is_absolute()
            or type(value["pending"]) is not bool
            or type(value["fallback"]) is not bool
            or type(value["attempts"]) is not int
            or not 0 <= value["attempts"] <= 3
        ):
            raise ValueError
        from .update_cleanup import SLOT

        if value["rejected_slot"] is not None and (
            not isinstance(value["rejected_slot"], str)
            or not SLOT.fullmatch(value["rejected_slot"])
        ):
            raise ValueError
        for index, runtime in enumerate((value["current"], value["previous"])):
            if runtime is None and index == 1:
                continue
            if (
                not isinstance(runtime, dict)
                or not {"slot", "python", "directory", "version"} <= runtime.keys()
            ):
                raise ValueError
            if runtime["slot"] is not None:
                if not isinstance(runtime["slot"], str) or not SLOT.fullmatch(runtime["slot"]):
                    raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ManifestError("Independent host-control runtime custody needs inspection") from None
    return value


def protected(root: Path) -> set:
    value = read(root)
    if value is None:
        return set()
    return {
        runtime["slot"] for runtime in (value["current"], value["previous"]) if runtime is not None
    }
