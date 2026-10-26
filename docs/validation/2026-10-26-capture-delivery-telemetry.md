# Capture delivery and fresh product telemetry

**26 October 2026, 4.46.21 source follow-up: implementation and focused source
validation complete.** Checks apply to the working-tree changes based on
`28747e87c66dbf1b77b79039c2eeb603845967d5`, before 4.46.21 version preparation.
They are not an installed or published release qualification. The decision and
receipts are retained under
`/home/jorqu/mnemion-completion/2026-10-26-capture-delivery-telemetry/`;
`decision.json` records the 26 October, 14:03:35 UTC decision.

## Implemented behavior and source boundaries

The original decision identified two distinct problems: `remote_committed_events`
includes GET reconciliation and repeated receipt items, so it cannot measure
fresh product usage; a later page or index authorization failure could discard
earlier acknowledgements from the shared cycle report.

The [capture service](../../mnemion/service/capture_custody.py) now reserves the
outer page's request-local disposition before nested memory writes. It preserves
receipt bodies and reports fresh/replayed status through the existing
`X-Mnemion-Idempotency` header. The new `X-Mnemion-Capture-Stored` header contains
only newly inserted events that are currently stored in the new page's receipt,
excluding duplicates and negative fences. Its range is 0–50 per page; replayed
POST and GET readback do not supply a fresh-count header. The
[request context](../../mnemion/service/request_replay.py) keeps metadata local
to one request, and the [OpenAPI route](../../mnemion/service/capture_api.py)
documents both headers. Metadata does not alter the receipt body.

The [Python SDK](../../mnemion/sdk.py) exposes optional per-call `RequestReceipt`
metadata and validates the fixed disposition/count. It adds no observation
owner, global last-response state or new retry. Older/custom clients retain the
existing delivery path, with fresh effects unavailable when metadata is absent.

[DeliveryProgress](../../mnemion/connectors/capture_delivery.py) retains only
the current call's acknowledged items. The
[shared cycle](../../mnemion/connectors/capture_cycle.py) preserves those counts
after a later failure; an uncertain POST makes the fresh total unavailable,
not zero. GET reconciliation contributes no fresh stored events. Live capture
reports include `newly_stored_events`, but
[CaptureReport](../../mnemion/desktop_capture.py) excludes it from
serialization, preserving saved desktop source history and older status readers.
The [headless writer](../../mnemion/connectors/headless_capture.py) also removes
this live count before saving activity, while returning it to the current caller.

The [catalog](../../mnemion/product_telemetry/catalog.json) now allows `capture`
for existing `result_items`. The
[headless](../../mnemion/maintenance_measurement.py) and
[native controller](../../studio/electron/maintenance-measurement.ts) adapters
emit that metric only for a verified fresh count. A completed cycle with neither
local acceptance nor verified fresh stored events adds no use, including
replay/readback-only work. Unknown fresh counts are omitted. The existing
capture-cycle owner remains the boundary: no second `capture.deliver` owner,
new metric, packet, coordinate or sampled wire view is introduced.

## Recorded validation and fixture correction

**172 distinct Python cases passed.** `python-checks.json` and
`python-checks.log` retain the initial **161 passed and ten failures**
(72.17 seconds). All ten failures stopped before capture at the ignored
`mnemion/_studio` bundle guard: that bundle still declared version 4.46.6.
`http-fixture-correction.json` records binding the existing successful current
frontend build through supported `MNEMION_STUDIO_DIST`; the product guard was
not weakened. This build contained the new source implementation with package
4.46.20 metadata. Only the ten failed cases reran; `http-checks.json` and
`http-checks.log` record **ten passed in 31.85 seconds**. The 161 earlier passes
are not counted again, and the original failures remain retained.

A subsequent source review found that headless activity wrote its raw report.
The writer now removes only the live fresh count from its saved copy.
`headless-history.json` and `headless-history.log` record one further passing
real HTTP/database case: fresh count one reaches the current caller, saved
activity omits it, and a subsequent unchanged scan returns zero fresh events.
The total is 161 + 10 + 1 = 172 distinct Python cases.

The Python selection covers SDK metadata, maintenance ownership, aggregates,
wire/coverage contracts, source-status persistence and real PostgreSQL/HTTP
capture journeys with synthetic local sources. Specific observed cases include:

| Case | Recorded result |
| --- | --- |
| New, replayed and GET page receipt | Body equality retained; fresh headers distinguish the new transaction. Mixed duplicate, fresh and fenced events count only fresh stored events. |
| 51 events, lost second-page reply | The failed cycle retains 50 acknowledged items and an unknown fresh total. A later GET reconciles the remaining one item with zero fresh events. |
| Index progress returns 403 | Two earlier acknowledgements remain in the cycle report, including their verified fresh count. |
| Older client without receipt metadata | Delivery succeeds; the fresh stored-event count stays unavailable. |
| Desktop and headless source-status persistence | The live fresh count is absent from saved activity, while current callers can consume it. |

`build-checks.json` records successful Electron and frontend source builds and
the Node selection. `native-checks.log` records **111 passed, zero failed**
desktop-source/wire cases run by Node against compiled desktop controllers;
these are not an installed Electron journey. `source-preparation.json` retains
format, lint and coverage-generation success. `catalog-compatibility.json`
verifies that the only catalog change adds capture to the existing result-item
family list; all existing coordinates and the wire/disclosure/route files are unchanged. No screenshots, browser journey,
model calls or resource benchmark were performed in this batch.
`release-preparation.json` records the successful repository lint/format checks
and 4.46.21 preparation. Installed-platform qualification and publication remain separate.

## Preserved scope and historical evidence

Category coverage remains **94 total, 87 mapped and seven unmeasured**. The
[earlier action audit](2026-10-26-telemetry-action-coverage.md) preserves its
86-mapped/eight-unmeasured baseline and the then-current exclusion of capture
from `result_items`; this new decision does not retroactively change that
evidence. The [individual-action preview](2026-10-26-telemetry-action-preview.md)
likewise retains its own source, browser and runtime boundaries.

V08 remains **Building**, with `collection_available: false`, destination null
and release route null. All 66 requirement texts remain unchanged. Rollback
completion, workspace-switch ownership, full interface/call-site coverage,
model resource/sensor qualification and full privacy, utility, resource and
installed-platform acceptance remain open. Existing release coordinators and
prior native evidence are outside this source batch; current publication is
tracked in [release status](../RELEASE_STATUS.md).
