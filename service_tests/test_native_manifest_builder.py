"""SDK orchestration/inventory fixtures; real PE/SDK behavior has a native gate."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import struct
from types import SimpleNamespace
from xml.etree import ElementTree as ET
import zipfile

import pytest

from deploy import build_native_postgres as builder

ASM = "urn:schemas-microsoft-com:asm.v1"
ASM3 = "urn:schemas-microsoft-com:asm.v3"
CODEPAGE = "http://schemas.microsoft.com/SMI/2019/WindowsSettings"


def manifest(*, codepage=None, identity=True):
    root = ET.Element(f"{{{ASM}}}assembly", manifestVersion="1.0")
    if identity:
        ET.SubElement(
            root,
            f"{{{ASM}}}assemblyIdentity",
            name="Preserved.Upstream",
            version="18.6.0.0",
            type="win32",
        )
    trust = ET.SubElement(root, f"{{{ASM3}}}trustInfo")
    security = ET.SubElement(trust, f"{{{ASM3}}}security")
    privileges = ET.SubElement(security, f"{{{ASM3}}}requestedPrivileges")
    ET.SubElement(
        privileges, f"{{{ASM3}}}requestedExecutionLevel", level="asInvoker", uiAccess="false"
    )
    dependency = ET.SubElement(root, f"{{{ASM}}}dependency")
    assembly = ET.SubElement(dependency, f"{{{ASM}}}dependentAssembly")
    ET.SubElement(
        assembly,
        f"{{{ASM}}}assemblyIdentity",
        name="Preserved.Dependency",
        version="1.0.0.0",
        type="win32",
    )
    if codepage:
        application = ET.SubElement(root, f"{{{ASM3}}}application")
        windows = ET.SubElement(application, f"{{{ASM3}}}windowsSettings")
        ET.SubElement(windows, f"{{{CODEPAGE}}}activeCodePage").text = codepage
    return ET.tostring(root)


class ManifestSDK:
    def __init__(self, resources, fault=None):
        self.resources, self.fault, self.embedded = resources, fault, []

    @staticmethod
    def parameter(arguments, prefix):
        return next((value[len(prefix) :] for value in arguments if value.startswith(prefix)), None)

    @staticmethod
    def merge(destination, source):
        if source.text and source.text.strip():
            destination.text = source.text
        for element in source:
            existing = next(
                (
                    child
                    for child in destination
                    if child.tag == element.tag and child.attrib == element.attrib
                ),
                None,
            )
            if existing is None:
                destination.append(deepcopy(element))
            else:
                ManifestSDK.merge(existing, element)

    def run(self, command, **options):
        assert options["check"] and options["timeout"] == 30
        args = command[2:]
        resource = self.parameter(args, "-inputresource:")
        output = self.parameter(args, "-out:")
        target = self.parameter(args, "-outputresource:")
        if resource:
            if self.fault == "extract":
                raise subprocess.CalledProcessError(31, command, output="c101008c locked fixture")
            key = resource.removesuffix(";#1")
            Path(output).write_bytes(self.resources[key])
        elif output:
            inputs = args[1 : args.index("-out:" + output)]
            combined = ET.Element(f"{{{ASM}}}assembly", manifestVersion="1.0")
            for source in inputs:
                self.merge(combined, ET.parse(source).getroot())
            if self.fault == "lost_settings":
                combined.remove(combined.find(f"{{{ASM3}}}trustInfo"))
            if self.fault == "duplicate":
                windows = combined.find(f".//{{{ASM3}}}windowsSettings")
                ET.SubElement(windows, f"{{{CODEPAGE}}}activeCodePage").text = "UTF-8"
            ET.ElementTree(combined).write(output, encoding="utf-8")
        elif target:
            key = target.removesuffix(";#1")
            content = Path(args[1]).read_bytes()
            if self.fault == "corrupt_embedding":
                content = content.replace(b"UTF-8", b"Legacy")
            self.resources[key] = content
            self.embedded.append(key)
            # Simulate changing the actual PE bytes before package hashing.
            with Path(key).open("ab") as executable:
                executable.write(content)
        else:
            assert "-validate_manifest" in args
            assert ET.parse(args[1]).getroot().find(f"{{{ASM}}}assemblyIdentity") is not None
        return subprocess.CompletedProcess(command, 0, "", "")


def fixture(tmp_path, monkeypatch, *, existing=None, fault=None):
    install = tmp_path / "installed runtime"
    (install / "bin").mkdir(parents=True)
    executable = install / "bin/postgres.exe"
    header = bytearray(64)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 60, 64)
    executable.write_bytes(header + b"PE\0\0" + struct.pack("<H", 0x8664) + b"fixture executable")
    library = install / "bin/libpq.dll"
    library.write_bytes(b"MZ fixture library")
    resources = {} if existing is None else {str(executable): existing}
    sdk = ManifestSDK(resources, fault)
    monkeypatch.setattr(builder, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(builder, "_windows_has_manifest", lambda path: str(path) in resources)
    monkeypatch.setattr(builder.subprocess, "run", sdk.run)
    return install, executable, sdk


@pytest.mark.parametrize(
    "existing", [None, manifest(identity=False), manifest(), manifest(codepage="UTF-8")]
)
def test_sdk_merge_preserves_identity_trust_and_dependencies_without_duplicate_codepages(
    tmp_path, monkeypatch, existing
):
    install, executable, sdk = fixture(tmp_path, monkeypatch, existing=existing)
    assert builder.configure_windows_utf8(install, mt="fixture-mt") == ["bin/postgres.exe"]
    result = ET.fromstring(sdk.resources[str(executable)])
    assert len(result.findall(f".//{{{CODEPAGE}}}activeCodePage")) == 1
    assert result.find(f".//{{{CODEPAGE}}}activeCodePage").text == "UTF-8"
    identity = result.find(f"{{{ASM}}}assemblyIdentity")
    assert identity is not None
    if existing is None or ET.fromstring(existing).find(f"{{{ASM}}}assemblyIdentity") is None:
        assert identity.attrib["processorArchitecture"] == "amd64"
    if existing is not None:
        assert result.find(f".//{{{ASM3}}}requestedExecutionLevel").attrib == {
            "level": "asInvoker",
            "uiAccess": "false",
        }
        assert (
            result.find(f".//{{{ASM}}}dependentAssembly/{{{ASM}}}assemblyIdentity").attrib["name"]
            == "Preserved.Dependency"
        )
        prior_identity = ET.fromstring(existing).find(f"{{{ASM}}}assemblyIdentity")
        if prior_identity is not None:
            assert identity.attrib == prior_identity.attrib
    assert sdk.embedded == [str(executable)]  # DLLs never receive process manifests.


@pytest.mark.parametrize("fault", ["extract", "lost_settings", "duplicate", "corrupt_embedding"])
def test_unexpected_sdk_errors_and_manifest_changes_fail_closed(tmp_path, monkeypatch, fault):
    install, _, sdk = fixture(tmp_path, monkeypatch, existing=manifest(), fault=fault)
    with pytest.raises((ValueError, RuntimeError)) as failure:
        builder.configure_windows_utf8(install, mt="fixture-mt")
    if fault == "extract":
        assert "locked fixture" in str(failure.value)
    if fault != "corrupt_embedding":
        assert not sdk.embedded


def test_existing_conflicting_codepage_requires_review(tmp_path, monkeypatch):
    install, _, sdk = fixture(tmp_path, monkeypatch, existing=manifest(codepage="Legacy"))
    with pytest.raises(ValueError, match="changed existing"):
        builder.configure_windows_utf8(install, mt="fixture-mt")
    assert not sdk.embedded


def test_archive_inventory_hashes_the_embedded_executable(tmp_path, monkeypatch):
    install, executable, _ = fixture(tmp_path, monkeypatch)
    before = builder.digest(executable)
    builder.configure_windows_utf8(install, mt="fixture-mt")
    after = builder.digest(executable)
    assert before != after
    monkeypatch.setattr(builder, "inspect", lambda *_: {"bin/postgres.exe": []})
    sources = {}
    configuration = {}
    for component in builder.COMPONENTS:
        sources[component] = tmp_path / component
        sources[component].mkdir()
        (sources[component] / "LICENSE").write_text("Fixture source license")
        configuration[component] = {"license": "LICENSE", "version": "18.6"}
    archive = builder.package_runtime(
        install, tmp_path / "output", sources, configuration, "windows", "x64"
    )
    with zipfile.ZipFile(archive) as packaged:
        inventory = json.loads(packaged.read("mnemion-runtime.json"))
        assert inventory["files"]["bin/postgres.exe"]["sha256"] == after
        assert packaged.read("bin/postgres.exe") == executable.read_bytes()


def test_manifest_architecture_comes_from_the_pe_instead_of_the_builder_host(tmp_path, monkeypatch):
    _, executable, _ = fixture(tmp_path, monkeypatch)
    assert builder._windows_manifest_architecture(executable) == "amd64"
    value = bytearray(executable.read_bytes())
    struct.pack_into("<H", value, 68, 0xAA64)
    executable.write_bytes(value)
    assert builder._windows_manifest_architecture(executable) == "arm64"
    struct.pack_into("<H", value, 68, 0x014C)
    executable.write_bytes(value)
    with pytest.raises(ValueError, match="unsupported Windows architecture"):
        builder._windows_manifest_architecture(executable)
    struct.pack_into("<I", value, 60, 0xFFFFFFFF)
    executable.write_bytes(value)
    with pytest.raises(ValueError, match="invalid PE header offset"):
        builder._windows_manifest_architecture(executable)
