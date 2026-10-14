"""Associate reviewed fixes with their verified public release, without posting messages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .published_release import REPOSITORY
from .release_automation import gh, semver


def reconcile(root: Path, *, apply=False) -> dict:
    record = json.loads((root / "deploy/issue-releases.json").read_text())
    if record.get("schema") != 1 or not isinstance(record.get("releases"), dict):
        raise ValueError("Use the reviewed issue-to-release mapping")
    result = {"eligible": {}, "pending": [], "labeled": 0, "closed": 0}
    for version, issues in record["releases"].items():
        semver(version)
        if (
            not isinstance(issues, list)
            or len(issues) > 200
            or any(type(number) is not int or number <= 0 for number in issues)
            or len(set(issues)) != len(issues)
        ):
            raise ValueError("Use distinct positive issue numbers")
        path = root / f"docs/validation/releases/{version}-status.json"
        evidence = json.loads(path.read_text()) if path.exists() else {}
        if (
            evidence.get("release_checks") != "passed"
            or evidence.get("availability") != "published"
            or evidence.get("tag_name") != "v" + version
        ):
            result["pending"].append(version)
            continue
        release = json.loads(gh("api", f"repos/{REPOSITORY}/releases/tags/v{version}"))
        if (
            release.get("draft") is not False
            or release.get("prerelease") is not False
            or not release.get("published_at")
            or release.get("target_commitish") != evidence.get("source_commit")
            or release.get("tag_name") != "v" + version
        ):
            raise ValueError("The fixing release no longer matches its passing public evidence")
        result["eligible"][version] = issues
        label = "fixed-in:" + version
        if apply:
            labels = json.loads(
                gh(
                    "label",
                    "list",
                    "--repo",
                    REPOSITORY,
                    "--search",
                    label,
                    "--limit",
                    "100",
                    "--json",
                    "name",
                )
                or "[]"
            )
            if not any(item["name"] == label for item in labels):
                gh(
                    "label",
                    "create",
                    label,
                    "--repo",
                    REPOSITORY,
                    "--color",
                    "0E8A16",
                    "--description",
                    f"Fix available: https://github.com/{REPOSITORY}/releases/tag/v{version}",
                )
        for number in issues:
            issue = json.loads(
                gh("issue", "view", str(number), "--repo", REPOSITORY, "--json", "state,labels")
            )
            first_label = label not in {item["name"] for item in issue["labels"]}
            # Reopened reports keep their version label and stay open. A fixed
            # issue must not be silently closed again by a scheduled replay.
            if issue["state"] == "OPEN" and first_label:
                result["closed"] += 1
                if apply:
                    gh("issue", "close", str(number), "--repo", REPOSITORY, "--reason", "completed")
            if first_label:
                result["labeled"] += 1
                if apply:
                    gh("issue", "edit", str(number), "--repo", REPOSITORY, "--add-label", label)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(reconcile(Path(__file__).resolve().parents[1], apply=args.apply)))


if __name__ == "__main__":
    main()
