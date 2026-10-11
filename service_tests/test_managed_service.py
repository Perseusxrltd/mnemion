"""Managed updates use real PostgreSQL, isolated credentials and live processes."""

import os
from pathlib import Path
import shutil
import socket
from threading import Thread
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import psutil
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mnemion.archives import verified_archive
from mnemion.service import service_updates as updates
from mnemion.service import supervision
from mnemion.service import update_state as state_io
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.db import migrate
from mnemion.service.recovery import BACKUP_FORMAT
from mnemion.service.update_manifest import ManifestError, version_tuple
from mnemion.version import __version__
from service_tests import managed_release_fixture

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed Supervisor updates run on Unix")


@pytest.fixture
def managed_database(postgres):
    name = "managed_" + uuid4().hex
    with psycopg.connect(postgres[0], autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    admin = make_conninfo(postgres[0], dbname=name)
    migrate(admin)
    owner = bootstrap_tenant(admin, tenant_name="Managed fixture", administrator_name="Owner")
    try:
        yield (
            admin,
            make_conninfo(postgres[1], dbname=name),
            make_conninfo(postgres[2], dbname=name),
            owner,
        )
    finally:
        with psycopg.connect(postgres[0], autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def prepare_managed(tmp_path, managed_database, pg_bin):
    admin, api, worker, owner = managed_database
    credentials = tmp_path / "roles.json"
    state_io.write(
        credentials,
        {"admin_database_url": admin, "database_url": api, "worker_database_url": worker},
    )
    environment = tmp_path / "runtime.json"
    state_io.write(
        environment,
        {
            "MNEMION_MODEL_OFFLINE": "1",
            "MNEMION_MODEL_CACHE": str(tmp_path / "models"),
            "MNEMION_EVALUATIONS_DISABLED": "1",
            "MNEMION_LIBRARIAN_DISABLED": "1",
        },
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    uv = os.environ.get("MNEMION_TEST_UV") or shutil.which("uv")
    if not uv:
        pytest.fail("Managed service tests require pinned uv on PATH or MNEMION_TEST_UV")
    state = tmp_path / "managed state 20%"
    configured = updates.setup(
        state,
        credentials,
        credentials,
        credentials,
        uv=Path(uv),
        pg_bin=pg_bin,
        port=port,
        environment=environment,
    )
    assert configured["automatic_updates"] is True
    # Protocol/process tests do not poll the live release feed.
    updates.preferences(state, False)
    return state, port, owner


def test_managed_roles_restart_and_take_a_real_verified_backup(
    managed_database, pg_bin, tmp_path, monkeypatch
):
    monkeypatch.setenv("MNEMION_ADMIN_DATABASE_URL", "sentinel-must-not-reach-service-children")
    state, port, owner = prepare_managed(tmp_path, managed_database, pg_bin)
    root = state / "updates"
    assert "admin_database_url" not in state_io.read(state / "api.json")
    assert "admin_database_url" not in state_io.read(state / "worker.json")
    before = []
    try:
        status = supervision.start(state)
        assert status["ready"]
        before = [psutil.Process(item["pid"]) for item in status["processes"]]
        assert {item["name"] for item in status["processes"]} == {
            "mnemion-api",
            "mnemion-worker",
            "mnemion-updater",
        }
        for process in before:
            assert "MNEMION_ADMIN_DATABASE_URL" not in process.environ()
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            assert client.get("/v1/me").status_code == 401
            auth = {"Authorization": "Bearer " + owner["api_key"]}
            saved = client.post(
                f"/v1/spaces/{owner['space_id']}/memories",
                headers={**auth, "Idempotency-Key": "managed-update-fixture"},
                json={"content": "Keep this memory through the managed restart"},
            )
            assert saved.status_code == 202
            memory = saved.json()["memory_id"]
            active = updates.resolved_runtime(state)
            release = SimpleNamespace(
                version="4.0.8", migrations=tuple(active["migrations"].items())
            )
            name = updates._backup(root, supervision.settings(state)[1], active, release)
            with verified_archive(root / "backups" / name, BACKUP_FORMAT) as verified:
                assert verified
            updates._processes(state, start=False)
            paused = supervision.status(state)
            assert paused["running"] and not paused["ready"]
            updater = next(
                item for item in paused["processes"] if item["name"] == "mnemion-updater"
            )
            assert updater["statename"] == "RUNNING"
            updates._processes(state, start=True)
            assert client.get("/v1/me", headers=auth).status_code == 200
            recalled = client.post(
                "/v1/recall",
                headers=auth,
                json={"query": "managed restart", "all_accessible": True, "mode": "lexical"},
            )
            assert recalled.status_code == 200
            assert any(hit["memory_id"] == memory for hit in recalled.json()["hits"])
        assert supervision.stop(state)["stopped"]
        assert supervision.stop(state)["stopped"]
        for process in before:
            assert not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
    finally:
        supervision.stop(state)


@pytest.mark.skipif(
    os.environ.get("MNEMION_TEST_MANAGED_INSTALL") != "1",
    reason="Opt-in real locked runtime installation",
)
def test_signed_locked_install_and_failed_update_preserve_real_accepted_memories(
    managed_database, pg_bin, tmp_path, monkeypatch
):
    from mnemion.service import studio

    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    bootstrap = managed_release_fixture.checkout(tmp_path / "fixture bootstrap", public)
    monkeypatch.setattr(studio, "source_root", lambda: bootstrap)
    monkeypatch.setattr(updates, "SERVICE_UPDATE_PUBLIC_KEY", public)
    major, minor, patch = version_tuple(__version__)
    first, second = f"{major}.{minor}.{patch + 1}", f"{major}.{minor}.{patch + 2}"
    packages, envelope = managed_release_fixture.candidate(
        bootstrap, tmp_path / "first publisher", first, key
    )
    available = {"packages": packages, "envelope": envelope}
    monkeypatch.setattr(updates, "fetch_manifest", lambda: available["envelope"])

    def download(version, artifact, destination):
        source = available["packages"] / artifact.name
        artifact.verify_file(source)
        shutil.copyfile(source, destination)
        destination.chmod(0o600)
        artifact.verify_file(destination)

    monkeypatch.setattr(updates, "download_artifact", download)
    state, port, owner = prepare_managed(tmp_path, managed_database, pg_bin)
    worker = None
    try:
        assert supervision.start(state)["ready"]
        auth = {"Authorization": "Bearer " + owner["api_key"]}
        url = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=url, trust_env=False, timeout=5) as client:
            saved = client.post(
                f"/v1/spaces/{owner['space_id']}/memories",
                headers={**auth, "Idempotency-Key": "native-managed-before"},
                json={"content": "Preserve the original managed fixture memory"},
            )
            assert saved.status_code == 202
            first_memory = saved.json()["memory_id"]
            assert updates.check(state)["available_version"] == first
            staged = updates.stage(state)
            assert staged["automatic_compatible"]
            assert updates.apply(state)["status"] == "updated"
            active = updates.resolved_runtime(state)
            assert active["version"] == first and active["isolated"]
            running = supervision.status(state)
            assert running["ready"]
            api = next(item for item in running["processes"] if item["name"] == "mnemion-api")
            arguments = psutil.Process(api["pid"]).cmdline()
            assert arguments[0] == active["python"] and "-I" in arguments
            updater = next(
                item for item in running["processes"] if item["name"] == "mnemion-updater"
            )
            assert psutil.Process(updater["pid"]).cmdline()[0] == active["python"]
            assert client.get("/v1/me", headers=auth).status_code == 200
            # Installed code is rechecked at each handoff, not just on download.
            version_file = Path(active["package"]) / "version.py"
            original = version_file.read_bytes()
            try:
                version_file.write_bytes(original + b"\n# changed after staging\n")
                with pytest.raises(ManifestError, match="differs"):
                    updates.resolved_runtime(state)
            finally:
                version_file.write_bytes(original)
            assert updates.resolved_runtime(state)["version"] == first
            packages, envelope = managed_release_fixture.candidate(
                bootstrap, tmp_path / "second publisher", second, key, fail_worker=True
            )
            available.update(packages=packages, envelope=envelope)
            assert updates.check(state)["available_version"] == second
            assert updates.stage(state)["automatic_compatible"]
            captured = {}
            old_pid = api["pid"]

            def save_during_failed_release():
                deadline = time.monotonic() + 55
                with httpx.Client(base_url=url, trust_env=False, timeout=2) as requester:
                    while time.monotonic() < deadline:
                        try:
                            health = requester.get("/health/ready")
                            current = state_io.read(state / "updates/active.json")
                            if (
                                health.status_code == 200
                                and health.headers.get("X-Mnemion-Process") != str(old_pid)
                                and current["version"] == second
                            ):
                                result = requester.post(
                                    f"/v1/spaces/{owner['space_id']}/memories",
                                    headers={
                                        **auth,
                                        "Idempotency-Key": "native-managed-during-failure",
                                    },
                                    json={
                                        "content": "Preserve a memory accepted before candidate worker failure"
                                    },
                                )
                                if result.status_code == 202:
                                    captured["memory_id"] = result.json()["memory_id"]
                                    return
                        except (OSError, httpx.HTTPError):
                            pass
                        time.sleep(0.1)

            worker = Thread(target=save_during_failed_release, daemon=True)
            worker.start()
            with pytest.raises(ManifestError, match="previous service runtime was restored"):
                updates.apply(state)
            worker.join(timeout=60)
            assert not worker.is_alive() and "memory_id" in captured
            assert updates.resolved_runtime(state)["version"] == first
            assert supervision.status(state)["ready"]
            assert updates.apply(state)["status"] == "held_after_failure"
            result = client.post(
                "/v1/recall",
                headers=auth,
                json={"query": "Preserve memory", "all_accessible": True, "mode": "lexical"},
            )
            assert result.status_code == 200
            ids = {hit["memory_id"] for hit in result.json()["hits"]}
            assert {first_memory, captured["memory_id"]} <= ids
            assert len(list((state / "updates/backups").glob("*.zip"))) == 2
    finally:
        if worker is not None:
            worker.join(timeout=5)
        supervision.stop(state)
