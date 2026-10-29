"""Resource evidence must compare like phases without inventing peak bounds."""

import json

import pytest

from deploy.report_telemetry_renderer import (
    PACKET_BYTES,
    PHASE_MEMORY_CHECKPOINTS,
    V3_WIRE_PATH,
    aligned_phase_memory,
    aligned_rss_growth,
    absorb_reviewed_chunk,
    describe_diagnostic_wire,
    retain_reviewed_packet,
    summarize,
    verify_phase_memory,
    verify_process_ownership,
)
from mnemion.product_telemetry import policy


def samples(values, pid):
    return [
        {
            "name": name,
            "processes": [
                {"pid": pid, "type": "Browser", "working_set_bytes": value, "cpu_ms": index * 10}
            ],
        }
        for index, (name, value) in enumerate(zip(("start", "middle", "end"), values))
    ]


def test_different_peak_phases_do_not_cancel_each_other():
    # Per-run maxima differ by 20, but the end phase actually differs by 220.
    result = aligned_rss_growth(samples([100, 300, 100], 10), samples([100, 110, 320], 20))
    row = result["processes"][0]
    assert [point["difference_rss_growth_bytes"] for point in row["phases"]] == [0, -190, 220]
    assert row["maximum_matched_growth_difference_bytes"] == 220
    assert row["all_phases_matched"]


def test_process_replacement_does_not_become_the_previous_process_peak():
    current = samples([100, 110, 9000], 20)
    current[-1]["processes"][0]["pid"] = 21
    result = aligned_rss_growth(samples([100, 300, 100], 10), current)
    row = result["processes"][0]
    assert [point["phase"] for point in row["phases"]] == ["start", "middle"]
    assert row["maximum_matched_growth_difference_bytes"] == 0
    assert not row["all_phases_matched"]


def test_duplicate_phase_names_are_rejected():
    current = samples([100, 110, 320], 20)
    current[-1]["name"] = "middle"
    with pytest.raises(ValueError, match="Duplicate workload phases"):
        aligned_rss_growth(samples([100, 300, 100], 10), current)


def test_ambiguous_process_types_remain_unmatched():
    baseline, current = samples([100, 300, 100], 10), samples([100, 110, 320], 20)
    for rows, pid in ((baseline, 30), (current, 40)):
        for phase in rows:
            phase["processes"].extend(
                [
                    {"pid": pid, "type": "Utility", "working_set_bytes": 100},
                    {"pid": pid + 1, "type": "Utility", "working_set_bytes": 9000},
                ]
            )
    result = aligned_rss_growth(baseline, current)
    assert result["ambiguous_initial_types"] == ["Utility"]
    assert [row["type"] for row in result["processes"]] == ["Browser"]


def test_counterbalanced_results_use_their_own_baselines(tmp_path):
    cases = [
        ("r1-unavailable", "unavailable", 1, [100, 300, 100]),
        ("r1-enabled", "enabled", 1, [100, 110, 320]),
        ("r2-enabled", "enabled", 2, [100, 130, 140]),
        ("r2-unavailable", "unavailable", 2, [100, 110, 120]),
    ]
    results = []
    for index, (label, condition, replicate, values) in enumerate(cases):
        results.append(
            {
                "variant": label,
                "condition": condition,
                "replicate": replicate,
                "samples": samples(values, index + 10),
                "elapsed_ms": 100,
            }
        )
        (tmp_path / (label + "-processes.json")).write_text("[]\n")
    (tmp_path / "receipt.json").write_text(json.dumps({"results": results}))
    result = summarize(tmp_path)
    assert [row["baseline"] for row in result["comparisons"]] == [
        "r1-unavailable",
        "r2-unavailable",
    ]
    assert [
        row["aligned_rss_growth"]["processes"][0]["maximum_matched_growth_difference_bytes"]
        for row in result["comparisons"]
    ] == [220, 20]
    assert (
        result["comparisons"][0]["processes"][0]["difference_sampled_peak_rss_growth_bytes"] == 20
    )
    assert result["resource_acceptance"] is False
    assert result["phase_memory"] is False
    assert "aligned_phase_memory" not in result["comparisons"][0]
    assert len(result["limits"]) == 7
    assert result["wire_label"] == "historical-v2"
    assert result["wire_version"] == 2
    assert result["packet_bytes"] == 4
    assert result["wire_path"] == "/v1/report"


