"""Managed updates use real PostgreSQL, isolated credentials and live processes."""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
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
from mnemion.connectors import managed as managed_connectors
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
            "MNEMION_API_DOCS": "1",
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


def assert_installed_process(pid, runtime, module):
    process = psutil.Process(pid)
    arguments = process.cmdline()
    assert arguments[1:4] == ["-I", "-m", module]
    assert Path(process.cwd()).resolve() == Path(runtime["directory"]).resolve()
    executables = {Path(runtime["python"]).resolve()}
    if sys.platform == "darwin":
        # Framework Python re-execs its app launcher while keeping the venv.
        executables.add(
            (Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python").resolve()
        )
    assert Path(arguments[0]).resolve() in executables


def connector_fixture(client, auth, owner, state, tmp_path):
    person = client.post("/v1/principals", headers=auth, json={"name": "Managed source fixture"})
    assert person.status_code == 201
    principal = person.json()["id"]
    key = client.post(
        f"/v1/principals/{principal}/keys", headers=auth, json={"name": "Source only"}
    )
    assert key.status_code == 201
    token = tmp_path / "connector.token"
    token.write_text(key.json()["api_key"])
    token.chmod(0o600)
    connector = client.post(
        "/v1/connectors",
        headers=auth,
        json={
            "name": "Managed filesystem fixture",
            "provider": "filesystem",
            "principal_id": principal,
            "access_mode": "published",
        },
    )
    assert connector.status_code == 201
    identifier = connector.json()["id"]
    binding = client.put(
        f"/v1/connectors/{identifier}/bindings",
        headers=auth,
        json={
            "external_id": "employee:fixture",
            "principal_id": owner["principal_id"],
            "role": "reviewer",
        },
    )
    assert binding.status_code == 200
    notes = tmp_path / "source notes"
    notes.mkdir()
    (notes / "kept.md").write_text("managedconnectorfixtureanchor Keep this source across patches.")
    (notes / "removed.md").write_text(
        "managedconnectorfixtureanchor Withdraw this source after rollback."
    )
    config = tmp_path / "source.json"
    state_io.write(
        config,
        {
            "service_url": str(client.base_url).rstrip("/"),
            "connector_id": identifier,
            "service_token": {"file": "connector.token"},
            "remote_sync": False,
            "provider": {
                "type": "filesystem",
                "path": "source notes",
                "scope_id": "fixture",
                "name": "Fixture source",
                "members": ["employee:fixture"],
                "publish_to_mapped_members": True,
            },
        },
    )
    root = state / "updates"
    registry = state_io.directory(root / "connectors")
    entry = state_io.directory(registry / identifier)
    return SimpleNamespace(
        path=config,
        notes=notes,
        root=root,
        entry=entry,
        identifier=identifier,
        original=config.read_bytes(),
    )


def connector_scan(fixture, state, version, client, auth):
    observation = managed_connectors.Observation(fixture.entry, fixture.identifier)
    with state_io.lock(fixture.entry) as singleton:
        code = managed_connectors._scan(
            state,
            fixture.root,
            managed_connectors._configuration(fixture.path),
            fixture.entry,
            singleton,
            observation,
            managed_connectors.Control(),
        )
    assert code == 0 and observation.value["scan_version"] == version
    assert fixture.path.read_bytes() == fixture.original
    found = client.post(
        "/v1/recall",
        headers=auth,
        json={
            "query": "managedconnectorfixtureanchor",
            "all_accessible": True,
            "mode": "lexical",
        },
    )
    assert found.status_code == 200
    return {hit["memory_id"] for hit in found.json()["hits"]}


def assert_connector_handoff(bootstrap, source, state, active):
    with (source.entry / "handoff-test.log").open("wb") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mnemion.connectors.runner",
                "--config",
                str(source.path),
                "--watch",
                "--managed-state",
                str(state),
            ],
            cwd=bootstrap,
            env=updates._environment(),
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                assert process.poll() is None, (
                    "Managed connector exited before its verified handoff"
                )
                rows = managed_connectors.status(source.root)["items"]
                row = next(item for item in rows if item["connector_id"] == source.identifier)
                if (
                    row.get("launcher_version") == active["version"]
                    and row["state"] == "waiting"
                    and row.get("last_exit_code") == 0
                ):
                    break
                time.sleep(0.25)
            else:
                pytest.fail("Managed connector did not finish its verified runtime handoff")
            assert_installed_process(process.pid, active, "mnemion.connectors.runner")
            assert "MNEMION_ADMIN_DATABASE_URL" not in psutil.Process(process.pid).environ()
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        assert process.returncode == 0
        assert managed_connectors.status(source.root)["items"][0]["state"] == "stopped"


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
        updates._processes(state, start=False, updater_only=True)
        paused_updater = supervision.status(state)
        assert paused_updater["service_ready"] and not paused_updater["ready"]
        updates._processes(state, start=True, service_only=True)
        updates._processes(state, start=True, updater_only=True)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            assert client.get("/v1/me").status_code == 401
            auth = {"Authorization": "Bearer " + owner["api_key"]}
            source = connector_fixture(client, auth, owner, state, tmp_path)
            source_ids = connector_scan(source, state, __version__, client, auth)
            assert len(source_ids) == 2
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
            assert connector_scan(source, state, __version__, client, auth) == source_ids
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
def test_signed_operator_upgrade_runs_real_candidate_migration_and_keeps_enrolled_sources(
    managed_database, pg_bin, tmp_path, monkeypatch
):
    from mnemion.service import managed_upgrade, studio

    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    bootstrap = managed_release_fixture.checkout(tmp_path / "fixture bootstrap", public)
    monkeypatch.setattr(studio, "source_root", lambda: bootstrap)
    monkeypatch.setattr(updates, "SERVICE_UPDATE_PUBLIC_KEY", public)
    major, minor, _ = version_tuple(__version__)
    target = f"{major}.{minor + 1}.0"
    next_migration = 1 + max(
        int(path.name.split("_", 1)[0])
        for path in (bootstrap / "mnemion/service/migrations").glob("*.sql")
    )
    fixture_migration = f"{next_migration:03d}_managed_fixture.sql"
    packages, envelope = managed_release_fixture.candidate(
        bootstrap,
        tmp_path / "operator publisher",
        target,
        key,
        extra_migrations={
            fixture_migration: "CREATE TABLE mnemion.managed_upgrade_fixture (value integer PRIMARY KEY);\n"
        },
    )
    monkeypatch.setattr(updates, "fetch_manifest", lambda: envelope)

    def download(version, artifact, destination):
        source = packages / artifact.name
        artifact.verify_file(source)
        shutil.copyfile(source, destination)
        destination.chmod(0o600)
        artifact.verify_file(destination)

    monkeypatch.setattr(updates, "download_artifact", download)
    state, port, owner = prepare_managed(tmp_path, managed_database, pg_bin)
    try:
        assert supervision.start(state)["ready"]
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5
        ) as client:
            auth = {"Authorization": "Bearer " + owner["api_key"]}
            source = connector_fixture(client, auth, owner, state, tmp_path)
            source_ids = connector_scan(source, state, __version__, client, auth)
            assert len(source_ids) == 2
            assert managed_upgrade.plan(state)["migrations"] == [fixture_migration]
            outcome = managed_upgrade.upgrade(state, version=target, allow_migration=True)
            assert outcome["status"] == "upgraded" and outcome["database_restored"] is False
            active = updates.resolved_runtime(state)
            assert active["version"] == target
            assert supervision.status(state)["ready"]
            assert client.get("/v1/me", headers=auth).status_code == 200
            assert connector_scan(source, state, target, client, auth) == source_ids
            with psycopg.connect(managed_database[0]) as connection:
                assert connection.execute(
                    "SELECT to_regclass('mnemion.managed_upgrade_fixture')"
                ).fetchone()[0]
            assert not (state / "updates/upgrade-journal.json").exists()
    finally:
        supervision.stop(state)


