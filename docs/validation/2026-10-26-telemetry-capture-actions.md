# Capture action ownership and source-CI capacity recovery

**26 October 2026, 4.46.24 source follow-up; focused checks and builds passed.**
The capture changes follow frozen 4.46.23 source
`e747707e1dfe4d7cedd3de7c574f501e3607a74d`. They classify fresh work more precisely
without another producer, catalog/disclosure change or collection activation.
Source validation is separate from release preparation, installed/native and
production qualification.

## One owner, selected after the cycle

Previously, a capture cycle with no locally accepted items and a positive verified
fresh stored count still recorded `capture.collect`. The
[Python](../../mnemion/product_telemetry/workflow.py) and
[desktop](../../studio/electron/telemetry-workflow.ts) workflow APIs now admit
two to four distinct fixed catalog choices under one original policy revision,
store generation and start time. Completion selects a declared category at most
once. It does not acquire new permission after the work. Final policy/generation
fences and the selected category's contribution limits remain enforced.

The [headless adapter](../../mnemion/maintenance_measurement.py) and
[desktop adapter](../../studio/electron/maintenance-measurement.ts) use the fixed
pair `capture.collect`/`capture.deliver`:

| Current-cycle evidence | Observation |
| --- | --- |
| No locally accepted items and a positive verified `newly_stored_events` | Select `capture.deliver`, preserving the whole cycle's outcome and latency. |
| Locally accepted items, with or without fresh delivery | Keep `capture.collect`; mixed work gets no second owner. |
| Completed cycle with no locally accepted items and zero or unknown fresh count | Discard the observation, including its submission. |
| Incomplete/denied cycle without verified fresh delivery | Preserve its existing non-success observation; unknown fresh count is not a verified zero. |

The category does not assert successful delivery or isolate HTTP transfer time.
The fresh count must be an integer between zero and this call's acknowledged
`remote_committed_events`. Unknown counts omit `result_items`. Replayed receipts,
GET reconciliation and saved source status cannot establish fresh work. Earlier
acknowledgements and uncertainty after an unconfirmed POST retain the
[4.46.21 delivery semantics](2026-10-26-capture-delivery-telemetry.md).

[DesktopSources](../../studio/electron/desktop-sources.ts) owns only automatic
maintenance cycles; explicit Sync already has its originating request owner.
The [standalone entrypoint](../../mnemion/connectors/runner.py) excludes requested
scans, managed/reporting children and reusable helpers. No SDK, HTTP or server
recounting is added. Resource cells remain separate process-only samples under
the original fence; this change establishes no resource saving or new sensor.

## Explicit conversation preview and pause

The [desktop map](../../mnemion/product_telemetry/desktop-origins.json) now maps
native `source.preview` and app IPC `sources:preview` to `capture.preview`.
Both reach the same preview controller. The
[standalone map](../../mnemion/product_telemetry/maintenance-origins.json) maps
`--capture-control` action `preview` to `capture.preview` and action `pause` to
one accepted `capture.pause` acknowledgement. Ownership begins at the explicit
entrypoint; nested preview/control helpers acquire no owner.

Preview success means the bounded local conversation inspection returned. A
returned catalog can still be limited or unavailable; it does not establish
configured capture, complete file coverage, collection or delivery. Telemetry
receives no paths, selection, configuration hash, content or returned preview.
Standalone `--inspect`, status and key generation remain excluded. Resume and
generic desktop source pause/resume keep their existing source categories.
Telemetry's own privacy and format-preview controls remain unmeasured.

## Inventory

The regenerated [inventory](../../mnemion/product_telemetry/workflow-coverage.json)
has **94 categories: 91 mapped and three unmeasured**, and **630 action rows:
356 mapped, 267 excluded, seven delegated and zero unmeasured within represented
declarations**. The remaining categories are `workspace.switch`, `backup.list`
and `update.verify`. Existing explicit workspace boundaries, backup inspection
exclusions and verification within update cycles do not gain synthetic owners.

