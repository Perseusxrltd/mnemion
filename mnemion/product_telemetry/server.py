"""Dedicated TLS collector process, separate from workspace services.

No access/error/trace output, forwarded headers, authentication, DNS lookup or
public reporting endpoint is enabled. The network stack necessarily handles
peer addresses transiently. Qualifying a deployment also requires inspecting
its host/provider logging and retention; this module does not enable clients.
"""

from __future__ import annotations

import argparse
import asyncio
from ipaddress import ip_address
import json
import os
from pathlib import Path
import socket
import ssl
import sys

import uvicorn
from uvicorn.protocols.http.flow_control import FlowControl
from uvicorn.protocols.http.h11_impl import H11Protocol

from .collector import Collector
from .publication import ReportStore

MAX_CONNECTIONS = 32
MAX_REQUEST_BYTES = 4096
CONNECTION_SECONDS = 5
QUIET_LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {"discard": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["discard"], "level": "CRITICAL"},
    "loggers": {
        name: {"handlers": ["discard"], "level": "CRITICAL", "propagate": False}
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "asyncio")
    },
}


class ConfigurationError(ValueError):
    pass


def _disable_crash_dumps():
    """Protect the dedicated Linux collector before loading private state."""
    if sys.platform != "linux":
        return
    try:
        import ctypes
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        # Linux ignores RLIMIT_CORE for piped crash handlers. Disable process
        # dumpability as well, then verify the kernel accepted that setting.
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        prctl.argtypes = [
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        prctl.restype = ctypes.c_int
        if prctl(4, 0, 0, 0, 0) != 0 or prctl(3, 0, 0, 0, 0) != 0:
            raise ConfigurationError
    except (AttributeError, ImportError, OSError, ValueError):
        raise ConfigurationError from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes invalid values. Operator errors, including
        # paths or accidental credentials, only receive a fixed error below.
        raise ConfigurationError


class MetadataBoundary:
    def __init__(self, app, route="/v1/report"):
        if route not in {"/v1/report", "/v3/report"}:
            raise ConfigurationError
        self.app = app
        self.route = route

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            method = scope.get("method")
            # Only the route selected for this process is preserved. Every other
            # path, including a near miss, becomes the inert sentinel.
            path = self.route if scope.get("path") == self.route else "/"
            query = b"?" if scope.get("query_string") else b""
            # Clear the original scope as well as the parser's shared header
            # list. Only fixed routing flags cross into aggregate processing.
            scope.get("headers", []).clear()
            scope.clear()
            scope.update(
                {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.3"},
                    "http_version": "1.1",
                    "scheme": "https",
                    "method": method if method in {"POST", "OPTIONS", "HEAD"} else "OTHER",
                    "path": path,
                    "raw_path": path.encode("ascii"),
                    "root_path": "",
                    "query_string": query,
                    "headers": [],
                    "client": None,
                    "server": None,
                }
            )
        await self.app(scope, receive, send)


class BoundedProtocol(H11Protocol):
    """Use h11 parsing with one short, bounded request per TLS connection."""

    def connection_made(self, transport):
        self.transport = transport
        self.flow = FlowControl(transport)
        self.client = self.server = None
        self.scheme = "https"
        self._received_bytes = 0
        self._deadline = None
        if len(self.connections) >= MAX_CONNECTIONS:
            transport.close()
            return
        self.connections.add(self)
        self._deadline = self.loop.call_later(CONNECTION_SECONDS, transport.close)

    def data_received(self, data):
        self._received_bytes += len(data)
        if self._received_bytes > MAX_REQUEST_BYTES:
            self.transport.close()
            return
        super().data_received(data)

    def on_response_complete(self):
        self.server_state.total_requests += 1
        # No pipelining, keepalive, per-connection profile or reconnect token.
        self.transport.close()

    def connection_lost(self, exc):
        if self._deadline is not None:
            self._deadline.cancel()
        super().connection_lost(exc)


def _tls_context(config, default_factory):
    context = default_factory()
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.options |= ssl.OP_NO_TICKET
    context.num_tickets = 0
    context.keylog_filename = None
    context.set_alpn_protocols(["http/1.1"])
    return context


class _Server(uvicorn.Server):
    async def startup(self, sockets=None):
        # The dedicated entrypoint has one validated listener and no reload
        # workers. Explicit TLS deadlines bound even a client that never sends
        # enough handshake data to instantiate BoundedProtocol.
        if sockets is not None and len(sockets) != 1:
            raise ConfigurationError
        await self.lifespan.startup()
        if self.lifespan.should_exit:
            self.should_exit = True
            return
        loop = asyncio.get_running_loop()

        def protocol():
            return BoundedProtocol(
                config=self.config,
                server_state=self.server_state,
                app_state=self.lifespan.state,
            )

        listener = await loop.create_server(
            protocol,
            **(
                {"sock": sockets[0]}
                if sockets is not None
                else {"host": self.config.host, "port": self.config.port}
            ),
            ssl=self.config.ssl,
            backlog=64,
            ssl_handshake_timeout=CONNECTION_SECONDS,
            ssl_shutdown_timeout=1,
        )
        self.servers = [listener]
        self.started = True


def _systemd_listener(bind: str, port: int) -> socket.socket:
    """Take exactly the named TCP listener handed to this process by systemd."""
    if (
        sys.platform != "linux"
        or os.environ.get("LISTEN_PID") != str(os.getpid())
        or os.environ.get("LISTEN_FDS") != "1"
        or os.environ.get("LISTEN_FDNAMES") != "telemetry"
    ):
        raise ConfigurationError
    for name in ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"):
        os.environ.pop(name, None)
    listener = socket.socket(fileno=3)
    try:
        listener.set_inheritable(False)
        family = socket.AF_INET6 if ip_address(bind).version == 6 else socket.AF_INET
        # Let the OS canonicalize numeric addresses and IPv6 scope IDs into its
        # native sockaddr shape. These flags prohibit name/service resolution.
        addresses = socket.getaddrinfo(
            bind,
            port,
            family,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
        )
        if (
            len(addresses) != 1
            or listener.family != family
            or listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM
            or listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1
            or listener.getsockname() != addresses[0][4]
        ):
            raise ConfigurationError
        return listener
    except BaseException:
        listener.close()
        raise


def _selected_application(mode: str, state: Path):
    """Mount one known collector and its own store. Unknown modes are refused."""
    if mode == "legacy":
        return MetadataBoundary(Collector(ReportStore(state)), route="/v1/report")
    if mode == "v3":
        from .collector_v3 import CollectorV3
        from .publication_v3 import ReportStore as ReportStoreV3

        return MetadataBoundary(CollectorV3(ReportStoreV3(state)), route="/v3/report")
    raise ConfigurationError


async def _serve(args, application, listener=None):
    # Default asyncio diagnostics can include protocol/transport reprs. This
    # applies only in the isolated collector process, never the workspace app.
    asyncio.get_running_loop().set_exception_handler(lambda _loop, _context: None)
    config = uvicorn.Config(
        application,
        host=args.bind,
        port=args.port,
        http=BoundedProtocol,
        ws="none",
        loop="asyncio",
        interface="asgi3",
        lifespan="on",
        workers=1,
        log_config=QUIET_LOGGING,
        access_log=False,
        proxy_headers=False,
        forwarded_allow_ips=[],
        server_header=False,
        date_header=False,
        headers=[("connection", "close")],
        limit_concurrency=MAX_CONNECTIONS,
        backlog=64,
        timeout_keep_alive=0,
        timeout_graceful_shutdown=5,
        h11_max_incomplete_event_size=MAX_REQUEST_BYTES,
        ssl_certfile=args.certificate,
        ssl_keyfile=args.private_key,
        ssl_context_factory=_tls_context,
    )
    server = _Server(config)
    await server.serve(sockets=[listener] if listener is not None else None)
    return 0 if server.started else 1


def main(argv=None):
    parser = _Parser(description="Perseus XR anonymous aggregate collector")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    serve = commands.add_parser("serve", help="Run one dedicated TLS listener")
    serve.add_argument("--state", type=Path, required=True)
    serve.add_argument("--mode", choices=("legacy", "v3"), default="legacy")
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8443)
    serve.add_argument("--certificate", type=Path, required=True)
    serve.add_argument("--private-key", type=Path, required=True)
    serve.add_argument(
        "--systemd-socket", action="store_true", help="Use the validated service-manager listener"
    )
    reports = commands.add_parser("reports", help="Read only retained closed-week summaries")
    reports.add_argument("--state", type=Path, required=True)
    listener = None
    try:
        args = parser.parse_args(argv)
        if not args.state.is_absolute():
            raise ConfigurationError
        if args.command == "reports":
            if not (args.state / "reports.sqlite3").is_file():
                raise ConfigurationError
            result = ReportStore(args.state).reports()
            print(json.dumps({"schema_version": 1, "reports": result}, allow_nan=False))
            return 0
        if (
            str(ip_address(args.bind)) != args.bind
            or not 1 <= args.port <= 65535
            or not args.certificate.is_absolute()
            or not args.private_key.is_absolute()
        ):
            raise ConfigurationError
        _disable_crash_dumps()
        if args.systemd_socket:
            listener = _systemd_listener(args.bind, args.port)
        application = _selected_application(args.mode, args.state)
        return asyncio.run(_serve(args, application, listener))
    except (ConfigurationError, ValueError, OSError):
        print('{"error":"telemetry_collector_configuration_invalid"}', file=sys.stderr)
        return 2
    except Exception:
        print('{"error":"telemetry_collector_failed"}', file=sys.stderr)
        return 1
    finally:
        if listener is not None:
            listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
