"""Reuse complete same-source Product checks and their required runtime artifact."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile

import yaml

from .published_release import fetch

ARTIFACT = "release-service-macos-x64"
REUSE_JOB = "Reuse verified Product checks"
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024


def required_jobs(workflow: str) -> set[str]:
    """Expand this checkout's complete static matrix; unknown syntax disables reuse."""
    jobs = yaml.safe_load(workflow)["jobs"]
    if not isinstance(jobs, dict) or not 1 <= len(jobs) <= 50:
        raise ValueError("Unsupported CI job inventory")
    names = []
    for identifier, job in jobs.items():
        matrix = job.get("strategy", {}).get("matrix", {})
        if not isinstance(matrix, dict) or matrix.keys() & {"include", "exclude"}:
            raise ValueError("Unsupported CI matrix")
        if any(
            not isinstance(values, list)
            or not 1 <= len(values) <= 20
            or any(not isinstance(value, str) for value in values)
            for values in matrix.values()
        ):
            raise ValueError("Unsupported CI matrix values")
        for values in itertools.product(*matrix.values()):
            fields = dict(zip(matrix, values, strict=True))
            name = job.get("name", identifier)
            if not isinstance(name, str):
                raise ValueError("Unsupported CI job name")
            if "name" in job:
                name = re.sub(
                    r"\$\{\{\s*matrix\.(\w+)\s*\}\}",
                    lambda match: fields[match[1]],
                    name,
                )
            elif values:
                name += " (" + ", ".join(values) + ")"
            if "${{" in name or not name or len(name) > 200:
                raise ValueError("Unsupported CI job expression")
            names.append(name)
            if len(names) > 100:
                raise ValueError("CI matrix exceeds the bounded evidence inventory")
    if len(names) != len(set(names)):
        raise ValueError("Ambiguous CI job names")
    return set(names)


def selection(repo: str, source: str, expected: set[str], get, *, now=None) -> dict:
    """No successful subset, foreign run, older retry or missing artifact qualifies."""
    now = now or datetime.now(timezone.utc)
    if not expected:
        raise ValueError("A complete CI job contract is required")
    report = {
        "repository": repo,
        "source_commit": source,
        "verified_at": now.isoformat(),
        "required_jobs": sorted(expected),
        "reusable": False,
        "reason": "no_matching_run",
    }
    runs = get(f"actions/workflows/ci.yml/runs?head_sha={source}&per_page=10")
    candidates = [
        run
        for run in runs["workflow_runs"]
        if isinstance(run, dict)
        and run.get("head_sha") == source
        and run.get("head_repository", {}).get("full_name") == repo
        and run.get("repository", {}).get("full_name") == repo
        and run.get("path", "").partition("@")[0] == ".github/workflows/ci.yml"
        and run.get("event") == "push"
        and run.get("head_branch") == "main"
        and type(run.get("id")) is int
        and run["id"] > 0
    ]
    if not candidates:
        return report
    run = max(candidates, key=lambda item: item["id"])
    run_id = run["id"]
    report.update(run_id=run_id, run_attempt=run.get("run_attempt"))
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return {**report, "reason": "latest_run_not_successful"}
    if type(run.get("run_attempt")) is not int or run["run_attempt"] < 1:
        raise ValueError("Unexpected CI run attempt")
    if run.get("html_url") != f"https://github.com/{repo}/actions/runs/{run_id}":
        raise ValueError("Unexpected CI run URL")
    jobs = get(f"actions/runs/{run_id}/jobs?filter=latest&per_page=100")
    rows = jobs["jobs"]
    if jobs["total_count"] != len(rows) or len(rows) != len(expected):
        return {**report, "reason": "incomplete_job_inventory"}
    if {job.get("name") for job in rows} != expected or len({job.get("id") for job in rows}) != len(
        rows
    ):
        return {**report, "reason": "different_job_inventory"}
    if any(
        job.get("head_sha") != source
        or job.get("run_id") != run_id
        or type(job.get("id")) is not int
        or job["id"] <= 0
        or job.get("status") != "completed"
        or job.get("conclusion") != "success"
        or not isinstance(job.get("steps"), list)
        or not job["steps"]
        or any(
            step.get("status") != "completed"
            or step.get("conclusion") not in {"success", "skipped"}
            for step in job["steps"]
        )
        for job in rows
    ):
        return {**report, "reason": "required_checks_not_successful"}
    inventory = get(f"actions/runs/{run_id}/artifacts?per_page=100")
    if inventory["total_count"] != len(inventory["artifacts"]):
        return {**report, "reason": "incomplete_artifact_inventory"}
    artifacts = [item for item in inventory["artifacts"] if item.get("name") == ARTIFACT]
    if len(artifacts) != 1:
        return {**report, "reason": "required_runtime_artifact_unavailable"}
    artifact = artifacts[0]
    expires = datetime.fromisoformat(artifact["expires_at"])
    if (
        artifact.get("expired") is not False
        or expires.tzinfo is None
        or expires <= now
        or type(artifact.get("id")) is not int
        or artifact["id"] <= 0
        or type(artifact.get("size_in_bytes")) is not int
        or not 0 < artifact["size_in_bytes"] <= MAX_ARTIFACT_BYTES
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", artifact.get("digest", ""))
        or artifact.get("workflow_run", {}).get("id") != run_id
        or artifact["workflow_run"].get("head_sha") != source
    ):
        return {**report, "reason": "runtime_artifact_not_verified"}
    return {
        **report,
        "reusable": True,
        "reason": "complete_same_source_checks",
        "run_url": run["html_url"],
        "jobs_passed": len(rows),
        "artifact": {
            key: artifact[key] for key in ("id", "name", "digest", "size_in_bytes", "expires_at")
        },
    }


