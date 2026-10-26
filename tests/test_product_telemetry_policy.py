"""Actual persistent/offline choices; these are not collector acceptance tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from mnemion.product_telemetry import policy


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "private installation"
    company = tmp_path / "machine-policy.json"
    monkeypatch.setattr(policy, "company_policy_file", lambda: company)
    return root, company


def choice(root, enabled, revision=0, disclosure=0):
    return policy.configure(
        root,
        {
            "enabled": enabled,
            "expected_revision": revision,
            "expected_generation": policy.status(root)["store_generation"],
            "disclosure_version": disclosure,
        },
    )


def test_new_installation_requires_disclosure_without_creating_files(installation):
    root, _ = installation
    state = policy.status(root)
    assert state["default_enabled"] is True
    assert state["user_enabled"] is True
    assert state["effective_enabled"] is False
    assert state["reason"] == "disclosure_required"
    assert not root.exists()
    assert policy.preview(root)["outbound_body"] is None


def test_pending_collector_cannot_be_preapproved(installation):
    root, _ = installation
    with pytest.raises(policy.PolicyError, match="telemetry_disclosure_unavailable"):
        choice(root, True, disclosure=policy.DISCLOSURE_VERSION)
    assert not root.exists()


def test_connection_choice_preserves_disclosure_and_stale_opt_out_wins(installation):
    root, _ = installation
    current = policy.configure(
        root, {"enabled": True, "expected_revision": 0, "connection_mode": "unmetered"}
    )
    assert current["connection_mode"] == "unmetered"
    assert current["disclosure_version"] == 0 and not current["effective_enabled"]
    off = policy.configure(
        root, {"enabled": False, "expected_revision": 0, "connection_mode": "metered"}
    )
    assert off["connection_mode"] == "unmetered" and off["reason"] == "user_disabled"
    retained = choice(root, True, revision=off["revision"])
    assert retained["connection_mode"] == "unmetered"
    with pytest.raises(policy.PolicyError, match="telemetry_choice_changed"):
        policy.configure(
            root,
            {
                "enabled": True,
                "expected_revision": off["revision"],
                "expected_generation": off["store_generation"],
                "connection_mode": "metered",
            },
        )


@pytest.mark.parametrize("mode", [None, True, 1, [], {}, "wifi", "PRIVATE_SENTINEL"])
def test_invalid_connection_choices_never_create_storage(installation, mode):
    root, _ = installation
    with pytest.raises(policy.PolicyError, match="^telemetry_invalid_choice$"):
        policy.configure(root, {"enabled": False, "expected_revision": 0, "connection_mode": mode})
    assert not root.exists()


def test_disable_wins_over_stale_enable_and_clears_persisted_pending(installation):
    root, _ = installation
    disabled = choice(root, False)
    assert disabled["revision"] == 1
    assert disabled["reason"] == "user_disabled"
    # This is a bounded synthetic queue, never a real event or network report.
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        connection.execute("INSERT INTO pending VALUES (7, 123, 20000)")
    repeated = choice(root, False, revision=0)
    assert repeated["revision"] == 2
    assert repeated["pending_records"] == 0
    with pytest.raises(policy.PolicyError, match="telemetry_choice_changed"):
        choice(root, True, revision=0)
    with pytest.raises(policy.PolicyError, match="telemetry_choice_changed"):
        choice(root, True, revision=1)
    enabled_preference = choice(root, True, revision=2)
    assert enabled_preference["user_enabled"] is True
    assert enabled_preference["effective_enabled"] is False
    assert enabled_preference["reason"] == "disclosure_required"
    assert enabled_preference["pending_records"] == 0
    assert (root / policy.DATABASE_NAME).stat().st_size <= policy.MAX_DATABASE_BYTES
    assert not (root / (policy.DATABASE_NAME + "-wal")).exists()


def test_explicit_opt_out_waits_for_a_brief_existing_reader(installation):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import closing
    from threading import Event
    import time

    root, _ = installation
    choice(root, True)
    ready = Event()

    def reader():
        with closing(sqlite3.connect(root / policy.DATABASE_NAME)) as db:
            db.execute("BEGIN")
            db.execute("SELECT * FROM preferences").fetchone()
            ready.set()
            time.sleep(0.05)

    with ThreadPoolExecutor(max_workers=1) as threads:
        future = threads.submit(reader)
        assert ready.wait(1)
        disabled = choice(root, False)
        future.result()
    assert disabled["reason"] == "user_disabled"


def test_choice_survives_separate_native_processes_without_desktop(tmp_path):
    root = tmp_path / "native-choice"
    command = [sys.executable, "-m", "mnemion.service.cli", "telemetry", "--root", str(root)]
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONNOUSERSITE": "1",
    }

    def invoke(request):
        response = subprocess.run(
            command,
            input=json.dumps(request) + "\n",
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        assert response.stderr == ""
        return json.loads(response.stdout)["result"]

    first = invoke({"action": "configure", "enabled": False, "expected_revision": 0})
    second = invoke({"action": "status"})
    assert first == second
    assert second["reason"] == "user_disabled"
    assert second["effective_enabled"] is False
    assert invoke({"action": "preview"})["outbound_bytes"] == 0


def test_missing_company_directory_remains_optional_and_fresh(tmp_path):
    selected = tmp_path / "new" / "nested" / "company.json"
    assert policy.company_policy(selected)["state"] == "unmanaged"
    selected.parent.mkdir(parents=True)
    selected.write_text(json.dumps({"schema_version": 1, "enabled": False, "metric_groups": []}))
    assert policy.company_policy(selected)["enabled"] is False


def test_missing_error_from_invalid_company_ancestor_is_unreadable(tmp_path, monkeypatch):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("")
    selected = blocked / "missing" / "company.json"
    original = Path.lstat

    def windows_missing(path, *args, **kwargs):
        # Windows reports ENOENT for this invalid path instead of ENOTDIR.
        if path == selected:
            raise FileNotFoundError(2, "missing", str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", windows_missing)
    assert policy.company_policy(selected) == {
        "state": "unreadable",
        "enabled": False,
        "metric_groups": [],
    }


def test_company_policy_disappearing_after_stat_is_unreadable(tmp_path, monkeypatch):
    selected = tmp_path / "company.json"
    selected.write_text(json.dumps({"schema_version": 1, "enabled": False, "metric_groups": []}))
    original = Path.open

    def remove_before_read(path, *args, **kwargs):
        if path == selected:
            path.unlink()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", remove_before_read)
    assert policy.company_policy(selected) == {
        "state": "unreadable",
        "enabled": False,
        "metric_groups": [],
    }


def test_company_policy_only_restricts_choice(installation, monkeypatch):
    root, company = installation
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    enabled = choice(root, True, disclosure=policy.DISCLOSURE_VERSION)
    assert enabled["effective_enabled"] is True
    company.write_text(
        json.dumps({"schema_version": 1, "enabled": False, "metric_groups": ["usage"]})
    )
    assert policy.status(root)["reason"] == "company_policy"
    disabled = choice(root, False, enabled["revision"])
    company.write_text(
        json.dumps({"schema_version": 1, "enabled": True, "metric_groups": ["usage"]})
    )
    assert policy.status(root)["reason"] == "user_disabled"
    company.unlink()
    assert policy.status(root)["user_enabled"] is False
    assert disabled["pending_records"] == 0


def test_unknown_company_fields_and_damaged_preferences_fail_closed(installation):
    root, company = installation
    choice(root, False)
    company.write_text(
        '{"schema_version":1,"enabled":true,"metric_groups":["usage"],"token":"PRIVATE_SENTINEL"}'
    )
    current = policy.status(root)
    assert current["company_policy"]["state"] == "unreadable"
    assert "PRIVATE_SENTINEL" not in json.dumps(current)
    path = root / policy.DATABASE_NAME
    path.write_bytes(b"damaged private data PRIVATE_SENTINEL")
    current = policy.status(root)
    assert current["effective_enabled"] is False
    assert current["storage"] == "unreadable"
    assert current["pending_records"] is None
    assert "PRIVATE_SENTINEL" not in json.dumps(current)
    assert path.read_bytes() == b"damaged private data PRIVATE_SENTINEL"


def test_unknown_input_does_not_enter_disk_or_public_error(installation):
    root, _ = installation
    with pytest.raises(policy.PolicyError) as error:
        policy.configure(
            root, {"enabled": False, "expected_revision": 0, "workspace": "PRIVATE_SENTINEL"}
        )
    assert str(error.value) == "telemetry_invalid_choice"
    assert not root.exists()


def test_future_or_corrupt_disclosure_cannot_emit(installation):
    root, _ = installation
    choice(root, False)
    with sqlite3.connect(root / policy.DATABASE_NAME) as connection:
        connection.execute("UPDATE preferences SET enabled=1, disclosure_version=1000000")
    current = policy.status(root)
    assert current["effective_enabled"] is False
    assert current["reason"] == "storage_unavailable"


def test_browser_page_receives_only_restrictive_machine_policy(installation):
    from html import unescape
    from mnemion.service.studio_policy import product_telemetry_page

    _, company = installation
    company.write_text(json.dumps({"schema_version": 1, "enabled": False, "metric_groups": []}))
    rendered = product_telemetry_page("<html><head></head><body>Existing app</body></html>")
    assert 'name="mnemion-product-telemetry-policy"' in rendered
    payload = unescape(rendered.split('content="', 1)[1].split('"', 1)[0])
    assert json.loads(payload) == {"state": "restricted", "enabled": False, "metric_groups": []}
    assert "<body>Existing app</body>" in rendered
    company.write_text('{"enabled":true,"key":"PRIVATE_SENTINEL"}')
    assert "PRIVATE_SENTINEL" not in product_telemetry_page("<head></head>")


@pytest.mark.skipif(os.name == "nt", reason="Unix ownership/mode boundary")
def test_other_user_readable_store_and_symlink_are_not_adopted(installation, tmp_path):
    root, _ = installation
    choice(root, False)
    path = root / policy.DATABASE_NAME
    path.chmod(0o644)
    assert policy.status(root)["reason"] == "storage_unavailable"
    path.chmod(0o600)
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    assert policy.status(linked)["reason"] == "storage_unavailable"
    assert policy.status(root)["reason"] == "user_disabled"
