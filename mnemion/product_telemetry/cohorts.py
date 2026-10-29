"""Coarse v2 cohort arguments for an already-sampled single view.

Passing these values does not publish fleet data and does not build a v3
report. The v2 encoder still chooses one permitted view per packet.
"""

from __future__ import annotations

import platform
import sys

from mnemion.version import __version__

from .wire import COHORTS


def _family(version: str) -> str:
    major = version.split(".", 1)[0]
    if not major.isdigit():
        return "unobserved"
    number = int(major)
    if number < 4:
        return "before_4"
    if number == 4:
        return "4"
    return "5_plus"


def reviewed_release_coordinate(version: str | None = None) -> tuple[int, int, int] | None:
    """Three release integers from the same version string the v2 family uses."""
    text = __version__ if version is None else version
    parts = text.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        return None
    numbers = tuple(int(part) for part in parts)
    if any(number > 255 for number in numbers):
        return None
    return numbers


def reviewed_operating_system(platform_name: str | None = None) -> str | None:
    """The same coarse OS map as ``reviewed_cohorts``. Missing names fail closed."""
    if platform_name is None:
        platform_name = {"win32": "windows", "darwin": "macos", "linux": "linux"}.get(sys.platform, "other")
    if platform_name not in ("windows", "macos", "linux", "other"):
        return None
    return platform_name


def reviewed_cohorts() -> dict[str, str]:
    """Public OS, CPU family and release family. No machine id and no serial."""
    system = {"win32": "windows", "darwin": "macos", "linux": "linux"}.get(sys.platform, "other")
    machine = platform.machine().lower()
    architecture = "x64" if machine in {"amd64", "x86_64"} else "arm64" if machine in {"aarch64", "arm64"} else "other"
    cohorts = {
        "platform": system,
        "architecture": architecture,
        "release_family": _family(__version__),
    }
    if any(value not in COHORTS[name]["values"] for name, value in cohorts.items()):
        return {}
    return cohorts