def verify_release_check_lanes(repo: str, source: str, jobs: list[dict], get) -> set[str]:
    """Allow only the unused check lane, with independent proof for the chosen lane."""
    content = get(f"contents/.github/workflows/ci.yml?ref={source}")
    if (
        content.get("type") != "file"
        or content.get("path") != ".github/workflows/ci.yml"
        or content.get("encoding") != "base64"
        or type(content.get("size")) is not int
        or not 0 < content["size"] <= 256 * 1024
    ):
        raise ValueError("The exact-source CI contract is unavailable")
    raw = base64.b64decode(content["content"].replace("\n", ""), validate=True)
    if len(raw) != content["size"]:
        raise ValueError("The exact-source CI contract is incomplete")
    expected = required_jobs(raw.decode("utf-8"))
    by_name = {job["name"]: job for job in jobs}
    if len(by_name) != len(jobs) or REUSE_JOB not in by_name:
        raise ValueError("The release check lanes are missing or ambiguous")
    ordinary = {name for name in by_name if name == "checks" or name.startswith("checks / ")}
    expanded = {"checks / " + name for name in expected}

    def completed(name, conclusion):
        job = by_name[name]
        return job.get("status") == "completed" and job.get("conclusion") == conclusion

    if completed(REUSE_JOB, "skipped"):
        if ordinary != expanded or not all(completed(name, "success") for name in ordinary):
            raise ValueError("Every original Product check must succeed when reuse is unused")
        return {REUSE_JOB}
    if not completed(REUSE_JOB, "success"):
        raise ValueError("The runtime transfer and reused checks did not succeed")
    if ordinary not in ({"checks"}, expanded) or not all(
        completed(name, "skipped") for name in ordinary
    ):
        raise ValueError("Only the complete unused Product check lane may be skipped")
    proof = selection(repo, source, expected, get)
    if not proof["reusable"]:
        raise ValueError("Independent same-source Product check verification failed")
    return ordinary


