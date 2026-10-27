# Fixed telemetry catalog lookups — 27 October 2026

This source follow-up is prepared on
`e57f84df51cb7db5746857162a88167dff46d1d4`. The
[catalog](../../studio/electron/telemetry-catalog.ts) now builds lookup arrays
for workflow families, allowed fields and resources once from release metadata, and
uses an indexed bucket search. It caches no privacy permission, generation,
queue contents or observation values. Packet/policy formats and fresh authority
checks remain unchanged.

## Original finding and fixed fixture

The first fixture stopped because Node's `MockTracker` rejects
`Array.prototype` as a mock target. That setup failure established no product
regression. Its receipt remains separate from the subsequent genuine
recurring-work failure, after a bounded wrapper with test cleanup corrected the
fixture setup.

The [catalog regression](../../studio/frontend/scripts/test-product-telemetry.mjs)
performs **128 iterations** of observation encoding, group lookup and full
description. Counters reset after catalog construction, so these are recurring
operations rather than total initialization work:

| Recurring operation | Original | Corrected |
| --- | ---: | ---: |
| Metric definition enumeration | 128 | 0 |
| Resource definition enumeration | 384 | 0 |
| Workflow family splitting | 640 | 0 |
| Bucket searches using `findIndex` callbacks | 384 | 0 |

The original fixture error, failing original counts and corrected counts remain
retained separately. These counters do not measure allocated bytes, RSS or CPU;
zero here does not mean the catalog performs no allocations.

## Qualified source checks

Actual **Electron 44.9.3 / Node 24.22.0 on Linux x64** passed **47 native checks**,
with **two Windows file/directory-permission skips** and no failures. The
browser-source selection on Node 22.22.0 passed **30 checks**, with no skips.
Independent Python parity passed for all **65,536 numeric cells**, **six invalid
cell inputs** and **981 observation/bucket cases**. SDK, Electron and frontend
builds passed; **771 checked inputs** are retained with the qualification.

The source-qualification receipt has SHA-256
`8bc330144346e1aaf6bd915e777f93c7bb0e967be4fa618869d9aa9037e855d1`.
Source/component checks establish neither installed-platform acceptance nor an
RSS/CPU saving. The [earlier resource overages](2026-10-27-telemetry-resource-roles.md)
and [original failed control diagnostic](2026-10-27-telemetry-probe-controls.md)
remain retained.

The declared [six-case comparison without allocation attribution](2026-10-27-telemetry-catalog-comparison.md),
original run **40477197149** on `bc4d6e0892af35e5952f14a4d18e35924c2a0157`,
completed with **failure**. All six cases completed their memory work, but the
second enabled case recorded 65 telemetry writes without reserving or sending
a report. Five journeys completed; the summary step was skipped and qualification
stopped on the missing summary. The delivery cause remains unestablished. No
RSS/CPU saving or resource acceptance is inferred, and no app rerun is used here.

The [canonical contract](../implementation/anonymous-product-telemetry.md#required-acceptance-evidence)
and [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) retain the full
resource, runtime/platform, installed, wire, provider/privacy and aggregate
requirements. The **2 MiB added RSS / 0.5% of one core** ceilings remain unchanged.
All 66 requirement states are retained; V08 remains **Building**, production
collection/destination/route are **false/null/null**, and release CAs are empty.
