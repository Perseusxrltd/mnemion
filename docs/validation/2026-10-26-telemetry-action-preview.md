# Telemetry: individual-action preview

**26 October 2026, source follow-up for 4.46.20.** This extends the
[4.46.19 ownership checkpoint](2026-10-26-telemetry-action-coverage.md) after
its frozen source `93eb300`. The new preview makes mapped, excluded, delegated
and unmeasured action declarations visible separately from category coverage.
This report describes source implementation and the scoped checks below; it
does not qualify a 4.46.20 installed release.

V08 remains Building. Collection is unavailable, destination and route address
remain null, and all 66 requirement texts and all 94 catalog categories remain
retained. The preview adds no collection owner, sensor, producer or permission.

## Category and action counts have different scopes

The [generated inventory](../../mnemion/product_telemetry/workflow-coverage.json)
retains **94 categories: 87 mapped and seven unmeasured**. Its new
`action_coverage` section records **525 actions and fixed variants**:

| State | Rows | Meaning |
| --- | --- | --- |
| `mapped` | 296 | The action or fixed variant has a reviewed workflow declaration. |
| `excluded` | 224 | A fixed reason records why this path is not an additional usage observation. |
| `delegated` | 5 | The action is owned elsewhere, including control delegation and aliases. It does not add a second owner. |
| `unmeasured` | 0 | No represented interface declaration currently lacks a reviewed mapping. This is not a count of every possible screen or runtime path. |

These are declaration rows, including fixed variants, not 525 independent
workflows or observations. Zero unmeasured action rows does not remove the seven
unmeasured categories or establish complete product coverage. The original
86-mapped/eight-unmeasured audit and later 87/seven ownership checkpoint remain
dated evidence; this preview does not rewrite either result.

## Four interfaces are enumerated independently

[The action generator](../../deploy/telemetry_actions.py) reads four shipped
interface sources without importing the application or invoking its commands:

| Interface | Source | Inventory owner |
| --- | --- | --- |
| API control operations | [agent_contract.json](../../mnemion/service/agent_contract.json) | `control_cli` |
| Native desktop/operator actions | [desktop-actions.ts](../../studio/electron/desktop-actions.ts) | `native_commands` |
| Studio SDK class methods | [client index.ts](../../packages/client/src/index.ts) | `studio_actions` |
| Legacy API object | [legacy client.ts](../../studio/frontend/src/api/client.ts) | `legacy_ui` |

The SDK-method rows describe the Studio wrapper's classification. The reusable
SDK and its other consumers do not acquire a collection owner from this view.

For these interfaces, generation starts with the action names in the interface,
then applies the reviewed origin map. A missing mapping therefore produces an
`unmeasured` action row even when a different action already maps to the same
workflow category. A stale map referring to an absent interface action is
rejected. The parser uses the current explicit declaration syntax; changed or
additional interface forms still require review.

Fixed variants and their exclusions come from the reviewed maps. The source
rejects overlapping mapped/excluded variants and unknown exclusion reasons.
An empty variant declaration must not silently remove its action from the
inventory; the final generator guard and its updated checks preserve that rule.
The generated input hashes include these four interface files as well as the
existing catalog/origin inputs, so the usual inventory verification also covers
the inspected declarations.

Browser connection routes, maintained/legacy local stdio, source/updater work,
standalone capture controls and explicit preparation use their existing
reviewed source-route maps. Those groups are not independently enumerated from
all implementation call sites by this generator. An unlisted route in those
groups still requires a source audit; the map cannot prove its own completeness.

The existing requirement to expose every unmapped supported action remains in
force. This implementation covers the represented declarations and makes
missing known-interface mappings visible; complete interface/call-site and
sensor reconciliation remains open.

## Read-only inspection

The existing on-demand format inspection exposes `action_coverage` alongside
the category metadata in app/browser and offline native schema/preview.
[TelemetryCoverage](../../studio/frontend/src/workspace/TelemetryCoverage.tsx)
retains the category view and adds **Individual actions** when the metadata is
available. An older response without `action_coverage` keeps the category view.

