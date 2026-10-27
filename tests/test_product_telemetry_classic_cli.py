"""Actual classic CLI dispatch, private choice and unchanged command behavior."""

import json
import argparse
from pathlib import Path
import subprocess
import sys

import pytest

from deploy import telemetry_coverage
from deploy.telemetry_cli_actions import command_names
from mnemion import cli, cli_measurement, product_telemetry
from mnemion.product_telemetry import aggregate, catalog, policy


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "private-choice"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/telemetry")
    monkeypatch.setattr(product_telemetry, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(product_telemetry, "COLLECTOR_URL", "https://example.invalid/telemetry")
    monkeypatch.setattr(cli, "_configure_stdio", lambda: None)
    policy.configure(root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1})
    return root


def cells(root):
    return [
        {**catalog.describe(row["cell"]), "count": row["count"]} for row in aggregate.preview(root)
    ]


def test_classic_search_owns_one_invocation_without_arguments_or_output(
    installation, monkeypatch, capsys
):
    calls = []

    def search(args):
        calls.append(args.query)
        print("PRIVATE_RESULT")

    monkeypatch.setattr(cli, "cmd_search", search)
    monkeypatch.setattr("sys.argv", ["mnemion", "search", "PRIVATE_QUERY"])
    cli.main()
    assert calls == ["PRIVATE_QUERY"]
    assert capsys.readouterr().out == "PRIVATE_RESULT\n"
    rows = cells(installation)
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert {row["workflow"] for row in rows} == {"memory.recall"}
    assert {row["surface"] for row in rows} == {"headless"}
    assert "PRIVATE" not in json.dumps(rows)


def test_classic_commands_are_visible_even_without_a_reviewed_owner():
    root = Path(__file__).resolve().parents[1]
    view = telemetry_coverage.build(root)["action_coverage"]
    rows = {row["action"]: row for row in view["actions"] if row["owner"] == "classic_cli"}
    assert "search" in rows
    assert "wiki compile" in rows
    assert rows["wiki compile"]["state"] == "unmeasured"
    assert rows["wiki compile"]["workflows"] == []


@pytest.mark.parametrize(
    "arguments,handler,expected",
    [
        (["wake-up"], "cmd_wakeup", "memory.context"),
        (["reconstruct", "PRIVATE_QUERY"], "cmd_reconstruct", "memory.knowledge"),
        (["source", "list"], "cmd_source", "memory.list"),
        (["source", "read", "PRIVATE_ID"], "cmd_source", "memory.read"),
        (["source", "search", "PRIVATE_QUERY"], "cmd_source", "memory.recall"),
        (["restore", "PRIVATE_ARCHIVE", "--merge"], "cmd_restore", "memory.import"),
        (["obsidian", "sync"], "cmd_obsidian", "memory.export"),
        (["obsidian", "setup"], "cmd_obsidian", "memory.export"),
    ],
)
def test_reviewed_cli_dispatches_keep_results_private_and_emit_once(
    installation, monkeypatch, arguments, handler, expected
):
    called = []

    def action(args):
        called.append(args)
        return {"PRIVATE_RESULT": object()}

    monkeypatch.setattr(cli, handler, action)
    monkeypatch.setattr("sys.argv", ["mnemion", *arguments])
    # The CLI has always returned None, even if a handler returns private data.
    assert cli.main() is None
    assert len(called) == 1
    rows = cells(installation)
    assert {row["workflow"] for row in rows} == {expected}
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == 1
    assert {row["metric"] for row in rows} == {"submissions", "outcomes", "latency_ms"}


@pytest.mark.parametrize(
    "condition", ["unavailable", "opted_out", "company", "unreadable", "nested"]
)
def test_cli_cannot_infer_permission_and_never_repeats_the_command(
    installation, monkeypatch, tmp_path, condition
):
    calls = []
    monkeypatch.setattr(cli, "cmd_search", lambda args: calls.append(args.query))
    monkeypatch.setattr("sys.argv", ["mnemion", "search", "PRIVATE_QUERY"])
    if condition == "opted_out":
        policy.configure(installation, {"enabled": False, "expected_revision": 0})
    if condition == "company":
        (tmp_path / "company.json").write_text(
            json.dumps({"schema_version": 1, "enabled": False, "metric_groups": []})
        )
    with monkeypatch.context() as scope:
        if condition == "unavailable":
            scope.setattr(product_telemetry, "COLLECTION_AVAILABLE", False)
            scope.setattr(
                cli_measurement,
                "_origins",
                lambda: pytest.fail("Inactive CLI read origin definitions"),
            )
        if condition == "unreadable":

            def unreadable(*_a, **_k):
                raise OSError("PRIVATE_PATH")

            scope.setattr(policy, "status", unreadable)
        assert cli.main(telemetry_owner=condition != "nested") is None
    assert calls == ["PRIVATE_QUERY"]
    assert cells(installation) == []


