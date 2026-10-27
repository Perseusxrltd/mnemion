"""Observable packet distributions, utility boundaries and closed-window privacy."""

from collections import Counter
from itertools import product
import json
import math

import pytest
from starlette.testclient import TestClient

from mnemion.product_telemetry import catalog, wire
from mnemion.product_telemetry.collector import Collector
from mnemion.product_telemetry.reporting import AggregateWindow, reporting_week


def draws(*values):
    iterator = iter(values)
    return lambda _limit: next(iterator)


def test_every_public_view_has_exact_full_support_and_likelihood_ratio_at_most_three():
    for view in wire.VIEWS:
        distributions = []
        for value in range(len(view["values"])):
            outcomes = Counter(
                wire.encode(view["id"], value, random_below=draws(column, coin))
                for column, coin in product(range(view["domain"]), range(4))
            )
            assert len(outcomes) == view["domain"] * 2
            assert set(outcomes.values()) == {1, 3}
            assert all(len(packet) == 4 for packet in outcomes)
            distributions.append(outcomes)
        support = set(distributions[0])
        assert all(set(item) == support for item in distributions)
        for packet in support:
            probabilities = [item[packet] for item in distributions]
            assert max(probabilities) <= 3 * min(probabilities)


def test_hadamard_reports_have_the_expected_mean_independently_of_the_decoder():
    selected = wire.VIEWS[0]
    for category in (0, 3, len(selected["values"]) - 1):
        packets = [
            wire.encode(0, category, random_below=draws(column, coin))
            for column, coin in product(range(selected["domain"]), range(4))
        ]
        for candidate in range(selected["domain"]):
            # Compute the mathematical parity directly, not the reporting
            # transform. Enumerating the four coins is an exact expectation.
            score = sum(
                (1 if packet[3] else -1)
                * (-1 if sum(int(bit) for bit in bin(candidate & packet[2])[2:]) % 2 else 1)
                for packet in packets
            )
            assert score * 2 == (len(packets) if candidate == category else 0)


def test_wire_view_inventory_covers_all_metrics_without_exporting_joint_profiles():
    assert len(wire.VIEWS) == 23
    assert sum(item["weight"] for item in wire.VIEWS) == 256
    assert wire.VIEWS[1]["values"][1:] == list(catalog.WORKFLOWS)
    assert wire.VIEWS[0]["values"][1:] == list(catalog.CATALOG["workflows"])
    metrics = {item["source"].get("metric") for item in wire.VIEWS}
    assert metrics >= set(catalog.METRICS) | set(catalog.RESOURCE_METRICS)
    assert set(wire.COHORTS) == {"platform", "architecture", "release_family"}
    for item in wire.VIEWS:
        assert item["id"] == wire.VIEWS.index(item)
        assert len(item["values"]) == len(set(item["values"]))
        assert item["domain"] == 2 ** math.ceil(math.log2(len(item["values"])))
        assert set(item["source"]) in ({"metric", "field"}, {"cohort"})


def test_sampling_is_count_weighted_and_independent_of_values_and_policy_is_restrictive():
    recall = catalog.observation(
        {"kind": "submission", "workflow": "memory.recall", "surface": "desktop"}
    )[1][0]
    backup = catalog.observation(
        {"kind": "submission", "workflow": "backup.create", "surface": "desktop"}
    )[1][0]
    rows = [(recall, 3), (backup, 1)]
    # Query draw zero always selects family; sample draw 0..2 selects memory,
    # and draw 3 selects backup. No returned report contains the selected row.
    for selected in range(4):
        expected = "memory" if selected < 3 else "backup"
        actual = wire.prepare(rows, groups=["usage"], random_below=draws(0, selected, 7, 0))
        assert actual == wire.encode(
            0, wire.VIEWS[0]["values"].index(expected), random_below=draws(7, 0)
        )
    for index in range(sum(item["weight"] for item in wire.VIEWS if item["group"] == "resources")):
        packet = wire.prepare(rows, groups=["resources"], random_below=draws(index, 0, 0))
        assert wire.view(wire.decode(packet)[0])["group"] == "resources"


