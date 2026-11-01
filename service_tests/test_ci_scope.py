"""Use real Git changes to verify which work may avoid product build queues."""

import subprocess

import pytest

from deploy.ci_scope import RENDERER_DIAGNOSTICS, TELEMETRY_PATHS, scope


def changed_repository(root, paths):
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Scope fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgsign", "false")
    (root / "README.md").write_text("Fixture\n")
    git("add", ".")
    git("commit", "-qm", "Before")
    before = git("rev-parse", "HEAD")
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Changed fixture\n")
    git("add", ".")
    git("commit", "-qm", "After")
    return {"before": before, "after": git("rev-parse", "HEAD")}


# Exact paths from the 2026-11-02 review. Spelled once so each family, the
# combined push, and the file check use the same 61 names.
LINUX_ADMISSION_DIAGNOSTICS = (
    "deploy/linux_bpf_lifetime/admission_guard.c",
    "deploy/linux_bpf_lifetime/admission_guard.h",
    "deploy/linux_bpf_lifetime/admission_guard_check.c",
    "deploy/linux_bpf_lifetime/admission_guard_owner.c",
    "deploy/linux_bpf_lifetime/admission_guard_owner.h",
    "deploy/linux_bpf_lifetime/admit_observe.py",
)
WINDOWS_ETW_DIAGNOSTICS = (
    ".github/workflows/windows-etw-abi.yml",
    ".github/workflows/windows-etw-lifecycle.yml",
    "deploy/owned_launch_windows_etw.py",
    "deploy/windows_etw_abi/README.md",
    "deploy/windows_etw_abi/compare_declarations.py",
    "deploy/windows_etw_abi/oracle/arm64/abi.json",
    "deploy/windows_etw_abi/oracle/arm64/metadata.json",
    "deploy/windows_etw_abi/oracle/manifest.json",
    "deploy/windows_etw_abi/oracle/x64/abi.json",
    "deploy/windows_etw_abi/oracle/x64/metadata.json",
    "deploy/windows_etw_lifecycle.py",
    "tests/test_owned_launch_windows_etw.py",
    "tests/test_windows_etw_lifecycle.py",
)
MAC_KEYCHAIN_PROOF_DIAGNOSTICS = (
    ".github/workflows/macos-keychain-helper-compile-only.yml",
    ".github/workflows/macos-keychain-injected-fixture.yml",
    "deploy/macos_keychain_proof/.gitignore",
    "deploy/macos_keychain_proof/FIXTURE_OWNER.md",
    "deploy/macos_keychain_proof/HelperInfo.plist",
    "deploy/macos_keychain_proof/IdentityEpoch",
    "deploy/macos_keychain_proof/IdentityEpoch-rotated",
    "deploy/macos_keychain_proof/ParentInfo.plist",
    "deploy/macos_keychain_proof/STAGED_BUILD.md",
    "deploy/macos_keychain_proof/auth.h",
    "deploy/macos_keychain_proof/auth.m",
    "deploy/macos_keychain_proof/bundle_manifest.c",
    "deploy/macos_keychain_proof/bundle_manifest.h",
    "deploy/macos_keychain_proof/caller_pin.h.in",
    "deploy/macos_keychain_proof/compile_only.sh",
    "deploy/macos_keychain_proof/exact_helper.h",
    "deploy/macos_keychain_proof/exact_helper.m",
    "deploy/macos_keychain_proof/fixture_inject.c",
    "deploy/macos_keychain_proof/fixture_inject.h",
    "deploy/macos_keychain_proof/fixture_owner.c",
    "deploy/macos_keychain_proof/fixture_store.h",
    "deploy/macos_keychain_proof/fixture_store.m",
    "deploy/macos_keychain_proof/fixture_store_cases.c",
    "deploy/macos_keychain_proof/fixture_store_config.h.in",
    "deploy/macos_keychain_proof/fixture_store_syntax.c",
    "deploy/macos_keychain_proof/fixture_store_syntax.h",
    "deploy/macos_keychain_proof/fixture_worker.c",
    "deploy/macos_keychain_proof/generation-a.txt",
    "deploy/macos_keychain_proof/generation-b.txt",
    "deploy/macos_keychain_proof/helper_main.m",
    "deploy/macos_keychain_proof/identity_dump.m",
    "deploy/macos_keychain_proof/key_item.h",
    "deploy/macos_keychain_proof/key_item.m",
    "deploy/macos_keychain_proof/parent_direct_lookup.h",
    "deploy/macos_keychain_proof/parent_direct_lookup.m",
    "deploy/macos_keychain_proof/parent_main.m",
    "deploy/macos_keychain_proof/parent_pin.h.in",
    "deploy/macos_keychain_proof/protocol.h",
    "deploy/macos_keychain_proof/signing.h",
    "deploy/macos_keychain_proof/signing.m",
    "deploy/macos_keychain_proof/v10_crypt.c",
    "deploy/macos_keychain_proof/v10_crypt.h",
)
REVIEWED_NATIVE_DIAGNOSTIC_ADDITIONS = (
    *LINUX_ADMISSION_DIAGNOSTICS,
    *WINDOWS_ETW_DIAGNOSTICS,
    *MAC_KEYCHAIN_PROOF_DIAGNOSTICS,
)


