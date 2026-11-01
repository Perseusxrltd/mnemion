"""Remote Git cache readiness before host restore claims completion.

Fixtures stay in pytest's temporary directory. No network, credentials, or
user repositories are used. Git commands that build a fixture repository are
local and do not fetch.
"""

from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from mnemion.connectors import providers as provider_module
from mnemion.connectors.config import GitConfig
from mnemion.connectors.providers import GitProvider
from mnemion.service import host_recovery
from mnemion.service.host_package import HostRecoveryError

REMOTE = "https://example.invalid/office.git"
OTHER = "https://example.invalid/other.git"


def connector(path, remote=REMOTE, **provider):
    return {
        "id": "c2cfd152-0a34-4495-af28-83f272c51c96",
        "config": {
            "version": 1,
            "service_url": "http://127.0.0.1:7891",
            "service_token": {"file": "@dedicated-token"},
            "connector_id": "c2cfd152-0a34-4495-af28-83f272c51c96",
            "provider": {
                "type": "git",
                "path": str(path),
                "remote": remote,
                "ref": "main",
                "scope_id": "office",
                "name": "Office",
                "members": ["staff:office"],
                "publish_to_mapped_members": True,
                **provider,
            },
        },
    }


def require(connectors, mappings, root, assets=(), ledger=None):
    before = json.dumps(connectors)
    deferred = host_recovery.require_remote_git_caches(
        connectors, list(assets), mappings, root, ledger
    )
    assert json.dumps(connectors) == before
    return deferred


@pytest.fixture
def isolated_git(monkeypatch, tmp_path):
    if shutil.which("git") is None:
        pytest.skip("Install Git to exercise native Git cache inspection")
    # The runner keeps HOME and drops GIT_CONFIG_GLOBAL / GIT_CONFIG_NOSYSTEM.
    # Git then reads $HOME/.gitconfig and $HOME/.config/git/config, so a private
    # home is what isolates inspection from the operator's global configuration.
    home = tmp_path / "git-home"
    (home / ".config" / "git").mkdir(parents=True)
    (home / ".gitconfig").write_text("")
    (home / ".config" / "git" / "config").write_text("")
    monkeypatch.setenv("HOME", str(home))
    for name in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_NOSYSTEM",
        "XDG_CONFIG_HOME",
    ):
        monkeypatch.delenv(name, raising=False)
    real = provider_module.command

    def guarded(args, **kwargs):
        assert "fetch" not in args and "clone" not in args and "ls-remote" not in args
        assert "core.hooksPath=" + os.devnull in args
        assert "protocol.file.allow=never" in args
        environment = kwargs.get("environment") or {}
        assert environment.get("HOME") == str(home)
        assert "GIT_CONFIG_GLOBAL" not in environment
        assert "GIT_CONFIG_NOSYSTEM" not in environment
        assert environment.get("GIT_TERMINAL_PROMPT") == "0"
        assert environment.get("GIT_OPTIONAL_LOCKS") == "0"
        return real(args, **kwargs)

    monkeypatch.setattr(provider_module, "command", guarded)


def git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True, timeout=30)


def bare_cache(tmp_path, origin, name="cache.git"):
    template = tmp_path / "empty-template"
    template.mkdir(exist_ok=True)
    cache = tmp_path / name
    git("init", "--bare", "--template", str(template), str(cache))
    git(
        "-c",
        "core.hooksPath=" + os.devnull,
        "-C",
        str(cache),
        "remote",
        "add",
        "origin",
        origin,
    )
    return cache