def setup_result(condition="enabled"):
    enabled = condition == "enabled"
    controls = {
        "schema_version": 1,
        "attempts": 1,
        "completed": 1,
        "failed": 0,
        "in_flight": 0,
        "overflow": False,
        "replies": [
            {
                "schema_version": 1,
                "user_enabled": enabled,
                "effective_enabled": enabled,
                "collection_available": True,
                "storage": "ready",
                "reason": "enabled" if enabled else "user_disabled",
                "connection_mode": "unmetered",
                "disclosure_acknowledged": enabled,
                "store_generation_valid": True,
            }
        ],
    }
    if condition == "unavailable":
        controls.update(attempts=0, completed=0, replies=[])
    return {
        "variant": condition,
        "condition": condition,
        "samples": samples([100, 110, 120], 10),
        "elapsed_ms": 100,
        "setup_controls": controls,
    }


def setup_summary(tmp_path, results, *, required=True):
    for result in results:
        (tmp_path / (result["variant"] + "-processes.json")).write_text("[]\n")
    (tmp_path / "receipt.json").write_text(
        json.dumps(
            {
                "setup_controls_required": required,
                "results": results,
            }
        )
    )
    return summarize(tmp_path)


def test_new_comparison_cannot_pass_with_missing_native_setup_reply(tmp_path):
    current = setup_result()
    del current["setup_controls"]
    with pytest.raises(ValueError, match="setup control"):
        setup_summary(tmp_path, [setup_result("unavailable"), current])


@pytest.mark.parametrize(
    "change",
    [
        {"failed": 1},
        {"in_flight": 1},
        {"completed": 0},
        {"attempts": True},
        {"overflow": True},
        {"replies": []},
    ],
)
def test_failed_or_unsettled_setup_is_not_qualified(tmp_path, change):
    current = setup_result()
    current["setup_controls"].update(change)
    with pytest.raises(ValueError, match="setup control"):
        setup_summary(tmp_path, [setup_result("unavailable"), current])


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_enabled", False),
        ("effective_enabled", False),
        ("collection_available", False),
        ("storage", "unreadable"),
        ("reason", "disclosure_required"),
        ("connection_mode", "auto"),
        ("disclosure_acknowledged", False),
        ("store_generation_valid", False),
    ],
)
def test_setup_reply_must_match_the_actual_declared_case(tmp_path, field, value):
    current = setup_result()
    current["setup_controls"]["replies"][0][field] = value
    with pytest.raises(ValueError, match="setup control"):
        setup_summary(tmp_path, [setup_result("unavailable"), current])


def test_unavailable_build_must_not_start_privacy_setup_control(tmp_path):
    current = setup_result()
    current.update(variant="unavailable", condition="unavailable")
    with pytest.raises(ValueError, match="setup control"):
        setup_summary(tmp_path, [current])


def test_setup_proof_is_separate_from_resource_acceptance(tmp_path):
    result = setup_summary(
        tmp_path,
        [
            setup_result(name)
            for name in [
                "unavailable",
                "opted_out",
                "enabled",
            ]
        ],
    )
    assert all(row["setup_controls_verified"] for row in result["observations"])
    assert result["resource_acceptance"] is False


