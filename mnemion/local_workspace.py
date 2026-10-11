"""Typed local operator used by Studio and agents running as the OS user.

This module is never reachable through an organization memory credential. Its
private stdout pipe includes the new owner connection only after actual checks.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import sys
import threading
import time
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import local_state as state
from .local_database import LocalDatabase, available_port, prepare_credentials
from . import local_memory
from .service.memory_budget import MemoryBudget, MemoryOptions, sample_memory, working_target
from .version import __version__


class SetupOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    workspace_name: str = Field(min_length=1, max_length=200)
    owner_name: str = Field(min_length=1, max_length=200)
    embedding_profile: Literal["e5-small", "bge-small-en"] = "e5-small"
    threads: int = Field(default=2, ge=1, le=8)
    port: int = Field(default=7892, ge=1024, le=65535)
    memory: MemoryOptions = Field(default_factory=MemoryOptions)

    @field_validator("workspace_name", "owner_name")
    @classmethod
    def names(cls, value: str) -> str:
        if not value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("Use a name without control characters")
        return value.strip()


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resources(root: Path) -> dict:
    import psutil

    location = root
    while not location.exists():
        location = location.parent
    memory = psutil.virtual_memory()
    capacity = sample_memory()
    target, reserve = working_target(MemoryOptions(), capacity)
    disk = shutil.disk_usage(location)
    return {
        "memory_bytes": memory.total,
        "available_memory_bytes": memory.available,
        "effective_memory_bytes": capacity.total,
        "effective_available_memory_bytes": capacity.available,
        "recommended_budget_bytes": target,
        "system_reserve_bytes": reserve,
        "recommended_profile": "e5-small" if target >= 1280 * 1024**2 else "bge-small-en",
        "available_disk_bytes": disk.free,
        "cpu_threads": os.cpu_count() or 1,
        "platform": sys.platform,
        "architecture": platform.machine(),
        "gpu_required": False,
        "minimum_free_disk_bytes": 2 * 1024**3,
        "profiles": [
            {
                "id": "e5-small",
                "label": "Multilingual E5 Small",
                "languages": "Multilingual",
                "minimum_available_memory_bytes": 1024**3,
            },
            {
                "id": "bge-small-en",
                "label": "BGE Small English",
                "languages": "English",
                "minimum_available_memory_bytes": 512 * 1024**2,
            },
        ],
    }


def configuration(root: Path) -> dict:
    value = state.read(root / "configuration.json")
    try:
        if value["format"] != 1:
            raise ValueError("Unsupported local format")
        UUID(value["workspace_id"])
        options = SetupOptions.model_validate(
            {name: value[name] for name in SetupOptions.model_fields if name in value}
        )
        if (
            type(value["database_port"]) is not int
            or not 1024 <= value["database_port"] <= 65535
            or options.port == value["database_port"]
        ):
            raise ValueError("Invalid database port")
        return {**value, **options.model_dump()}
    except (KeyError, ValueError, TypeError):
        raise state.LocalSetupError(
            "damaged_configuration",
            "The saved workspace settings need recovery. Existing data has been retained.",
        ) from None


def inspect(root: Path) -> dict:
    result = {
        "configured": False,
        "data_directory": str(root),
        "resources": resources(root),
        "engine_version": __version__,
    }
    if (root / "configuration.json").exists():
        settings = configuration(root)
        result.update(
            configured=True,
            settings=settings,
            **local_memory.inspection(root),
            memory=local_memory.live_status(root),
        )
        if (root / "readiness.json").exists():
            result["last_verification"] = state.read(root / "readiness.json")
    return result


def initialize(root: Path, options: SetupOptions) -> dict:
    if (root / "configuration.json").exists():
        saved = configuration(root)
        if any(
            saved[name] != getattr(options, name)
            for name in ("workspace_name", "owner_name", "embedding_profile", "threads")
        ):
            raise state.LocalSetupError(
                "already_configured",
                "This local workspace already has saved settings. Resume it before changing its configuration.",
            )
        return saved
    if any(path.name != "operator.lock" for path in root.iterdir()):
        raise state.LocalSetupError(
            "existing_data",
            "This folder already contains data. Recover the existing workspace instead of creating one over it.",
        )
    capacity = resources(root)
    if capacity["effective_available_memory_bytes"] < 256 * 1024**2:
        raise state.LocalSetupError(
            "memory_budget",
            "Free some memory, choose the smaller English model, or join a workspace hosted on another computer.",
        )
    if capacity["available_disk_bytes"] < capacity["minimum_free_disk_bytes"]:
        raise state.LocalSetupError(
            "disk_budget", "Free at least 2 GB on this drive before creating a local workspace."
        )
    port = available_port(options.port)
    database_port = available_port()
    while database_port == port:
        database_port = available_port()
    value = {
        "format": 1,
        "workspace_id": str(uuid4()),
        "created_at": timestamp(),
        **options.model_dump(),
        "port": port,
        "database_port": database_port,
    }
    state.write(root / "configuration.json", value, replace=False)
    local_memory.configure(
        root, local_memory.MemoryChange(**options.memory.model_dump()), initial=True
    )
    return value


def registry_for(root: Path, settings: dict):
    from .service.embeddings import LocalEmbedder
    from .service.model_catalog import LOCAL_GENERATIONS
    from .service.model_registry import ModelRegistry

    cache = state.directory(root / "models")
    profiles = {
        name: LocalEmbedder(cache, threads=settings["threads"], generation=generation)
        for name, generation in LOCAL_GENERATIONS.items()
    }
    return ModelRegistry(profiles[settings["embedding_profile"]], profiles)


def _backup_before_migration(database: LocalDatabase, emit) -> None:
    import hashlib
    from importlib.resources import files
    import psycopg

    with psycopg.connect(database.dsn(database="postgres")) as connection:
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname='mnemion'").fetchone()
    if not exists:
        return
    with psycopg.connect(database.dsn()) as connection:
        if not connection.execute("SELECT to_regclass('mnemion.schema_migrations')").fetchone()[0]:
            return
        applied = dict(connection.execute("SELECT name,sha256 FROM mnemion.schema_migrations"))
    expected = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files("mnemion.service").joinpath("migrations").iterdir()
        if p.name.endswith(".sql")
    }
    if any(expected.get(name) != digest for name, digest in applied.items()):
        raise state.LocalSetupError(
            "schema_version",
            "This workspace needs a newer or matching app version. Its schema has not been changed.",
        )
    if applied == expected:
        return
    emit(
        {
            "event": "progress",
            "stage": "backup",
            "message": "Saving a verified backup before the database update…",
        }
    )
    from .service.recovery import create_backup

    output = state.directory(database.root / "backups") / (
        "before-" + __version__ + "-" + uuid4().hex + ".zip"
    )
    create_backup(database.dsn(), output, pg_bin=database.runtime / "bin")


def run(
    root: Path,
    runtime: Path,
    *,
    options: SetupOptions | None,
    emit,
    stop: threading.Event,
    desktop_memory=None,
) -> None:
    with state.lock(root):
        settings = initialize(root, options) if options is not None else configuration(root)
        credentials = prepare_credentials(root)
        database = LocalDatabase(root, runtime, settings, credentials)
        registry = registry_for(root, settings)
        saved_policy = local_memory.policy(root)
        budget = MemoryBudget(
            MemoryOptions.model_validate(saved_policy["settings"]),
            revision=saved_policy["revision"],
            sample=lambda: sample_memory(
                database_identity=database.process_identity,
                desktop_bytes=desktop_memory() if desktop_memory else 0,
            ),
        )
        budget.attach(registry)
        monitor = local_memory.MemoryMonitor(root, budget, emit)

        def progress(stage: str, message: str):
            if stop.is_set():
                raise state.LocalSetupError(
                    "setup_paused", "Setup is paused. Resume whenever you are ready."
                )
            emit({"event": "progress", "stage": stage, "message": message})

        try:
            progress("database", "Preparing your private local database…")
            database.start()
            _backup_before_migration(database, emit)
            progress("access", "Creating your workspace and checking its permissions…")
            database.provision(registry.default.generation)
            import psycopg
            from .service.admin import register_generation

            with psycopg.connect(database.dsn()) as connection:
                for generation in registry.generation_ids:
                    register_generation(connection, registry.get(generation).generation)
            progress(
                "model", "Preparing your memory model. The first download can take a few minutes…"
            )
            monitor.start()
            if budget.can_schedule(registry.default):
                from .service.errors import ServiceError

                try:
                    registry.default.prepare()
                    # The real model must perform inference, not merely download files.
                    registry.default.query("Verify this private memory workspace")
                except ServiceError as error:
                    if error.code != "inference_memory_budget":
                        raise
            progress("service", "Starting the memory service and background indexing…")
            asyncio.run(
                _serve(root, settings, credentials, database, registry, monitor, emit, stop)
            )
        finally:
            monitor.close()
            registry.close()
            database.stop()


async def _serve(
    root: Path,
    settings: dict,
    credentials: dict,
    database: LocalDatabase,
    registry,
    monitor,
    emit,
    stop: threading.Event,
):
    import uvicorn
    from .service.api import create_app
    from .service.db import Database
    from .service.model_worker import ModelWorker
    from .service.telemetry import Telemetry

    listener = socket.socket()
    if os.name == "nt":
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(("127.0.0.1", settings["port"]))
        listener.listen(64)
    except OSError:
        listener.close()
        raise state.LocalSetupError(
            "port_in_use",
            "Another program is using this workspace’s local address. Close it and retry, or change the workspace port.",
        ) from None
    api = Database(database.dsn("api"), max_size=4)
    worker_db = Database(database.dsn("worker"), worker=True, max_size=2)
    worker_stop = threading.Event()
    worker_failure = threading.Event()
    worker_ready = threading.Event()
    worker = None
    try:
        api.open()
        worker_db.open()
        telemetry = Telemetry(worker_db)
        processor = ModelWorker(worker_db, registry, telemetry=telemetry)

        def process():
            try:
                # Readiness means the already-open worker can run. A resumed
                # workspace may have hours of queued indexing; draining that
                # queue must not prevent access to its durable memories.
                worker_ready.set()
                while not worker_stop.is_set():
                    if not processor.run_once():
                        worker_stop.wait(0.25)
            except Exception:
                worker_failure.set()
                stop.set()

        app = create_app(database=api, registry=registry, mcp_enabled=True, studio_enabled=False)
        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(application):
            nonlocal worker
            async with original_lifespan(application):
                telemetry.start()
                worker = threading.Thread(target=process, name="mnemion-local-index", daemon=True)
                worker.start()
                try:
                    yield
                finally:
                    worker_stop.set()
                    await asyncio.to_thread(worker.join, 35)
                    telemetry.stop()

        app.router.lifespan_context = lifespan
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=settings["port"],
                access_log=False,
                proxy_headers=False,
                workers=1,
                limit_concurrency=24,
                timeout_keep_alive=5,
                timeout_graceful_shutdown=30,
                log_level="warning",
            )
        )
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            deadline = time.monotonic() + 30
            while not server.started or not worker_ready.is_set():
                if serving.done():
                    await serving
                    raise state.LocalSetupError(
                        "service_start",
                        "The local memory service could not start. Retry to resume your workspace.",
                    )
                if stop.is_set() or time.monotonic() > deadline:
                    raise state.LocalSetupError(
                        "service_start",
                        "The local memory service did not become ready. Retry to resume your workspace.",
                    )
                await asyncio.sleep(0.1)
            if stop.is_set():
                raise state.LocalSetupError(
                    "service_start",
                    "The local memory service stopped before its checks. Retry to resume your workspace.",
                )
            endpoint = "http://127.0.0.1:" + str(settings["port"])
            emit(
                {
                    "event": "progress",
                    "stage": "verification",
                    "message": "Checking a saved memory, search and your agent connection…",
                }
            )
            await asyncio.to_thread(_verify, root, endpoint, credentials, settings, registry)
            if stop.is_set() or worker_failure.is_set() or serving.done():
                raise state.LocalSetupError(
                    "service_start",
                    "The local memory service stopped during its checks. Retry to resume your workspace.",
                )
            emit(
                {
                    "event": "ready",
                    "endpoint": endpoint,
                    "credential": credentials["api_key"],
                    "workspace_id": settings["workspace_id"],
                    "engine_version": __version__,
                }
            )
            next_resources = 0.0
            while not stop.is_set() and not serving.done():
                if time.monotonic() >= next_resources:
                    next_resources = time.monotonic() + 2
                    target = registry.memory_budget.snapshot()["target_bytes"]
                    server.config.limit_concurrency = min(24, max(4, target // (64 * 1024**2)))
                await asyncio.sleep(0.25)
            if worker_failure.is_set():
                raise state.LocalSetupError(
                    "indexing_stopped",
                    "Background indexing stopped. Restart the local workspace to retry; saved memories remain in its database.",
                )
        finally:
            worker_stop.set()
            server.should_exit = True
            await serving
    finally:
        worker_stop.set()
        if worker is not None:
            await asyncio.to_thread(worker.join, 35)
        worker_db.close()
        api.close()
        listener.close()


def _verify(root: Path, endpoint: str, credentials: dict, settings: dict, registry) -> None:
    from .sdk import Client, MnemionError

    generation_id = registry.default.generation.id
    semantic = False
    indexed = False
    with Client(endpoint, credentials["api_key"], retries=0) as client:
        identity = client.request("GET", "/v1/me")
        if (
            identity["tenant_id"] != credentials["tenant_id"]
            or identity["principal_id"] != credentials["principal_id"]
        ):
            raise state.LocalSetupError(
                "workspace_identity", "The workspace identity did not match the saved setup."
            )
        ready = client.request("GET", "/health/ready")
        if ready["generation_id"] != generation_id:
            raise state.LocalSetupError(
                "model_identity", "The workspace model did not match the selected profile."
            )
        first_start = not (root / "readiness.json").exists()
        receipt = None
        if first_start:
            receipt = client.save(
                credentials["space_id"],
                "Welcome to your private Mnemion workspace. You can save memories, connect your sources, and give each assistant access to the spaces it needs.",
                subject="Welcome to Mnemion",
                kind="note",
                metadata={"origin": "workspace-setup"},
                idempotency_key="local-welcome-" + settings["workspace_id"],
            )

        # Query on every start, even when a previous readiness record exists.
        # A restart does not recreate a welcome note the owner may have deleted
        # or add a new probe to the durable indexing queue.
        found = client.search("private workspace", [credentials["space_id"]], mode="lexical")
        if receipt is not None and not any(
            str(hit.memory_id) == str(receipt.memory_id) for hit in found.hits
        ):
            raise state.LocalSetupError(
                "search_verification",
                "The saved welcome memory was not returned by keyword search. Retry before adding more sources.",
            )
        selected = registry.get(found.index.generation_id)
        if registry.memory_budget.can_schedule(selected):
            if receipt is not None:
                operation = client.wait(str(receipt.operation_id), timeout=60)
                if operation["state"] != "ready":
                    raise state.LocalSetupError(
                        "index_verification",
                        "Your welcome memory was saved, but indexing needs a retry. Setup will resume without duplicating it.",
                    )
            try:
                found = client.search(
                    "private workspace", [credentials["space_id"]], mode="semantic"
                )
            except MnemionError as error:
                # A live reduction may arrive after admission. Preserve
                # keyword access without recording unperformed inference as
                # successful. Other service errors still fail readiness.
                reduced = error.code == "embedding_unavailable" and (
                    not registry.memory_budget.can_schedule(selected)
                    or (
                        hasattr(selected, "_model")
                        and not registry.memory_budget.can_infer(selected)
                    )
                )
                busy = not first_start and error.code == "inference_busy"
                if not (reduced or busy):
                    raise
            else:
                semantic = True
                indexed = bool(found.hits)
                if receipt is not None and not any(
                    str(hit.memory_id) == str(receipt.memory_id) for hit in found.hits
                ):
                    raise state.LocalSetupError(
                        "search_verification",
                        "The saved welcome memory was not returned by semantic search. Retry before adding more sources.",
                    )
        state.write(
            root / "readiness.json",
            {
                "format": 1,
                "verified_at": timestamp(),
                "engine_version": __version__,
                "generation_id": generation_id,
                "workspace_id": settings["workspace_id"],
                "database": True,
                "separate_database_roles": True,
                "worker": True,
                "authenticated_api": True,
                "lexical_search": True,
                "model_inference": semantic,
                "semantic_index": indexed,
                "shared_inference_process": True,
            },
        )


def arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action", choices=["status", "initialize", "run", "memory", "memory-repair"]
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--database-runtime", type=Path)


def dispatch(args) -> int:
    output_lock = threading.Lock()

    def emit(value):
        with output_lock:
            print(json.dumps(value, ensure_ascii=True), flush=True)

    root = args.root.expanduser().absolute()
    stop = threading.Event()
    try:
        if args.action == "status":
            emit({"event": "status", **inspect(root)})
            return 0
        if args.action in {"memory", "memory-repair"}:
            line = sys.stdin.buffer.readline(4097)
            if len(line) > 4096:
                raise ValueError("The RAM policy exceeds its size limit")
            value = (
                local_memory.repair(root, local_memory.MemoryRepair.model_validate_json(line))
                if args.action == "memory-repair"
                else local_memory.configure(
                    root, local_memory.MemoryChange.model_validate_json(line)
                )
            )
            emit({"event": "memory_policy", "policy": value, "apply_within_seconds": 2})
            return 0
        if not args.database_runtime:
            raise state.LocalSetupError(
                "missing_runtime",
                "The local database package is missing. Reinstall the complete app.",
            )
        options = None
        if args.action == "initialize":
            line = sys.stdin.buffer.readline(32769)
            if len(line) > 32768:
                raise state.LocalSetupError(
                    "invalid_options", "The setup options exceed their size limit."
                )
            options = SetupOptions.model_validate_json(line)

        desktop_bytes = 0

        def input_monitor():
            nonlocal desktop_bytes
            while line := sys.stdin.buffer.readline(1025):
                if len(line) > 1024:
                    continue
                try:
                    command = json.loads(line)
                    if command == {"action": "stop"}:
                        break
                    if (
                        command.get("action") == "desktop_usage"
                        and type(command.get("resident_bytes")) is int
                        and 0 <= command["resident_bytes"] <= 1024**4
                    ):
                        desktop_bytes = command["resident_bytes"]
                except (ValueError, AttributeError):
                    pass
            stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        threading.Thread(target=input_monitor, name="mnemion-operator-control", daemon=True).start()
        run(
            root,
            args.database_runtime,
            options=options,
            emit=emit,
            stop=stop,
            desktop_memory=lambda: desktop_bytes,
        )
        emit({"event": "stopped"})
        return 0
    except state.LocalSetupError as error:
        emit({"event": "error", "code": error.code, "message": str(error), "data_retained": True})
    except (ValidationError, ValueError):
        emit(
            {
                "event": "error",
                "code": "invalid_options",
                "message": "Check the workspace names, model and resource settings, then retry.",
                "data_retained": True,
            }
        )
    except Exception:
        # Database, inference and provider exceptions can contain private paths,
        # DSNs or source text. Only reviewed messages cross this operator pipe.
        emit(
            {
                "event": "error",
                "code": "setup_failed",
                "message": "Local setup could not finish. Check the network, available memory and disk, then retry. Existing data has been retained.",
                "data_retained": True,
            }
        )
    return 1
