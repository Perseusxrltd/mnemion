# Saved-workspace selection and backup inventory ownership

**26 October 2026, 4.46.25 source follow-up; focused checks and builds passed.** This batch
follows integrated 4.46.24 source `49c6459fc93b40773294b45f31f8098f6caff3e6`.
It adds precise ownership for existing explicit saved-workspace selection and
backup inventory. Installed/native, resource and production acceptance remain
separate gates; release preparation is not credited by this source report.

## Explicit saved selection

Only native `workspace.restore` and its app IPC route `workspaces:restore` now
choose between `workspace.open` and `workspace.switch`. The
[connection controller](../../studio/electron/workspace-connections.ts) makes
the comparison after identity verification and its final connection-generation
check. It compares the normalized endpoint, tenant and principal with the
currently active profile; session handles and bookmark labels do not decide.

| Verified explicit restore | Telemetry category and outcome |
| --- | --- |
| No active profile, or the same endpoint/tenant/principal with a fresh session | `workspace.open`, retaining the existing `accepted` outcome. |
| A different verified endpoint, tenant or principal | `workspace.switch`, retaining `accepted`. |
| Selected local workspace to a saved workspace | `workspace.switch`, handled in both app and native paths. |
| Restore throws | Preserve the previous failed `workspace.open` observation; do not infer a completed switch. |
| A successful result lacks unused controller metadata | Discard completion rather than infer open/switch from result fields. |

[Desktop measurement](../../studio/electron/desktop-measurement.ts) starts one
fixed choice under the original privacy revision, store generation and clock.
The category decision does not take a new consent snapshot after the operation.
Final opt-out/store-generation fences and contribution limits remain in force;
one selection does not become both an open and a switch observation.

The [selection metadata](../../studio/electron/workspace-selection.ts) is only
an `opened`/`switched` enum associated with the exact result in a one-use WeakMap.
It is not added to JSON, IPC fields or saved state. The
[native workspace wrapper](../../studio/electron/desktop-workspace-actions.ts)
transfers this enum to its outward result; the
[app bridge](../../studio/electron/service-bridge.ts) handles local-to-saved
selection. Telemetry consumes the enum without inspecting endpoint, tenant,
principal, private session fields or revision hashes. Clones, unbranded objects
and reused results cannot establish fresh selection evidence. The enum is
consumed even when telemetry admission was refused.

Automatic resume has no owner and clears any selection metadata created by its
internal restore. New connect, sign-in and local-open actions retain their
existing labels. Reusable controller helpers do not acquire an extra owner.
This changes classification of an existing explicit action, not the scope of
workspace capabilities or a count reconstructed from saved sessions.

## Explicit backup inventory

The [desktop origin map](../../mnemion/product_telemetry/desktop-origins.json)
now maps native `backup.inventory` and app `local:backup-inventory` to
`backup.list`, with `success` when the bounded controller operation returns.
The observer does not inspect returned backup content, locations or identifiers.
List success does not establish backup validity, restoration or cloud delivery.
Status, polling, cached operator replies and reusable inventory helpers remain
unowned. The app's existing Backup inventory request and native operator action
share this reviewed boundary.

## Current inventory and preserved checkpoints

The generated [inventory](../../mnemion/product_telemetry/workflow-coverage.json)
now contains **94 categories: 93 mapped and one unmeasured**, and **632 action
rows: 360 mapped, 265 excluded, seven delegated and zero unmeasured within
represented declarations**. Desktop operations remain 77, with 46 eligible and
31 excluded; state-inspection exclusions decrease to 14. Five interfaces remain
independently enumerated, while other owners use reviewed source-route maps.
These declarations do not prove every screen, sensor, call site or installed app.

`update.verify` remains the one independent unmeasured category. Verification
continues within the existing owned download cycle; this batch adds no separate
product action or observation for it. The broader telemetry acceptance contract
is unchanged.

The [4.46.24 capture report](2026-10-26-telemetry-capture-actions.md) retains its
91-mapped/three-unmeasured and 630-row checkpoint, initial failures, corrections
and source checks. The [4.46.22 workspace report](2026-10-26-workspace-telemetry-ownership.md)
retains its earlier open-only restore mapping and automatic-resume exclusion.
Neither historical test set qualifies these new selection boundaries.

## Completed source checks and retained failures

| Selection | Result and scope |
| --- | --- |
| Python coverage and preview | 30 distinct cases passed: 28 initially, then only the two corrected cases. |
| Compiled workspace/authentication/measurement controllers | 69 Node cases passed, with no skips. |
| Cross-runtime selection policy | One separate Node/Python SQLite policy integration case passed, bringing the Node total to 70. |
| Browser-source preview/policy | 25 cases passed; this is not a live browser journey. |
| Builds | Electron and frontend source builds passed. |

`python-qualification.json` and `coverage-and-preview-tests.log` retain the
initial **28 passes and two failures**. `corrected-coverage.json` and
`corrected-coverage-tests.log` record the two corrected passes. Neither
correction changed runtime behavior or repeated the already passing cases:

- `test_future_interface_action_is_not_hidden_or_given_an_invented_workflow`
  repeated the previous 91/three category totals. It now compares the original
  category summary before and after adding an unmapped future interface action.
  The independent current-inventory assertion still requires 94/93/one and exact
  source owners.
- `test_desktop_channels_are_independently_visible_including_resume_and_transport`
  keyed rows only by action and collapsed saved restore's two variants. It now
  asserts both exact opened/switched variants, their selector and workflows, and
  explicit `backup.list` coverage.

Both cases are in `tests/test_product_telemetry_coverage.py`.
`initial-failure-analysis.json` retains their explanation.
`native-qualification.json`, `native-workspace-and-measurement.log` and
`cross-runtime-selection-consent.log` bind the 69-plus-one Node results and
Electron build. `browser-qualification.json` and `browser-preview-checks.log`
bind the 25 browser-source cases and frontend build.

These are compiled-controller and local policy/storage checks. The separate
Node/Python case exercises SQLite policy sharing, not installed Electron or a
real provider. They do not establish native release or resource qualification.

Catalog, disclosure, wire coordinates and resource budgets are unchanged.
V08 remains **Building** with collection/destination/route **false/null/null**.
All 66 requirement texts and states remain. Resource, whole-wire/provider/ingress
privacy and installed-platform acceptance remain open. Current release availability
and live gate status belong to [release status](../RELEASE_STATUS.md).
