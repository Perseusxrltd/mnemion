# Telemetry aggregate utility — 27 October 2026

**Detailed utility at initial adoption remains unqualified.** One analysis of
source `051c9c8ac9beed7912321502ef50fbd8c2a1a4b9` evaluated configuration
arithmetic and four deterministic Linux Python fixtures. It made no network or
model calls and changed no product, privacy, threshold or resource setting.
This was not a statistical coverage trial.

The [machine-readable result](2026-10-27-telemetry-aggregate-utility.json)
retains source hashes and allocation results for all **23 views / 280 aggregate
categories**. Original result SHA-256:
`ad0145fb4005a9e70b96e78848769d4a8d87f021ec3846c3b50b0e180b43abfd`.

## Expected report volume

The [wire configuration](../../mnemion/product_telemetry/wire-v2.json) requires
**64 total reports** for a closed-week publication and **4,096 accepted automatic
reports per view** for detail. Reviewed reports contribute only to coarse global
volume. With all metric groups permitted, view weights sum to **256**. For a
view of weight `w`, reaching 4,096 reports in expectation requires
`ceil(4096 × 256 / w)` total accepted automatic reports.

| View | Weight | Total automatic reports (expectation) | Optimistic reporting stores |
| --- | ---: | ---: | ---: |
| Feature family | 40 | 26,215 | 3,745 |
| Feature | 16 | 65,536 | 9,363 |
| Latency | 32 | 32,768 | 4,682 |
| Each weight-4 view, such as result items | 4 | 262,144 | 37,450 |

The last column assumes every store uses the maximum **seven attempts per
rolling week** and every attempt succeeds. Spacing, jitter, inactivity, refusal
and opt-out make that optimistic. Stores and reports are not people or devices;
expected counts are not probability guarantees. Even **1,000
stores / 7,000 reports** yield only **1,093.75 family** and **437.5 feature**
reports in expectation, both below 4,096. All 23 views remain intact.
The resulting fractions describe automatically sampled reports. They are not
a census of operations, customers or installations.

## Precision and deterministic fixtures

The [aggregator](../../mnemion/product_telemetry/reporting.py) uses the lower
public count bucket `B` and simultaneous 95% radius
`sqrt(2 ln(2 × 280 / 0.05) / B) / 0.5`. This is approximately **13.49 percentage
points at 4,096** and **4.77 points at 32,768**, conditional on independent
conforming randomization and packet-independent inclusion.

| Automatic reports in the family view | Balanced fixture proportions | Actual aggregate result |
| --- | --- | --- |
| 1,024 | 75% / 25% | No detailed view: insufficient reports |
| 4,096 | 75% / 25% | 75% [61.5%, 88.5%] and 25% [11.5%, 38.5%] |
| 4,096 | 98.4375% / 1.5625% | Rare cell suppressed |
| 65,536 | About 99.0234% / 0.9766% | Rare cell suppressed |

Each actual codec/aggregator fixture balanced the encoding choices to remove
sampling variation; these are not independent real-sampling trials. Every
accumulator was erased after sealing.

For a **1% category mean**, the first public bucket whose radius permits a
positive lower bound at that mean is **1,048,576 view reports**. A weight-16 feature view would require
**16,777,216 total automatic reports in expectation**, above the collector's
**10,000,000-report window cap**. This is neither a detection-power guarantee
nor a claim that chance fluctuations can never publish a cell.

This identifies a sampling and precision decision for the remaining telemetry
work. At a hypothetical 512-report bucket the same confidence rule still has
a radius of **38.17 percentage points**; changing the eligibility threshold
alone would not provide precise small-sample statistics. A revised design needs
comparison against the same privacy, contribution, resource and retention
requirements. This analysis selects no parameter or architecture change.

## Conditional privacy and remaining acceptance

The automatic category-replacement bound is **ln(3) per report**, conditional on
the permitted view and report inclusion. If an observer can link `n` such
reports, composition gives a worst-case bound of **n ln(3)**, or likelihood
ratio at most **3^n**: **2,187 for seven**, approximately **5.23 × 10^26 for 56**.
These are bounds, not typical inference accuracy or identification success.
They establish no participation, lifetime, network, distinct cohort or poisoning
guarantee.

Existing immutable closed-week publication, no-filter and report-schema guards
remain unchanged. Real-population utility, aggregate attack resistance and
actual ingress/privacy qualification remain required in the
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md). Earlier failures
and **2 MiB / 0.5%** resource limits remain binding. All 66 requirements are
unchanged; V08 remains **Building**, collection/destination/route
**false/null/null**, and release CAs empty.
