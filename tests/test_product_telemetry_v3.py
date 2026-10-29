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
from pathlib import Path

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
    _quantiles,
    envelope_radius,
    epsilon_holds,
    validate,
    vector_l1,
)
from mnemion.product_telemetry.cohorts import reviewed_cohorts
from mnemion.product_telemetry.collector import Collector
from mnemion.product_telemetry.collector_v3 import CollectorV3
from mnemion.product_telemetry.maintainer_v3 import main, render
from mnemion.product_telemetry.publication import validate as validate_v2
from mnemion.product_telemetry.publication_v3 import MAX_REPORT_BYTES, ReportStore
from mnemion.product_telemetry.utility_v3 import modelled_utility
from mnemion.product_telemetry.wire_v3 import (
    METRIC_BY_ID,
    METRICS,
    PACKET_BYTES,
    WIRE,
    WireV3Error,
    bucket_label,
    decode,
    encode,
    prepare,
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


def pinned(bit: int):
    state = {"n": 0}

    def random_below(limit: int) -> int:
        state["n"] += 1
        if state["n"] == 1:
            if limit != 2:
                raise AssertionError(limit)
            return bit
        return limit - 1

    return random_below


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
        release=release,
        operating_system="linux",
        random_below=pinned(0),
    )


def os_packet(name: str = "linux") -> bytes:
    return summarize(
        measured(),
        groups=GROUPS,
        release=RELEASE,
        operating_system=name,
        random_below=pinned(1),
    )


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
    assert WIRE["privacy"]["unit"] == "add_or_remove_one_input_report_including_admission_and_clipping"
    assert WIRE["axis_rule"]["name"] == "per_report_secure_coin"
    assert "even_week" not in WIRE["axis_rule"]
    assert WIRE["admission"]["cross_report_eviction"] is False
    assert "maximum_reports_per_window" not in WIRE["reporting"]
    assert WIRE["storage"]["maximum_report_bytes"] == MAX_REPORT_BYTES > 209365
    assert WIRE["storage"]["maximum_database_bytes"] > 8 * MAX_REPORT_BYTES


def test_clipping_disabled_groups_and_missing_sensors_keep_one_tick():
    disabled = decode(
        summarize(
            [{"kind": "resource", "metric": "cpu_millicores", "value": 999999}],
            groups=["usage"],
            release=RELEASE,
            operating_system="linux",
            random_below=pinned(0),
        )
    )
    assert disabled.buckets[metric_index("cpu_millicores")] == 0
    assert disabled.buckets[metric_index("latency_ms")] == 0
    missing = decode(
        summarize(
            [submission()],
            groups=GROUPS,
            release=RELEASE,
            operating_system="linux",
            random_below=pinned(0),
        )
    )
    assert missing.buckets[metric_index("latency_ms")] == 1
    assert missing.buckets[metric_index("cpu_millicores")] == 1
    assert missing.buckets[metric_index("reason")] == 1
    repeated = [submission() for _ in range(300)]
    window = AggregateWindow(2900)
    before = window._counts[:]
    assert window.contribute(
        summarize(repeated, groups=GROUPS, release=RELEASE, operating_system="linux", random_below=pinned(0))
    )
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
    assert window.contribute(os_packet())
    assert not window.contribute(bytes(changed))
    assert window._total == 2


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
    listed = release_packet()
    linux = os_packet("linux")
    windows = os_packet("windows")
    original = _counts([listed, linux])
    inserted = _counts([windows, listed, linux])
    assert vector_l1(original, inserted) == SENSITIVITY


def _counts(packets: list[bytes]) -> list[int]:
    window = AggregateWindow(2900)
    accepted = [window.contribute(packet) for packet in packets]
    assert accepted == [True] * len(packets)
    return window._counts


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
    assert exact["suppressed_remainder"]["axes"] == [
        {
            "axis": "os",
            "ids": ["windows", "macos", "linux", "other"],
            "denominator": 0,
            "metrics": exact["suppressed_remainder"]["axes"][0]["metrics"],
            "quantiles": "not_a_single_population",
        }
    ]
    assert [row["axis"] for row in exact["cohorts"]] == ["release", "release"]
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
    release_group = hidden["suppressed_remainder"]["axes"][0]
    assert release_group["ids"] == ["4.46.53", "unlisted"]
    assert release_group["denominator"] == 20
    assert hidden["suppressed_remainder"]["axes"][1]["axis"] == "os"
    grouped = AggregateWindow(2901)
    for _ in range(80):
        assert grouped.contribute(os_packet("linux"))
    mixed = grouped.seal(stop)
    assert [row["id"] for row in mixed["cohorts"]] == ["linux"]
    assert {row["axis"]: row["ids"] for row in mixed["suppressed_remainder"]["axes"]} == {
        "release": ["4.46.53", "unlisted"],
        "os": ["windows", "macos", "other"],
    }
    assert mixed["global"]["denominator"] == 80
    assert mixed["domain"]["releases"][0]["id"] == "4.46.53"
    assert mixed["admission"]["cross_report_eviction"] is False


