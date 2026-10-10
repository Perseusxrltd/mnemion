"""Validate Mnemion's native Sparkle control adapter using disposable app bundles."""

from __future__ import annotations

import argparse
import base64
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import plistlib
import queue
import signal
import subprocess
import sys
import threading
import time
from uuid import uuid4

from deploy.macos_update_probe import bundle, keys, prepare_upstream, run, write_feed


def compile_adapter(root: Path, distribution: Path) -> Path:
    source = Path(__file__).resolve().parent.parent / "studio/electron/native/macos-updater.m"
    executable = root / "MnemionUpdater"
    arguments = [
        "clang",
        "-fobjc-arc",
        "-fmodules",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-unused-parameter",
        "-framework",
        "Cocoa",
        "-framework",
        "Sparkle",
        "-F",
        distribution,
        "-Wl,-rpath,@executable_path/../Frameworks",
        source,
        "-o",
        executable,
    ]
    # Compile both production and fixture branches. Only the fixture accepts loopback.
    run(arguments)
    run(arguments[:1] + ["-DMNEMION_UPDATER_FIXTURE=1"] + arguments[1:])
    run(["codesign", "--force", "--sign", "-", executable])
    return executable


def embed(application: Path, executable: Path, distribution: Path) -> None:
    destination = application / "Contents/MacOS/MnemionUpdater"
    run(["ditto", executable, destination])
    frameworks = application / "Contents/Frameworks"
    frameworks.mkdir()
    run(["ditto", distribution / "Sparkle.framework", frameworks / "Sparkle.framework"])
    run(["codesign", "--force", "--sign", "-", application])
    run(["codesign", "--verify", "--deep", "--strict", application])


class Adapter:
    def __init__(self, application: Path, log: Path):
        self.events: queue.Queue = queue.Queue()
        self.observed: list[dict] = []
        self.errors = log.open("w")
        self.process = subprocess.Popen(
            [str(application / "Contents/MacOS/MnemionUpdater")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
            text=True,
        )
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        for line in self.process.stdout:
            if len(line) > 2048 or len(self.observed) > 500:
                self.events.put({"state": "protocol-error"})
                return
            event = json.loads(line)
            self.observed.append(event)
            self.events.put(event)
        self.events.put({"state": "eof"})

    def until(self, state: str, timeout: int = 120) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event = self.events.get(timeout=max(0.1, deadline - time.monotonic()))
            if event["state"] == state:
                return event
            if event["state"] in {"eof", "error", "protocol-error"}:
                raise AssertionError(f"Expected {state}; received {event}; events={self.observed}")
        raise TimeoutError(f"No {state} from the native adapter")

    def send(self, command: str):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def finish(self):
        code = self.process.wait(timeout=30)
        self.thread.join(timeout=5)
        self.errors.close()
        return code

    def cleanup(self):
        if self.process.poll() is None:
            self.send("cancel")
            try:
                self.finish()
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=10)
        self.errors.close()


def assert_unchanged(application: Path, process: subprocess.Popen) -> None:
    version = plistlib.loads((application / "Contents/Info.plist").read_bytes())["CFBundleVersion"]
    if version != "4.0.0" or process.poll() is not None:
        raise AssertionError("An unapproved update replaced or stopped the running application")


def execute(root: Path) -> dict:
    _, distribution = prepare_upstream(root)
    executable = compile_adapter(root, distribution)
    public = root / "http"
    public.mkdir()
    requests: list[str] = []

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(public), **kwargs)

        def log_message(self, *_):
            pass

        def do_GET(self):
            if len(requests) < 1000:
                requests.append(self.path)
            super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    pair = keys(root)
    identifier = "com.perseusxr.mnemion.update-probe." + uuid4().hex
    installed = bundle(root, "installed", "4.0.0", identifier, pair["public"], origin + "/feed.xml")
    candidate = bundle(root, "candidate", "4.0.1", identifier, pair["public"], origin + "/feed.xml")
    for application in [installed, candidate]:
        embed(application, executable, distribution)
    archive = public / "update.zip"
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", candidate, archive])
    signature = run(
        [distribution / "bin/sign_update", "--ed-key-file", "-", "-p", archive],
        input_text=pair["seed"],
        sensitive=True,
    ).stdout.strip()
    del pair["seed"]
    wrong_bytes = base64.b64decode(signature, validate=True)
    wrong = base64.b64encode(bytes([wrong_bytes[0] ^ 1]) + wrong_bytes[1:]).decode()
    host = subprocess.Popen(
        [str(installed / "Contents/MacOS/ProbeHost")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    adapters: list[Adapter] = []
    try:
        time.sleep(1)
        write_feed(public / "feed.xml", origin + "/update.zip", archive, wrong)
        invalid = Adapter(installed, root / "bridge-invalid.log")
        adapters.append(invalid)
        invalid.until("error")
        invalid.finish()
        assert_unchanged(installed, host)
        if not any(path.startswith("/update.zip") for path in requests):
            raise AssertionError("The invalid archive was not downloaded")

        write_feed(public / "feed.xml", origin + "/update.zip", archive, signature)
        cancelled = Adapter(installed, root / "bridge-cancel.log")
        adapters.append(cancelled)
        cancelled.until("ready")
        time.sleep(1)
        assert_unchanged(installed, host)
        cancelled.send("cancel")
        cancelled.until("cancelled")
        if cancelled.finish() != 0:
            raise AssertionError("Cancellation did not complete cleanly")
        # An abandoned Sparkle installer must not install after the host quits.
        host.terminate()
        host.wait(timeout=10)
        time.sleep(3)
        version = plistlib.loads((installed / "Contents/Info.plist").read_bytes())[
            "CFBundleVersion"
        ]
        if version != "4.0.0":
            raise AssertionError("A cancelled update installed on application exit")
        host = subprocess.Popen(
            [str(installed / "Contents/MacOS/ProbeHost")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        accepted = Adapter(installed, root / "bridge-install.log")
        adapters.append(accepted)
        accepted.until("ready")
        assert_unchanged(installed, host)
        accepted.send("install")
        result = accepted.until("installed", timeout=180)
        if not result.get("relaunched") or accepted.finish() != 0:
            raise AssertionError("The controlled update did not install and relaunch")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            version = plistlib.loads((installed / "Contents/Info.plist").read_bytes())[
                "CFBundleVersion"
            ]
            launches = (root / "launches.txt").read_text()
            if version == "4.0.1" and any(
                line.endswith(" 4.0.1") for line in launches.splitlines()
            ):
                break
            time.sleep(0.2)
        else:
            raise AssertionError("The updated bundle did not launch from the original location")
        run(["codesign", "--verify", "--deep", "--strict", installed])
        return {
            "invalid_archive_rejected": True,
            "ready_update_waited_for_parent_permission": True,
            "cancelled_update_did_not_install_on_exit": True,
            "explicit_install_replaced_and_relaunched": True,
            "developer_id_used": False,
            "actual_electron_integration": "not exercised by this native control fixture",
        }
    finally:
        for adapter in adapters:
            adapter.cleanup()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        if host.poll() is None:
            host.terminate()
            host.wait(timeout=10)
        if (root / "launches.txt").exists():
            for line in (root / "launches.txt").read_text().splitlines():
                pid = int(line.split()[0])
                command = run(["ps", "-p", str(pid), "-o", "command="], check=False).stdout
                if str(installed / "Contents/MacOS/ProbeHost") in command:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("The updater control probe requires a native Mac")
    os.umask(0o077)
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = execute(root)
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
