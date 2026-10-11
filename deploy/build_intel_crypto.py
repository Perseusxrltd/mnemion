"""Build the current cryptography wheel on a free native Intel Mac runner.

Only release builders compile code. Managed hosts install the signed wheel with
its statically linked, source-pinned OpenSSL and bundled upstream licenses.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
import zipfile

MAX_DOWNLOAD = 128 * 1024 * 1024


def download(url: str, digest: str, destination: Path) -> None:
    if not url.startswith(
        ("https://github.com/openssl/openssl/", "https://files.pythonhosted.org/")
    ):
        raise ValueError("Unexpected source publisher")
    request = urllib.request.Request(url, headers={"User-Agent": "Mnemion-release-builder"})
    with urllib.request.urlopen(request, timeout=30) as response, destination.open("xb") as output:
        total = 0
        checksum = hashlib.sha256()
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise ValueError("Build source exceeds its size budget")
            checksum.update(chunk)
            output.write(chunk)
    if checksum.hexdigest() != digest:
        raise ValueError("Build source differs from its reviewed hash")


def unpack(source: Path, destination: Path, prefix: str) -> Path:
    destination.mkdir()
    with tarfile.open(source, "r:gz") as archive:
        entries = archive.getmembers()
        if len(entries) > 40_000 or sum(item.size for item in entries) > 512 * 1024 * 1024:
            raise ValueError("Build source exceeds its expanded budget")
        if any(item.name.split("/", 1)[0] != prefix for item in entries):
            raise ValueError("Build source has an unexpected root")
        archive.extractall(destination, filter="data")
    return destination / prefix


def add_provenance(source: Path, output: Path, version: str, provenance: dict, license_text: bytes):
    prefix = f"cryptography-{version}.dist-info/"
    with zipfile.ZipFile(source) as archive:
        entries = {item.filename: archive.read(item) for item in archive.infolist()}
        if len(entries) != len(archive.infolist()):
            raise ValueError("Duplicate built wheel entries")
    entries.pop(prefix + "RECORD")
    entries[prefix + "mnemion-build.json"] = (
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    ).encode()
    entries[prefix + "licenses/LICENSE.OpenSSL"] = license_text
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, content in sorted(entries.items()):
        writer.writerow(
            [
                name,
                "sha256="
                + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("="),
                len(content),
            ]
        )
    writer.writerow([prefix + "RECORD", "", ""])
    entries[prefix + "RECORD"] = record.getvalue().encode()
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            archive.writestr(name, content)


def build(root: Path, output: Path) -> Path:
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise ValueError("Build the Intel Mac wheel on a native Intel Mac runner")
    uv = shutil.which("uv")
    if not uv or subprocess.check_output([uv, "--version"], text=True).split()[:2] != [
        "uv",
        "0.12.24",
    ]:
        raise ValueError("Use the reviewed uv release builder")
    configuration = json.loads((root / "deploy/intel-crypto.json").read_text())
    packages = {p["name"]: p for p in tomllib.loads((root / "uv.lock").read_text())["package"]}
    crypto = packages["cryptography"]
    version = crypto["version"]
    openssl_version = configuration["openssl_version"]
    output.mkdir(parents=True, exist_ok=True)
    filename = f"cryptography-{version}-cp311-abi3-{configuration['target']}.whl"
    target = output / filename
    if target.exists():
        raise ValueError("Do not replace a previously built runtime wheel")
    with tempfile.TemporaryDirectory(prefix="mnemion-intel-crypto-") as temporary:
        work = Path(temporary)
        openssl_archive, crypto_archive = work / "openssl.tar.gz", work / "cryptography.tar.gz"
        download(configuration["openssl_url"], configuration["openssl_sha256"], openssl_archive)
        download(
            crypto["sdist"]["url"], crypto["sdist"]["hash"].removeprefix("sha256:"), crypto_archive
        )
        openssl = unpack(openssl_archive, work / "openssl-source", f"openssl-{openssl_version}")
        source = unpack(crypto_archive, work / "crypto-source", f"cryptography-{version}")
        environment = dict(os.environ)
        environment.update(
            {
                "MACOSX_DEPLOYMENT_TARGET": "11.0",
                "CARGO_BUILD_JOBS": "2",
                "OPENSSL_STATIC": "1",
                "OPENSSL_NO_VENDOR": "1",
                "OPENSSL_DIR": str(work / "openssl-install"),
                "UV_NO_CONFIG": "1",
                "UV_PYTHON_DOWNLOADS": "never",
            }
        )

        def run(command, *, cwd=work, timeout=900):
            subprocess.run(command, cwd=cwd, env=environment, check=True, timeout=timeout)

        run(
            [
                "perl",
                "./Configure",
                "darwin64-x86_64-cc",
                "no-shared",
                "no-tests",
                "no-module",
                "-fPIC",
                "-mmacosx-version-min=11.0",
                "--prefix=" + environment["OPENSSL_DIR"],
                "--openssldir=/nonexistent/mnemion-openssl",
            ],
            cwd=openssl,
        )
        run(["make", "-j2"], cwd=openssl)
        run(["make", "install_sw"], cwd=openssl)
        run([uv, "venv", "--python", sys.executable, str(work / "builder")])
        python = work / "builder/bin/python"
        run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                "--only-binary",
                ":all:",
                f"maturin=={configuration['maturin']}",
                f"setuptools=={configuration['setuptools']}",
                f"cffi=={packages['cffi']['version']}",
                f"pycparser=={packages['pycparser']['version']}",
            ]
        )
        built = work / "built"
        run(
            [
                uv,
                "build",
                "--wheel",
                "--no-build-isolation",
                "--python",
                str(python),
                "--out-dir",
                str(built),
                str(source),
            ]
        )
        wheels = list(built.glob("*.whl"))
        if len(wheels) != 1 or wheels[0].name != filename:
            raise ValueError("Built runtime wheel has an unexpected platform or Python ABI")
        with zipfile.ZipFile(wheels[0]) as archive:
            native = [name for name in archive.namelist() if name.endswith((".so", ".dylib"))]
            if not native:
                raise ValueError("Built runtime has no native library")
            for index, name in enumerate(native):
                binary = work / f"native-{index}.so"
                binary.write_bytes(archive.read(name))
                architectures = subprocess.check_output(
                    ["lipo", "-archs", str(binary)], text=True
                ).strip()
                if architectures != "x86_64":
                    raise ValueError("Built runtime has another architecture")
                libraries = subprocess.check_output(
                    ["otool", "-L", str(binary)], text=True
                ).splitlines()[1:]
                if any(
                    not line.strip().split(" ", 1)[0].startswith(("/usr/lib/", "/System/Library/"))
                    for line in libraries
                ):
                    raise ValueError("Built runtime depends on a non-system dynamic library")
        provenance = {
            "format": 1,
            "cryptography_version": version,
            "cryptography_source_sha256": crypto["sdist"]["hash"].removeprefix("sha256:"),
            "openssl_version": openssl_version,
            "openssl_source_sha256": configuration["openssl_sha256"],
            "static_openssl": True,
            "target": configuration["target"],
            "maturin": configuration["maturin"],
        }
        add_provenance(
            wheels[0], target, version, provenance, (openssl / "LICENSE.txt").read_bytes()
        )
        run([uv, "pip", "install", "--python", str(python), "--no-deps", "--no-index", str(target)])
        run(
            [
                str(python),
                "-I",
                "-c",
                "from cryptography.hazmat.backends.openssl.backend import backend; from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; key=Ed25519PrivateKey.generate(); key.public_key().verify(key.sign(b'Mnemion native release probe'), b'Mnemion native release probe'); assert backend.openssl_version_text().startswith('OpenSSL "
                + openssl_version
                + " '); print(backend.openssl_version_text())",
            ]
        )
    print(
        json.dumps(
            {
                "wheel": target.name,
                "sha256": hashlib.file_digest(target.open("rb"), "sha256").hexdigest(),
                "openssl": openssl_version,
                "static": True,
            }
        )
    )
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(Path(__file__).resolve().parent.parent, args.output.resolve())


if __name__ == "__main__":
    main()