def test_quantiles_are_bucket_bounds_or_insufficient_precision():
    metric = METRIC_BY_ID["latency_ms"]
    counterexample = [0, 0, 200, 50, 0, 0, 0, 0, 0, 0]
    refused = _quantiles(counterexample, metric, parts=1)
    assert refused["p50"]["state"] == "insufficient_precision"
    assert refused["p95"]["state"] == "insufficient_precision"
    assert refused["p95"]["qualification"] == "mechanism_envelope_not_a_percentile_confidence_interval"
    assert "lower_inclusive" not in refused["p95"]
    assert "upper_inclusive" not in refused["p95"]
    measurement = counterexample[2:]
    assert sum(measurement) == 250
    assert sum(measurement[:1]) < 0.95 * 250 <= sum(measurement[:2])
    assert envelope_radius(1, len(measurement)) > HALFWIDTH
    window = AggregateWindow(2900)
    packet = release_packet()
    for _ in range(20000):
        assert window.contribute(packet)
    report = window.seal(stop)
    cohort = next(row for row in report["cohorts"] if row["id"] == "4.46.53")
    cohort_latency = next(item for item in cohort["metrics"] if item["id"] == "latency_ms")
    global_latency = next(item for item in report["global"]["metrics"] if item["id"] == "latency_ms")
    assert cohort_latency["quantiles"]["p50"]["state"] == "bucket_bounds"
    assert cohort_latency["quantiles"]["p95"]["state"] == "bucket_bounds"
    assert cohort_latency["quantiles"]["p95"]["lower_exclusive"] == 9
    assert cohort_latency["quantiles"]["p95"]["upper_inclusive"] == 49
    assert cohort_latency["quantiles"]["p95"]["qualification"] == refused["p95"]["qualification"]
    assert "value" not in cohort_latency["quantiles"]["p95"]
    assert global_latency["quantiles"]["p95"]["state"] == "insufficient_precision"
    assert global_latency["quantiles"]["p95"]["noise_parts"] > cohort_latency["quantiles"]["p95"]["noise_parts"]
    assert global_latency["quantiles"]["p95"]["envelope_radius"] > cohort_latency["quantiles"]["p95"]["envelope_radius"]
    spread = AggregateWindow(2900)
    slow = measured()
    slow[1] = {**slow[1], "latency_ms": 5000}
    for index in range(120):
        observations = measured() if index % 2 == 0 else slow
        assert spread.contribute(release_packet(observations=observations))
    mixed = spread.seal(stop)
    mixed_latency = next(item for item in mixed["global"]["metrics"] if item["id"] == "latency_ms")
    assert mixed_latency["quantiles"]["p50"]["state"] == "insufficient_precision"
    assert mixed_latency["quantiles"]["p95"]["state"] == "insufficient_precision"


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
    assert flags[(100, 2)] == (False, False, False)
    assert flags[(100, 7)] == (True, True, False)
    assert flags[(1000, 2)] == (True, True, True)
    assert flags[(1000, 7)] == (True, True, True)
    assert table["axis_split"] == "each_report_chooses_release_or_os_with_probability_one_half"
    sparse = next(row for row in table["rows"] if (row["installations"], row["reports_per_installation"]) == (100, 2))
    assert sparse["expected_axis_ticks"] == 100
    assert sparse["model_frequency_axis_clears_publish_bar"] == 0.004361
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


