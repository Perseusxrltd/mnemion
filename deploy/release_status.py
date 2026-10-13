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
    runs: dict, workflow: str, source: str, *, published_at: str, assets_updated_at: str
) -> dict:
    """Only same-repository, exact-source runs can become passing evidence."""
    result = {
        "name": WORKFLOWS[workflow],
        "status": "not recorded",
        "url": f"{ORIGIN}/actions/workflows/{workflow}",
    }
    candidates = []
    for run in runs.get("workflow_runs", []):
        if (
            run.get("head_sha") != source
            or run.get("head_repository", {}).get("full_name") != REPOSITORY
            or run.get("path", "").partition("@")[0] != f".github/workflows/{workflow}"
            or run.get("event") not in {"push", "release", "workflow_dispatch", "workflow_run"}
        ):
            continue
        # Dispatches can select only one target, or another version. A complete
        # release-event rehearsal is the automatic all-published-target gate.
        if workflow in {"public-updates.yml", "website-release.yml"} and (
            run.get("event") != "release" or timestamp(run["created_at"]) < timestamp(published_at)
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
    result.update({"run_id": run["id"], "url": run["html_url"], "updated_at": run["updated_at"]})
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
        runs = api(f"actions/workflows/{workflow}/runs?head_sha={source}&per_page=10")
        result = gate(
            runs,
            workflow,
            source,
            published_at=published["published_at"],
            assets_updated_at=assets_updated,
        )
        if workflow == "public-updates.yml" and result["status"] == "passed":
            result = public_upgrade_coverage(
                result,
                api(f"actions/runs/{result['run_id']}/jobs?filter=latest&per_page=100"),
                targets,
            )
        gates.append(result)
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
    print(f"Release status: {data['tag_name']}, {data['release_checks']}")


if __name__ == "__main__":
    main()
