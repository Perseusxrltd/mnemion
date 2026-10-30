"""Select verified OS/architecture pairs without holding ready downloads back."""

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
    {"os": "macos-26", "arch": "arm64", "platform": "macos"},
]


def database_targets(desktops: list[dict]) -> list[dict]:
    """Windows ARM runs the separately probed x64 database, once per build."""
    selected = {
        (item["platform"], "x64" if item["platform"] == "windows" else item["arch"])
        for item in desktops
    }
    return [
        {"os": item["os"], "target": item["platform"], "arch": item["arch"]}
        for item in MATRIX
        if (item["platform"], item["arch"]) in selected
    ]


def release_targets(version: str | None = None, path: Path | None = None) -> dict[str, list[str]]:
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
    architectures = data.get(
        "architectures", {platform: ["x64", "arm64"] for platform in platforms}
    )
    if (
        not isinstance(architectures, dict)
        or set(architectures) != set(platforms)
        or any(
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or value not in {"x64", "arm64"} for value in values)
            or len(set(values)) != len(values)
            for values in architectures.values()
        )
    ):
        raise ValueError("Each selected platform needs explicit, unique supported architectures")
    return {platform: architectures[platform] for platform in platforms}


def release_platforms(version: str | None = None, path: Path | None = None) -> list[str]:
    return list(release_targets(version, path))


def reviewed_targets(selection: str) -> list[dict]:
    """Select matrix rows by OS name. Empty keeps the full six-target matrix."""
    if selection.strip() == "":
        return list(MATRIX)
    parts = [part.strip() for part in selection.split(",")]
    if not parts or any(part == "" for part in parts) or len(parts) != len(set(parts)):
        raise ValueError("Telemetry delivery targets must be unique comma-separated matrix OS names")
    known = {item["os"] for item in MATRIX}
    if any(part not in known for part in parts):
        raise ValueError("Telemetry delivery targets include a name outside the release matrix")
    selected = set(parts)
    return [item for item in MATRIX if item["os"] in selected]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--macos-only", action="store_true")
    parser.add_argument("--windows-only", action="store_true")
    parser.add_argument("--architecture", choices=["all", "x64", "arm64"], default="all")
    parser.add_argument("--targets", default="", help="Comma-separated matrix OS names. Empty selects all six.")
    args = parser.parse_args()
    if args.targets and (args.release or args.macos_only or args.windows_only or args.architecture != "all"):
        raise SystemExit("Reviewed delivery targets cannot be combined with another selector")
    if args.targets:
        try:
            desktops = reviewed_targets(args.targets)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        print("matrix=" + json.dumps(desktops))
        print("database_matrix=" + json.dumps(database_targets(desktops)))
        return
    selected = (
        release_targets()
        if args.release
        else {
            platform: ["x64", "arm64"] if args.architecture == "all" else [args.architecture]
            for platform in (
                ["macos"]
                if args.macos_only
                else ["windows"]
                if args.windows_only
                else ["windows", "macos", "linux"]
            )
        }
    )
    desktops = [item for item in MATRIX if item["arch"] in selected.get(item["platform"], [])]
    print("matrix=" + json.dumps(desktops))
    print("database_matrix=" + json.dumps(database_targets(desktops)))


if __name__ == "__main__":
    main()
