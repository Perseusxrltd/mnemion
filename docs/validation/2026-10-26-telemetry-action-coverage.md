# Telemetry: action ownership audit and completed boundaries

**26 October 2026, pre-fix source audit at `263161f7` / `95c2000c`.** This
report distinguishes declared telemetry categories from inspected action call
sites. The focused telemetry documents, maps, generator and implementation
paths inspected have no changes between those two commits. The findings below
describe that baseline; they do not credit later menu or headless-control fixes.
The later source changes and their validation are recorded separately below.

V08 remains Building. Collection is unavailable, and destination and release
route address are null. All 66 requirement texts and all 94 catalog categories
remain retained. This audit does not qualify installed native behavior, sensors,
resource limits, privacy, production collection or a release.

## Declarations and inspected call sites

The [generated inventory](../../mnemion/product_telemetry/workflow-coverage.json)
at this baseline has **94 categories: 86 mapped and eight unmeasured**. Its
seven recorded input hashes matched the inspected files. The
[generator](../../deploy/telemetry_coverage.py) reads the catalog and six origin
maps, resolves variant selectors and delegated control operations, and unions
declared owners by category. It does not inspect the implementation call sites.

A mapped category therefore establishes a declaration at one or more reviewed
boundaries, not that every action or surface emits it. The
[preview table](../../studio/frontend/src/workspace/TelemetryCoverage.tsx)
displays category rows; it does not enumerate every action or surface. The
existing requirement to make each unmapped action visible as unmeasured in the
local preview remains unfinished, even when another action maps to the same
category. An arbitrary other-operation event is not a substitute.

The 86/94 description is correctly qualified as a declaration count. It must not
be presented as a percentage of implemented sensors, screens, users or roadmap
completion. Excluded operations must not acquire owners merely to increase it.

## Eight unmeasured categories at the pre-fix baseline

