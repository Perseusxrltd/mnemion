# Telemetry cold-start allocations — 26 October 2026

This source follow-up, based on `2666615d9803dead4aa53fdf93358d20a11ce331`,
corrects two deterministically reproduced allocation paths. It does not establish
RSS/CPU savings or resource acceptance.

## Reproduced behaviors and corrections

The unchanged compiled runtime materialized the bundled TLS certificate list
once when loading the telemetry sender, and 32 fresh reads of an absent optional
company policy threw 32 `ENOENT` exceptions. The original cold-start reproduction
retains both expected failures: `1 !== 0` and `32 !== 0`.

The [native sender](../../studio/electron/telemetry-transport.ts) now uses
`createRequire` to select only `connect` and `createSecureContext` from the TLS
module. This avoids the ES-module facade enumerating the lazy `rootCertificates`
export; release-owned trust and TLS verification remain unchanged. The
[policy reader](../../studio/electron/telemetry-store.ts) uses nonthrowing `lstat`
for a missing optional company-policy file. Only absence selects the existing
company-policy default; other errors and malformed or restrictive policy still
deny. Checks remain fresh, with no positive permission cache. Consent, generation,
spending, schema and wire rules are unchanged.

## Completed source checks and diagnostic

The Electron build passed. **Two cold-start tests passed under Node 22.22.0**;
the actual Electron 44.9.3 / Node 24.22.0 binary in Node mode passed **95
cold-start/store/delivery/owner/TLS checks, with two platform skips** and no
failures. The two cold-start cases overlap between runtimes and are not counted
as 97 distinct tests.

The fixed changed-source allocation diagnostic completed in **190.816 seconds**.
Its unavailable and enabled cases each completed **128 synthetic memory cycles,
384 operations and 387/387 successful HTTP requests** in the unpackaged Linux x64
source app. Enabled delivered one accepted four-byte report; unavailable delivered
none. No forbidden metadata or model calls were recorded. Both leases cleared;
fixture cleanup removed profiles/certificate material, stopped the collector and
left production disclosure unchanged.

The baseline inventory had 2,178 source/compiled inputs; the corrected inventory
had 2,179. Both corrected cases' input manifests match, SHA-256
`11006d23fe46c09caf6bfc4cadc750504f140fc85f34cb1bc5f1c8a2bb5051e8`.
The six changed input paths are the two native source files linked above,
`studio/electron/dist/telemetry-store.js`,
`studio/electron/dist/telemetry-transport.js`, `studio/electron/package.json` and
`studio/electron/scripts/test-telemetry-cold-start.mjs`.

| Weighted JavaScript allocation samples, bytes | Baseline | Corrected |
| --- | ---: | ---: |
| Unavailable total | 27,074,788 | 26,803,808 |
| Enabled total | 30,410,620 | 29,973,980 |
| Enabled bundled-root getter | 169,872 | 0 |
| Enabled `lstat` | 277,364 | 7,252 |

Sampling included collected JavaScript objects, with no forced GC or idle padding.
These values are allocation samples, **not RSS or CPU savings**. They do not
qualify a stable per-process ceiling, native allocation coverage or installed
platforms. The retained Node SQLite reference confirms statement finalization at
close; no binding replacement based on a deferred-finalization leak was selected.

The closed `allocation-corrections-qualification.json` receipt has SHA-256
`aa84eb5468d43108c28670883f0599cebb39218cb3c2fcaf7ae7f5f41c82732e`.
It binds the original and corrected summaries/profile receipts, plans, references,
failed reproduction and successful focused checks. All original failures remain
retained; no additional resource trial is selected.

All 66 requirement texts and states remain unchanged. V08 stays Building with
collection/destination/route false/null/null and release authorities empty. The
[earlier RSS failure](2026-10-26-telemetry-scoped-trust-results.md),
[browser qualification gap](2026-10-26-telemetry-browser-pressure.md), unchanged
2 MiB / 0.5% budgets and installed/provider/privacy/whole-wire gates remain open.
Full V08 completion and its notification remain pending.
