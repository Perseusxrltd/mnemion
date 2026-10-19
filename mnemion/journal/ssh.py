"""Pinned, noninteractive SSH with disposable owner-only credential snapshots."""

from contextlib import contextmanager
import os
import shlex
from urllib.parse import urlsplit

from .. import local_state
from ..private_input import read_private
from ..private_output import private_output
from .format import JournalError


def credential_bytes(authentication):
    """Validate existing files without repairing their ownership or permissions."""
    try:
        key = read_private(authentication.identity_file, maximum=128 * 1024)
        hosts = read_private(authentication.known_hosts_file, maximum=64 * 1024)
        if not key.strip() or not hosts.strip() or b"\0" in key or b"\0" in hosts:
            raise ValueError
        key.decode("ascii")
        hosts.decode("utf-8")
    except (OSError, ValueError):
        raise JournalError("journal_ssh_credentials_unavailable") from None
    return key, hosts


@contextmanager
def transport(destination, parent, environment):
    """Never consult user SSH config, agents, prompts, or global Git rewrites.

    Files are read through checked handles, then copied to a private staging
    directory. SSH consumes these snapshots rather than reopening mutable input
    paths. Key material never enters arguments, Git objects or public receipts.
    """
    key, hosts = credential_bytes(destination.ssh)
    with local_state.temporary_directory(prefix="journal-ssh-", dir=parent) as root:
        identity, known_hosts = root / "identity", root / "known_hosts"
        for path, content in ((identity, key), (known_hosts, hosts)):
            with private_output(path) as stream:
                stream.write(content)
        # OpenSSH accepts forward slashes on Windows; Git's command string is
        # interpreted by its POSIX shell on all supported platforms.
        identity_path = identity.as_posix().replace("%", "%%").replace('"', '\\"')
        hosts_path = known_hosts.as_posix().replace("%", "%%").replace('"', '\\"')
        command = [
            "ssh",
            "-F",
            "none",
            "-o",
            'IdentityFile="' + identity_path + '"',
            "-o",
            'UserKnownHostsFile="' + hosts_path + '"',
            "-o",
            "GlobalKnownHostsFile=none",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UpdateHostKeys=no",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "IdentityAgent=none",
            "-o",
            "AddKeysToAgent=no",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            "KbdInteractiveAuthentication=no",
            "-o",
            "PreferredAuthentications=publickey",
            "-o",
            "NumberOfPasswordPrompts=0",
            "-o",
            "ForwardAgent=no",
            "-o",
            "ClearAllForwardings=yes",
            "-o",
            "PermitLocalCommand=no",
            "-o",
            "RequestTTY=no",
            "-o",
            "ControlMaster=no",
            "-o",
            "ControlPath=none",
            "-o",
            "ConnectionAttempts=1",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ServerAliveInterval=10",
            "-o",
            "ServerAliveCountMax=2",
            "-o",
            "LogLevel=ERROR",
        ]
        # Bind host-key lookup to the literal enrolled address. A per-user DNS
        # alias or system-wide SSH configuration cannot replace this pin.
        remote = urlsplit(destination.remote)
        host = remote.hostname
        if remote.port is not None and remote.port != 22:
            host = f"[{host}]:{remote.port}"
        command += ["-o", "HostKeyAlias=" + host]
        yield {
            **environment,
            "GIT_SSH_COMMAND": shlex.join(command),
            "GIT_SSH_VARIANT": "ssh",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "SSH_ASKPASS_REQUIRE": "never",
        }
