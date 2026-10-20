"""Collect bounded issue/build changes once; never start jobs or decide feature completion."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

from .published_release import REPOSITORY
from .release_automation import gh, semver
from .release_status import WORKFLOWS as RELEASE_WORKFLOWS

LIMIT = 100
ISSUE_LIMIT = 1000
WORKFLOWS = {*RELEASE_WORKFLOWS, "database-cache.yml"}


def object_from_gh(*arguments):
    return json.loads(gh(*arguments))


def issue_rows(rows: list[dict]) -> list[dict]:
    # Never infer that missing issues closed from a truncated first page.
    if not isinstance(rows, list) or len(rows) >= ISSUE_LIMIT:
        raise ValueError(
            "Issue inventory needs pagination before it can replace the saved snapshot"
        )
    result = []
    for row in rows:
        number = row.get("number")
        if type(number) is not int or number <= 0:
            raise ValueError("Invalid issue number")
        result.append(
            {
                "number": number,
                "title": " ".join(row["title"].split())[:300],
                "updated_at": row["updatedAt"],
                "url": f"https://github.com/{REPOSITORY}/issues/{number}",
                "labels": sorted(label["name"] for label in row.get("labels", [])),
            }
        )
    if len({row["number"] for row in result}) != len(result):
        raise ValueError("Duplicate issue number")
    return sorted(result, key=lambda row: row["number"])


def run_rows(rows: list[dict], release: dict) -> list[dict]:
    latest = {}
    for row in rows:
        workflow = row.get("path", "").partition("@")[0].removeprefix(".github/workflows/")
        if (
            workflow not in WORKFLOWS
            or (row.get("head_repository") or {}).get("full_name") != REPOSITORY
        ):
            continue
        source_matches = row["head_sha"] == release["target_commitish"] or (
            workflow == "verify-artifacts.yml"
            and row.get("display_title") == f"Verify release / {release['target_commitish']}"
        )
        if (
            row["status"] == "completed"
            and row["updated_at"] < release["published_at"]
            and not source_matches
        ):
            continue
        key = (workflow, row["head_branch"])
        if key in latest and latest[key]["id"] >= row["id"]:
            continue
        latest[key] = {
            "id": row["id"],
            "attempt": row.get("run_attempt", 1),
            "workflow": workflow,
            "branch": row["head_branch"],
            "source_commit": row["head_sha"],
            "status": row["status"],
            "conclusion": row.get("conclusion"),
            "updated_at": row["updated_at"],
            "url": f"https://github.com/{REPOSITORY}/actions/runs/{row['id']}",
        }
    return sorted(latest.values(), key=lambda row: (row["workflow"], row["branch"] or ""))


def collect(previous: dict) -> dict:
    requests = (
        (
            "issue",
            "list",
            "--repo",
            REPOSITORY,
            "--state",
            "open",
            "--limit",
            str(ISSUE_LIMIT),
            "--json",
            "number,title,updatedAt,labels",
        ),
        ("api", f"repos/{REPOSITORY}/actions/runs?per_page={LIMIT}"),
        ("api", f"repos/{REPOSITORY}/releases/latest"),
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(object_from_gh, *arguments) for arguments in requests]
        issues, runs, release = (future.result() for future in futures)
    semver(release["tag_name"].removeprefix("v"))
    if release["draft"] or release["prerelease"] or not release["published_at"]:
        raise ValueError("The stable release must already be published")
    rows = run_rows(runs["workflow_runs"], release)
    old_runs = {row["id"]: row for row in previous.get("runs", [])}
    for row in rows:
        if row["status"] == "completed" and row["conclusion"] != "failure":
            continue
        old = old_runs.get(row["id"], {})
        if (
            row["status"] == "completed"
            and all(
                old.get(field) == row[field]
                for field in ("attempt", "updated_at", "status", "conclusion")
            )
            and "failed_jobs" in old
        ):
            row["failed_jobs"] = old["failed_jobs"]
            if "job_progress" in old:
                row["job_progress"] = old["job_progress"]
            continue
        jobs = object_from_gh(
            "api", f"repos/{REPOSITORY}/actions/runs/{row['id']}/jobs?filter=latest&per_page=100"
        )
        if jobs["total_count"] > 100:
            raise ValueError("This run needs paginated job inspection")
        row["job_progress"] = {
            "total": jobs["total_count"],
            "completed": sum(job.get("status") == "completed" for job in jobs["jobs"]),
            "succeeded": sum(job.get("conclusion") == "success" for job in jobs["jobs"]),
            "active": [
                {
                    "id": job["id"],
                    "name": job["name"],
                    "status": job["status"],
                    "steps": [
                        step["name"]
                        for step in job.get("steps", [])
                        if step.get("status") == "in_progress"
                    ],
                }
                for job in jobs["jobs"]
                if job.get("status") in {"queued", "pending", "waiting", "in_progress"}
            ],
        }
        row["failed_jobs"] = [
            {
                "name": job["name"],
                "id": job["id"],
                "steps": [
                    step["name"]
                    for step in job.get("steps", [])
                    if step.get("conclusion") == "failure"
                ],
            }
            for job in jobs["jobs"]
            if job.get("conclusion") == "failure"
        ]
    return {
        "schema": 1,
        "repository": REPOSITORY,
        "run_window": LIMIT,
        "release": {
            "version": release["tag_name"],
            "published_at": release["published_at"],
            "url": f"https://github.com/{REPOSITORY}/releases/tag/{release['tag_name']}",
        },
        "issues": issue_rows(issues),
        "runs": rows,
    }


def changes(previous: dict, current: dict) -> dict:
    old_issues = {row["number"]: row for row in previous.get("issues", [])}
    new_issues = {row["number"]: row for row in current["issues"]}
    old_runs = {row["id"]: row for row in previous.get("runs", [])}
    comparable = {key: value for key, value in previous.items() if key != "observed_at"}
    return {
        "changed": comparable != current,
        "release": current["release"]["version"],
        "open_issues": len(new_issues),
        "new_or_updated_issues": [
            key for key, row in new_issues.items() if old_issues.get(key) != row
        ],
        "closed_issues": sorted(old_issues.keys() - new_issues.keys()),
        "changed_runs": [row for row in current["runs"] if old_runs.get(row["id"]) != row],
        "failed_runs": sum(
            row["conclusion"] == "failure" or bool(row.get("failed_jobs"))
            for row in current["runs"]
        ),
        "active_runs": sum(row["status"] != "completed" for row in current["runs"]),
    }


def escaped(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+.!|<>])", r"\\\1", " ".join(value.split()))


def markdown(data: dict) -> str:
    lines = [
        "# Automated maintenance status",
        "",
        f"Observed: {data['observed_at']}. Updated by repository events and the scheduled status workflow.",
        "",
        f"Published release: [{data['release']['version']}]({data['release']['url']}). "
        "[Release evidence](RELEASE_STATUS.md) · [Full requirements](PRODUCT_REQUIREMENTS.md).",
        "",
        "This inventory reports GitHub state; issue closure does not prove that an entire product requirement is complete. "
        f"Build observations cover the latest {data['run_window']} runs, retaining the latest relevant run per workflow and branch. "
        "Active builds report job progress and failures from the same observation; completed failures are inspected once per changed attempt. "
        "This automation never retries a build or publishes a release.",
        "",
        f"## Open issues ({len(data['issues'])})",
        "",
        "| Issue | Report | Last activity |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| [#{row['number']}]({row['url']}) | {escaped(row['title'])} | {row['updated_at']} |"
        for row in data["issues"]
    )
    lines.extend(
        [
            "",
            "## Relevant builds",
            "",
            "| Workflow | Branch | State | Evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        f"| {escaped(row['workflow'])} | {escaped(row['branch'] or 'detached')} | {escaped(row['conclusion'] or row['status'])} | [Run {row['id']}]({row['url']}) |"
        for row in data["runs"]
    )
    active = [row for row in data["runs"] if row.get("job_progress", {}).get("active")]
    if active:
        lines.extend(["", "## Active jobs", ""])
        for row in active:
            progress = row["job_progress"]
            lines.append(
                f"[Run {row['id']}]({row['url']}): {progress['completed']}/{progress['total']} "
                f"jobs completed; {progress['succeeded']} succeeded."
            )
            lines.append("")
            lines.extend(
                f"- {escaped(job['name'])}: {escaped(job['status'])}"
                + (f" — {escaped(', '.join(job['steps']))}" if job["steps"] else "")
                + "."
                for job in progress["active"]
            )
            lines.append("")
    failures = [row for row in data["runs"] if row.get("failed_jobs")]
    if failures:
        lines.extend(["", "## Failed jobs", ""])
        for row in failures:
            lines.extend(
                f"- [Run {row['id']}]({row['url']}): {escaped(job['name'])}. Steps: {escaped(', '.join(job['steps']))}."
                for job in row["failed_jobs"]
            )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="Refresh the repository's generated snapshot and guide"
    )
    parser.add_argument(
        "--watch-seconds",
        type=int,
        default=0,
        help="Observe changes for up to 43200 seconds; 0 performs one observation",
    )
    parser.add_argument("--interval", type=int, default=60, help="Watch interval, 30–60 seconds")
    args = parser.parse_args()
    if not 0 <= args.watch_seconds <= 43200 or not 30 <= args.interval <= 60:
        parser.error("Use 0–43200 watch seconds and a 30–60 second interval")
    root = Path(__file__).resolve().parents[1]
    path = root / "deploy/maintenance-status.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    deadline = time.monotonic() + args.watch_seconds
    first = True
    while first or time.monotonic() < deadline:
        current = collect(previous)
        summary = changes(previous, current)
        if args.write and summary["changed"]:
            current["observed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            path.write_text(json.dumps(current, indent=2) + "\n")
            (root / "docs/MAINTENANCE_STATUS.md").write_text(markdown(current))
        if first or summary["changed"]:
            print(json.dumps(summary), flush=True)
        previous, first = current, False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))


if __name__ == "__main__":
    main()
