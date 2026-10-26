# Workspace ownership and desktop request inventory

**26 October 2026, 4.46.22 source follow-up; focused tests and builds passed.** This
records source changes based on integrated 4.46.21 commit
`279017c1cccd8970a25e59dcc98893902c65ee9b`. The local decision receipt was recorded on 26 October at 14:41:24 UTC. Source
validation and release preparation passed; installed/native and production
qualification remain separate and pending.

## Explicit workspace boundaries

[Connect](../../studio/frontend/src/workspace/Connect.tsx) invokes workspace
resume from its startup effect. [WorkspaceConnections.resume](../../studio/electron/workspace-connections.ts)
can return an already active session or share an in-flight restoration. Counting
that call as a fresh `workspace.open` would misclassify automatic connection work.

The reviewed [desktop map](../../mnemion/product_telemetry/desktop-origins.json)
now excludes `workspaces:resume` as `automatic_connection`. The
[dispatcher](../../studio/electron/service-bridge.ts) uses
[desktopIpcSelection](../../studio/electron/desktop-measurement.ts) before
telemetry policy or observation access. Excluded requests continue their original
operation without a telemetry owner. Explicit `workspaces:restore` remains
owned as `workspace.open`; explicit `workspaces:reset` now owns one
`workspace.forget` acknowledgement.

## Inventory and runtime map

The map's `ipc` section classifies **all 72 actual preload request channels**,
including fixed `hosts:action` and `sources:control` variants. It records explicit
inspection, privacy, configuration, automatic-connection and transport exclusions;
enclosing Studio actions retain ownership of delegated service/vault transport.
The runtime dispatcher and the action inventory consume the same reviewed map.

The [generator](../../deploy/telemetry_actions.py) now independently enumerates
[preload.ts](../../studio/electron/preload.ts), its fifth interface after the
control contract, native actions, SDK class methods and legacy API declarations.
Absent channel mappings remain visible as unmeasured; a stale mapped channel or
native-action reference is rejected by the generator. Focused source checks
cover inventory gaps and invalid mappings.

The current [generated inventory](../../mnemion/product_telemetry/workflow-coverage.json)
reports **622 actions and fixed variants: 348 mapped, 267 excluded, seven
delegated and zero unmeasured among represented declarations**. Category counts
remain **94 total, 87 mapped and seven unmeasured**. The larger declaration
inventory does not establish complete screen, call-site, sensor or installed
coverage. Other owners still use reviewed source-route maps rather than a full
independent call-site inventory.

## Scope decisions

Changing workspace is represented by the chosen explicit connect, sign-in or
open action. No additional synthetic `workspace.switch` observation is added;
the catalog retains that unmeasured category. The original requirement to expose
unmapped supported actions remains in force.

Managed-server rollback cannot inherit a local administrator's telemetry choice
or backfill observations from private operational journals. A separately
disclosed host owner and cross-restart completion qualification remain open.
This decision supplies neither a rollback producer nor a completed recovery claim.

## Source validation and retained evidence

The final source selection totals **54 distinct Python cases and 26 Node tests**.
The retained local validation receipts identify the commands and logs below.
`python-checks.json` and `python-checks.log` record **53 passed in 9.75 seconds**
for coverage, preview and inspection. `build-checks.json` records successful
Electron and frontend source builds and the combined Node command;
`native-checks.log` records **26 passed, zero failed** across
`test-desktop-measurement.mjs`, `test-desktop-workspaces.mjs` and the existing
`test-product-telemetry.mjs` script in that command. There was no automatic retry.

The additional Python case preserves and corrects the original 4.46.21
[Python 3.13 CI failure](https://github.com/Perseusxrltd/mnemion/actions/runs/40340059114/job/121632168636):
**one failed, 2,286 passed and 16 skipped**. The failure was the stale equality
assertion in
`service_tests/test_desktop_durable_capture.py::test_native_offline_capture_then_missing_folder_delivery_and_status`.
The live report contained `newly_stored_events=1`; the saved report intentionally
omitted it, with 17 other fields identical. `preceding-python313-failure.json`
and the original job log retain that result.

Only the test changed: it now requires the live count to be one, forbids that
field in saved report/disk, compares every other field exactly and verifies
that saving did not mutate the live report. Runtime behavior is unchanged.
`capture-regression-decision.json`, `capture-regression-checks.json` and
`capture-regression.log` record this correction and **one passed in 15.72 seconds**.
This was a real HTTP/PostgreSQL regression with the external test DSN unset;
the frontend fixture was rebuilt with prepared 4.46.22 metadata and selected
through `MNEMION_STUDIO_DIST`. It adds one distinct case to the original 53.

The compiled fixtures used changed source based on `279017c1`, with package
4.46.21 metadata before 4.46.22 preparation. WorkspaceConnections/WorkspaceStore
fixtures covered active-session
readback, lock/resume, absent sessions, explicit restore/reset, failed offline
automatic resume and native-agent transitions. Automatic resumes produced zero
policy reads and observations; each tested explicit control owned one workflow,
with no identity in cells. These disposable fixtures used a synthetic cipher and
local stubs. They do not qualify installed Electron, a real provider or resource
overhead. No new resource benchmark was run.

`compatibility.json` confirms that catalog, wire-v2, disclosure and release-route
files are byte-unchanged. This batch adds no collection permission or wire change.

The [earlier action preview](2026-10-26-telemetry-action-preview.md) retains its
525-row/four-interface source and Chrome checkpoint. The
[capture-delivery report](2026-10-26-capture-delivery-telemetry.md) retains its
172 distinct Python and 111 Node cases for the preceding batch. Neither qualifies
these workspace changes or an installed 4.46.22 release.

## Release coordination checkpoint

The 4.46.20 private coordinator stopped at its **30-minute native-observation
timeout** while the original 4.46.19 Mac Intel run remained live. That timeout
was not a native product failure. Separately, the 4.46.21 source-CI Mac ARM job
was cancelled before acquiring a runner. GitHub's annotation was: “The job was
not acquired by Runner of type hosted even after multiple attempts”, alongside
macOS ARM capacity notices. No retry or release bypass occurred.

The original [4.46.19 native run](https://github.com/Perseusxrltd/mnemion/actions/runs/40333990605)
has since succeeded. Its [public artifact verification](https://github.com/Perseusxrltd/mnemion/actions/runs/40343874190)
is still running at this checkpoint; this report does not claim publication or
transfer that native result to 4.46.22.

The intended recovery is to consolidate the unreleased 4.46.20/21 changes in
4.46.22 after remaining live runs settle, avoiding duplicate native release runs.
Release preparation passed. Native qualification and publication remain pending
at this checkpoint; the source passes above do not complete those gates.

V08 remains **Building**. Collection is unavailable, destination and release
route are null, and wire/disclosure contracts are unchanged. All 66 requirement
texts remain retained. Full interface/call-site, model resource/sensor, privacy,
utility, resource and installed-platform acceptance remain open. Consult
[release status](../RELEASE_STATUS.md) for publication, which is separate from
this source record.
