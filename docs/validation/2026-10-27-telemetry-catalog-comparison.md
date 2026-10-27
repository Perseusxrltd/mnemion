# Catalog comparison: retained failed original — 27 October 2026

Original [run 40477197149](https://github.com/Perseusxrltd/mnemion/actions/runs/40477197149)
on source `bc4d6e0892af35e5952f14a4d18e35924c2a0157` completed with
**failure**. This was the declared six-case comparison following the
[catalog lookup correction](2026-10-27-telemetry-catalog-residency.md), without
allocation attribution. The original archive remains retained with SHA-256
`d9fe95df4d274420f7436014b13bf9597e8f51695d999722bc2904124e4e4eed`.

## Recorded work and incomplete delivery

The unpackaged Linux x64 app used Electron **44.9.3 / Node 24.22.0**. All six
cases completed **128 memory cycles and 387/387 successful API requests each**.
Each retained result records valid process ownership and native setup controls,
with no page errors. Five of the six journeys completed:

| Case, in original order | Accepted telemetry writes | Reserved attempts | Accepted collector reports | Journey completed |
| --- | ---: | ---: | --- | --- |
| r1-unavailable | 0 | 0 | 0 | true |
| r1-opted_out | 0 | 0 | 0 | true |
| r1-enabled | 65 | 1 | One four-byte report | true |
| r2-enabled | 65 | 0 | 0 | **false** |
| r2-opted_out | 0 | 0 | 0 | true |
| r2-unavailable | 0 | 0 | 0 | true |

The second enabled case recorded observations but made no reservation and
delivered no report. Its exact cause is **not established**. An admission or
opportunity issue remains a hypothesis; the retained counters do not identify
the cause.

All leases cleared. Cleanup confirms that isolated profiles and the certificate
profile were removed, the collector stopped and production disclosure remained
unchanged.

## Qualification boundary

The original workflow's app-journey step failed and **Summarize retained
measurements** was skipped. The retained qualifier exited with failure because
`summary.json` was absent. No completed summary or full/resource qualification
is credited. The original receipts, per-case results, job steps, cleanup and
qualifier failure remain intact; this report uses them without an app rerun.

The recorded source commit identifies the run, but the incomplete qualifier
does not establish that every runtime input or privacy requirement was
independently verified. Per-case flags do not supply that missing acceptance.
**No RSS/CPU saving is inferred from this incomplete delivery comparison.**
The earlier source checks and all [prior resource overages](2026-10-27-telemetry-resource-roles.md)
retain their original scope.

The [canonical acceptance contract](../implementation/anonymous-product-telemetry.md#required-acceptance-evidence)
and [ledger](2026-10-27-telemetry-acceptance-ledger.md) remain unchanged in scope.
The **2 MiB added RSS / 0.5% of one core** ceilings remain unchanged. Resource,
installed/platform, wire, provider/privacy and aggregate gates remain open.
All 66 requirement states are retained; V08 is **Building**, collection/
destination/route remain **false/null/null**, and release CAs remain empty.