@pytest.mark.parametrize("condition", ["opt_out", "reenable", "storage_loss"])
def test_command_completion_keeps_its_original_privacy_fence(installation, monkeypatch, condition):
    def action(_args):
        if condition == "storage_loss":
            (installation / policy.DATABASE_NAME).unlink()
            policy.configure(
                installation, {"enabled": True, "expected_revision": 0, "disclosure_version": 1}
            )
        else:
            off = policy.configure(installation, {"enabled": False, "expected_revision": 0})
            if condition == "reenable":
                policy.configure(
                    installation,
                    {
                        "enabled": True,
                        "expected_revision": off["revision"],
                        "expected_generation": off["store_generation"],
                        "disclosure_version": 1,
                    },
                )

    monkeypatch.setattr(cli, "cmd_search", action)
    monkeypatch.setattr("sys.argv", ["mnemion", "search", "PRIVATE_QUERY"])
    cli.main()
    assert cells(installation) == []


@pytest.mark.parametrize(
    "arguments,handler",
    [
        (["obsidian", "sync", "--dry-run"], "cmd_obsidian"),
        (["obsidian", "setup", "--dry-run"], "cmd_obsidian"),
        (["status"], "cmd_status"),
        (["instructions", "search"], "cmd_instructions"),
        (["wiki", "compile"], "cmd_wiki"),
    ],
)
def test_preview_excluded_and_unmapped_commands_stay_unmeasured(
    installation, monkeypatch, arguments, handler
):
    called = []
    monkeypatch.setattr(cli, handler, lambda args: called.append(args))
    monkeypatch.setattr("sys.argv", ["mnemion", *arguments])
    cli.main()
    assert len(called) == 1 and cells(installation) == []


@pytest.mark.parametrize(
    "error,command,outcome",
    [
        (SystemExit(0), "search", "success"),
        (SystemExit(2), "search", "failed"),
        (SystemExit("PRIVATE_ERROR"), "restore", "unconfirmed"),
        (KeyboardInterrupt(), "restore", "cancelled"),
        (RuntimeError("PRIVATE_ERROR"), "restore", "unconfirmed"),
    ],
)
def test_cli_preserves_original_exceptions_and_bounded_outcomes(
    installation, error, command, outcome
):
    calls = []

    def action():
        calls.append(True)
        raise error

    with pytest.raises(type(error)) as found:
        cli_measurement.invoke(command, action, owned=True)
    assert found.value is error and calls == [True]
    rows = cells(installation)
    assert next(row["bucket"] for row in rows if row["metric"] == "outcomes") == outcome
    assert "PRIVATE" not in json.dumps(rows)


def test_optional_finisher_failure_cannot_hide_a_result_or_replay(installation, monkeypatch):
    from mnemion.product_telemetry import workflow

    def unavailable(*_a, **_k):
        raise OSError("PRIVATE_ERROR")

    monkeypatch.setattr(workflow.Workflow, "finish", unavailable)
    result, calls = object(), []
    assert (
        cli_measurement.invoke("search", lambda: (calls.append(True), result)[1], owned=True)
        is result
    )
    assert calls == [True] and cells(installation) == []


def test_static_command_inventory_matches_the_actual_argparse_tree(monkeypatch):
    captured = []

    class Captured(Exception):
        pass

    def capture(parser, *_a, **_k):
        captured.append(parser)
        raise Captured

    monkeypatch.setattr(cli, "_configure_stdio", lambda: None)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", capture)
    with pytest.raises(Captured):
        cli.main(telemetry_owner=False)

    def leaves(parser, prefix=()):
        groups = [
            action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        ]
        if not groups:
            return {" ".join(prefix)}
        assert len(groups) == 1
        return set().union(
            *(leaves(child, (*prefix, name)) for name, child in groups[0].choices.items())
        )

    assert command_names(Path(cli.__file__).read_text()) == leaves(captured[0])


def test_new_classic_command_remains_visible_without_guessing_an_owner():
    original = Path(cli.__file__).read_text()
    modified = original.replace(
        '\n    sub.add_parser("status",',
        '\n    sub.add_parser("future-action")\n    sub.add_parser("status",',
    )
    assert "future-action" in command_names(modified)
    assert "future-action" not in cli_measurement._origins()["operations"]


@pytest.mark.parametrize(
    "declaration",
    [
        "commands.add_parser(private_name)",
        'commands.add_parser("search", **private_options)',
        'commands.add_parser("search", aliases=private_aliases)',
        'commands.add_parser("search")\n    commands.add_parser("search")',
        'other.add_parser("hidden")',
    ],
)
def test_unrecognized_command_declarations_require_review(declaration):
    source = (
        'def main():\n    parser = argparse.ArgumentParser()\n    commands = parser.add_subparsers(dest="command")\n    '
        + declaration
    )
    with pytest.raises(ValueError):
        command_names(source)


def test_declared_aliases_keep_nested_command_paths():
    source = """def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    child = commands.add_parser("source", aliases=["sources"])
    sub = child.add_subparsers(dest="action")
    sub.add_parser("read", aliases=["get"])
"""
    assert command_names(source) == {"source read", "source get", "sources read", "sources get"}


def test_inactive_cli_does_not_load_policy_or_collection_runtime():
    script = """import sys
from mnemion import cli
cli._configure_stdio = lambda: None
cli.cmd_search = lambda args: None
sys.argv = ["mnemion", "search", "PRIVATE_QUERY"]
cli.main()
assert "mnemion.product_telemetry.policy" not in sys.modules
assert "mnemion.product_telemetry.workflow" not in sys.modules
assert "mnemion.product_telemetry.activity" not in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, timeout=15)
