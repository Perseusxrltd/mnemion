"""Discover the packaged web UI and build an explicit source checkout."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

from ..version import __version__

MAX_FILE_BYTES = 16_000_000
MAX_BUNDLE_BYTES = 64_000_000
MAX_BUNDLE_FILES = 4000


def bundle_files(path: Path) -> dict:
    """Hash a bounded, regular-file bundle without following links."""
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Studio must be a regular directory")
    files = {}
    total = 0
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ValueError("Studio artifacts cannot contain symlinks")
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError("Studio artifacts must be regular files")
        name = item.relative_to(path).as_posix()
        if name == "release.json":
            continue
        size = item.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_BUNDLE_BYTES or len(files) >= MAX_BUNDLE_FILES:
            raise ValueError("Studio artifacts exceed the package budget")
        with item.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files[name] = {"size": size, "sha256": digest}
    if "index.html" not in files or not any(name.startswith("assets/") for name in files):
        raise ValueError("Build the web frontend before staging Studio")
    return files


def validate_bundle(path: Path, version: str = __version__) -> dict:
    manifest = path / "release.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 1_000_000:
        raise ValueError("Packaged Studio is incomplete; reinstall the official release")
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or (
        metadata.get("schema"),
        metadata.get("version"),
        metadata.get("base"),
    ) != (1, version, "/"):
        raise ValueError(
            "Packaged Studio does not match this service version. Run mnemion-service studio "
            "build in a source checkout, or reinstall the matching official release."
        )
    files = metadata.get("files")
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_BUNDLE_FILES:
        raise ValueError("Packaged Studio has an invalid file inventory")
    for name, item in files.items():
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or relative.as_posix() != name
            or name == "release.json"
            or not isinstance(item, dict)
            or type(item.get("size")) is not int
            or not 0 <= item["size"] <= MAX_FILE_BYTES
            or not isinstance(item.get("sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
        ):
            raise ValueError("Packaged Studio has an invalid file inventory")
    if files != bundle_files(path):
        raise ValueError("Packaged Studio files do not match; reinstall the official release")
    if not {"notices/LICENSE", "notices/NOTICE", "notices/inventory.json"} <= files.keys():
        raise ValueError("Packaged Studio is missing dependency notices")
    if 'src="/assets/' not in (path / "index.html").read_text(encoding="utf-8"):
        raise ValueError("Packaged Studio must use the web build, with absolute asset paths")
    return metadata


def source_root() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    manifest = root / "studio/frontend/package.json"
    if not (root / "pyproject.toml").is_file() or not manifest.is_file():
        return None
    if json.loads(manifest.read_text(encoding="utf-8")).get("name") != "mnemion-studio":
        return None
    return root


def _ready(path: Path) -> bool:
    return (path / "index.html").is_file() and (path / "assets").is_dir()


def resolve_studio() -> tuple[Path | None, str]:
    if os.environ.get("MNEMION_STUDIO_ENABLED") == "0":
        return None, "disabled"
    if selected := os.environ.get("MNEMION_STUDIO_DIST"):
        path = Path(selected).expanduser().resolve()
        if not _ready(path):
            raise ValueError("MNEMION_STUDIO_DIST must contain a built Studio frontend")
        return path, "explicit"
    bundled = Path(__file__).resolve().parents[1] / "_studio"
    if bundled.exists():
        validate_bundle(bundled)
        return bundled, "bundled"
    root = source_root()
    if root and _ready(root / "studio/frontend/dist"):
        return root / "studio/frontend/dist", "checkout"
    return None, "not_built"


def studio_status() -> dict:
    path, source = resolve_studio()
    return {
        "available": path is not None,
        "source": source,
        "version": __version__,
        "path": str(path) if path else None,
        "build_command": "mnemion-service studio build" if source_root() else None,
    }


def npm_command() -> list[str]:
    """Use npm's JS entry point, including Windows, without a command shell."""
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node:
        raise ValueError("Studio source builds require Node.js 22 or later with npm")
    candidates = []
    if entry := os.environ.get("npm_execpath"):
        candidates.append(Path(entry))
    if npm:
        resolved = Path(npm).resolve()
        if resolved.name == "npm-cli.js":
            candidates.append(resolved)
        candidates.append(Path(npm).parent / "node_modules/npm/bin/npm-cli.js")
    candidates.append(Path(node).parent / "node_modules/npm/bin/npm-cli.js")
    script = next((path for path in candidates if path.is_file()), None)
    if script is None:
        raise ValueError("Cannot locate npm-cli.js; install Node.js with npm or set npm_execpath")
    version = subprocess.run(
        [node, "--version"], check=True, capture_output=True, text=True, timeout=10
    )
    try:
        major = int(version.stdout.strip().removeprefix("v").split(".")[0])
    except ValueError:
        major = 0
    if major < 22:
        raise ValueError("Studio source builds require Node.js 22 or later")
    return [node, str(script)]


def build_studio() -> dict:
    root = source_root()
    if root is None:
        raise ValueError(
            "Build Studio from a source checkout; official release packages include it"
        )
    # The repository owns the reviewed build recipe. No database or provider
    # credential is needed, and no shell command is accepted from an API.
    recipe = root / "deploy/bundle_studio.py"
    if not recipe.is_file():
        raise ValueError("This checkout is missing the Studio build recipe")
    subprocess.run(
        [sys.executable, str(recipe), "--root", str(root)], check=True, stdout=sys.stderr
    )
    return studio_status()
