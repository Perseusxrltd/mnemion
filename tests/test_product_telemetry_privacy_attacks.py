"""Known-background inference, linked reports and immutable-publication attacks."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from fractions import Fraction
import sqlite3
from threading import Barrier

import pytest
from starlette.testclient import TestClient

from deploy.assess_telemetry_privacy import assess, _balanced
from mnemion.product_telemetry import wire
from mnemion.product_telemetry.collector import Collector
from mnemion.product_telemetry.publication import ReportStore
from mnemion.product_telemetry.reporting import AggregateWindow


@pytest.fixture(scope="module")
def assessment():
    return assess()


def test_closed_documents_bound_known_background_inference_in_every_view(assessment):
    assert assessment["scoped_checks_passed"]
    assert assessment["views"] == 23
    cases = assessment["cases"]
    assert len(cases) == 46
    assert all(case["same_output_support"] and case["same_probability_mass"] for case in cases)
    assert all(case["passed"] for case in cases)
    assert all(
        case["withheld_values_absent"] for case in cases if case["scenario"] == "rare_category"
    )
    assert not assessment["full_telemetry_acceptance"]


def test_linked_reports_do_not_inherit_a_single_report_or_lifetime_guarantee(assessment):
    linked = assessment["linked_report_inference"]
    assert [row["linked_reports"] for row in linked] == [1, 7, 56]
    assert [row["likelihood_ratio_maximum"] for row in linked[:2]] == [3, 2187]
    assert linked[0]["equal_prior_optimal_inference_success"] == 0.625
    assert (
        linked[0]["equal_prior_optimal_inference_success"]
        < linked[1]["equal_prior_optimal_inference_success"]
        < linked[2]["equal_prior_optimal_inference_success"]
    )
    posteriors = [
        Fraction(
            int(row["most_informative_output_posterior"]["numerator"]),
            int(row["most_informative_output_posterior"]["denominator"]),
        )
        for row in linked
    ]
    assert posteriors[1] > Fraction(68, 100)
    assert all(value < 1 for value in posteriors)
    assert all(row["passed"] for row in linked)


def test_participation_and_permitted_groups_are_explicit_counterexamples(assessment):
    controls = assessment["negative_controls"]
    assert controls["participation_can_change_publication"]
    assert controls["published_volume_bucket"] == {"minimum": 64, "maximum_exclusive": 128}
    assert controls["disjoint_permitted_groups_have_disjoint_view_support"]
    assert not controls["participation_guarantee"]
    assert not controls["policy_choice_guarantee"]
    assert not controls["network_or_lifetime_guarantee"]


def test_competing_publishers_cannot_expose_two_versions_of_one_week(tmp_path):
    def clock():
        return 345600 + 2901 * 604800

    first = ReportStore(tmp_path / "publisher", clock=clock)
    second = ReportStore(first.root, clock=clock)
    documents = []
    for category in (1, 2):
        window = AggregateWindow(2900)
        _balanced(window, 0, category, 4096)
        documents.append(window.seal())
    barrier = Barrier(2)

    def publish(index):
        barrier.wait(timeout=5)
        try:
            (first, second)[index](documents[index])
            return True
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        successes = list(executor.map(publish, (0, 1)))
    assert successes.count(True) == 1
    winner = documents[successes.index(True)]
    original = first.path.read_bytes()
    for store in (first, second, ReportStore(first.root, clock=clock)):
        assert store.reports() == [winner]
        attempted = deepcopy(documents[1 - successes.index(True)])
        with pytest.raises(sqlite3.IntegrityError):
            store(attempted)
        assert store.reports() == [winner]
    assert first.path.read_bytes() == original


@pytest.mark.parametrize(
    "route",
    ["/v1/report?view=platform", "/v1/report?without=one", "/v1/reports", "/v1/report/2900"],
)
def test_aggregate_difference_queries_cannot_select_or_release_a_second_view(route):
    publications = []
    app = Collector(publications.append, clock=lambda: 345600 + 2900 * 604800)
    packet = wire.encode(0, 0, reviewed=True)
    with TestClient(app) as client:
        response = client.post(route, content=packet)
        assert response.status_code == 404
        assert response.content == b""
        assert client.get("/v1/report").status_code == 404
        assert app._window._total == 0
        assert publications == []