def test_browser_journey_files_stay_on_the_manual_diagnostic(tmp_path):
    event = changed_repository(
        tmp_path,
        [
            ".github/workflows/telemetry-browser-journeys.yml",
            "deploy/probe_telemetry_browser.py",
            "deploy/probe_telemetry_browser.mjs",
            "tests/test_telemetry_browser_journey.py",
            "docs/implementation/telemetry-browser-journeys-2026-10-30.md",
        ],
    )
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "reason": "diagnostic_only",
    }


def test_isolated_renderer_changes_do_not_reserve_product_runners(tmp_path):
    event = changed_repository(
        tmp_path,
        [
            ".github/workflows/telemetry-renderer.yml",
            "deploy/probe_telemetry_renderer.py",
            "docs/check.md",
        ],
    )
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "reason": "diagnostic_only",
    }


@pytest.mark.parametrize("path", ["mnemion/service/api.py", ".github/workflows/desktop.yml"])
def test_one_runtime_or_release_change_keeps_all_checks(tmp_path, path):
    event = changed_repository(tmp_path, ["deploy/probe_telemetry_renderer.py", path])
    assert scope(tmp_path, event, event_name="push")["runtime"] is True


def test_release_and_manual_validation_never_skip_diagnostic_only_changes(tmp_path):
    event = changed_repository(tmp_path, ["deploy/report_telemetry_renderer.py"])
    assert scope(tmp_path, event, event_name="push", release=True)["runtime"] is True
    assert scope(tmp_path, event, event_name="workflow_dispatch")["runtime"] is True
    assert scope(tmp_path, event, event_name="pull_request")["runtime"] is True


def test_missing_comparison_history_keeps_all_checks(tmp_path):
    event = changed_repository(tmp_path, ["deploy/probe_telemetry_renderer.py"])
    event["before"] = "1" * 40
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": True,
        "reason": "unavailable_diff",
    }


@pytest.mark.parametrize(
    "path",
    [
        "mnemion/product_telemetry/workflow.py",
        "studio/electron/telemetry-owner.ts",
        "studio/frontend/src/workspace/telemetry-policy.ts",
        "tests/test_product_telemetry_transport.py",
    ],
)
def test_reviewed_components_select_telemetry_checks_only_for_pushes(tmp_path, path):
    event = changed_repository(tmp_path, [path, "docs/telemetry.md"])
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "telemetry": True,
        "reason": "telemetry_components_only",
    }
    for event_name, release in [
        ("push", True),
        ("workflow_call", False),
        ("workflow_dispatch", False),
        ("pull_request", False),
    ]:
        selected = scope(tmp_path, event, event_name=event_name, release=release)
        assert selected["runtime"] is True and not selected.get("telemetry", False)