def test_setup_controls_follow_real_optout_disclosure_revocation(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://collector.invalid/v1/report")
    status = policy.configure(
        tmp_path / "privacy",
        {
            "enabled": False,
            "expected_revision": 0,
            "disclosure_version": 1,
            "connection_mode": "unmetered",
        },
        policy_path=tmp_path / "company-absent.json",
    )
    assert status["disclosure_version"] == 0
    assert status["reason"] == "user_disabled"
    current = setup_result("opted_out")
    reply = current["setup_controls"]["replies"][0]
    for name in ("user_enabled", "effective_enabled", "collection_available", "storage", "reason"):
        reply[name] = status[name]
    reply["disclosure_acknowledged"] = (
        status["disclosure_version"] == status["required_disclosure_version"]
    )
    result = setup_summary(tmp_path, [setup_result("unavailable"), current])
    assert all(row["setup_controls_verified"] for row in result["observations"])
    assert result["resource_acceptance"] is False


def test_opted_out_setup_must_not_retain_a_disclosure_acknowledgment(tmp_path):
    current = setup_result("opted_out")
    current["setup_controls"]["replies"][0]["disclosure_acknowledged"] = True
    with pytest.raises(ValueError, match="setup control"):
        setup_summary(tmp_path, [setup_result("unavailable"), current])


def test_old_results_remain_readable_without_inventing_control_proof(tmp_path):
    current = setup_result("unavailable")
    del current["setup_controls"]
    result = setup_summary(tmp_path, [current], required=False)
    assert result["observations"][0]["setup_controls_verified"] is False


def owned_samples():
    result = samples([100, 110, 120], 10)
    for sample in result:
        sample["processes"][0]["role"] = "app_main"
        sample["processes"].append(
            {
                "pid": 20,
                "type": "Tab",
                "role": "app_renderer",
                "working_set_bytes": 200,
                "cpu_ms": sample["processes"][0]["cpu_ms"],
            }
        )
        sample["ownership"] = {
            "schema_version": 1,
            "main_pid": 10,
            "renderer_pid": 20,
            "app_windows": 1,
            "all_windows": 1,
            "devtools_present": False,
            "renderer_processes": 1,
            "valid": True,
        }
    return result


def test_extra_renderer_cannot_hide_behind_a_valid_owner_flag():
    current = owned_samples()
    current[1]["processes"].append(
        {
            "pid": 21,
            "type": "Tab",
            "role": "Tab",
            "working_set_bytes": 9000,
        }
    )
    with pytest.raises(ValueError, match="ownership"):
        verify_process_ownership(current, required=True)


def test_replacement_renderer_does_not_keep_the_old_ownership():
    current = owned_samples()
    current[-1]["processes"][1]["pid"] = 21
    current[-1]["ownership"]["renderer_pid"] = 21
    with pytest.raises(ValueError, match="ownership"):
        verify_process_ownership(current, required=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("devtools_present", True),
        ("all_windows", 2),
        ("renderer_pid", True),
    ],
)
def test_uncertain_window_state_is_not_qualified(field, value):
    current = owned_samples()
    current[1]["ownership"][field] = value
    with pytest.raises(ValueError, match="ownership"):
        verify_process_ownership(current, required=True)


def test_old_receipts_stay_readable_without_inventing_new_ownership_proof():
    assert verify_process_ownership(samples([100, 110, 120], 10)) is False
    with pytest.raises(ValueError, match="actual app process ownership"):
        verify_process_ownership(samples([100, 110, 120], 10), required=True)
    assert verify_process_ownership(owned_samples(), required=True)


def test_a_process_role_present_only_in_one_case_stays_visible():
    baseline, current = samples([100, 110, 120], 10), samples([100, 110, 120], 20)
    for sample in current:
        sample["processes"].append({"pid": 30, "type": "Utility", "working_set_bytes": 100})
    assert aligned_rss_growth(baseline, current)["unmatched_initial_roles"] == ["Utility"]


