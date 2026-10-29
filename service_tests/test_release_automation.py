"""Automatic publication is conditional, source-specific and safe to resume."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from deploy import release_automation as subject

REPO = "example/mnemion"
COMMIT = "a" * 40


def test_prepare_coverage_uses_the_regenerated_agent_contract(tmp_path, monkeypatch):
    from deploy import telemetry_actions, telemetry_coverage

    root = Path(subject.__file__).resolve().parents[1]
    for name in telemetry_coverage.INPUTS:
        relative = telemetry_coverage.OUTPUT.parent / name
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    for name in telemetry_actions.INPUTS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    contract_path = tmp_path / "mnemion/service/agent_contract.json"
    initial = contract_path.read_bytes()
    validated = []

    def command(arguments, *, cwd, check):
        assert cwd == tmp_path and check
        if arguments[1:] == [
            "-m",
            "mnemion.service.cli",
            "schema",
            "--output",
            "docs/service/openapi.json",
        ]:
            return
        if arguments[1:] == [
            "-m",
            "mnemion.service.cli",
            "agent-schema",
            "--output",
            "mnemion/service/agent_contract.json",
        ]:
            contract = json.loads(initial)
            contract["operations"][0]["summary"] = "Updated interface fixture"
            contract_path.write_text(json.dumps(contract))
            return
        if arguments[1:] == ["-m", "deploy.telemetry_coverage", "--write"]:
            (tmp_path / telemetry_coverage.OUTPUT).write_text(telemetry_coverage.render(tmp_path))
            return
        assert arguments[1:] == ["deploy/release.py"]
        assert contract_path.read_bytes() != initial
        # The real source-hash check must accept the post-export contract.
        # Generating coverage earlier reproduces the original stale-hash error.
        telemetry_coverage.verify(tmp_path)
        validated.append(True)

    monkeypatch.setattr(subject, "__file__", str(tmp_path / "deploy/release_automation.py"))
    monkeypatch.setattr(subject, "prepare", lambda *_: [])
    monkeypatch.setattr(subject.sys, "argv", ["release_automation", "prepare", "4.2.3"])
    monkeypatch.setattr(subject.subprocess, "run", command)
    subject.main()
    assert validated == [True]


@pytest.fixture
def fixture(monkeypatch):
    release = {
        "id": 17,
        "tag_name": "v4.2.3",
        "target_commitish": COMMIT,
        "draft": True,
        "prerelease": False,
        "body": "Reviewed release notes.",
        "published_at": "2026-10-13T16:00:00Z",
        "html_url": f"https://github.com/{REPO}/releases/tag/v4.2.3",
        "assets": [
            {
                "id": 1,
                "name": "SHA256SUMS.txt",
                "state": "uploaded",
                "size": 128,
                "digest": "sha256:" + "b" * 64,
            }
        ],
    }
    state = SimpleNamespace(
        release=release,
        latest={"tag_name": "v4.2.2"},
        comparison={"status": "ahead"},
        verifier={
            "path": ".github/workflows/verify-artifacts.yml",
            "event": "workflow_run",
            "repository": {"full_name": REPO},
            "head_repository": {"full_name": REPO},
        },
        jobs={"jobs": [{"name": "verify", "status": "completed", "conclusion": "success"}]},
        tag=COMMIT,
        existing=False,
        calls=[],
    )
    state.receipt = {
        "repository": REPO,
        "version": "4.2.3",
        "source_commit": COMMIT,
        "release_run": 99,
        "release_id": 17,
        "exact_source_production_validator_passed": True,
        "asset_ids_sizes_digests_unchanged_after_verification": True,
        "inventory": [{k: release["assets"][0][k] for k in ("id", "name", "size", "digest")}],
    }

    def api(repo, path):
        assert repo == REPO
        if path == "actions/runs/100":
            return state.verifier
        if path.startswith("actions/runs/100/jobs?"):
            return state.jobs
        if path == f"compare/{COMMIT}...main":
            return state.comparison
        if path == "releases/17":
            return copy.deepcopy(state.release)
        if path == "releases/latest":
            return state.latest
        if path == "git/ref/tags/v4.2.3":
            return {"object": {"type": "commit", "sha": state.tag}}
        if path.startswith("actions/workflows/"):
            return {
                "workflow_runs": [
                    {
                        "head_sha": COMMIT,
                        "event": "workflow_dispatch",
                        "created_at": "2026-10-13T16:00:01Z",
                        "display_title": "Public updates / v4.2.3 / all / all"
                        if "public-updates.yml" in path
                        else "Public website / v4.2.3",
                    }
                ]
                if state.existing
                else []
            }
        raise AssertionError(path)

    def gh(*args):
        state.calls.append(args)
        if args == ("api", f"repos/{REPO}/git/matching-refs/tags/v4.2.3"):
            return json.dumps(
                [{"ref": "refs/tags/v4.2.3", "object": {"type": "commit", "sha": state.tag}}]
            )
        if args[:2] == ("release", "edit"):
            state.release["draft"] = False
            return ""
        assert args[:2] == ("workflow", "run"), args
        return ""

    monkeypatch.setattr(subject, "api", api)
    monkeypatch.setattr(subject, "gh", gh)
    monkeypatch.setattr(subject, "release_run", lambda *_: {"head_sha": COMMIT})
    return state


@pytest.mark.parametrize(
    "failure",
    [
        "foreign",
        "failed",
        "changed_assets",
        "changed_source",
        "not_on_main",
        "newer_release",
        "wrong_tag",
        "missing_proof",
    ],
)
def test_failed_or_changed_evidence_stops_before_publication(fixture, failure):
    if failure == "foreign":
        fixture.verifier["head_repository"]["full_name"] = "foreign/repo"
    elif failure == "failed":
        fixture.jobs["jobs"][0]["conclusion"] = "failure"
    elif failure == "changed_assets":
        fixture.release["assets"][0]["digest"] = "sha256:" + "c" * 64
    elif failure == "changed_source":
        fixture.receipt["source_commit"] = "d" * 40
    elif failure == "not_on_main":
        fixture.comparison["status"] = "diverged"
    elif failure == "newer_release":
        fixture.latest["tag_name"] = "v4.2.4"
    elif failure == "wrong_tag":
        fixture.tag = "e" * 40
    else:
        fixture.receipt["exact_source_production_validator_passed"] = False
    with pytest.raises(ValueError):
        subject.publish(REPO, fixture.receipt, 100)
    assert fixture.release["draft"] is True
    assert all(call[0] == "api" for call in fixture.calls)


def test_publication_dispatches_complete_checks_and_resume_does_not_repeat_them(fixture):
    result = subject.publish(REPO, fixture.receipt, 100)
    assert (
        result["uploaded_inventory_unchanged_at_publication"]
        and result["tag_matches_verified_source"]
    )
    mutations = [call for call in fixture.calls if call[0] != "api"]
    assert len(mutations) == 3 and mutations[0][:2] == ("release", "edit")
    assert mutations[-1][-6:] == (
        "-f",
        "tag=v4.2.3",
        "-f",
        "platform=all",
        "-f",
        "architecture=all",
    )
    fixture.existing = True
    fixture.calls.clear()
    resumed = subject.publish(REPO, fixture.receipt, 100)
    assert set(resumed["followups"].values()) == {"existing"}
    assert all(call[0] == "api" for call in fixture.calls)


def test_dry_run_checks_evidence_without_mutating_or_dispatching(fixture):
    assert subject.publish(REPO, fixture.receipt, 100, dry_run=True)["ready"]
    assert fixture.release["draft"] is True
    assert all(call[0] == "api" for call in fixture.calls)


def test_delayed_job_metadata_settles_before_the_single_publication(fixture, monkeypatch):
    original = subject.api
    replies = [
        {"jobs": []},
        {"jobs": [{"name": "verify", "status": "in_progress", "conclusion": None}]},
        fixture.jobs,
    ]
    clock = [0.0]
    monkeypatch.setattr(subject, "monotonic", lambda: clock[0])
    monkeypatch.setattr(subject, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def api(repo, path):
        if path.startswith("actions/runs/100/jobs?"):
            assert fixture.release["draft"]
            assert not fixture.calls
            return replies.pop(0)
        return original(repo, path)

    monkeypatch.setattr(subject, "api", api)
    result = subject.publish(REPO, fixture.receipt, 100)
    assert not replies and clock[0] == 4
    assert result["uploaded_inventory_unchanged_at_publication"]
    assert sum(call[:2] == ("release", "edit") for call in fixture.calls) == 1


@pytest.mark.parametrize("missing", [True, False])
def test_unsettled_metadata_has_a_finite_read_only_wait(fixture, monkeypatch, missing):
    fixture.jobs = {"jobs": [] if missing else [{"name": "verify", "status": "queued"}]}
    clock = [0.0]
    monkeypatch.setattr(subject, "monotonic", lambda: clock[0])
    monkeypatch.setattr(subject, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    with pytest.raises(ValueError, match="verification job must have passed"):
        subject.publish(REPO, fixture.receipt, 100)
    assert clock[0] == 60
    assert fixture.release["draft"] and not fixture.calls


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral"])
def test_terminal_verification_rejection_never_waits_or_publishes(fixture, monkeypatch, conclusion):
    fixture.jobs["jobs"][0]["conclusion"] = conclusion
    monkeypatch.setattr(subject, "sleep", lambda _: pytest.fail("A rejection must not be retried"))
    with pytest.raises(ValueError, match="verification job must have passed"):
        subject.publish(REPO, fixture.receipt, 100)
    assert fixture.release["draft"] and not fixture.calls


def test_ambiguous_verification_jobs_never_choose_the_passing_one(fixture, monkeypatch):
    fixture.jobs["jobs"].append({"name": "verify", "status": "in_progress", "conclusion": None})
    monkeypatch.setattr(subject, "sleep", lambda _: pytest.fail("Ambiguous proof must be rejected"))
    with pytest.raises(ValueError, match="verification job must have passed"):
        subject.publish(REPO, fixture.receipt, 100)
    assert fixture.release["draft"] and not fixture.calls


def test_verification_api_failure_does_not_retry_or_publish(fixture, monkeypatch):
    original = subject.api

    def api(repo, path):
        if path.startswith("actions/runs/100/jobs?"):
            raise RuntimeError("unavailable")
        return original(repo, path)

    monkeypatch.setattr(subject, "api", api)
    monkeypatch.setattr(
        subject, "sleep", lambda _: pytest.fail("An API failure must not be retried")
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        subject.publish(REPO, fixture.receipt, 100)
    assert fixture.release["draft"] and not fixture.calls


def _release_tree(
    tmp_path: Path,
    *,
    source: str,
    target: str,
    allowlist: list[dict],
    distribution_separator: str = " ",
    maximum_slots: int = 32,
) -> None:
    def write(name, text):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    for directory, name in (
        (Path("."), "mnemion"),
        (Path("studio/client"), "mnemion-desktop-build"),
    ):
        write(directory / "pyproject.toml", f'[project]\nname = "{name}"\nversion = "{source}"\n')
        write(
            directory / "uv.lock",
            f'[[package]]\nname = "{name}"\nversion = "{source}"\n\n'
            '[[package]]\nname = "unrelated"\nversion = "4.2.2"\n',
        )
    write("mnemion/version.py", f'__version__ = "{source}"\n')
    write(f"docs/releases/{target}.md", f"# Mnemion {target}\n\nConcrete changes.\n")
    write(
        "docs/ROADMAP.md",
        f"Reviewed source distribution: **{source}**."
        + distribution_separator
        + "Roadmap updated: **2026-10-13**.\n\nUnfinished scope remains.\n",
    )
    write(
        "deploy/release-targets.json",
        json.dumps({"version": source, "platforms": ["windows", "macos", "linux"]}),
    )
    write(
        "mnemion/product_telemetry/wire-v3.json",
        json.dumps(
            {
                "release_coordinate": {"minimum": 0, "maximum": 255},
                "allowlist_maximum_slots": maximum_slots,
                "release_allowlist": allowlist,
            },
            indent=2,
        )
        + "\n",
    )
    for directory in ("packages/client", "studio/frontend", "studio/electron"):
        for name in ("package.json", "package-lock.json"):
            write(
                f"{directory}/{name}",
                json.dumps(
                    {
                        "version": source,
                        "packages": {
                            "": {"version": source},
                            "../../packages/client": {"version": source},
                            "node_modules/unrelated": {"version": "4.2.2"},
                        },
                    }
                ),
            )


def _tree_text(tmp_path: Path) -> dict[str, str]:
    return {
        path.relative_to(tmp_path).as_posix(): path.read_text()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    "distribution_separator",
    [
        " ",
        "\nPublic distribution: [current release status](RELEASE_STATUS.md). ",
    ],
)
def test_version_preparation_preserves_unrelated_pins_and_is_repeatable(
    tmp_path, distribution_separator
):
    _release_tree(
        tmp_path,
        source="4.2.2",
        target="4.2.3",
        allowlist=[{"slot": 0, "major": 4, "minor": 2, "patch": 2, "id": "4.2.2"}],
        distribution_separator=distribution_separator,
    )
    assert subject.prepare(tmp_path, "4.2.3")
    assert subject.prepare(tmp_path, "4.2.3") == []
    assert 'name = "unrelated"\nversion = "4.2.2"' in (tmp_path / "uv.lock").read_text()
    data = json.loads((tmp_path / "studio/frontend/package-lock.json").read_text())
    assert data["packages"]["../../packages/client"]["version"] == "4.2.3"
    assert data["packages"]["node_modules/unrelated"]["version"] == "4.2.2"
    assert (tmp_path / "docs/ROADMAP.md").read_text() == (
        "Reviewed source distribution: **4.2.3**."
        + distribution_separator
        + f"Roadmap updated: **{subject.datetime.now(subject.timezone.utc).date().isoformat()}**."
        + "\n\nUnfinished scope remains.\n"
    )


def test_prepare_adds_current_and_target_release_cohorts(tmp_path):
    _release_tree(
        tmp_path,
        source="4.2.2",
        target="4.2.3",
        allowlist=[{"slot": 0, "major": 4, "minor": 2, "patch": 1, "id": "4.2.1"}],
    )
    changed = subject.prepare(tmp_path, "4.2.3")
    assert "mnemion/product_telemetry/wire-v3.json" in changed
    catalog = json.loads((tmp_path / "mnemion/product_telemetry/wire-v3.json").read_text())
    assert catalog["release_allowlist"] == [
        {"slot": 0, "major": 4, "minor": 2, "patch": 1, "id": "4.2.1"},
        {"slot": 1, "major": 4, "minor": 2, "patch": 2, "id": "4.2.2"},
        {"slot": 2, "major": 4, "minor": 2, "patch": 3, "id": "4.2.3"},
    ]
    assert (tmp_path / "mnemion/version.py").read_text() == '__version__ = "4.2.3"\n'
    assert subject.prepare(tmp_path, "4.2.3") == []


def test_prepare_retains_at_most_32_release_cohorts(tmp_path):
    _release_tree(
        tmp_path,
        source="1.0.0",
        target="1.0.32",
        allowlist=[
            {"slot": index, "major": 1, "minor": 0, "patch": index, "id": f"1.0.{index}"}
            for index in range(32)
        ],
    )
    subject.prepare(tmp_path, "1.0.32")
    catalog = json.loads((tmp_path / "mnemion/product_telemetry/wire-v3.json").read_text())
    cohorts = catalog["release_allowlist"]
    assert [item["slot"] for item in cohorts] == list(range(32))
    assert len(cohorts) == catalog["allowlist_maximum_slots"]
    identities = [item["id"] for item in cohorts]
    assert identities[0] == "1.0.0"
    assert identities[-1] == "1.0.32"
    assert "1.0.1" not in identities
    assert subject.prepare(tmp_path, "1.0.32") == []


def test_prepare_rejects_invalid_release_cohorts_without_writing(tmp_path):
    _release_tree(
        tmp_path,
        source="4.2.2",
        target="4.2.256",
        allowlist=[{"slot": 0, "major": 4, "minor": 2, "patch": 2, "id": "4.2.2"}],
    )
    before = _tree_text(tmp_path)
    with pytest.raises(ValueError, match="Release cohort coordinates must fit in one byte"):
        subject.prepare(tmp_path, "4.2.256")
    assert _tree_text(tmp_path) == before

    broken = tmp_path / "broken-catalog"
    _release_tree(
        broken,
        source="4.2.2",
        target="4.2.3",
        allowlist=[{"slot": 5, "major": 4, "minor": 2, "patch": 2, "id": "4.2.2"}],
    )
    before = _tree_text(broken)
    with pytest.raises(ValueError, match="not a contiguous reviewed allowlist"):
        subject.prepare(broken, "4.2.3")
    assert _tree_text(broken) == before

    linked = tmp_path / "linked-catalog"
    _release_tree(
        linked,
        source="4.2.2",
        target="4.2.3",
        allowlist=[{"slot": 0, "major": 4, "minor": 2, "patch": 2, "id": "4.2.2"}],
    )
    catalog = linked / "mnemion/product_telemetry/wire-v3.json"
    payload = catalog.read_text()
    outside = tmp_path / "outside-catalog.json"
    outside.write_text(payload)
    catalog.unlink()
    catalog.symlink_to(outside)
    before = _tree_text(linked)
    with pytest.raises(ValueError, match="ordinary repository files"):
        subject.prepare(linked, "4.2.3")
    assert _tree_text(linked) == before
    assert outside.read_text() == payload


@pytest.mark.parametrize(
    "case", ["dirty", "unmerged", "conflicting_branch", "already_running", "clean"]
)
def test_release_start_requires_committed_integrated_source_and_never_repeats_a_run(
    tmp_path, monkeypatch, case
):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "4.2.3"\n')
    calls = []

    def git(args, **kwargs):
        return (
            " M changed.py\n"
            if args[1] == "status" and case == "dirty"
            else ""
            if args[1] == "status"
            else COMMIT + "\n"
        )

    def api(repo, path):
        assert repo == REPO
        if path.startswith("compare/"):
            return {"status": "diverged" if case == "unmerged" else "ahead"}
        return {
            "workflow_runs": [{"id": 99, "head_sha": COMMIT}] if case == "already_running" else []
        }

    def gh(*args):
        calls.append(args)
        if args[0] == "api" and "matching-refs" in args[1]:
            return (
                json.dumps(
                    [
                        {
                            "ref": "refs/heads/release/4.2.3",
                            "object": {"sha": "b" * 40 if case == "conflicting_branch" else COMMIT},
                        }
                    ]
                )
                if case != "clean"
                else "[]"
            )
        return ""

    monkeypatch.setattr(subject.subprocess, "check_output", git)
    monkeypatch.setattr(subject, "api", api)
    monkeypatch.setattr(subject, "gh", gh)
    if case in {"dirty", "unmerged", "conflicting_branch"}:
        with pytest.raises(ValueError):
            subject.start(tmp_path, REPO)
    else:
        result = subject.start(tmp_path, REPO)
        assert result["existing_run"] == 99 if case == "already_running" else result["dispatched"]
    mutations = [call for call in calls if call[:2] in {("api", "--method"), ("workflow", "run")}]
    assert len(mutations) == (2 if case == "clean" else 0)


@pytest.mark.parametrize("published", ["4.2.2", "4.2.3", "4.2.4"])
def test_corrected_attempt_preserves_frozen_source_and_cannot_replace_a_public_version(
    tmp_path, monkeypatch, fixture, published
):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "4.2.3"\n')
    fixture.latest["tag_name"] = "v" + published
    monkeypatch.setattr(
        subject.subprocess,
        "check_output",
        lambda args, **kwargs: "" if args[1] == "status" else COMMIT,
    )
    calls = []

    def gh(*args):
        calls.append(args)
        if args[:2] == ("api", f"repos/{REPO}/git/matching-refs/heads/release/4.2.3-r2"):
            return "[]"
        assert args[:2] in {("api", "--method"), ("workflow", "run")}
        return ""

    monkeypatch.setattr(subject, "gh", gh)
    if published != "4.2.2":
        with pytest.raises(ValueError, match="cannot replace a published version"):
            subject.start(tmp_path, REPO, attempt=2)
        assert calls == []
        return
    result = subject.start(tmp_path, REPO, attempt=2)
    assert result["branch"] == "release/4.2.3-r2" and result["dispatched"]
    assert calls[1] == (
        "api",
        "--method",
        "POST",
        f"repos/{REPO}/git/refs",
        "-f",
        "ref=refs/heads/release/4.2.3-r2",
        "-f",
        "sha=" + COMMIT,
    )
    assert calls[2] == (
        "workflow",
        "run",
        "release.yml",
        "--repo",
        REPO,
        "--ref",
        "release/4.2.3-r2",
    )


@pytest.mark.parametrize("problem", ["dirty", "source_changed", "frozen"])
def test_integration_never_pushes_unreviewed_source_or_rebases_a_frozen_release(
    tmp_path, monkeypatch, problem
):
    calls = []

    def git(root, *args, check=True):
        calls.append(args)
        result = ""
        if args[0] == "status" and problem == "dirty":
            result = " M changed.py"
        elif args[0] == "symbolic-ref":
            result = "release/4.2.3" if problem == "frozen" else "codex/reviewed-batch"
        elif args[0] == "remote":
            result = "https://github.com/Perseusxrltd/mnemion.git"
        elif args[0] == "diff":
            result = "mnemion/service/changed.py\n"
        return SimpleNamespace(stdout=result, returncode=0)

    # This fixture exercises Git admission; actual source preflight is below.
    monkeypatch.setattr(subject, "check_source", lambda root: None)
    monkeypatch.setattr(subject, "_integration_git", git)
    with pytest.raises(ValueError):
        subject.integrate(tmp_path, "Perseusxrltd/mnemion")
    assert not any(args[0] in {"rebase", "push", "merge"} for args in calls)


@pytest.mark.parametrize("contents", ["value=1\n", "from pathlib import Path\n"])
def test_main_integration_checks_actual_source_before_contacting_remote(
    tmp_path, monkeypatch, contents
):
    source = tmp_path / "example.py"
    source.write_text(contents)
    calls = []

    def git(root, *args, check=True):
        calls.append(args)
        responses = {
            ("status", "--porcelain"): "",
            ("symbolic-ref", "--short", "HEAD"): "codex/reviewed-batch",
            ("remote", "get-url", "origin"): "https://github.com/Perseusxrltd/mnemion.git",
        }
        assert args in responses, "Invalid source must stop before any remote Git operation"
        return SimpleNamespace(stdout=responses[args], returncode=0)

    monkeypatch.setattr(subject, "_integration_git", git)
    with pytest.raises(subprocess.CalledProcessError):
        subject.integrate(tmp_path, "Perseusxrltd/mnemion")
    assert source.read_text() == contents
    assert not any(args[0] in {"fetch", "rebase", "push", "merge"} for args in calls)


def test_main_integration_never_pushes_when_secret_scan_fails(tmp_path, monkeypatch):
    calls, scans = [], []

    def git(root, *args, check=True):
        calls.append(args)
        responses = {
            ("status", "--porcelain"): "",
            ("symbolic-ref", "--short", "HEAD"): "codex/reviewed-batch",
            ("remote", "get-url", "origin"): "https://github.com/Perseusxrltd/mnemion.git",
        }
        assert args in responses, "Rejected secret scan must stop before remote Git operations"
        return SimpleNamespace(stdout=responses[args], returncode=0)

    def run(command, **kwargs):
        if "deploy.secret_scan" in command:
            scans.append(command)
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subject, "_integration_git", git)
    monkeypatch.setattr(subject.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        subject.integrate(tmp_path, "Perseusxrltd/mnemion")
    assert len(scans) == 1
    assert not any(args[0] in {"fetch", "rebase", "push", "merge"} for args in calls)


def test_main_integration_refuses_missing_reviewed_release_docs_before_remote(
    tmp_path, monkeypatch
):
    repository = Path(__file__).parents[1]
    for name in (
        "pyproject.toml",
        "deploy/release.py",
        "deploy/release_targets.py",
        "deploy/release-targets.json",
        "mnemion/version.py",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository / name).read_bytes())
    (tmp_path / "mnemion/__init__.py").write_text("")
    version = subject.tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]["version"]
    notes = tmp_path / "docs/releases" / f"{version}.md"
    notes.parent.mkdir(parents=True)
    notes.write_text(f"# Mnemion {version}\n")
    roadmap = tmp_path / "docs/ROADMAP.md"
    roadmap.write_text("# Roadmap\n\nPublic release status is tracked separately.\n")
    calls = []

    def git(root, *args, check=True):
        calls.append(args)
        responses = {
            ("status", "--porcelain"): "",
            ("symbolic-ref", "--short", "HEAD"): "codex/reviewed-batch",
            ("remote", "get-url", "origin"): "https://github.com/Perseusxrltd/mnemion.git",
        }
        assert args in responses, "Release documentation must pass before contacting GitHub"
        return SimpleNamespace(stdout=responses[args], returncode=0)

    monkeypatch.setattr(subject, "_integration_git", git)
    with pytest.raises(subprocess.CalledProcessError):
        subject.integrate(tmp_path, "Perseusxrltd/mnemion")
    assert "Reviewed source distribution:" not in roadmap.read_text()
    assert not any(args[0] in {"fetch", "push", "merge"} for args in calls)


@pytest.mark.parametrize("resolved_conflict", [False, True])
def test_generated_status_race_preserves_the_reviewed_hotfix_parent(
    tmp_path, monkeypatch, resolved_conflict
):
    remote, writer, reviewed = (tmp_path / name for name in ("remote.git", "writer", "reviewed"))

    def git(root, *args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Perseusxrltd",
                "-c",
                "user.email=226232767+Perseusxrltd@users.noreply.github.com",
                *args,
            ],
            cwd=root,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()

    git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))
    git(tmp_path, "clone", str(remote), str(writer))
    (writer / "deploy").mkdir()
    (writer / "deploy/release-status.json").write_text('{"observed":1}\n')
    (writer / "app.py").write_text("VALUE = 1\n")
    git(writer, "add", ".")
    git(writer, "commit", "-m", "Published baseline")
    published = git(writer, "rev-parse", "HEAD")
    (writer / "future-feature.txt").write_text("Unreleased feature work\n")
    if resolved_conflict:
        (writer / "app.py").write_text("VALUE = 2\n")
    git(writer, "add", ".")
    git(writer, "commit", "-m", "Main continues development")
    git(writer, "push", "origin", "main")
    git(tmp_path, "clone", str(remote), str(reviewed))
    git(reviewed, "checkout", "-b", "hotfix/security", published)
    (reviewed / "security.txt").write_text("Reviewed security fix\n")
    if resolved_conflict:
        (reviewed / "app.py").write_text("VALUE = 3\n")
    git(reviewed, "add", ".")
    git(reviewed, "commit", "-m", "Standalone reviewed hotfix")
    hotfix = git(reviewed, "rev-parse", "HEAD")
    git(reviewed, "checkout", "-b", "codex/reviewed", "main")
    if resolved_conflict:
        with pytest.raises(subprocess.CalledProcessError):
            git(reviewed, "merge", "--no-ff", "--no-commit", hotfix)
        git(reviewed, "restore", "--source=main", "--staged", "--worktree", "app.py")
        git(reviewed, "commit", "-m", "Retain hotfix ancestry and reviewed resolution")
    else:
        git(reviewed, "merge", "--no-ff", "-m", "Retain hotfix ancestry", hotfix)
    reviewed_merge = git(reviewed, "rev-parse", "HEAD")
    (writer / "deploy/release-status.json").write_text('{"observed":2}\n')
    git(writer, "add", ".")
    git(writer, "commit", "-m", "Concurrent generated status")
    git(writer, "push", "origin", "main")

    actual = subject._integration_git

    def local_remote(root, *args, check=True):
        if args == ("remote", "get-url", "origin"):
            return SimpleNamespace(stdout="https://github.com/Perseusxrltd/mnemion.git\n")
        return actual(root, *args, check=check)

    monkeypatch.setattr(subject, "_integration_git", local_remote)
    # A miniature Git repository has no distribution metadata. The independent
    # preflight regression above exercises the actual release validator.
    monkeypatch.setattr(subject, "check_source", lambda root: None)
    result = subject.integrate(reviewed, "Perseusxrltd/mnemion")
    assert result["pushed_to"] == "main"
    assert git(reviewed, "merge-base", "--is-ancestor", hotfix, "HEAD") == ""
    assert git(reviewed, "merge-base", "--is-ancestor", reviewed_merge, "HEAD") == ""
    assert git(remote, "rev-parse", "main") == result["source_commit"]
    assert (reviewed / "future-feature.txt").read_text() == "Unreleased feature work\n"
    assert "future-feature.txt" not in git(reviewed, "ls-tree", "-r", "--name-only", hotfix)
    assert json.loads((reviewed / "deploy/release-status.json").read_text()) == {"observed": 2}
    assert (reviewed / "app.py").read_text() == (
        "VALUE = 2\n" if resolved_conflict else "VALUE = 1\n"
    )
    assert not git(reviewed, "status", "--porcelain")
