"""Focused checks for the four resource-boundary corrections."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from deploy.owned_installed_launch import finalize_owned_launch
from deploy.owned_launch_accounting import OwnedLaunchError
from deploy.probe_telemetry_installed import (
    _run_resource_smoke,
    installed_resource_case_completed,
    note_resource_ingress,
    resource_counterbalance_cases,
    resource_journey_completed,
)
from deploy.report_telemetry_renderer import OwnedPhaseCursor, apply_owned_marker
from mnemion.product_telemetry.wire_v3 import METRICS, PACKET_BYTES, decode, encode


CHECKPOINTS = [
    "before_workspace_connect",
    "workspace_connected",
    "first_memory_cycle_and_delivery",
    "8_memory_cycles",
    "16_memory_cycles",
    "32_memory_cycles",
    "64_memory_cycles",
    "96_memory_cycles",
    "128_memory_cycles",
]

_CHILD = """
import os, sys
advance = os.environ.get("RESOURCE_BOUNDARY_ADVANCE")
memory = os.environ.get("RESOURCE_BOUNDARY_MEMORY")
done = os.environ.get("RESOURCE_BOUNDARY_DONE")
labels = sys.argv[1:]
for index, label in enumerate(labels):
    line = ('RESOURCE_CASE {"label":"%s"}\\n' % label).encode()
    sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()
    ack = sys.stdin.buffer.readline()
    if ack != ('RESOURCE_CASE_ACK %s\\n' % label).encode():
        sys.exit(2)
    if index == 0 and memory and advance:
        with open(advance, "w", encoding="ascii") as handle:
            handle.write("started")
        with open(memory, "w", encoding="ascii") as handle:
            handle.write("768")
if done:
    with open(done, "w", encoding="ascii") as handle:
        handle.write("done")
