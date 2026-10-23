"""Synchronize the latest public release description from reviewed Git documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .draft_release import publication_notes
from .published_release import ORIGIN, REPOSITORY, version

MAX_NOTES = 64 * 1024


def api(path: str, body: dict | None = None) -> dict:
    command = ["gh", "api", f"repos/{REPOSITORY}/{path}"]
    if body is not None:
        command += ["--method", "PATCH", "--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "Release description synchronization failed; inspect the existing release"
        )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("Invalid release response")
    return value


def identity(release: dict) -> dict:
    tag = release.get("tag_name")
    version(tag)
    if (
        type(release.get("id")) is not int
        or release["id"] <= 0
        or release.get("draft") is not False
        or release.get("prerelease") is not False
        or not release.get("published_at")
        or release.get("html_url") != f"{ORIGIN}/releases/tag/{tag}"
        or not isinstance(release.get("target_commitish"), str)
        or not re.fullmatch(r"[a-f0-9]{40}", release["target_commitish"])
        or not isinstance(release.get("body"), str)
    ):
        raise ValueError("Only the identified stable public release description may change")
    return {
        key: release.get(key)
        for key in (
            "id",
            "tag_name",
            "target_commitish",
            "draft",
            "prerelease",
            "published_at",
            "html_url",
        )
    } | {
        "assets": sorted(
            (asset["id"], asset["name"], asset["size"], asset.get("digest"))
            for asset in release.get("assets", [])
        )
    }


def git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, text=True, timeout=30).strip()


def synchronize(root: Path, *, write: bool = False) -> dict:
    commit = git(root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Use a committed documentation checkout")
    release = api("releases/latest")
    original = identity(release)
    selected = release["tag_name"][1:]
    notes = root / "docs/releases" / f"{selected}.md"
    if notes.is_symlink() or not notes.is_file() or notes.stat().st_size > MAX_NOTES:
        raise ValueError("The published version needs bounded, ordinary Git release notes")
    if not notes.read_text(encoding="utf-8").startswith(f"# Mnemion {selected}\n"):
        raise ValueError("Release notes identify a different version")
    body = publication_notes(notes, root, REPOSITORY, selected, documentation_ref=commit)
    if len(body.encode("utf-8")) > MAX_NOTES:
        raise ValueError("Rendered release description exceeds its bound")
    changed = release["body"] != body
    if changed and write:
        if git(root, "status", "--porcelain"):
            raise ValueError(
                "Commit the reviewed documentation before updating its public description"
            )
        current = api(f"releases/{release['id']}")
        if identity(current) != original or current["body"] != release["body"]:
            raise RuntimeError(
                "Release changed during review; preserve it and inspect the current state"
            )
        # This request can edit only Markdown. Assets, tags and publication state
        # are never included in the mutation; their response identities must agree.
        updated = api(f"releases/{release['id']}", {"body": body})
        if identity(updated) != original or updated["body"] != body:
            raise RuntimeError(
                "Inspect the original release-description update before further work"
            )
    return {
        "version": selected,
        "documentation_commit": commit,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "changed": changed,
        "written": changed and write,
        "assets_or_tag_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(synchronize(Path(__file__).resolve().parent.parent, write=args.write)))


if __name__ == "__main__":
    main()
