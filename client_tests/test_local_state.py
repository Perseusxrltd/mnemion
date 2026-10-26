"""Local setup state must survive interruption without exposing operator secrets."""

import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from mnemion import local_state as state


@pytest.mark.parametrize("finish_publication", [True, False])
def test_status_read_waits_for_exclusive_publication_but_refuses_a_persistent_alias(
    tmp_path, monkeypatch, finish_publication
):
    root = state.directory(tmp_path / "Published state Équipe")
    path = root / "configuration.json"
    expected = {"complete": True, "version": "first publication"}
    published, release, observed = threading.Event(), threading.Event(), threading.Event()
    original_link, original_lstat = os.link, Path.lstat
    failures, timers = [], []

    def pause_publication(source, target, *args, **kwargs):
        original_link(source, target, *args, **kwargs)
        if Path(target) == path:
            published.set()
            if not release.wait(10):
                raise TimeoutError("The publication reader did not finish")

    def observe_publication(candidate, *args, **kwargs):
        info = original_lstat(candidate, *args, **kwargs)
        if candidate == path and info.st_nlink == 2 and not observed.is_set():
            observed.set()
            if finish_publication:
                timer = threading.Timer(0.02, release.set)
                timers.append(timer)
                timer.start()
        return info

    def writer():
        try:
            state.write(path, expected, replace=False)
        except Exception as error:
            failures.append(error)

    monkeypatch.setattr(os, "link", pause_publication)
    monkeypatch.setattr(Path, "lstat", observe_publication)
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        assert published.wait(5)
        if finish_publication:
            assert state.read(path) == expected
        else:
            with pytest.raises(state.LocalSetupError, match="without links"):
                state.read(path)
        assert observed.is_set()
    finally:
        release.set()
        thread.join(5)
        for timer in timers:
            timer.join(5)
    assert not thread.is_alive() and not failures
    assert path.lstat().st_nlink == 1 and state.read(path) == expected
    assert [entry.name for entry in root.iterdir()] == [path.name]


def test_record_link_added_after_path_check_is_refused_before_reading(tmp_path, monkeypatch):
    root = state.directory(tmp_path / "Private state")
    path, alias = root / "state.json", root / "alias.json"
    state.write(path, {"private": True})
    original_open = os.open

    def link_before_open(candidate, *args, **kwargs):
        if Path(candidate) == path:
            os.link(path, alias)
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(os, "open", link_before_open)
    with pytest.raises(state.LocalSetupError, match="could not be read"):
        state.read(path)
    assert path.lstat().st_nlink == alias.lstat().st_nlink == 2