@pytest.mark.skipif(
    os.environ.get("MNEMION_TEST_MANAGED_INSTALL") != "1",
    reason="Opt-in real locked runtime installation",
)
@pytest.mark.parametrize("legacy_previous", [False, True])
def test_signed_locked_install_and_failed_update_preserve_real_accepted_memories(
    managed_database, pg_bin, tmp_path, monkeypatch, legacy_previous
):
    from mnemion.service import studio

    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    bootstrap = managed_release_fixture.checkout(tmp_path / "fixture bootstrap", public)
    monkeypatch.setattr(studio, "source_root", lambda: bootstrap)
    monkeypatch.setattr(updates, "SERVICE_UPDATE_PUBLIC_KEY", public)
    major, minor, patch = version_tuple(__version__)
    # Keep the legacy-readiness patch path, and exercise a same-schema minor
    # upgrade plus failed following patch with the current installed protocol.
    first, second = (
        (f"{major}.{minor}.{patch + 1}", f"{major}.{minor}.{patch + 2}")
        if legacy_previous
        else (f"{major}.{minor + 1}.0", f"{major}.{minor + 1}.1")
    )
    packages, envelope = managed_release_fixture.candidate(
        bootstrap, tmp_path / "first publisher", first, key, legacy_readiness=legacy_previous
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
        # These assertions span deliberate listener replacements and idle connector
        # handoffs. Use fresh connections rather than reusing that fixture's pool.
        with httpx.Client(
            base_url=url,
            trust_env=False,
            timeout=5,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            source = connector_fixture(client, auth, owner, state, tmp_path)
            source_ids = connector_scan(source, state, __version__, client, auth)
            assert len(source_ids) == 2
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
            assert active["readiness_protocol"] == (0 if legacy_previous else 1)
            assert active["connector_protocol"] == 1
            assert connector_scan(source, state, first, client, auth) == source_ids
            assert_connector_handoff(bootstrap, source, state, active)
            running = supervision.status(state)
            assert running["ready"]
            assert running["children_initialized"] is (None if legacy_previous else True)
            api = next(item for item in running["processes"] if item["name"] == "mnemion-api")
            assert_installed_process(api["pid"], active, "mnemion.service.cli")
            schema = client.get("/openapi.json")
            assert schema.status_code == 200 and schema.json()["info"]["version"] == first
            updater = next(
                item for item in running["processes"] if item["name"] == "mnemion-updater"
            )
            assert_installed_process(updater["pid"], active, "mnemion.service.service_updates")
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
            assert supervision.status(state)["children_initialized"] is (
                None if legacy_previous else True
            )
            assert client.get("/openapi.json").json()["info"]["version"] == first
            (source.notes / "removed.md").unlink()
            remaining_sources = connector_scan(source, state, first, client, auth)
            assert len(remaining_sources) == 1 and remaining_sources < source_ids
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