@pytest.mark.parametrize(
    "path",
    [
        "mnemion/cli.py",
        "mnemion/service/api.py",
        "studio/frontend/src/App.tsx",
        "mnemion/product_telemetry/unknown.py",
        "studio/electron/telemetry-new.ts",
        "mnemion/product_telemetry/disclosure.json",
        "mnemion/product_telemetry/transport-route.json",
        "mnemion/product_telemetry/catalog.json",
        "mnemion/product_telemetry/wire-v2.json",
        "pyproject.toml",
        "uv.lock",
        "studio/frontend/package-lock.json",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "deploy/ci_scope.py",
    ],
)
def test_telemetry_mixed_with_shared_or_unknown_source_keeps_full_checks(tmp_path, path):
    event = changed_repository(tmp_path, ["mnemion/product_telemetry/workflow.py", path])
    selected = scope(tmp_path, event, event_name="push")
    assert selected["runtime"] is True and not selected.get("telemetry", False)


def test_allowlist_only_names_existing_isolated_components():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert TELEMETRY_PATHS and all((root / path).is_file() for path in TELEMETRY_PATHS)


def test_reviewed_native_diagnostics_skip_the_product_matrix(tmp_path):
    event = changed_repository(
        tmp_path,
        [
            ".github/workflows/windows-sdk-abi.yml",
            ".github/workflows/linux-bpf-lifetime-diagnostic.yml",
            "tests/test_linux_bpf_lifetime_parse.py",
            "deploy/linux_bpf_lifetime/.gitignore",
            "deploy/linux_bpf_lifetime/BUILD.md",
            "deploy/linux_bpf_lifetime/Makefile",
            "deploy/linux_bpf_lifetime/lifetime.bpf.c",
            "deploy/linux_bpf_lifetime/lifetime_abi.h",
            "deploy/linux_bpf_lifetime/lifetime_bpf_prelude.h",
            "deploy/linux_bpf_lifetime/lifetime_loader.c",
            "deploy/linux_bpf_lifetime/lifetime_receipt.h",
            "deploy/linux_bpf_lifetime/lifetime_sha256.h",
            "deploy/linux_bpf_lifetime/receipt.py",
            "deploy/linux_bpf_lifetime/sha256_selftest.c",
            "deploy/windows_sdk_abi/README.md",
            "deploy/windows_sdk_abi/REFERENCE_LAYOUTS.txt",
            "deploy/windows_sdk_abi/build_sdk_abi.ps1",
            "deploy/windows_sdk_abi/sdk_abi.c",
            *REVIEWED_NATIVE_DIAGNOSTIC_ADDITIONS,
        ],
    )
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "reason": "diagnostic_only",
    }


@pytest.mark.parametrize(
    "path",
    [
        "mnemion/service/api.py",
        "deploy/linux_bpf_lifetime/unreviewed.c",
        "deploy/windows_sdk_abi/unreviewed.c",
        "deploy/macos_keychain_proof/unreviewed.m",
        "deploy/windows_etw_abi/oracle/arm64/unreviewed.json",
        ".github/workflows/windows-etw-unreviewed.yml",
        ".github/workflows/ci.yml",
        "deploy/ci_scope.py",
        "pyproject.toml",
    ],
)
def test_native_diagnostic_with_runtime_or_unknown_sibling_keeps_all_checks(tmp_path, path):
    event = changed_repository(
        tmp_path,
        [
            "deploy/windows_sdk_abi/sdk_abi.c",
            "deploy/linux_bpf_lifetime/lifetime.bpf.c",
            "deploy/linux_bpf_lifetime/admission_guard_owner.c",
            "deploy/owned_launch_windows_etw.py",
            "deploy/macos_keychain_proof/fixture_owner.c",
            path,
        ],
    )
    selected = scope(tmp_path, event, event_name="push")
    assert selected == {"runtime": True, "reason": "runtime_or_unknown_files"}