def test_inaccessible_unmapped_ancestor_fails_before_restore_claims_success(tmp_path, monkeypatch):
    blocked = tmp_path / "previous-machine" / "mnemion-office"
    blocked.parent.mkdir()
    blocked.mkdir()
    cache = blocked / "connectors" / "office-git.git"
    real_lstat = os.lstat

    def denied(value, *args, **kwargs):
        if Path(value) == cache or blocked in Path(value).parents:
            error = PermissionError(errno.EACCES, "Permission denied")
            error.errno = errno.EACCES
            raise error
        return real_lstat(value, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", denied)
    mutated = []

    def refuse_directory(path):
        mutated.append(path)
        raise AssertionError("destination mutated")

    def refuse_backup(*_args, **_kwargs):
        mutated.append("backup")
        raise AssertionError("database mutated")

    monkeypatch.setattr(host_recovery.supervision, "_unix", lambda: None)
    monkeypatch.setattr(host_recovery.update_state, "directory", refuse_directory)
    monkeypatch.setattr(host_recovery.recovery, "restore_backup", refuse_backup)
    monkeypatch.setattr(
        host_recovery.recovery,
        "read_ledger",
        lambda _path: {
            "snapshot_at": "2026-10-31T18:09:57+00:00",
            "tenant_ids": ["11111111-1111-1111-1111-111111111111"],
        },
    )
    monkeypatch.setattr(
        host_recovery,
        "public_plan",
        lambda _value: {
            "snapshot_at": "2026-10-31T18:09:57+00:00",
            "tenant_ids": ["11111111-1111-1111-1111-111111111111"],
        },
    )
    saved = {
        "plan": {},
        "host": "127.0.0.1",
        "port": 7891,
        "public_url": None,
        "assets": [],
        "connectors": [connector(cache)],
    }

    @contextmanager
    def opened(*_args, **_kwargs):
        yield saved, tmp_path, "ab" * 32

    monkeypatch.setattr(host_recovery, "opened", opened)
    destination = tmp_path / "restored-host"
    with pytest.raises(HostRecoveryError) as caught:
        host_recovery.restore(
            tmp_path / "package.mnemion-host",
            tmp_path / "recovery.key",
            destination,
            operator_dsn="dbname=postgres",
            database_name="cache_preflight",
            expected_sha256="ab" * 32,
            managed=False,
        )
    assert str(caught.value) == "provider.path: git_cache_ancestor_inaccessible"
    assert str(cache) not in str(caught.value)
    assert REMOTE not in str(caught.value)
    assert mutated == []
    assert not destination.exists()
    assert not cache.exists()


@pytest.mark.skipif(
    os.name != "posix" or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="needs an unprivileged POSIX directory the owner cannot search",
)
def test_posix_unsearchable_ancestor_is_inaccessible_without_chmod_of_shared_data(tmp_path):
    blocked = tmp_path / "mnemion-office"
    blocked.mkdir()
    cache = blocked / "connectors" / "office-git.git"
    blocked.chmod(0)
    try:
        with pytest.raises(HostRecoveryError) as caught:
            require([connector(cache)], [], tmp_path / "dest")
    finally:
        blocked.chmod(0o700)
    assert str(caught.value) == "provider.path: git_cache_ancestor_inaccessible"
    assert str(cache) not in str(caught.value)
    assert not cache.exists()


def test_valid_mapped_absent_cache_passes_without_network_or_leaf(tmp_path, monkeypatch):
    def forbid_git(*_args, **_kwargs):
        raise AssertionError("absent cache must not run git")

    monkeypatch.setattr(provider_module, "command", forbid_git)
    old = tmp_path / "old-host" / "connectors"
    new = tmp_path / "connector-caches"
    new.mkdir()
    leaf = new / "office-git.git"
    notes = tmp_path / "missing-notes"
    local_git = tmp_path / "local-only"
    connectors = [
        connector(old / "office-git.git"),
        {
            "id": "5ded2f77-b85b-4ad9-b455-0485132d10d3",
            "config": {"provider": {"type": "filesystem", "path": str(notes)}},
        },
        connector(local_git, remote=None),
    ]
    require(connectors, [(str(old), str(new))], tmp_path / "dest")
    assert not leaf.exists()
    assert not notes.exists()
    assert not local_git.exists()
    assert not (tmp_path / "dest").exists()


def test_existing_mismatched_origin_fails(isolated_git, tmp_path):
    cache = bare_cache(tmp_path, OTHER)
    config_bytes = (cache / "config").read_bytes()
    with pytest.raises(HostRecoveryError) as caught:
        require([connector(cache, remote=REMOTE)], [], tmp_path / "dest")
    assert str(caught.value) == "provider.path: git_cache_remote_mismatch"
    assert REMOTE not in str(caught.value) and OTHER not in str(caught.value)
    assert str(cache) not in str(caught.value)
    assert (cache / "config").read_bytes() == config_bytes
    assert not (cache / "FETCH_HEAD").exists()


def test_existing_matching_bare_cache_remains_acceptable(isolated_git, tmp_path):
    cache = bare_cache(tmp_path, REMOTE)
    config_bytes = (cache / "config").read_bytes()
    require([connector(cache)], [], tmp_path / "dest")
    assert (cache / "config").read_bytes() == config_bytes
    assert not (cache / "FETCH_HEAD").exists()
    assert not (tmp_path / "dest").exists()


def work_tree(tmp_path, origin):
    template = tmp_path / "empty-template"
    template.mkdir(exist_ok=True)
    work = tmp_path / "work"
    git("init", "--template", str(template), str(work))
    git(
        "-c",
        "core.hooksPath=" + os.devnull,
        "-C",
        str(work),
        "remote",
        "add",
        "origin",
        origin,
    )
    return work


def test_existing_matching_work_tree_remains_acceptable(isolated_git, tmp_path):
    work = work_tree(tmp_path, REMOTE)
    config_bytes = (work / ".git" / "config").read_bytes()
    require([connector(work)], [], tmp_path / "dest")
    assert (work / ".git" / "config").read_bytes() == config_bytes
    assert not (work / "FETCH_HEAD").exists()
    assert not (work / ".git" / "FETCH_HEAD").exists()
    assert not (tmp_path / "dest").exists()


def test_rejected_remote_does_not_publish_a_secret(tmp_path):
    cache = tmp_path / "connector-caches" / "office-git.git"
    cache.parent.mkdir()
    secret = "https://user:super-secret-token@example.invalid/office.git"
    with pytest.raises(HostRecoveryError) as caught:
        require([connector(cache, remote=secret)], [], tmp_path / "dest")
    assert str(caught.value) == "provider.path: git_cache_mapping_invalid"
    assert "super-secret-token" not in str(caught.value)
    assert not cache.exists()


class _PreflightReached(RuntimeError):
    """Stops restore at the first mutation after a successful cache check."""


ACTIVE = "5ded2f77-b85b-4ad9-b455-0485132d10d3"
REVOKED = "c2cfd152-0a34-4495-af28-83f272c51c96"
TENANT = "11111111-1111-1111-1111-111111111111"


def identified(entry, identifier):
    entry = json.loads(json.dumps(entry))
    entry["id"] = identifier
    entry["config"]["connector_id"] = identifier
    return entry


def ledger_connections(*rows):
    return {"connector_state": {"version": 3, "connections": list(rows)}}


def connection(identifier, disabled_at):
    return {"tenant_id": TENANT, "id": identifier, "disabled_at": disabled_at}


@pytest.mark.skipif(
    os.name != "posix" or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="needs an unprivileged POSIX account; mode bits are not Windows ACLs",
)
def test_unwritable_git_metadata_is_not_reusable(isolated_git, tmp_path):
    cache = bare_cache(tmp_path, REMOTE)
    config_bytes = (cache / "config").read_bytes()
    cache.chmod(0o555)
    try:
        with pytest.raises(HostRecoveryError) as caught:
            require([connector(cache)], [], tmp_path / "dest")
    finally:
        cache.chmod(0o700)
    assert str(caught.value) == "provider.path: git_cache_inaccessible"
    assert str(cache) not in str(caught.value)
    assert REMOTE not in str(caught.value)
    assert (cache / "config").read_bytes() == config_bytes
    assert not (cache / "FETCH_HEAD").exists()
    assert not (cache / "FETCH_HEAD.lock").exists()


@pytest.mark.skipif(
    os.name != "posix" or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="needs an unprivileged POSIX account; mode bits are not Windows ACLs",
)
def test_unwritable_fetch_head_is_not_reusable(isolated_git, tmp_path):
    cache = bare_cache(tmp_path, REMOTE)
    fetch_head = cache / "FETCH_HEAD"
    fetch_head.write_text("0123456789abcdef0123456789abcdef01234567\n")
    fetch_head.chmod(0o444)
    try:
        with pytest.raises(HostRecoveryError) as caught:
            require([connector(cache)], [], tmp_path / "dest")
    finally:
        fetch_head.chmod(0o644)
    assert str(caught.value) == "provider.path: git_cache_inaccessible"
    assert str(cache) not in str(caught.value)
    assert fetch_head.read_text() == "0123456789abcdef0123456789abcdef01234567\n"
    assert not (cache / "FETCH_HEAD.lock").exists()


@pytest.mark.skipif(
    os.name != "posix" or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="needs an unprivileged POSIX account; mode bits are not Windows ACLs",
)
def test_readonly_work_tree_documents_remain_acceptable(isolated_git, tmp_path):
    work = work_tree(tmp_path, REMOTE)
    notes = work / "notes.txt"
    notes.write_text("keep")
    notes.chmod(0o444)
    work.chmod(0o555)
    try:
        require([connector(work)], [], tmp_path / "dest")
    finally:
        work.chmod(0o700)
        notes.chmod(0o644)
    assert notes.read_text() == "keep"
    assert not (work / ".git" / "FETCH_HEAD").exists()
    assert not (tmp_path / "dest").exists()


def test_ambient_git_overrides_do_not_redirect_inspection(isolated_git, tmp_path, monkeypatch):
    cache = bare_cache(tmp_path, REMOTE)
    other = bare_cache(tmp_path, OTHER, "other.git")
    monkeypatch.setenv("GIT_DIR", str(other))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "remote.origin.url")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", OTHER)
    current = provider_module.command

    def capturing(args, **kwargs):
        environment = kwargs.get("environment") or {}
        for name in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_PARAMETERS",
        ):
            assert name not in environment
        assert environment.get("GIT_TERMINAL_PROMPT") == "0"
        assert environment.get("GIT_OPTIONAL_LOCKS") == "0"
        return current(args, **kwargs)

    monkeypatch.setattr(provider_module, "command", capturing)
    config_bytes = (cache / "config").read_bytes()
    other_bytes = (other / "config").read_bytes()
    require([connector(cache)], [], tmp_path / "dest")
    assert (cache / "config").read_bytes() == config_bytes
    assert (other / "config").read_bytes() == other_bytes
    assert not (cache / "FETCH_HEAD").exists()


