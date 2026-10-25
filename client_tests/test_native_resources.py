"""Installer resources must be complete, unchanged and executable on their target."""

import hashlib
import json
from pathlib import Path
import struct

import pytest

from deploy.native_resources import ROOT, binary_target, source_digest, verify
from deploy.release_targets import MATRIX, database_targets


def binary(platform, arch):
    header = bytearray(128)
    if platform == "windows":
        header[:2] = b"MZ"
        struct.pack_into("<I", header, 60, 64)
        header[64:68] = b"PE\0\0"
        struct.pack_into("<H", header, 68, 0x8664 if arch == "x64" else 0xAA64)
    elif platform == "linux":
        header[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", header, 18, 62 if arch == "x64" else 183)
    else:
        header[:4] = b"\xcf\xfa\xed\xfe"
        struct.pack_into("<I", header, 4, 0x01000007 if arch == "x64" else 0x0100000C)
    return bytes(header)


def fixture(root: Path, platform="linux", arch="x64"):
    for component, folder, target in (
        ("service", "engine", "x64" if platform == "windows" else arch),
        ("postgresql", "postgresql", "x64" if platform == "windows" else arch),
    ):
        directory = root / folder
        suffix = ".exe" if platform == "windows" else ""
        if component == "service":
            executables = [
                "mnemion-engine" + suffix,
                "_internal/mnemion/product_telemetry/network-state.node",
            ]
            licenses = ["LICENSE", "NOTICE", "inventory.json", "sbom.cdx.json"]
        else:
            executables = [
                "bin/" + name + suffix
                for name in ("postgres", "pg_ctl", "initdb", "pg_dump", "pg_restore", "psql")
            ]
            licenses = [name + ".txt" for name in ("postgresql", "pgvector", "openssl", "zlib")]
        for name in executables + ["licenses/" + name for name in licenses]:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                binary(platform, target) if name in executables else b"license fixture"
            )
            if name in executables:
                path.chmod(0o755)
        metadata = {
            "format": 1,
            "component": component,
            "platform": platform,
            "architecture": target,
            "version": "4.0.10",
            "model_weights_bundled": False,
            "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
            "source_sha256": source_digest(ROOT),
        }
        if component == "postgresql":
            configuration = json.loads((ROOT / "deploy/native-postgres.json").read_text())
            metadata["sources"] = {
                name: configuration[name] for name in ("postgresql", "pgvector", "openssl", "zlib")
            }
        inventory(directory, metadata)
    return root


def inventory(directory, metadata=None):
    manifest = directory / "mnemion-runtime.json"
    metadata = metadata or json.loads(manifest.read_text())
    metadata["files"] = {
        path.relative_to(directory).as_posix(): {
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "executable": bool(path.stat().st_mode & 0o111),
        }
        for path in directory.rglob("*")
        if path.is_file() and path != manifest
    }
    manifest.write_text(json.dumps(metadata))


@pytest.mark.parametrize(
    "platform,arch",
    [
        ("linux", "x64"),
        ("linux", "arm64"),
        ("macos", "x64"),
        ("macos", "arm64"),
        ("windows", "x64"),
        ("windows", "arm64"),
    ],
)
def test_all_six_targets_preserve_the_explicit_database_architecture(tmp_path, platform, arch):
    result = verify(fixture(tmp_path, platform, arch), platform, arch, "4.0.10")
    assert result["engine_architecture"] == ("x64" if platform == "windows" else arch)
    assert result.get("engine_emulation", False) == (platform == "windows" and arch == "arm64")
    assert result["database_emulation"] == (platform == "windows" and arch == "arm64")


@pytest.mark.parametrize(
    "change",
    [
        "tamper",
        "unlisted",
        "wrong_architecture",
        "wrong_platform",
        "missing_license",
        "missing_network_probe",
        "invalid_network_probe",
        "old_source",
    ],
)
def test_packaging_rejects_an_incomplete_or_wrong_runtime(tmp_path, change):
    fixture(tmp_path)
    engine = tmp_path / "engine"
    if change == "tamper":
        (engine / "mnemion-engine").write_bytes(b"tampered")
    elif change == "unlisted":
        (engine / "extra-library.so").write_bytes(binary("linux", "x64"))
    elif change in {"wrong_architecture", "wrong_platform"}:
        (engine / "mnemion-engine").write_bytes(
            binary(
                "windows" if change == "wrong_platform" else "linux",
                "arm64" if change == "wrong_architecture" else "x64",
            )
        )
        inventory(engine)
    elif change == "missing_license":
        (engine / "licenses/NOTICE").unlink()
        inventory(engine)
    elif change == "missing_network_probe":
        (engine / "_internal/mnemion/product_telemetry/network-state.node").unlink()
        inventory(engine)
    elif change == "invalid_network_probe":
        (engine / "_internal/mnemion/product_telemetry/network-state.node").write_bytes(
            b"not a library"
        )
        inventory(engine)
    else:
        manifest = engine / "mnemion-runtime.json"
        metadata = json.loads(manifest.read_text())
        metadata["source_sha256"] = "0" * 64
        manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        verify(tmp_path, "linux", "x64", "4.0.10")


@pytest.mark.parametrize("name", ["mnemion-engine.exe", "_internal/msvcp140.dll"])
def test_arm_windows_cannot_mislabel_an_arm_service_as_the_x64_backend(tmp_path, name):
    fixture(tmp_path, "windows", "arm64")
    engine = tmp_path / "engine"
    (engine / name).parent.mkdir(parents=True, exist_ok=True)
    (engine / name).write_bytes(binary("windows", "arm64"))
    inventory(engine)
    with pytest.raises(ValueError, match="architecture"):
        verify(tmp_path, "windows", "arm64", "4.0.10")


def test_universal_macos_library_contains_requested_slices(tmp_path):
    header = struct.pack(">II", 0xCAFEBABE, 2)
    header += struct.pack(">IIIII", 0x01000007, 3, 48, 64, 0)
    header += struct.pack(">IIIII", 0x0100000C, 0, 112, 64, 0)
    path = tmp_path / "universal.dylib"
    path.write_bytes(header + bytes(128))
    assert binary_target(path) == ("macos", {"x64", "arm64"})


def test_database_matrix_builds_windows_x64_once_even_for_arm_only():
    windows = [item for item in MATRIX if item["platform"] == "windows"]
    expected = [{"os": "windows-2022", "target": "windows", "arch": "x64"}]
    assert database_targets(windows) == expected
    assert database_targets([windows[1]]) == expected


def test_frozen_windows_manifest_keeps_default_safety_and_unicode_settings():
    from xml.etree import ElementTree
    from deploy.build_native_engine import windows_manifest

    template = b"""<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
      <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges>
      <requestedExecutionLevel level="asInvoker" uiAccess="false" />
      </requestedPrivileges></security></trustInfo>
      <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"><application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" />
      </application></compatibility>
      <application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
      </windowsSettings></application></assembly>"""
    result = ElementTree.fromstring(windows_manifest(template))
    settings = {node.tag.rsplit("}", 1)[-1]: node for node in result.iter()}
    assert settings["requestedExecutionLevel"].attrib == {"level": "asInvoker", "uiAccess": "false"}
    assert settings["longPathAware"].text == "true"
    assert settings["supportedOS"].attrib["Id"] == "{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"
    assert settings["activeCodePage"].text == "UTF-8"
    with pytest.raises(ValueError, match="Review"):
        windows_manifest(windows_manifest(template))