sys.exit(0)
"""


def _valid_packet() -> bytes:
    packet = encode("os", [1] * len(METRICS), operating_system="linux")
    decode(packet)
    return packet


def _owned():
    return {"canonical_operations_completed": 128, "resource_acceptance": False}


def _case(**overrides):
    evidence = {
        "memory_cycles": 128,
        "memory_results_verified": True,
        "checkpoints": CHECKPOINTS,
        "model_calls": 0,
        "resource_acceptance": False,
        "condition": "enabled",
        "memory_api_operations": 384,
        "telemetry_attempts": 1,
        "telemetry_reserved_bytes": 65536,
        "telemetry_events": [],
        "memory_successful": 384,
        "inspected_body_hex": None,
    }
    evidence.update(overrides)
    return evidence


class _Launch:
    def __init__(self):
        self.calls = 0
        self.marks = []

    def mark_phase(self, name, *, canonical_operations_completed, active):
        self.marks.append((name, canonical_operations_completed))
        if name == "measuring":
            raise OwnedLaunchError("invalid_phase")

    def finish(self, *, canonical_operations_completed=None):
        self.calls += 1
        return {
            "lifetime_cpu_microseconds": 10,
            "cleanup": {"ok": True, "failure": None, "retried": False},
        }


def _spawn(
    tmp_path: Path, labels: list[str], on_case, expected: list[str], timeout: int, memory: bool
):
    script = tmp_path / "child.py"
    script.write_text(_CHILD, encoding="utf-8")
    advance = tmp_path / "advanced"
    counter = tmp_path / "memory"
    if memory:
        counter.write_text("384", encoding="ascii")
    env = os.environ.copy()
    env["RESOURCE_BOUNDARY_ADVANCE"] = str(advance)
    if memory:
        env["RESOURCE_BOUNDARY_MEMORY"] = str(counter)
    lines = b"".join(f'RESOURCE_CASE {{"label":"{label}"}}\n'.encode() for label in labels)
    assert len(lines) < 4096
    completed = _run_resource_smoke(
        [sys.executable, str(script), *labels],
        tmp_path,
        env,
        timeout,
        on_case,
        expected,
    )
    return completed, advance, counter


def test_case_cannot_advance_before_its_counters_are_frozen(tmp_path: Path):
    frozen = []
    counter = tmp_path / "memory"

    def on_case(payload):
        frozen.append(
            (
                payload["label"],
                int(counter.read_text(encoding="ascii")),
                (tmp_path / "advanced").exists(),
            )
        )

    completed, advance, _counter = _spawn(
        tmp_path,
        ["r1-unavailable", "r1-opted_out"],
        on_case,
        ["r1-unavailable", "r1-opted_out"],
        5,
        True,
    )
    assert completed.returncode == 0
    assert frozen == [
        ("r1-unavailable", 384, False),
        ("r1-opted_out", 768, True),
    ]
    assert advance.read_text(encoding="ascii") == "started"


def test_unknown_duplicate_and_oversized_boundaries_are_not_acknowledged(tmp_path: Path):
    def on_case(_payload):
        raise AssertionError("an invalid boundary was treated as a case")

    try:
        _spawn(tmp_path, ["not-a-case"], on_case, ["r1-unavailable"], 5, False)
    except RuntimeError as error:
        assert str(error) == "resource_case_unknown"
    else:
        raise AssertionError("unknown label was acknowledged")
    assert not (tmp_path / "advanced").exists()

    try:
        _spawn(
            tmp_path,
            ["r1-opted_out"],
            on_case,
            ["r1-unavailable", "r1-opted_out"],
            5,
            False,
        )
    except RuntimeError as error:
        assert str(error) == "resource_case_out_of_order"
    else:
        raise AssertionError("out-of-order label was acknowledged")

    script = tmp_path / "dup.py"
    script.write_text(_CHILD, encoding="utf-8")
    env = os.environ.copy()
    env["RESOURCE_BOUNDARY_DONE"] = str(tmp_path / "second-ack")
    seen = []
    try:
        _run_resource_smoke(
            [sys.executable, str(script), "r1-unavailable", "r1-unavailable"],
            tmp_path,
            env,
            5,
            lambda payload: seen.append(payload["label"]),
            ["r1-unavailable", "r1-opted_out"],
        )
    except RuntimeError as error:
        assert str(error) == "resource_case_duplicate"
    else:
        raise AssertionError("duplicate label was acknowledged")
    assert seen == ["r1-unavailable"]
    assert not (tmp_path / "second-ack").exists()

    fat = tmp_path / "fat.py"
    fat.write_text(
        "import sys\nsys.stdout.buffer.write(b'x' * 3000 + b'\\n')\nsys.stdout.buffer.flush()\nsys.stdin.buffer.readline()\n",
        encoding="utf-8",
    )
    try:
        _run_resource_smoke(
            [sys.executable, str(fat)],
            tmp_path,
            os.environ.copy(),
            5,
            on_case,
            ["r1-unavailable"],
        )
    except RuntimeError as error:
        assert str(error) == "resource_case_malformed"
    else:
        raise AssertionError("oversized output was acknowledged")


def test_missing_boundary_times_out(tmp_path: Path):
    script = tmp_path / "sleep.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    try:
        _run_resource_smoke(
            [sys.executable, str(script)],
            tmp_path,
            os.environ.copy(),
            1,
            lambda _payload: None,
            ["r1-unavailable"],
        )
    except TimeoutError as error:
        assert "finite timeout" in str(error)
    else:
        raise AssertionError("a silent controller was accepted")


def test_invalid_and_rejected_reports_do_not_complete_a_case():
    invalid = bytes(PACKET_BYTES)
    assert invalid[0] == 0
    counts = {"malformed_body": 0, "reports": 6, "accepted": 0}
    rejected_body = note_resource_ingress(bytearray(invalid), [], counts, status=400)
    assert rejected_body["valid"] is False
    assert rejected_body["accepted"] is False
    assert rejected_body["body_hex"] == invalid.hex()
    assert counts["reports"] == 6
    assert (
        installed_resource_case_completed(_case(telemetry_events=[rejected_body]), _owned())
        is False
    )
    laundered = note_resource_ingress(bytearray(invalid), [], counts, status=204)
    assert laundered["accepted"] is False
    assert installed_resource_case_completed(_case(telemetry_events=[laundered]), _owned()) is False

    valid = _valid_packet()
    non_204 = note_resource_ingress(bytearray(valid), [], counts, status=400)
    assert non_204["valid"] is True
    assert non_204["accepted"] is False
    assert non_204["status"] == 400
    assert installed_resource_case_completed(_case(telemetry_events=[non_204]), _owned()) is False

    forbidden = note_resource_ingress(
        bytearray(valid), [], counts, status=204, forbidden_metadata=True
    )
    assert forbidden["forbidden_metadata"] is True
    assert forbidden["valid"] is True
    assert installed_resource_case_completed(_case(telemetry_events=[forbidden]), _owned()) is False

    accepted = note_resource_ingress(bytearray(valid), [], counts, status=204)
    assert accepted["accepted"] is True
    assert accepted["status"] == 204
    assert (
        installed_resource_case_completed(
            _case(telemetry_events=[accepted], inspected_body_hex=valid.hex()),
            _owned(),
        )
        is True
    )
    assert (
        installed_resource_case_completed(
            _case(
                condition="unavailable",
                telemetry_attempts=0,
                telemetry_reserved_bytes=0,
                telemetry_events=[],
            ),
            _owned(),
        )
        is True
    )
    assert (
        installed_resource_case_completed(
            _case(
                condition="opted_out",
                telemetry_attempts=0,
                telemetry_reserved_bytes=0,
                telemetry_events=[],
            ),
            _owned(),
        )
        is True
    )


def test_journey_requires_one_accepted_report_for_each_enabled_case():
    def telemetry(condition):
        enabled = condition == "enabled"
        return {
            "reports": 1 if enabled else 0,
            "malformed": 0,
            "accepted": 1 if enabled else 0,
        }

    cases = [
        {
            "condition": row["condition"],
            "workload_completed": True,
            "telemetry": telemetry(row["condition"]),
        }
        for row in resource_counterbalance_cases()
    ]
    counts = {"forbidden_metadata": 0, "reports": 2, "malformed_body": 0, "accepted": 2}
    assert (
        resource_journey_completed(
            returncode=0,
            cases=cases,
            diagnostics=False,
            private_withheld=False,
            counts=counts,
        )
        is True
    )
    denied = [dict(item) for item in cases]
    denied[2] = {**denied[2], "telemetry": {"reports": 0, "malformed": 0, "accepted": 0}}
    assert (
        resource_journey_completed(
            returncode=0,
            cases=denied,
            diagnostics=False,
            private_withheld=False,
            counts={"forbidden_metadata": 0, "reports": 1, "malformed_body": 0, "accepted": 1},
        )
        is False
    )
    assert (
        resource_journey_completed(
            returncode=0,
            cases=cases,
            diagnostics=False,
            private_withheld=False,
            counts={**counts, "forbidden_metadata": 1},
        )
        is False
    )
    assert (
        resource_journey_completed(
            returncode=0,
            cases=cases,
            diagnostics=False,
            private_withheld=False,
            counts={**counts, "reports": 3},
        )
        is False
    )
    assert (
        resource_journey_completed(
            returncode=0,
            cases=cases,
            diagnostics=False,
            private_withheld=False,
            counts={**counts, "reports": 3, "malformed_body": 1},
        )
        is False
    )
    for key in ("reports", "malformed_body"):
        incomplete = dict(counts)
        del incomplete[key]
        assert (
            resource_journey_completed(
                returncode=0,
                cases=cases,
                diagnostics=False,
                private_withheld=False,
                counts=incomplete,
            )
            is False
        )
    omitted = [dict(item) for item in cases]
    omitted[0] = {**omitted[0], "telemetry": {"malformed": 0, "accepted": 0}}
    assert (
        resource_journey_completed(
            returncode=0,
            cases=omitted,
            diagnostics=False,
            private_withheld=False,
            counts=counts,
        )
        is False
    )
    assert (
        resource_journey_completed(
            returncode=0,
            cases=cases,
            diagnostics=False,
            private_withheld=False,
            counts={**counts, "reports": 2.0},
        )
        is False
    )


def test_hard_exit_without_a_terminal_marker_is_an_unknown_total():
    launch = _Launch()
    cursor = OwnedPhaseCursor()

    def observe():
        apply_owned_marker(launch, {"phase": "96_memory_cycles"}, cursor)
        return False, None, None

    report = finalize_owned_launch(launch, cursor, observe)
    assert launch.calls == 1
    assert report["canonical_operations_completed"] == 96
    assert report["canonical_operations_known"] is False
    assert report["hosting_ready"] is False
    assert report["root_exit_code"] is None
    assert report.get("observation_error") is None
    assert report["lifetime_cpu_microseconds"] == 10

    established = _Launch()
    known = OwnedPhaseCursor()

    def finish_clean():
        apply_owned_marker(established, {"phase": "96_memory_cycles"}, known)
        apply_owned_marker(
            established,
            {"phase": "finished", "completed": 128, "completed_known": True},
            known,
        )
        return True, None, 0

    exact = finalize_owned_launch(established, known, finish_clean)
    assert established.calls == 1
    assert exact["canonical_operations_completed"] == 128
    assert exact["canonical_operations_known"] is True

    failed = _Launch()
    cursor = OwnedPhaseCursor()

    def crash_after_phase_error():
        apply_owned_marker(failed, {"phase": "96_memory_cycles"}, cursor)
        apply_owned_marker(failed, {"phase": "measuring"}, cursor)
        return False, None, None

    retained = finalize_owned_launch(failed, cursor, crash_after_phase_error)
    assert failed.calls == 1
    assert retained["canonical_operations_completed"] == 96
    assert retained["canonical_operations_known"] is False
    assert retained["observation_error"] == "invalid_phase"
    assert retained["marker_applied"] is False
