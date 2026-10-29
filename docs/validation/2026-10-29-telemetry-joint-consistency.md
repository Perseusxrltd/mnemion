# Telemetry joint-category consistency — 29 October 2026

**Scoped source qualification passed** at
`5c293fdca584492d4ac84d6cd0d6d4bcf0d25048`. The correction prevents individually
plausible category intervals from describing an impossible total probability.
Production collection remains unavailable; full V08 acceptance is open.

## Failure and correction

The original selection recorded **three genuine assertion failures**: two
syntactically valid packet streams produced views marked `estimated` when their
intervals were jointly impossible, and the publisher accepted an impossible
visible interval set. The original failed receipts are retained.

[Reporting](../../mnemion/product_telemetry/reporting.py) now checks every
unrounded category interval, including the unobserved category and cells that
will be withheld. For bounds within `[0, 1]`, a compatible distribution requires
`sum(lower bounds) <= 1 <= sum(upper bounds)`. If that fails, the view becomes
`inconsistent_reports` with `estimates: null`. The existing count bucket remains,
and sealing still wipes the accumulators. Point estimates are not renormalized.

The [publisher validator](../../mnemion/product_telemetry/publication.py) applies
the same compatibility check to visible intervals. A withheld cell contributes
only an unknown `[0, 1]` range to validation; its value and interval remain null.
The validator neither reconstructs complementary values nor rewrites reports.
For example, sixteen intervals of `[0.4, 0.6]` have lower bounds totaling 6.4;
sixteen `[0.01, 0.04]` intervals have upper bounds totaling 0.64. Both are refused.

## Verified scope and limits

The retained final selection completed at **03:09:53 UTC** with **75 passed,
zero failed, zero errors and zero skips**. Ruff check and format also passed.

| Selected tests | Passed |
| --- | ---: |
| Joint-category consistency | 5 |
| Wire and distribution | 38 |
| Publication and historical reports | 24 |
| Privacy attacks | 8 |

`tests/test_product_telemetry_joint_consistency.py` covers both impossible packet
streams, excessive lower bounds, insufficient upper bounds and compatible
visible intervals with withheld cells left unknown. Existing tests retain valid
historical schemas, immutable closed reports and wiping behavior.

Three additional [historical feature-report cases](../../tests/test_product_telemetry_catalog_compatibility.py)
passed on the prepared 4.46.50 source. They verify that stored schema 1, 2 and 3
feature reports remain byte-preserved alongside schema 4's expanded category
set. This brings the distinct selected checks to **78**, without repeating the
75 passing checks above.

The conditional automatic `ln(3)` bound, report schema 4, wire parameters,
thresholds and count buckets are unchanged. This is not sender authentication
or general poisoning resistance: biased but feasible contributions can still
pass. Representative-population utility, privacy/provider, resource, wire and
installed-platform acceptance remain open. All **66 requirement states** are
unchanged; **V08 remains Building**, collection/destination/route are
**false/null/null**, and release certificate authorities remain empty.

## Retained receipts

The following receipt names and SHA-256 values identify the original and final
private receipts without publishing operational paths or credentials.

| Receipt | SHA-256 |
| --- | --- |
| `original-plan.json` | `b05914e23da1306e74968d68c4584167289fb9c37241826e8e4cd8dd990b782f` |
| `original/original-joint-telemetry-consistency.json` | `bca085959d0b50c45a0e4b375ae0c60d749a58cd557c42781a681d3fabbc3607` |
| `original/tests.xml` | `220dfec5104ea4befc95203f9a6679e4e96e8310e63b6df4c617af521dcd5dcc` |
| `check-plan.json` | `3c36d92e5859c65e0910913e368bec7a9016d07f186df906a9fad8f0bd9af0f9` |
| `checks/joint-telemetry-consistency.json` | `63a43edd11d36d4c9f5feb84485f77d044f8204ba7f606beffc90b8475bb834e` |
| `checks/tests.xml` | `e57d38018e6ac57d1bd19fa90725a608b79c5429023d505206fe484cc805805d` |
| `checks/ruff-check.log` | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `checks/ruff-format.log` | `eee76f865de5a9f2456950f710ae5d5f9b5bd0ea02aa54f614c5eed6642a0bfd` |
| `compatibility-plan.json` | `9e4ada545e03440f8aa8c7da9b700cca240fc45838ad6699ee68b9dfae8a6402` |
| `compatibility-checks/joint-telemetry-historical-compatibility.json` | `2b47fc5fc3ea2a285ee0b556868e41bbb524e06e2d79ddf4169da04fc5b1e818` |
| `compatibility-checks/tests.xml` | `3055abcfbc0d56221f53d48d3474886be391316ba2d9f58d84f0790a4ff7d036` |
