"""A release must actually contain a usable, matching web application."""

import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

import pytest

from deploy.bundle_studio import build_lock, install_bundle, verify_python_distributions
from mnemion.service import studio
from mnemion.version import __version__


def make_bundle(path, marker="fixture"):
    (path / "assets").mkdir(parents=True)
    (path / "notices").mkdir()
    (path / "index.html").write_text('<script type="module" src="/assets/app.js"></script>')
    (path / "assets/app.js").write_text(f'console.log("{marker}")')
    for name in ("LICENSE", "NOTICE", "inventory.json"):
        (path / "notices" / name).write_text("{}" if name.endswith("json") else "Fixture license")
    (path / "release.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "version": __version__,
                "base": "/",
                "files": studio.bundle_files(path),
            }
        )
    )
    return path


def distributions(root, bundle):
    wheel = root / f"mnemion-{__version__}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for item in bundle.rglob("*"):
            if item.is_file():
                archive.write(item, "mnemion/_studio/" + item.relative_to(bundle).as_posix())
    with tarfile.open(root / f"mnemion-{__version__}.tar.gz", "w:gz") as archive:
        archive.add(bundle, arcname=f"mnemion-{__version__}/mnemion/_studio")
    return wheel


def test_python_release_requires_both_matching_ui_packages(tmp_path):
    bundle = make_bundle(tmp_path / "bundle")
    wheel = distributions(tmp_path, bundle)
    assert len(verify_python_distributions(tmp_path, __version__)) == 2
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("mnemion/__init__.py", "")
    with pytest.raises(ValueError, match="incomplete"):
        verify_python_distributions(tmp_path, __version__)


@pytest.mark.parametrize(
    "fault", ["altered", "version", "relative_assets", "extra", "missing_notice"]
)
def test_bundle_integrity_rejects_unusable_or_changed_ui(tmp_path, fault):
    bundle = make_bundle(tmp_path / "bundle")
    if fault == "altered":
        (bundle / "assets/app.js").write_text("unexpected code")
    elif fault == "version":
        path = bundle / "release.json"
        value = json.loads(path.read_text())
        value["version"] = "0.0.0"
        path.write_text(json.dumps(value))
    elif fault == "extra":
        (bundle / "assets/unlisted.js").write_text("unexpected code")
    else:
        if fault == "relative_assets":
            (bundle / "index.html").write_text('<script src="./assets/app.js"></script>')
        else:
            (bundle / "notices/NOTICE").unlink()
        path = bundle / "release.json"
        value = json.loads(path.read_text())
        value["files"] = studio.bundle_files(bundle)
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        studio.validate_bundle(bundle)


@pytest.mark.parametrize("name", ["../../outside.js", "..\\outside.js", "/outside.js"])
def test_package_paths_cannot_escape_the_bundle(tmp_path, name):
    wheel = distributions(tmp_path, make_bundle(tmp_path / "bundle"))
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("mnemion/_studio/" + name, "unexpected code")
    with pytest.raises(ValueError, match="Unsafe path"):
        verify_python_distributions(tmp_path, __version__)


def test_failed_bundle_switch_preserves_the_previous_build(tmp_path, monkeypatch):
    previous = make_bundle(tmp_path / "installed", "previous")
    staged = make_bundle(tmp_path / "staging/new", "new")
    original = Path.replace

    def fail(source, target):
        if source == staged:
            raise PermissionError("fixture locked destination")
        return original(source, target)

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(PermissionError):
        install_bundle(staged, previous)
    assert '"previous"' in (previous / "assets/app.js").read_text()
    studio.validate_bundle(previous)
    monkeypatch.setattr(Path, "replace", original)
    install_bundle(staged, previous)
    assert '"new"' in (previous / "assets/app.js").read_text()
    studio.validate_bundle(previous)


def test_concurrent_builds_cannot_replace_dependencies_or_steal_the_lock(tmp_path):
    with build_lock(tmp_path):
        with pytest.raises(ValueError, match="Another Studio build"):
            with build_lock(tmp_path):
                pytest.fail("A second build acquired the same lock")
        assert (tmp_path / "web-studio.lock").is_file()
    with build_lock(tmp_path):
        pass


def test_npm_uses_js_entrypoint_without_windows_shell_quoting(tmp_path, monkeypatch):
    node = tmp_path / "Program Files/Node/node.exe"
    node.parent.mkdir(parents=True)
    entry = node.parent / "node_modules/npm/bin/npm-cli.js"
    entry.parent.mkdir(parents=True)
    entry.write_text("fixture npm entrypoint")
    monkeypatch.delenv("npm_execpath", raising=False)
    monkeypatch.setattr(
        studio.shutil,
        "which",
        lambda name: str(node if name == "node" else node.with_name("npm.cmd")),
    )

    def run(args, **kwargs):
        assert args == [str(node), "--version"] and "shell" not in kwargs
        return subprocess.CompletedProcess(args, 0, "v22.22.0\n", "")

    monkeypatch.setattr(studio.subprocess, "run", run)
    assert studio.npm_command() == [str(node), str(entry)]