| Category | Inspected disposition | Evidence |
| --- | --- | --- |
| `backup.list` | Deliberate state-inspection exclusion. Backup inventory is implemented; inspecting earlier backups is not a new backup workflow. | `backup.inventory` in the [desktop map](../../mnemion/product_telemetry/desktop-origins.json); `local:backup-inventory` in the [dispatcher](../../studio/electron/service-bridge.ts). |
| `capture.preview` | Deliberate configuration-preview exclusion. The source-preview feature exists without a usage observer. | `source.preview` in the [desktop map](../../mnemion/product_telemetry/desktop-origins.json); `previewCapture` in [DesktopSource](../../studio/frontend/src/workspace/DesktopSource.tsx) and `sources:preview` in the [dispatcher](../../studio/electron/service-bridge.ts). |
| `update.verify` | Verification and bounded retries deliberately belong to the original download cycle. There is no separate verification observation. | `updater_internal_stage` in the [maintenance map](../../mnemion/product_telemetry/maintenance-origins.json); [UpdateMeasurement](../../studio/electron/maintenance-measurement.ts) and the verification branch in [DesktopUpdates](../../studio/electron/updates.ts). |
| `capture.pause` | Desktop capture pause/resume uses `sources.pause` / `sources.resume`. Explicit headless capture controls lack a primary owner at this baseline. | The `source.pause` boolean selector in the [desktop map](../../mnemion/product_telemetry/desktop-origins.json); source-control selection in [desktop-measurement](../../studio/electron/desktop-measurement.ts); the headless-control gap below. |
| `capture.deliver` | Delivery participates in the owned `capture.collect` cycle's overall outcome. Explicit desktop draining has a `capture.drain` acknowledgement. A separate delivered-item measurement is absent, and the existing `result_items` contract excludes capture. | The [shared capture cycle](../../mnemion/connectors/capture_cycle.py), [native adapter](../../studio/electron/maintenance-measurement.ts), [headless adapter](../../mnemion/maintenance_measurement.py) and [metric contract](../../mnemion/product_telemetry/catalog.json). |
| `workspace.switch` | Current transitions use disconnect/connect/open owners. There is no independent switch boundary or explicit switch exclusion; that ownership decision remains open. | Connection actions in the [desktop](../../mnemion/product_telemetry/desktop-origins.json) and [UI maps](../../mnemion/product_telemetry/ui-origins.json); actual controls in [Workspace](../../studio/frontend/src/workspace/Workspace.tsx) and [Connect](../../studio/frontend/src/workspace/Connect.tsx). |
| `models.prepare` | The explicit `mnemion-service prepare-model` command has no product observer. Any future owner must distinguish direct invocation from deployment/startup calls to the same command. Model configuration does not establish preparation coverage. | The `prepare-model` branch in the [service CLI](../../mnemion/service/cli.py), its nested callers in [deployment](../../mnemion/service/deployment.py), and `local.models` in the [desktop map](../../mnemion/product_telemetry/desktop-origins.json). |
| `update.rollback` | Managed rollback exists, but telemetry outcome ownership across restarts remains unresolved. Its private operational records cannot supply a backfilled product observation. | `_rollback`, `_recover` and `_apply` in [service updates](../../mnemion/service/service_updates.py); the [catalog's completion-ownership contract](../implementation/anonymous-product-telemetry-catalog.md#common-bounded-measurements-and-outcomes). |

These dispositions do not remove any category or product feature. Deliberate
inspection/preview exclusions, delegated substeps, missing sensors and missing
primary owners are distinct findings.

## Concrete action gaps at the pre-fix baseline

### Desktop application menus

The desktop map declares `app.preferences`, `app.update-check` and
`app.update-restart`, corresponding to `setup.configure`, `update.check` and
`update.restart`. Their native-agent execution passes through `measureAction`
in the [service dispatcher](../../studio/electron/service-bridge.ts).

The [application menu](../../studio/electron/application.ts), however, calls
`updates.check()`, `updates.restartIfSafe(true)` and `updates.setPreference()`
directly. Those callbacks bypass the mapped action observer at this baseline.
A menu check or restart can subsequently produce a download/apply observation;
that observation does not measure the missing check/restart action itself.

Evidence locations at the baseline: `desktop-origins.json:55-57`,
`application.ts:234-242`, `service-bridge.ts:890-892,928`, and
`desktop-measurement.ts:27-60`. This is a gap in particular entrypoints, not
evidence that the declared native-agent routes are absent.

### Explicit headless capture controls

The connector entrypoint handles `--capture-control` and returns before
`begin_source`. The [control dispatcher](../../mnemion/connectors/headless_capture_control.py)
implements enrollment, pause/resume, drain, backup, inspection and recovery
operations, but that path has no primary product observer at this baseline.

The maintenance map deliberately says capture-control transport does not start
a background observer. That rule prevents a second owner; it does not supply an
owner for the explicit action. Reusing an administrator's choice for remote or
host-managed work remains excluded.

Evidence locations at the baseline: `mnemion/connectors/runner.py:502-514`
returns before `:520`; `headless_capture_control.py:401-429` dispatches the
implemented controls; `maintenance-origins.json:24` states the background
exclusion. Desktop equivalents mapping to a category do not close this headless
entrypoint gap.

### Delivered-item metrics remain outside this batch

The shared capture cycle reports `remote_committed_events` privately and uses
delivery completion in its overall result. Both telemetry adapters use the
remote committed count when deciding whether work was empty. They then emit
local accepted items as `work_items`, pending items as `queue_items` and local
storage as `stored_bytes`; they do not emit the delivered-item count.

The [catalog](../../mnemion/product_telemetry/catalog.json) currently excludes
the capture family from `result_items`. Writing a capture delivery count to that
bucket would therefore require a contract change; it is not authorized by the
existing metric name. This batch does not widen that contract or establish
delivered-item coverage. The separate measurement remains open. Delivery must
not be counted again through the generic page-acceptance transport or through
saved server receipts.

Evidence locations at the baseline: `capture_cycle.py:35-79`,
`studio/electron/maintenance-measurement.ts:28-35`,
`mnemion/maintenance_measurement.py:36-43`, and the `result_items` family
allowlist in `mnemion/product_telemetry/catalog.json`.

## Three documentation corrections

The [catalog](../implementation/anonymous-product-telemetry-catalog.md) has
three scoped wording corrections:

- Selected source owners already provide bounded counts, timing and resource
  samples when admitted. The encoder does not sample those sensors, collection
  remains unavailable, and missing sensors produce no substitute observation.
- Fixed closed-week aggregation, publication and retention exist in source.
  Platform/release cohort views remain unimplemented; production reporting is
  not qualified. The implementation is visible in
  [reporting](../../mnemion/product_telemetry/reporting.py),
  [collector window advancement](../../mnemion/product_telemetry/collector.py)
  and the [wire-v2 reporting contract](../../mnemion/product_telemetry/wire-v2.json).
- The current preview shows category-level declarations. Its existing obligation
  to show every unmapped action as unmeasured remains an explicit open item.

These corrections describe source truth without changing the formal V08
contract, the 66 requirement texts, the 94 categories or any metric allowlist.

## Implemented follow-up

The application and tray now use the same
[menu callbacks](../../studio/electron/update-menu.ts), observed by the existing
desktop consent/measurement boundary. Explicit update checks and restart
requests report an acknowledgement without waiting for the download or install.
Their existing background download/apply cycles retain their own distinct
categories. Constructing or refreshing a menu creates no observation.

Preference changes now confirm whether the requested value was saved. A failed
save is a failed outcome, and the native-agent acknowledgement exposes the same
`applied` boolean alongside its ordinary app status. Neither the preference key
nor its value enters the telemetry encoder.

The standalone `--capture-control` entrypoint now validates its typed action and
uses the [reviewed control map](../../mnemion/product_telemetry/maintenance-origins.json).
All **13** actions are classified: **ten** eligible acknowledgements and **three**
explicit exclusions for status, preview and key generation. Managed/reporting
children, remote-requested work and reusable `perform` calls acquire no owner.
Capture content, request fields, keys, archive paths and returned objects stay
outside the observer. An uncertain control outcome is `unconfirmed`; an
interrupt remains an interrupt, with no replay of the operation.

The same 4.46.19 batch now implements explicit embedding preparation and
`librarian-models --prepare` ownership. The
[service CLI](../../mnemion/service/cli.py) passes only the constant
`embedding` or `librarian_tokenizer` kind to `_preparation_scope` and the
[preparation observer](../../mnemion/maintenance_measurement.py). Both kinds
map to `models.prepare`; model/profile identifiers and normal command output
remain outside telemetry. A completed command records a success, an uncertain
exception records `unconfirmed`, and a keyboard interruption remains an
interruption. The original action and registry cleanup are preserved without
replaying preparation.

Both automatic [deployment/startup calls](../../mnemion/service/deployment.py)
explicitly set `preparation_owner=False`. Listing without `--prepare`, registry
helpers and nested startup acquire no preparation owner. This implements the
direct CLI boundary; it does not qualify model resource use or additional
sensors, and it does not run models for telemetry.

The first menu/capture-control stage retained the original
**94 categories / 86 mapped / eight unmeasured**. With explicit preparation,
the **current inventory is 94 categories / 87 mapped / seven unmeasured**.
`models.prepare` now has the declared `headless_models` owner. The seven
remaining unmeasured categories are `backup.list`, `capture.deliver`,
`capture.pause`, `capture.preview`, `update.rollback`, `update.verify` and
`workspace.switch`. The eight original findings above remain a pre-fix record;
these source changes do not turn the category count into full action coverage
or close the other ownership/sensor findings.

**64 Python checks, 24 distinct Electron/agent checks and 25 browser-source
checks passed**, with no failures or skips. The Python total combines 49
maintenance, coverage-generation and explicit-preparation checks with 15
preview checks; the earlier 35-check selection remains retained. The
Electron/agent result combines 14 final measurement/menu checks and ten
unchanged operator checks; the earlier 23-check result remains retained. A
final confirmation case ensures missing acknowledgements stay unconfirmed.
The Electron build and final frontend build passed.

The tests exercise the actual runner and CLI entrypoints and shared menu
callbacks with disposable controls and stubbed preparation registries. They
verify one original action, result preservation, excluded/managed/nested work,
listing exclusions, disabled collection, opt-out during an action, observer
failure, interruption, registry cleanup, uncertain outcomes and failed
preference saves. These local source checks performed no inference, model
download, real backup, provider call or update. Fixture memory bounds are replaced with a no-op context
for the ownership checks; they do not qualify resource limits. Full native,
model resource/sensor and production acceptance remain open.

The final Python log records `49 passed in 9.00s` in
`/home/jorqu/mnemion-completion/2026-10-26-telemetry-action-coverage/complete-python-checks.log`.
The adjacent `preparation-checks.json` retains the successful command receipts,
coverage regeneration and final frontend build. The recovered
`preview-checks.json` and its logs record the separate 15-Python and
25-browser-source selections, both completed once with exit zero. The
[preparation tests](../../tests/test_product_telemetry_model_preparation.py)
show the stubbed registry and preparation methods; these are ownership checks,
not model execution or resource qualification.

## Audit evidence and limits

This was a focused read-only source audit. The reviewed declarations were the
catalog and six origin maps, including Studio method delegation. Inspection
followed the control CLI, desktop/native dispatcher, Studio/browser/legacy
wrappers, maintained and legacy local stdio dispatch, selected maintenance,
capture controls, model preparation and managed rollback paths.

Static inspection found no eligible maintained-gateway label lacking a literal
`_tool` route, no desktop-map key absent from the desktop action contract, and no
selected Studio/legacy method lacking a frontend property-call site. Those
limited checks do not prove execution, final outcome classification or installed
coverage. No tests, benchmarks, model calls, native acceptance, external writes
or product actions were performed for this audit.

The attributed draft and exact old/new catalog wording are retained with the
private source evidence. That earlier draft conditionally considered
`result_items` for capture. This
report records the subsequent contract finding: capture is excluded, and no
delivered-item change is included in this batch.

## Remaining work and release boundary

Desktop menu, explicit headless capture-control and direct model-preparation
ownership are implemented in source with the scoped validation above. The
pre-fix baseline and original eight findings remain historical evidence.

`update.rollback`, delivered-item metrics, independent switch ownership, full
action-level preview visibility and complete sensor coverage remain open.
Direct preparation ownership does not close model resource/sensor
qualification. Resource, whole-wire, privacy, useful-output, installed-platform
and production/release gates also remain open. Existing exclusions and
delegation remain in force; mapping an additional action does not close them.

At the recorded pre-fix checkpoint, frozen 4.46.18 was held before native start
after 4.46.17 Mac ARM failed during `save_librarian` with `action_failed` and an
unknown underlying cause. Diagnostic-retention work is not proof of a native
bug fix. Public v4.46.13 remained available. Consult the maintained
[release status](../RELEASE_STATUS.md) for subsequent availability and the
[telemetry evidence index](telemetry-evidence-index.md) for separately qualified
results. V08 remains Building, with production collection unavailable.

The later [focused Mac ARM installed-app job](https://github.com/Perseusxrltd/mnemion/actions/runs/40324338816/job/121577644715)
passed for the application copied from the DMG: **package 4.46.18, source
`95c2000c81d3eb7ac5f0a2912fc0769f65dd060f`**. Its retained receipt reports
`passed: true`, including the expected disclosure, restart, recovery and
capture checks. This native journey included a real model download; it is
separate from the stubbed local ownership tests above. The earlier
`save_librarian` failure was not reproduced, and its cause remains unknown.
This result does not qualify the newer 4.46.19 action/preparation changes or
full V08.

The focused native receipt is retained at
`/home/jorqu/mnemion-completion/2026-10-26-native-model-action-diagnostics/macos-arm64/installed-hosting.receipt.json`,
with archive SHA-256
`d6749efedafdc4c83b5c3e7a781eb993fa90d2ba74d467c1bde8e5a233b7a301`.
