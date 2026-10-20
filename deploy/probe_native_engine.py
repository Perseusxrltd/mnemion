"""Run the portable service through real local setup, retrieval and restart."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
from zipfile import ZipFile

from deploy.probe_native_postgres import expand


def verify_agent_package(executable: Path, root: Path) -> None:
    """Check the installed command and logo data, without a server or model call."""
    destination = root / "Perseus XR connection.zip"
    result = subprocess.run(
        [
            str(executable),
            "agent-package",
            "--provider",
            "claude",
            "--mcp-url",
            "https://memory.example.test/mcp",
            "--output",
            str(destination),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode or len(result.stdout) > 16384:
        raise RuntimeError("The installed engine could not export its connection package")
    receipt = json.loads(result.stdout)
    assert receipt["author"] == "Perseus XR" and not receipt["contains_credentials"]
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == receipt["sha256"]
    with ZipFile(destination) as archive:
        manifest = json.loads(archive.read(".claude-plugin/plugin.json"))
        assert manifest["author"]["name"] == "Perseus XR"
        assert manifest["version"] == receipt["version"]
        assert archive.read("assets/icon.png").startswith(b"\x89PNG\r\n\x1a\n")
        assert ".app.json" not in archive.namelist()


class Engine:
    def __init__(self, executable: Path, workspace: Path, database: Path, *, initialize: bool):
        self.events = queue.Queue()
        self.executable, self.workspace = executable, workspace
        self.diagnostics = []
        self.peak_rss = 0
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("MNEMION_", "PG", "PYTHON", "HF_", "HUGGING_FACE"))
            and key not in {"LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"}
        }
        environment.update(
            HF_HOME=str(workspace.parent / "model-download-cache"),
            HF_HUB_DISABLE_TELEMETRY="1",
            HF_HUB_DISABLE_PROGRESS_BARS="1",
        )
        self.error_path = workspace.parent / (
            "engine-setup.log" if initialize else "engine-restart.log"
        )
        self.error_log = self.error_path.open("wb")
        self.child = subprocess.Popen(
            [
                str(executable),
                "local",
                "initialize" if initialize else "run",
                "--root",
                str(workspace),
                "--database-runtime",
                str(database),
            ],
            cwd=workspace.parent,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.error_log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if initialize:
            options = {
                "workspace_name": "Équipe native validation",
                "owner_name": "Disposable owner",
                "embedding_profile": "e5-small",
                "threads": 2,
                "memory": {"mode": "manual", "limit_mib": 1536},
            }
            self.child.stdin.write(json.dumps(options).encode() + b"\n")
            self.child.stdin.flush()

        def receive():
            while line := self.child.stdout.readline(32769):
                if len(line) > 32768:
                    self.events.put({"event": "error", "message": "Oversized operator response"})
                    return
                try:
                    self.events.put(json.loads(line))
                except ValueError:
                    self.events.put({"event": "error", "message": "Invalid operator response"})

        threading.Thread(target=receive, daemon=True).start()

    def memory(self, options: dict) -> dict:
        result = subprocess.run(
            [str(self.executable), "local", "memory", "--root", str(self.workspace)],
            input=json.dumps(options).encode() + b"\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        value = json.loads(result.stdout)
        if result.returncode or value.get("event") != "memory_policy":
            raise RuntimeError("The native agent could not update its private RAM policy")
        revision = value["policy"]["revision"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=0.25)
            except queue.Empty:
                continue
            if event.get("event") == "resources" and event["memory"]["revision"] == revision:
                return event["memory"]
        raise TimeoutError("The running engine did not apply the agent's RAM policy")

    def ready(self, timeout: int = 240) -> dict:
        import psutil

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                process = psutil.Process(self.child.pid)
                self.peak_rss = max(self.peak_rss, process.memory_info().rss)
            except psutil.NoSuchProcess:
                pass
            try:
                event = self.events.get(timeout=0.25)
            except queue.Empty:
                if self.child.poll() is not None:
                    raise RuntimeError("The native local service exited before becoming ready")
                continue
            if event.get("event") == "ready":
                return event
            if event.get("event") == "error":
                raise RuntimeError(
                    "Native setup failed: "
                    + event.get("code", "unknown")
                    + " / "
                    + event["message"]
                )
            self.diagnostics.append(
                {key: event[key] for key in ("event", "stage", "message") if key in event}
            )
        raise TimeoutError("The portable local service did not finish setup within its deadline")

    def stop(self):
        if self.child.poll() is None:
            try:
                self.child.stdin.write(b'{"action":"stop"}\n')
                self.child.stdin.close()
            except (OSError, BrokenPipeError):
                pass
            try:
                self.child.wait(timeout=90)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=10)
                raise RuntimeError("The native local service did not shut down cleanly") from None
        self.error_log.close()


def probe(
    executable: Path, database_archive: Path, output: Path, *, retain: Path | None = None
) -> dict:
    import httpx
    from mnemion.sdk import Client

    temporary = None if retain else tempfile.TemporaryDirectory(prefix="mnemion-engine-validation-")
    root = retain.resolve() if retain else Path(temporary.name).resolve()
    root.mkdir(mode=0o700, exist_ok=True)
    try:
        verify_agent_package(executable, root)
        database = root / "Native database with spaces"
        if not database.exists():
            expand(database_archive, database)
        workspace = root / "Private workspace Équipe"
        if workspace.exists():
            raise ValueError("Use a new disposable workspace for native validation")
        engine = None
        first = second = None
        first_memory = None
        initial_time = time.monotonic()
        try:
            engine = Engine(executable, workspace, database, initialize=True)
            first = engine.ready()
            setup_seconds = time.monotonic() - initial_time
            peak_rss = engine.peak_rss
            with Client(first["endpoint"], first["credential"]) as client:
                spaces = client.request("GET", "/v1/spaces")["items"]
                assert len(spaces) == 1
                space = spaces[0]["id"]
                saved = client.save(
                    space,
                    "Native installation validation: shared memory works across applications.",
                    kind="note",
                )
                assert client.wait(saved.operation_id, timeout=60)["state"] == "ready"
                first_memory = saved.memory_id
                hits = client.search("shared memory across applications", [space], mode="semantic")
                assert any(row.memory_id == first_memory for row in hits.hits)
                paused = engine.memory({"mode": "manual", "limit_mib": 256})
                assert paused["target_bytes"] <= 256 * 1024**2 and paused["indexing_paused"]
                assert paused["model_evictions"] >= 1
                pending = client.save(
                    space,
                    "A durable budgetcheckpoint memory survives paused model indexing.",
                    kind="note",
                )
                lexical = client.search("budgetcheckpoint", [space], mode="hybrid")
                assert any(hit.memory_id == pending.memory_id for hit in lexical.hits)
                assert "semantic_unavailable_lexical_only" in lexical.warnings
                assert client.request("GET", "/v1/insights/runtime")["model_loaded"] is False
                automatic = engine.memory({"mode": "auto", "limit_mib": None})
                assert (
                    automatic["mode"] == "auto"
                    and automatic["target_bytes"] <= automatic["effective_hardware_bytes"] // 4
                )
                resumed = engine.memory({"mode": "manual", "limit_mib": 1536})
                assert resumed["mode"] == "manual"
                assert client.wait(pending.operation_id, timeout=60)["state"] == "ready"
                assert any(
                    hit.memory_id == pending.memory_id
                    for hit in client.search("budgetcheckpoint", [space], mode="semantic").hits
                )
                with httpx.Client(base_url=first["endpoint"], timeout=20, trust_env=False) as http:
                    assert http.get("/v1/spaces").status_code == 401
                    response = http.post(
                        "/mcp",
                        headers={
                            "Authorization": "Bearer " + first["credential"],
                            "Accept": "application/json, text/event-stream",
                        },
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    )
                    assert response.status_code == 200
                    payload = response.json()
                    names = {tool["name"] for tool in payload["result"]["tools"]}
                    assert "memory_search" in names and "memory_save" in names
            engine.stop()
            assert engine.child.returncode == 0
            assert not (workspace / "database/postmaster.pid").exists()
            before = (workspace / "credentials.json").read_bytes()
            restart_time = time.monotonic()
            engine = Engine(executable, workspace, database, initialize=False)
            second = engine.ready()
            assert (workspace / "credentials.json").read_bytes() == before
            assert first["credential"] == second["credential"]
            assert first["endpoint"] == second["endpoint"]
            with Client(second["endpoint"], second["credential"]) as client:
                assert client.fetch(first_memory).memory_id == first_memory
                spaces = client.request("GET", "/v1/spaces")["items"]
                assert len(spaces) == 1 and spaces[0]["id"] == space
                memory_status = client.request("GET", "/v1/insights/runtime")["memory_budget"]
                assert (
                    memory_status["mode"] == "manual"
                    and memory_status["requested_limit_mib"] == 1536
                )
            result = {
                "passed": True,
                "engine_version": second["engine_version"],
                "real_model_inference": True,
                "real_semantic_index_and_search": True,
                "authenticated_api": True,
                "authenticated_mcp_tools": True,
                "perseus_agent_package": True,
                "anonymous_access_refused": True,
                "restart_preserves_credentials": True,
                "restart_preserves_memories_and_identity": True,
                "stable_local_address": True,
                "clean_database_shutdown": True,
                "single_service_and_model_process": True,
                "live_agent_ram_budget": True,
                "ram_budget_persists_after_restart": True,
                "automatic_ram_budget_respects_hardware": True,
                "lowering_ram_releases_idle_model": True,
                "paused_indexing_preserves_lexical_access": True,
                "raising_ram_resumes_pending_indexing": True,
                "setup_seconds": round(setup_seconds, 2),
                "restart_seconds": round(time.monotonic() - restart_time, 2),
                "observed_service_peak_rss_bytes": max(peak_rss, engine.peak_rss),
                "scope": "Portable engine and native database on a disposable local workspace; the GUI installer is a separate gate.",
            }
        finally:
            if engine is not None:
                engine.stop()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        if temporary is not None:
            temporary.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--database-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--retain",
        type=Path,
        help="Keep this disposable local fixture for investigation; it contains private generated credentials",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            probe(
                args.engine.resolve(),
                args.database_archive.resolve(),
                args.output.resolve(),
                retain=args.retain,
            )
        )
    )


if __name__ == "__main__":
    main()
