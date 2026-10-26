# Repeated telemetry metadata allocation — 26 October 2026

This source follow-up, based on `8aadccf3026420465b4c3974342b77f628739f0d`,
removes repeated derivation of fixed metadata while retaining fresh authority
checks. Correctness checks and both builds passed. No RSS/CPU saving or
whole-app resource qualification is established.

## Changes and retained reproduction

The original bounded selection passed its unavailable-trust control and failed
three allocation assertions. The corrected selection passed the intended counts:

| Operation in the fixed tests | Original | Corrected |
| --- | ---: | ---: |
| Database URL derivations | 5 | 1 |
| Full descriptions made only for group filtering | 3 | 0 |
| Certificate decodes across repeated owner availability checks | 130 | 1 |
| Certificate decodes when collection is unavailable | 0 | 0 |

These are deterministic operation counts, not resource measurements. The three
original failures remain retained in `original-checks/repeated-static-metadata.log`.

[DesktopTelemetryActivity](../../studio/electron/telemetry-activity.ts) lazily
validates its copied, frozen certificate list once for its availability gate.
Caller mutation cannot replace that copy. Actual endpoint construction,
certificate/hostname verification and current consent remain required; no TLS
acceptance or positive policy decision is cached.

[NativeTelemetryStore](../../studio/electron/telemetry-store.ts) derives its
fixed database path and read/write URI strings once per store lifetime. Every
filesystem/ACL, current-policy and transaction-local SQLite authority check
remains in place. The cache retains no database handle, statement or permission.
The regression uses spaces, percent/hash signs and a non-ASCII path character,
then verifies refusal after a real policy change.

[TelemetryCatalog](../../studio/electron/telemetry-catalog.ts) shares one strict
decoder between group-only filtering and full descriptions. Native/browser
filtering avoids unnecessary description objects; actual preview and wire
preparation retain them. Numeric coordinates, family restrictions and rejection
rules remain unchanged. This does not claim allocation-free filtering.

## Qualification and limits

The actual Electron runtime in Node mode passed **100 checks**, with **two
Windows-specific skips** and no failures. All **134 browser-source tests passed**,
with no skips or failures. Electron and frontend builds passed. The independent
Python comparison agreed on group classification and invalid-cell rejection for
all **65,536 numeric coordinates**; six additional invalid inputs were rejected.
No model calls occurred.

The private `2026-10-26-telemetry-metadata-allocation` evidence set retains the
original findings, failures, checked source hashes and closed check receipt.
`source-qualification.json` has SHA-256
`3093fd3ee8b6955764e01365bca07647a2492206f523f5c4222097e4c7425203`;
the bound check receipt has SHA-256
`8d08657d7e07635046f9ed19d1087c80cb6dd636eeb8a7feb12ecad0d98cc2db`.
The original failure log has SHA-256
`39be5377b559330f9b0536beef049a211dd9b3206d2802d37a03b8a4555502eb`.

One fixed six-case comparison of the changed source is selected after
integration; **its result is pending**. Earlier
[resource failures](2026-10-26-telemetry-scoped-trust-results.md) remain binding
under the unchanged **2 MiB / 0.5%** gates. This source qualification establishes
no installed-platform, production, provider/privacy or full V08 acceptance.
All 66 requirement texts and states remain unchanged. V08 stays Building with
collection/destination/route **false/null/null** and release CAs empty.
