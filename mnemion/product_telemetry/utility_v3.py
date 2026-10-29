"""Modelled precision of one closed week. These are not guaranteed observations.

Each report chooses release or coarse OS with equal probability, independently
of its measurements. A modelled installation that shares one release and one
OS therefore puts about half of its ticks on each axis. The binomial spread of
that split is part of the model. Whole-population counts are not.
"""

from __future__ import annotations

from fractions import Fraction
from math import exp, lgamma, log, sqrt

from .aggregate_v3 import DENOMINATOR, HALFWIDTH, NUMERATOR, THRESHOLD


def _stddev() -> float:
    decay = Fraction(NUMERATOR, DENOMINATOR)
    variance = 2 * decay / (1 - decay) ** 2
    return float(variance) ** 0.5


def _axis_frequency(trials: int, lowest: int) -> float:
    """Model frequency of Bin(trials, 1/2) >= lowest. Not a confidence claim."""
    if lowest <= 0:
        return 1.0
    if lowest > trials:
        return 0.0
    log_half = trials * log(0.5)
    total = 0.0
    for count in range(lowest, trials + 1):
        total += exp(lgamma(trials + 1) - lgamma(count + 1) - lgamma(trials - count + 1) + log_half)
    if total < 1e-6:
        return 0.0
    if total > 1 - 1e-6:
        return 1.0
    return round(min(1.0, total), 6)


def modelled_utility() -> dict:
    deviation = _stddev()
    publish_bar = THRESHOLD + HALFWIDTH
    share_bar = 2 * HALFWIDTH
    rows = []
    for installations in (10, 100, 1000):
        for rate in (2, 7):
            ticks = installations * rate
            expected = ticks / 2
            sampling = sqrt(ticks) / 2
            low = expected - 2 * sampling
            published = low >= publish_bar
            rows.append(
                {
                    "installations": installations,
                    "reports_per_installation": rate,
                    "modelled_report_ticks": ticks,
                    "expected_axis_ticks": expected,
                    "axis_sampling_stddev": sampling,
                    "conservative_axis_ticks": low,
                    "model_frequency_axis_clears_publish_bar": _axis_frequency(ticks, publish_bar),
                    "distinct_people": "not_identified",
                    "expected_counts_are_not_guaranteed": True,
                    "denominator_usually_published": published,
                    "coarse_majority_bucket_usable": published and low / 2 >= share_bar,
                    "uniform_eight_bucket_usable": published and low / 8 >= share_bar,
                }
            )
    return {
        "mechanism_stddev": deviation,
        "mechanism_halfwidth_95": HALFWIDTH,
        "suppression_threshold": THRESHOLD,
        "share_bar": share_bar,
        "publish_bar": publish_bar,
        "assumption": "one_shared_release_and_one_coarse_os_split_independently_across_both_axes",
        "axis_split": "each_report_chooses_release_or_os_with_probability_one_half",
        "sampling_screen": "mean_minus_two_binomial_standard_deviations_must_clear_the_bar",
        "rows": rows,
        "reading": {
            "10": "Even the full tick count stays inside the noise. The axis split does not produce a usable comparison.",
            "100": "Half of 200 ticks stays under the publish bar after sampling spread. The model frequency of clearing that bar is 0.004361, which is not the screen and not a guarantee. Half of 700 clears a cohort total and a coarse majority bucket. An even 8-bucket split does not.",
            "1000": "The lower side of the axis split still clears a cohort total, a coarse majority bucket, and an even 8-bucket split in this model.",
        },
        "limitations": [
            "Modelled products are not a promise that a future week will land on these counts.",
            "The axis coin is sampling uncertainty. It is not an independent-user confidence interval.",
            "Noise is the publication mechanism. A coordinate half-width is not a percentile confidence interval.",
            "A sum of cohort histograms is noisier than one coordinate. This table describes one cohort, not that sum.",
            "Seven reports require seven locally spaced attempts. Two is a sparse model, not a measured rate.",
            "A clipped normalized tick is not an uncapped event count, and a tick is not a person.",
            "Release and OS cohorts stay separate marginals in the same week and must not be joined.",
        ],
    }
