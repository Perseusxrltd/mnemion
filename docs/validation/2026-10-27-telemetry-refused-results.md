# Refused telemetry leaves action results opaque — 27 October 2026

This source-only follow-up, prepared on
`d63ec5356fa60abb68f11bb27290be603439b11b`, removes optional result/error
classification when no telemetry measurement was admitted. It preserves the
action's original result or error and invokes its callback exactly once.

## Retained finding

Four selected original tests failed because optional classification still ran:

| Original case | Unnecessary optional reads observed |
| --- | ---: |
| Unavailable Studio result | 3 |
| Unavailable Studio error | 1 |
| Unavailable legacy success flag | 1 |
| Studio result after admission timed out | 3 |

The private `checks/original-refusal.log` and its exit-1 receipt retain these
failures. They establish unnecessary local work; they do not establish data
transmission, a persisted observation or an RSS regression.

## Source correction

The [Studio wrapper](../../studio/frontend/src/workspace/measured-client.ts)
now calls the original action directly when admission returns no measurement.
It skips telemetry result/error classification and idempotency inspection;
when collection is unavailable it also skips telemetry workflow/variant
selection. The [UI/legacy wrapper](../../studio/frontend/src/workspace/measurement-action.ts)
uses the same direct path without reading a success flag or classifying errors.

Both direct calls sit outside the optional-work catch, so a synchronous action
failure cannot cause the callback to run again. Admitted observations retain
their existing classification, **25 ms** admission deadline, original policy
revision/generation and completion checks. SDK behavior, retry/idempotency rules
and the returned application result/error remain unchanged.

## Verification and limits

The [frontend tests](../../studio/frontend/scripts/test-telemetry-client.mjs)
cover five refusal modes on desktop and browser paths: unavailable collection,
synchronous null, asynchronous null, rejected policy read and admission timeout.
They require zero optional inspection, the original result/error, one callback
per action and no recorded observation. Late snapshots cannot revive the
refused Studio or legacy action. Existing positive measurement, fresh/replayed
receipt, retry and opt-out checks remain in the selection.

The completed owner/policy selection passed **53 source tests**, with **zero
failures or skips**. The current SDK and frontend builds passed. Original and
corrected results remain separate in `checks/original-refusal.log`,
`checks/owner-policy.log` and the build receipts.

Dependency reuse initially stopped at a strict lock-identity check before any
build or installation. Subsequent graph comparison confirmed matching cached
dependencies; only local release-version metadata differed. A local frontend
SDK overlay used the current compiled client. Registry dependency versions were
not ignored, and no packages were installed. The initial refusal and reuse
receipt remain retained.

These are compiled frontend source fixtures, not a new installed-app or actual
browser journey. No resource experiment was performed and no RSS/CPU saving is
established. The [canonical acceptance contract](../implementation/anonymous-product-telemetry.md#required-acceptance-evidence)
and [evidence index](telemetry-evidence-index.md) retain all prior failures and
remaining resource, provider/ingress, full runtime/platform, installed, wire and
aggregate qualification.

All 66 requirements and their states remain unchanged. V08 remains **Building**;
production collection/destination/route stay **false/null/null**, with release
CAs empty. The **2 MiB added RSS / 0.5% of one core** ceilings remain unchanged.
This source follow-up adds no native or public-release acceptance.