def test_invalid_origin_bytes_stay_a_fixed_class(tmp_path, monkeypatch):
    cache = tmp_path / "cache.git"
    cache.mkdir()

    def fake(args, **_kwargs):
        if "rev-parse" in args:
            return f"{cache}\n{cache}\n{cache / 'FETCH_HEAD'}\n".encode()
        if "get-url" in args:
            return b"\xff\xfe"
        raise AssertionError(args)

    monkeypatch.setattr(provider_module, "command", fake)
    with pytest.raises(HostRecoveryError) as caught:
        require([connector(cache)], [], tmp_path / "dest")
    assert str(caught.value) == "provider.path: git_cache_invalid"
    assert caught.value.__cause__ is None
    assert str(cache) not in str(caught.value)
    assert not (cache / "FETCH_HEAD").exists()


@pytest.mark.parametrize(
    ("number", "code"),
    (
        (errno.ELOOP, "git_cache_ancestor_invalid"),
        (errno.EACCES, "git_cache_ancestor_inaccessible"),
    ),
)
def test_asset_parent_resolution_failure_stays_a_fixed_class(tmp_path, monkeypatch, number, code):
    original = Path.resolve

    def guarded(self, *args, **kwargs):
        if self.name == "assets":
            raise OSError(number, "resolution failed", str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded)
    with pytest.raises(HostRecoveryError) as caught:
        require([connector(tmp_path / "cache.git")], [], tmp_path / "dest")
    assert str(caught.value) == "provider.path: " + code
    assert str(tmp_path) not in str(caught.value)
    assert caught.value.__cause__ is None


