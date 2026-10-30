"""Disposable real memory API for the desktop resource diagnostic.

Only the PostgreSQL server created here can be used. Model providers, production
profiles and inherited Mnemion configuration are excluded. The existing 4-D
embedder fixture is a protocol fixture, not a retrieval-quality evaluation.

MNEMION_POSTGRES_ARCHIVES selects the verified native PostgreSQL archive for
this platform. Callers without that archive keep the pgserver development server.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack, asynccontextmanager
import os
from pathlib import Path
import socket

import uvicorn


def _native_archive() -> Path:
    directory = Path(os.environ["MNEMION_POSTGRES_ARCHIVES"])
    archives = sorted(path for path in directory.glob("*.zip") if path.is_file() and not path.is_symlink())
    if len(archives) != 1:
        raise RuntimeError("Supply exactly one verified native PostgreSQL archive")
    return archives[0]


class _NativeCluster:
    def __init__(self, root: Path, data: Path, binaries: Path, port: int, environment: dict[str, str]):
        self.root = root
        self.data = data
        self.binaries = binaries
        self.environment = environment
        self.dsn = f"postgresql://runtime_owner@127.0.0.1:{port}/postgres"

    def run(self, name: str, args: tuple[str, ...], *, timeout: int = 60) -> None:
        from mnemion.private_output import private_process

        suffix = ".exe" if os.name == "nt" else ""
        result = private_process(
            [str(self.binaries / (name + suffix)), *args],
            directory=self.root,
            env=self.environment,
            timeout=timeout,
        )
        if result.returncode:
            raise RuntimeError(f"Native PostgreSQL {name} failed ({result.returncode})")

    def cleanup(self) -> None:
        """Stop the cluster and refuse success while its postmaster is still present."""
        error: Exception | None = None
        try:
            self.run("pg_ctl", ("stop", "-D", str(self.data), "-m", "fast", "-w", "-t", "30"), timeout=40)
        except Exception as exc:
            error = exc
        if (self.data / "postmaster.pid").is_file():
            raise RuntimeError("Native PostgreSQL remained running after stop") from error
        if error is not None:
            raise RuntimeError("Native PostgreSQL stop failed") from error

    def stop(self) -> None:
        self.cleanup()


def _start_native_cluster(root: Path) -> _NativeCluster:
    from deploy.probe_native_postgres import expand, verify_database_sources
    from mnemion.local_state import directory as private_directory

    base = root / "native-postgres"
    base.mkdir(parents=True, exist_ok=True)
    install = base / "runtime"
    metadata = expand(_native_archive(), install)
    verify_database_sources(metadata)
    data = private_directory(base / "data")
    binaries = install / "bin"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PG")
        and key not in {
            "LD_LIBRARY_PATH",
            "DYLD_LIBRARY_PATH",
            "DYLD_FALLBACK_LIBRARY_PATH",
            "OPENSSL_MODULES",
            "OPENSSL_CONF",
        }
    }
    environment["LC_ALL"] = "C"
    environment["PATH"] = str(binaries) + os.pathsep + environment.get("PATH", "")
    control = private_directory(base / "control")
    cluster = _NativeCluster(control, data, binaries, 0, environment)
    cluster.run(
        "initdb",
        (
            "-D",
            str(data),
            "-U",
            "runtime_owner",
            "--auth-host=trust",
            "--auth-local=trust",
            "--encoding=UTF8",
            "--locale=C",
            "--locale-provider=builtin",
            "--builtin-locale=C.UTF-8",
        ),
        timeout=120,
    )
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    with (data / "postgresql.conf").open("a", encoding="utf-8") as stream:
        stream.write(
            "\nlisten_addresses='127.0.0.1'\n"
            f"port={port}\nunix_socket_directories=''\n"
            "shared_buffers='16MB'\nmax_connections=20\nssl=off\n"
        )
    cluster.dsn = f"postgresql://runtime_owner@127.0.0.1:{port}/postgres"
    try:
        cluster.run(
            "pg_ctl",
            ("start", "-D", str(data), "-l", str(control / "postgres.log"), "-w", "-t", "30"),
            timeout=40,
        )
    except Exception as start_error:
        try:
            cluster.cleanup()
        except Exception as cleanup_error:
            raise RuntimeError("Native PostgreSQL remained running after a failed start") from cleanup_error
        raise start_error
    return cluster


def _pgserver(directory: Path):
    import pgserver

    directory.mkdir(mode=0o700)
    return pgserver.get_server(directory, cleanup_mode="stop")


@asynccontextmanager
async def memory_workspace(root):
    # Imports and server/model construction belong to the unmeasured parent.
    from mnemion.service.api import create_app
    from service_tests.conftest import env, postgres

    if os.environ.get("MNEMION_POSTGRES_ARCHIVES"):
        cluster = await asyncio.to_thread(_start_native_cluster, Path(root))
        dsn = cluster.dsn
        cleanup = cluster.cleanup
    else:
        server = _pgserver(Path(root) / "postgres")
        dsn = server.get_uri()
        cleanup = server.cleanup
    counts = {"requests": 0, "successful": 0}
    try:
        with ExitStack() as resources:
            isolated = {
                key: value for key, value in os.environ.items() if not key.startswith("MNEMION_")
            }
            isolated.update(
                MNEMION_TEST_ADMIN_DSN=dsn,
                MNEMION_LIBRARIAN_DISABLED="1",
                MNEMION_EVALUATIONS_DISABLED="1",
            )
            resources.enter_context(patch_environment(isolated))
            database = postgres.__wrapped__(None)
            connections = next(database)
            resources.callback(next, database, None)
            setup = env.__wrapped__(connections)
            workspace = next(setup)
            resources.callback(next, setup, None)
            application = create_app(
                database=workspace.db,
                embedder=workspace.embedder,
                mcp_enabled=False,
                studio_enabled=False,
            )

            async def ingress(scope, receive, send):
                if scope["type"] == "http":
                    counts["requests"] += 1

                async def counted(event):
                    if event["type"] == "http.response.start" and 200 <= event["status"] < 300:
                        counts["successful"] += 1
                    await send(event)

                await application(scope, receive, counted)

            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(8)
                port = listener.getsockname()[1]
                api = uvicorn.Server(
                    uvicorn.Config(
                        ingress,
                        log_config=None,
                        access_log=False,
                        server_header=False,
                        date_header=False,
                    )
                )
                task = asyncio.create_task(api.serve(sockets=[listener]))
                try:
                    async with asyncio.timeout(20):
                        while not api.started:
                            if task.done():
                                await task
                                raise RuntimeError("Disposable memory API did not start")
                            await asyncio.sleep(0.01)
                    yield (
                        {
                            "base_url": f"http://127.0.0.1:{port}",
                            "api_key": workspace.token,
                            "space_id": str(workspace.space),
                        },
                        counts,
                    )
                finally:
                    api.should_exit = True
                    await task
    finally:
        await asyncio.to_thread(cleanup)


def patch_environment(isolated: dict[str, str]):
    from unittest.mock import patch

    return patch.dict(os.environ, isolated, clear=True)
