"""Selected-file read failures stay categorized without publishing host errors."""

import errno
import hashlib
import os

import pytest

from mnemion.connectors.protocol import Document, SkippedDocument
from mnemion.connectors.providers import FilesystemConfig, FilesystemProvider
from mnemion.connectors.source_files import (
    INVENTORY_STOP_CODES,
    SourceReadError,
    classify_source_os_error,
    read_selected,
    relative_evidence,
)
from mnemion.service.connector_models import SourceFileError
from mnemion.source_codes import ACCESS_WITHHOLD_CODES


def published():
    return {
        "scope_id": "fixture",
        "name": "Fixture",
        "members": [],
        "publish_to_mapped_members": True,
        "max_file_bytes": 1000,
    }


def test_os_errors_use_fixed_categories_and_drop_host_text():
    private = "PRIVATE_OS_STRING"
    absolute = r"C:\secret\notes.md"
    assert classify_source_os_error(PermissionError(errno.EACCES, private, absolute)) == (
        "source_permission_denied"
    )
    assert classify_source_os_error(FileNotFoundError(errno.ENOENT, private, absolute)) == (
        "source_disappeared"
    )
    assert classify_source_os_error(OSError(errno.ELOOP, private, absolute)) == (
        "source_link_or_handle_changed"
    )
    assert classify_source_os_error(OSError(errno.EIO, private, absolute)) == "source_io_failed"
    denied = SourceReadError("source_permission_denied", relative="notes/denied.md")
    assert str(denied) == "source_permission_denied"
    assert private not in str(denied) and absolute not in str(denied)
    assert relative_evidence(absolute) == {}
    assert relative_evidence("../secret.md") == {}
    assert INVENTORY_STOP_CODES == ACCESS_WITHHOLD_CODES
    assert "source_too_large" not in ACCESS_WITHHOLD_CODES
    assert (
        set(SourceFileError.model_fields["error_code"].annotation.__args__) >= INVENTORY_STOP_CODES
    )


def _inject(monkeypatch, name, error, opened=None):
    """Raise for one selected file. Windows must hit the no-follow opener, not os.open."""
    from pathlib import Path

    from mnemion.connectors import source_files

    if os.name == "nt":
        real = source_files._windows_open_unfollowed

        def guarded(path, relative):
            chosen = Path(path).name
            if opened is not None:
                opened.append(chosen)
            if chosen == name:
                raise error
            return real(path, relative)

        monkeypatch.setattr(source_files, "_windows_open_unfollowed", guarded)
        return
    real = source_files.os.open

    def guarded(path, flags, *args, **kwargs):
        chosen = os.fsdecode(path)
        if opened is not None:
            opened.append(chosen)
        if chosen == name:
            raise error
        return real(path, flags, *args, **kwargs)

    monkeypatch.setattr(source_files.os, "supports_dir_fd", {*os.supports_dir_fd, guarded})
    monkeypatch.setattr(source_files.os, "open", guarded)


