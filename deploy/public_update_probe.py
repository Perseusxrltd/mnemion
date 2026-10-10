"""Observe unmodified public installers updating through their production feeds.

Runs only on disposable GitHub-hosted runners. No fixture entry point, signing
key, feed override, debugger, simulated idle time or disabled sandbox is used.
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
import struct
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from deploy.published_release import API, ORIGIN, NoRedirects, fetch, manifest, version
from deploy.release_targets import MATRIX


def installer_name(tag: str, system: str, architecture: str) -> str:
    version(tag)
    extension = {"windows": "exe", "macos": "dmg", "linux": "AppImage"}[system]
    arch = "x86_64" if (system, architecture) == ("linux", "x64") else architecture
    return f"Mnemion-Studio-{tag[1:]}-{system}-{arch}.{extension}"


def release(tag: str) -> dict:
    if tag != "latest":
        version(tag)
    url = API if tag == "latest" else API.removesuffix("latest") + "tags/" + tag
    data = json.loads(fetch(url, api=True))
    actual_tag = data.get("tag_name")
    version(actual_tag)
    checksums = fetch(f"{ORIGIN}/releases/download/{actual_tag}/SHA256SUMS.txt")
    return manifest(data, checksums)


def select_pairs(target: dict, previous: list[dict]) -> tuple[list[dict], list[str]]:
    """A new architecture needs a first public installer before a public upgrade."""
    target_version = version(target["tag_name"])
    target_assets = {row["name"] for row in target["assets"]}
    candidates = []
    for row in previous:
        if row.get("draft") is not False or row.get("prerelease") is not False:
            continue
        try:
            earlier = version(row.get("tag_name"))
        except ValueError:
            continue
        if earlier < target_version:
            candidates.append(row)
    candidates.sort(key=lambda row: version(row["tag_name"]), reverse=True)
    selected, skipped = [], []
    for pair in MATRIX:
        system, arch = pair["platform"], pair["arch"]
        if installer_name(target["tag_name"], system, arch) not in target_assets:
            continue
        before = next(
            (
                row
                for row in candidates
                if installer_name(row["tag_name"], system, arch)
                in {asset["name"] for asset in row["assets"]}
            ),
            None,
        )
        if before:
            selected.append({**pair, "from": before["tag_name"], "to": target["tag_name"]})
        else:
            skipped.append(f"{system}/{arch}: no earlier public installer")
    return selected, skipped


def download(asset: dict, destination: Path) -> None:
    """Stream verified public bytes; never send credentials to an asset/CDN host."""
    if not 40 * 1024**2 <= asset["size"] <= 1024**3:
        raise ValueError("Installer size is outside the public rehearsal limit")
    url = asset["browser_download_url"]
    opener = build_opener(NoRedirects())
    deadline = time.monotonic() + 300
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        for _ in range(4):
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in {"github.com", "release-assets.githubusercontent.com"}
                or parsed.port not in {None, 443}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
            ):
                raise ValueError("Installer redirect left the approved public hosts")
            try:
                response = opener.open(
                    Request(url, headers={"User-Agent": "Mnemion-public-update-rehearsal"}),
                    timeout=20,
                )
            except HTTPError as error:
                status, location = error.code, error.headers.get("Location")
                error.close()
                if status in {301, 302, 303, 307, 308} and location:
                    url = location
                    continue
                raise RuntimeError(f"Public installer download failed (HTTP {status})") from None
            with response, partial.open("xb") as handle:
                count, digest = 0, hashlib.sha256()
                while chunk := response.read(256 * 1024):
                    count += len(chunk)
                    if count > asset["size"] or time.monotonic() > deadline:
                        raise ValueError("Installer exceeded its declared size or deadline")
                    digest.update(chunk)
                    handle.write(chunk)
                if count != asset["size"] or "sha256:" + digest.hexdigest() != asset["digest"]:
                    raise ValueError(
                        "Public installer did not match the verified release inventory"
                    )
            partial.rename(destination)
            return
        raise ValueError("Too many installer redirects")
    finally:
        partial.unlink(missing_ok=True)


def asar_json(path: Path, name: str = "package.json") -> dict:
    """Read bounded metadata from an ASAR without extracting or changing it."""
    with path.open("rb") as handle:
        first = handle.read(8)
        if len(first) != 8:
            raise ValueError("Missing ASAR header")
        payload, size = struct.unpack("<II", first)
        if payload != 4 or not 8 <= size <= 4 * 1024**2 or size % 4:
            raise ValueError("Invalid ASAR header size")
        header = handle.read(size)
        if len(header) != size:
            raise ValueError("Truncated ASAR header")
        payload, length = struct.unpack("<II", header[:8])
        if payload != size - 4 or not 1 <= length <= size - 8:
            raise ValueError("Invalid ASAR header payload")
        entry = json.loads(header[8 : 8 + length])
        for component in name.split("/"):
            if component in {"", ".", ".."}:
                raise ValueError("Invalid ASAR metadata path")
            entry = entry["files"][component]
        offset, length = entry.get("offset"), entry.get("size")
        if (
            entry.get("unpacked")
            or not isinstance(offset, str)
            or not re.fullmatch(r"[0-9]{1,12}", offset)
            or type(length) is not int
            or not 1 <= length <= 1024**2
            or 8 + size + int(offset) + length > path.stat().st_size
        ):
            raise ValueError("Invalid ASAR metadata entry")
        handle.seek(8 + size + int(offset))
        result = json.loads(handle.read(length))
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object in ASAR metadata")
        return result


def child_environment() -> dict[str, str]:
    allowed = {
        "path",
        "home",
        "user",
        "logname",
        "lang",
        "lc_all",
        "tmpdir",
        "temp",
        "tmp",
        "systemroot",
        "windir",
        "userprofile",
        "appdata",
        "localappdata",
        "programdata",
        "allusersprofile",
        "programfiles",
        "programfiles(x86)",
        "programw6432",
        "comspec",
        "homedrive",
        "homepath",
        "systemdrive",
        "os",
        "processor_architecture",
        "display",
        "xauthority",
        "xdg_config_home",
        "xdg_cache_home",
        "xdg_runtime_dir",
        "dbus_session_bus_address",
        "__cf_user_text_encoding",
    }
    # Preserve normal system paths, but no CI/API keys, loader overrides or smoke flags.
    result = {key: value for key, value in os.environ.items() if key.lower() in allowed}
    result["MNEMION_START_AT_LOGIN"] = "0"
    return result


def run(command: list, *, env: dict, timeout: int = 180) -> None:
    result = subprocess.run(
        list(map(str, command)), env=env, capture_output=True, timeout=timeout, check=False
    )
    if result.returncode:
        raise RuntimeError(f"Native operation {Path(command[0]).name} failed ({result.returncode})")


def install(source: Path, directory: Path, system: str, env: dict) -> Path:
    directory.mkdir()
    if system == "windows":
        # Start-Process -Wait tracks the NSIS process tree, including emulated stubs.
        env = {**env, "MNEMION_PROBE_INSTALLER": str(source), "MNEMION_PROBE_DEST": str(directory)}
        run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                '$ErrorActionPreference="Stop"; $p=Start-Process -FilePath $env:MNEMION_PROBE_INSTALLER '
                '-ArgumentList @("/S","/currentuser",("/D="+$env:MNEMION_PROBE_DEST)) '
                "-PassThru -Wait; exit $p.ExitCode",
            ],
            env=env,
        )
        return directory / "Mnemion Studio.exe"
    if system == "macos":
        mount = directory.parent / "mounted-dmg"
        mount.mkdir()
        run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, source], env=env)
        bundle = directory / "Mnemion Studio.app"
        try:
            run(["ditto", mount / bundle.name, bundle], env=env)
        finally:
            run(["hdiutil", "detach", mount], env=env)
        run(["codesign", "--verify", "--deep", "--strict", bundle], env=env)
        return bundle / "Contents/MacOS/Mnemion Studio"
    target = directory / source.name
    shutil.copyfile(source, target)
    target.chmod(0o755)
    return target


def profiles(system: str) -> list[Path]:
    if system == "windows":
        base = Path(os.environ["APPDATA"])
    elif system == "macos":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return [base / "mnemion-studio", base / "Mnemion Studio"]


def app_processes(executable: Path, system: str, started: float) -> list:
    import psutil

    found = []
    for process in psutil.process_iter(["pid", "name", "exe", "create_time"]):
        info = process.info
        if info.get("create_time", 0) < started - 1 or not info.get("exe"):
            continue
        path = Path(info["exe"])
        if system == "linux":
            if path.name != "mnemion-studio":
                continue
        elif path != executable:
            continue
        try:
            if any(arg.startswith("--type=") for arg in process.cmdline()):
                continue
            if system == "linux":
                image = Path(process.environ().get("APPIMAGE", "/not-an-appimage"))
                if image.parent != executable.parent:
                    continue
            found.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def app_archive(process, system: str) -> Path:
    path = Path(process.exe())
    return (
        path.parent.parent / "Resources" if system == "macos" else path.parent / "resources"
    ) / "app.asar"


def observe(args) -> dict:
    import psutil

    expected_system = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}[platform.system()]
    expected_arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
    root = args.output.resolve()
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        or root.exists()
        or not root.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve())
        or (args.platform, args.arch) != (expected_system, expected_arch)
        or any(path.exists() for path in profiles(args.platform))
    ):
        raise ValueError(
            "Use a fresh matching GitHub-hosted runner and a new RUNNER_TEMP directory"
        )
    before, after = release(args.from_tag), release(args.to_tag)
    if version(before["tag_name"]) >= version(after["tag_name"]):
        raise ValueError("The public target must be newer than the installed release")
    if release("latest")["tag_name"] != after["tag_name"]:
        raise ValueError("The live feed advanced; rerun against the latest public release")
    root.mkdir(mode=0o700)
    asset = next(
        row
        for row in before["assets"]
        if row["name"] == installer_name(args.from_tag, args.platform, args.arch)
    )
    target_asset = next(
        row
        for row in after["assets"]
        if row["name"] == installer_name(args.to_tag, args.platform, args.arch)
    )
    source = root / asset["name"]
    download(asset, source)
    env = child_environment()
    executable = install(source, root / "installed with spaces", args.platform, env)
    started = time.time()
    log = deque(maxlen=16)
    child = subprocess.Popen(
        [str(executable), "--background"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )

    def capture():
        while chunk := child.stdout.read1(4096):
            log.append(chunk)

    threading.Thread(target=capture, daemon=True).start()
    observed, original, profile, preferences = {}, None, None, None
    sentinel = os.urandom(32)
    result = {
        "from": args.from_tag,
        "to": args.to_tag,
        "platform": args.platform,
        "architecture": args.arch,
        "source_sha256": asset["digest"],
        "status": "failed",
    }
    last_progress = 0
    try:
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            for process in app_processes(executable, args.platform, started):
                try:
                    package = asar_json(app_archive(process, args.platform))
                    current = package["version"]
                    observed[process.pid] = current
                    if original is None and current == args.from_tag[1:]:
                        ready = [
                            path
                            for path in profiles(args.platform)
                            if (path / "desktop-preferences.json").is_file()
                        ]
                        if len(ready) != 1:
                            continue
                        original, profile = process.pid, ready[0]
                        preferences = (profile / "desktop-preferences.json").read_bytes()
                        if json.loads(preferences).get("automaticUpdates") is not True:
                            raise ValueError(
                                "The public installation did not enable automatic updates"
                            )
                        (profile / "public-upgrade-sentinel.bin").write_bytes(sentinel)
                    elif (
                        original is not None
                        and process.pid != original
                        and current == args.to_tag[1:]
                    ):
                        time.sleep(10)
                        if not process.is_running() or psutil.pid_exists(original):
                            continue
                        if (profile / "public-upgrade-sentinel.bin").read_bytes() != sentinel or (
                            profile / "desktop-preferences.json"
                        ).read_bytes() != preferences:
                            raise ValueError(
                                "The public update did not preserve the profile and preferences"
                            )
                        if args.platform == "macos":
                            run(
                                [
                                    "codesign",
                                    "--verify",
                                    "--deep",
                                    "--strict",
                                    executable.parents[2],
                                ],
                                env=env,
                            )
                        elif args.platform == "linux":
                            image = Path(process.environ()["APPIMAGE"])
                            with image.open("rb") as handle:
                                digest = hashlib.file_digest(handle, "sha256").hexdigest()
                            if "sha256:" + digest != target_asset["digest"]:
                                raise ValueError(
                                    "The installed AppImage is not the verified public target"
                                )
                        result.update(
                            status="passed",
                            original_pid=original,
                            updated_pid=process.pid,
                            profile_preserved=True,
                            official_feed=True,
                            unmodified_packages=True,
                            real_system_idle=True,
                            elapsed_seconds=round(time.time() - started, 2),
                        )
                        return result
                except (
                    FileNotFoundError,
                    PermissionError,
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                ):
                    continue
            elapsed = int(time.time() - started)
            if original is None and elapsed > 90:
                raise RuntimeError(
                    "The initial public application did not start with its default profile"
                )
            if elapsed >= last_progress + 30:
                print(
                    json.dumps(
                        {
                            "elapsed_seconds": elapsed,
                            "observed_versions": sorted(set(observed.values())),
                            "waiting_for": args.to_tag,
                        }
                    ),
                    flush=True,
                )
                last_progress = elapsed
            time.sleep(3)
        raise TimeoutError(
            "No automatic public replacement and relaunch within the real idle/update deadline"
        )
    finally:
        result["observed_process_versions"] = observed
        candidates = []
        for process in psutil.process_iter(["pid", "name", "create_time"]):
            if (
                "mnemion" not in (process.info.get("name") or "").lower()
                or process.info.get("create_time", 0) < started - 1
            ):
                continue
            entry = {"pid": process.pid, "name": process.info["name"]}
            try:
                entry["executable"] = process.exe()
                entry["appimage"] = process.environ().get("APPIMAGE")
                entry["appdir"] = process.environ().get("APPDIR")
            except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
                entry["inspection_error"] = type(error).__name__
            candidates.append(entry)
            if len(candidates) >= 20:
                break
        result["candidate_processes"] = candidates
        result["profile_directories"] = [
            {
                "name": path.name,
                "exists": path.exists(),
                "preferences": (path / "desktop-preferences.json").exists(),
            }
            for path in profiles(args.platform)
        ]
        result["initial_launcher_pid"] = child.pid
        result["initial_launcher_exit"] = child.poll()
        (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        (root / "application.log").write_bytes(b"".join(log)[-32768:])
        for process in app_processes(executable, args.platform, started):
            try:
                for descendant in process.children(recursive=True):
                    descendant.kill()
                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if child.poll() is None:
            try:
                child.kill()
            except ProcessLookupError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select", action="store_true")
    parser.add_argument(
        "--selection-platform", choices=["all", "windows", "macos", "linux"], default="all"
    )
    parser.add_argument("--tag", default="latest")
    parser.add_argument("--from-tag")
    parser.add_argument("--to-tag")
    parser.add_argument("--platform", choices=["windows", "macos", "linux"])
    parser.add_argument("--arch", choices=["x64", "arm64"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.select:
        target = release(args.tag)
        if release("latest")["tag_name"] != target["tag_name"]:
            selected, skipped = [], ["Release superseded by the current public feed"]
        else:
            previous = json.loads(fetch(API.removesuffix("/latest") + "?per_page=5", api=True))
            selected, skipped = select_pairs(target, previous)
            if args.selection_platform != "all":
                selected = [row for row in selected if row["platform"] == args.selection_platform]
        print("matrix=" + json.dumps(selected))
        print("available=" + str(bool(selected)).lower())
        print("skipped=" + json.dumps(skipped))
    else:
        if not all((args.from_tag, args.to_tag, args.platform, args.arch, args.output)):
            parser.error(
                "Provide both tags, native platform/architecture and a new output directory"
            )
        print(json.dumps(observe(args), indent=2))


if __name__ == "__main__":
    main()
