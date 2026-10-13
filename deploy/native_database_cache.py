"""Fingerprint native database builds without reusing another compiler image."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys

from deploy.build_native_postgres import host_target

INPUTS = (
    ".github/workflows/native-runtime.yml",
    "deploy/build_native_postgres.py",
    "deploy/native-postgres.json",
    "deploy/native_database_cache.py",
    "deploy/windows-native-runtime.manifest",
)


def cache_key(
    root: Path,
    *,
    target: str,
    architecture: str,
    image_os: str,
    image_version: str,
    python_version: str,
) -> str | None:
    if target not in {"linux", "macos", "windows"} or architecture not in {"x64", "arm64"}:
        raise ValueError("Unknown native database cache target")
    # Custom/missing runner metadata falls back to compiling. Never share an
    # ambiguous 'unknown image' cache across machines or compiler toolchains.
    if not all(
        isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value)
        for value in (image_os, image_version, python_version)
    ):
        return None
    sources = {}
    for name in INPUTS:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Native cache input must be an ordinary repository file")
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    identity = {
        "format": 1,
        "target": target,
        "architecture": architecture,
        "image_os": image_os,
        "image_version": image_version,
        "python_version": python_version,
        "sources": sources,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return f"native-postgres-v1-{target}-{architecture}-{hashlib.sha256(encoded).hexdigest()}"


def main() -> None:
    target, architecture = host_target()
    key = cache_key(
        Path(__file__).resolve().parents[1],
        target=target,
        architecture=architecture,
        image_os=os.environ.get("ImageOS", ""),
        image_version=os.environ.get("ImageVersion", ""),
        python_version=".".join(str(value) for value in sys.version_info[:3]),
    )
    print("eligible=" + ("true" if key else "false"))
    print("key=" + (key or ""))


if __name__ == "__main__":
    main()
