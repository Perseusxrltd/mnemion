"""Private, user-level Supervisor setup for Unix hosts without systemd."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import http.client
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import plistlib
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
import urllib.request
import xmlrpc.client

from ..archives import private_json
from ..version import __version__

ROLE_VARIABLES = {
    "MNEMION_DATABASE_URL",
    "MNEMION_WORKER_DATABASE_URL",
    "MNEMION_ADMIN_DATABASE_URL",
    "MNEMION_DATABASE_PASSWORD_FILE",
    "MNEMION_API_KEY",
    "MNEMION_CREDENTIALS_FILE",
    "MNEMION_SUPERVISED_INSTANCE",
    "MNEMION_SUPERVISED_STATE",
    "MNEMION_SUPERVISED_ROLE",
    "PGPASSWORD",
    "PGPASSFILE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGUSER",
    "PGDATABASE",
    "PGHOST",
    "PGPORT",
    "PGOPTIONS",
}

# Persisted during managed staging so older, verified rollback runtimes remain
# usable. A runtime advertising this protocol must acknowledge both children.
READINESS_PROTOCOL = 1


class SupervisionError(ValueError):
    """A reviewed operator diagnostic with no credentials or source content."""


def _unix() -> None:
    if os.name != "posix":
        raise SupervisionError(
            "Supervisor supports Linux/macOS. Use the documented Docker deployment on Windows."
        )
    if os.geteuid() == 0:
        raise SupervisionError("Run user-level supervision as an unprivileged service account")


def _directory(path: Path) -> None:
    if path.is_symlink():
        raise SupervisionError("Supervision directories cannot be symlinks")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise SupervisionError("Supervision state must belong to the current user")
    path.chmod(0o700)


def _bytes(path: Path, maximum: int = 262144) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise SupervisionError("Use a bounded regular supervision input file")
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise SupervisionError("Supervision input is too large")
    return content


def _read(path: Path, maximum: int = 262144) -> dict:
    value = json.loads(_bytes(path, maximum))
    if not isinstance(value, dict):
        raise SupervisionError("Use a JSON object for supervision input")
    return value


def _private(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise SupervisionError("Managed supervision files must be private and owned by this user")


def _value(value: str, *, expansions: int = 1) -> str:
    # Supervisor's INI parser handles percent interpolation and semicolon
    # comments before command quoting. Never accept an injected INI directive.
    if any(ord(c) < 32 or ord(c) == 127 or c in ";#" for c in value):
        raise SupervisionError("Supervision paths cannot contain controls, semicolons or #")
    return value.replace("%", "%" * (2**expansions))


def _once(path: Path, value: dict) -> None:
    if path.exists():
        if path.is_symlink() or _read(path) != value:
            raise SupervisionError(
                "Existing supervision settings differ; use a new private state directory"
            )
        if path.stat().st_mode & 0o077:
            raise SupervisionError("Existing supervision state must have owner-only permissions")
    else:
        private_json(path, value)


def _content_once(path: Path, content: bytes) -> None:
    if path.exists():
        _private(path)
        if _bytes(path) != content:
            raise SupervisionError(
                "Existing generated startup configuration differs; it was preserved"
            )
    else:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)


def _runtime(state: Path) -> tuple[str, Path]:
    identifier = "mnemion-" + hashlib.sha256(str(state).encode()).hexdigest()[:24]
    if len(os.fsencode(state / "run/control.sock")) <= 100:
        directory = state / "run"
    else:
        parent = Path("/tmp") / f"mnemion-supervise-{os.getuid()}"
        _directory(parent)
        directory = parent / identifier
    _directory(directory)
    path = directory / "control.sock"
    if len(os.fsencode(path)) > 100:
        raise SupervisionError(
            "The supervision control socket path exceeds this operating system's limit"
        )
    return identifier, directory


def _environment(value: dict) -> dict[str, str]:
    result = {}
    for name, content in value.items():
        if (
            not name
            or not name.replace("_", "").isalnum()
            or name[0].isdigit()
            or not isinstance(content, str)
            or len(content) > 16384
            or "\x00" in content
            or name in ROLE_VARIABLES
            or name in {"PYTHONHOME", "PYTHONPATH"}
        ):
            raise SupervisionError(
                "Use string environment settings; database credentials belong in their role files"
            )
        result[name] = content
    return result


def prepare(
    state: Path,
    api: Path,
    worker: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 7892,
    public_url: str | None = None,
    studio: Path | None = None,
    environment: Path | None = None,
    managed_updates: bool = False,
) -> dict:
    _unix()
    state = state.expanduser().absolute()
    if state.is_symlink():
        raise SupervisionError("Supervision state cannot be a symlink")
    state = state.resolve()
    ipaddress.ip_address(host)
    if not 1024 <= port <= 65535:
        raise SupervisionError("Choose a service port between 1024 and 65535")
    if public_url:
        origin = urlsplit(public_url)
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path not in ("", "/")
            or origin.query
            or origin.fragment
        ):
            raise SupervisionError(
                "Use a public HTTPS origin without credentials, path, query or fragment"
            )
    credentials = {}
    for role, path, key in (
        ("api", api, "database_url"),
        ("worker", worker, "worker_database_url"),
    ):
        value = _read(path).get(key)
        if not isinstance(value, str) or not 1 <= len(value) <= 16384 or "\x00" in value:
            raise SupervisionError(
                f"The {role} credential file is missing its restricted database login"
            )
        credentials[role] = {key: value}
    runtime_environment = {
        key: value
        for key, value in os.environ.items()
        if (
            key.startswith(("MNEMION_MODEL_", "MNEMION_EMBEDDING_", "MNEMION_LIBRARIAN_"))
            or key
            in {
                "MNEMION_DB_POOL_SIZE",
                "MNEMION_HTTP_CONCURRENCY",
                "MNEMION_API_DOCS",
                "MNEMION_CORS_ORIGINS",
                "MNEMION_EVALUATIONS_DISABLED",
            }
        )
        and key not in ROLE_VARIABLES
    }
    runtime_environment.update(_read(environment) if environment else {})
    runtime_environment = _environment(runtime_environment)
    identifier, runtime = _runtime(state)
    # Preserve the venv executable path; resolve() would follow its symlink to
    # the base interpreter and discard the installed environment.
    executable = str(Path(sys.executable).absolute())
    from .studio import source_root

    settings = {
        "format": 1,
        "created_by_version": __version__,
        "identifier": identifier,
        "python": executable,
        "directory": str(source_root() or state),
        "host": host,
        "port": port,
        "public_url": public_url,
        "studio": str(studio.expanduser().resolve()) if studio else None,
        "runtime": str(runtime),
        "environment": runtime_environment,
        **({"managed_updates": True} if managed_updates else {}),
    }
    for value in (str(state), str(runtime), executable, settings["directory"]):
        _value(value)
    text = render(state, settings)
    settings["config_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    launchd_label = "com.mnemion.service." + identifier
    launchd = plistlib.dumps(
        {
            "Label": launchd_label,
            "ProgramArguments": [
                executable,
                "-m",
                "mnemion.service.supervision",
                "run",
                "--state-dir",
                str(state),
            ],
            "WorkingDirectory": settings["directory"],
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": 30,
            "ExitTimeOut": 90,
            # Supervisor rotates its private process logs. Avoid an unbounded
            # duplicate of its foreground output in launchd's file descriptors.
            "StandardOutPath": "/dev/null",
            "StandardErrorPath": "/dev/null",
        }
    )
    settings["launchd_sha256"] = hashlib.sha256(launchd).hexdigest()
    if len(json.dumps(settings).encode()) > 262144:
        raise SupervisionError("Supervision settings exceed the 256 KiB budget")
    _directory(state)
    _directory(state / "logs")
    for role, value in credentials.items():
        _once(state / f"{role}.json", value)
    _once(state / "settings.json", settings)
    _content_once(state / "supervisord.conf", text.encode())
    _content_once(state / "launchd.plist", launchd)
    boot = (
        "cd "
        + shlex.quote(settings["directory"])
        + " && "
        + shlex.join(
            [executable, "-m", "mnemion.service.supervision", "start", "--state-dir", str(state)]
        )
    )
    return {
        "prepared": True,
        "state_directory": str(state),
        "systemd_required": False,
        "boot_command": boot,
        "cron_entry": "@reboot " + boot.replace("%", r"\%"),
        "launchd_file": str(state / "launchd.plist"),
        "launchd_label": launchd_label,
    }


def render(state: Path, settings: dict) -> str:
    runtime = Path(settings["runtime"])
    config = f"""[unix_http_server]
