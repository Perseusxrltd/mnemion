"""Offline, exact aggregate-inference checks; never a sender or deployment.

The adversary knows every background packet and the target's chosen view.
Only the target category changes. These deliberately strong side-information
fixtures test the released document, not just the packet serializer. They do
not establish participant, lifetime, network or useful-population anonymity.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from fractions import Fraction
import hashlib
from itertools import product
import json
from pathlib import Path

from mnemion.product_telemetry import catalog, wire
from mnemion.product_telemetry.publication import validate
from mnemion.product_telemetry.reporting import AggregateWindow


def _packet_law(identifier: int, category: int) -> Counter[bytes]:
    law: Counter[bytes] = Counter()
    for column, coin in product(range(wire.VIEWS[identifier]["domain"]), range(4)):
        draws = iter((column, coin))
        law[wire.encode(identifier, category, random_below=lambda _: next(draws))] += 1
    return law


def _balanced(window: AggregateWindow, identifier: int, category: int, count: int) -> None:
    """Construct a fixed valid background; this is not a random-sample trial."""
    packets = _packet_law(identifier, category)
    period = [packet for packet, mass in packets.items() for _ in range(mass)]
    for index in range(count):
        if not window.contribute(period[index % len(period)]):
            raise AssertionError("The declared background exceeded the accumulator contract")


def _image_law(
    background: AggregateWindow, identifier: int, category: int, withheld: tuple[int, ...]
) -> tuple[Counter[str], bool]:
    images: Counter[str] = Counter()
    absent_values = True
    for packet, mass in _packet_law(identifier, category).items():
        # Every counterfactual starts from the same real accumulated packets.
        # Copying the fixture changes no production accumulator or threshold.
        trial = deepcopy(background)
        if not trial.contribute(packet):
            raise AssertionError("Counterfactual report was unexpectedly refused")
        result = trial.seal()
        if result is None:
            raise AssertionError("The declared released window was suppressed entirely")
        validate(result)
        cells = result["views"][identifier]["estimates"]
        for index in withheld:
            absent_values &= cells is None or (
                cells[index]["state"] == "insufficient_precision"
                and cells[index]["fraction"] is None
                and cells[index]["interval"] is None
            )
        raw = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
        images[raw] += mass
        if trial.seal() is not None or trial._total or any(trial._counts):
            raise AssertionError("A sealed counterfactual retained or regenerated a window")
        if any(any(values) for values in trial._sums):
            raise AssertionError("A sealed counterfactual retained coordinate sums")
    return images, absent_values


def _replacement_cases() -> list[dict]:
    cases = []
    minimum = wire.WIRE["reporting"]["minimum_reports_per_view"]
    cohort_ids = [view["id"] for view in wire.VIEWS if "cohort" in view["source"]]
    for spec in wire.VIEWS:
        identifier = spec["id"]
        for scenario in ("rare_category", "known_coincident_cohorts"):
            background = AggregateWindow(2900)
            if scenario == "rare_category":
                _balanced(background, identifier, 1, minimum)
                hypotheses = (0, len(spec["values"]) - 1)
                withheld = hypotheses
            else:
                _balanced(background, identifier, 1, minimum * 3 // 4)
                _balanced(background, identifier, 2, minimum // 4)
                # Fixed platform/architecture/release observations are known
                # to the adversary. No synthetic participant join is supplied.
                for cohort in cohort_ids:
                    if cohort != identifier:
                        _balanced(background, cohort, 1, minimum)
                hypotheses, withheld = (1, 2), ()
            try:
                left, left_hidden = _image_law(background, identifier, hypotheses[0], withheld)
                right, right_hidden = _image_law(background, identifier, hypotheses[1], withheld)
            finally:
                background.discard()
            same_support = left.keys() == right.keys()
            same_mass = sum(left.values()) == sum(right.values()) == 4 * spec["domain"]
            maximum = max(
                (
                    max(Fraction(left[key], right[key]), Fraction(right[key], left[key]))
                    for key in left.keys() & right.keys()
                ),
                default=Fraction(0),
            )
            cases.append(
                {
                    "view": spec["name"],
                    "scenario": scenario,
                    "hypotheses": [spec["values"][value] for value in hypotheses],
                    "equiprobable_draws_per_hypothesis": 4 * spec["domain"],
                    "distinct_released_documents": len(left.keys() | right.keys()),
                    "same_output_support": same_support,
                    "same_probability_mass": same_mass,
                    "maximum_likelihood_ratio": {
                        "numerator": maximum.numerator,
                        "denominator": maximum.denominator,
                    },
                    "withheld_values_absent": left_hidden and right_hidden if withheld else None,
                    "passed": same_support
                    and same_mass
                    and maximum <= 3
                    and left_hidden
                    and right_hidden,
                }
            )
    return cases


def _linked_reports() -> list[dict]:
    left, right = _packet_law(0, 1), _packet_law(0, 2)
    mass = sum(left.values())
    step: Counter[int] = Counter()
    for packet, count in left.items():
        ratio = Fraction(count, right[packet])
        exponent = {Fraction(1, 3): -1, Fraction(1): 0, Fraction(3): 1}[ratio]
        step[exponent] += Fraction(count, mass)
    probability: Counter[int] = Counter({0: Fraction(1)})
    week = wire.WIRE["budget_proposal"]["maximum_attempts_per_rolling_week"]
    horizons = (1, week, week * wire.WIRE["reporting"]["retained_windows"])
    result = []
    for count in range(1, max(horizons) + 1):
        next_probability: Counter[int] = Counter()
        for before, p in probability.items():
            for added, q in step.items():
                next_probability[before + added] += p * q
        probability = next_probability
        if count not in horizons:
            continue
        opposite = {exponent: probability[-exponent] for exponent in probability}
        maximum = max(Fraction(p, opposite[exponent]) for exponent, p in probability.items())
        success = sum(max(p, opposite[exponent]) for exponent, p in probability.items()) / 2
        posterior = maximum / (999 + maximum)
        result.append(
            {
                "linked_reports": count,
                "likelihood_ratio_maximum": maximum.numerator,
                "expected_bound": 3**count,
                "equal_prior_optimal_inference_success": float(success),
                "rare_prior": {"numerator": 1, "denominator": 1000},
                # A float rounds the 56-report value to 1.0. Decimal strings
                # preserve this exact rational in Python and browser readers.
                "most_informative_output_posterior": {
                    "numerator": str(posterior.numerator),
                    "denominator": str(posterior.denominator),
                },
                "passed": sum(probability.values()) == 1 and maximum == 3**count,
            }
        )
    return result


def _unprotected_controls() -> dict:
    threshold = wire.WIRE["reporting"]["minimum_reports_per_window"]
    before, after = AggregateWindow(2900), AggregateWindow(2900)
    packet = wire.encode(0, 0, reviewed=True)
    for _ in range(threshold - 1):
        if not before.contribute(packet) or not after.contribute(packet):
            raise AssertionError("Participation fixture unexpectedly refused")
    if not after.contribute(packet):
        raise AssertionError("Participation fixture unexpectedly refused")
    no_release, release = before.seal(), after.seal()
    row = catalog.observation(
        {"kind": "submission", "workflow": "memory.recall", "surface": "desktop"}
    )[1][0]
    usage = wire.prepare([(row, 1)], groups=["usage"], random_below=lambda _: 0)
    reliability = wire.prepare([(row, 1)], groups=["reliability"], random_below=lambda _: 0)
    return {
        "participation_can_change_publication": no_release is None and release is not None,
        "published_volume_bucket": release["report_range"] if release else None,
        "disjoint_permitted_groups_have_disjoint_view_support": wire.view(usage[1])["group"]
        != wire.view(reliability[1])["group"],
        "participation_guarantee": False,
        "policy_choice_guarantee": False,
        "network_or_lifetime_guarantee": False,
    }


def assess() -> dict:
    cases, linked, controls = _replacement_cases(), _linked_reports(), _unprotected_controls()
    root = Path(__file__).resolve().parents[1]
    inputs = [
        "deploy/assess_telemetry_privacy.py",
        *[
            f"mnemion/product_telemetry/{name}"
            for name in (
                "__init__.py",
                "catalog.py",
                "catalog.json",
                "disclosure.json",
                "wire.py",
                "wire-v2.json",
                "reporting.py",
                "publication.py",
                "collector.py",
            )
        ],
    ]
    return {
        "schema_version": 1,
        "method": "exact finite counterfactual distributions, fixed known background, no Monte Carlo or private inputs",
        "protected_unit": "one automatic categorical replacement, conditional on view, permission and packet-independent inclusion",
        "source_inputs": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in inputs
        },
        "views": len(wire.VIEWS),
        "cases": cases,
        "linked_report_inference": linked,
        "negative_controls": controls,
        "scoped_checks_passed": all(case["passed"] for case in cases + linked)
        and controls["participation_can_change_publication"]
        and controls["disjoint_permitted_groups_have_disjoint_view_support"],
        "full_telemetry_acceptance": False,
        "resource_acceptance": False,
        "production_ingress_qualified": False,
        "real_population_utility_qualified": False,
        "network_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = assess()
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result["scoped_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
