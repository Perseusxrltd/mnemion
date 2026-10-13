"""Prepare or refresh a draft without modifying a published GitHub release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import quote, urlsplit


def publication_notes(notes: Path, root: Path, repo: str, version: str) -> str:
    """Keep repository-relative documentation links usable on GitHub Releases."""

    def replace(match: re.Match[str]) -> str:
        target = urlsplit(match.group(1))
        path = (notes.parent / target.path).resolve()
        relative = path.relative_to(root.resolve())
        if not path.is_file():
            raise ValueError(f"Release documentation does not exist: {relative}")
        # Instructions stay tied to their release; changing availability and
        # plans must lead readers to the continuously maintained documents.
        ref = (
            "main"
            if relative.as_posix()
            in {"docs/RELEASE_STATUS.md", "docs/ROADMAP.md", "docs/PRODUCT_REQUIREMENTS.md"}
            else f"v{version}"
        )
        url = f"https://github.com/{repo}/blob/{ref}/{quote(relative.as_posix())}"
        if target.fragment:
            url += "#" + target.fragment
        return f"]({url})"

    return re.sub(r"\]\((\.\.?/[^)\s]+)\)", replace, notes.read_text(encoding="utf-8"))


def gh(*arguments: str) -> str:
    result = subprocess.run(["gh", *arguments], capture_output=True, text=True, check=False)
    if result.returncode:
        # Do not mistake an API/authentication failure for a missing release.
        raise RuntimeError(f"GitHub command failed ({result.returncode}); draft retained")
    return result.stdout


def prepare(repo: str, commit: str, version: str, artifacts: Path, notes: Path) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Expected an owner/repository")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Use the full reviewed commit SHA")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a stable version")
    files = sorted(artifacts.iterdir())
    if not files or any(
        path.is_symlink()
        or not path.is_file()
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}", path.name)
        for path in files
    ):
        raise ValueError("Release assets must be regular files with safe names")
    if not notes.is_file():
        raise ValueError("Release notes are required")
    expected = {}
    for path in files:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        expected[path.name] = (path.stat().st_size, f"sha256:{digest}")

    tag = f"v{version}"
    endpoint = f"repos/{repo}/releases"
    # The tag endpoint does not find a draft whose Git tag is not created yet.
    pages = json.loads(gh("api", "--paginate", "--slurp", f"{endpoint}?per_page=100"))
    matches = [release for page in pages for release in page if release["tag_name"] == tag]
    if len(matches) > 1:
        raise RuntimeError("Multiple releases use this version; refusing to modify them")
    if matches and matches[0].get("draft") is not True:
        raise RuntimeError("Published releases are immutable; use a new patch version")
    if not matches:
        gh(
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--draft",
            "--target",
            commit,
            "--title",
            f"Mnemion {version}",
            "--notes-file",
            str(notes.resolve()),
        )
        release_id = json.loads(gh("release", "view", tag, "--repo", repo, "--json", "databaseId"))[
            "databaseId"
        ]
    else:
        release_id = matches[0]["id"]

    def draft() -> dict:
        current = json.loads(gh("api", f"{endpoint}/{release_id}"))
        if current.get("draft") is not True or current.get("tag_name") != tag:
            raise RuntimeError("Release is no longer the expected draft; stopping")
        return current

    draft()
    gh(
        "release",
        "edit",
        tag,
        "--repo",
        repo,
        "--draft",
        "--target",
        commit,
        "--title",
        f"Mnemion {version}",
        "--notes-file",
        str(notes.resolve()),
    )
    draft()
    gh("release", "upload", tag, "--repo", repo, "--clobber", *map(str, files))
    # Remove stale draft manifests only after the replacement upload succeeds.
    # Every mutation checks draft status; the workflow also serializes assembly.
    for asset in draft()["assets"]:
        if asset["name"] not in expected:
            draft()
            gh("release", "delete-asset", tag, asset["name"], "--repo", repo, "--yes")
    final = draft()
    if final.get("target_commitish") != commit:
        raise RuntimeError("Draft target does not match the reviewed commit")
    if {asset["name"] for asset in final["assets"]} != set(expected):
        raise RuntimeError("Draft asset inventory does not match the verified build")
    for asset in final["assets"]:
        size, digest = expected[asset["name"]]
        if asset.get("size") != size or (
            asset.get("digest") is not None and asset["digest"] != digest
        ):
            raise RuntimeError("Uploaded draft asset differs from the verified build")
    print(f"Prepared {tag} at {commit}: {len(files)} assets; still a draft")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [sys.executable, str(root / "deploy/release.py"), "--artifacts", str(args.artifacts)],
        check=True,
    )
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    with tempfile.TemporaryDirectory(prefix="mnemion-release-notes-") as directory:
        notes = Path(directory) / "release.md"
        notes.write_text(
            publication_notes(
                root / "docs" / "releases" / f"{version}.md", root, args.repo, version
            ),
            encoding="utf-8",
        )
        prepare(args.repo, args.commit, version, args.artifacts, notes)


if __name__ == "__main__":
    main()