def test_disabled_ledger_connector_is_omitted_without_authority_change(tmp_path, monkeypatch):
    def forbid_git(*_args, **_kwargs):
        raise AssertionError("omitted and absent caches must not run git")

    monkeypatch.setattr(provider_module, "command", forbid_git)
    secret = "https://user:super-secret-token@example.invalid/office.git"
    revoked = connector(tmp_path / "blocked" / "old.git", remote=secret)
    active = identified(connector(tmp_path / "old-host" / "connectors" / "office-git.git"), ACTIVE)
    mapped = tmp_path / "connector-caches"
    mapped.mkdir()
    saved = ledger_connections(
        connection(REVOKED, "2026-10-31T18:09:57+00:00"),
        connection(ACTIVE, None),
    )
    before = json.dumps(saved)
    require(
        [revoked, active],
        [(str(tmp_path / "old-host" / "connectors"), str(mapped))],
        tmp_path / "dest",
        ledger=saved,
    )
    assert json.dumps(saved) == before
    assert saved["connector_state"]["connections"][0]["disabled_at"] == "2026-10-31T18:09:57+00:00"
    assert secret not in json.dumps(saved)
    assert not (tmp_path / "blocked").exists()
    assert not (mapped / "office-git.git").exists()
    assert not (tmp_path / "dest").exists()