def test_closed_report_keeps_its_domain_when_the_allowlist_grows(tmp_path, monkeypatch, capsys):
    from mnemion.product_telemetry import aggregate_v3, wire_v3
    from mnemion.product_telemetry.reporting import reporting_week
    import time

    current = reporting_week(time.time())
    window = AggregateWindow(current - 1)
    for _ in range(100):
        assert window.contribute(release_packet())
    sealed = window.seal(stop)
    assert sealed["domain"]["unlisted_release"] == {"slot": 1, "id": "unlisted"}
    assert sealed["domain"]["releases"] == [
        {"slot": 0, "major": 4, "minor": 46, "patch": 53, "id": "4.46.53"}
    ]
    releases = (
        {"slot": 0, "major": 4, "minor": 46, "patch": 53, "id": "4.46.53"},
        {"slot": 1, "major": 4, "minor": 46, "patch": 54, "id": "4.46.54"},
    )
    by_coordinate = {(item["major"], item["minor"], item["patch"]): item for item in releases}
    monkeypatch.setattr(wire_v3, "ALLOWLIST", releases)
    monkeypatch.setattr(wire_v3, "RELEASE_BY_COORDINATE", by_coordinate)
    monkeypatch.setattr(wire_v3, "RELEASE_BY_SLOT", {item["slot"]: item for item in releases})
    monkeypatch.setattr(aggregate_v3, "ALLOWLIST", releases)
    fresh = AggregateWindow(current - 1)
    assert next(row["slot"] for row in fresh.cohorts if row["id"] == "unlisted") == 2
    assert validate(sealed)["domain"]["unlisted_release"]["slot"] == 1
    broken = json.loads(json.dumps(sealed))
    broken["domain"]["releases"][0]["id"] = "not-a-release"
    with pytest.raises(WireV3Error):
        validate(broken)
    broken = json.loads(json.dumps(sealed))
    broken["domain"]["unlisted_release"]["id"] = "misc"
    with pytest.raises(WireV3Error):
        validate(broken)
    broken = json.loads(json.dumps(sealed))
    broken["domain"]["operating_systems"][0]["id"] = "freebsd"
    with pytest.raises(WireV3Error):
        validate(broken)
    store = ReportStore(tmp_path, clock=lambda: stamp(current))
    store(sealed)
    assert main(["--state", str(tmp_path), "--format", "json"]) == 0
    exported = json.loads(capsys.readouterr().out)
    report = exported["reports"][0]
    assert report["domain"]["releases"][0]["id"] == "4.46.53"
    assert report["domain"]["unlisted_release"]["slot"] == 1
    assert report["cohorts"][0]["id"] == "4.46.53"
    assert report["cohorts"][0]["slot"] == 0


def test_maximum_release_domain_fits_eight_retained_windows(tmp_path):
    from mnemion.product_telemetry.reporting import reporting_week
    import time

    triples = [(1, 0, index) for index in range(32)]
    releases = tuple(
        {"slot": index, "major": major, "minor": minor, "patch": patch, "id": f"{major}.{minor}.{patch}"}
        for index, (major, minor, patch) in enumerate(triples)
    )
    from mnemion.product_telemetry import aggregate_v3, wire_v3

    saved = (
        wire_v3.ALLOWLIST,
        wire_v3.RELEASE_BY_COORDINATE,
        wire_v3.RELEASE_BY_SLOT,
        aggregate_v3.ALLOWLIST,
    )
    wire_v3.ALLOWLIST = releases
    wire_v3.RELEASE_BY_COORDINATE = {(item["major"], item["minor"], item["patch"]): item for item in releases}
    wire_v3.RELEASE_BY_SLOT = {item["slot"]: item for item in releases}
    aggregate_v3.ALLOWLIST = releases
    try:
        current = reporting_week(time.time())
        buckets = [2] * len(METRICS)
        window = AggregateWindow(current - 1)
        for major, minor, patch in triples:
            packet = encode("release", buckets, release=(major, minor, patch))
            for _ in range(200):
                assert window.contribute(packet)
        sealed = window.seal(stop)
        raw = json.dumps(sealed, separators=(",", ":"), allow_nan=False).encode("utf-8")
        assert len(raw) > 65536
        assert len(raw) <= MAX_REPORT_BYTES
        assert len(sealed["domain"]["releases"]) == 32
        assert sum(row["axis"] == "release" for row in sealed["cohorts"]) == 33
        store = ReportStore(tmp_path, clock=lambda: stamp(current))
        for week in range(current - 8, current):
            body = json.loads(raw)
            body["window_week"] = week
            store(body)
        assert len(store.reports()) == 8
        assert (tmp_path / "reports-v3.sqlite3").stat().st_size <= WIRE["storage"]["maximum_database_bytes"]
    finally:
        wire_v3.ALLOWLIST, wire_v3.RELEASE_BY_COORDINATE, wire_v3.RELEASE_BY_SLOT, aggregate_v3.ALLOWLIST = saved


