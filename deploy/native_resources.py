"""Assemble and verify the exact native resources shipped inside a desktop app.

This build-only module never starts a service or opens a user's workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct

ROOT = Path(__file__).resolve().parents[1]


def source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [root / "studio/engine/main.py", root / "pyproject.toml", root / "uv.lock"]
    paths += [
        p
        for p in (root / "mnemion").rglob("*")
        if p.is_file() and p.suffix in {".py", ".sql", ".json", ".yaml", ".yml"}
    ]
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def binary_target(path: Path) -> tuple[str, set[str]] | None:
    """Read headers, never execute a file to discover its architecture."""
    with path.open("rb") as stream:
        header = stream.read(64)
        if header[:2] == b"MZ":
            if len(header) != 64:
                raise ValueError("Invalid PE header")
            offset = struct.unpack_from("<I", header, 60)[0]
            if not 64 <= offset <= path.stat().st_size - 6:
                raise ValueError("Invalid PE header offset")
            stream.seek(offset)
            pe = stream.read(6)
            if pe[:4] != b"PE\0\0":
                raise ValueError("Invalid PE signature")
            codes, platform = [struct.unpack_from("<H", pe, 4)[0]], "windows"
            mapping = {0x8664: "x64", 0xAA64: "arm64"}
        elif header[:4] == b"\x7fELF":
            if len(header) != 64 or header[4:6] != b"\x02\x01":
                raise ValueError("The runtime requires a 64-bit little-endian ELF binary")
            codes, platform = [struct.unpack_from("<H", header, 18)[0]], "linux"
            mapping = {62: "x64", 183: "arm64"}
        elif header[:4] == b"\xcf\xfa\xed\xfe":
            codes, platform = [struct.unpack_from("<I", header, 4)[0]], "macos"
            mapping = {0x01000007: "x64", 0x0100000C: "arm64"}
        elif header[:4] in {b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}:
            count = struct.unpack_from(">I", header, 4)[0]
            if not 1 <= count <= 8:
                raise ValueError("Invalid universal Mach-O binary")
            width = 32 if header[:4] == b"\xca\xfe\xba\xbf" else 20
            stream.seek(8)
            records = stream.read(count * width)
            if len(records) != count * width:
                raise ValueError("Incomplete universal Mach-O binary")
            codes, platform = (
                [struct.unpack_from(">I", records, i * width)[0] for i in range(count)],
                "macos",
            )
            mapping = {0x01000007: "x64", 0x0100000C: "arm64"}
        else:
            return None
    if any(code not in mapping for code in codes):
        raise ValueError("Unsupported native architecture")
    return platform, {mapping[code] for code in codes}


def verify_component(directory: Path, component: str, platform: str, arch: str) -> dict:
    manifest = directory / "mnemion-runtime.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 4 * 1024**2:
        raise ValueError("Missing or oversized native file inventory")
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if any(
        metadata.get(key) != value
        for key, value in {
            "format": 1,
            "component": component,
            "platform": platform,
            "architecture": arch,
        }.items()
    ):
        raise ValueError("Native component target differs from the desktop target")
    files = metadata.get("files")
    if not isinstance(files, dict) or not files or len(files) > 10000:
        raise ValueError("Invalid native file inventory")
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Native resources must contain only ordinary files and directories")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(files) | {"mnemion-runtime.json"}:
        raise ValueError("Native resource inventory is incomplete")
    binaries = 0
    total = 0
    seen = set()
    for name, expected in files.items():
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or ":" in name
            or "\\" in name
            or path.as_posix() != name
            or name.casefold() in seen
        ):
            raise ValueError("Unsafe native resource inventory path")
        seen.add(name.casefold())
        target = directory / name
        total += target.stat().st_size
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            target.stat().st_size != expected.get("size")
            or digest != expected.get("sha256")
            or (
                os.name != "nt"
                and bool(target.stat().st_mode & 0o111) != expected.get("executable")
            )
        ):
            raise ValueError("Native resource differs from its inventory: " + name)
        binary = binary_target(target)
        if binary:
            binaries += 1
            if binary[0] != platform or arch not in binary[1]:
                raise ValueError("Native binary architecture differs from its component: " + name)
    if total > 768 * 1024**2 or not binaries:
        raise ValueError("Native runtime exceeds its size budget or contains no binaries")
    suffix = ".exe" if platform == "windows" else ""
    if component == "service":
        required = [
            "mnemion-engine" + suffix,
            "licenses/LICENSE",
            "licenses/NOTICE",
            "licenses/inventory.json",
            "licenses/sbom.cdx.json",
        ]
        if metadata.get("model_weights_bundled") is not False:
            raise ValueError("Model weights must remain a managed first-run download")
    else:
        required = [
            "bin/" + name + suffix
            for name in ("postgres", "pg_ctl", "initdb", "pg_dump", "pg_restore", "psql")
        ]
        required += [
            "licenses/" + name + ".txt" for name in ("postgresql", "pgvector", "openssl", "zlib")
        ]
        if metadata.get("sources") != {
            name: json.loads((ROOT / "deploy/native-postgres.json").read_text())[name]
            for name in ("postgresql", "pgvector", "openssl", "zlib")
        }:
            raise ValueError("The database does not use the reviewed source manifest")
    if not all(name in files and files[name]["size"] > 0 for name in required):
        raise ValueError("Native runtime is missing a required executable or license")
    if os.name != "nt" and any(
        not files[name]["executable"] for name in required if not name.startswith("licenses/")
    ):
        raise ValueError("Native runtime entry points must retain executable permissions")
    return metadata


def verify(
    resources: Path, platform: str, arch: str, version: str, *, check_source: bool = True
) -> dict:
    database_arch = "x64" if platform == "windows" else arch
    engine_arch = "x64" if platform == "windows" else arch
    engine = verify_component(resources / "engine", "service", platform, engine_arch)
    database = verify_component(resources / "postgresql", "postgresql", platform, database_arch)
    if (
        engine.get("version") != version
        or engine.get("lock_sha256") != hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    ):
        raise ValueError("Native engine version or locked dependencies differ from the app")
    if check_source and engine.get("source_sha256") != source_digest(ROOT):
        raise ValueError("Native engine was frozen from different source files")
    result = {
        "format": 1,
        "version": version,
        "platform": platform,
        "desktop_architecture": arch,
        "engine_architecture": engine_arch,
        "database_architecture": database_arch,
        "database_emulation": platform == "windows" and arch == "arm64",
        "engine_files": len(engine["files"]),
        "database_files": len(database["files"]),
        "model_weights_bundled": False,
    }
    if engine_arch != arch:
        result["engine_emulation"] = True
    inventory = resources / "native-runtime.json"
    if inventory.exists() and json.loads(inventory.read_text()) != result:
        raise ValueError("Desktop native resource inventory differs from its components")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--platform", choices=["linux", "macos", "windows"], required=True)
    parser.add_argument("--arch", choices=["x64", "arm64"], required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--engine-archive", type=Path)
    parser.add_argument("--database-archive", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise ValueError("Invalid desktop version")
    if bool(args.engine_archive) != bool(args.database_archive):
        raise ValueError("Assembly requires both native archives")
    if args.engine_archive:
        from deploy.probe_native_postgres import expand

        args.resources.mkdir(parents=True)
        expand(args.engine_archive, args.resources / "engine", component="service")
        expand(args.database_archive, args.resources / "postgresql")
    result = verify(args.resources, args.platform, args.arch, args.version)
    if args.engine_archive:
        (args.resources / "native-runtime.json").write_text(json.dumps(result, indent=2) + "\n")
    elif not (args.resources / "native-runtime.json").is_file():
        raise ValueError("The desktop native resource inventory is missing")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