def test_a_transient_process_is_retained_and_prevents_complete_cpu_accounting(tmp_path):
    current = samples([100, 110, 120], 10)
    current[1]["processes"].append(
        {
            "pid": 30,
            "type": "Utility",
            "working_set_bytes": 9000,
            "cpu_ms": 50,
        }
    )
    result = {"variant": "unavailable", "samples": current, "elapsed_ms": 100}
    (tmp_path / "receipt.json").write_text(json.dumps({"results": [result]}))
    (tmp_path / "unavailable-processes.json").write_text("[]\n")
    observed = summarize(tmp_path)["observations"][0]
    assert observed["new_electron_processes_seen"] == 1
    assert observed["new_electron_processes_at_end"] == 0
    assert observed["electron_cpu_ms"] is None
    transient = observed["processes"][1]
    assert not transient["present_at_start"] and not transient["present_at_end"]
    assert transient["cpu_ms"] is None


def test_comparison_does_not_accept_a_partial_or_profiled_case_selection(tmp_path):
    (tmp_path / "receipt.json").write_text(
        json.dumps(
            {
                "comparison": True,
                "attribution": False,
                "review_journey": False,
                "declared_case_order": ["r1-enabled"],
                "results": [{"variant": "r1-enabled"}],
            }
        )
    )
    with pytest.raises(ValueError, match="complete declared six-case order"):
        summarize(tmp_path)


def test_cpu_difference_is_reported_for_each_comparable_process(tmp_path):
    baseline, current = samples([100, 110, 120], 10), samples([100, 120, 130], 20)
    current[-1]["processes"][0]["cpu_ms"] = 70
    results = [
        {"variant": "unavailable", "samples": baseline, "elapsed_ms": 100},
        {"variant": "enabled", "samples": current, "elapsed_ms": 120},
    ]
    (tmp_path / "receipt.json").write_text(json.dumps({"results": results}))
    for label in ("unavailable", "enabled"):
        (tmp_path / (label + "-processes.json")).write_text("[]\n")
    row = summarize(tmp_path)["comparisons"][0]["processes"][0]
    assert row["difference_cpu_ms"] == 50
    assert row["difference_cpu_percent_one_core_over_baseline_elapsed"] == 50


def phase_counters(rss_anon, vm_rss=1024):
    return {
        "linux": {
            "VmRSS": vm_rss,
            "VmHWM": 2048,
            "RssAnon": rss_anon,
            "RssFile": 4096,
            "RssShmem": 0,
        },
        "heap": {
            "total_heap_size": 8192,
            "total_physical_size": 8192,
            "used_heap_size": 0,
            "malloced_memory": 0,
        },
    }


def comparison_sample(name, main_bytes, rss_anon, vm_rss=1024):
    return {
        "name": name,
        "processes": [
            {
                "pid": 10,
                "type": "Browser",
                "role": "app_main",
                "working_set_bytes": main_bytes,
                "cpu_ms": 10,
            },
            {
                "pid": 20,
                "type": "Tab",
                "role": "app_renderer",
                "working_set_bytes": 200,
                "cpu_ms": 10,
            },
        ],
        "ownership": {
            "schema_version": 1,
            "main_pid": 10,
            "renderer_pid": 20,
            "app_windows": 1,
            "all_windows": 1,
            "devtools_present": False,
            "renderer_processes": 1,
            "valid": True,
        },
        "phase_memory": phase_counters(rss_anon, vm_rss),
    }


PHASE_CASES = (
    ("r1-unavailable", "unavailable", 1),
    ("r1-opted_out", "opted_out", 1),
    ("r1-enabled", "enabled", 1),
    ("r2-enabled", "enabled", 2),
    ("r2-opted_out", "opted_out", 2),
    ("r2-unavailable", "unavailable", 2),
)


def phase_case_result(label, condition, replicate):
    rows = []
    for name in PHASE_MEMORY_CHECKPOINTS:
        if label == "r1-unavailable" and name == "96_memory_cycles":
            main, anon, vm_rss = 900_000, 8_000, None
        elif label == "r1-unavailable":
            main, anon, vm_rss = 1_000_000, 10_000, 1024
        elif label == "r1-enabled" and name == "96_memory_cycles":
            main, anon, vm_rss = 2_100_000, 12_000, 50_000
        elif label == "r1-enabled":
            main, anon, vm_rss = 2_000_000, 11_000, 4096
        else:
            main, anon, vm_rss = 1_000_000, 10_000, 1024
        rows.append(comparison_sample(name, main, anon, vm_rss))
    return {
        "variant": label,
        "condition": condition,
        "replicate": replicate,
        "comparison": True,
        "phase_memory": True,
        "devtools_auto_open": False,
        "process_ownership_verified": True,
        "allocation": {"enabled": False},
        "elapsed_ms": 1000,
        "samples": rows,
    }


