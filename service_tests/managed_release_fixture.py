"""Real Python packages with temporary fixture keys, never publication assets."""

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tomllib
import zipfile

from deploy.service_update_manifest import signed_document
from mnemion.service.studio import bundle_files


def checkout(destination: Path, public_key: bytes) -> Path:
    repository = Path(__file__).resolve().parents[1]
    destination.mkdir(mode=0o700)
    shutil.copytree(
        repository / "mnemion",
        destination / "mnemion",
        ignore=shutil.ignore_patterns("__pycache__", "_studio"),
    )
    for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "NOTICE"):
        shutil.copyfile(repository / name, destination / name)
    (destination / "studio/frontend").mkdir(parents=True)
    (destination / "studio/frontend/package.json").write_text('{"name":"mnemion-studio"}')
    (destination / "mnemion/service/update_trust.py").write_text(
        "import base64\nSERVICE_UPDATE_PUBLIC_KEY = base64.b64decode("
        + repr(base64.b64encode(public_key).decode())
        + ")\n"
    )
    version = tomllib.loads((destination / "pyproject.toml").read_text())["project"]["version"]
    studio(destination, version)
    return destination


def studio(root: Path, version: str):
    """Minimal protocol fixture UI; this is not a product/visual smoke test."""
    path = root / "mnemion/_studio"
    if path.exists():
        shutil.rmtree(path)
    (path / "assets").mkdir(parents=True)
    (path / "notices").mkdir()
    (path / "index.html").write_text(
        '<!doctype html><p>Managed update protocol fixture</p><script src="/assets/fixture.js"></script>'
    )
    (path / "assets/fixture.js").write_text(f"window.fixtureVersion={json.dumps(version)};")
    for name in ("LICENSE", "NOTICE"):
        (path / "notices" / name).write_text("Protocol fixture only")
    (path / "notices/inventory.json").write_text("{}")
    (path / "release.json").write_text(
        json.dumps({"schema": 1, "version": version, "base": "/", "files": bundle_files(path)})
    )


def candidate(
    bootstrap: Path, destination: Path, version: str, key, *, fail_worker=False
) -> tuple[Path, bytes]:
    shutil.copytree(bootstrap, destination)
    project = destination / "pyproject.toml"
    old = tomllib.loads(project.read_text())["project"]["version"]
    project.write_text(
        project.read_text().replace(f'version = "{old}"', f'version = "{version}"', 1)
    )
    lock = destination / "uv.lock"
    lock.write_text(
        lock.read_text().replace(
            f'name = "mnemion"\nversion = "{old}"', f'name = "mnemion"\nversion = "{version}"', 1
        )
    )
    (destination / "mnemion/version.py").write_text(f'__version__ = "{version}"\n')
    if fail_worker:
        cli = destination / "mnemion/service/cli.py"
        text = cli.read_text()
        marker = "    args = parser.parse_args(argv)"
        assert marker in text
        cli.write_text(
            text.replace(
                marker,
                marker
                + '\n    if args.command == "worker":\n        raise RuntimeError("Intentional managed-update fixture startup failure")',
                1,
            )
        )
    studio(destination, version)
    artifacts = destination / "artifacts"
    artifacts.mkdir()
    files = [
        destination / name
        for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "NOTICE")
    ]
    code = sorted(
        path
        for path in (destination / "mnemion").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    files.extend(code)
    with tarfile.open(artifacts / f"mnemion-{version}.tar.gz", "w:gz") as archive:
        for path in files:
            archive.add(
                path, arcname=f"mnemion-{version}/{path.relative_to(destination).as_posix()}"
            )
    members = {path.relative_to(destination).as_posix(): path.read_bytes() for path in code}
    prefix = f"mnemion-{version}.dist-info/"
    members[prefix + "METADATA"] = (
        f"Metadata-Version: 2.4\nName: mnemion\nVersion: {version}\nRequires-Python: >=3.12,<3.15\n\n".encode()
    )
    members[prefix + "WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: managed-protocol-fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, content in members.items():
        writer.writerow(
            [
                name,
                "sha256="
                + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("="),
                len(content),
            ]
        )
    writer.writerow([prefix + "RECORD", "", ""])
    members[prefix + "RECORD"] = record.getvalue().encode()
    with zipfile.ZipFile(
        artifacts / f"mnemion-{version}-py3-none-any.whl", "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    envelope = signed_document(
        destination,
        artifacts,
        "a" * 40,
        key.private_bytes_raw(),
        key.public_key().public_bytes_raw(),
    )
    return artifacts, envelope
