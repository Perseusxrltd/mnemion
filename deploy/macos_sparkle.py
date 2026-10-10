"""Build the pinned native macOS updater and sign immutable release archives."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "studio/electron/native"
OUTPUT = ROOT / "build-tmp/macos-update"
XML_NAMESPACE = "http://www.andymatuschak.org/xml-namespaces/sparkle"
MAXIMUM_ARCHIVE_BYTES = 1024 * 1024 * 1024


def configuration() -> dict:
    config = json.loads((NATIVE / "sparkle.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"\d+\.\d+\.\d+", config["version"]):
        raise ValueError("Invalid Sparkle version")
    if not re.fullmatch(r"[0-9a-f]{40}", config["commit"]):
        raise ValueError("Invalid pinned Sparkle commit")
    if not re.fullmatch(r"[0-9a-f]{64}", config["sha256"]):
        raise ValueError("Invalid pinned Sparkle digest")
    if len(base64.b64decode(config["publicKey"], validate=True)) != 32:
        raise ValueError("Invalid update public key")
    return config


def download(url: str, destination: Path, expected: str, limit: int) -> None:
    request = Request(url, headers={"User-Agent": "Mnemion-native-updater-build"})
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


def prepare_distribution(root: Path) -> Path:
    config = configuration()
    archive = root / "sparkle.tar.xz"
    download(
        f"https://github.com/sparkle-project/Sparkle/releases/download/{config['version']}/Sparkle-{config['version']}.tar.xz",
        archive,
        config["sha256"],
        20_000_000,
    )
    distribution = root / "sparkle"
    distribution.mkdir()
    with tarfile.open(archive) as package:
        package.extractall(distribution, filter="data")
    return distribution


def run(arguments, *, input_text=None, sensitive=False):
    environment = dict(os.environ)
    environment.pop("MNEMION_MAC_UPDATE_PRIVATE_KEY", None)
    result = subprocess.run(
        list(map(str, arguments)),
        input=input_text,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
        env=environment,
    )
    if result.returncode:
        detail = "" if sensitive else (result.stdout + result.stderr)[-4000:]
        raise RuntimeError(f"{Path(arguments[0]).name} failed. {detail}")
    return result.stdout.strip()


def build() -> None:
    if OUTPUT.is_symlink():
        raise ValueError("Native build output must not be a symbolic link")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, mode=0o700)
    distribution = prepare_distribution(OUTPUT)
    executable = OUTPUT / "MnemionUpdater"
    run(
        [
            "clang",
            "-fobjc-arc",
            "-fmodules",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-parameter",
            "-mmacosx-version-min=13.0",
            "-framework",
            "Cocoa",
            "-framework",
            "Sparkle",
            "-F",
            distribution,
            "-Wl,-rpath,@executable_path/../Frameworks",
            NATIVE / "macos-updater.m",
            "-o",
            executable,
        ]
    )
    run(["codesign", "--force", "--sign", "-", executable])
    config = configuration()
    (OUTPUT / "build.json").write_text(
        json.dumps(
            {
                "sparkle_version": config["version"],
                "sparkle_distribution_sha256": config["sha256"],
                "source_sha256": hashlib.sha256(
                    (NATIVE / "macos-updater.m").read_bytes()
                ).hexdigest(),
                "architecture": platform.machine(),
                "public_key": config["publicKey"],
                "fixture": False,
                "developer_id": False,
            },
            indent=2,
        )
        + "\n"
    )
    print("Built the pinned native updater; no fixture overrides or publisher enrollment used.")


def create_feed(version: str, architecture: str, archive: Path, signature: str) -> bytes:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or architecture not in {"arm64", "x64"}:
        raise ValueError("Invalid release version or architecture")
    if archive.name != f"Mnemion-Studio-{version}-macos-{architecture}.zip":
        raise ValueError("The update archive must use the canonical release filename")
    if (
        archive.is_symlink()
        or not archive.is_file()
        or not 0 < archive.stat().st_size <= MAXIMUM_ARCHIVE_BYTES
    ):
        raise ValueError("Missing, unsafe or oversized update archive")
    if len(base64.b64decode(signature, validate=True)) != 64:
        raise ValueError("Invalid Ed25519 update signature")
    ET.register_namespace("sparkle", XML_NAMESPACE)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Mnemion Studio stable updates"
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = f"Mnemion Studio {version}"
    for name, value in [
        ("version", version),
        ("shortVersionString", version),
        ("minimumSystemVersion", "13.0"),
    ]:
        ET.SubElement(item, f"{{{XML_NAMESPACE}}}{name}").text = value
    ET.SubElement(
        item,
        "enclosure",
        {
            "url": f"https://github.com/Perseusxrltd/mnemion/releases/download/v{version}/{archive.name}",
            "length": str(archive.stat().st_size),
            "type": "application/octet-stream",
            f"{{{XML_NAMESPACE}}}edSignature": signature,
        },
    )
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True) + b"\n"


def sign_release(artifacts: Path) -> None:
    config = configuration()
    version = json.loads((ROOT / "studio/electron/package.json").read_text())["version"]
    architecture = {"arm64": "arm64", "x86_64": "x64"}[platform.machine()]
    archive = artifacts / f"Mnemion-Studio-{version}-macos-{architecture}.zip"
    seed = os.environ.pop("MNEMION_MAC_UPDATE_PRIVATE_KEY", "")
    if len(base64.b64decode(seed, validate=True)) != 32:
        raise ValueError("Configure the protected macOS update signing key before releasing")
    signer = OUTPUT / "sparkle/bin/sign_update"
    if not signer.is_file():
        raise ValueError("Build the pinned updater before signing release archives")
    signature = run([signer, "--ed-key-file", "-", "-p", archive], input_text=seed, sensitive=True)
    del seed
    # Verify with the public key committed into every installed application.
    from deploy.release import verify_ed25519

    verify_ed25519(archive, signature, config["publicKey"])
    feed = artifacts / f"latest-{architecture}-mac.xml"
    feed.write_bytes(create_feed(version, architecture, archive, signature))
    print(f"Signed and verified {archive.name}; generated {feed.name}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "sign"])
    parser.add_argument("--artifacts", type=Path, default=ROOT / "dist-electron")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Build and sign on a native macOS runner")
    os.umask(0o077)
    if args.action == "build":
        build()
    else:
        sign_release(args.artifacts.resolve())


if __name__ == "__main__":
    main()
