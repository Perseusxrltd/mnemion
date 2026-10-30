"""The diagnostic bake refuses every destination that is not the loopback fixture."""

import inspect
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from deploy.telemetry_installed_fixture import baked_documents, validate_loopback_target


DISCLOSURE = {
    "version": 2,
    "collection_available": False,
    "destination": None,
}
ROUTE = {"version": 2, "address": None, "certificate_authorities": []}
CERTIFICATE = "-----BEGIN CERTIFICATE-----\nQUJD\n-----END CERTIFICATE-----\n"


def test_loopback_bake_changes_only_availability_and_route():
    disclosure, route = baked_documents(
        DISCLOSURE, ROUTE, "https://localhost:8443/v3/report", "127.0.0.1", CERTIFICATE
    )
    assert disclosure["collection_available"] is True
    assert disclosure["destination"] == "https://localhost:8443/v3/report"
    assert disclosure["version"] == 2
    assert route == {
        "version": 2,
        "address": "127.0.0.1",
        "certificate_authorities": [CERTIFICATE],
    }


@pytest.mark.parametrize(
    "destination,address",
    [
        ("https://example.com/v3/report", "127.0.0.1"),
        ("https://127.0.0.1:8443/v3/report", "127.0.0.1"),
        ("http://localhost:8443/v3/report", "127.0.0.1"),
        ("https://localhost/v3/report", "127.0.0.1"),
        ("https://localhost:8443/v1/report", "127.0.0.1"),
        ("https://user:pass@localhost:8443/v3/report", "127.0.0.1"),
        ("https://localhost:8443/v3/report?x=1", "127.0.0.1"),
        ("https://localhost:8443/v3/report", "8.8.8.8"),
        ("https://localhost:8443/v3/report", "::1"),
    ],
)
def test_non_loopback_targets_fail_closed(destination, address):
    with pytest.raises(ValueError):
        validate_loopback_target(destination, address, CERTIFICATE)


def test_shared_loopback_destination_uses_the_fixed_port():
    from deploy.telemetry_installed_fixture import LOOPBACK_PORT, loopback_destination

    destination = loopback_destination()
    assert destination == f"https://localhost:{LOOPBACK_PORT}/v3/report"
    validate_loopback_target(destination, "127.0.0.1", CERTIFICATE)


def test_private_key_material_is_refused():
    from deploy.telemetry_installed_fixture import assert_public_certificate

    private = "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END PRIVATE KEY-----\n"
    with pytest.raises(ValueError):
        assert_public_certificate(private)
    with pytest.raises(ValueError):
        validate_loopback_target("https://localhost:48763/v3/report", "127.0.0.1", private)


def test_active_production_disclosure_is_refused(tmp_path: Path):
    copy = tmp_path / "copy"
    target = copy / "mnemion/product_telemetry"
    target.mkdir(parents=True)
    (target / "disclosure.json").write_text(
        json.dumps({**DISCLOSURE, "collection_available": True}), encoding="utf-8"
    )
    (target / "transport-route.json").write_text(json.dumps(ROUTE), encoding="utf-8")
    package = copy / "studio/electron"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps(
            {"main": "dist/main.js", "scripts": {"dist": "electron-builder --publish never"}}
        ),
        encoding="utf-8",
    )
    from deploy.telemetry_installed_fixture import write_bake

    with pytest.raises(ValueError, match="Production disclosure"):
        write_bake(copy, "https://localhost:8443/v3/report", "127.0.0.1", CERTIFICATE)


def test_cli_requires_the_shared_loopback_material(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["probe_telemetry_installed", "--source", "source", "--output", "output"]
    )
    from deploy.probe_telemetry_installed import main

    with pytest.raises(SystemExit):
        main()


def test_loopback_material_keeps_the_private_key_separate(tmp_path: Path):
    from deploy.probe_telemetry_installed import _key_stays_outside, _require_loopback_material

    material = tmp_path / "loopback"
    material.mkdir()
    (material / "certificate.pem").write_text(CERTIFICATE, encoding="utf-8")
    (material / "key.pem").write_text(
        "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END PRIVATE KEY-----\n", encoding="utf-8"
    )
    certificate, key, public = _require_loopback_material(material)
    assert certificate.name == "certificate.pem"
    assert "PRIVATE KEY" not in public
    _key_stays_outside(key, tmp_path / "evidence")
    with pytest.raises(RuntimeError, match="outside"):
        _key_stays_outside(key, material)
    (material / "key.pem").write_text(CERTIFICATE, encoding="utf-8")
    with pytest.raises(RuntimeError, match="separate"):
        _require_loopback_material(material)


