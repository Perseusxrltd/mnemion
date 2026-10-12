"""Independently verify uploaded release bytes without publishing or changing them."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

MAX_ASSETS = 128
MAX_ASSET_BYTES = 2 * 1024**3
MAX_TOTAL_BYTES = 8 * 1024**3


def gh(*arguments: str) -> str:
    result = subprocess.run(
        ["gh", *arguments], capture_output=True, text=True, timeout=900, check=False
    )
    if result.returncode:
        raise RuntimeError("GitHub verification request failed; no release was changed")
    return result.stdout


def release_run(repo: str, run_id: int) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or run_id < 1:
        raise ValueError("A repository and positive release run ID are required")
    run = json.loads(gh("api", f"repos/{repo}/actions/runs/{run_id}"))
    if (
        run.get("id") != run_id
        or run.get("path") != ".github/workflows/release.yml"
        or run.get("event") != "workflow_dispatch"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("repository", {}).get("full_name") != repo
        or run.get("head_repository", {}).get("full_name") != repo
        or not re.fullmatch(r"[a-f0-9]{40}", run.get("head_sha", ""))
    ):
        raise ValueError("The exact repository release workflow must have succeeded")
    jobs = json.loads(
        gh("run", "view", str(run_id), "--repo", repo, "--json", "headSha,conclusion,jobs")
    )
    if (
        jobs.get("headSha") != run["head_sha"]
        or jobs.get("conclusion") != "success"
        or not {"Release preflight", "assemble"}.issubset(
            {job.get("name") for job in jobs.get("jobs", [])}
        )
        or any(
            job.get("status") != "completed" or job.get("conclusion") != "success"
            for job in jobs["jobs"]
        )
    ):
        raise ValueError("Release jobs do not match the completed source and gates")
    return run


def inventory(release: dict, version: str, commit: str) -> dict[str, dict]:
    if (
        release.get("tag_name") != "v" + version
        or release.get("target_commitish") != commit
        or type(release.get("draft")) is not bool
        or release.get("prerelease") is not False
        or type(release.get("id")) is not int
        or release["id"] < 1
        or not isinstance(release.get("body"), str)
        or re.search(r"\]\(\.\.?/", release["body"])
    ):
        raise ValueError("Release identity, state or documentation does not match")
    rows = release.get("assets")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ASSETS:
        raise ValueError("Release inventory is missing or exceeds its bound")
    result = {}
    ids = set()
    total = 0
    for asset in rows:
        name = asset.get("name", "")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}", name)
            or name in result
            or asset.get("state") != "uploaded"
            or type(asset.get("id")) is not int
            or asset["id"] < 1
            or asset["id"] in ids
            or type(asset.get("size")) is not int
            or not 0 < asset["size"] <= MAX_ASSET_BYTES
            or not isinstance(asset.get("digest"), str)
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", asset["digest"])
        ):
            raise ValueError("Unsafe, duplicate, incomplete or oversized release asset")
        result[name] = {key: asset[key] for key in ("id", "name", "size", "digest")}
        ids.add(asset["id"])
        total += asset["size"]
    if total > MAX_TOTAL_BYTES or "SHA256SUMS.txt" not in result:
        raise ValueError("Release exceeds its total bound or has no checksum inventory")
    return result


def file_matches(path: Path, asset: dict) -> bool:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Release assets must be regular files, never links or directories")
    if not path.is_file() or path.stat().st_size != asset["size"]:
        return False
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return asset["digest"] == "sha256:" + digest


def download(repo: str, tag: str, artifacts: Path, asset: dict) -> None:
    path = artifacts / asset["name"]
    if not file_matches(path, asset):
        gh(
            "release",
            "download",
            tag,
            "--repo",
            repo,
            "--dir",
            str(artifacts),
            "--pattern",
            asset["name"],
            "--clobber",
        )
    if not file_matches(path, asset):
        raise ValueError("Downloaded bytes differ from GitHub's exact size or digest")


def verify(repo: str, run_id: int, source: Path, output: Path) -> dict:
    run = release_run(repo, run_id)
    source = source.resolve()
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()
    if actual != run["head_sha"]:
        raise ValueError("Verification source differs from the completed release commit")
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=source,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    if dirty.strip():
        raise ValueError("Release verification requires unchanged tracked source files")
    version = tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("A stable source version is required")
    tag = "v" + version
    # gh resolves a draft before its Git tag exists; the tag REST endpoint cannot.
    release_id = json.loads(gh("release", "view", tag, "--repo", repo, "--json", "databaseId"))[
        "databaseId"
    ]
    if type(release_id) is not int or release_id < 1:
        raise ValueError("Invalid release identifier")
    endpoint = f"repos/{repo}/releases/{release_id}"
    release = json.loads(gh("api", endpoint))
    assets = inventory(release, version, actual)
    if output.is_symlink():
        raise ValueError("Verification output must not be a link")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output = output.resolve()
    artifacts = output / "artifacts"
    if artifacts.is_symlink():
        raise ValueError("Verification artifacts must not be a linked directory")
    artifacts.mkdir(mode=0o700, exist_ok=True)
    if any(path.name not in assets for path in artifacts.iterdir()):
        raise ValueError("Unexpected files in the release artifact directory")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        pending = [pool.submit(download, repo, tag, artifacts, a) for a in assets.values()]
        for finished in concurrent.futures.as_completed(pending):
            finished.result()
    if {p.name for p in artifacts.iterdir()} != set(assets):
        raise ValueError("Downloaded inventory differs from the release")
    checksums = artifacts / "SHA256SUMS.txt"
    original = checksums.read_bytes()
    # Invoke the existing production signature/feed/package validator from the
    # exact release commit, not the possibly newer default-branch implementation.
    subprocess.run(
        [sys.executable, str(source / "deploy/release.py"), "--artifacts", str(artifacts)],
        cwd=source,
        check=True,
        timeout=600,
        env={
            key: value
            for key, value in os.environ.items()
            if key
            not in {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"}
        },
    )
    if checksums.read_bytes() != original:
        raise ValueError("Recomputed checksum inventory differs from uploaded bytes")
    if not all(file_matches(artifacts / name, asset) for name, asset in assets.items()):
        raise ValueError("Local release bytes changed during production verification")
    current = json.loads(gh("api", endpoint))
    if current["id"] != release["id"] or inventory(current, version, actual) != assets:
        raise ValueError("Release assets changed while verification was running")
    if current["draft"] is False:
        ref = json.loads(gh("api", f"repos/{repo}/git/ref/tags/{tag}"))["object"]
        if ref["type"] == "tag":
            ref = json.loads(gh("api", f"repos/{repo}/git/tags/{ref['sha']}"))["object"]
        if ref.get("type") != "commit" or ref.get("sha") != actual:
            raise ValueError("Published tag differs from the verified source commit")
    receipt = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "repository": repo,
        "version": version,
        "source_commit": actual,
        "release_run": run_id,
        "release_id": current["id"],
        "release_state": "draft" if current["draft"] else "published",
        "assets": len(assets),
        "bytes": sum(a["size"] for a in assets.values()),
        "checksum_digest": assets["SHA256SUMS.txt"]["digest"],
        "exact_source_production_validator_passed": True,
        "asset_ids_sizes_digests_unchanged_after_verification": True,
        "inventory": [assets[name] for name in sorted(assets)],
    }
    (output / "release-verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.resolve:
        print("commit=" + release_run(args.repo, args.run)["head_sha"])
    else:
        if args.source is None or args.output is None:
            parser.error("--source and --output are required for verification")
        receipt = verify(args.repo, args.run, args.source, args.output)
        print(json.dumps({key: value for key, value in receipt.items() if key != "inventory"}))


if __name__ == "__main__":
    main()
