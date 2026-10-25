"""Build the small shared OS network-policy probe using the target system SDK."""

from __future__ import annotations

import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def build(destination: Path, *, architecture: str | None = None) -> Path:
    destination = destination.absolute()
    architecture = architecture or {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(platform.machine().lower())
    if architecture not in {"x64", "arm64"} or destination.suffix != ".node":
        raise ValueError("Use a supported native target and a .node destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    native = ROOT / "mnemion/product_telemetry/native"
    sources = [str(native / name) for name in ("network-state.c", "network-node.c")]
    if sys.platform == "win32":
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "deploy/build_telemetry_network.ps1"),
            "-Architecture",
            architecture,
            "-Destination",
            str(destination),
        ]
    elif sys.platform == "darwin":
        command = [
            "xcrun",
            "clang",
            "-x",
            "objective-c",
            "-fobjc-arc",
            "-fblocks",
            "-std=c11",
            "-arch",
            "x86_64" if architecture == "x64" else "arm64",
            "-mmacosx-version-min=13.0",
            "-O2",
            "-fvisibility=hidden",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-dynamiclib",
            *sources,
            "-framework",
            "Network",
            "-framework",
            "Foundation",
            "-o",
            str(destination),
        ]
    elif sys.platform == "linux":
        host = {"x86_64": "x64", "aarch64": "arm64"}.get(platform.machine().lower())
        if architecture != host:
            raise ValueError("Build Linux probes on the matching native target")
        compiler = shutil.which("cc")
        if not compiler:
            raise ValueError("Building the native OS probe requires the system C compiler")
        command = [
            compiler,
            "-std=c11",
            "-O2",
            "-fPIC",
            "-fvisibility=hidden",
            "-fstack-protector-strong",
            "-D_FORTIFY_SOURCE=2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            *sources,
            "-Wl,-z,relro,-z,now",
            "-pthread",
            "-ldl",
            "-o",
            str(destination),
        ]
    else:
        raise ValueError("The native OS probe needs Windows, macOS or Linux")
    subprocess.run(command, check=True, timeout=120)
    if not destination.is_file() or not 1024 < destination.stat().st_size < 256 * 1024:
        raise ValueError("Inspect the unexpected native probe artifact")
    from deploy.native_resources import binary_target

    expected_platform = {"win32": "windows", "darwin": "macos", "linux": "linux"}[sys.platform]
    if binary_target(destination) != (expected_platform, {architecture}):
        raise ValueError("The network-policy probe does not match the requested native target")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arch", choices=["x64", "arm64"])
    args = parser.parse_args()
    print(build(args.output, architecture=args.arch))


if __name__ == "__main__":
    main()
