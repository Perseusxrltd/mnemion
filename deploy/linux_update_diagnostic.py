"""Separate, instrumented Linux investigation; never a public update acceptance gate.

The public AppImage is verified, copied and extracted. Inspector mode changes
only the copied runtime's inspector fuse. Timer experiments instead trace the
existing restart callback, with an optional timer-reference change and no
debugger. Feeds and safety guards remain unchanged; no user profile is admitted.
"""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import threading
import time

from deploy.public_update_probe import (
    app_archive,
    app_processes,
    asar_json,
    child_environment,
    download,
    install,
    installer_name,
    linux_idle_seconds,
    linux_login_entry,
    profiles,
    release,
)


def observe(tag: str, architecture: str, root: Path, mode: str = "inspect") -> None:
    import psutil

    root = root.resolve()
    native_arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
    if (
        platform.system() != "Linux"
        or architecture != native_arch
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        or root.exists()
        or root == Path(os.environ["RUNNER_TEMP"]).resolve()
        or not root.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve())
        or any(path.exists() for path in profiles("linux"))
        or linux_login_entry().exists()
    ):
        raise ValueError("Use a fresh matching Linux runner and new RUNNER_TEMP directory")
    source = release(tag)
    asset = next(
        row
        for row in source["assets"]
        if row["name"] == installer_name(source["tag_name"], "linux", architecture)
    )
    root.mkdir(mode=0o700)
    archive = root / asset["name"]
    download(asset, archive)
    env = child_environment()
    image = install(archive, root / "installed with spaces", "linux", env)
    subprocess.run(
        [str(image), "--appimage-extract"],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
        check=True,
    )
    bundle = root / "squashfs-root"
    code = bundle / "resources/app.asar"
    code_digest = hashlib.sha256(code.read_bytes()).hexdigest()
    helper = Path(__file__).with_name("electron_update_snapshot.mjs").resolve()
    prepare = (
        ["--prepare", str(bundle / "mnemion-studio")]
        if mode == "inspect"
        else ["--prepare-timers", str(code), mode, str(root / "timers.jsonl")]
    )
    prepared = subprocess.run(
        ["node", str(helper), *prepare],
        capture_output=True,
        timeout=30,
        check=True,
        text=True,
    )
    if mode == "inspect" and hashlib.sha256(code.read_bytes()).hexdigest() != code_digest:
        raise ValueError("The diagnostic changed application code")
    evidence = {
        **json.loads(prepared.stdout),
        "tag": source["tag_name"],
        "architecture": architecture,
        "source_sha256": asset["digest"],
        "original_asar_sha256": code_digest,
        "mode": mode,
    }
    (root / "diagnostic.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if mode == "mounted-guards":
        repack(image, bundle, env)
        with image.open("rb") as handle:
            evidence["diagnostic_appimage_sha256"] = hashlib.file_digest(
                handle, "sha256"
            ).hexdigest()
    else:
        env.update(APPIMAGE=str(image), APPDIR=str(bundle))
    started = time.time()
    log: deque[bytes] = deque(maxlen=16)
    child = subprocess.Popen(
        [
            str(image if mode == "mounted-guards" else bundle / "AppRun"),
            *(["--inspect=127.0.0.1:0"] if mode == "inspect" else []),
            "--background",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def capture() -> None:
        while chunk := child.stdout.read1(4096):
            log.append(chunk)

    threading.Thread(target=capture, daemon=True).start()
    try:
        deadline = time.monotonic() + 30
        address = None
        while mode == "inspect" and time.monotonic() < deadline and child.poll() is None:
            match = re.search(rb"ws://127\.0\.0\.1:[0-9]+/[a-f0-9-]+", b"".join(list(log)))
            if match:
                address = match[0].decode("ascii")
                break
            time.sleep(0.2)
        if mode == "inspect" and not address:
            raise RuntimeError("The isolated inspector did not start")
        deadline = time.monotonic() + 720
        while time.monotonic() < deadline and child.poll() is None:
            row = {
                "elapsed_seconds": round(time.time() - started, 1),
                "x11_idle_seconds": linux_idle_seconds(),
                "developer_diagnostic_only": True,
            }
            if address:
                snapshot = subprocess.run(
                    ["node", str(helper), address],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=12,
                )
                if snapshot.returncode == 0:
                    row["runtime"] = json.loads(snapshot.stdout)
                else:
                    row["error"] = "snapshot_unavailable"
            row["observed_versions"] = process_versions(image, started)
            with (root / "snapshots.jsonl").open("a") as handle:
                handle.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)
            time.sleep(15)
        # Passive process/filesystem inspection also records the replacement
        # after the original launcher exits. It does not wake Electron's loop.
        if child.poll() is not None:
            time.sleep(15)
        evidence["launcher_exit"] = child.poll()
        evidence["observed_versions"] = process_versions(image, started)
        evidence["installed_files"] = []
        for path in image.parent.glob("*.AppImage"):
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            evidence["installed_files"].append({"name": path.name, "sha256": digest})
        (root / "diagnostic.json").write_text(json.dumps(evidence, indent=2) + "\n")
    finally:
        (root / "application.log").write_bytes(b"".join(list(log))[-32768:])
        for process in app_processes(image, "linux", started):
            try:
                for descendant in process.children(recursive=True):
                    descendant.kill()
                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)


def process_versions(image: Path, started: float) -> list[str]:
    import psutil

    result = set()
    for process in app_processes(image, "linux", started):
        try:
            result.add(asar_json(app_archive(process, "linux"))["version"])
        except (OSError, ValueError, KeyError, psutil.Error):
            pass
    return sorted(result)


def repack(image: Path, bundle: Path, env: dict) -> None:
    """Retain the copied public runtime and mount a diagnostic-only filesystem."""
    offset = int(subprocess.check_output([str(image), "--appimage-offset"], env=env, timeout=10))
    if not 1024 <= offset <= 4 * 1024**2:
        raise ValueError("Review the changed AppImage runtime boundary")
    filesystem = bundle.parent / "diagnostic.squashfs"
    subprocess.run(
        [
            "mksquashfs",
            str(bundle),
            str(filesystem),
            "-noappend",
            "-comp",
            "gzip",
            "-processors",
            "2",
            "-no-progress",
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    replacement = image.with_suffix(".diagnostic")
    with (
        image.open("rb") as source,
        replacement.open("xb") as target,
        filesystem.open("rb") as payload,
    ):
        target.write(source.read(offset))
        shutil.copyfileobj(payload, target)
    replacement.chmod(0o755)
    replacement.replace(image)
    filesystem.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--arch", choices=["x64", "arm64"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=[
            "inspect",
            "original-timers",
            "referenced-timers",
            "mounted-guards",
            "extracted-guards",
        ],
        default="inspect",
    )
    args = parser.parse_args()
    observe(args.tag, args.arch, args.output, args.mode)
