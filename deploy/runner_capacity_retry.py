"""Retry one unstarted release attempt when GitHub explicitly reports no runner."""

from __future__ import annotations

import argparse
import json
import re

from .published_release import REPOSITORY
from .release_automation import api, gh, semver, tag_commit

CAPACITY_FAILURE = "The job was not acquired by Runner of type hosted even after multiple attempts"
WORKFLOWS = {".github/workflows/public-updates.yml", ".github/workflows/release.yml"}
IDENTITY = ("id", "head_sha", "head_branch", "path", "event", "run_attempt", "status", "conclusion")


def pages(path: str, key: str | None = None) -> list[dict]:
    result = []
    for page in range(1, 11):
        data = json.loads(gh("api", f"repos/{REPOSITORY}/{path}?per_page=100&page={page}"))
        rows = data.get(key) if key and isinstance(data, dict) else data
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Invalid runner evidence")
        result.extend(rows)
        if len(rows) < 100:
            if key and data.get("total_count") != len(result):
                raise ValueError("Incomplete job inventory")
            return result
    raise ValueError("Runner evidence exceeds the bounded inventory")


def eligible_source(run: dict, run_id: int) -> bool:
    if (
        run.get("id") != run_id
        or run.get("event") != "workflow_dispatch"
        or run.get("path") not in WORKFLOWS
        or run.get("run_attempt") != 1
        or run.get("status") != "completed"
        or run.get("conclusion") not in {"failure", "cancelled"}
        or any(
            (run.get(key) or {}).get("full_name") != REPOSITORY
            for key in ("repository", "head_repository")
        )
        or not re.fullmatch(r"[a-f0-9]{40}", run.get("head_sha", ""))
    ):
        return False
    latest = api(REPOSITORY, "releases/latest")
    if latest.get("draft") is not False or latest.get("prerelease") is not False:
        return False
    if not latest.get("published_at"):
        return False
    latest_tag = latest.get("tag_name", "")
    if not latest_tag.startswith("v"):
        return False
    latest_version = semver(latest_tag[1:])
    branch = run.get("head_branch", "")
    if run["path"] == ".github/workflows/public-updates.yml":
        if branch != latest_tag:
            return False
        ref = api(REPOSITORY, "git/ref/tags/" + branch)
        return tag_commit(REPOSITORY, ref["object"]) == run["head_sha"]
    match = re.fullmatch(r"release/([0-9]+\.[0-9]+\.[0-9]+)(?:-r([2-9]|[1-9][0-9]+))?", branch)
    if not match or semver(match[1]) <= latest_version:
        return False
    ref = api(REPOSITORY, "git/ref/heads/" + branch)
    target = ref.get("object", {})
    if target.get("type") != "commit" or target.get("sha") != run["head_sha"]:
        return False
    comparison = api(REPOSITORY, f"compare/{run['head_sha']}...main")
    return comparison.get("status") in {"ahead", "identical"}


def inspect(run_id: int, *, apply: bool = False) -> dict:
    if type(run_id) is not int or not 0 < run_id < 10**20:
        raise ValueError("Use a positive GitHub run identifier")
    run_path = f"actions/runs/{run_id}"
    run = api(REPOSITORY, run_path)
    result = {"run_id": run_id, "eligible": False, "retried": False}
    if not eligible_source(run, run_id):
        return {**result, "reason": "Not a first failed attempt of an eligible current release"}
    jobs = pages(run_path + "/attempts/1/jobs", "jobs")
    failed = []
    for job in jobs:
        if job.get("status") != "completed" or job.get("run_id") != run_id:
            return {**result, "reason": "Job inventory is unfinished or belongs to another run"}
        if job.get("conclusion") in {"success", "skipped"}:
            continue
        if (
            job.get("conclusion") not in {"cancelled", "failure"}
            or job.get("steps") != []
            or job.get("runner_name") not in {None, ""}
            or job.get("runner_id") not in {None, 0}
        ):
            return {**result, "reason": "A job started or failed for an unrecognized reason"}
        match = re.fullmatch(
            rf"https://api\.github\.com/repos/{re.escape(REPOSITORY)}/check-runs/([1-9][0-9]*)",
            job.get("check_run_url", ""),
        )
        if not match:
            return {**result, "reason": "Missing trusted runner-capacity evidence"}
        annotations = pages(f"check-runs/{match[1]}/annotations")
        failures = [
            row.get("message", "").strip()
            for row in annotations
            if row.get("annotation_level") == "failure"
        ]
        if not failures or any(message != CAPACITY_FAILURE for message in failures):
            return {**result, "reason": "Failure is not exclusively GitHub runner capacity"}
        failed.append(job["id"])
    if not failed:
        return {**result, "reason": "No unstarted capacity failure"}
    result.update(eligible=True, job_ids=failed, source_commit=run["head_sha"])
    if not apply:
        return {**result, "reason": "Dry run; one retry is eligible"}
    current = api(REPOSITORY, run_path)
    if any(current.get(key) != run.get(key) for key in IDENTITY) or not eligible_source(
        current, run_id
    ):
        return {**result, "eligible": False, "reason": "Release or run changed before retry"}
    try:
        gh("api", "--method", "POST", f"repos/{REPOSITORY}/{run_path}/rerun-failed-jobs")
    except RuntimeError:
        current = api(REPOSITORY, run_path)
        if current.get("run_attempt") != 1 or current.get("status") != "completed":
            return {**result, "eligible": False, "reason": "Another retry already changed the run"}
        raise
    return {**result, "retried": True, "reason": "Requested the single failed-job retry"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(inspect(arguments.run, apply=arguments.apply), indent=2))


if __name__ == "__main__":
    main()
