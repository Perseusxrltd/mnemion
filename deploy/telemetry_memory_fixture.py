"""Disposable real memory API for the desktop resource diagnostic.

Only the PostgreSQL server created here can be used. Model providers, production
profiles and inherited Mnemion configuration are excluded. The existing 4-D
embedder fixture is a protocol fixture, not a retrieval-quality evaluation.
"""

import asyncio
from contextlib import ExitStack, asynccontextmanager
import os
from unittest.mock import patch

import pgserver
import uvicorn


@asynccontextmanager
async def memory_workspace(root):
    # Imports and server/model construction belong to the unmeasured parent.
    from mnemion.service.api import create_app
    from service_tests.conftest import env, postgres

    directory = root / "postgres"
    directory.mkdir(mode=0o700)
    server = pgserver.get_server(directory, cleanup_mode="stop")
    counts = {"requests": 0, "successful": 0}
    try:
        with ExitStack() as resources:
            isolated = {
                key: value for key, value in os.environ.items() if not key.startswith("MNEMION_")
            }
            isolated.update(
                MNEMION_TEST_ADMIN_DSN=server.get_uri(),
                MNEMION_LIBRARIAN_DISABLED="1",
                MNEMION_EVALUATIONS_DISABLED="1",
            )
            resources.enter_context(patch.dict(os.environ, isolated, clear=True))
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

            import socket

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
        server.cleanup()
