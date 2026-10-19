"""Publish one version-specific readiness record without making release decisions."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .published_release import API, ORIGIN, REPOSITORY, fetch, manifest, version

API_ROOT = f"https://api.github.com/repos/{REPOSITORY}"
WORKFLOWS = {
    "ci.yml": "Product checks on the release source",
    "release.yml": "Native packages and installed-workspace release gates",
    "verify-artifacts.yml": "Independent uploaded-byte and signature verification",
    "public-updates.yml": "Automatic upgrades from public installers",
    "website-release.yml": "Live website downloads, version, notes and guides",
}
STATES = ("Shipped", "Partial", "Building", "Planned", "Ongoing", "External")


def timestamp(value: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Missing release evidence time")
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError("Release evidence time requires a timezone")
    return instant


def api(path: str) -> dict:
    result = json.loads(fetch(f"{API_ROOT}/{path}", api=True))
    if not isinstance(result, dict):
        raise ValueError("Invalid GitHub evidence response")
    return result


def requirement_counts(contents: str) -> dict:
    rows = re.findall(r"^\| ([A-Z][0-9]{2}) \| [^|\n]+ \| ([^|\n]+) \|", contents, re.M)
    if not rows or len({key for key, _ in rows}) != len(rows):
        raise ValueError("The requirements checklist must have unique identifiers")
    counts = Counter(state for _, state in rows)
    if counts.keys() - set(STATES):
        raise ValueError("Unknown requirements status")
    return {"total": len(rows), **{state: counts[state] for state in STATES}}


def installers(published: dict) -> list[dict]:
    assets = {asset["name"]: asset for asset in published["assets"]}
    result = []
    for platform, extension in (("windows", "exe"), ("macos", "dmg"), ("linux", "AppImage")):
        for arch in ("x64", "arm64"):
            artifact_arch = "x86_64" if (platform, arch) == ("linux", "x64") else arch
            name = (
                f"Mnemion-Studio-{published['tag_name'][1:]}-{platform}-{artifact_arch}.{extension}"
            )
            if name in assets:
                result.append(
                    {
                        "platform": platform,
                        "arch": arch,
                        "url": assets[name]["browser_download_url"],
                    }
                )
    return result


def gate(
    runs: dict,
    workflow: str,
    source: str,
    *,
    published_at: str,
    assets_updated_at: str,
    published_tag: str | None = None,
) -> dict:
    """Only same-repository, exact-source runs can become passing evidence."""
    result = {
        "name": WORKFLOWS[workflow],
        "status": "not recorded",
        "url": f"{ORIGIN}/actions/workflows/{workflow}",
    }
    candidates = []
    for run in runs.get("workflow_runs", []):
        source_matches = run.get("head_sha") == source or (
            workflow == "verify-artifacts.yml"
            and run.get("event") == "workflow_run"
            and run.get("display_title") == f"Verify release / {source}"
        )
        if (
            not source_matches
            or run.get("head_repository", {}).get("full_name") != REPOSITORY
            or run.get("path", "").partition("@")[0] != f".github/workflows/{workflow}"
            or run.get("event") not in {"push", "release", "workflow_dispatch", "workflow_run"}
        ):
            continue
        # Automatic token-based publication explicitly dispatches these jobs.
        # Accept only a source-tagged dispatch whose workflow title identifies
        # this exact version and, for upgrades, the complete platform selection.
        tag = published_tag
        dispatch_matches = (
            run.get("event") == "workflow_dispatch"
            and isinstance(tag, str)
            and re.fullmatch(r"v\d+\.\d+\.\d+", tag) is not None
            and run.get("head_branch") == tag
            and run.get("display_title")
            == (
                f"Public updates / {tag} / all / all"
                if workflow == "public-updates.yml"
                else f"Public website / {tag}"
            )
        )
        if workflow in {"public-updates.yml", "website-release.yml"} and (
            (run.get("event") != "release" and not dispatch_matches)
            or timestamp(run["created_at"]) < timestamp(published_at)
        ):
            continue
        if type(run.get("id")) is not int or run["id"] <= 0:
            raise ValueError("Invalid evidence run identifier")
        if run.get("html_url") != f"{ORIGIN}/actions/runs/{run['id']}":
            raise ValueError("Evidence link belongs to another repository")
        timestamp(run["updated_at"])
        candidates.append(run)
    if not candidates:
        return result
    run = max(candidates, key=lambda item: (timestamp(item["updated_at"]), item["id"]))
    result.update(
        {
            "run_id": run["id"],
            "url": run["html_url"],
            "updated_at": run["updated_at"],
            "event": run.get("event"),
            "conclusion": run.get("conclusion"),
        }
    )
    if run.get("status") != "completed":
        result["status"] = "pending"
    elif run.get("conclusion") == "success":
        result["status"] = "passed"
        if workflow in {
            "verify-artifacts.yml",
            "public-updates.yml",
            "website-release.yml",
        } and timestamp(assets_updated_at) > timestamp(run["updated_at"]):
            result["status"] = "recheck required"
    else:
        result["status"] = "not passed"
    return result


def public_upgrade_coverage(result: dict, jobs: dict, targets: list[dict]) -> dict:
    if result["status"] != "passed":
        return result
    expected = {f"{target['platform']} / {target['arch']} public upgrade" for target in targets}
    passed = {
        job.get("name")
        for job in jobs.get("jobs", [])
        if job.get("status") == "completed" and job.get("conclusion") == "success"
    }
    if not expected or not expected <= passed:
        return {**result, "status": "incomplete", "missing_targets": sorted(expected - passed)}
    return {**result, "targets_passed": len(expected)}


def complete_jobs(run_id: int, source: str) -> dict[str, dict]:
    """GitHub's latest filter includes the retained successful jobs of a retry."""
    rows = []
    expected = None
    for page in range(1, 11):
        data = api(f"actions/runs/{run_id}/jobs?filter=latest&per_page=100&page={page}")
        total, jobs = data.get("total_count"), data.get("jobs")
        if (
            type(total) is not int
            or not 0 < total <= 1000
            or (expected is not None and total != expected)
            or not isinstance(jobs, list)
            or not jobs
            or len(jobs) > 100
        ):
            raise ValueError("Incomplete release job inventory")
        expected = total
        rows.extend(jobs)
        if len(rows) >= total:
            break
    if len(rows) != expected:
        raise ValueError("Incomplete release job inventory")
    names, ids = {}, set()
    for job in rows:
        name = job.get("name")
        if (
            not isinstance(name, str)
            or not 0 < len(name) <= 300
            or name in names
            or type(job.get("id")) is not int
            or job["id"] <= 0
            or job["id"] in ids
            or job.get("run_id") != run_id
            or job.get("head_sha") != source
            or not isinstance(job.get("steps"), list)
        ):
            raise ValueError("Release jobs must belong to the exact source and run")
        names[name] = job
        ids.add(job["id"])
    return names


