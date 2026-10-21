"""Repeatable version preparation and publication of already verified artifacts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from .verify_artifacts import inventory, release_run


def semver(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})", value
    ):
        raise ValueError("Use a stable X.Y.Z version")
    return tuple(map(int, value.split(".")))


def prepare(root: Path, version: str) -> list[str]:
    """Update package boundaries once; never invent release notes or completion."""
    semver(version)
    notes = root / f"docs/releases/{version}.md"
    if not notes.is_file() or not notes.read_text().startswith(f"# Mnemion {version}\n"):
        raise ValueError("Write this version's concrete release notes before preparation")
    updates = {}
    for directory in (Path("."), Path("studio/client")):
        project_path = directory / "pyproject.toml"
        contents = (root / project_path).read_text()
        project = tomllib.loads(contents)["project"]
        if semver(project["version"]) > semver(version):
            raise ValueError("Preparation must not decrease a package version")
        updates[project_path] = re.sub(
            r'(?m)^version = "[^"]+"$', f'version = "{version}"', contents, count=1
        )
        lock = directory / "uv.lock"
        pattern = (
            r'(\[\[package\]\]\nname = "'
            + re.escape(project["name"])
            + r'"\nversion = ")[^"]+("\n)'
        )
        updates[lock], count = re.subn(
            pattern, lambda match: match[1] + version + match[2], (root / lock).read_text()
        )
        if count != 1:
            raise ValueError("The project must have exactly one local lock entry")
    path = Path("mnemion/version.py")
    updates[path], count = re.subn(
        r'(?m)^__version__ = "[^"]+"$', f'__version__ = "{version}"', (root / path).read_text()
    )
    if count != 1:
        raise ValueError("Missing canonical version")
    for directory in ("packages/client", "studio/frontend", "studio/electron"):
        for name in ("package.json", "package-lock.json"):
            path = Path(directory) / name
            data = json.loads((root / path).read_text())
            data["version"] = version
            for key in ("", "../../packages/client"):
                if key in data.get("packages", {}):
                    data["packages"][key]["version"] = version
            updates[path] = json.dumps(data, indent=2) + "\n"
    path = Path("deploy/release-targets.json")
    data = json.loads((root / path).read_text())
    data["version"] = version
    updates[path] = json.dumps(data, indent=2) + "\n"
    path = Path("docs/ROADMAP.md")
    updates[path], count = re.subn(
        r"(?m)^Reviewed source distribution: \*\*[^*]+\*\*\. Roadmap updated: \*\*[^*]+\*\*\.$",
        f"Reviewed source distribution: **{version}**. Roadmap updated: **{datetime.now(timezone.utc).date().isoformat()}**.",
        (root / path).read_text(),
    )
    if count != 1:
        raise ValueError("Missing reviewed-source roadmap marker")
    for path in updates:
        if (root / path).is_symlink():
            raise ValueError("Release metadata must be ordinary repository files")
    changed = []
    for path, contents in updates.items():
        if (root / path).read_text() != contents:
            (root / path).write_text(contents)
            changed.append(str(path))
    return changed


def gh(*arguments: str) -> str:
    result = subprocess.run(["gh", *arguments], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(
            "Release automation request failed; inspect the workflow before retrying"
        )
    return result.stdout


def api(repo: str, path: str) -> dict:
    data = json.loads(gh("api", f"repos/{repo}/{path}"))
    if not isinstance(data, dict):
        raise ValueError("Invalid GitHub release response")
    return data


def tag_commit(repo: str, target: dict) -> str:
    for _ in range(3):
        if not re.fullmatch(r"[a-f0-9]{40}", target.get("sha", "")):
            break
        if target.get("type") == "commit":
            return target["sha"]
        if target.get("type") != "tag":
            break
        target = api(repo, "git/tags/" + target["sha"])["object"]
    raise ValueError("The release tag must identify an ordinary commit")


def _integration_git(root: Path, *arguments: str, check=True):
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Perseusxrltd",
            "-c",
            "user.email=226232767+Perseusxrltd@users.noreply.github.com",
            "-c",
            "credential.helper=",
            "-c",
            "credential.helper=!gh auth git-credential",
            *arguments,
        ],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=120,
        check=check,
    )


def check_source(root: Path) -> None:
    """Refuse cheap source failures before pushing main or reserving runners."""
    # The locked development environment supplies the pinned formatter/linter.
    # Report the problem without changing reviewed or committed source.
    for check in (["format", "--check", "."], ["check", "."]):
        subprocess.run([sys.executable, "-m", "ruff", *check], cwd=root, check=True)


def integrate(root: Path, repo: str) -> dict:
    """Push reviewed commits normally; merge only generated metadata races automatically."""
    if repo != "Perseusxrltd/mnemion":
        raise ValueError("This integration policy is configured only for the Mnemion repository")

    def git(*arguments, check=True):
        return _integration_git(root, *arguments, check=check)

    if git("status", "--porcelain").stdout.strip():
        raise ValueError("Commit the reviewed source before integrating")
    branch = git("symbolic-ref", "--short", "HEAD").stdout.strip()
    if branch.startswith("release/"):
        raise ValueError("Frozen release branches cannot be rebased by integration")
    origin = git("remote", "get-url", "origin").stdout.strip()
    if origin not in {
        f"https://github.com/{repo}",
        f"https://github.com/{repo}.git",
        f"git@github.com:{repo}.git",
    }:
        raise ValueError("Origin does not match the authorized repository")
    check_source(root)
    generated = {
        "deploy/published-release.json",
        "deploy/release-status.json",
        "docs/RELEASE_STATUS.md",
        "deploy/maintenance-status.json",
        "docs/MAINTENANCE_STATUS.md",
        "deploy/research-watch.json",
        "docs/research/RESEARCH_WATCH.md",
    }
    for attempt in range(1, 4):
        git("fetch", "origin", "main")
        incoming = git("diff", "--name-only", "HEAD...origin/main").stdout.splitlines()
        if any(
            path not in generated
            and not re.fullmatch(
                r"docs/validation/releases/[0-9]+\.[0-9]+\.[0-9]+-[a-z-]+\.json", path
            )
            for path in incoming
        ):
            raise ValueError(
                "Main contains source changes; review and integrate them before publication"
            )
        if git("merge-base", "--is-ancestor", "origin/main", "HEAD", check=False).returncode:
            # Preserve exact hotfix parents and reviewed conflict resolutions.
            # Replaying a merge can reopen conflicts even when the only new
            # commits contain generated status. Ordinary merge keeps the
            # reviewed source intact and still refuses any metadata conflict.
            git("merge", "--no-edit", "origin/main")
        commit = git("rev-parse", "HEAD").stdout.strip()
        if git("push", "origin", "HEAD:main", check=False).returncode:
            continue
        local_main = None
        for block in git("worktree", "list", "--porcelain", "-z").stdout.split("\0\0"):
            fields = block.split("\0")
            if "branch refs/heads/main" not in fields:
                continue
            location = Path(
                next(
                    field.removeprefix("worktree ")
                    for field in fields
                    if field.startswith("worktree ")
                )
            )
            if location.resolve() == root.resolve():
                local_main = True
            elif not _integration_git(location, "status", "--porcelain").stdout.strip():
                local_main = (
                    _integration_git(location, "merge", "--ff-only", commit, check=False).returncode
                    == 0
                )
            else:
                local_main = False
        return {
            "source_commit": commit,
            "pushed_to": "main",
            "attempts": attempt,
            "local_main_updated": local_main,
        }
    raise RuntimeError(
        "Main could not be updated after three normal push attempts; inspect the remote"
    )


def start(root: Path, repo: str, *, attempt: int = 1) -> dict:
    """Freeze the clean main source and start its one complete release run."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Use a repository owner/name")

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True, timeout=30).strip()

    if git("status", "--porcelain"):
        raise ValueError("Commit the reviewed release source before starting")
    commit = git("rev-parse", "HEAD")
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    semver(version)
    if type(attempt) is not int or not 1 <= attempt <= 100:
        raise ValueError("Use a release attempt from 1 to 100")
    if attempt > 1 and semver(api(repo, "releases/latest")["tag_name"].removeprefix("v")) >= semver(
        version
    ):
        raise ValueError("Corrected attempts cannot replace a published version")
    if api(repo, f"compare/{commit}...main").get("status") not in {"ahead", "identical"}:
        raise ValueError("Push this source to main before starting its release")
    branch = "release/" + version + (f"-r{attempt}" if attempt > 1 else "")
    refs = json.loads(gh("api", f"repos/{repo}/git/matching-refs/heads/{branch}"))
    if not isinstance(refs, list) or len(refs) > 128:
        raise ValueError("Invalid release branch inventory")
    existing = [ref for ref in refs if ref.get("ref") == "refs/heads/" + branch]
    if existing and existing[0]["object"]["sha"] != commit:
        raise ValueError("This release branch is already frozen at different source")
    if not existing:
        gh(
            "api",
            "--method",
            "POST",
            f"repos/{repo}/git/refs",
            "-f",
            "ref=refs/heads/" + branch,
            "-f",
            "sha=" + commit,
        )
    runs = api(repo, f"actions/workflows/release.yml/runs?branch={branch}&per_page=20")
    matching = [run for run in runs.get("workflow_runs", []) if run.get("head_sha") == commit]
    if matching:
        return {
            "version": version,
            "source_commit": commit,
            "branch": branch,
            "existing_run": matching[0]["id"],
        }
    gh("workflow", "run", "release.yml", "--repo", repo, "--ref", branch)
    return {"version": version, "source_commit": commit, "branch": branch, "dispatched": True}