def test_unknown_sensor_and_cohort_are_not_a_zero_sensor_or_joined_fingerprint():
    row = catalog.observation({"kind": "resource", "metric": "rss_bytes", "value": 0})[1][0]
    # The first resources view is queue_items, absent here; no fabricated zero.
    packet = wire.prepare([(row, 1)], groups=["resources"], random_below=draws(0, 2, 0))
    identifier = wire.decode(packet)[0]
    assert wire.view(identifier)["name"] == "queue_items"
    assert packet == wire.encode(identifier, 0, random_below=draws(2, 0))
    with pytest.raises(wire.WireError, match="^telemetry_invalid_report$"):
        wire.prepare([(row, 1)], groups=["resources"], cohorts={"platform": "PRIVATE_HOST"})
    with pytest.raises(wire.WireError):
        wire.prepare([(row, 1)], groups=["resources"], cohorts={"machine_id": "PRIVATE_ID"})


@pytest.mark.parametrize(
    "packet",
    [
        b"",
        b"PRIVATE_SENTINEL",
        b'{"key":"PRIVATE_TOKEN"}',
        bytes((2, 255, 0, 1)),
        bytes((2, 0, 16, 1)),
        bytes((2, 0, 0, 4)),
        bytes((1, 0, 0, 1)),  # Earlier packets cannot prove automatic inclusion.
        [2, 0, 0, 1],
    ],
)
def test_invalid_frames_cannot_become_private_free_text_or_extra_fields(packet):
    with pytest.raises(wire.WireError, match="^telemetry_invalid_report$"):
        wire.decode(packet)


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [(0, 0)],
        [(0, True)],
        [(0, 256)],
        [(0, 1), (0, 1)],
        [(65535, 1)],
        [{"private": "text"}],
        [(0, 1)] * 513,
    ],
)
def test_invalid_source_cells_are_rejected_without_an_outbound_fallback(rows):
    with pytest.raises(wire.WireError, match="^telemetry_invalid_report$"):
        wire.prepare(rows, groups=["usage"])


def fill(window, *, view=0, category=3, repeats=64, reviewed=False):
    for _ in range(repeats):
        for column, coin in product(range(wire.view(view)["domain"]), range(4)):
            assert window.contribute(
                wire.encode(view, category, reviewed=reviewed, random_below=draws(column, coin))
            )


def test_collector_stores_only_small_numeric_arrays_and_releases_once_then_erases():
    window = AggregateWindow(2900)
    assert window.storage_bytes < 4096
    fill(window)
    # The exact count differs from either public power-of-two boundary.
    for _ in range(8):
        assert window.contribute(wire.encode(0, 3))
    result = window.seal()
    assert result["report_unit"] == "unverified_anonymous_report_not_a_user_or_device"
    measured = result["views"][0]
    assert measured["report_range"] == {"minimum": 4096, "maximum_exclusive": 8192}
    estimate = measured["estimates"][3]
    assert (
        estimate["state"] == "estimated" and estimate["interval"][0] <= 1 <= estimate["interval"][1]
    )
    assert all(
        item["fraction"] is None for index, item in enumerate(measured["estimates"]) if index != 3
    )
    assert all(item["state"] == "insufficient_reports" for item in result["views"][1:])
    assert "4104" not in json.dumps(result)
    assert window.seal() is None
    assert not window.contribute(wire.encode(0, 0))
    assert window._total == 0 and not any(window._counts)
    assert not any(value for sums in window._sums for value in sums)


def test_small_windows_and_saturation_do_not_publish_residuals_or_grow_storage(monkeypatch):
    window = AggregateWindow(2900)
    before = window.storage_bytes
    monkeypatch.setitem(wire.WIRE["reporting"], "maximum_reports_per_window", 2)
    assert window.contribute(wire.encode(0, 0))
    assert window.contribute(wire.encode(0, 0))
    assert not window.contribute(wire.encode(0, 0))
    assert window.storage_bytes == before
    assert window.seal() is None
    assert not any(window._counts)


