"""Rehearse an update using the packaged Electron controller in disposable bundles.

The fixture substitutes a small test entry point and synthetic renderer draft,
retaining the packaged DesktopUpdates and MacUpdateBridge implementations.
System inactivity is simulated; the native window, Sparkle installer, signatures,
bundle replacement and relaunch are real. No installed application is targeted.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import plistlib
import signal
import subprocess
import sys
import threading
import time
from uuid import uuid4

from deploy.macos_sparkle import OUTPUT, ROOT, configuration
from deploy.macos_update_bridge_probe import compile_adapter
from deploy.macos_update_probe import keys, run, write_feed


def sign_bundle(path: Path) -> None:
    run(
        [
            "codesign",
            "--force",
            "--sign",
            "-",
            "--options",
            "runtime",
            "--entitlements",
            ROOT / "studio/electron/entitlements.mac.plist",
            path,
        ]
    )
    run(["codesign", "--verify", "--deep", "--strict", path])


def execute(root: Path) -> dict:
    config = configuration()
    architecture = {"arm64": "arm64", "x86_64": "x64"}[platform.machine()]
    folder = "mac-arm64" if architecture == "arm64" else "mac"
    source = ROOT / "dist-electron" / folder / "Mnemion Studio.app"
    source_info = plistlib.loads((source / "Contents/Info.plist").read_bytes())
    version = source_info["CFBundleShortVersionString"]
    major, minor, patch = map(int, version.split("."))
    target = f"{major}.{minor}.{patch + 1}"
    stamp = json.loads((source / "Contents/Resources/macos-updater-build.json").read_text())
    if stamp["fixture"] is not False or stamp["public_key"] != config["publicKey"]:
        raise ValueError("Start the rehearsal from the verified production bundle")
    distribution = OUTPUT / "sparkle"
    executable = compile_adapter(root, distribution)
    public = root / "http"
    public.mkdir()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(public), **kwargs)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    pair = keys(root)
    identifier = "com.perseusxr.mnemion.update-probe." + uuid4().hex
    installed = root / "installed/Mnemion Studio.app"
    candidate = root / "candidate/Mnemion Studio.app"
    run(["ditto", source, installed])
    resources = installed / "Contents/Resources"
    run(["ditto", executable, installed / "Contents/MacOS/MnemionUpdater"])
    header_hash = run(
        [
            "node",
            ROOT / "studio/electron/scripts/make-update-fixture.mjs",
            resources,
            root / "unpacked-fixture",
        ]
    ).stdout.strip()
    user_data = root / "user-data"
    user_data.mkdir()
    (user_data / "desktop-preferences.json").write_text(
        json.dumps(
            {
                "automaticUpdates": True,
                "startAtLogin": False,
                "background": True,
            }
        )
    )
    receipt = root / "events.jsonl"
    (resources / "update-fixture.json").write_text(
        json.dumps(
            {
                "userData": str(user_data),
                "receipt": str(receipt),
                "expectedVersion": target,
            }
        )
    )
    stamp.update({"fixture": True, "public_key": pair["public"]})
    (resources / "macos-updater-build.json").write_text(json.dumps(stamp))
    info = deepcopy(source_info)
    info.update(
        {
            "CFBundleIdentifier": identifier,
            "SUFeedURL": origin + "/feed.xml",
            "SUPublicEDKey": pair["public"],
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        }
    )
    asar = info.get("ElectronAsarIntegrity", {})
    if "Resources/app.asar" not in asar:
        raise ValueError("The built app is missing its embedded ASAR integrity declaration")
    asar["Resources/app.asar"] = {"algorithm": "SHA256", "hash": header_hash}
    (installed / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    sign_bundle(installed)
    run(["ditto", installed, candidate])
    candidate_hash = run(
        [
            "node",
            ROOT / "studio/electron/scripts/make-update-fixture.mjs",
            candidate / "Contents/Resources",
            root / "unpacked-candidate",
            target,
        ]
    ).stdout.strip()
    candidate_info = {
        **deepcopy(info),
        "CFBundleVersion": target,
        "CFBundleShortVersionString": target,
    }
    candidate_info["ElectronAsarIntegrity"]["Resources/app.asar"]["hash"] = candidate_hash
    (candidate / "Contents/Info.plist").write_bytes(plistlib.dumps(candidate_info))
    sign_bundle(candidate)
    archive = public / "update.zip"
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", candidate, archive])
    signature = run(
        [distribution / "bin/sign_update", "--ed-key-file", "-", "-p", archive],
        input_text=pair["seed"],
        sensitive=True,
    ).stdout.strip()
    del pair["seed"]
    write_feed(public / "feed.xml", origin + "/update.zip", archive, signature, target)
    logs = (root / "electron.log").open("w")
    application_executable = installed / "Contents/MacOS" / info["CFBundleExecutable"]
    child = subprocess.Popen([str(application_executable)], stdout=logs, stderr=logs)
    try:
        deadline = time.monotonic() + 180
        events = []
        while time.monotonic() < deadline:
            if receipt.exists():
                events = [json.loads(line) for line in receipt.read_text().splitlines()]
                if errors := [event for event in events if event["event"] == "error"]:
                    raise AssertionError(f"The packaged update rehearsal failed: {errors}")
                relaunched = [event for event in events if event["event"] == "relaunched"]
                if relaunched:
                    break
            if child.poll() not in {None, 0}:
                raise AssertionError("The packaged Electron fixture exited with an error")
            time.sleep(0.2)
        else:
            raise TimeoutError(f"The packaged update did not relaunch; events={events}")
        names = [event["event"] for event in events]
        if (
            names.count("workspace-stop") != 2
            or names.count("restart-cancelled") != 1
            or "guards-passed" not in names
        ):
            raise AssertionError("The packaged restart guards were not exercised")
        if relaunched[0]["version"] != target or relaunched[0]["pid"] == child.pid:
            raise AssertionError("The updated application did not start a new process")
        os.kill(relaunched[0]["pid"], 0)
        updated = plistlib.loads((installed / "Contents/Info.plist").read_bytes())
        if updated["CFBundleVersion"] != target:
            raise AssertionError("The update did not replace the original bundle")
        run(["codesign", "--verify", "--deep", "--strict", installed])
        if plistlib.loads((source / "Contents/Info.plist").read_bytes()) != source_info:
            raise AssertionError("The production build was modified by the disposable rehearsal")
        return {
            "architecture": architecture,
            "original_version": version,
            "updated_version": target,
            "packaged_electron_controller": True,
            "native_signature_verification": True,
            "focus_transfer_draft_idle_guards": True,
            "automatic_replacement_and_relaunch": True,
            "developer_id_used": False,
            "fixture_scope": "Packaged update controller; synthetic renderer draft and system idle time",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        # Terminate only this disposable bundle's main process and Electron helpers.
        processes = run(["ps", "-axo", "pid=,command="], check=False).stdout.splitlines()
        for process in processes:
            parts = process.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[1].startswith(str(installed) + "/"):
                try:
                    os.kill(int(parts[0]), signal.SIGTERM)
                except ProcessLookupError:
                    pass
        if child.poll() is None:
            child.wait(timeout=15)
        logs.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Run the packaged update rehearsal on a native Mac")
    os.umask(0o077)
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = execute(root)
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
