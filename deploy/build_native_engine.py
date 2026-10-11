"""Freeze the locked service, CPU model drivers and local operator for Studio."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from deploy.build_native_postgres import host_target
from deploy.probe_native_postgres import executable_architecture

ROOT = Path(__file__).resolve().parents[1]


def build(work: Path, output: Path) -> Path:
    operating_system, architecture = host_target()
    if work.exists() or output.exists():
        raise ValueError("Use new engine build and output directories")
    if importlib.metadata.version("pyinstaller") != "6.22.3":
        raise ValueError("Use the reviewed PyInstaller 6.22.3 build environment")
    if importlib.metadata.version("fastembed") != "0.9.0":
        raise ValueError("The frozen engine must use the pinned inference runtime")
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "mnemion-engine",
        "--onedir",
        "--clean",
        "--noupx",
        "--paths",
        str(ROOT),
        "--distpath",
        str(work / "frozen"),
        "--workpath",
        str(work / "analysis"),
        "--specpath",
        str(work),
        "--hidden-import",
        "mnemion.service.api",
        "--collect-submodules",
        "uvicorn",
        "--collect-submodules",
        "fastembed",
        "--collect-data",
        "mnemion.service",
    ]
    for distribution in ("fastembed", "onnxruntime", "tokenizers", "huggingface_hub"):
        command += ["--copy-metadata", distribution]
    for excluded in ("chromadb", "torch", "pytest", "tkinter"):
        command += ["--exclude-module", excluded]
    command.append(str(ROOT / "studio/engine/main.py"))
    subprocess.run(command, cwd=ROOT, check=True)
    frozen = work / "frozen/mnemion-engine"
    for path in frozen.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(frozen.resolve()):
            raise ValueError("The engine contains a link outside its own package")
    # File aliases become regular files so all archive consumers use the same
    # bounded extraction policy on Windows, macOS and Linux.
    runtime = output / "mnemion-engine"
    shutil.copytree(frozen, runtime, symlinks=False)
    binary = runtime / ("mnemion-engine.exe" if os.name == "nt" else "mnemion-engine")
    if executable_architecture(binary) != architecture:
        raise ValueError("The frozen engine does not match the build architecture")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "deploy.notices",
            "--root",
            str(ROOT),
            "--python",
            "--analysis",
            str(work / "analysis/mnemion-engine/Analysis-00.toc"),
            "--output",
            str(runtime / "licenses"),
        ],
        cwd=ROOT,
        check=True,
    )
    from mnemion.version import __version__

    files = {}
    for path in sorted(runtime.rglob("*")):
        if path.is_symlink():
            raise ValueError("Engine aliases were not flattened")
        if path.is_file():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files[path.relative_to(runtime).as_posix()] = {
                "sha256": digest,
                "size": path.stat().st_size,
                "executable": bool(path.stat().st_mode & 0o111),
            }
    if len(files) > 10000 or sum(row["size"] for row in files.values()) > 768 * 1024**2:
        raise ValueError("The frozen engine exceeds its packaging budget")
    metadata = {
        "format": 1,
        "component": "service",
        "version": __version__,
        "platform": operating_system,
        "architecture": architecture,
        "python": sys.version.split()[0],
        "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "model_weights_bundled": False,
        "files": files,
    }
    (runtime / "mnemion-runtime.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    archive = output / f"mnemion-engine-{__version__}-{operating_system}-{architecture}.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(runtime.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(runtime).as_posix())
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"archive": str(build(args.work.resolve(), args.output.resolve()))}))


if __name__ == "__main__":
    main()