def test_packet_selection_cannot_turn_reviewed_reports_into_false_usage_estimates():
    def distribution(category):
        return Counter(
            wire.encode(0, category, random_below=draws(column, coin))
            for column, coin in product(range(wire.VIEWS[0]["domain"]), range(4))
        )

    original, selected = distribution(1), distribution(2)
    repeat = 65
    offered = {packet: count * 3 * repeat for packet, count in original.items()}
    accepted = {packet: count * repeat for packet, count in selected.items()}
    # Every retained packet could come from setup, but the chosen subset has
    # exactly the randomized distribution of workspace. No sampler can infer
    # the original usage distribution from these received packets alone.
    assert sum(offered.values()) == 12480 and sum(accepted.values()) == 4160
    assert all(accepted[packet] <= count for packet, count in offered.items())
    window = AggregateWindow(2900)
    before = window.storage_bytes
    canonical = bytes((2, 0, 0, 2))
    # These categorical packets cannot be relabeled as reviewed. The accepted
    # manual body has no varying coordinate/sign in which selection can encode
    # a categorical value; the original randomized subset is not sent.
    for packet in accepted:
        marked = bytes((*packet[:3], packet[3] | 2))
        if marked != canonical:
            assert not window.contribute(marked)
    for _ in range(sum(accepted.values())):
        assert window.contribute(canonical)
    assert not any(window._counts) and not any(value for sums in window._sums for value in sums)
    result = window.seal()
    assert result["report_range"] == {"minimum": 4096, "maximum_exclusive": 8192}
    assert all(
        item["state"] == "insufficient_reports"
        and item["report_range"] is None
        and item["estimates"] is None
        for item in result["views"]
    )
    assert result["reviewed_report_use"] == "coarse_global_volume_only"
    assert result["estimation_population"] == "automatic_reports_only"
    assert "reviewed_report_range" not in result
    assert window.storage_bytes == before


def test_reviewed_reports_cannot_inflate_automatic_thresholds_or_precision():
    reference, mixed, insufficient = (AggregateWindow(2900) for _ in range(3))
    fill(reference, category=1)
    fill(mixed, category=1)
    fill(mixed, category=2, repeats=65, reviewed=True)
    fill(insufficient, category=1, repeats=63)
    fill(insufficient, category=2, repeats=65, reviewed=True)
    assert reference.seal()["views"] == mixed.seal()["views"]
    assert all(item["state"] == "insufficient_reports" for item in insufficient.seal()["views"])


def test_review_preview_limits_its_privacy_claim_and_legacy_wire_is_not_assumed_automatic():
    automatic = wire.preview(wire.encode(0, 1, random_below=draws(7, 0)))
    reviewed = wire.preview(wire.encode(0, 1, reviewed=True, random_below=draws(7, 0)))
    assert automatic["per_report_privacy_loss"] == "ln(3)"
    assert reviewed["per_report_privacy_loss"] is None
    assert reviewed["randomization_privacy_loss"] is None
    assert reviewed["randomized_sign"] is None
    assert reviewed["privacy_bound_scope"] == "fixed_body_for_permitted_groups"
    assert reviewed["report_selection"] == "reviewed"
    assert reviewed["body_bytes"] == automatic["body_bytes"] == 4
    window = AggregateWindow(2900)
    assert not window.contribute(bytes((1, 0, 7, 0)))
    assert window._total == 0
    with pytest.raises(wire.WireError):
        wire.encode(0, 1, reviewed="PRIVATE_VALUE")


def test_manual_body_is_constant_for_all_values_and_preparation_never_draws_entropy():
    def no_entropy(_):
        pytest.fail("A volume-only report must not sample a category, view or sign")

    for view in wire.VIEWS:
        packets = {
            wire.encode(view["id"], category, reviewed=True, random_below=no_entropy)
            for category in range(len(view["values"]))
        }
        assert packets == {bytes((2, view["id"], 0, 2))}
    first = catalog.observation(
        {"kind": "submission", "workflow": "memory.recall", "surface": "desktop"}
    )[1][0]
    second = catalog.observation(
        {"kind": "submission", "workflow": "backup.create", "surface": "desktop"}
    )[1][0]
    for groups in (["usage", "resources"], ["performance"], ["resources", "reliability"]):
        expected = next(view["id"] for view in wire.VIEWS if view["group"] in groups)
        for rows in ([(first, 1)], [(second, 255)]):
            assert wire.prepare(
                rows, groups=groups, reviewed=True, random_below=no_entropy
            ) == bytes((2, expected, 0, 2))


