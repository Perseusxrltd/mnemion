"""Real OpenSSH/Git publication, pinned trust, deploy-key revocation and receipts."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import pytest

from mnemion import local_state
from mnemion.journal.config import Destination, SshAuthentication
from mnemion.journal.format import JournalError
from mnemion.journal.git import GitJournal
from mnemion.journal.ssh import credential_bytes
from service_tests.test_memory_journal import configure, entry, git, revision


@pytest.fixture
def ssh_root():
    # sshd StrictModes checks every ancestor of AuthorizedKeysFile. /tmp is
    # world-writable, so keep the disposable server under the current OS home.
    # No existing SSH configuration, key, or authorized_keys file is touched.
    with local_state.temporary_directory(prefix="mnemion-sshd-test-", dir=Path.home()) as root:
        yield root


@pytest.fixture
def ssh_repository(ssh_root):
    if os.name == "nt":
        pytest.skip("The isolated sshd fixture requires a POSIX host")
    import pwd

    executable = os.environ.get("MNEMION_TEST_SSHD") or shutil.which("sshd")
    if executable is None and Path("/usr/sbin/sshd").exists():
        executable = "/usr/sbin/sshd"
    if not executable:
        if os.environ.get("MNEMION_REQUIRE_SSH_TESTS") == "1":
            pytest.fail("The release checks require the real OpenSSH server fixture")
        pytest.skip("Install OpenSSH server or set MNEMION_TEST_SSHD")
    root = ssh_root
    host_key, identity, known_hosts = root / "host-key", root / "deploy-key", root / "known-hosts"
    for path in (host_key, identity):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)], check=True)
    authorized = root / "authorized-keys"
    authorized.write_bytes(identity.with_suffix(".pub").read_bytes())
    authorized.chmod(0o600)
    with socket.socket() as selected:
        selected.bind(("127.0.0.1", 0))
        port = selected.getsockname()[1]
    known_hosts.write_text(f"[127.0.0.1]:{port} " + host_key.with_suffix(".pub").read_text())
    known_hosts.chmod(0o600)
    user = pwd.getpwuid(os.getuid()).pw_name
    config = root / "sshd.conf"
    config.write_text(
        f'HostKey "{host_key}"\nPidFile "{root / "pid"}"\n'
        f'AuthorizedKeysFile "{authorized}"\nPort {port}\nListenAddress 127.0.0.1\n'
        f"AllowUsers {user}\nUsePAM no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n"
        "AllowAgentForwarding no\nAllowTcpForwarding no\nX11Forwarding no\nLogLevel VERBOSE\n"
    )
    env = dict(os.environ)
    if libraries := os.environ.get("MNEMION_TEST_SSHD_LIBRARY_PATH"):
        env["LD_LIBRARY_PATH"] = libraries
    with (root / "server.log").open("w+") as log:
        server = subprocess.Popen(
            [str(Path(executable).absolute()), "-D", "-e", "-f", str(config)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 5
            while True:
                if server.poll() is not None or time.monotonic() >= deadline:
                    log.seek(0)
                    pytest.fail("Disposable SSH server did not start: " + log.read()[-2000:])
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.02)
            first = entry(text="SSH repository keeps équipe memories and 東京 evidence.")
            original = configure(root, first)
            destination = Destination.model_validate(
                {
                    **original.model_dump(),
                    "local_repository": None,
                    "remote": f"ssh://{user}@127.0.0.1:{port}{original.local_repository}",
                    "state_directory": root / "Mémoire 'single' \"double\" % vault",
                    "ssh": {"identity_file": identity, "known_hosts_file": known_hosts},
                }
            )
            yield destination, original.local_repository, first, authorized
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def test_real_ssh_push_retry_and_readback_keep_private_keys_out_of_git(ssh_repository, monkeypatch):
    destination, repository, first, _ = ssh_repository
    monkeypatch.setenv("GIT_SSH_COMMAND", "unreviewed-command")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/unreviewed/agent")
    publisher = GitJournal(destination)
    report = publisher.publish([first])
    assert report["destination_kind"] == "ssh_repository"
    assert report["commit"] == git(repository, "rev-parse", "refs/heads/main").strip().decode()
    path = destination.prefix + "/" + first.relative_path
    assert git(repository, "show", "main:" + path) == first.line()
    assert publisher.publish([first])["commit"] == report["commit"]
    assert not list(publisher.control.glob("journal-ssh-*"))
    assert destination.ssh.identity_file.read_bytes() not in git(
        repository, "cat-file", "--batch-all-objects", "--batch"
    )
    assert "identity_file" not in json.dumps(report) and "known_hosts" not in json.dumps(report)


def test_unknown_host_pin_and_revoked_deploy_key_do_not_acknowledge_new_memories(ssh_repository):
    destination, repository, first, authorized = ssh_repository
    publisher = GitJournal(destination)
    report = publisher.publish([first])
    changed = revision(first, text="This revision must wait for restored repository access.")
    receipt = (publisher.spool.root / "publication.json").read_bytes()
    pins = destination.ssh.known_hosts_file.read_bytes()
    # A real, different public key must fail host verification before authentication.
    line = (
        pins.split(b" ", 1)[0]
        + b" "
        + destination.ssh.identity_file.with_suffix(".pub").read_bytes()
    )
    destination.ssh.known_hosts_file.write_bytes(line)
    with pytest.raises(JournalError, match="journal_ssh_connection_failed"):
        publisher.publish([changed])
    destination.ssh.known_hosts_file.write_bytes(pins)
    accepted = authorized.read_bytes()
    authorized.write_bytes(b"")
    with pytest.raises(JournalError, match="journal_ssh_connection_failed"):
        publisher.publish([changed])
    assert (publisher.spool.root / "publication.json").read_bytes() == receipt
    assert git(repository, "rev-parse", "refs/heads/main").strip().decode() == report["commit"]
    assert not list(publisher.control.glob("journal-ssh-*"))
    authorized.write_bytes(accepted)
    resumed = publisher.publish([changed])
    assert resumed["commit"] != report["commit"]
    assert publisher.publish([changed])["commit"] == resumed["commit"]


def test_real_ssh_concurrent_push_refetches_and_keeps_both_events(ssh_repository):
    destination, repository, first, _ = ssh_repository
    publisher = GitJournal(destination)
    publisher.publish([first])
    ours = revision(first, text="First writer's new revision.")
    theirs = entry(tenant_id=first.tenant_id, space_id=first.space_id)
    other = GitJournal(
        destination.model_copy(
            update={"state_directory": destination.state_directory.parent / "other-publisher"}
        )
    )
    raced = False

    def race():
        nonlocal raced
        if not raced:
            raced = True
            other.publish([theirs])

    result = publisher.publish([ours], before_push=race)
    assert result["attempts"] == 2
    for value in (ours, theirs):
        assert value.line() in git(
            repository, "show", "main:" + destination.prefix + "/" + value.relative_path
        )
    assert publisher.publish([ours])["commit"] == result["commit"]


def test_cli_enrollment_and_http_important_save_use_real_ssh_receipts(
    env, ssh_repository, capsys, monkeypatch
):
    from fastapi.testclient import TestClient
    from mnemion.journal.config import Configuration
    from mnemion.service.api import create_app
    from mnemion.service.cli import main
    from mnemion.service.writeback import WritebackService
    from service_tests.test_writeback import policy

    original, repository, _, authorized = ssh_repository
    destination = original.model_copy(
        update={"tenant_id": env.owner.tenant_id, "space_id": env.space}
    )
    registry = destination.state_directory.parent / "registry.json"
    assert (
        main(
            [
                "journal",
                "enroll",
                "--config",
                str(registry),
                "--id",
                destination.id,
                "--label",
                destination.label,
                "--tenant",
                str(env.owner.tenant_id),
                "--space",
                str(env.space),
                "--state",
                str(destination.state_directory),
                "--remote",
                destination.remote,
                "--ssh-key-file",
                str(destination.ssh.identity_file),
                "--ssh-known-hosts-file",
                str(destination.ssh.known_hosts_file),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert json.loads(output)["destinations"][0]["destination_kind"] == "ssh_repository"
    assert str(destination.ssh.identity_file) not in output
    registered = Configuration.from_file(registry)
    assert registered.destinations[0].fingerprint == destination.fingerprint
    monkeypatch.setattr(WritebackService, "start", lambda self: None)
    with TestClient(
        create_app(env.db, env.embedder, studio_enabled=False, writeback_configuration=registered)
    ) as client:
        headers = {"Authorization": "Bearer " + env.token}
        assert (
            client.put(
                f"/v1/spaces/{env.space}/writeback",
                headers=headers,
                json=policy(destination).model_dump(mode="json"),
            ).status_code
            == 200
        )
        content = "A synthetic important decision was received by the SSH repository."
        response = client.post(
            f"/v1/spaces/{env.space}/memories",
            headers={**headers, "Idempotency-Key": "ssh-important"},
            json={"content": content, "metadata": {"important": True}},
        )
        assert response.status_code == 202, response.text
        assert response.json()["writeback"]["destination_kind"] == "ssh_repository"
        assert response.json()["writeback"]["durability"] == "remote_git"
        assert response.json()["writeback"]["remote_pending"] is False
        status = client.get(f"/v1/spaces/{env.space}/writeback", headers=headers)
        assert (
            status.json()["last_commit"]
            == git(repository, "rev-parse", "refs/heads/main").strip().decode()
        )
        assert status.json()["pending_entries"] == 0
        for private_path in (
            destination.ssh.identity_file,
            destination.ssh.known_hosts_file,
            destination.state_directory,
        ):
            assert str(private_path) not in status.text
        # Revocation must leave the committed memory retryable without claiming
        # that its important Git delivery succeeded.
        authorized.write_bytes(b"")
        failed = client.post(
            f"/v1/spaces/{env.space}/memories",
            headers={**headers, "Idempotency-Key": "ssh-revoked"},
            json={
                "content": "A second decision waits for repository access.",
                "metadata": {"important": True},
            },
        )
        assert failed.status_code == 503
        assert (
            git(repository, "rev-parse", "refs/heads/main").strip().decode()
            == status.json()["last_commit"]
        )


def test_optional_ssh_fields_do_not_change_existing_destination_fingerprints(tmp_path):
    destination = configure(tmp_path, entry())
    for existing in (
        destination,
        destination.model_copy(
            update={"local_repository": None, "remote": "https://git.example.test/team/memory.git"}
        ),
    ):
        legacy = existing.model_dump(mode="json", exclude={"label", "ssh"})
        assert (
            existing.fingerprint
            == hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest()
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"ssh": None},
        {"remote": "ssh://git:secret@example.test/repo"},
        {"remote": "ssh://example.test/repo"},
        {"remote": "ssh://-oOption@example.test/repo"},
        {"remote": "ssh://git@-oProxyCommand/repo"},
        {"remote": "ssh://git@example.test/repo?password=secret"},
        {"remote": "git@example.test:repo"},
        {"remote": "ext::ssh example.test"},
        {"remote": "https://example.test/repo"},
        {"remote": "ssh://git@example.test/repo\n"},
        {"ssh": {"identity_file": "relative", "known_hosts_file": "/private/pins"}},
        {
            "ssh": {
                "identity_file": "/private/key",
                "known_hosts_file": "/private/pins",
                "command": "unreviewed",
            }
        },
    ],
)
def test_ssh_requires_explicit_safe_remote_and_operator_paths(tmp_path, patch):
    destination = configure(tmp_path, entry())
    with pytest.raises(ValueError):
        Destination.model_validate(
            {
                **destination.model_dump(),
                "local_repository": None,
                "remote": "ssh://git@example.test/repo",
                "ssh": {"identity_file": tmp_path / "key", "known_hosts_file": tmp_path / "pins"},
                **patch,
            }
        )


def test_ssh_private_inputs_refuse_links_broad_permissions_and_oversize(tmp_path):
    key, pins = tmp_path / "key", tmp_path / "pins"
    key.write_bytes(b"synthetic key")
    key.chmod(0o600)
    pins.write_bytes(b"synthetic host pins")
    pins.chmod(0o600)
    auth = SshAuthentication(identity_file=key, known_hosts_file=pins)
    if os.name != "nt":
        key.chmod(0o644)
        with pytest.raises(JournalError, match="journal_ssh_credentials_unavailable"):
            credential_bytes(auth)
        key.chmod(0o600)
        link = tmp_path / "key-link"
        link.symlink_to(key)
        with pytest.raises(JournalError, match="journal_ssh_credentials_unavailable"):
            credential_bytes(auth.model_copy(update={"identity_file": link}))
    key.write_bytes(b"x" * (128 * 1024 + 1))
    with pytest.raises(JournalError, match="journal_ssh_credentials_unavailable"):
        credential_bytes(auth)