Current desktop operations total 77, with 45 eligible and 32 excluded. The 13
standalone capture controls have eleven eligible actions and two status/key
exclusions. Five interfaces remain independently enumerated; other owners use
reviewed source-route maps. These counts do not prove every screen, sensor or
installed runtime. The historical 4.46.23 inventory remains 88 mapped/six
unmeasured categories and 628 rows (351 mapped, 270 excluded, seven delegated).

## Source-CI capacity recovery

The related [release automation](../implementation/release-automation.md)
extends the existing once-only hosted-capacity retry to the latest eligible
Product checks push on `main`. The motivating
[4.46.23 source run](https://github.com/Perseusxrltd/mnemion/actions/runs/40359469526)
completed with 11 of 12 jobs passing and only its unstarted Mac supervision job
cancelled for capacity. Retained evidence shows zero steps, no assigned runner
and GitHub's exact annotation: “The job was not acquired by Runner of type hosted
even after multiple attempts.” That failed source run is not qualification.

[The helper](../../deploy/runner_capacity_retry.py) requires complete bounded
job/annotation inventories and exclusively recognized unstarted capacity
failures. Source must still match `main`, or a bounded, untruncated comparison
must show only the existing `ci_scope.documentation()` paths, including both
names of any rename. Runtime changes, newer main CI, ordinary test failures,
unfinished runs and second attempts are rejected. Run/source eligibility is
checked again immediately before the single failed-job retry request. The
[status workflow](../../.github/workflows/release-status.yml) uses trusted code
from `main`; failed or incomplete checks never become passing release evidence.

## Completed checks and retained failures

| Selection | Result and scope |
| --- | --- |
| Capture workflow, maintenance, coverage, preview and inspection | 109 distinct Python cases passed across initial and corrective selections. |
| Compiled desktop/store/controller checks | 154 Node cases passed, with two Windows-only skips. |
| Browser-source telemetry checks | 120 Node cases passed; this is not a live browser journey. |
| Source-CI capacity guards | 41 Python cases passed with mocked GitHub reads and mutations; no live retry qualification. |
| Builds | Frontend and Electron source builds passed. |

The original receipts are retained: `python-qualification.json`,
`native-qualification.json`, `corrected-fixtures.json`,
`browser-qualification.json` and `runner-capacity-qualification.json`, with
their named logs. Counts combine distinct passing cases; overlaps are not added
twice. The initial capture selections recorded **106 Python passes/three
failures** and **153 Node passes/one failure/two skips**. The four failed cases
passed after test-only corrections, with no runtime change for those corrections:

- Consent re-enable fixtures now supply the required current generation while
  retaining the check that the original operation cannot inherit renewed consent.
- The saturation fixture fills 64 individual observations, rather than treating
  64 submission/outcome pairs as 64 observations. The separate delivery allowance
  still permits its bounded contribution.
- The existing review-contention fixture now forces nonblocking refusal and
  checks that the same approved packet remains with zero spent attempts. A later
  race permits at most one claimant, followed by an uncontended claim if needed;
  exactly the original bytes are claimed once, one attempt is spent, and further
  claims are refused.

`initial-failure-analysis.json` and `initial-review-race-state.json` retain the
original explanations and approved, unspent report state. Successful corrections
do not erase the failed receipts. Capacity tests passed separately; they do not
establish an actual retry, runner availability or recovered native acceptance.

The catalog, disclosure, route, metric coordinates and wire views are unchanged.
V08 remains **Building**, with collection/destination/route **false/null/null**.
All 66 requirement texts, states and existing resource/privacy limits remain.
Resource, whole-wire/provider/ingress privacy and installed-platform gates are
open. No new benchmark, provider/model calls, live browser journey, 4.46.24 native
qualification or publication is established by these source checks. Current
release availability belongs to [release status](../RELEASE_STATUS.md).