def reuse_release_checks(ci: dict, release: dict, source: str) -> dict:
    """A superseded branch run can use the same complete reusable CI suite."""
    if (
        ci.get("status") != "not passed"
        or ci.get("conclusion") != "cancelled"
        or ci.get("event") != "push"
        or release.get("status") != "passed"
        or timestamp(release["updated_at"]) < timestamp(ci["updated_at"])
    ):
        return ci
    standalone = complete_jobs(ci["run_id"], source)
    # A cancellation after an actual failure must not conceal that failure.
    if any(
        job.get("status") != "completed"
        or job.get("conclusion") not in {"success", "cancelled", "skipped"}
        or any(
            step.get("conclusion") in {"failure", "timed_out", "action_required"}
            for step in job["steps"]
        )
        for job in standalone.values()
    ):
        return ci
    embedded = {
        name.removeprefix("checks / "): job
        for name, job in complete_jobs(release["run_id"], source).items()
        if name.startswith("checks / ")
    }
    # Equality retains every matrix target, including future jobs. It also
    # refuses an incomplete branch inventory or a differently structured suite.
    if set(embedded) != set(standalone) or any(
        job.get("status") != "completed"
        or job.get("conclusion") != "success"
        or any(
            step.get("conclusion") in {"failure", "timed_out", "action_required"}
            for step in job["steps"]
        )
        for job in embedded.values()
    ):
        return ci
    return {
        **ci,
        "status": "passed",
        "conclusion": "success",
        "run_id": release["run_id"],
        "event": release.get("event"),
        "url": release["url"],
        "updated_at": release["updated_at"],
        "evidence": "complete reusable Product checks",
        "jobs_passed": len(embedded),
        "superseded_run_id": ci["run_id"],
        "superseded_url": ci["url"],
        "standalone_conclusion": "cancelled",
        "standalone_event": ci["event"],
    }


