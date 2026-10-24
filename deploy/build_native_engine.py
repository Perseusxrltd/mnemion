"""Freeze the locked service, CPU model drivers and local operator for Studio."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from xml.dom import minidom
import zipfile

from deploy.probe_native_postgres import executable_architecture
from deploy.native_resources import source_digest

ROOT = Path(__file__).resolve().parents[1]


def windows_manifest(template: bytes) -> bytes:
    """Add UTF-8 while preserving PyInstaller's UAC, compatibility and long paths."""
    with minidom.parseString(template) as document:
        settings = document.getElementsByTagName("windowsSettings")
        if len(settings) != 1 or document.getElementsByTagName("activeCodePage"):
            raise ValueError("Review the changed PyInstaller Windows manifest")
        namespace = "http://schemas.microsoft.com/SMI/2019/WindowsSettings"
        codepage = document.createElementNS(namespace, "activeCodePage")
        codepage.setAttribute("xmlns", namespace)
        codepage.appendChild(document.createTextNode("UTF-8"))
        settings[0].appendChild(codepage)
        return document.toxml(encoding="UTF-8")


def build(work: Path, output: Path) -> Path:
    # Windows ARM currently runs the complete x64 backend: the locked
    # psycopg-binary distribution has no Windows ARM wheel. Inspect Python's PE
    # header, since platform.machine() can report the physical ARM host even
    # when this interpreter and PyInstaller bootloader run as x64.
    operating_system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(
        platform.system()
    )
    architecture = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine().lower()
    )
    if operating_system == "windows":
        architecture = executable_architecture(Path(sys.executable))
        if architecture != "x64":
            raise ValueError("Use x64 Python for the locked Windows service backend")
    if not operating_system or not architecture:
        raise ValueError("Unsupported native engine build target")
    if work.exists() or output.exists():
        raise ValueError("Use new engine build and output directories")
    if importlib.metadata.version("pyinstaller") != "6.22.3":
        raise ValueError("Use the reviewed PyInstaller 6.22.3 build environment")
    if importlib.metadata.version("fastembed") != "0.9.0":
        raise ValueError("The frozen engine must use the pinned inference runtime")
    if importlib.metadata.version("ngrok") != "1.7.0":
        raise ValueError("The frozen engine must use the reviewed ngrok SDK")
    from deploy.bundle_studio import build as build_studio, build_lock

    # The hosted browser and consent page use the matching web build. The
    # Electron file:// build remains a separate resource with its own base.
    with build_lock(ROOT / "build-tmp"):
        build_studio(ROOT)
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
        "--collect-data",
        "mnemion.product_telemetry",
        "--collect-all",
        "ngrok",
        "--add-data",
        str(ROOT / "mnemion/_studio") + os.pathsep + "mnemion/_studio",
        "--add-data",
        str(ROOT / "mnemion/assets") + os.pathsep + "mnemion/assets",
    ]
    for distribution in ("fastembed", "onnxruntime", "tokenizers", "huggingface_hub", "ngrok"):
        command += ["--copy-metadata", distribution]
    for excluded in ("chromadb", "torch", "pytest", "tkinter"):
        command += ["--exclude-module", excluded]
    if operating_system == "windows":
        from PyInstaller.utils.win32.winmanifest import create_application_manifest

        manifest = work / "mnemion-engine.manifest"
        manifest.write_bytes(windows_manifest(create_application_manifest()))
        command += ["--manifest", str(manifest)]
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
    # Exercise the actual frozen interpreter and SSH dependencies before the
    # archive can enter any of the longer installed desktop journeys.
    from deploy.probe_native_host_control import run as probe_host_client

    print(json.dumps({"native_host_client": probe_host_client(binary)}), flush=True)
    if operating_system == "windows":
        from PyInstaller.utils.win32.winmanifest import read_manifest_from_executable

        with minidom.parseString(read_manifest_from_executable(str(binary))) as document:
            codepages = document.getElementsByTagName("activeCodePage")
            if len(codepages) != 1 or codepages[0].firstChild.nodeValue != "UTF-8":
                raise ValueError("The frozen service must use UTF-8 for native library file paths")
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
        "source_sha256": source_digest(ROOT),
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
