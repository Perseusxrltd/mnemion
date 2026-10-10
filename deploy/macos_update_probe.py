"""Exercise Sparkle's free update-signing path on a disposable native Mac.

This is a release-engineering experiment, not Mnemion's production updater.
It never changes Gatekeeper, imports a certificate or touches an installed app.
Only synthetic bundles beneath a new private output directory are updated.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import plistlib
import signal
import subprocess
import sys
import tarfile
import threading
import time
from urllib.request import Request, urlopen
from uuid import uuid4
from xml.etree import ElementTree as ET


SPARKLE_VERSION = "2.10.0"
SPARKLE_COMMIT = "eef1a539a373c1f1a320624b1130fc5de7b2e100"
SPARKLE_SHA256 = "c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c"
CLI_FILES = {
    "main.m": "6df90a46bc481a76261f1b5c1a3123572f316fa3dc4463ab4269e2f5ecd0051e",
    "SPUCommandLineDriver.h": "3f7d8efdd5b1be0e150ecb75795e70b0cd4fadbd1b18818b2dcf7c26f0dd6171",
    "SPUCommandLineDriver.m": "0924b26df77f726afafed2bb149998c4c27813574c0a9e67ddf69cc0419490b1",
    "SPUCommandLineUserDriver.h": "525cc91b76b7c88d3f0bc476cfdf0df72c50739c31d3ff71e9da9a6bb4773c42",
    "SPUCommandLineUserDriver.m": "7e23c34763c74afbdbb7095cdd02d23343e9d0836e358e9da1099ff198e51600",
}
SPARKLE_XML = "http://www.andymatuschak.org/xml-namespaces/sparkle"

HOST_SOURCE = r"""#import <Cocoa/Cocoa.h>
#include <unistd.h>
@interface ProbeDelegate : NSObject <NSApplicationDelegate>
@end
@implementation ProbeDelegate
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    NSBundle *bundle = [NSBundle mainBundle];
    NSString *path = [bundle objectForInfoDictionaryKey:@"MnemionProbeReceipt"];
    NSString *version = [bundle objectForInfoDictionaryKey:@"CFBundleVersion"];
    NSData *line = [[NSString stringWithFormat:@"%d %@\n", getpid(), version]
        dataUsingEncoding:NSUTF8StringEncoding];
    if (![[NSFileManager defaultManager] fileExistsAtPath:path]) {
        [line writeToFile:path atomically:YES];
    } else {
        NSFileHandle *handle = [NSFileHandle fileHandleForWritingAtPath:path];
        [handle seekToEndOfFile]; [handle writeData:line]; [handle closeFile];
    }
}
@end
int main(void) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        ProbeDelegate *delegate = [ProbeDelegate new];
        [app setDelegate:delegate];
        [app setActivationPolicy:NSApplicationActivationPolicyAccessory];
        [app run];
    }
    return 0;
}
"""


def run(arguments, *, input_text=None, timeout=120, check=True, sensitive=False):
    result = subprocess.run(
        list(map(str, arguments)),
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        detail = "" if sensitive else (result.stdout + result.stderr)[-5000:]
        raise RuntimeError(f"{Path(arguments[0]).name} failed ({result.returncode}). {detail}")
    return result


def download(url: str, destination: Path, expected: str, limit: int) -> None:
    request = Request(url, headers={"User-Agent": "Mnemion-native-update-validation"})
    digest, size = hashlib.sha256(), 0
    with urlopen(request, timeout=30) as response, destination.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError("Upstream download exceeded its declared limit")
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("Upstream artifact digest did not match the pinned release")


def prepare_upstream(root: Path) -> tuple[Path, Path]:
    archive = root / "sparkle.tar.xz"
    download(
        f"https://github.com/sparkle-project/Sparkle/releases/download/{SPARKLE_VERSION}/Sparkle-{SPARKLE_VERSION}.tar.xz",
        archive,
        SPARKLE_SHA256,
        20_000_000,
    )
    distribution = root / "sparkle"
    distribution.mkdir()
    with tarfile.open(archive) as package:
        package.extractall(distribution, filter="data")
    source = root / "upstream-cli"
    source.mkdir()
    for filename, digest in CLI_FILES.items():
        download(
            f"https://raw.githubusercontent.com/sparkle-project/Sparkle/{SPARKLE_COMMIT}/sparkle-cli/{filename}",
            source / filename,
            digest,
            200_000,
        )
    executable = root / "sparkle-cli"
    # Compile the unmodified upstream CLI against the matching pinned framework.
    # An ad-hoc executable can load this framework without Developer ID enrollment.
    run(
        [
            "clang",
            "-fobjc-arc",
            "-fmodules",
            "-framework",
            "Cocoa",
            "-framework",
            "Sparkle",
            "-F",
            distribution,
            f"-Wl,-rpath,{distribution}",
            source / "main.m",
            source / "SPUCommandLineDriver.m",
            source / "SPUCommandLineUserDriver.m",
            "-o",
            executable,
        ]
    )
    run(["codesign", "--force", "--sign", "-", executable])
    return executable, distribution


def keys(root: Path) -> dict:
    generator = root / "generate-probe-key.swift"
    generator.write_text(
        "import Foundation\nimport CryptoKit\n"
        "let key = Curve25519.Signing.PrivateKey()\n"
        'let pair = ["seed": key.rawRepresentation.base64EncodedString(), '
        '"public": key.publicKey.rawRepresentation.base64EncodedString()]\n'
        "let data = try JSONSerialization.data(withJSONObject: pair)\n"
        "FileHandle.standardOutput.write(data)\n"
    )
    # This ephemeral seed stays in memory and a pipe; never print or publish it.
    result = json.loads(run(["swift", generator], sensitive=True).stdout)
    if len(base64.b64decode(result["seed"], validate=True)) != 32:
        raise ValueError("The native key generator returned an unexpected key format")
    return result


def bundle(root: Path, name: str, version: str, identifier: str, public: str, feed: str) -> Path:
    application = root / name / "Mnemion Update Probe.app"
    executable = application / "Contents/MacOS/ProbeHost"
    executable.parent.mkdir(parents=True)
    source = root / "host.m"
    source.write_text(HOST_SOURCE)
    run(["clang", "-fobjc-arc", "-framework", "Cocoa", source, "-o", executable])
    configuration = {
        "CFBundleIdentifier": identifier,
        "CFBundleName": "Mnemion Update Probe",
        "CFBundleExecutable": "ProbeHost",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": version,
        "CFBundleShortVersionString": version,
        "LSUIElement": True,
        "MnemionProbeReceipt": str(root / "launches.txt"),
        "SUFeedURL": feed,
        "SUPublicEDKey": public,
        "SUEnableAutomaticChecks": False,
        "SUAutomaticallyUpdate": False,
        "SUVerifyUpdateBeforeExtraction": True,
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    }
    (application / "Contents/Info.plist").write_bytes(plistlib.dumps(configuration))
    run(["codesign", "--force", "--sign", "-", application])
    description = run(["codesign", "--display", "--verbose=2", application]).stderr
    if "Signature=adhoc" not in description or "Authority=Developer ID" in description:
        raise AssertionError("The probe must exercise ad-hoc bundles without Developer ID")
    return application


def write_feed(path: Path, url: str, archive: Path, signature: str) -> None:
    ET.register_namespace("sparkle", SPARKLE_XML)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Disposable Mnemion updater validation"
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = "Probe 4.0.1"
    ET.SubElement(item, f"{{{SPARKLE_XML}}}version").text = "4.0.1"
    ET.SubElement(item, f"{{{SPARKLE_XML}}}shortVersionString").text = "4.0.1"
    ET.SubElement(
        item,
        "enclosure",
        {
            "url": url,
            "length": str(archive.stat().st_size),
            "type": "application/octet-stream",
            f"{{{SPARKLE_XML}}}edSignature": signature,
        },
    )
    temporary = path.with_suffix(".pending")
    temporary.write_bytes(ET.tostring(rss, encoding="utf-8", xml_declaration=True))
    temporary.replace(path)


def wait_launch(root: Path, version: str, timeout: float = 30) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        path = root / "launches.txt"
        if path.exists():
            for line in path.read_text().splitlines():
                pid, observed = line.split()
                if observed == version:
                    os.kill(int(pid), 0)
                    return int(pid)
        time.sleep(0.2)
    raise TimeoutError(f"The probe bundle did not launch version {version}")


def execute(root: Path) -> dict:
    cli, distribution = prepare_upstream(root)
    pair = keys(root)
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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    identifier = "com.perseusxr.mnemion.update-probe." + uuid4().hex
    old = bundle(root, "installed", "4.0.0", identifier, pair["public"], origin + "/feed.xml")
    new = bundle(root, "candidate", "4.0.1", identifier, pair["public"], origin + "/feed.xml")
    archive = public / "update.zip"
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", new, archive])
    signed = run(
        [distribution / "bin/sign_update", "--ed-key-file", "-", "-p", archive],
        input_text=pair["seed"],
        sensitive=True,
    ).stdout.strip()
    del pair["seed"]
    signature_bytes = base64.b64decode(signed, validate=True)
    if len(signature_bytes) != 64:
        raise ValueError("Sparkle returned an unexpected update signature")
    wrong = base64.b64encode(bytes([signature_bytes[0] ^ 1]) + signature_bytes[1:]).decode()
    host = subprocess.Popen(
        [str(old / "Contents/MacOS/ProbeHost")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        initial_pid = wait_launch(root, "4.0.0")
        arguments = [
            cli,
            old,
            "--check-immediately",
            "--user-agent-name",
            "Mnemion Update Probe",
            "--verbose",
        ]
        write_feed(public / "feed.xml", origin + "/update.zip", archive, wrong)
        rejected = run(arguments, check=False, timeout=120)
        (root / "invalid-signature.log").write_text(rejected.stdout + rejected.stderr)
        if rejected.returncode == 0 or not any(path.startswith("/update.zip") for path in requests):
            raise AssertionError("The invalid update was not downloaded and rejected")
        if "signature" not in (rejected.stdout + rejected.stderr).lower():
            raise AssertionError("The invalid update did not report a signature failure")
        if plistlib.loads((old / "Contents/Info.plist").read_bytes())["CFBundleVersion"] != "4.0.0":
            raise AssertionError("An invalid update changed the installed bundle")
        os.kill(initial_pid, 0)
        requests.clear()
        write_feed(public / "feed.xml", origin + "/update.zip", archive, signed)
        accepted = run(arguments, check=False, timeout=180)
        (root / "valid-signature.log").write_text(accepted.stdout + accepted.stderr)
        if accepted.returncode:
            raise RuntimeError(
                "The valid update failed: " + (accepted.stdout + accepted.stderr)[-5000:]
            )
        restarted_pid = wait_launch(root, "4.0.1")
        if restarted_pid == initial_pid:
            raise AssertionError("The application was not relaunched after replacement")
        if plistlib.loads((old / "Contents/Info.plist").read_bytes())["CFBundleVersion"] != "4.0.1":
            raise AssertionError("The new version was not installed at the original path")
        run(["codesign", "--verify", "--deep", "--strict", old])
        return {
            "sparkle_version": SPARKLE_VERSION,
            "sparkle_commit": SPARKLE_COMMIT,
            "sparkle_distribution_sha256": SPARKLE_SHA256,
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "developer_id_used": False,
            "gatekeeper_settings_changed": False,
            "invalid_signature_rejected": True,
            "old_bundle_survived_rejection": True,
            "valid_signed_archive_installed": True,
            "application_relaunched": True,
            "new_adhoc_bundle_signature_valid": True,
            "first_install_gatekeeper_validation": "not tested by this already-launched fixture",
            "production_mnemion_integration": "not implemented by this probe",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        launch_file = root / "launches.txt"
        if launch_file.exists():
            for line in launch_file.read_text().splitlines():
                pid = int(line.split()[0])
                command = run(["ps", "-p", str(pid), "-o", "command="], check=False).stdout
                if str(old / "Contents/MacOS/ProbeHost") in command:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
        if host.poll() is None:
            host.terminate()
            host.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This probe requires a native macOS host")
    os.umask(0o077)
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = execute(root)
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