def test_release_manual_and_pull_request_keep_native_diagnostic_checks(tmp_path):
    event = changed_repository(
        tmp_path,
        [
            ".github/workflows/windows-sdk-abi.yml",
            "deploy/windows_sdk_abi/sdk_abi.c",
            "deploy/linux_bpf_lifetime/Makefile",
            "deploy/linux_bpf_lifetime/admission_guard_owner.c",
            ".github/workflows/windows-etw-lifecycle.yml",
            "deploy/windows_etw_lifecycle.py",
            ".github/workflows/macos-keychain-injected-fixture.yml",
            "deploy/macos_keychain_proof/fixture_owner.c",
        ],
    )
    assert scope(tmp_path, event, event_name="push", release=True) == {
        "runtime": True,
        "reason": "release_or_non_push",
    }
    assert scope(tmp_path, event, event_name="workflow_dispatch")["runtime"] is True
    assert scope(tmp_path, event, event_name="pull_request")["runtime"] is True
    assert scope(tmp_path, event, event_name="workflow_call") == {
        "runtime": True,
        "reason": "release_or_non_push",
    }


@pytest.mark.parametrize(
    "paths",
    [
        LINUX_ADMISSION_DIAGNOSTICS,
        WINDOWS_ETW_DIAGNOSTICS,
        MAC_KEYCHAIN_PROOF_DIAGNOSTICS,
    ],
    ids=["linux-admission", "windows-etw", "macos-keychain-proof"],
)
def test_each_reviewed_native_family_skips_the_product_matrix(tmp_path, paths):
    event = changed_repository(tmp_path, paths)
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "reason": "diagnostic_only",
    }


def test_admission_guard_owner_change_skips_the_product_matrix(tmp_path):
    event = changed_repository(
        tmp_path,
        ["deploy/linux_bpf_lifetime/admission_guard_owner.c"],
    )
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": False,
        "reason": "diagnostic_only",
    }


def test_selector_correction_keeps_full_checks(tmp_path):
    event = changed_repository(
        tmp_path,
        ["deploy/ci_scope.py", "service_tests/test_ci_scope.py"],
    )
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": True,
        "reason": "runtime_or_unknown_files",
    }


@pytest.mark.parametrize(
    "path",
    [
        "deploy/build_telemetry_network.py",
        "deploy/build_telemetry_network.ps1",
        "deploy/probe_telemetry_network.py",
    ],
)
def test_deployed_telemetry_network_builders_keep_full_checks(tmp_path, path):
    event = changed_repository(
        tmp_path,
        ["deploy/linux_bpf_lifetime/admission_guard_owner.c", path],
    )
    assert scope(tmp_path, event, event_name="push") == {
        "runtime": True,
        "reason": "runtime_or_unknown_files",
    }


def test_reviewed_native_additions_stay_explicit_files():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    additions = REVIEWED_NATIVE_DIAGNOSTIC_ADDITIONS
    assert len(additions) == 61 and len(set(additions)) == 61
    assert set(additions) <= RENDERER_DIAGNOSTICS
    assert set(additions).isdisjoint(TELEMETRY_PATHS)
    assert all((root / path).is_file() for path in additions)
    assert all("*" not in path and not path.endswith("/") for path in RENDERER_DIAGNOSTICS)
    refused = {
        "deploy/build_telemetry_network.py",
        "deploy/build_telemetry_network.ps1",
        "deploy/probe_telemetry_network.py",
        "deploy/ci_scope.py",
        "service_tests/test_ci_scope.py",
    }
    assert refused.isdisjoint(RENDERER_DIAGNOSTICS)
    assert all(not path.startswith("mnemion/product_telemetry") for path in RENDERER_DIAGNOSTICS)