def restore_archive(archive: Path, destination: Path, digest: str) -> list[str]:
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("A verified artifact digest is required")
    if archive.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("CI artifact exceeds the transfer limit")
    with archive.open("rb") as stream:
        actual = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != digest:
        raise ValueError("CI artifact bytes differ from the verified GitHub digest")
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if not 1 <= len(entries) <= 8 or len({item.filename for item in entries}) != len(entries):
            raise ValueError("CI runtime artifact has an ambiguous inventory")
        if sum(item.file_size for item in entries) > MAX_ARTIFACT_BYTES or any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]{1,200}\.whl", item.filename)
            or stat.S_IFMT(item.external_attr >> 16) not in {0, stat.S_IFREG}
            or item.flag_bits & 1
            for item in entries
        ):
            raise ValueError("CI runtime artifact must contain bounded regular wheels")
        destination.mkdir(parents=True, exist_ok=False)
        for item in entries:
            with package.open(item) as source, (destination / item.filename).open("xb") as out:
                shutil.copyfileobj(source, out, 1024 * 1024)
        return [item.filename for item in entries]


def restore(repo: str, artifact_id: int, digest: str, destination: Path) -> list[str]:
    if artifact_id <= 0:
        raise ValueError("A verified artifact identifier is required")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("A verified artifact digest is required before downloading")

    def limit_download():
        # This release-transfer job runs on Ubuntu. Bound gh's output on disk.
        import resource

        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_ARTIFACT_BYTES, MAX_ARTIFACT_BYTES))

    with tempfile.TemporaryDirectory(prefix="mnemion-checked-runtime-") as temporary:
        archive = Path(temporary) / "runtime.zip"
        with archive.open("xb") as out:
            result = subprocess.run(
                ["gh", "api", f"repos/{repo}/actions/artifacts/{artifact_id}/zip"],
                stdout=out,
                stderr=subprocess.DEVNULL,
                timeout=90,
                preexec_fn=limit_download,
            )
        if result.returncode:
            raise RuntimeError("The verified CI runtime artifact could not be downloaded")
        return restore_archive(archive, destination, digest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--source", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--output", type=Path, default=Path("output/ci-reuse.json"))
    parser.add_argument("--restore-artifact-id", type=int)
    parser.add_argument("--artifact-digest")
    parser.add_argument("--destination", type=Path, default=Path("output/reused-runtime"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo) or not re.fullmatch(
        r"[a-f0-9]{40}", args.source
    ):
        parser.error("An explicit GitHub repository and immutable source are required")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != args.source:
        raise ValueError("CI reuse must inspect the exact checked-out release source")
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--", ".github/workflows/ci.yml"], text=True
    ).strip():
        raise ValueError("The checked-out CI contract has local changes")
    if args.restore_artifact_id is not None:
        files = restore(args.repo, args.restore_artifact_id, args.artifact_digest, args.destination)
        print(json.dumps({"restored_runtime_files": files, "digest_verified": True}))
        return

    def get(path):
        return json.loads(fetch(f"https://api.github.com/repos/{args.repo}/{path}", api=True))

    try:
        expected = required_jobs(Path(".github/workflows/ci.yml").read_text())
        report = selection(args.repo, args.source, expected, get)
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        yaml.YAMLError,
    ) as error:
        # An unavailable or unfamiliar proof runs the ordinary full suite.
        report = {
            "repository": args.repo,
            "source_commit": args.source,
            "reusable": False,
            "reason": "evidence_unavailable",
            "error_type": type(error).__name__,
        }
    if args.output.is_symlink():
        raise ValueError("The evidence output must be a regular file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print("reusable=" + str(report["reusable"]).lower())
    print("run_id=" + (str(report["run_id"]) if report["reusable"] else ""))
    print("artifact_id=" + (str(report["artifact"]["id"]) if report["reusable"] else ""))
    print("artifact_digest=" + (report["artifact"]["digest"] if report["reusable"] else ""))


if __name__ == "__main__":
    main()
