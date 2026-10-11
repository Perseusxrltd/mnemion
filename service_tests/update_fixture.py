"""Tiny real package archives for service update protocol tests."""

import io
from pathlib import Path
import tarfile
import zipfile


def package_inputs(root: Path, *, version: str = "4.0.8") -> Path:
    (root / "mnemion/service/migrations").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname="mnemion"\nversion="{version}"\nrequires-python=">=3.12,<3.15"\n'
    )
    (root / "uv.lock").write_bytes(b"fixture locked dependencies")
    (root / "mnemion/__init__.py").write_bytes(b"")
    (root / "mnemion/version.py").write_text(f'__version__ = "{version}"\n')
    (root / "mnemion/service/migrations/001_initial.sql").write_bytes(b"fixture schema")
    artifacts = root / "artifacts"
    artifacts.mkdir()
    rebuild_packages(root, artifacts, version)
    return artifacts


def rebuild_packages(
    root: Path, artifacts: Path, version: str = "4.0.8", *, extra_source=(), extra_wheel=()
):
    files = [root / "pyproject.toml", root / "uv.lock"] + sorted(
        p for p in (root / "mnemion").rglob("*") if p.is_file()
    )
    with tarfile.open(artifacts / f"mnemion-{version}.tar.gz", "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=f"mnemion-{version}/{path.relative_to(root).as_posix()}")
        for name, data, kind in extra_source:
            entry = tarfile.TarInfo(name)
            entry.type = kind
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    with zipfile.ZipFile(artifacts / f"mnemion-{version}-py3-none-any.whl", "w") as archive:
        for path in files:
            if path.is_relative_to(root / "mnemion"):
                archive.write(path, arcname=path.relative_to(root).as_posix())
        archive.writestr(
            f"mnemion-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: mnemion\nVersion: {version}\nRequires-Python: <3.15,>=3.12\n\n",
        )
        for name, data in extra_wheel:
            archive.writestr(name, data)
