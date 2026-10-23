"""Explicit OS-owner adoption, separate from memory API credentials."""

import hashlib
import ipaddress
import json
from pathlib import Path
import plistlib
import shlex
from urllib.parse import urlsplit
from uuid import uuid4

import asyncssh

from .. import local_state
from ..private_output import private_output
from ..service import runtime_pins, service_updates as updates, supervision
from ..service import update_state as state_io
from . import HostControlError
from .locking import operator_lock
from .protocol import Operator, canonical, fingerprint
from .store import STORE_FORMAT, Store
from .transport import Connection

CAPABILITIES = {"host_control_protocol": 1, "store_format": STORE_FORMAT}


def compatible_runtime(service, runtime):
    """Execute only a verified runtime, with no inherited service credentials."""
    runtime = updates.resolved_runtime(service, runtime=runtime)
    output = updates._command(
        [
            runtime["python"],
            *(["-I"] if runtime["isolated"] else []),
            "-m",
            "mnemion.host_control.cli",
            "capabilities",
        ],
        cwd=Path(runtime["directory"]),
        environment=updates._environment(),
        log=service / "updates/logs/host-control-probe.log",
        timeout=15,
    )
    if canonical(json.loads(output)) != canonical(CAPABILITIES):
        raise HostControlError(
            "unsupported_runtime", "This runtime cannot maintain the adopted host controller."
        )
    return runtime


def render(root, value):
    """A private Supervisor with one restricted listener, no memory processes."""
    escape = supervision._value
    runtime = Path(value["runtime"])
    command = shlex.join([value["python"], str(root / "launcher.py"), str(root)])
    return f"""[unix_http_server]
file={escape(str(runtime / "control.sock"))}
chmod=0600

[supervisord]
identifier={value["identifier"]}
logfile={escape(str(root / "logs/supervisord.log"))}
logfile_maxbytes=2MB
logfile_backups=2
pidfile={escape(str(runtime / "supervisord.pid"))}
childlogdir={escape(str(root / "logs"))}
umask=077
minfds=128
minprocs=32

[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface

[program:mnemion-host-control]
command={escape(command)}
directory={escape(value["directory"])}
autostart=true
autorestart=true
startsecs=2
startretries=5
stopsignal=TERM
stopwaitsecs=10
stopasgroup=true
killasgroup=true
redirect_stderr=true
stdout_logfile={escape(str(root / "logs/control.log"), expansions=2)}
stdout_logfile_maxbytes=2MB
stdout_logfile_backups=2
environment=PYTHONUNBUFFERED="1"
"""


def settings(root: Path):
    supervision._unix()
    root = Path(root).expanduser().absolute()
    local_state._regular(root, directory=True)
    root = root.resolve()
    value = state_io.read(root / "settings.json")
    service, existing = supervision.settings(Path(value["service_state"]))
    identifier, runtime = supervision._runtime(root)
    if (
        value.get("format") != 1
        or value.get("identifier") != identifier
        or value.get("runtime") != str(runtime)
        or value.get("service_identity") != existing["identifier"]
        or not existing.get("managed_updates")
        or value.get("python") != existing["python"]
        or value.get("directory") != existing["directory"]
        or service == root
        or root.is_relative_to(service)
        or service.is_relative_to(root)
    ):
        raise HostControlError("host_identity_changed", "Inspect the adopted host configuration.")
    for name in ("launcher.py", "supervisord.conf", "launchd.plist", "memory-launchd.plist"):
        supervision._private(root / name)
        content = supervision._bytes(root / name, 65536)
        if hashlib.sha256(content).hexdigest() != value.get("hashes", {}).get(name):
            raise HostControlError(
                "host_configuration_changed", "Review the changed host startup configuration."
            )
    supervision._private(root / "host.key")
    key = asyncssh.import_private_key(supervision._bytes(root / "host.key", 16384))
    connection = Connection.model_validate(value["connection"])
    record = Store(root / "authority").host_record()
    if (
        key.get_algorithm() != "ssh-ed25519"
        or key.get_fingerprint("sha256") != connection.host_key_fingerprint
        or str(connection.host_id) != record["id"]
        or record["id"] != value["host_id"]
        or record["service_state"] != str(service)
        or record["service_identity"] != existing["identifier"]
        or type(value.get("port")) is not int
        or connection.port != value["port"]
        or not 1024 <= value["port"] <= 65535
    ):
        raise HostControlError("host_identity_changed", "Inspect the adopted host identity.")
    ipaddress.ip_address(value["bind"])
    return root, value


def _pins(root, value, runtime):
    path = Path(value["service_state"]) / "updates"
    pins = runtime_pins.read(path)
    if pins is not None:
        if pins["host_id"] != value["host_id"] or pins["state"] != str(root):
            raise HostControlError(
                "host_already_adopted", "This service already has an independent controller."
            )
        return
    state_io.write(
        path / runtime_pins.FILE,
        {
            "format": 1,
            "host_id": value["host_id"],
            "state": str(root),
            "current": runtime,
            "previous": None,
            "pending": False,
            "attempts": 0,
            "revision": str(uuid4()),
            "fallback": False,
            "rejected_slot": None,
        },
        replace=False,
    )


