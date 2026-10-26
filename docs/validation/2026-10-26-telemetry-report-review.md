# Exact telemetry report review: source checkpoint

**26 October 2026 — source and isolated UI checks passed.** The new
source provides optional manual report review through the app, native controls
and maintained local stdio. It is excluded from published 4.46.13. V08 remains
Building, all 66 requirement states are unchanged, and production collection,
destination and route remain false/null/null.

## Implemented boundary

- Automatic remains default. Manual review can be selected before permission;
  an actual packet requires authorized observations, disclosure, a configured
  route and an eligible allowance. This implements the dated
  [contract clarification](../implementation/anonymous-product-telemetry.md#proposed-outbound-schema-and-payload-preview),
  superseding literal actual-packet inspection before collection permission.
- [Python inspection](../../mnemion/product_telemetry/inspection.py), the
  [portable state](../../mnemion/product_telemetry/review.py) and
  [private SQLite row](../../mnemion/product_telemetry/review_storage.py) retain
  one randomized four-byte body. Inspection consumes its pending snapshot but
  spends no delivery allowance. Repeat inspection preserves bytes and the
  original lifetime, capped at 15 minutes or earlier observation expiry.
- Approval permits one eligible reservation of those same bytes. Native and
  browser delivery recheck permission, binding and the original review lifetime
  at handoff. New observations, contribution limits and spent budgets survive;
  consumed snapshots are never restored. Expiry/discard never auto-resumes.
- Private SQLite schema 6 and browser choice 5/budget 2 fence older senders.
  Status/format reads remain nonmutating and do not reveal a staged body;
  explicit review mutations require revision, generation and review-token checks.
- [Privacy controls](../../studio/frontend/src/workspace/Privacy.tsx) and
  [local actions](../guides/product-telemetry-controls.md#report-actions-in-the-new-source)
  expose inspection, approval and discard. Standalone CLI approval only arms a
  later awake owner; the app/browser can offer their existing owner an attempt.

## Source and fixture evidence

The final Python telemetry suite passed **306 tests in 59.20 s**, including
maintained local stdio review, shared compare-and-set controls and HTTP denial.
The earlier headless/aggregate selection passed 86 tests; it is overlapping
evidence, not an additional total. Browser-source checks passed **116 tests**.
Two actual Python/Node SQLite handoff checks passed: approved bytes were used
without redrawing, post-stage pending observations survived, and a changed full
company scope prevented final handoff. Electron and full frontend builds passed.
After keeping inspection imports and clock reads out of automatic producer
maintenance, the 48-test aggregate/inspection selection passed again. This
overlaps the full suite; it is not an additional total.

An actual Chromium Privacy UI journey returned a successful structured result
for exact repeat inspection, live cross-tab byte preservation, approval held
on a metered connection, cross-tab discard, expiry after all live clock
participants closed, and explicit automatic-mode selection. It recorded
**zero report requests and zero delivery attempts**, with the expired packet
erased. The fixture used an isolated in-memory capability and synthetic input;
it did not exercise a production collector, network delivery or private user data.

The separate unavailable-build journey exercised pre-permission pause,
opt-out/reload retention and the synthetic format display, with no actual
packet or observation queue. Its retained log contains executed assertions
but no structured JSON Result; it is not presented as a separate receipt.

Interactive selection/privacy, statistical utility, complete resources and
sensors, whole-wire and installed/platform acceptance remain open. No production
endpoint or collector is activated, and none of these checks completes V08.

## Compiler-free headless review clock

[Direct OS clock access](../../mnemion/product_telemetry/review_clock_system.py)
is used only when the packaged helper is absent. A present broken helper or its
unavailable result cannot trigger this fallback. It needs no compiler, process,
worker or persistent clock file and grants no collection permission.

Actual Linux x64 and Windows x64 components verified that direct Python clocks
match the packaged helper. The Windows direct path uses the documented
`kernelbase.dll` `QueryInterruptTime` export; the initial mismatch failure is
retained. These are component checks. The new direct macOS Python path still
awaits its source CI; the earlier compiled macOS clock evidence below remains
valid and separate.

## Retained clock qualification

The earlier [clock foundation](2026-10-26-telemetry-preview.md#review-clock-foundation)
retains its Linux and Windows x64 evidence. At **05:37:49 UTC**, retained
artifacts from [CI run 40273536081](https://github.com/Perseusxrltd/mnemion/actions/runs/40273536081),
source `cc74631e0e1b1e2e4b0249a82b9c3c619e93aad1`, qualified the clock component on
[macOS ARM64](https://github.com/Perseusxrltd/mnemion/actions/runs/40273536081/job/121411374517)
and [macOS x64](https://github.com/Perseusxrltd/mnemion/actions/runs/40273536081/job/121411374464).
Both Python 3.12.10 and Node 22.23.2 observed the shared clock. These are
component checks, not Electron, installed-review or resource qualification.

The original CI failed container builds because a source-family COPY was
missing. A COPY-only correction still failed because `.dockerignore` excluded
the module. Both rules were corrected separately on source
`92719f4c24accbb40962d24cbab6340c9daa19fe`. A fresh read of
[CI 40277005529](https://github.com/Perseusxrltd/mnemion/actions/runs/40277005529)
showed **8 of 12 jobs successful, zero failed**, with both container jobs passed
and the overall run still in progress. Those container checks cover the separate
input correction, not qualification of this newer review implementation.
Original failures remain preserved. The macOS qualification receipt SHA-256 is
`1abf9e5447e64a7b8afba1beb581448baa4708157a41046040a681f3b3a8a45a`.

## Retained evidence digests

| Evidence | SHA-256 |
| --- | --- |
| Final Python telemetry suite | `c8109c9e979b34714f40fe44866c7cbfad660ffb728de2ee3cbe957737a9bed3` |
| Browser-source suite | `423cfe43b2baf81a537919e5f88ed1443683d36fc749eca7cbe12a0f0fe3422e` |
| Python/Node handoff checks | `c9546953a8018922a96ba7f8670d3a102ccc087f7f647329bdb3cc175740c6a5` |
| Chromium review result and script | `7b79d64681efc2e4e0612c1f4dc3c2c9b76a6a2cb6eb084fd473e31207d77676` |
| Unavailable-build assertions | `0010e039b98e2c0b32ab178edbc0bccc225d57a7b9a09a5184a765ca422d0793` |
| Linux direct-clock comparison | `5f18471e3db6d14760d8d6e25c6f09b89656bba98e803a62e1026147abe50811` |
| Windows direct-clock comparison | `dd41de0ecb3f2d17b50057b44abb475e0030e769dcf427a5d09a5f141db81654` |
| Original Windows direct-clock failure | `8d5ecdf68bc6752752a871c1443dc1fec289cbd453fbbeae138cdc21009d83d5` |
| Electron build | `5e8be4ed286ae0fc76d4c1440a631a5664a43b83fa432d25fc79d5a278b966f6` |
| Full frontend build | `52ed2012e2858085b266c56bff5f2b6b2b3129b8dc619dcd251ffd416efcb65b` |