def collect(root: Path) -> dict:
    release = json.loads(fetch(API, api=True))
    tag = release.get("tag_name")
    version(tag)
    published = manifest(release, fetch(f"{ORIGIN}/releases/download/{tag}/SHA256SUMS.txt"))
    target = api(f"git/ref/tags/{tag}").get("object", {})
    for _ in range(3):
        if not re.fullmatch(r"[a-f0-9]{40}", target.get("sha", "")):
            raise ValueError("Invalid release tag target")
        if target.get("type") == "commit":
            break
        if target.get("type") != "tag":
            raise ValueError("Release tag does not identify source")
        target = api(f"git/tags/{target['sha']}").get("object", {})
    if (
        target.get("type") != "commit"
        or not re.fullmatch(r"[a-f0-9]{40}", target.get("sha", ""))
        or target.get("sha") != release.get("target_commitish")
    ):
        raise ValueError("Release and tag must identify the same explicit source commit")
    source = target["sha"]
    assets_updated = max(release["assets"], key=lambda asset: timestamp(asset["updated_at"]))[
        "updated_at"
    ]
    targets = installers(published)
    gates = []
    for workflow in WORKFLOWS:
        selection = (
            "per_page=30"
            if workflow == "verify-artifacts.yml"
            else f"head_sha={source}&per_page=10"
        )
        runs = api(f"actions/workflows/{workflow}/runs?{selection}")
        result = gate(
            runs,
            workflow,
            source,
            published_at=published["published_at"],
            assets_updated_at=assets_updated,
            published_tag=tag,
        )
        if workflow == "public-updates.yml" and result["status"] == "passed":
            result = public_upgrade_coverage(
                result,
                api(f"actions/runs/{result['run_id']}/jobs?filter=latest&per_page=100"),
                targets,
            )
        gates.append(result)
    gates[0] = reuse_release_checks(gates[0], gates[1], source)
    return {
        "schema": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tag_name": tag,
        "source_commit": source,
        "published_at": published["published_at"],
        "release_url": published["html_url"],
        "availability": "published",
        "release_checks": "passed"
        if all(item["status"] == "passed" for item in gates)
        else "evidence incomplete",
        "asset_count": len(published["assets"]),
        "checksum_digest": next(
            asset["digest"] for asset in published["assets"] if asset["name"] == "SHA256SUMS.txt"
        ),
        "platforms": targets,
        "gates": gates,
        "requirements": requirement_counts(
            (root / "docs/PRODUCT_REQUIREMENTS.md").read_text(encoding="utf-8")
        ),
    }


