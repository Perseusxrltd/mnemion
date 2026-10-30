"""Local v3 release allowlist for one collector. Not a client or host update.

The process that accepts reports never opens a socket to obtain this file. A
separate operator job writes it after checking the public wire document. Each
aggregate week freezes the snapshot it started with, including the coordinate
to slot map. A missing, malformed, or stale file does not erase that week's
counters. The next week keeps the last valid snapshot, or the allowlist bundled
with this process when nothing valid has been adopted yet.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from contextlib import suppress
import urllib.error
import urllib.request

from . import wire_v3
from .wire_v3 import PACKET_BYTES, UNLISTED, WIRE, WireV3Error

SCHEMA_NAME = "mnemion-v3-release-catalog"
SCHEMA_VERSION = 1
FILENAME = "release-catalog.json"
BUNDLED_SOURCE = "bundled-wire-v3"
SOURCE = (
    "https://raw.githubusercontent.com/Perseusxrltd/mnemion/"
    "main/mnemion/product_telemetry/wire-v3.json"
)
USER_AGENT = "mnemion-telemetry-catalog-sync"
LOCAL_KEYS = {"schema_name", "schema_version", "source", "generated_at", "release_allowlist"}
MAX_LOCAL_BYTES = 65536
MAX_WIRE_BYTES = 262144
FRESHNESS_SECONDS = WIRE["reporting"]["retained_windows"] * WIRE["reporting"]["window_seconds"]
FUTURE_SKEW_SECONDS = 86400
_GENERATED_AT_LIMIT = 4_102_444_800
_COMPONENT_MAXIMUM = WIRE["release_coordinate"]["maximum"]
_MAXIMUM_SLOTS = WIRE["allowlist_maximum_slots"]


class CatalogError(ValueError):
    def __init__(self, reason: str = "malformed"):
        self.reason = reason if reason in {"missing", "malformed", "stale"} else "malformed"
        super().__init__("telemetry_release_catalog_invalid")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse would echo the rejected argument. Operator paths stay unprinted.
        raise CatalogError


class ReleaseCatalog:
    """One validated allowlist and the slot map a single week is allowed to use."""

    __slots__ = ("releases", "by_coordinate", "unlisted_index")

    def __init__(self, releases: tuple[dict, ...]):
        self.releases = releases
        self.by_coordinate = {
            (item["major"], item["minor"], item["patch"]): item for item in releases
        }
        self.unlisted_index = len(releases)


class CatalogAdoption:
    """Where the snapshot came from. This is not a row in the public aggregate."""

    __slots__ = ("state", "reason", "source", "generated_at", "snapshot")

    def __init__(self, state: str, reason: str | None, source: str, generated_at, snapshot):
        self.state = state
        self.reason = reason
        self.source = source
        self.generated_at = generated_at
        self.snapshot = snapshot

    def describe(self) -> dict:
        return {
            "state": self.state,
            "reason": self.reason,
            "source": self.source,
            "generated_at": self.generated_at,
            "release_ids": [item["id"] for item in self.snapshot.releases],
        }


def validate_releases(releases: object) -> ReleaseCatalog:
    """Contiguous reviewed coordinates, at most the bundled slot maximum."""
    if type(releases) not in (list, tuple) or not 1 <= len(releases) <= _MAXIMUM_SLOTS:
        raise WireV3Error
    copied = []
    seen = set()
    for index, item in enumerate(releases):
        if type(item) is not dict or set(item) != {"slot", "major", "minor", "patch", "id"}:
            raise WireV3Error
        major, minor, patch = item["major"], item["minor"], item["patch"]
        parts = (major, minor, patch)
        if (
            any(type(part) is not int or not 0 <= part <= _COMPONENT_MAXIMUM for part in parts)
            or item["slot"] != index
        ):
            raise WireV3Error
        identity = f"{major}.{minor}.{patch}"
        if item["id"] != identity or identity in seen or identity == UNLISTED:
            raise WireV3Error
        seen.add(identity)
        copied.append(
            {"slot": index, "major": major, "minor": minor, "patch": patch, "id": identity}
        )
    return ReleaseCatalog(tuple(copied))


def snapshot_from_allowlist() -> ReleaseCatalog:
    """The allowlist imported with this process, not a file a peer can replace."""
    return validate_releases(wire_v3.ALLOWLIST)


def _seconds(value: object) -> int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise CatalogError
    seconds = int(value)
    if seconds < 0 or seconds > _GENERATED_AT_LIMIT:
        raise CatalogError
    return seconds


def _document(snapshot: ReleaseCatalog, generated_at: int) -> dict:
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "generated_at": generated_at,
        "release_allowlist": [dict(item) for item in snapshot.releases],
    }


def _atomic_write(path: Path, text: str) -> None:
    """Replace one regular file in its own directory. A crash keeps the previous file."""
    if path.is_symlink():
        raise CatalogError
    directory = path.parent
    if directory.is_symlink() or not directory.is_dir():
        raise CatalogError
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".release-catalog.", suffix=".pending", dir=directory
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            with suppress(OSError):
                os.unlink(temporary)
    if os.name == "posix":
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def install_catalog(directory: Path, releases: object, *, generated_at: int) -> Path:
    """Write a local catalog after the same coordinate check the collector uses."""
    if type(generated_at) is not int or not 0 <= generated_at <= _GENERATED_AT_LIMIT:
        raise CatalogError
    if not isinstance(directory, Path) or not directory.is_absolute() or directory.is_symlink():
        raise CatalogError
    snapshot = validate_releases(releases)
    destination = directory / FILENAME
    _atomic_write(destination, json.dumps(_document(snapshot, generated_at), indent=2) + "\n")
    return destination


def _read_capped_text(path: Path) -> str:
    """Read at most one byte past the catalog ceiling from the opened handle."""
    with path.open("rb", buffering=0) as handle:
        blob = handle.read(MAX_LOCAL_BYTES + 1)
    if type(blob) is not bytes or not 0 < len(blob) <= MAX_LOCAL_BYTES:
        raise CatalogError
    return blob.decode("utf-8")


def _parse_json(payload: object):
    """Parser failures, including nesting past the recursion ceiling, are catalog errors."""
    try:
        return json.loads(payload)
    except (RecursionError, OverflowError, UnicodeError, ValueError, TypeError):
        raise CatalogError from None


def read_local(path: Path, now: object) -> tuple[ReleaseCatalog, int] | str:
    """Load one local file. The reason is missing, malformed, or stale; packets stay valid."""
    try:
        if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
            return "malformed"
        if not path.exists():
            return "missing"
        if not path.is_file():
            return "malformed"
        document = _parse_json(_read_capped_text(path))
        if (
            type(document) is not dict
            or set(document) != LOCAL_KEYS
            or document.get("schema_name") != SCHEMA_NAME
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("source") != SOURCE
        ):
            return "malformed"
        generated_at = document.get("generated_at")
        if type(generated_at) is not int or not 0 <= generated_at <= _GENERATED_AT_LIMIT:
            return "malformed"
        snapshot = validate_releases(document.get("release_allowlist"))
        seconds = _seconds(now)
    except (
        CatalogError,
        OSError,
        UnicodeError,
        RecursionError,
        OverflowError,
        WireV3Error,
        TypeError,
        ValueError,
    ):
        return "malformed"
    if generated_at > seconds + FUTURE_SKEW_SECONDS or generated_at < seconds - FRESHNESS_SECONDS:
        return "stale"
    return snapshot, generated_at


def adopt_catalog(path: Path | None, *, now: object, previous: CatalogAdoption | None = None):
    """Choose a snapshot without clearing counters. Callers seal a week on their own."""
    try:
        if path is None:
            if previous is not None:
                return previous
            return CatalogAdoption("bundled", None, BUNDLED_SOURCE, None, snapshot_from_allowlist())
        if not isinstance(path, Path):
            found = "malformed"
        else:
            found = read_local(path, now)
    except (
        CatalogError,
        OSError,
        WireV3Error,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
    ):
        found = "malformed"
    if type(found) is tuple:
        snapshot, generated_at = found
        return CatalogAdoption("local", None, SOURCE, generated_at, snapshot)
    reason = found if found in {"missing", "malformed", "stale"} else "malformed"
    if previous is not None and previous.state in {"local", "retained"}:
        return CatalogAdoption(
            "retained", reason, previous.source, previous.generated_at, previous.snapshot
        )
    try:
        snapshot = snapshot_from_allowlist()
    except WireV3Error:
        if previous is not None:
            return previous
        raise
    return CatalogAdoption("bundled", reason, BUNDLED_SOURCE, None, snapshot)


def recover_catalog(previous: CatalogAdoption | None) -> CatalogAdoption:
    """Last valid snapshot, or the bundled allowlist, after a read that must not escape."""
    if previous is not None and previous.state in {"local", "retained"}:
        return CatalogAdoption(
            "retained", "malformed", previous.source, previous.generated_at, previous.snapshot
        )
    if previous is not None:
        return CatalogAdoption("bundled", "malformed", BUNDLED_SOURCE, None, previous.snapshot)
    return CatalogAdoption("bundled", "malformed", BUNDLED_SOURCE, None, snapshot_from_allowlist())


def catalog_path_for(publisher: object) -> Path | None:
    """State directory of the v3 store. A publisher without one keeps the bundled list."""
    root = getattr(publisher, "root", None)
    if isinstance(root, Path) and root.is_absolute() and not root.is_symlink():
        return root / FILENAME
    return None


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CatalogError


def _default_open(request, timeout):
    opener = urllib.request.build_opener(_RefuseRedirects())
    return opener.open(request, timeout=timeout)


def _read_bounded(response) -> bytes:
    chunks = []
    total = 0
    while True:
        block = response.read(8192)
        if not block:
            break
        if type(block) is not bytes:
            raise CatalogError
        total += len(block)
        if total > MAX_WIRE_BYTES:
            raise CatalogError
        chunks.append(block)
    return b"".join(chunks)


def allowlist_from_public_wire(document: object) -> ReleaseCatalog:
    """Keep release coordinates only. Metric rows and packet layout stay on this build."""
    if type(document) is not dict:
        raise CatalogError
    if (
        document.get("version") != 3
        or document.get("packet_bytes") != PACKET_BYTES
        or document.get("allowlist_maximum_slots") != _MAXIMUM_SLOTS
        or document.get("unlisted_release_id") != UNLISTED
    ):
        raise CatalogError
    try:
        return validate_releases(document.get("release_allowlist"))
    except WireV3Error:
        raise CatalogError from None


def fetch_public_allowlist(opener=None) -> ReleaseCatalog:
    request = urllib.request.Request(
        SOURCE,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    if request.get_header("Authorization") is not None or request.full_url != SOURCE:
        raise CatalogError
    open_request = opener or _default_open
    try:
        with open_request(request, 15) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = getattr(response, "code", None)
            final = response.geturl() if hasattr(response, "geturl") else ""
            if status != 200 or final != SOURCE:
                raise CatalogError
            payload = _read_bounded(response)
    except CatalogError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise CatalogError from None
    return allowlist_from_public_wire(_parse_json(payload))


def sync_catalog(state: Path, *, now: object = None, opener=None) -> Path:
    """Validate the public document, then atomically replace the local catalog."""
    if (
        not isinstance(state, Path)
        or not state.is_absolute()
        or state.is_symlink()
        or not state.is_dir()
    ):
        raise CatalogError
    snapshot = fetch_public_allowlist(opener)
    generated_at = _seconds(time.time() if now is None else now)
    return install_catalog(state, snapshot.releases, generated_at=generated_at)


def main(argv=None) -> int:
    parser = _Parser(description="Refresh the public Mnemion v3 release catalog")
    parser.add_argument("command", choices=("sync",))
    parser.add_argument("--state", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        if not args.state.is_absolute():
            raise CatalogError
        sync_catalog(args.state)
    except CatalogError:
        print('{"error":"telemetry_release_catalog_sync_failed"}', file=sys.stderr)
        return 1
    except Exception:
        print('{"error":"telemetry_release_catalog_sync_failed"}', file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