def test_read_selected_distinguishes_denial_disappearance_link_and_io(tmp_path, monkeypatch):
    root = tmp_path / "notes"
    root.mkdir()
    (root / "readable.md").write_text("synthetic permitted text", encoding="utf-8")
    assert read_selected(root, "readable.md", 1000) == b"synthetic permitted text"
    with pytest.raises(SourceReadError) as missing:
        read_selected(root, "missing.md", 1000)
    assert missing.value.code == "source_disappeared" and missing.value.relative == "missing.md"
    assert "synthetic" not in str(missing.value)

    outside = tmp_path / "outside.md"
    outside.write_text("synthetic-outside", encoding="utf-8")
    try:
        (root / "linked.md").symlink_to(outside)
    except OSError:
        pytest.skip("Creating a test symlink requires an extra privilege on this account")
    with pytest.raises(SourceReadError) as linked:
        read_selected(root, "linked.md", 1000)
    assert linked.value.relative == "linked.md"
    assert linked.value.code in {
        "source_link_or_handle_changed",
        "source_outside_selected_root",
        "source_is_not_regular_file",
    }
    assert "synthetic-outside" not in str(linked.value)

    (root / "denied.md").write_text("synthetic denied", encoding="utf-8")
    _inject(
        monkeypatch,
        "denied.md",
        PermissionError(errno.EACCES, "PRIVATE_OS_STRING", str(root / "denied.md")),
    )
    with pytest.raises(SourceReadError) as denied:
        read_selected(root, "denied.md", 1000)
    assert denied.value.code == "source_permission_denied"
    assert denied.value.relative == "denied.md"
    assert "PRIVATE_OS_STRING" not in str(denied.value)
    assert str(root) not in str(denied.value)

    _inject(
        monkeypatch, "denied.md", OSError(errno.EIO, "PRIVATE_OS_STRING", str(root / "denied.md"))
    )
    with pytest.raises(SourceReadError) as failed:
        read_selected(root, "denied.md", 1000)
    assert failed.value.code == "source_io_failed"
    assert "PRIVATE_OS_STRING" not in str(failed.value)


