"""Host installation archives must fail before executing altered or unsafe files."""

import hashlib
import io
import json
import socket
import ssl
import tarfile
import urllib.error
import zipfile

import pytest

from deploy.build_native_postgres import extract, fetch
from deploy import build_native_postgres as builder
from deploy.probe_native_postgres import expand


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "source/../../escape", "source/C:escape"]
)
def test_source_traversal_is_rejected(tmp_path, name):
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as out:
        entry = tarfile.TarInfo(name)
        entry.size = 3
        out.addfile(entry, io.BytesIO(b"bad"))
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, tmp_path / "expanded", "source")
    assert not (tmp_path / "escape").exists()


def test_source_links_and_case_collisions_are_rejected(tmp_path):
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as out:
        entry = tarfile.TarInfo("source/link")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "../outside"
        out.addfile(entry)
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, tmp_path / "linked", "source")
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("File", b"one")
        out.writestr("file", b"two")
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, tmp_path / "colliding", None)


def test_cached_source_hash_is_checked_without_replacing_it(tmp_path):
    expected = hashlib.sha256(b"reviewed source").hexdigest()
    cached = tmp_path / expected
    cached.write_bytes(b"altered source")
    with pytest.raises(ValueError, match="pinned digest"):
        fetch(
            {"sha256": expected, "url": "https://ftp.postgresql.org/pub/source/fixture.tar.gz"},
            tmp_path,
        )
    assert cached.read_bytes() == b"altered source"


SOURCE_URL = "https://ftp.postgresql.org/pub/source/fixture.tar.gz"
SOURCE_BYTES = b"reviewed source archive"


def source_spec():
    return {"sha256": hashlib.sha256(SOURCE_BYTES).hexdigest(), "url": SOURCE_URL}


def download_fixture(monkeypatch, responses):
    pending = iter(responses)
    calls, waits = [], []

    def open_response(request, *, timeout):
        calls.append((request.full_url, timeout))
        result = next(pending)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(builder.urllib.request, "urlopen", open_response)
    monkeypatch.setattr(builder.time, "sleep", waits.append)
    return calls, waits


def test_native_source_retries_dns_failure_and_still_checks_the_pin(tmp_path, monkeypatch):
    calls, waits = download_fixture(
        monkeypatch,
        [
            urllib.error.URLError(socket.gaierror(-2, "fixture resolver failure")),
            io.BytesIO(SOURCE_BYTES),
        ],
    )
    result = fetch(source_spec(), tmp_path)
    assert result.read_bytes() == SOURCE_BYTES
    assert calls == [(SOURCE_URL, 30)] * 2 and waits == [2]
    assert list(tmp_path.iterdir()) == [result]


def test_interrupted_source_download_discards_its_partial_bytes(tmp_path, monkeypatch):
    class Interrupted(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise ConnectionResetError("fixture transfer interrupted")
            return super().read(5)

    calls, waits = download_fixture(
        monkeypatch, [Interrupted(SOURCE_BYTES), io.BytesIO(SOURCE_BYTES)]
    )
    result = fetch(source_spec(), tmp_path)
    assert result.read_bytes() == SOURCE_BYTES
    assert len(calls) == 2 and waits == [2]
    assert list(tmp_path.iterdir()) == [result]


@pytest.mark.parametrize("status", [429, 503])
def test_native_source_retry_budget_is_bounded(tmp_path, monkeypatch, status):
    failures = [
        urllib.error.HTTPError(SOURCE_URL, status, "fixture unavailable", {}, io.BytesIO())
        for _ in range(3)
    ]
    calls, waits = download_fixture(monkeypatch, failures)
    with pytest.raises(urllib.error.HTTPError) as error:
        fetch(source_spec(), tmp_path)
    assert error.value is failures[-1]
    assert failures[0].fp.closed and failures[1].fp.closed
    assert len(calls) == 3 and waits == [2, 4]
    assert not list(tmp_path.iterdir())
    error.value.close()


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.HTTPError(SOURCE_URL, 404, "fixture missing", {}, None),
        urllib.error.URLError(ssl.SSLCertVerificationError("fixture certificate failure")),
    ],
)
def test_native_source_does_not_retry_permanent_or_tls_failures(tmp_path, monkeypatch, failure):
    calls, waits = download_fixture(monkeypatch, [failure])
    with pytest.raises(type(failure)):
        fetch(source_spec(), tmp_path)
    assert len(calls) == 1 and not waits and not list(tmp_path.iterdir())


def test_native_source_integrity_failure_stops_without_retry(tmp_path, monkeypatch):
    calls, waits = download_fixture(monkeypatch, [io.BytesIO(b"unexpected source")])
    with pytest.raises(ValueError, match="pinned digest"):
        fetch(source_spec(), tmp_path)
    assert len(calls) == 1 and not waits and not list(tmp_path.iterdir())


def test_native_source_does_not_delete_another_transfers_file(tmp_path, monkeypatch):
    temporary = tmp_path / (source_spec()["sha256"] + ".download")
    temporary.write_bytes(b"another transfer owns this file")
    calls, waits = download_fixture(monkeypatch, [io.BytesIO(SOURCE_BYTES)])
    with pytest.raises(FileExistsError):
        fetch(source_spec(), tmp_path)
    assert temporary.read_bytes() == b"another transfer owns this file"
    assert len(calls) == 1 and not waits


def test_inventory_detects_changed_native_code_and_unlisted_files(tmp_path):
    original = b"native binary fixture"
    metadata = {
        "format": 1,
        "component": "postgresql",
        "files": {
            "bin/postgres": {
                "sha256": hashlib.sha256(original).hexdigest(),
                "size": len(original),
                "executable": False,
            }
        },
    }

    def bundle(name, content, extra=False):
        archive = tmp_path / (name + ".zip")
        with zipfile.ZipFile(archive, "w") as out:
            out.writestr("mnemion-runtime.json", json.dumps(metadata))
            out.writestr("bin/postgres", content)
            if extra:
                out.writestr("unexpected-library", b"extra")
        return archive

    assert expand(bundle("valid", original), tmp_path / "valid")["component"] == "postgresql"
    with pytest.raises(ValueError, match="differs"):
        expand(bundle("altered", original.replace(b"native", b"unsafe")), tmp_path / "altered")
    with pytest.raises(ValueError, match="inventory"):
        expand(bundle("extra", original, True), tmp_path / "extra")
