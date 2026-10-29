"""V3 codec, sensitivity, cohorts, suppression and legacy boundaries.

These checks exercise the reference mechanism. They do not rerun installed
resource trials or treat modelled counts as guaranteed fleet results.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
from fractions import Fraction

import pytest
from starlette.testclient import TestClient

from mnemion.product_telemetry import CONTRACT, catalog, wire
from mnemion.product_telemetry.aggregate_v3 import (
    DENOMINATOR,
    HALFWIDTH,
    NUMERATOR,
    SENSITIVITY,
    THRESHOLD,
    AggregateWindow,
    epsilon_holds,
    vector_l1,
)
from mnemion.product_telemetry.cohorts import reviewed_cohorts
from mnemion.product_telemetry.collector import Collector
from mnemion.product_telemetry.collector_v3 import CollectorV3
from mnemion.product_telemetry.maintainer_v3 import main, render
from mnemion.product_telemetry.publication import validate as validate_v2
from mnemion.product_telemetry.publication_v3 import ReportStore
from mnemion.product_telemetry.utility_v3 import modelled_utility
from mnemion.product_telemetry.wire_v3 import (
    METRICS,
    PACKET_BYTES,
    WIRE,
    WireV3Error,
    decode,
    encode,
    release_slot,
    summarize,
)

GROUPS = ["usage", "reliability", "performance", "resources"]
RELEASE = (4, 46, 53)
WEEK_ZERO = 345600


def stamp(week: int) -> int:
    return WEEK_ZERO + week * 604800


def stop(limit: int) -> int:
    return limit - 1


def submission() -> dict:
    return {"kind": "submission", "workflow": "memory.recall", "surface": "desktop"}


def measured() -> list[dict]:
    return [
        submission(),
        {
            "kind": "outcome",
            "workflow": "memory.recall",
            "surface": "desktop",
            "outcome": "failed",
            "reason": "offline",
            "latency_ms": 10,
        },
        {"kind": "resource", "metric": "cpu_millicores", "value": 20},
        {"kind": "resource", "metric": "rss_bytes", "value": 70_000_000},
    ]


def release_packet(*, release=RELEASE, observations=None) -> bytes:
    return summarize(
        observations if observations is not None else measured(),
        groups=GROUPS,
        axis="release",
        release=release,
        random_below=stop,
    )


def os_packet(name: str = "linux") -> bytes:
    return summarize(measured(), groups=GROUPS, axis="os", operating_system=name, random_below=stop)


def metric_index(name: str) -> int:
    return next(index for index, metric in enumerate(METRICS) if metric["id"] == name)


def test_contract_keeps_every_catalog_metric_inside_the_daily_budget():
    covered = {metric["id"] for metric in METRICS}
    assert covered >= set(catalog.METRICS) | set(catalog.RESOURCE_METRICS)
    assert {"feature_family", "feature", "outcome", "reason"} <= covered
    assert PACKET_BYTES == 25
    assert PACKET_BYTES <= CONTRACT["limits"]["wire_bytes_per_day"]
    assert WIRE["client_budget"]["maximum_attempts_per_rolling_week"] == 7
    assert WIRE["client_budget"]["minimum_attempt_spacing_seconds"] == 86400
    assert SENSITIVITY == len(METRICS) + 1 == 20


def test_clipping_disabled_groups_and_missing_sensors_keep_one_tick():
    disabled = decode(
        summarize(
            [{"kind": "resource", "metric": "cpu_millicores", "value": 999999}],
            groups=["usage"],
            axis="release",
            release=RELEASE,
            random_below=stop,
        )
    )
    assert disabled.buckets[metric_index("cpu_millicores")] == 0
    assert disabled.buckets[metric_index("latency_ms")] == 0
    missing = decode(summarize([submission()], groups=GROUPS, axis="release", release=RELEASE, random_below=stop))
    assert missing.buckets[metric_index("latency_ms")] == 1
    assert missing.buckets[metric_index("cpu_millicores")] == 1
    assert missing.buckets[metric_index("reason")] == 1
    repeated = [submission() for _ in range(300)]
    window = AggregateWindow(2900)
    before = window._counts[:]
    assert window.contribute(summarize(repeated, groups=GROUPS, axis="release", release=RELEASE, random_below=stop))
    assert vector_l1(before, window._counts) == SENSITIVITY


def test_hostile_packets_cannot_exceed_the_contribution_or_smuggle_a_second_axis():
    good = release_packet()
    assert len(good) == PACKET_BYTES
    changed = bytearray(good)
    changed[5] = 1
    with pytest.raises(WireV3Error):
        decode(bytes(changed))
    changed = bytearray(good)
    changed[6] = 255
    with pytest.raises(WireV3Error):
        decode(bytes(changed))
    with pytest.raises(WireV3Error):
        decode(good + b"\x00")
    with pytest.raises(WireV3Error):
        decode(bytes([2, 0, 0, 0]))
    smuggled = bytearray(os_packet())
    smuggled[3] = 46
    smuggled[4] = 53
    with pytest.raises(WireV3Error):
        decode(bytes(smuggled))
    window = AggregateWindow(2900)
    assert window.contribute(good)
    assert not window.contribute(os_packet())
    assert not window.contribute(bytes(changed))
    assert window._total == 1


def test_one_report_moves_the_whole_query_by_the_proved_sensitivity():
    window = AggregateWindow(2900)
    before = window._counts[:]
    assert window.contribute(release_packet())
    assert vector_l1(before, window._counts) == SENSITIVITY
    before = window._counts[:]
    assert window.contribute(release_packet(release=(9, 8, 7)))
    assert vector_l1(before, window._counts) == SENSITIVITY
    assert epsilon_holds()
    decay = Fraction(NUMERATOR, DENOMINATOR)
    unit = Fraction(DENOMINATOR, NUMERATOR)
    for point in range(-20, 21):
        left = decay ** abs(point)
        right = decay ** abs(point - 1)
        assert left / right <= unit
    assert unit**SENSITIVITY <= 3
    assert DENOMINATOR**SENSITIVITY <= 3 * NUMERATOR**SENSITIVITY


def test_release_coordinates_keep_their_meaning_and_unknown_values_collapse():
    assert release_slot(4, 46, 53) == 0
    assert release_slot(4, 46, 54) is None
    listed = decode(release_packet())
    unknown = decode(release_packet(release=(4, 46, 54)))
    assert listed.axis == "release" and listed.cohort_id == "4.46.53" and listed.cohort_index == 0
    assert unknown.cohort_id == "unlisted" and unknown.cohort_index == 1
    assert WIRE["release_allowlist"][0]["id"] == "4.46.53"
    reversed_slots = sorted(WIRE["release_allowlist"], key=lambda item: -item["slot"])
    assert {item["slot"]: item["id"] for item in reversed_slots}[0] == "4.46.53"


def test_suppression_uses_noisy_output_and_does_not_isolate_one_cohort():
    single = AggregateWindow(2900)
    for _ in range(100):
        assert single.contribute(release_packet())
    exact = single.seal(stop)
    assert {row["id"]: row["denominator"] for row in exact["cohorts"]} == {"4.46.53": 100, "unlisted": 0}
    assert exact["suppressed_remainder"] is None
    calls = {"n": 0}

    def push_down(limit: int) -> int:
        calls["n"] += 1
        if 2 <= calls["n"] <= 81:
            return 0
        return limit - 1

    moved = AggregateWindow(2900)
    for _ in range(100):
        assert moved.contribute(release_packet())
    hidden = moved.seal(push_down)
    assert hidden["cohorts"] == []
    assert hidden["global"]["denominator"] == 20
    assert hidden["suppressed_remainder"]["ids"] == ["4.46.53", "unlisted"]
    assert hidden["suppressed_remainder"]["denominator"] == 20
    grouped = AggregateWindow(2901)
    for _ in range(80):
        assert grouped.contribute(os_packet("linux"))
    mixed = grouped.seal(stop)
    assert [row["id"] for row in mixed["cohorts"]] == ["linux"]
    assert mixed["suppressed_remainder"]["ids"] == ["windows", "macos", "other"]
    assert mixed["global"]["denominator"] == 80
    assert mixed["other_axis_published"] is False


def test_quantiles_are_bucket_bounds_or_insufficient_precision():
    window = AggregateWindow(2900)
    for _ in range(120):
        assert window.contribute(release_packet())
    report = window.seal(stop)
    latency = next(item for item in report["global"]["metrics"] if item["id"] == "latency_ms")
    assert latency["quantiles"]["p95"]["state"] == "bucket_bounds"
    assert latency["quantiles"]["p95"]["lower_exclusive"] == 9
    assert latency["quantiles"]["p95"]["upper_inclusive"] == 49
    assert "value" not in latency["quantiles"]["p95"]
    assert "p95" not in latency["counts"]
    spread = AggregateWindow(2900)
    slow = measured()
    slow[1] = {**slow[1], "latency_ms": 5000}
    for index in range(120):
        observations = measured() if index % 2 == 0 else slow
        assert spread.contribute(release_packet(observations=observations))
    mixed = spread.seal(stop)
    mixed_latency = next(item for item in mixed["global"]["metrics"] if item["id"] == "latency_ms")
    assert mixed_latency["quantiles"]["p50"] == {"state": "insufficient_precision"}
    assert mixed_latency["quantiles"]["p95"] == {"state": "insufficient_precision"}


def test_closed_weeks_are_immutable_bounded_and_keep_no_raw_packet(tmp_path):
    clock = {"week": 2910}
    store = ReportStore(tmp_path, clock=lambda: stamp(clock["week"]))
    packet = release_packet()
    window = AggregateWindow(2908)
    assert window.contribute(packet)
    stored = window.seal(stop)
    assert not window._total and not any(window._counts)
    store(stored)
    assert packet not in (tmp_path / "reports-v3.sqlite3").read_bytes()
    with pytest.raises(WireV3Error):
        store(stored)
    for week in range(2902, 2910):
        if week == 2908:
            continue
        store(AggregateWindow(week).seal(stop))
    assert len(store.reports()) == 8
    with pytest.raises(WireV3Error):
        store(AggregateWindow(2904).seal(stop))
    clock["week"] = 2911
    assert len(store.reports()) == 7
    store(AggregateWindow(2910).seal(stop))
    assert len(store.reports()) == 8
    assert not (tmp_path / "reports.sqlite3").exists()
    later = AggregateWindow(2908)
    assert later._total == 0


def test_v2_paths_and_disclosure_stay_unchanged():
    assert CONTRACT["default_enabled"] is True
    assert CONTRACT["collection_available"] is False
    assert CONTRACT["destination"] is None
    cell = catalog.observation(submission())[1][0]
    legacy = wire.prepare(
        [(cell, 1)],
        groups=["usage", "resources", "reliability"],
        cohorts=reviewed_cohorts(),
        random_below=stop,
    )
    assert len(legacy) == 4 and legacy[0] == 2
    with pytest.raises(WireV3Error):
        decode(legacy)
    from mnemion.product_telemetry.wire import WireError

    with pytest.raises(WireError):
        validate_v2(AggregateWindow(2900).seal(stop))
    current = [stamp(2900)]
    legacy_app = Collector(lambda _result: None, clock=lambda: current[0])
    reference = CollectorV3(lambda _result: None, clock=lambda: current[0], random_below=stop)
    with TestClient(legacy_app) as client, TestClient(reference) as other:
        assert client.post("/v3/report", content=release_packet()).status_code == 404
        assert other.post("/v1/report", content=legacy).status_code == 404
        assert other.post("/v3/report", content=release_packet()).status_code == 204
        assert reference._window._total == 1
    from mnemion.product_telemetry.cli import execute

    schema = execute(None, {"action": "schema"})
    assert "v3" not in schema["actions"]
    assert schema["disclosure"]["collection_available"] is False
    assert schema["disclosure"]["destination"] is None
    assert schema["disclosure"]["default_enabled"] is True


def test_request_bytes_cannot_select_the_test_random_source():
    published = []
    current = [stamp(2900)]
    app = CollectorV3(published.append, clock=lambda: current[0])
    assert app._random_below is None
    with TestClient(app) as client:
        assert (
            client.post(
                "/v3/report",
                content=release_packet(),
                headers={"X-Deterministic-Noise": "0", "X-Test-Random": "zero"},
            ).status_code
            == 204
        )
        current[0] = stamp(2901)
        assert app._advance()
    exact = AggregateWindow(2900)
    assert exact.contribute(release_packet())
    assert published[0]["global"]["metrics"] != exact.seal(stop)["global"]["metrics"]


def test_python_activity_supplies_cohorts_without_enabling_collection(tmp_path, monkeypatch):
    from mnemion.product_telemetry import activity, delivery, policy

    captured = {}

    class Budget:
        def __init__(self, *_args, **_kwargs):
            pass

        def reserve(self, **kwargs):
            captured.update(kwargs)
            return None

        def cancel(self, _report):
            pass

    monkeypatch.setattr(delivery, "DeliveryBudget", Budget)
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)

    class Endpoint:
        def validate(self):
            return True

    async def scenario():
        owner = activity.Activity(tmp_path, Endpoint(), lambda: {})
        await owner._attempt(1, "a" * 32)
        monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", False)
        await owner._attempt(1, "b" * 32)

    asyncio.run(scenario())
    cohorts = captured["cohorts"]
    assert set(cohorts) == {"platform", "architecture", "release_family"}
    assert cohorts["release_family"] == "4"
    assert all(cohorts[name] in wire.COHORTS[name]["values"] for name in cohorts)
    assert captured["expected_generation"] == "a" * 32


def test_utility_model_names_its_limits_at_each_population():
    table = modelled_utility()
    flags = {
        (row["installations"], row["reports_per_installation"]): (
            row["denominator_usually_published"],
            row["coarse_majority_bucket_usable"],
            row["uniform_eight_bucket_usable"],
        )
        for row in table["rows"]
    }
    assert flags[(10, 2)] == (False, False, False)
    assert flags[(10, 7)] == (False, False, False)
    assert flags[(100, 2)] == (True, False, False)
    assert flags[(100, 7)] == (True, True, False)
    assert flags[(1000, 2)] == (True, True, True)
    assert flags[(1000, 7)] == (True, True, True)
    assert table["rows"][0]["distinct_people"] == "not_identified"
    assert table["rows"][0]["expected_counts_are_not_guaranteed"] is True
    assert "not a person" in table["limitations"][-2]
    assert HALFWIDTH == 55
    assert THRESHOLD == 64


def test_maintainer_export_is_validated_and_is_not_a_privacy_page(tmp_path, capsys):
    from mnemion.product_telemetry.reporting import reporting_week
    import time

    current = reporting_week(time.time())
    store = ReportStore(tmp_path, clock=lambda: stamp(current))
    store(AggregateWindow(current - 1).seal(stop))
    document = json.loads(render(store.reports(), "json"))
    assert document["summary"]["ordinary_privacy_settings_contain_fleet_data"] is False
    assert document["summary"]["reports_are_not_unique_people"] is True
    assert document["summary"]["noise_is_not_independent_user_or_causal_inference"] is True
    assert document["summary"]["collection_available"] is False
    table = list(csv.DictReader(io.StringIO(render(store.reports(), "csv"))))
    assert table[0]["record"] == "summary"
    assert table[0]["reports_are_not_unique_people"] == "True"
    assert main(["--utility", "--format", "json"]) == 0
    utility = json.loads(capsys.readouterr().out)
    assert utility["rows"][0]["installations"] == 10
    assert main(["--state", str(tmp_path), "--format", "json"]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["summary"]["report_count"] == 1
    assert main(["--state", "relative", "--format", "json"]) == 2