def test_publication_failure_is_observable_and_is_not_resealed(tmp_path):
    calls = {"n": 0}

    def random_below(limit: int) -> int:
        calls["n"] += 1
        return limit - 1

    class Publisher:
        def __init__(self, store):
            self.store = store
            self.attempts = 0

        def __call__(self, result):
            self.attempts += 1
            raise WireV3Error

        def record_publication_failure(self, week):
            assert type(week) is int
            self.store.record_publication_failure(week)

        def prune(self, week):
            self.store.prune(week)

    clock = {"now": stamp(2900)}
    store = ReportStore(tmp_path, clock=lambda: clock["now"])
    publisher = Publisher(store)
    app = CollectorV3(publisher, clock=lambda: clock["now"], random_below=random_below)
    app._window.contribute(release_packet())
    clock["now"] = stamp(2901)
    assert app._advance()
    drawn = calls["n"]
    assert drawn > 0 and publisher.attempts == 1
    assert app._advance()
    assert calls["n"] == drawn and publisher.attempts == 1
    notice = {"window_week": 2900, "state": "publication_failed"}
    assert app.publication_failures == [notice]
    assert store.publication_failures() == [notice]
    assert store.reports() == []
    raw = (tmp_path / "reports-v3.sqlite3").read_bytes()
    assert b"4.46.53" not in raw
    assert b"packet" not in raw
    document = json.loads(render(store.reports(), "json", store.publication_failures()))
    assert document["summary"]["publication_failures"] == [notice]
    assert "denominator" not in document["summary"]["publication_failures"][0]


def _exact_draws(values):
    state = {"n": 0}

    def random_below(limit):
        if state["n"] >= len(values):
            raise AssertionError("extra draw")
        value = values[state["n"]]
        state["n"] += 1
        if type(value) is not int or not 0 <= value < limit:
            raise AssertionError((value, limit))
        return value

    random_below.used = lambda: state["n"]
    return random_below


def _vector_rows(case):
    if "repeat" in case:
        return [(0, 1)] * case["repeat"]
    if "rows" in case:
        return case["rows"]
    if "rows_from" in case:
        rows = []
        for item in case["rows_from"]:
            _contribution, cells = catalog.observation(item["observation"])
            picked = [cell for cell in cells if catalog.describe(cell)["metric"] == item["metric"]]
            assert len(picked) == 1
            rows.append((picked[0], item["count"]))
        return rows
    totals = {}
    order = []
    for item in case.get("observations", []):
        _contribution, cells = catalog.observation(item)
        for cell in cells:
            if cell not in totals:
                order.append(cell)
                totals[cell] = 0
            totals[cell] += 1
    return [(cell, totals[cell]) for cell in order]


def _vector_call(function, case, rows):
    draws = _exact_draws(case["draws"])
    packet = function(
        case["observations"] if function is summarize else rows,
        groups=case.get("groups", GROUPS),
        release=tuple(case.get("release", (4, 46, 53))),
        operating_system=case.get("operating_system", "linux"),
        random_below=draws,
    )
    assert draws.used() == len(case["draws"])
    return packet


def test_failed_outcome_without_a_reason_is_not_no_failure():
    failed = {"kind": "outcome", "workflow": "memory.recall", "surface": "desktop", "outcome": "failed"}
    success = {**failed, "outcome": "success"}
    deferred = {**failed, "outcome": "deferred"}
    offline = {**failed, "reason": "offline"}

    def reason_of(packet):
        decoded = decode(packet)
        return bucket_label(METRIC_BY_ID["reason"], decoded.buckets[metric_index("reason")])

    lone = summarize(
        [failed], groups=GROUPS, release=RELEASE, operating_system="linux", random_below=_exact_draws([0])
    )
    assert reason_of(lone) == "sensor_missing"
    assert lone == prepare(_vector_rows({"observations": [failed]}), groups=GROUPS, release=RELEASE,
                            operating_system="linux", random_below=_exact_draws([0]))
    assert reason_of(summarize([success], groups=GROUPS, release=RELEASE, operating_system="linux",
                                random_below=_exact_draws([0]))) == "no_failure"
    assert reason_of(summarize([deferred], groups=GROUPS, release=RELEASE, operating_system="linux",
                                random_below=_exact_draws([0]))) == "sensor_missing"
    assert reason_of(summarize([offline], groups=GROUPS, release=RELEASE, operating_system="linux",
                                random_below=_exact_draws([0]))) == "offline"
    mixed = [success, failed]
    unknown = summarize(mixed, groups=GROUPS, release=RELEASE, operating_system="linux",
                         random_below=_exact_draws([0, 0, 0]))
    assert reason_of(unknown) == "sensor_missing"
    assert unknown == prepare(_vector_rows({"observations": mixed}), groups=GROUPS, release=RELEASE,
                               operating_system="linux", random_below=_exact_draws([0, 0, 0]))
    kept = summarize(mixed, groups=GROUPS, release=RELEASE, operating_system="linux",
                      random_below=_exact_draws([0, 0, 1]))
    assert reason_of(kept) == "no_failure"


