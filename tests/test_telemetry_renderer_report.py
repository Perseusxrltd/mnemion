"""Resource evidence must compare like phases without inventing peak bounds."""

import json

import pytest

from deploy.report_telemetry_renderer import aligned_rss_growth, summarize, verify_process_ownership


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
