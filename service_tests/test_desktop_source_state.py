import base64
import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mnemion import desktop_sources as sources
from mnemion.local_state import LocalSetupError


def source(tmp_path, **values):
    return sources.Source(
        **{
            "id": uuid4(),
            "endpoint": "https://memory.example.invalid",
            "tenant_id": uuid4(),
            "connector_id": uuid4(),
            "principal_id": uuid4(),
            "name": "Selected folder",
            "provider": "filesystem",
            "path": str(tmp_path / "vault"),
            "members": ["employee:alice"],
            "publish_to_mapped_members": True,
            **values,
        }
    )


def test_settings_reopen_private_compare_revision_and_retain_original_on_failure(tmp_path):
    root = tmp_path / "private"
    value = source(tmp_path).model_dump(mode="json")
    value["sealed_key"] = base64.b64encode(os.urandom(96)).decode()
    initial = sources.load(root)
    assert initial.sources == []
    saved = sources.store(root, initial.revision, [value])
    assert sources.load(root).model_dump(mode="json", exclude_none=True) == saved
    before = (root / "sources.json").read_bytes()
    with pytest.raises(LocalSetupError, match="settings changed"):
        sources.store(root, initial.revision, [])
    with pytest.raises(ValidationError):
        sources.store(root, saved["revision"], [{**value, "credential": "private-fixture-key"}])
    with pytest.raises(ValidationError):
        sources.store(root, saved["revision"], [value, {**value, "id": str(uuid4())}])
    assert (root / "sources.json").read_bytes() == before
    if os.name != "nt":
        assert (root.stat().st_mode & 0o077) == 0
        assert ((root / "sources.json").stat().st_mode & 0o077) == 0
    (root / "sources.json").write_bytes(b"damaged")
    with pytest.raises(LocalSetupError):
        sources.store(root, saved["revision"], [])
    assert (root / "sources.json").read_bytes() == b"damaged"


def test_source_folder_never_ingests_private_app_state_or_follows_replaced_link(tmp_path):
    root = tmp_path / "source-control"
    root.mkdir()
    app = tmp_path / "application"
    app.mkdir()
    private_file = app / "connections.json"
    private_file.write_text("private fixture")
    vault = tmp_path / "vault"
    vault.mkdir()
    good = source(tmp_path)
    assert sources.source_folder(good, root, [app]) == vault
    for path in (root, app, tmp_path):
        with pytest.raises(ValueError):
            sources.source_folder(source(tmp_path, path=str(path)), root, [app])
    assert private_file.read_text() == "private fixture"
    if os.name != "nt":
        vault.rmdir()
        vault.symlink_to(app, target_is_directory=True)
        with pytest.raises(ValueError):
            sources.source_folder(good, root, [app])


@pytest.mark.parametrize(
    "value",
    [
        "http://company.invalid",
        "https://user:password@example.org",
        "https://example.org/?key=private",
    ],
)
def test_plaintext_remote_addresses_and_embedded_credentials_are_refused(tmp_path, value):
    with pytest.raises(ValidationError):
        source(tmp_path, endpoint=value)


def test_source_types_are_bounded_and_keep_established_safe_exclusions(tmp_path):
    for values in (
        {"memory_limit_mib": 1},
        {"poll_seconds": 0},
        {"max_files": 100001},
        {"provider": "shell"},
        {"publish_to_mapped_members": False},
    ):
        with pytest.raises(ValidationError):
            source(tmp_path, **values)
    config = source(tmp_path).connector(tmp_path / "capture")
    assert "*.pem" in config.provider.exclude and ".env*" in config.provider.exclude
    assert config.provider.max_file_bytes <= 20_000_000
    conversation = source(tmp_path, provider="conversations").connector(tmp_path / "capture")
    assert conversation.provider.normalize_conversations
    assert conversation.provider.state_directory == tmp_path / "capture"
    assert conversation.provider.max_scan_seconds == 60
    assert config.service_token.model_dump(exclude_none=True) == {
        "env": "MNEMION_DESKTOP_SOURCE_UNUSED"
    }


def test_actual_source_process_stops_at_its_measured_ram_allowance(tmp_path):
    request = {
        "operation": "scan",
        "source": source(tmp_path, memory_limit_mib=128).model_dump(mode="json"),
        "credential": "unused-private-fixture-credential",
    }
    # Exercise the real process/RSS monitor with bounded actual allocation.
    # The slow source has no network, model or user-file side effects.
    code = """
import time
from pathlib import Path
from types import SimpleNamespace
from mnemion import desktop_sources as source
def allocate(*args):
    buffer = bytearray(160 * 1024 * 1024)
    time.sleep(8)
    return {"unexpected_completion": len(buffer)}
source.perform = allocate
raise SystemExit(source.dispatch(SimpleNamespace(root=Path('.'), private_root=[])))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(request),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )
    assert result.returncode == 2
    final = json.loads(result.stdout.splitlines()[-1])
    assert final == {"event": "result", "ok": False, "error": "source_memory_limit"}
    assert request["credential"] not in result.stdout + result.stderr