def test_disabled_connector_does_not_hide_an_active_cache_mismatch(isolated_git, tmp_path):
    cache = bare_cache(tmp_path, OTHER)
    secret = "https://user:super-secret-token@example.invalid/office.git"
    revoked = connector(tmp_path / "blocked" / "old.git", remote=secret)
    active = identified(connector(cache, remote=REMOTE), ACTIVE)
    saved = ledger_connections(
        connection(REVOKED, "2026-10-31T18:09:57+00:00"),
        connection(ACTIVE, None),
    )
    before = json.dumps(saved)
    config_bytes = (cache / "config").read_bytes()
    deferred = require([revoked, active], [], tmp_path / "dest", ledger=saved)
    assert deferred == {ACTIVE: "git_cache_remote_mismatch"}
    assert "super-secret-token" not in json.dumps(deferred)
    assert str(cache) not in json.dumps(deferred)
    assert json.dumps(saved) == before
    assert (cache / "config").read_bytes() == config_bytes
    assert not (tmp_path / "blocked").exists()


def test_absent_ledger_connection_does_not_keep_an_enabled_cache_failure(isolated_git, tmp_path):
    absent_cache = bare_cache(tmp_path, OTHER, "absent.git")
    enabled_cache = bare_cache(tmp_path, OTHER, "enabled.git")
    absent = identified(connector(absent_cache, remote=REMOTE), REVOKED)
    enabled = identified(connector(enabled_cache, remote=REMOTE), ACTIVE)
    saved = ledger_connections(connection(ACTIVE, None))
    absent_bytes = (absent_cache / "config").read_bytes()
    enabled_bytes = (enabled_cache / "config").read_bytes()
    deferred = require([absent, enabled], [], tmp_path / "dest", ledger=saved)
    assert deferred == {ACTIVE: "git_cache_remote_mismatch"}
    assert REVOKED not in deferred
    assert (absent_cache / "config").read_bytes() == absent_bytes
    assert (enabled_cache / "config").read_bytes() == enabled_bytes
    assert not (tmp_path / "dest").exists()