file={_value(str(runtime / "control.sock"))}
chmod=0600

[supervisord]
identifier={settings["identifier"]}
logfile={_value(str(state / "logs/supervisord.log"))}
logfile_maxbytes=5MB
logfile_backups=2
pidfile={_value(str(runtime / "supervisord.pid"))}
childlogdir={_value(str(state / "logs"))}
umask=077
minfds=128
minprocs=32

[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix://{_value(str(runtime / "control.sock"))}
"""
    for role in (
        ("api", "worker", "updater") if settings.get("managed_updates") else ("api", "worker")
    ):
        command = shlex.join(
            [
                settings["python"],
                "-m",
                "mnemion.service.supervision",
                "child",
                "--state-dir",
                str(state),
                "--role",
                role,
            ]
        )
        config += f"""
[program:mnemion-{role}]
command={_value(command)}
directory={_value(settings["directory"])}
autostart=true
autorestart=true
startsecs=2
startretries=5
stopsignal=TERM
stopwaitsecs=35
stopasgroup=true
killasgroup=true
redirect_stderr=true
stdout_logfile={_value(str(state / "logs" / (role + ".log")), expansions=2)}
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=2
environment=PYTHONUNBUFFERED="1"
"""
    return config


def settings(state: Path) -> tuple[Path, dict]:
    _unix()
    state = state.expanduser().absolute()
    if (
        state.is_symlink()
        or not state.is_dir()
        or state.stat().st_uid != os.getuid()
        or state.stat().st_mode & 0o077
    ):
        raise SupervisionError("Use this user's private, prepared supervision state directory")
    state = state.resolve()
    for name in ("settings.json", "api.json", "worker.json", "supervisord.conf", "launchd.plist"):
        _private(state / name)
    value = _read(state / "settings.json")
    identifier, runtime = _runtime(state)
    if (
        value.get("format") != 1
        or value.get("identifier") != identifier
        or value.get("runtime") != str(runtime)
    ):
        raise SupervisionError("Supervision settings do not identify this local instance")
    if hashlib.sha256(_bytes(state / "supervisord.conf", 65536)).hexdigest() != value.get(
        "config_sha256"
    ):
        raise SupervisionError(
            "The managed Supervisor configuration was changed; review it before running commands"
        )
    if hashlib.sha256(_bytes(state / "launchd.plist", 65536)).hexdigest() != value.get(
        "launchd_sha256"
    ):
        raise SupervisionError(
            "The managed launchd configuration was changed; review it before use"
        )
    return state, value


class _Transport(xmlrpc.client.Transport):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def request(self, host, handler, body, verbose=False):
        connection = http.client.HTTPConnection("localhost", timeout=3)
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stream.settimeout(3)
        try:
            stream.connect(str(self.path))
            connection.sock = stream
            connection.request("POST", "/RPC2", body, {"Content-Type": "text/xml"})
            response = connection.getresponse()
            content = response.read(65537)
            if response.status != 200 or len(content) > 65536:
                raise SupervisionError("Invalid response from the local supervisor")
            return xmlrpc.client.loads(content)[0]
        finally:
            connection.close()
            stream.close()


def _rpc(value: dict):
    path = Path(value["runtime"]) / "control.sock"
    if path.is_symlink():
        raise SupervisionError("The private control socket cannot be a symlink")
    if path.exists():
        info = path.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise SupervisionError("The supervisor control socket must be private to this user")
    client = xmlrpc.client.ServerProxy("http://localhost/RPC2", transport=_Transport(path))
    if client.supervisor.getIdentification() != value["identifier"]:
        raise SupervisionError("The local supervisor belongs to a different instance")
    return client


@contextmanager
def process_ready(role: str, generations: list[str]):
    """Acknowledge initialization from the actual service process, after exec/imports.

    Supervisor RUNNING only describes survival past startsecs. A private receipt
    binds initialization to this process incarnation and the code/models it loaded.
    Ordinary service commands outside Supervisor do not publish host state.
    """
    location = os.environ.get("MNEMION_SUPERVISED_STATE")
    if location is None:
        yield
        return
    if role not in {"api", "worker"} or os.environ.get("MNEMION_SUPERVISED_ROLE") != role:
        raise SupervisionError("The service readiness role does not match its supervisor")
    import psutil

    from . import update_state

    _, value = settings(Path(location))
    process = psutil.Process()
    receipt = {
        "instance": value["identifier"],
        "role": role,
        "pid": process.pid,
        "created": process.create_time(),
        "version": __version__,
        "package": str(Path(__file__).resolve().parents[1]),
        "generations": sorted(set(generations)),
    }
    path = Path(value["runtime"]) / f"{role}-ready.json"
    update_state.write(path, receipt)
    try:
        yield
    finally:
        # A replacement process may already have published its own receipt.
        try:
            if update_state.read(path) == receipt:
                path.unlink()
        except (OSError, ValueError):
            pass


def _initialized(state: Path, value: dict, processes: list[dict]) -> bool | None:
    """Reject old receipts, reused PIDs, and a process from a different runtime."""
    import psutil

    from . import update_state

    try:
        runtime = (
            update_state.read(state / "updates/active.json")
            if value.get("managed_updates")
            else {"version": __version__, "readiness_protocol": READINESS_PROTOCOL}
        )
        protocol = runtime.get("readiness_protocol", 0)
        if type(protocol) is not int or protocol not in {0, READINESS_PROTOCOL}:
            return False
        if protocol == 0:
            # Older verified installations predate receipts. Keep their existing
            # readiness contract available for adoption and runtime rollback.
            return None
        models = None
        for role in ("api", "worker"):
            info = next(item for item in processes if item["name"] == "mnemion-" + role)
            if info["statename"] != "RUNNING" or info["pid"] <= 0:
                return False
            receipt = update_state.read(Path(value["runtime"]) / f"{role}-ready.json")
            process = psutil.Process(info["pid"])
            generations = receipt.get("generations")
            if (
                receipt.get("instance") != value["identifier"]
                or receipt.get("role") != role
                or receipt.get("pid") != info["pid"]
                or receipt.get("created") != process.create_time()
                or receipt.get("version") != runtime["version"]
                or (
                    runtime.get("isolated")
                    and receipt.get("package") != str(Path(runtime["package"]).resolve())
                )
                or not process.is_running()
                or process.status() == psutil.STATUS_ZOMBIE
                or not isinstance(generations, list)
                or not generations
                or not all(isinstance(item, str) for item in generations)
                or ("generations" in runtime and generations != runtime["generations"])
                or (models is not None and generations != models)
            ):
                return False
            models = generations
        return True
    except (OSError, ValueError, KeyError, StopIteration, psutil.Error):
        return False


def status(state: Path) -> dict:
    state, value = settings(state)
    try:
        with _rpc(value) as client:
            processes = client.supervisor.getAllProcessInfo()
            pid = client.supervisor.getPID()
    except xmlrpc.client.Fault as error:
        if error.faultCode == 6:  # Supervisor rejects normal RPC while draining children.
            return {"running": True, "stopping": True, "ready": False, "processes": []}
        raise
    except (FileNotFoundError, ConnectionRefusedError):
        return {"running": False, "ready": False, "processes": []}
    expected = {"mnemion-api", "mnemion-worker"}
    if value.get("managed_updates"):
        expected.add("mnemion-updater")
    if {item["name"] for item in processes} != expected:
        raise SupervisionError("Unexpected processes in the managed supervisor")
    host = value["host"]
    host = "127.0.0.1" if host == "0.0.0.0" else "::1" if host == "::" else host
    host = f"[{host}]" if ":" in host else host
    ready = False
    instance_matches = False
    try:
        # Ignore inherited HTTP proxies for this local readiness request.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{host}:{value['port']}/health/ready", timeout=3) as response:
            ready = response.status == 200
            api_pid = next(item["pid"] for item in processes if item["name"] == "mnemion-api")
            instance_matches = response.headers.get("X-Mnemion-Instance") == value[
                "identifier"
            ] and response.headers.get("X-Mnemion-Process") == str(api_pid)
    except (OSError, ValueError):
        pass
    initialized = _initialized(state, value, processes)
    unchanged = False
    if ready and instance_matches and initialized is not False:
        # HTTP and receipt checks must describe the same process snapshot. A
        # restart during either check cannot make a previous generation ready.
        def snapshot(items):
            return sorted(
                (item["name"], item["pid"], item.get("start"), item["statename"]) for item in items
            )

        try:
            with _rpc(value) as client:
                current = client.supervisor.getAllProcessInfo()
            unchanged = snapshot(current) == snapshot(processes)
            processes = current
        except (OSError, EOFError, xmlrpc.client.Error, http.client.HTTPException):
            # A supervisor may begin draining between the two observations.
            # Preserve a not-ready result instead of reporting stale readiness.
            unchanged = False
    return {
        "running": True,
        "ready": ready
        and instance_matches
        and initialized is not False
        and unchanged
        and all(item["statename"] == "RUNNING" for item in processes),
        "http_ready": ready,
        "instance_matches": instance_matches,
        "children_initialized": initialized,
        "supervisor_pid": pid,
        "processes": [
            {key: item[key] for key in ("name", "statename", "pid", "exitstatus")}
            for item in processes
        ],
        "logs_directory": str(state / "logs"),
    }


def start(state: Path, *, foreground: bool = False) -> dict:
    state, value = settings(state)
    if status(state)["running"]:
        return {**status(state), "already_running": True}
    if importlib.util.find_spec("supervisor") is None:
        raise SupervisionError(
            "Install the free supervision extra: uv sync --locked --extra supervision, or select that extra from the matching official Python release."
        )
    environment = {key: content for key, content in os.environ.items() if key not in ROLE_VARIABLES}
    command = [
        value["python"],
        "-m",
        "supervisor.supervisord",
        "-c",
        str(state / "supervisord.conf"),
    ]
    if foreground:
        os.execve(value["python"], [*command, "--nodaemon"], environment)
    result = subprocess.run(command, env=environment, capture_output=True, timeout=15, check=False)
    if result.returncode:
        descriptor, name = tempfile.mkstemp(prefix=".startup-", dir=state / "logs")
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(result.stdout[-16384:] + result.stderr[-16384:])
            os.replace(temporary, state / "logs/startup.log")
        finally:
            temporary.unlink(missing_ok=True)
        raise SupervisionError("Supervisor did not start; inspect the private logs directory")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        current = status(state)
        if current["ready"]:
            return current
        time.sleep(0.25)
    return status(state)


def stop(state: Path) -> dict:
    _, value = settings(state)
    deadline = time.monotonic() + 40
    requested = False
    attempted = False
    current = {"running": True, "ready": False, "control_unavailable": True}
    while time.monotonic() < deadline:
        if not requested:
            try:
                with _rpc(value) as client:
                    attempted = True
                    client.supervisor.shutdown()
                    requested = True
            except (FileNotFoundError, ConnectionRefusedError):
                return {"stopped": True, **({} if attempted else {"already_stopped": True})}
            except xmlrpc.client.Fault as error:
                if error.faultCode != 6:
                    raise
                requested = True
            except (ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected):
                # Shutdown may close a connection before its acknowledgement.
                # Repeat the idempotent request; a reset alone does not prove exit.
                pass
        if requested:
            try:
                current = status(state)
                if not current["running"]:
                    return {"stopped": True}
            except (ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected):
                pass
        time.sleep(0.25)
    return {"stopped": False, "status": current}


def child(state: Path, role: str) -> int:
    state, value = settings(state)
    os.environ.update(_environment(value["environment"]))
    for key in ROLE_VARIABLES:
        os.environ.pop(key, None)
    runtime = None
    if value.get("managed_updates"):
        from .service_updates import resolved_runtime, watch

        runtime = resolved_runtime(state)
        if role == "updater":
            if runtime["isolated"]:
                os.chdir(runtime["directory"])
                os.execve(
                    runtime["python"],
                    [
                        runtime["python"],
                        "-I",
                        "-m",
                        "mnemion.service.service_updates",
                        "watch",
                        "--state-dir",
                        str(state),
                    ],
                    os.environ,
                )
            return watch(state)
    elif role == "updater":
        raise SupervisionError("This Supervisor instance has no managed updater")
    arguments = ["--credentials", str(state / f"{role}.json")]
    os.environ["MNEMION_SUPERVISED_STATE"] = str(state)
    os.environ["MNEMION_SUPERVISED_ROLE"] = role
    if role == "worker":
        arguments.append("worker")
    else:
        os.environ["MNEMION_SUPERVISED_INSTANCE"] = value["identifier"]
        arguments += ["serve", "--host", value["host"], "--port", str(value["port"])]
        if value["public_url"]:
            arguments += ["--public-url", value["public_url"]]
        if value["studio"]:
            arguments += ["--studio", value["studio"]]
    if runtime and runtime["isolated"]:
        os.chdir(runtime["directory"])
        os.execve(
            runtime["python"],
            [runtime["python"], "-I", "-m", "mnemion.service.cli", *arguments],
            os.environ,
        )
    from .cli import main as service

    return service(arguments)


def arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=("prepare", "start", "run", "status", "stop", "child"))
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--api-credentials", type=Path)
    parser.add_argument("--worker-credentials", type=Path)
    parser.add_argument(
        "--environment", type=Path, help="Private JSON runtime settings and provider environment"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7892)
    parser.add_argument("--public-url")
    parser.add_argument("--studio", type=Path)
    parser.add_argument("--role", choices=("api", "worker", "updater"))


def execute(args: argparse.Namespace) -> int:
    try:
        if args.action == "prepare":
            if args.api_credentials is None or args.worker_credentials is None:
                raise SupervisionError("prepare requires both role credential paths")
            result = prepare(
                args.state_dir,
                args.api_credentials,
                args.worker_credentials,
                host=args.host,
                port=args.port,
                public_url=args.public_url,
                studio=args.studio,
                environment=args.environment,
            )
        elif args.action in {"start", "run"}:
            result = start(args.state_dir, foreground=args.action == "run")
        elif args.action == "stop":
            result = stop(args.state_dir)
        elif args.action == "child":
            if args.role is None:
                raise SupervisionError("child requires a role")
            return child(args.state_dir, args.role)
        else:
            result = status(args.state_dir)
        print(json.dumps(result))
        if args.action in {"start", "run"}:
            return 0 if result.get("ready") else 2
        return 0 if result.get("stopped", True) else 2
    except (OSError, ValueError, subprocess.SubprocessError, xmlrpc.client.Error) as error:
        # Third-party errors may contain a DSN, environment value or private path.
        message = (
            str(error)
            if isinstance(error, SupervisionError)
            else "Supervision command failed; inspect private settings and logs."
        )
        print(json.dumps({"error": message}), file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    return execute(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