@pytest.mark.parametrize("count", [0, 63, 64, 127, 128, 700, 4095])
def test_closed_volume_is_coarse_and_does_not_release_small_view_counts(count):
    window = AggregateWindow(2900)
    before = window.storage_bytes
    for index in range(count):
        identifier = index % len(wire.VIEWS)
        assert window.contribute(wire.encode(identifier, 0))
    assert not window.contribute(b"PRIVATE_INVALID_PACKET")
    assert window.storage_bytes == before
    result = window.seal()
    if count < 64:
        assert result is None
    else:
        assert result["schema_version"] == 4
        assert result["report_range"] == {
            "minimum": 1 << (count.bit_length() - 1),
            "maximum_exclusive": 1 << count.bit_length(),
        }
        assert all(
            item["state"] == "insufficient_reports"
            and item["report_range"] is None
            and item["estimates"] is None
            for item in result["views"]
        )
        assert result["participation_or_lifetime_guarantee"] is False
        assert "PRIVATE" not in json.dumps(result)
        assert "count" not in result and "users" not in result and "devices" not in result
    assert window.seal() is None
    assert not window._total and not any(window._counts)
    assert not any(value for sums in window._sums for value in sums)


def test_collector_publishes_volume_once_at_boundary_without_a_live_or_filter_route():
    published = []
    current = [345600 + 2900 * 604800]
    app = Collector(published.append, clock=lambda: current[0])
    with TestClient(app) as client:
        for _ in range(65):
            assert client.post("/v1/report", content=wire.encode(0, 3)).status_code == 204
        assert client.post("/v1/report", content=b"PRIVATE_INVALID_PACKET").status_code == 400
        assert not published
        assert client.get("/stats").status_code == 404
        assert client.get("/v1/report?view=feature").status_code == 404
        current[0] += 604800
        assert app._advance()
        assert len(published) == 1
        assert published[0]["report_range"] == {"minimum": 64, "maximum_exclusive": 128}
        assert all(item["estimates"] is None for item in published[0]["views"])
        assert app._advance() and len(published) == 1
    assert not app._window._total


def test_asgi_drops_headers_metadata_malformed_bodies_and_arbitrary_queries(capsys):
    published = []
    current = [345600 + 2900 * 604800]
    app = Collector(published.append, clock=lambda: current[0])
    headers = {
        "Authorization": "Bearer PRIVATE_SENTINEL",
        "Cookie": "PRIVATE_COOKIE",
        "Origin": "https://PRIVATE_ORIGIN.invalid",
        "User-Agent": "PRIVATE_AGENT",
        "Referer": "https://PRIVATE_REFERRER.invalid",
        "X-Request-ID": "PRIVATE_ID",
    }
    with TestClient(app) as client:
        good = client.post("/v1/report", content=wire.encode(0, 3), headers=headers)
        assert good.status_code == 204 and good.content == b""
        assert (
            "set-cookie" not in good.headers
            and "access-control-allow-credentials" not in good.headers
        )
        assert client.post("/v1/report", content=b"PRIVATE_PAYLOAD").status_code == 400
        assert (
            client.post("/v1/report?filter=PRIVATE_ID", content=wire.encode(0, 3)).status_code
            == 404
        )
        assert client.get("/v1/report").status_code == 404
        assert client.get("/stats?filter=PRIVATE_ID").status_code == 404
        assert client.options("/v1/report", headers=headers).status_code == 204
        assert app._window._total == 1
        assert published == []
        fill(app._window)
        current[0] += 604800
        assert app._advance()
        assert len(published) == 1 and not app._window._total
        assert "PRIVATE" not in json.dumps(published)
        assert client.post("/v1/report", content=wire.encode(0, 3)).status_code == 204
        current[0] -= 604800
        assert client.post("/v1/report", content=wire.encode(0, 3)).status_code == 400
        assert not app._window._total
    assert not app._window._total
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err


def test_reporting_week_is_server_owned_and_has_no_client_timestamp_field():
    assert reporting_week(345600) == 0
    assert reporting_week(345600 + 604800 - 0.01) == 0
    assert reporting_week(345600 + 604800) == 1
    for timestamp in (-1, True, float("nan"), float("inf"), "PRIVATE_TIME"):
        with pytest.raises(wire.WireError):
            reporting_week(timestamp)


def test_local_agent_discovery_exposes_the_format_without_activating_delivery(tmp_path):
    from mnemion.product_telemetry import cli, policy

    schema = cli.execute(tmp_path / "absent", {"action": "schema"})
    assert schema["transport_catalog"] == wire.specification()
    assert schema["transport_available"] is False
    assert schema["disclosure"]["collection_available"] is False
    assert schema["disclosure"]["destination"] is None
    assert policy.preview(tmp_path / "absent")["outbound_body"] is None
    assert not list(tmp_path.iterdir())
