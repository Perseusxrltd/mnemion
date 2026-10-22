"""Release scan boundaries use actual archives without executing their contents."""

import io
import tarfile
import zipfile

import pytest

from deploy import secret_scan as scan


def zipped(name, content):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, content)
    return stream.getvalue()


def test_nested_wheels_and_normally_excluded_names_are_inspected(tmp_path):
    package = tmp_path / "release.zip"
    package.write_bytes(zipped("nested.whl", zipped("package-lock.json", b"private-canary")))
    ordinary = tmp_path / "config.bin"
    ordinary.write_bytes(b"\x7fELF\x02\x01\x01\x00\nprivate-file-canary")
    output = io.BytesIO()
    report = scan.scan_input([ordinary, package], output)
    content = output.read()
    assert b"private-canary" in content
    assert ordinary.read_bytes() in content
    assert content.splitlines()[0].isascii()
    assert report["locations"][0]["first_line"] == 2
    assert any(
        item["member"].endswith("!nested.whl!package-lock.json") for item in report["locations"]
    )


def test_archive_expansion_and_depth_limits_fail_instead_of_skipping(tmp_path, monkeypatch):
    package = tmp_path / "large.whl"
    package.write_bytes(zipped("text.txt", b"x" * 1000))
    monkeypatch.setattr(scan, "MAX_EXPANSION", 500)
    with pytest.raises(scan.ScanError, match="oversized|budget"):
        scan.scan_input([package], io.BytesIO())
    monkeypatch.setattr(scan, "MAX_EXPANSION", 100000)
    content = b"private-nested-canary"
    for _ in range(6):
        content = zipped("nested.whl", content)
    package.write_bytes(content)
    with pytest.raises(scan.ScanError, match="depth budget"):
        scan.scan_input([package], io.BytesIO())


def test_archive_links_never_read_host_files(tmp_path):
    private = tmp_path / "private-host-data"
    private.write_bytes(b"host-file-content-must-never-be-read")
    archive = tmp_path / "links.tgz"
    with tarfile.open(archive, "w:gz") as package:
        entry = tarfile.TarInfo("../outside")
        entry.type, entry.linkname = tarfile.SYMTYPE, str(private)
        package.addfile(entry)
    output = io.BytesIO()
    scan.scan_input([archive], output)
    content = output.read()
    assert str(private).encode() in content
    assert private.read_bytes() not in content


def test_changed_scanner_cache_is_rejected_before_execution(tmp_path, monkeypatch):
    name = "linux_x64.tar.gz"
    monkeypatch.setattr(scan, "archive_name", lambda: name)
    (tmp_path / f"gitleaks_{scan.VERSION}_{name}").write_bytes(b"unverified-scanner")
    monkeypatch.setattr(
        scan.subprocess, "run", lambda *a, **k: pytest.fail("Unverified scanner executed")
    )
    with pytest.raises(scan.ScanError, match="pinned digest"):
        with scan.scanner(tmp_path):
            pytest.fail("Invalid scanner accepted")


def test_scanner_archive_rejects_linked_executable():
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        entry = tarfile.TarInfo("gitleaks")
        entry.type, entry.linkname = tarfile.SYMTYPE, "/unrelated/program"
        archive.addfile(entry)
    with pytest.raises(scan.ScanError, match="regular file"):
        scan.executable_bytes(output.getvalue(), "linux_x64.tar.gz")


def test_existing_exact_bounded_reader_exception_keeps_its_narrow_scope():
    import re
    import tomllib

    config = tomllib.loads((scan.ROOT / ".gitleaks.toml").read_text())
    pattern = next(item for item in config["allowlists"] if item["regexTarget"] == "line")[
        "regexes"
    ][0]
    template = "    _read_json(selected.{name}, max_bytes={limit} * 1024 * 1024),"
    assert re.fullmatch(pattern, template.format(name="credentials", limit=16))
    assert not re.fullmatch(pattern, template.format(name="credentials", limit=32))
