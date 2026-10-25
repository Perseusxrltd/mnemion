"""Real encrypted captures wait for scans without stale settings or replay."""

import json
import os

import pytest

from mnemion.service import host_package, supervision, update_state as state_io
from mnemion.version import __version__
from service_tests.test_host_control_scan_drain import source_scan
from service_tests.test_host_recovery import host_fixture as host_fixture

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix managed host recovery")


def managed(host):
    # Add coordination records to the real prepared database/crypto fixture;
    # these tests do not stage an updater or qualify its signature verification.
    state, settings = supervision.settings(host["state"])
    state_io.write(state / "settings.json", {**settings, "managed_updates": True})
    root = state_io.directory(state / "updates")
    state_io.write(root / "active.json", {"version": __version__})
    state_io.write(root / "config.json", {"format": 1, "enabled": True})
    return root


def capture(host, kind, output, pg_bin):
    options = {"admin": host["roles"]}
    if kind == "snapshot":
        options["pg_bin"] = pg_bin
    return getattr(host_package, kind if kind == "snapshot" else "export_ledger")(
        host["state"], output, host["key_file"], **options
    )


@pytest.mark.parametrize("kind", ["snapshot", "ledger"])
def test_capture_waits_for_a_long_scan_and_reads_current_settings(
    host_fixture, pg_bin, tmp_path, monkeypatch, kind
):
    host = host_fixture
    root = managed(host)
    output = tmp_path / ("after-scan." + kind)
    announce = state_io.pause_new_connector_scans

    def update_while_waiting(root):
        owned = announce(root)
        path = host["state"] / "settings.json"
        state_io.write(
            path, {**json.loads(path.read_text()), "public_url": "https://fresh.example.com"}
        )
        return owned

    monkeypatch.setattr(state_io, "pause_new_connector_scans", update_while_waiting)
    with source_scan(monkeypatch, root, finish_after=75) as scan:
        result = capture(host, kind, output, pg_bin)
        assert scan == {"elapsed": 75.0, "finished": True}
    assert not (root / "connector-update-pending.json").exists()
    if kind == "snapshot":
        with host_package.opened(output, host["key_file"], result["sha256"]) as (recipe, _, digest):
            assert recipe["public_url"] == "https://fresh.example.com"
            assert digest == result["sha256"]
    else:
        with host_package.opened_ledger(output, host["key_file"], result["sha256"]) as (_, ledger):
            assert ledger["snapshot_at"] == result["snapshot_at"]
    assert result["off_host_delivery_verified"] is False
    with state_io.lock(root):
        pass


def test_capture_deadline_preserves_the_running_scan_and_creates_no_artifact(
    host_fixture, pg_bin, tmp_path, monkeypatch
):
    host = host_fixture
    root = managed(host)
    output = tmp_path / "deferred.mnemion-ledger"
    with source_scan(monkeypatch, root) as scan:
        with pytest.raises(state_io.OperationBusy):
            capture(host, "ledger", output, pg_bin)
        assert scan == {"elapsed": 300.0, "finished": False}
        assert not output.exists()
        with pytest.raises(state_io.OperationBusy), state_io.lock(root):
            pytest.fail("An unfinished source scan lost its lease")
    assert not (root / "connector-update-pending.json").exists()


def test_runtime_change_while_waiting_refuses_capture_before_database_work(
    host_fixture, pg_bin, tmp_path, monkeypatch
):
    host = host_fixture
    root = managed(host)
    output = tmp_path / "stale-runtime.mnemion-ledger"
    announce = state_io.pause_new_connector_scans

    def replace_runtime(root):
        owned = announce(root)
        state_io.write(root / "active.json", {"version": "0.0.0"})
        return owned

    monkeypatch.setattr(state_io, "pause_new_connector_scans", replace_runtime)
    monkeypatch.setattr(
        host_package.recovery,
        "export_ledger",
        lambda *_: pytest.fail("Stale runtime reached the database"),
    )
    with source_scan(monkeypatch, root, finish_after=1):
        with pytest.raises(host_package.HostRecoveryError, match="active host runtime"):
            capture(host, "ledger", output, pg_bin)
    assert not output.exists()
    assert not (root / "connector-update-pending.json").exists()


def test_existing_controller_lease_is_borrowed_without_another_wait(
    host_fixture, tmp_path, monkeypatch
):
    host = host_fixture
    root = managed(host)
    output = tmp_path / "borrowed.mnemion-ledger"
    # The guard detects a transition during acquisition; it must not add a
    # blanket restriction on an unchanged, compatible older host runtime.
    state_io.write(root / "active.json", {"version": "4.46.5"})
    monkeypatch.setattr(
        state_io,
        "operator_lock",
        lambda *_args, **_kwargs: pytest.fail("An existing lease must be borrowed"),
    )
    with state_io.lock(root):
        result = host_package.export_ledger(
            host["state"], output, host["key_file"], admin=host["roles"], lock_held=True
        )
        with pytest.raises(state_io.OperationBusy), state_io.lock(root):
            pytest.fail("Capture released its caller's lease")
    with host_package.opened_ledger(output, host["key_file"], result["sha256"]):
        pass


def test_a_destination_created_during_wait_is_not_overwritten(
    host_fixture, pg_bin, tmp_path, monkeypatch
):
    host = host_fixture
    root = managed(host)
    output = tmp_path / "claimed.mnemion-host"
    announce = state_io.pause_new_connector_scans

    def claim_destination(root):
        owned = announce(root)
        output.write_bytes(b"existing operator artifact")
        return owned

    monkeypatch.setattr(state_io, "pause_new_connector_scans", claim_destination)
    with source_scan(monkeypatch, root, finish_after=1):
        with pytest.raises(host_package.HostRecoveryError, match="existing files are preserved"):
            capture(host, "snapshot", output, pg_bin)
    assert output.read_bytes() == b"existing operator artifact"