def phase_summary(tmp_path, *, flagged=True):
    results = [phase_case_result(*case) for case in PHASE_CASES]
    for result in results:
        (tmp_path / (result["variant"] + "-processes.json")).write_text("[]\n")
    (tmp_path / "receipt.json").write_text(
        json.dumps(
            {
                "comparison": True,
                "attribution": False,
                "review_journey": False,
                "phase_memory": flagged,
                "declared_case_order": [label for label, _, _ in PHASE_CASES],
                "results": results,
            }
        )
    )
    return summarize(tmp_path)


def test_phase_memory_reports_matched_counters_without_replacing_rss(tmp_path):
    result = phase_summary(tmp_path)
    assert result["schema_version"] == 3
    assert result["phase_memory"] is True
    assert result["resource_acceptance"] is False
    assert len(result["limits"]) == 8
    assert "do not replace working-set RSS" in result["limits"][-1]
    compared = next(row for row in result["comparisons"] if row["variant"] == "r1-enabled")
    main = next(
        row for row in compared["aligned_rss_growth"]["processes"] if row["role"] == "app_main"
    )
    assert main["maximum_matched_growth_difference_bytes"] == 200_000
    memory = compared["aligned_phase_memory"]
    assert set(memory) == {"phases", "unmatched_phases", "scope"}
    assert "Not a working-set replacement" in memory["scope"]
    phase = next(row for row in memory["phases"] if row["phase"] == "96_memory_cycles")
    assert phase["difference_growth_bytes"]["RssAnon"] == 3_000
    assert phase["difference_growth_bytes"]["VmRSS"] is None
    assert phase["difference_growth_bytes"]["used_heap_size"] == 0
    assert phase["difference_growth_bytes"]["malloced_memory"] == 0


def test_null_phase_counter_is_not_treated_as_zero():
    def row(name, rss_anon, vm_rss):
        return {"name": name, "phase_memory": phase_counters(rss_anon, vm_rss)}

    aligned = aligned_phase_memory(
        [
            row("before_workspace_connect", 0, None),
            row("96_memory_cycles", 0, None),
        ],
        [
            row("before_workspace_connect", 0, 0),
            row("96_memory_cycles", 0, 0),
        ],
    )
    difference = aligned["phases"][1]["difference_growth_bytes"]
    assert difference["RssAnon"] == 0
    assert difference["VmRSS"] is None
    assert "maximum_matched_growth_difference_bytes" not in aligned


def test_unlabelled_samples_cannot_be_summarized_as_an_old_comparison(tmp_path):
    with pytest.raises(ValueError, match="cannot carry phase-memory counters"):
        phase_summary(tmp_path, flagged=False)


def test_phase_memory_without_comparison_is_rejected(tmp_path):
    (tmp_path / "receipt.json").write_text(
        json.dumps(
            {
                "phase_memory": True,
                "attribution": False,
                "review_journey": False,
                "results": [],
            }
        )
    )
    with pytest.raises(ValueError, match="unattributed comparison"):
        summarize(tmp_path)


@pytest.mark.parametrize("value", [True, "3220 kB", -1, 1.5])
def test_non_integer_phase_counters_are_rejected(value):
    result = phase_case_result("r1-enabled", "enabled", 1)
    result["samples"][0]["phase_memory"]["linux"]["RssFile"] = value
    with pytest.raises(ValueError, match="non-negative integers or null"):
        verify_phase_memory(result, required=True)


