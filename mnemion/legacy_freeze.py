"""A persistent maintenance boundary for updated v3 writer entry points."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .archives import private_json

MARKER = ".mnemion-writers-paused.json"


def require_writable(directory: str | Path) -> None:
    directory = Path(directory).expanduser().resolve()
    if any((root / MARKER).exists() for root in (directory, directory.parent)):
        raise RuntimeError(
            "This legacy profile is paused for migration or recovery; use the service or explicitly resume the verified profile"
        )


def freeze_profile(profile: Path) -> dict:
    profile = profile.expanduser().resolve()
    if not profile.is_dir():
        raise ValueError("Legacy profile does not exist")
    path = profile / MARKER
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = {
        "version": 1,
        "freeze_id": str(uuid4()),
        "paused_at": datetime.now(timezone.utc).isoformat(),
    }
    private_json(path, result)
    return result


def thaw_profile(profile: Path, freeze_id: str) -> None:
    path = profile.expanduser().resolve() / MARKER
    marker = json.loads(path.read_text(encoding="utf-8"))
    if marker["freeze_id"] != freeze_id:
        raise ValueError("The freeze ID does not match this paused profile")
    path.unlink()