def test_bounded_client_vectors_keep_one_tick_and_reject_malformed_rows():
    fixture = Path(__file__).parents[1] / "tests/fixtures/telemetry-v3-client-vectors.json"
    document = json.loads(fixture.read_text())
    for case in document["cases"]:
        rows = _vector_rows(case)
        if case.get("error"):
            with pytest.raises(WireV3Error):
                _vector_call(prepare, case, rows)
            continue
        prepared = decode(_vector_call(prepare, case, rows))
        if "observations" in case:
            summarized = decode(_vector_call(summarize, case, rows))
            assert summarized.buckets == prepared.buckets
            assert (summarized.axis, summarized.cohort_id) == (prepared.axis, prepared.cohort_id)
        expect = case["expect"]
        if "axis" in expect:
            assert prepared.axis == expect["axis"]
        if "cohort" in expect:
            assert prepared.cohort_id == expect["cohort"]
        if "cohort_index" in expect:
            assert prepared.cohort_index == expect["cohort_index"]
        for name, label in expect.get("metrics", {}).items():
            assert bucket_label(METRIC_BY_ID[name], prepared.buckets[metric_index(name)]) == label


def test_summary_coin_is_drawn_before_contents_and_not_from_secrets(monkeypatch):
    events = []

    def random_below(limit):
        events.append(("draw", limit))
        return 0

    def describe(cell):
        events.append("cell")
        return catalog.describe(cell)

    def refuse_secrets(_limit):
        raise AssertionError("secrets")

    monkeypatch.setattr("mnemion.product_telemetry.wire_v3.describe", describe)
    monkeypatch.setattr("mnemion.product_telemetry.wire_v3.secrets.randbelow", refuse_secrets)
    prepare([(0, 1)], groups=GROUPS, release=RELEASE, operating_system="linux", random_below=random_below)
    assert events[0] == ("draw", 2) and "cell" in events
    events.clear()
    with pytest.raises(WireV3Error):
        prepare([(0, 1)], groups=[], release=RELEASE, operating_system="linux", random_below=random_below)
    assert events == [("draw", 2)]


def test_report_metadata_rejects_free_form_labels():
    sealed = validate(AggregateWindow(2900).seal(stop))
    for field in ("report_unit", "weighting"):
        broken = json.loads(json.dumps(sealed))
        broken[field] = "unexpected_free_form_label"
        with pytest.raises(WireV3Error):
            validate(broken)


def test_publication_failures_stay_inside_eight_closed_windows(tmp_path):
    clock = {"now": stamp(2900)}
    store = ReportStore(tmp_path, clock=lambda: clock["now"])
    for week in range(2900, 2909):
        with pytest.raises(WireV3Error):
            store.record_publication_failure(week)
    assert store.publication_failures() == []
    assert store.reports() == []
    calls = {"n": 0}

    def random_below(limit: int) -> int:
        calls["n"] += 1
        return limit - 1

    app = CollectorV3(store, clock=lambda: clock["now"], random_below=random_below)
    for week in range(2900, 2912):
        clock["now"] = stamp(week + 1)
        app._record_failure(week)
    retained = list(range(2904, 2912))
    assert [item["window_week"] for item in app.publication_failures] == retained
    assert [item["window_week"] for item in store.publication_failures()] == retained
    app._record_failure(2911)
    store.record_publication_failure(2911)
    assert [item["window_week"] for item in store.publication_failures()] == retained
    assert len(app.publication_failures) == 8
    clock["now"] = stamp(2912)
    app._record_failure(2912)
    assert [item["window_week"] for item in app.publication_failures] == retained
    clock["now"] = stamp(2920)
    assert app.publication_failures == []
    assert store.publication_failures() == []
    assert store.reports() == []
    assert calls["n"] == 0
    raw = (tmp_path / "reports-v3.sqlite3").read_bytes()
    assert b"4.46.53" not in raw
    assert b"packet" not in raw