def test_interrupted_replacement_preserves_existing_private_state(tmp_path, monkeypatch):
    root = state.directory(tmp_path / "Workspace Équipe")
    path = root / "credentials.json"
    state.write(path, {"credential": "original"}, replace=False)
    before = path.read_bytes()

    def fail(*args):
        raise OSError("simulated atomic replacement failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        state.write(path, {"credential": "replacement"})
    assert state.read(path) == {"credential": "original"}
    assert path.read_bytes() == before
    assert [p.name for p in root.iterdir()] == ["credentials.json"]


@pytest.mark.skipif(os.name != "nt", reason="Windows replacement sharing semantics")
@pytest.mark.parametrize("release_reader", [True, False])
def test_windows_atomic_state_write_tolerates_a_brief_reader_but_retains_data_on_denial(
    tmp_path, monkeypatch, release_reader
):
    from client_tests.windows_acl import assert_private_acl

    root = state.directory(tmp_path / "Private state Équipe with spaces")
    path = root / "last-ledger.json"
    original = {"version": "original"}
    replacement = {"version": "replacement"}
    state.write(path, original)
    opened, release = threading.Event(), threading.Event()
    read_values, failures, timers = [], [], []

    def reader():
        # An ordinary Windows file reader denies deletion/replacement while
        # open, matching a status reader or scanner outside the writer's lock.
        with path.open("rb") as stream:
            opened.set()
            release.wait(10)
            read_values.append(json.load(stream))

    worker = threading.Thread(target=reader)
    worker.start()
    real_replace = os.replace

    def observed_replace(source, destination):
        try:
            return real_replace(source, destination)
        except OSError as error:
            failures.append(error.winerror)
            if release_reader and len(failures) == 1:
                timer = threading.Timer(0.1, release.set)
                timers.append(timer)
                timer.start()
            raise

    try:
        assert opened.wait(5)
        monkeypatch.setattr(os, "replace", observed_replace)
        if release_reader:
            state.write(path, replacement)
        else:
            with pytest.raises(
                state.LocalSetupError, match="Existing data has been retained"
            ) as caught:
                state.write(path, replacement)
            assert caught.value.code == "state_file_locked"
            assert caught.value.__cause__.winerror in {5, 32, 33}
    finally:
        release.set()
        worker.join(5)
        for timer in timers:
            timer.join(5)
    assert not worker.is_alive()
    assert failures and all(code in {5, 32, 33} for code in failures)
    assert read_values == [original]
    assert state.read(path) == (replacement if release_reader else original)
    assert_private_acl(path)
    assert not list(root.glob(".local-state-*"))


def test_local_state_rejects_linked_or_oversized_records(tmp_path):
    root = state.directory(tmp_path / "workspace")
    path = root / "state.json"
    state.write(path, {"private": True})
    with pytest.raises(FileExistsError):
        state.write(path, {"private": False}, replace=False)
    os.link(path, root / "alias.json")
    with pytest.raises(state.LocalSetupError, match="without links"):
        state.read(path)
    (root / "alias.json").unlink()
    path.write_bytes(b" " * (state.MAX_RECORD_BYTES + 1))
    with pytest.raises(state.LocalSetupError, match="could not be read"):
        state.read(path)


def test_local_operator_lock_is_exclusive_across_processes_and_released(tmp_path):
    root = state.directory(tmp_path / "workspace")
    program = (
        "import sys; from pathlib import Path; from mnemion.local_state import lock,LocalSetupError\n"
        "try:\n with lock(Path(sys.argv[1])): pass\n"
        "except LocalSetupError as e: sys.exit(23 if e.code=='workspace_busy' else 24)\n"
    )
    command = [sys.executable, "-c", program, str(root)]
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    with state.lock(root):
        assert (
            subprocess.run(command, env=environment, capture_output=True, timeout=10).returncode
            == 23
        )
    assert subprocess.run(command, env=environment, capture_output=True, timeout=10).returncode == 0


@pytest.mark.parametrize("interrupted", [False, True])
def test_private_staging_is_owned_before_use_and_removed_after_exit(tmp_path, interrupted):
    root = state.directory(tmp_path / "Private backups Équipe")

    def capture():
        with state.temporary_directory(prefix="capture-", dir=root) as staging:
            # Native backup code must be able to validate the folder immediately,
            # including when Windows' default owner would be Administrators.
            assert state.directory(staging) == staging
            if os.name == "nt":
                from client_tests.windows_acl import assert_private_acl, assert_restricted_access

                assert_private_acl(staging, directory=True)
            else:
                assert staging.stat().st_uid == os.getuid()
                assert staging.stat().st_mode & 0o077 == 0
            state.write(staging / "ledger.json", {"private": True})
            dump = staging / "database.dump"
            dump.write_bytes(b"private database fixture")
            if os.name == "nt":
                assert_private_acl(dump, inherited=True)
                assert_restricted_access(staging, dump, staging / "ledger.json")
            if interrupted:
                raise RuntimeError("Interrupted capture")

    if interrupted:
        with pytest.raises(RuntimeError, match="Interrupted capture"):
            capture()
    else:
        capture()
    assert list(root.iterdir()) == []


def test_private_staging_never_adopts_an_existing_directory(tmp_path, monkeypatch):
    from uuid import UUID

    identifier = UUID("bd0a7b14-a7dd-4d13-8278-ae30bd8fddf1")
    existing = state.directory(tmp_path / ("capture-" + identifier.hex))
    retained = existing / "retained.txt"
    retained.write_text("Existing user data")
    monkeypatch.setattr(state, "uuid4", lambda: identifier)
    with pytest.raises(FileExistsError):
        with state.temporary_directory(prefix="capture-", dir=tmp_path):
            pytest.fail("Existing directory was adopted")
    assert retained.read_text() == "Existing user data"
    with pytest.raises(FileExistsError):
        state.directory(existing, exist_ok=False)
    assert retained.read_text() == "Existing user data"


def test_private_staging_does_not_delete_a_replacement_directory(tmp_path):
    moved = tmp_path / "retained-original"
    with pytest.raises(state.LocalSetupError, match="staging folder changed"):
        with state.temporary_directory(dir=tmp_path) as staging:
            (staging / "original.txt").write_text("Original data")
            staging.rename(moved)
            state.directory(staging, exist_ok=False)
            (staging / "replacement.txt").write_text("Replacement data")
    assert (staging / "replacement.txt").read_text() == "Replacement data"
    assert (moved / "original.txt").read_text() == "Original data"


@pytest.mark.skipif(os.name == "nt", reason="POSIX ownership and private directory modes")
def test_shared_or_redirected_state_folder_is_refused(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    # A restrictive process umask must not silently make this unsafe fixture private.
    shared.chmod(0o755)
    with pytest.raises(state.LocalSetupError, match="private"):
        state.directory(shared)
    private = state.directory(tmp_path / "private")
    redirected = tmp_path / "redirected"
    redirected.symlink_to(private, target_is_directory=True)
    with pytest.raises(state.LocalSetupError, match="redirected"):
        state.directory(redirected / "nested")


@pytest.mark.skipif(os.name != "nt", reason="Native Windows inherited directory ACLs")
def test_windows_workspace_and_secrets_survive_removal_of_administrator_access(tmp_path):
    from client_tests.windows_acl import (
        assert_private_acl,
        assert_restricted_access,
    )

    root = state.directory(tmp_path / "Local workspace Équipe")
    assert_private_acl(root, directory=True)
    # PostgreSQL creates its own children. They must inherit the private ACL,
    # even when the elevated process's default owner is Administrators.
    data = root / "database"
    data.mkdir()
    record = data / "postgres-file"
    record.write_text("private database fixture")
    assert_private_acl(record, inherited=True)
    state.write(root / "state.json", {"ready": True})
    assert json.loads((root / "state.json").read_text()) == {"ready": True}
    assert_restricted_access(root, record, root / "state.json")


@pytest.mark.skipif(os.name != "nt", reason="Windows existing folder ownership")
def test_windows_refuses_existing_foreign_owned_folder_without_taking_ownership(tmp_path):
    from client_tests.windows_acl import make_administrators_owned, security_descriptor

    root = state.directory(tmp_path / "foreign-owner-fixture")
    (root / "retained.txt").write_text("keep existing data")
    if not make_administrators_owned(root):
        pytest.skip("Fixture requires an elevated process; native Windows CI runs elevated")
    before = security_descriptor(root)
    with pytest.raises(state.LocalSetupError, match="owned by your OS account"):
        state.directory(root)
    assert security_descriptor(root) == before
    assert (root / "retained.txt").read_text() == "keep existing data"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction rejection")
def test_windows_refuses_redirected_workspace_parent(tmp_path):
    import _winapi

    root = state.directory(tmp_path / "retained-folder")
    junction = tmp_path / "redirected-folder"
    # CPython's native helper creates the same directory reparse point without
    # making this security check depend on cold PowerShell startup on CI hosts.
    _winapi.CreateJunction(str(root), str(junction))
    try:
        with pytest.raises(state.LocalSetupError, match="redirected"):
            state.directory(junction / "nested")
        assert not (root / "nested").exists()
    finally:
        junction.rmdir()


@pytest.mark.skipif(os.name == "nt", reason="POSIX system temporary-directory symlink")
def test_native_database_probe_resolves_the_system_temporary_alias(tmp_path, monkeypatch):
    from deploy.probe_native_postgres import private_probe_directory

    actual = tmp_path / "system temporary directory"
    actual.mkdir(mode=0o700)
    alias = tmp_path / "system temporary alias"
    alias.symlink_to(actual, target_is_directory=True)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(alias))
    with private_probe_directory() as root:
        assert root.parent == actual
        assert root.is_dir()
        assert root.stat().st_mode & 0o077 == 0
    assert not root.exists()
