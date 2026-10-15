"""Backup publication must flush successfully on every native filesystem."""

import errno
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
import zipfile

import pytest

from mnemion.archives import private_json, publish_file, verified_archive, write_archive


def test_verified_archive_round_trip_is_complete_and_does_not_replace_an_existing_backup(tmp_path):
    source = tmp_path / "source.txt"
    payload = "Synthetic recovery evidence: équipe, memories and permissions.\n".encode()
    source.write_bytes(payload)
    output = tmp_path / "backup.zip"
    manifest = write_archive(
        output, {"source.txt": source}, {"format": "publication-test", "version": 1}
    )
    original = output.read_bytes()
    with verified_archive(output, "publication-test") as (actual, unpacked):
        assert actual == manifest
        assert (unpacked / "source.txt").read_bytes() == payload
    with pytest.raises(FileExistsError):
        write_archive(output, {"source.txt": source}, {"format": "publication-test", "version": 1})
    assert output.read_bytes() == original
    assert not list(tmp_path.glob(".mnemion-archive-*"))


def test_recovery_json_is_complete_private_and_exclusive(tmp_path):
    output = tmp_path / "ledger.json"
    value = {"format": "publication-test", "scope": "équipe", "deleted": ["fixture"]}
    private_json(output, value)
    original = output.read_bytes()
    assert json.loads(original) == value
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        private_json(output, {"replacement": True})
    assert output.read_bytes() == original
    assert not list(tmp_path.glob(".mnemion-json-*"))


def test_archive_admits_staging_capacity_before_extracting_any_payload(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "backup.zip"
    source.write_bytes(b"retained archive evidence")
    write_archive(output, {"source": source}, {"format": "disk-check", "version": 1})
    before = output.read_bytes()
    monkeypatch.setattr("mnemion.archives.shutil.disk_usage", lambda path: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match="disk space"):
        with verified_archive(output, "disk-check", temporary_directory=tmp_path):
            pytest.fail("A full staging drive must not publish extracted data")
    assert output.read_bytes() == before
    assert not list(tmp_path.glob("mnemion-verified-*"))


def test_failed_flush_does_not_publish_or_remove_staged_bytes(tmp_path, monkeypatch):
    staged, output = tmp_path / "staged", tmp_path / "published"
    staged.write_bytes(b"complete but not confirmed durable")

    def unavailable(descriptor):
        raise OSError(errno.EIO, "Synthetic flush failure")

    monkeypatch.setattr("mnemion.archives.os.fsync", unavailable)
    with pytest.raises(OSError) as error:
        publish_file(staged, output)
    assert error.value.errno == errno.EIO
    assert not output.exists()
    assert staged.read_bytes() == b"complete but not confirmed durable"


def test_concurrent_publishers_cannot_overwrite_the_winning_backup(tmp_path):
    output = tmp_path / "published"
    barrier = Barrier(2)

    def publish(number):
        staged = tmp_path / str(number)
        content = ("publisher-" + str(number)).encode()
        staged.write_bytes(content)
        barrier.wait(timeout=10)
        try:
            publish_file(staged, output)
        except FileExistsError:
            return None
        return content

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, (1, 2)))
    winners = [value for value in results if value is not None]
    assert len(winners) == 1
    assert output.read_bytes() == winners[0]


def test_filesystem_without_hard_links_uses_exclusive_native_publication(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError(errno.EOPNOTSUPP, "Synthetic filesystem without hard links")

    monkeypatch.setattr("mnemion.archives.os.link", unavailable)
    staged, output = tmp_path / "staged", tmp_path / "published"
    staged.write_bytes(b"Verified recovery bytes")
    publish_file(staged, output)
    assert output.read_bytes() == b"Verified recovery bytes"
    assert not staged.exists()
    staged.write_bytes(b"Another backup")
    with pytest.raises(FileExistsError):
        publish_file(staged, output)
    assert staged.read_bytes() == b"Another backup"
    assert output.read_bytes() == b"Verified recovery bytes"


def test_no_link_fallback_preserves_exclusion_between_concurrent_publishers(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError(errno.EOPNOTSUPP, "Synthetic filesystem without hard links")

    monkeypatch.setattr("mnemion.archives.os.link", unavailable)
    test_concurrent_publishers_cannot_overwrite_the_winning_backup(tmp_path)


def test_failed_atomic_fallback_never_uses_an_overwriting_rename(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError(errno.EOPNOTSUPP, "Synthetic unsupported filesystem")

    monkeypatch.setattr("mnemion.archives.os.link", unavailable)
    monkeypatch.setattr("mnemion.archives._rename_exclusive", unavailable)
    staged, output = tmp_path / "staged", tmp_path / "published"
    staged.write_bytes(b"Retained complete source")
    with pytest.raises(OSError):
        publish_file(staged, output)
    assert staged.read_bytes() == b"Retained complete source"
    assert not output.exists()


def test_cancellation_after_one_archive_block_never_publishes_partial_output(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "cancelled.zip"
    source.write_bytes(bytes(range(256)) * (12 * 1024))
    stopped = Event()
    original = zipfile._ZipWriteFile.write
    chunks = []

    def written(stream, data):
        result = original(stream, data)
        chunks.append(len(data))
        stopped.set()
        return result

    def checkpoint():
        if stopped.is_set():
            raise InterruptedError("Requested archive cancellation")

    monkeypatch.setattr(zipfile._ZipWriteFile, "write", written)
    with pytest.raises(InterruptedError):
        write_archive(
            output,
            {"source": source},
            {"format": "cancel-test", "version": 1},
            check_cancelled=checkpoint,
        )
    assert chunks == [1024 * 1024]
    assert source.stat().st_size == 3 * 1024 * 1024
    assert not output.exists() and not list(tmp_path.glob(".mnemion-archive-*"))


def test_cancelled_verification_removes_only_its_private_staging(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "verified.zip"
    source.write_bytes(bytes(range(256)) * (12 * 1024))
    write_archive(output, {"source": source}, {"format": "cancel-test", "version": 1})
    before = output.read_bytes()
    scratch = tmp_path / "Private verification"
    scratch.mkdir(mode=0o700)
    retained = scratch / "retained"
    retained.write_bytes(b"Existing unrelated private data")
    stopped = Event()
    locations = []
    original = zipfile.ZipExtFile.read

    def reading(stream, size=-1):
        data = original(stream, size)
        if stream.name == "source" and data:
            locations.extend(scratch.glob("mnemion-verified-*"))
            stopped.set()
        return data

    def checkpoint():
        if stopped.is_set():
            raise InterruptedError("Requested verification cancellation")

    monkeypatch.setattr(zipfile.ZipExtFile, "read", reading)
    with (
        pytest.raises(InterruptedError),
        verified_archive(
            output, "cancel-test", temporary_directory=scratch, check_cancelled=checkpoint
        ),
    ):
        pytest.fail("Cancelled verification must not expose unpacked data")
    assert locations and all(path.parent == scratch and not path.exists() for path in locations)
    assert retained.read_bytes() == b"Existing unrelated private data"
    assert output.read_bytes() == before