def test_matching_cache_preflight_reaches_restore_before_mutation(
    isolated_git, tmp_path, monkeypatch
):
    cache = bare_cache(tmp_path, REMOTE)
    config_bytes = (cache / "config").read_bytes()
    mutated = []

    def directory(path):
        mutated.append(path)
        raise _PreflightReached

    def refuse_backup(*_args, **_kwargs):
        mutated.append("backup")
        raise AssertionError("database mutated")

    monkeypatch.setattr(host_recovery.supervision, "_unix", lambda: None)
    monkeypatch.setattr(host_recovery.update_state, "directory", directory)
    monkeypatch.setattr(host_recovery.recovery, "restore_backup", refuse_backup)
    monkeypatch.setattr(
        host_recovery.recovery,
        "read_ledger",
        lambda _path: {"snapshot_at": "2026-10-31T18:09:57+00:00", "tenant_ids": [TENANT]},
    )
    monkeypatch.setattr(
        host_recovery,
        "public_plan",
        lambda _value: {"snapshot_at": "2026-10-31T18:09:57+00:00", "tenant_ids": [TENANT]},
    )
    saved = {
        "plan": {},
        "host": "127.0.0.1",
        "port": 7891,
        "public_url": None,
        "assets": [],
        "connectors": [connector(cache)],
    }

    @contextmanager
    def opened(*_args, **_kwargs):
        yield saved, tmp_path, "ab" * 32

    monkeypatch.setattr(host_recovery, "opened", opened)
    destination = tmp_path / "restored-host"
    with pytest.raises(_PreflightReached):
        host_recovery.restore(
            tmp_path / "package.mnemion-host",
            tmp_path / "recovery.key",
            destination,
            operator_dsn="dbname=postgres",
            database_name="cache_preflight",
            expected_sha256="ab" * 32,
            managed=False,
        )
    assert [Path(path) for path in mutated] == [destination.expanduser().absolute()]
    assert (cache / "config").read_bytes() == config_bytes
    assert not (cache / "FETCH_HEAD").exists()
    assert not destination.exists()


def test_remote_ref_fetch_sequence_stays_on_the_runner_environment(tmp_path, monkeypatch):
    ambient = str(tmp_path / "ambient-git-dir")
    monkeypatch.setenv("GIT_DIR", ambient)
    calls = []

    def fake(args, **kwargs):
        calls.append((args, kwargs.get("environment") or {}))
        if "get-url" in args:
            return (REMOTE + "\n").encode()
        if "fetch" in args:
            return b""
        if "rev-parse" in args:
            return b"0123456789abcdef0123456789abcdef01234567\n"
        raise AssertionError(args)

    monkeypatch.setattr(provider_module, "command", fake)
    work = tmp_path / "cache"
    work.mkdir()
    provider = GitProvider(
        GitConfig(
            path=work,
            remote=REMOTE,
            ref="main",
            scope_id="office",
            name="Office",
            members=["staff:office"],
            publish_to_mapped_members=True,
        )
    )
    assert provider.scopes() == ["git:office"]
    kinds = []
    for args, environment in calls:
        assert environment.get("GIT_DIR") == ambient
        if "get-url" in args:
            kinds.append("origin")
        elif "fetch" in args:
            kinds.append("fetch")
            assert args[args.index("fetch") :] == [
                "fetch",
                "--prune",
                "--no-tags",
                "origin",
                "main",
            ]
        elif "rev-parse" in args:
            kinds.append("rev-parse")
            assert args[-1] == "FETCH_HEAD^{commit}"
    assert kinds == ["origin", "fetch", "rev-parse"]
    assert provider.commit == "0123456789abcdef0123456789abcdef01234567"
