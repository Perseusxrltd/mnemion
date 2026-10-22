import subprocess

import pytest

from deploy.ci_scope import documentation, scope


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("README.md", True),
        ("docs/service/agents.md", True),
        ("deploy/issue-releases.json", True),
        ("deploy/research-watch.json", True),
        ("deploy/research_watch.py", False),
        ("docs/validation/releases/4.30.2-status.json", True),
        ("docs/validation/2026-10-22-l1-release-native-acceptance.json", True),
        ("docs/validation/2026-10-13-v4_1_6-hosted-verification.json", True),
        ("docs/validation/current.json", False),
        ("docs/validation/2026-10-22-native.json.py", False),
        ("docs/validation/2026-10-22-fixtures/records.json", False),
        ("docs/validation/../../mnemion/2026-10-22-native.json", False),
        ("docs/service/openapi.json", False),
        ("mnemion/service/README.md", False),
        ("service_tests/fixtures/README.md", False),
        ("deploy/release-targets.json", False),
        (".github/workflows/ci.yml", False),
        ("../README.md", False),
        ("/README.md", False),
        ("", False),
    ],
)
def test_only_reviewed_documentation_and_metadata_paths_skip_runtime_checks(path, expected):
    assert documentation(path) is expected


def test_real_push_diff_preserves_release_pr_and_renamed_source_checks(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "--quiet")
    git("config", "user.name", "Mnemion CI fixture")
    git("config", "user.email", "ci@example.invalid")
    (tmp_path / "README.md").write_text("Original guide\n")
    (tmp_path / "runtime.py").write_text("def run():\n    return 1\n")
    git("add", ".")
    git("commit", "--quiet", "-m", "Initial fixture")
    before = git("rev-parse", "HEAD")
    (tmp_path / "README.md").write_text("Updated guide\n")
    evidence = tmp_path / "docs/validation/2026-10-22-native-acceptance.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"scope":"dated validation report"}\n')
    git("add", "README.md", str(evidence.relative_to(tmp_path)))
    git("commit", "--quiet", "-m", "Update the guide and its dated evidence")
    after = git("rev-parse", "HEAD")
    event = {"before": before, "after": after}
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "reason": "documentation_only",
    }
    for event_name, release in [
        ("push", True),
        ("pull_request", False),
        ("workflow_dispatch", False),
    ]:
        assert scope(tmp_path, event, event_name=event_name, release=release)["runtime"]
    assert scope(tmp_path, {"before": "f" * 40, "after": after}, event_name="push")["runtime"]
    assert scope(tmp_path, {"before": before, "after": before}, event_name="push")["runtime"]
    assert scope(tmp_path, {}, event_name="push")["runtime"]
    # A rename into the documentation allowlist must retain the removed source
    # path in the comparison; Git's ordinary rename display can hide that path.
    git("mv", "runtime.py", "old-runtime.md")
    git("commit", "--quiet", "-am", "Move the fixture source")
    renamed = {"before": after, "after": git("rev-parse", "HEAD")}
    assert scope(tmp_path, renamed, event_name="push")["runtime"]
