"""Compiler reuse must not cross inputs, host images or approved dependencies."""

from contextlib import contextmanager
import copy
import json
from pathlib import Path

import pytest
import yaml

from deploy.native_database_cache import INPUTS, cache_key
from deploy import probe_native_postgres

ROOT = Path(__file__).resolve().parents[1]
HOST = {
    "target": "linux",
    "architecture": "x64",
    "image_os": "ubuntu22",
    "image_version": "20261012.1.0",
    "python_version": "3.12.13",
}


@pytest.fixture
def inputs(tmp_path):
    for name in INPUTS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic compiler input: " + name)
    return tmp_path


@pytest.mark.parametrize("name", INPUTS)
def test_each_compiler_input_change_invalidates_the_archive_key(inputs, name):
    original = cache_key(inputs, **HOST)
    assert original and cache_key(inputs, **HOST) == original
    changed = inputs / name
    changed.write_text(changed.read_text() + "\nchanged")
    assert cache_key(inputs, **HOST) != original


@pytest.mark.parametrize(
    "field,value",
    [
        ("target", "macos"),
        ("architecture", "arm64"),
        ("image_os", "ubuntu24"),
        ("image_version", "20261013.1.0"),
        ("python_version", "3.12.14"),
    ],
)
def test_native_cache_cannot_cross_architecture_or_compiler_images(inputs, field, value):
    assert cache_key(inputs, **HOST) != cache_key(inputs, **{**HOST, field: value})


@pytest.mark.parametrize("value", ["", None, "unknown/image", "image\nkey=injected", "x" * 129])
def test_unknown_image_metadata_chooses_a_fresh_compile(inputs, value):
    assert cache_key(inputs, **{**HOST, "image_version": value}) is None


def test_linked_compiler_inputs_are_not_hashed_as_repository_files(inputs, tmp_path):
    external = tmp_path / "external"
    external.write_text("outside the approved compiler inputs")
    path = inputs / INPUTS[0]
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(ValueError, match="ordinary repository file"):
        cache_key(inputs, **HOST)


@pytest.mark.parametrize("mutation", ["version", "sha256", "url", "missing", "extra"])
def test_cached_dependency_changes_fail_before_a_native_executable_is_inspected(
    monkeypatch, tmp_path, mutation
):
    configuration = json.loads((ROOT / "deploy/native-postgres.json").read_text())
    metadata = {
        "sources": {
            name: configuration[name] for name in ("postgresql", "pgvector", "openssl", "zlib")
        }
    }
    probe_native_postgres.verify_database_sources(metadata)
    changed = copy.deepcopy(metadata)
    if mutation == "missing":
        del changed["sources"]["openssl"]
    elif mutation == "extra":
        changed["sources"]["unexpected"] = {}
    else:
        changed["sources"]["openssl"][mutation] = "changed"

    @contextmanager
    def directory():
        yield tmp_path

    monkeypatch.setattr(probe_native_postgres, "private_probe_directory", directory)
    monkeypatch.setattr(probe_native_postgres, "expand", lambda *_: changed)
    monkeypatch.setattr(
        probe_native_postgres,
        "executable_architecture",
        lambda *_: pytest.fail("Unapproved cached binaries must not reach executable inspection"),
    )
    with pytest.raises(ValueError, match="current pinned configuration"):
        probe_native_postgres.probe(tmp_path / "unused.zip", tmp_path / "unused.json")


def test_native_database_changes_still_trigger_the_complete_desktop_gate():
    desktop = yaml.load(
        (ROOT / ".github/workflows/desktop.yml").read_text(), Loader=yaml.BaseLoader
    )
    native = yaml.load(
        (ROOT / ".github/workflows/native-runtime.yml").read_text(), Loader=yaml.BaseLoader
    )
    release = yaml.load(
        (ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert desktop["jobs"]["native_database"]["uses"] == "./.github/workflows/native-runtime.yml"
    assert set(native["on"]) == {"workflow_call", "workflow_dispatch"}
    assert set(desktop["on"]) == {"pull_request", "workflow_call", "workflow_dispatch"}
    assert desktop["on"]["pull_request"] == {"branches": ["main"]}
    assert release["jobs"]["native"]["uses"] == "./.github/workflows/desktop.yml"
    assert release["jobs"]["native"]["with"]["release"] == "true"