def test_build_environment_is_captured_before_the_memory_fixture():
    from deploy import probe_telemetry_installed as driver

    source = inspect.getsource(driver._serve)
    assert source.index("environment = _build_env(source)") < source.index("memory_workspace(")
    assert "tempfile.mkdtemp" not in source
    assert "ignore_errors=True" not in source


def test_captured_build_environment_survives_fixture_isolation(monkeypatch, tmp_path: Path):
    archive = tmp_path / "pg"
    engine = tmp_path / "python"
    monkeypatch.setenv("MNEMION_POSTGRES_ARCHIVES", str(archive))
    monkeypatch.setenv("MNEMION_ENGINE_PYTHON", str(engine))
    monkeypatch.setenv("MNEMION_BUILD_PYTHON", str(tmp_path / "build-python"))
    monkeypatch.setenv("MNEMION_TELEMETRY_FIXTURE_KEY", "not-for-the-package")
    if sys.platform == "win32":
        monkeypatch.setenv("MNEMION_ENGINE_ARCHIVES", str(tmp_path / "engine"))
    from deploy.probe_telemetry_installed import _build_env

    captured = _build_env(tmp_path)
    monkeypatch.delenv("MNEMION_POSTGRES_ARCHIVES", raising=False)
    monkeypatch.delenv("MNEMION_ENGINE_PYTHON", raising=False)
    monkeypatch.delenv("MNEMION_ENGINE_ARCHIVES", raising=False)
    assert captured["MNEMION_POSTGRES_ARCHIVES"] == str(archive)
    assert captured["MNEMION_ENGINE_PYTHON"] == str(engine)
    assert "MNEMION_TELEMETRY_FIXTURE_KEY" not in captured
    assert os.environ.get("MNEMION_POSTGRES_ARCHIVES") is None


def test_copy_declared_source_keeps_tracked_bytes_and_refuses_a_dirty_tree(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.check_call(["git", "init"], cwd=source)
    script = source / "tool.sh"
    payload = b"#!/bin/sh\necho ok\n"
    script.write_bytes(payload)
    if os.name != "nt":
        script.chmod(0o755)
    subprocess.check_call(["git", "add", "tool.sh"], cwd=source)
    subprocess.check_call(
        [
            "git",
            "-c",
            "user.email=probe@example.com",
            "-c",
            "user.name=probe",
            "commit",
            "-m",
            "init",
        ],
        cwd=source,
    )
    destination = tmp_path / "copy"
    destination.mkdir()
    from deploy.probe_telemetry_installed import copy_declared_source

    copied = copy_declared_source(source, destination)
    assert (destination / "tool.sh").read_bytes() == payload
    if os.name != "nt":
        assert stat.S_IMODE((destination / "tool.sh").stat().st_mode) == 0o755
    assert len(copied["tracked_sha256"]) == 64
    (source / "tool.sh").write_bytes(payload + b"\n")
    with pytest.raises(RuntimeError, match="clean tracked checkout"):
        copy_declared_source(source, tmp_path / "again")


def test_logged_command_timeout_kills_the_process(tmp_path: Path):
    from deploy.probe_telemetry_installed import _run_logged

    log_path = tmp_path / "command.log"
    with pytest.raises(TimeoutError, match="finite timeout"):
        _run_logged(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path,
            os.environ.copy(),
            log_path,
            1,
        )


def test_native_cluster_cleanup_does_not_hide_a_live_postmaster(tmp_path: Path):
    pytest.importorskip("uvicorn")
    from deploy.telemetry_memory_fixture import _NativeCluster

    data = tmp_path / "data"
    data.mkdir()
    (data / "postmaster.pid").write_text("1\n", encoding="utf-8")
    cluster = _NativeCluster(tmp_path, data, tmp_path, 1, {})
    cluster.run = lambda *args, **kwargs: None
    with pytest.raises(RuntimeError, match="remained running"):
        cluster.cleanup()


def test_native_cluster_cleanup_reports_a_failed_stop_after_exit(tmp_path: Path):
    pytest.importorskip("uvicorn")
    from deploy.telemetry_memory_fixture import _NativeCluster

    data = tmp_path / "data"
    data.mkdir()
    cluster = _NativeCluster(tmp_path, data, tmp_path, 1, {})

    def fail(*args, **kwargs):
        raise RuntimeError("pg_ctl failed")

    cluster.run = fail
    with pytest.raises(RuntimeError, match="stop failed"):
        cluster.cleanup()
