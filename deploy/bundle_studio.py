#!/usr/bin/env python3
"""Build and stage the matching web Studio and notices in Python distributions."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mnemion.service.studio import (  # noqa: E402
    MAX_BUNDLE_BYTES,
    MAX_BUNDLE_FILES,
    MAX_FILE_BYTES,
    bundle_files,
    npm_command,
    validate_bundle,
)
from mnemion.version import __version__  # noqa: E402


@contextmanager
def build_lock(root: Path):
    root.mkdir(exist_ok=True)
    path = root / "web-studio.lock"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "Another Studio build owns build-tmp/web-studio.lock. "
            "Remove a stale lock only after confirming its builder has stopped."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()) + "\n")
        yield
    finally:
        path.unlink(missing_ok=True)


def install_bundle(staged: Path, destination: Path) -> None:
    """Keep the previous bundle until the complete new build can be renamed."""
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError("Studio staging destination must be a regular directory")
    backup = staged.parent / "previous"
    previous = destination.exists()
    if previous:
        destination.replace(backup)
    try:
        staged.replace(destination)
    except BaseException:
        if previous:
            backup.replace(destination)
        raise
    if previous:
        shutil.rmtree(backup)


def verify_python_distributions(artifacts: Path, version: str) -> dict:
    """Independently inspect both uploaded Python formats, with bounded extraction."""
    summaries = {}
    inventories = []
    for extension in ("whl", "tar.gz"):
        name = (
            f"mnemion-{version}-py3-none-any.whl"
            if extension == "whl"
            else f"mnemion-{version}.tar.gz"
        )
        package = artifacts / name
        if package.is_symlink() or not package.is_file():
            raise ValueError("The release requires both Python packages with bundled Studio")
        wheel = extension == "whl"
        prefix = "mnemion/_studio/" if wheel else f"mnemion-{version}/mnemion/_studio/"
        with tempfile.TemporaryDirectory(prefix="mnemion-studio-review-") as temporary:
            destination = Path(temporary)
            archive = zipfile.ZipFile(package) if wheel else tarfile.open(package, "r:gz")
            total, seen = 0, set()
            with archive:
                entries = archive.infolist() if wheel else archive.getmembers()
                for entry in entries:
                    full_name = entry.filename if wheel else entry.name
                    if not full_name.startswith(prefix):
                        continue
                    relative = full_name.removeprefix(prefix)
                    parts = PurePosixPath(relative)
                    if (
                        parts.is_absolute()
                        or ".." in parts.parts
                        or "\\" in relative
                        or relative.rstrip("/") != parts.as_posix()
                    ):
                        if not relative:  # The bundle's directory entry.
                            continue
                        raise ValueError("Unsafe path in packaged Studio")
                    mode = stat.S_IFMT(entry.external_attr >> 16) if wheel else None
                    if (wheel and mode not in (0, stat.S_IFREG, stat.S_IFDIR)) or (
                        not wheel and not (entry.isfile() or entry.isdir())
                    ):
                        raise ValueError("Packaged Studio must contain regular files")
                    if entry.is_dir() if wheel else entry.isdir():
                        continue
                    size = entry.file_size if wheel else entry.size
                    total += size
                    if (
                        relative in seen
                        or len(seen) > MAX_BUNDLE_FILES
                        or size > MAX_FILE_BYTES
                        or total > MAX_BUNDLE_BYTES + 1_000_000
                    ):
                        raise ValueError("Packaged Studio exceeds its budget or repeats a path")
                    seen.add(relative)
                    stream = archive.open(entry) if wheel else archive.extractfile(entry)
                    with stream:
                        content = stream.read(MAX_FILE_BYTES + 1)
                    if len(content) != size:
                        raise ValueError("Packaged Studio has invalid file lengths")
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
            metadata = validate_bundle(destination, version)
            inventories.append(metadata["files"])
            summaries[name] = {"studio_files": len(seen), "studio_bytes": total}
    if inventories[0] != inventories[1]:
        raise ValueError("Wheel and source package contain different Studio builds")
    return summaries


def build(root: Path) -> dict:
    root = root.resolve()
    if root != ROOT:
        raise ValueError("Use the build recipe belonging to the selected checkout")
    frontend = root / "studio/frontend"
    for path in (frontend / "package.json", root / "packages/client/package.json"):
        if json.loads(path.read_text(encoding="utf-8"))["version"] != __version__:
            raise ValueError("Studio and Python package versions differ")
    npm = npm_command()
    environment = {**os.environ, "npm_execpath": npm[1]}
    environment.pop("ELECTRON_BUILD", None)
    # Runtime credentials are unrelated to a public frontend build.
    for key in (
        "MNEMION_DATABASE_URL",
        "MNEMION_WORKER_DATABASE_URL",
        "MNEMION_ADMIN_DATABASE_URL",
        "MNEMION_API_KEY",
    ):
        environment.pop(key, None)
    for project in (root / "packages/client", frontend):
        subprocess.run(
            [*npm, "--prefix", str(project), "ci", "--no-fund", "--no-audit"],
            env=environment,
            check=True,
            timeout=600,
        )
        subprocess.run(
            [*npm, "--prefix", str(project), "run", "build"],
            env=environment,
            check=True,
            timeout=600,
        )
    source = frontend / "dist"
    bundle_files(source)
    build_root = root / "build-tmp"
    build_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="web-studio-", dir=build_root) as temporary:
        staged = Path(temporary) / "studio"
        shutil.copytree(source, staged)
        subprocess.run(
            [
                sys.executable,
                str(root / "deploy/notices.py"),
                "--root",
                str(root),
                "--output",
                str(staged / "notices"),
                "--frontend",
                str(frontend),
            ],
            env=environment,
            check=True,
            timeout=120,
        )
        files = bundle_files(staged)
        metadata = {"schema": 1, "version": __version__, "base": "/", "files": files}
        (staged / "release.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        validate_bundle(staged)
        install_bundle(staged, root / "mnemion/_studio")
    return {
        "version": __version__,
        "files": len(files),
        "bytes": sum(item["size"] for item in files.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verify-artifacts", type=Path)
    args = parser.parse_args()
    if args.verify_artifacts:
        result = verify_python_distributions(args.verify_artifacts, __version__)
    else:
        with build_lock(ROOT / "build-tmp"):
            result = build(args.root)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
