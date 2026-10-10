"""Select complete native platforms without holding ready releases for pending ones."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MATRIX = [
    {"os": "ubuntu-22.04", "arch": "x64", "platform": "linux"},
    {"os": "ubuntu-22.04-arm", "arch": "arm64", "platform": "linux"},
    {"os": "windows-2022", "arch": "x64", "platform": "windows"},
    {"os": "windows-11-arm", "arch": "arm64", "platform": "windows"},
    {"os": "macos-15-intel", "arch": "x64", "platform": "macos"},
    {"os": "macos-15", "arch": "arm64", "platform": "macos"},
]


def release_platforms(version: str | None = None, path: Path | None = None) -> list[str]:
    path = path or Path(__file__).with_name("release-targets.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    platforms = data.get("platforms") if isinstance(data, dict) else None
    if (
        not isinstance(platforms, list)
        or not platforms
        or any(
            not isinstance(item, str) or item not in {"windows", "macos", "linux"}
            for item in platforms
        )
        or len(set(platforms)) != len(platforms)
        or (version is not None and data.get("version") != version)
    ):
        raise ValueError("Release targets must match the version and name complete platforms")
    return platforms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--macos-only", action="store_true")
    parser.add_argument("--windows-only", action="store_true")
    args = parser.parse_args()
    platforms = (
        release_platforms()
        if args.release
        else (
            ["macos"]
            if args.macos_only
            else ["windows"]
            if args.windows_only
            else ["windows", "macos", "linux"]
        )
    )
    print("matrix=" + json.dumps([item for item in MATRIX if item["platform"] in platforms]))


if __name__ == "__main__":
    main()