[The action table](../../studio/frontend/src/workspace/TelemetryActions.tsx)
shows the action, source, state, fixed selector/variant and workflow mapping or
exclusion reason. A delegated control can open the corresponding source view.
Search matches action names, fixed variants, source labels and workflows;
source and state filters can be combined. Pages show at most **50 rows**, with
previous/next controls and a visible empty-result message.

The component filters fixed metadata in local view state. It does not invoke
the actions it describes, inspect private activity, acknowledge disclosure,
reserve reports or add telemetry observations. Collection and the existing
privacy choices retain their separate authority.

The complete inventory, including category metadata, action reasons and input
hashes, has an **81,194-byte JSON representation** and a **119,617-byte pretty
JSON file** at this checkpoint. These are inspection-metadata sizes. They are
not a resource qualification, a report payload or a whole-wire measurement.
Pagination bounds displayed rows; it does not establish the 2 MiB / 0.5%
telemetry overhead limits.

## Recorded source validation

**22 distinct Python, 16 Electron/bridge and 42 browser-source/client checks
passed**, with no failures or skips. The Electron/bridge total comprises the
14 native-measurement cases and two Node-to-Python bridge cases using compiled desktop controllers. The
seven updated generator cases are part of the 22 Python cases, not seven
additional cases. The earlier 22/14/42 results and build logs remain retained.
Electron and frontend source builds and the final 4.46.20 preparation passed.
These are scoped source/bridge receipts, not a 4.46.20 installed-package receipt.

The coverage/preview checks include missing and future known-interface actions:
their action rows remain unmeasured regardless of another owner's category
mapping. Compiled reflection checks validate the current native, SDK and legacy
interface extractors against their exported declarations. These checks address
extractor coverage and preview behavior, not instrumentation of every call site
or collection in every installed runtime.

The command receipts and logs are retained under
`/home/jorqu/mnemion-completion/2026-10-26-telemetry-action-preview/`:
`python-checks.json` and `python-checks.log` record the 22-pass Python selection;
`build-checks.json`, `native-checks.log` and `browser-source-checks.log` record
the original 14/42 selections and successful source builds. `final-checks.json`
records the updated seven-case generator pass, two actual Electron-to-Python
bridge checks and successful 4.46.20 preparation. Overlapping cases are not
counted twice, and no count from the earlier ownership batch is reused as
qualification of this new preview.

## Actual Chrome verification

`browser-acceptance.json` records **eight evaluated observations**, retained
interaction commands and `passed: true`. Page one and page two each displayed
50 action rows. Searching `models.prepare` returned the two preparation routes.
The excluded standalone-control filter showed `key`, `preview` and `status`
with their fixed reasons. The five delegated routes were visible, and inspecting
the delegated control source showed 167 actions/fixed variants. The unmeasured
filter produced the expected empty state.

The metadata asset was absent initially and loaded once after explicit format
inspection. Recorded `localStorage` key counts stayed at zero. No report or
foreign-origin request was observed, and privacy-status refresh cleared the
preview without activating collection. The console had zero warnings and
errors. The browser closed; `browser-cleanup.json` records the expected server
SIGTERM exit 143 and verifies that its listener was absent.

`browser-assets.json` binds the 503 compiled files used by this journey to base
source `93eb300170d0755bf6b8156281419126ef91a25b`, with the new action-preview
code present and **package 4.46.19 metadata before 4.46.20 preparation**. These
were changed compiled assets, not an unchanged frozen 4.46.19 bundle or an
installed 4.46.20 package. The receipt qualifies the recorded browser behavior;
it does not qualify all interfaces, sensors, installed/native behavior or
production collection.

Full installed/native, resource, sensor, privacy, useful-output and production
acceptance remain open. Refer to the maintained
[release status](../RELEASE_STATUS.md) for release availability.
