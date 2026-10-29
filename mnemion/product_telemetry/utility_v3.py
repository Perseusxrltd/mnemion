"""Modelled precision of one closed week. These are not guaranteed observations.

The figures assume every participating installation contributes the stated
number of report ticks, on the week's single cohort axis, and that those ticks
land in one listed release or one coarse OS. A random noise draw can miss the
model. Report ticks are not people.
"""

from __future__ import annotations

from fractions import Fraction

from .aggregate_v3 import DENOMINATOR, HALFWIDTH, NUMERATOR, THRESHOLD


def _stddev() -> float:
    decay = Fraction(NUMERATOR, DENOMINATOR)
    variance = 2 * decay / (1 - decay) ** 2
    return float(variance) ** 0.5


def modelled_utility() -> dict:
    deviation = _stddev()
    publish_bar = THRESHOLD + HALFWIDTH
    share_bar = 2 * HALFWIDTH
    rows = []
    for installations in (10, 100, 1000):
        for rate in (2, 7):
            ticks = installations * rate
            majority = ticks / 2
            uniform = ticks / 8
            published = ticks >= publish_bar
            rows.append(
                {
                    "installations": installations,
                    "reports_per_installation": rate,
                    "modelled_report_ticks": ticks,
                    "distinct_people": "not_identified",
                    "expected_counts_are_not_guaranteed": True,
                    "denominator_usually_published": published,
                    "coarse_majority_bucket_usable": published and majority >= share_bar,
                    "uniform_eight_bucket_usable": published and uniform >= share_bar,
                }
            )
    return {
        "mechanism_stddev": deviation,
        "mechanism_halfwidth_95": HALFWIDTH,
        "suppression_threshold": THRESHOLD,
        "share_bar": share_bar,
        "assumption": "one_shared_listed_release_or_one_coarse_os_in_a_single_parity_week",
        "rows": rows,
        "reading": {
            "10": "Report ticks stay inside or near the noise and the suppression bar. No histogram comparison is usable.",
            "100": "A single cohort denominator can clear the noise. A coarse majority bucket is usable only toward the 7-report model. An even 8-bucket split is not.",
            "1000": "Coarse and evenly split buckets are both above the mechanism half-width in this model.",
        },
        "limitations": [
            "Modelled products are not a promise that a future week will land on these counts.",
            "Noise is the publication mechanism. It is not an independent-user confidence interval.",
            "Seven reports require seven locally spaced attempts. Two is a sparse model, not a measured rate.",
            "Clients that miss the public week axis are dropped and are not in these totals.",
            "A clipped normalized tick is not an uncapped event count, and a tick is not a person.",
            "Release weeks and OS weeks are different partitions and must not be joined.",
        ],
    }