def publish(repo: str, receipt: dict, verification_run: int, *, dry_run=False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or verification_run < 1:
        raise ValueError("A repository and verification run are required")
    verifier = api(repo, f"actions/runs/{verification_run}")
    if (
        verifier.get("path") != ".github/workflows/verify-artifacts.yml"
        or verifier.get("event") not in {"workflow_run", "workflow_dispatch"}
        or verifier.get("repository", {}).get("full_name") != repo
        or verifier.get("head_repository", {}).get("full_name") != repo
    ):
        raise ValueError("Verification must come from this repository's trusted workflow")
    jobs = api(repo, f"actions/runs/{verification_run}/jobs?filter=latest&per_page=100")
    if not any(
        job.get("name") == "verify"
        and job.get("status") == "completed"
        and job.get("conclusion") == "success"
        for job in jobs.get("jobs", [])
    ):
        raise ValueError("The uploaded-byte verification job must have passed")
    if (
        receipt.get("repository") != repo
        or receipt.get("exact_source_production_validator_passed") is not True
        or receipt.get("asset_ids_sizes_digests_unchanged_after_verification") is not True
        or type(receipt.get("release_run")) is not int
        or type(receipt.get("release_id")) is not int
    ):
        raise ValueError("Missing complete verification receipt")
    version, commit = receipt["version"], receipt["source_commit"]
    semver(version)
    run = release_run(repo, receipt["release_run"])
    if run["head_sha"] != commit:
        raise ValueError("Receipt and completed release source disagree")
    comparison = api(repo, f"compare/{commit}...main")
    if comparison.get("status") not in {"ahead", "identical"}:
        raise ValueError("The verified release must already be on main")
    release = api(repo, f"releases/{receipt['release_id']}")
    assets = inventory(release, version, commit)
    expected = receipt.get("inventory", [])
    if (
        not isinstance(expected, list)
        or len(expected) != len(assets)
        or expected != [assets[name] for name in sorted(assets)]
    ):
        raise ValueError("Uploaded assets changed after verification")
    latest = api(repo, "releases/latest")
    if semver(latest["tag_name"].removeprefix("v")) > semver(version):
        raise ValueError("A newer stable release is already published")
    tag = "v" + version
    refs = json.loads(gh("api", f"repos/{repo}/git/matching-refs/tags/{tag}"))
    if not isinstance(refs, list) or len(refs) > 128:
        raise ValueError("Invalid release tag inventory")
    for ref in refs:
        if ref.get("ref") == "refs/tags/" + tag and tag_commit(repo, ref["object"]) != commit:
            raise ValueError("An existing release tag points to different source")
    already_public = not release["draft"]
    if dry_run:
        return {
            "version": version,
            "source_commit": commit,
            "ready": True,
            "already_public": already_public,
        }
    if not already_public:
        gh("release", "edit", tag, "--repo", repo, "--draft=false", "--latest")
    current = api(repo, f"releases/{receipt['release_id']}")
    if current["draft"] or inventory(current, version, commit) != assets:
        raise ValueError("Published assets differ from the verified release")
    target = api(repo, f"git/ref/tags/{tag}")["object"]
    if tag_commit(repo, target) != commit:
        raise ValueError("The published tag does not identify the verified source")
    followups = {}
    # GITHUB_TOKEN publication does not emit another release workflow event.
    # Explicit dispatches keep website and public upgrades automatic. Matching
    # existing runs (including failed ones) are retained rather than rerun blindly.
    for workflow in ("website-release.yml", "public-updates.yml"):
        runs = api(repo, f"actions/workflows/{workflow}/runs?branch={tag}&per_page=30")
        title = (
            f"Public updates / {tag} / all / all"
            if workflow == "public-updates.yml"
            else f"Public website / {tag}"
        )
        existing = [
            item
            for item in runs.get("workflow_runs", [])
            if item.get("head_sha") == commit
            and (
                item.get("event") == "release"
                or (item.get("event") == "workflow_dispatch" and item.get("display_title") == title)
            )
            and item.get("created_at", "") >= current["published_at"]
        ]
        if existing:
            followups[workflow] = "existing"
            continue
        arguments = ["workflow", "run", workflow, "--repo", repo, "--ref", tag]
        if workflow == "public-updates.yml":
            arguments += ["-f", "tag=" + tag, "-f", "platform=all", "-f", "architecture=all"]
        gh(*arguments)
        followups[workflow] = "dispatched"
    return {
        "version": version,
        "source_commit": commit,
        "published_at": current["published_at"],
        "release_id": current["id"],
        "release_url": current["html_url"],
        "assets": len(assets),
        "checksum_digest": assets["SHA256SUMS.txt"]["digest"],
        "release_run": receipt["release_run"],
        "verification_run": verification_run,
        "uploaded_inventory_unchanged_at_publication": True,
        "tag_matches_verified_source": True,
        "followups": followups,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("version")
    integrate_command = commands.add_parser("integrate")
    integrate_command.add_argument("--repo", default="Perseusxrltd/mnemion")
    start_command = commands.add_parser("start")
    start_command.add_argument("--repo", default="Perseusxrltd/mnemion")
    start_command.add_argument("--attempt", type=int, default=1)
    publish_command = commands.add_parser("publish")
    publish_command.add_argument("--repo", required=True)
    publish_command.add_argument("--receipt", type=Path, required=True)
    publish_command.add_argument("--verification-run", type=int, required=True)
    publish_command.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == "prepare":
        changed = prepare(root, args.version)
        for arguments in (
            ["-m", "mnemion.service.cli", "schema", "--output", "docs/service/openapi.json"],
            [
                "-m",
                "mnemion.service.cli",
                "agent-schema",
                "--output",
                "mnemion/service/agent_contract.json",
            ],
            ["deploy/release.py"],
        ):
            subprocess.run([sys.executable, *arguments], cwd=root, check=True)
        print(json.dumps({"version": args.version, "changed": changed}))
    elif args.command == "integrate":
        print(json.dumps(integrate(root, args.repo)))
    elif args.command == "start":
        check_source(root)
        from deploy.binary_preflight import check as check_binaries
        from deploy.client_preflight import check as check_client
        from deploy.migration_preflight import check as check_migrations

        print(json.dumps({"binary_preflight": check_binaries(root)}))
        print(json.dumps({"client_preflight": check_client(root)}))
        print(json.dumps({"migration_preflight": check_migrations(root)}))
        print(json.dumps(start(root, args.repo, attempt=args.attempt)))
    else:
        if (
            args.receipt.is_symlink()
            or not args.receipt.is_file()
            or args.receipt.stat().st_size > 131072
        ):
            raise ValueError("Use the bounded ordinary verification receipt")
        receipt = json.loads(args.receipt.read_text())
        result = publish(args.repo, receipt, args.verification_run, dry_run=args.dry_run)
        if not args.dry_run:
            directory = root / "docs/validation/releases"
            directory.mkdir(parents=True, exist_ok=True)
            for suffix, data in (("publication", result), ("artifacts", receipt)):
                path = directory / f"{result['version']}-{suffix}.json"
                if path.is_symlink():
                    raise ValueError("Release evidence must be an ordinary file")
                path.write_text(json.dumps(data, indent=2) + "\n")
        print(json.dumps(result))


if __name__ == "__main__":
    main()