def test_in_root_symlink_is_refused_and_ordinary_file_remains(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    (root / "a-plain.md").write_text("ordinary selected", encoding="utf-8")
    (root / "z-target.md").write_text("IN_ROOT_TARGET", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("OUTSIDE_REDIRECT", encoding="utf-8")
    try:
        (root / "m-link.md").symlink_to(root / "z-target.md")
        (root / "n-outside.md").symlink_to(outside)
    except OSError:
        pytest.skip("Creating a test symlink requires an extra privilege on this account")
    with pytest.raises(SourceReadError) as linked:
        read_selected(root, "m-link.md", 1000)
    assert linked.value.code == "source_link_or_handle_changed" or linked.value.code in {
        "source_outside_selected_root",
        "source_is_not_regular_file",
    }
    assert linked.value.relative == "m-link.md"
    assert "IN_ROOT_TARGET" not in str(linked.value)
    assert read_selected(root, "a-plain.md", 1000) == b"ordinary selected"
    provider = FilesystemProvider(
        FilesystemConfig(path=root, **published() | {"max_file_bytes": 1000})
    )
    results = list(provider.documents(provider.scopes()[0]))
    documents = [value for value in results if isinstance(value, Document)]
    stopped = [value for value in results if isinstance(value, SkippedDocument)]
    assert [value.external_id for value in documents] == ["a-plain.md"]
    assert documents[0].text == "ordinary selected"
    assert stopped and stopped[0].abort_inventory and stopped[0].path == "m-link.md"
    assert stopped[0].code in {
        "source_link_or_handle_changed",
        "source_outside_selected_root",
        "source_is_not_regular_file",
    }
    rendered = repr(results)
    assert "IN_ROOT_TARGET" not in rendered and "OUTSIDE_REDIRECT" not in rendered


def test_permission_denial_stops_before_later_files_and_keeps_content_skips(tmp_path, monkeypatch):
    root = tmp_path / "notes"
    root.mkdir()
    (root / "a-denied.md").write_text("synthetic denied", encoding="utf-8")
    (root / "b-later.md").write_text("synthetic later", encoding="utf-8")
    (root / "c-binary.md").write_bytes(b"\xff")
    opened = []
    _inject(
        monkeypatch,
        "a-denied.md",
        PermissionError(errno.EACCES, "PRIVATE_OS_STRING"),
        opened,
    )
    provider = FilesystemProvider(FilesystemConfig(path=root, **published()))
    results = list(provider.documents(provider.scopes()[0]))
    stopped = [value for value in results if isinstance(value, SkippedDocument)]
    assert [(value.path, value.code, value.abort_inventory) for value in stopped] == [
        ("a-denied.md", "source_permission_denied", True)
    ]
    assert not any(isinstance(value, Document) for value in results)
    assert "b-later.md" not in opened
    assert "PRIVATE_OS_STRING" not in repr(results)
    report = stopped[0].report()
    assert report["path"] == "a-denied.md"
    assert report["path_sha256"] == hashlib.sha256(b"a-denied.md").hexdigest()
    assert "synthetic later" not in repr(results)


def test_ordinary_text_still_reads_and_oversize_stays_a_content_skip(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    (root / "ok.md").write_text("ok", encoding="utf-8")
    (root / "big.md").write_text("x" * 50, encoding="utf-8")
    provider = FilesystemProvider(
        FilesystemConfig(path=root, **published() | {"max_file_bytes": 10})
    )
    results = list(provider.documents(provider.scopes()[0]))
    assert any(isinstance(value, Document) and value.external_id == "ok.md" for value in results)
    skipped = [value for value in results if isinstance(value, SkippedDocument)]
    assert [(value.path, value.code, value.abort_inventory) for value in skipped] == [
        ("big.md", "source_too_large", False)
    ]


def test_cloud_placeholder_tag_is_not_a_name_redirect(tmp_path, monkeypatch):
    # The cloud values are the documented tags, applied to an ordinary local
    # file. No cloud provider is configured and no hydration runs.
    from mnemion.connectors import source_files

    reparse = 0x400
    assert source_files._windows_reparse_is_name_redirect(reparse, 0xA000000C)
    assert source_files._windows_reparse_is_name_redirect(reparse, 0xA0000003)
    assert source_files._windows_reparse_is_name_redirect(reparse, 0x80000017)
    assert source_files._windows_reparse_is_name_redirect(reparse, 0x9000001A | 0x20000000)
    assert not source_files._windows_reparse_is_name_redirect(reparse, 0x9000001A)
    assert not source_files._windows_reparse_is_name_redirect(reparse, 0x9000F01A)
    assert not source_files._windows_reparse_is_name_redirect(0x20, 0)
    if os.name != "nt":
        return
    root = tmp_path / "notes"
    root.mkdir()
    (root / "cloud.md").write_text("synthetic cloud body", encoding="utf-8")
    calls = {"n": 0}

    def cloud_tag(kernel, handle):
        calls["n"] += 1
        return reparse, 0x9000001A

    monkeypatch.setattr(source_files, "_windows_reparse_tag", cloud_tag)
    assert read_selected(root, "cloud.md", 1000) == b"synthetic cloud body"
    assert calls["n"] == 2
    calls["n"] = 0

    def symlink_tag(kernel, handle):
        calls["n"] += 1
        return reparse, 0xA000000C

    monkeypatch.setattr(source_files, "_windows_reparse_tag", symlink_tag)
    with pytest.raises(SourceReadError) as linked:
        read_selected(root, "cloud.md", 1000)
    assert linked.value.code == "source_link_or_handle_changed"
    assert linked.value.relative == "cloud.md"
    assert "synthetic cloud body" not in str(linked.value)
    assert calls["n"] == 1


def test_windows_failed_handle_conversion_closes_the_raw_handle(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows HANDLE ownership is checked on a native Windows interpreter")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    root = tmp_path / "notes"
    root.mkdir()
    (root / "plain.md").write_text("ordinary selected", encoding="utf-8")

    def handles():
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        current = kernel.GetCurrentProcess
        current.restype = wintypes.HANDLE
        get = kernel.GetProcessHandleCount
        get.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get.restype = wintypes.BOOL
        count = wintypes.DWORD()
        if not get(current(), ctypes.byref(count)):
            raise OSError(ctypes.get_last_error(), "GetProcessHandleCount")
        return count.value

    def explode(handle, flags):
        raise OSError(errno.EINVAL, "conversion failed")

    monkeypatch.setattr(msvcrt, "open_osfhandle", explode)
    before = handles()
    for _ in range(20):
        with pytest.raises(SourceReadError) as failed:
            read_selected(root, "plain.md", 1000)
        assert failed.value.code == "source_io_failed"
        assert failed.value.relative == "plain.md"
        assert "ordinary selected" not in str(failed.value)
    assert handles() - before < 5