def test_an_extra_phase_memory_string_is_rejected():
    result = phase_case_result("r1-enabled", "enabled", 1)
    result["samples"][0]["phase_memory"]["linux"]["Name"] = "bash"
    with pytest.raises(ValueError, match="fixed counters"):
        verify_phase_memory(result, required=True)


def test_valid_phase_memory_absence_passes_the_normal_journey_gate():
    ordinary = {
        "comparison": True,
        "phase_memory": False,
        "samples": [{"name": "before_workspace_connect"}],
    }
    absent = verify_phase_memory(ordinary, required=False)
    assert absent is None
    assert absent is not False
    enabled = verify_phase_memory(phase_case_result("r1-enabled", "enabled", 1), required=True)
    assert enabled is True
    smuggled = {
        "comparison": True,
        "samples": [{"name": "before_workspace_connect", "phase_memory": phase_counters(0)}],
    }
    try:
        absent = verify_phase_memory(smuggled, required=False)
    except ValueError:
        absent = False
    assert absent is False


def test_reviewed_v3_capture_keeps_only_an_exact_packet():
    packet = bytes(range(PACKET_BYTES))
    assert PACKET_BYTES == 25
    assert V3_WIRE_PATH == "/v3/report"
    assert retain_reviewed_packet([packet], review=False) is None
    assert retain_reviewed_packet([packet], review=True) == packet.hex()
    assert retain_reviewed_packet([packet[:10], packet[10:]], review=True) == packet.hex()
    assert retain_reviewed_packet([packet[:4]], review=True) is None
    assert retain_reviewed_packet([packet + b"\x00"], review=True) is None
    assert retain_reviewed_packet([packet[:4], b"more than the fixed packet"], review=True) is None
    assert retain_reviewed_packet([None], review=True) is None
    captured, kept = absorb_reviewed_chunk(bytearray(packet), 1, b"\x00")
    assert captured is None and kept == 2
    captured = bytearray()
    kept = 0
    for _ in range(8):
        captured, kept = absorb_reviewed_chunk(captured, kept, b"\x01")
    assert captured is not None and len(captured) == 8
    captured, kept = absorb_reviewed_chunk(captured, kept, b"\x01")
    assert captured is None and kept == 9
    captured, kept = absorb_reviewed_chunk(None, kept, packet)
    assert captured is None


def test_v3_diagnostic_is_labelled_and_cannot_reuse_a_v2_result(tmp_path):
    observed = {
        "variant": "unavailable",
        "wire_version": 3,
        "wire_path": "/v3/report",
        "packet_bytes": 25,
        "samples": samples([100, 110, 120], 10),
        "elapsed_ms": 100,
    }
    (tmp_path / "unavailable-processes.json").write_text("[]\n")
    (tmp_path / "receipt.json").write_text(
        json.dumps(
            {
                "wire_version": 3,
                "wire_path": "/v3/report",
                "packet_bytes": 25,
                "results": [observed],
            }
        )
    )
    result = summarize(tmp_path)
    assert result["wire_label"] == "v3"
    assert result["packet_bytes"] == 25
    assert result["resource_acceptance"] is False
    described = describe_diagnostic_wire({"results": []})
    assert described["wire_label"] == "historical-v2"
    historical_body = describe_diagnostic_wire(
        {"results": [{"collector": {"reports": 1, "accepted": 1, "body_bytes": 4}}]}
    )
    assert historical_body["wire_label"] == "historical-v2"
    assert historical_body["packet_bytes"] == 4
    v3 = {"wire_version": 3, "wire_path": "/v3/report", "packet_bytes": 25}
    with pytest.raises(ValueError, match="same wire contract"):
        describe_diagnostic_wire({**v3, "results": [{}]})
    with pytest.raises(ValueError, match="conflicts with its declared version"):
        describe_diagnostic_wire(
            {**v3, "results": [{"wire_version": 3, "packet_bytes": 4, "wire_path": "/v1/report"}]}
        )
    with pytest.raises(ValueError, match="complete or absent"):
        describe_diagnostic_wire({"wire_version": 3, "wire_path": "/v3/report", "results": []})