def markdown(data: dict) -> str:
    scope = data["requirements"]
    percent = 100 * scope["Shipped"] / scope["total"]
    lines = [
        "# Current release status",
        "",
        "<!-- Generated by deploy/release_status.py. Edit the generator, not this record. -->",
        "",
        f"**{data['tag_name']} is published. Release-check evidence: {data['release_checks']}.**",
        f"Checked {data['checked_at']}; published {data['published_at']}.",
        "",
        "[Download Mnemion](https://www.perseusxr.com/mnemion) · "
        f"[This release]({data['release_url']}) · "
        "[Machine-readable status](../deploy/release-status.json)",
        "",
        f"Source: `{data['source_commit']}`. Verified inventory: {data['asset_count']} assets.",
        f"Checksum-file digest: `{data['checksum_digest']}`.",
        "",
        "## Available downloads",
        "",
        "| Platform | Architecture | Installer |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {item['platform']} | {item['arch']} | [Download]({item['url']}) |"
        for item in data["platforms"]
    ]
    lines += [
        "",
        "## Version-specific release evidence",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {item['name']} | {item['status']} | [Workflow]({item['url']}) |"
        for item in data["gates"]
    ]
    for item in data["gates"]:
        if item.get("evidence") == "complete reusable Product checks":
            lines += [
                "",
                f"Product checks passed as all {item['jobs_passed']} matching jobs inside the "
                f"exact-source release workflow. The [separate branch run]({item['superseded_url']}) "
                "was superseded and cancelled; its cancellation is not counted as a pass.",
            ]
    lines += [
        "",
        "Passing evidence belongs to the exact release source. Public upgrade evidence",
        "must cover every advertised platform and architecture. Missing, running, failed,",
        "cancelled or outdated checks never count as passed. These checks do not claim",
        "that every customer's computer or independently hosted server has updated.",
        "",
        "## Full product scope",
        "",
        f"**{scope['Shipped']} of {scope['total']} requirements shipped ({percent:g}% strict coverage).**",
        ", ".join(f"{scope[state]} {state.lower()}" for state in STATES if state != "Shipped")
        + ".",
        "",
        "This count measures completed requirements, not code, effort or app usability.",
        "A published release does not mean every roadmap item or reported issue is done.",
        "See the [complete checklist](PRODUCT_REQUIREMENTS.md), [roadmap](ROADMAP.md)",
        f"and [open issues]({ORIGIN}/issues?q=is%3Aissue+is%3Aopen).",
        "",
        "## Which announcement applies",
        "",
        "This current record supersedes earlier availability assessments for older",
        "versions. The 10 October pre-release assessment was followed by publication",
        "of [4.0.0 for macOS and Linux](releases/4.0.0.md). By the",
        "[4.0.7 all-platform announcement](releases/4.0.7.md), Windows downloads were",
        "also published. Those are dated availability milestones; use the version and",
        "gate evidence above for the current decision.",
        "",
        "Every new release/status announcement must state its version, available",
        "platforms, passed and outstanding gates, and which earlier assessment it",
        "supersedes. Link this record, and keep full-roadmap progress separate.",
        "Creating this record does not send email or publish a release.",
        "",
        "The record refreshes automatically after release/check events and on a",
        "schedule. [Workflow](../.github/workflows/release-status.yml). If a refresh",
        "fails, the last record remains dated; check the linked workflow before",
        "treating old evidence as current.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data = collect(root)
    output = root / "deploy/release-status.json"
    document = root / "docs/RELEASE_STATUS.md"
    if output.is_symlink() or document.is_symlink():
        raise ValueError("Status outputs must be regular files")
    if output.exists() and version(json.loads(output.read_text())["tag_name"]) > version(
        data["tag_name"]
    ):
        raise ValueError("Refusing to replace a newer release status")
    output.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    document.write_text(markdown(data), encoding="utf-8")
    # Retain each version's final observed gates even after the live record
    # advances; future releases need no hand-copied status JSON or percentages.
    archive = root / "docs/validation/releases"
    archive.mkdir(parents=True, exist_ok=True)
    snapshot = archive / (data["tag_name"][1:] + "-status.json")
    if snapshot.is_symlink():
        raise ValueError("Release evidence must be an ordinary file")
    snapshot.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Release status: {data['tag_name']}, {data['release_checks']}")


if __name__ == "__main__":
    main()