def adopt(
    root: Path,
    service: Path,
    operator: Operator,
    *,
    bind="127.0.0.1",
    port=7893,
    advertised_host=None,
    approve_network=False,
):
    """Prepare only. Explicit service start/boot registration remain observable."""
    supervision._unix()
    address = ipaddress.ip_address(bind)
    if type(port) is not int or not 1024 <= port <= 65535:
        raise HostControlError("invalid_port", "Use a host-control port between 1024 and 65535.")
    if not address.is_loopback and approve_network is not True:
        raise HostControlError(
            "network_approval_required", "Explicitly approve this host's network listener."
        )
    service, existing = supervision.settings(service)
    if not existing.get("managed_updates"):
        raise HostControlError("unmanaged_host", "Adopt managed updates before host control.")
    root = Path(root).expanduser().absolute()
    if root.is_symlink():
        raise HostControlError("invalid_state", "Use a separate private host-control directory.")
    root = root.resolve()
    if root == service or root.is_relative_to(service) or service.is_relative_to(root):
        raise HostControlError("invalid_state", "Keep host control outside the service directory.")
    hostname = advertised_host or urlsplit(existing.get("public_url") or "").hostname
    if hostname is None and address.is_unspecified:
        raise HostControlError("invalid_address", "Supply the address other operators can reach.")
    hostname = hostname or address.compressed
    with operator_lock(service / "updates"):
        prior = runtime_pins.read(service / "updates")
        if prior is not None and prior["state"] != str(root):
            raise HostControlError(
                "host_already_adopted", "This service already has an independent controller."
            )
        if (root / "settings.json").exists():
            root, value = settings(root)
            store = Store(root / "authority")
            actor = store.authenticate(operator.public_key)
            authority = store.authority(actor, value["host_id"])
            connection = Connection.model_validate(value["connection"])
            if (
                value["service_state"] != str(service)
                or value["bind"] != address.compressed
                or value["port"] != port
                or connection.hostname != Connection.address(hostname)
                or str(connection.operator_id) != actor
                or authority["operator"]["role"] != "custodian"
            ):
                raise HostControlError(
                    "adoption_changed", "Existing adoption differs; inspect it before changing it."
                )
            if prior is None:
                _pins(root, value, compatible_runtime(service, updates.resolved_runtime(service)))
            return {"prepared": True, "already_prepared": True, "connection": value["connection"]}
        runtime = compatible_runtime(service, updates.resolved_runtime(service))
        observed = supervision.status(service)
        with state_io.adoption(root):
            _, identity = Store.adopt(
                root / "authority",
                service,
                existing["identifier"],
                operator,
                service_running=observed["running"],
            )
            host_key = asyncssh.generate_private_key("ssh-ed25519")
            connection = Connection(
                host_id=identity["host_id"],
                operator_id=identity["operator_id"],
                hostname=hostname,
                port=port,
                host_key_fingerprint=host_key.get_fingerprint("sha256"),
                operator_key_fingerprint=fingerprint(operator.public_key),
            )
            identifier, socket_root = supervision._runtime(root)
            for child in ("logs", "worker", "runtime-control"):
                state_io.directory(root / child)
            value = {
                "format": 1,
                "host_id": identity["host_id"],
                "identifier": identifier,
                "service_state": str(service),
                "service_identity": existing["identifier"],
                "python": existing["python"],
                "directory": existing["directory"],
                "runtime": str(socket_root),
                "bind": address.compressed,
                "port": port,
                "connection": connection.model_dump(mode="json"),
            }
            contents = {
                "launcher.py": Path(__file__).with_name("launcher.py").read_bytes(),
                "supervisord.conf": render(root, value).encode(),
                "launchd.plist": plistlib.dumps(
                    {
                        "Label": "com.mnemion.host-control." + identifier,
                        "ProgramArguments": [
                            value["python"],
                            "-m",
                            "supervisor.supervisord",
                            "--nodaemon",
                            "-c",
                            str(root / "supervisord.conf"),
                        ],
                        "WorkingDirectory": value["directory"],
                        "RunAtLoad": True,
                        "KeepAlive": {"SuccessfulExit": False},
                        "ThrottleInterval": 30,
                        "ExitTimeOut": 15,
                        "StandardOutPath": "/dev/null",
                        "StandardErrorPath": "/dev/null",
                    }
                ),
                "memory-launchd.plist": plistlib.dumps(
                    {
                        "Label": "com.mnemion.host-memory." + identifier,
                        "ProgramArguments": [
                            value["python"],
                            str(root / "launcher.py"),
                            str(root),
                            "memory",
                        ],
                        "WorkingDirectory": value["directory"],
                        "RunAtLoad": True,
                        "KeepAlive": {"SuccessfulExit": False},
                        "ThrottleInterval": 30,
                        "ExitTimeOut": 90,
                        "StandardOutPath": "/dev/null",
                        "StandardErrorPath": "/dev/null",
                    }
                ),
            }
            value["hashes"] = {
                name: hashlib.sha256(data).hexdigest() for name, data in contents.items()
            }
            for name, data in {**contents, "host.key": host_key.export_private_key()}.items():
                with private_output(root / name) as stream:
                    stream.write(data)
            state_io.write(root / "settings.json", value, replace=False)
        # Commit the independent root first. A lost pin write is completed by
        # the idempotent adoption above, without rekeying or replacing grants.
        _pins(root, value, runtime)
        return {"prepared": True, "already_prepared": False, "connection": value["connection"]}
