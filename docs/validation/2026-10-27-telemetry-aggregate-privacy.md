# Telemetry aggregate privacy assessment — 27 October 2026

This offline assessment, prepared on source
`7c49f4865376d8975dcdeeab98168b51618a5f5c`, provides scoped evidence for
conditional category protection and explicit counterexamples outside that scope.
It changes no product runtime, threshold, wire/resource setting or production
endpoint and makes no network or model calls.

The [reusable assessment](../../deploy/assess_telemetry_privacy.py),
[attack tests](../../tests/test_product_telemetry_privacy_attacks.py) and
[machine-readable result](2026-10-27-telemetry-aggregate-privacy.json) retain the
method, source-input hashes and outcomes. Final assessment SHA-256:
`9f0b0c4d3ed345aa3625696836fd3afec338e739579f570b181e11a1b75c1059`.

## Conditional category replacement

All **46 exact scenarios across 23 views** passed: one rare-category and one
known coincident-cohort background per view. The adversary knows every other
background packet and the target's view. Only one automatic report's category
changes; permission, view and packet-independent inclusion remain fixed.
The cohort fixtures use known platform/architecture/release observations,
without introducing a participant join.

The assessment enumerates every equiprobable encoder draw and groups complete
released documents by their canonical JSON text. Both hypotheses have equal
total probability mass and the same output support; maximum output likelihood
ratios are 1 or 3. All 23 rare-category cases withhold the selected rare values
and their numeric intervals. Sealing clears the real accumulator and prevents a
second release.

The conditional proof is postprocessing: each possible packet has likelihood
ratio at most **3** under the two category hypotheses. Summing probabilities
for packets that produce the same closed aggregate document cannot increase
that bound, even with the background known. These fixtures exercise two fixed
backgrounds per view; they are not real-population sampling trials or proof of
participation, permission-choice or lifetime anonymity.

## Linked reports and unprotected controls

For two alternative categories in one fixed view, with equal prior odds and
independent conforming randomization, the model assumes the adversary can link
all reports from the same hypothesis:

| Linked reports | Maximum likelihood ratio | Optimal equal-prior inference success |
| ---: | ---: | ---: |
| 1 | 3 | 62.5% |
| 7 | 2,187 | 83.276176% |
| 56 | 3^56 | 99.727859% |

These are conditional adversary-model figures. They do not estimate how often
reports can be linked, deployment identity rates or typical inference success.
For a rare prior of **1/1,000**, the most informative seven-report sequence
gives posterior **81/118**, approximately **68.64%**. At 56 reports the exact
posterior is
`19383245667680019896796723 / 19383245667680019896796760`, still strictly below
one. This is the posterior for the most informative output, not the probability
of receiving that output or an average posterior.

Two negative controls explicitly demonstrate missing guarantees:

- With all other reports known, adding the 64th report changes a suppressed
  window into publication with volume bucket `[64, 128)`. Category replacement
  protection does not protect report participation at this threshold.
- Disjoint permitted `usage` and `reliability` groups have disjoint view
  support. The category bound does not protect that permission choice.

## Publication guards and retained validation

Two real `ReportStore`/SQLite connections in two threads concurrently attempted
different documents for one closed week. Exactly one won; duplicate attempts
were rejected, reopening returned the winner and the stored bytes stayed
unchanged. This is local component evidence, not competing installed OS
processes. In-process collector HTTP tests rejected all four alternate query
routes, including `?view=platform`, `?without=one` and per-week/plural routes,
with empty 404 responses and no contribution or publication. GET of the report
endpoint was also rejected. Actual deployed ingress remains unqualified.

The original selection passed **70 tests in 3.37 seconds**: 62 existing
wire/publication tests and eight new attack tests. The diagnostic originally
rounded the 56-report posterior to `1.0`; its original passing checks, assessment
and source remain retained in the private `before-exact-fractions` evidence.
The follow-up groups canonical JSON directly and emits posterior numerators
and denominators as exact decimal strings. Its **eight affected tests passed
in 2.42 seconds**, and the final assessment exited successfully. Nine existing
product-runtime input hashes matched, so the other 62 results remain applicable:
**70 distinct qualified tests**. This correction changes diagnostic/test output;
it identifies no production runtime defect or fix.

## Remaining acceptance

The [aggregate utility evidence](2026-10-27-telemetry-aggregate-utility.md) and
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) remain binding.
Complete aggregate privacy/utility acceptance is still open, including
participant/lifetime protection, real-population utility and actual ingress or
provider behavior. Full runtime/platform, installed and resource qualification
also remain unfinished. The **2 MiB / 0.5%** ceilings and all failed resource
evidence are unchanged; no new resource run is selected.

All 66 requirements and their states remain unchanged. V08 is **Building**;
production collection/destination/route remain **false/null/null**, with release
certificate authorities empty. No universal anonymity or full acceptance is
claimed.
