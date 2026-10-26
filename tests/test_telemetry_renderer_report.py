"""Resource evidence must compare like phases without inventing peak bounds."""

import json

import pytest

from deploy.report_telemetry_renderer import aligned_rss_growth, summarize


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
