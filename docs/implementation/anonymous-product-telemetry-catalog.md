# Anonymous product telemetry catalog — V08

**Building/source implementation, 26 October 2026.** This supplements the
[V08 contract](anonymous-product-telemetry.md). Catalog version 1 defines **94
workflows in 15 families**, four invocation surfaces, 11 workflow metrics and
four separate resource metrics. Python and TypeScript encoders, bounded native
and browser queues, revision/generation fencing, local controls and exact manual
report review are implemented. Source owners cover `mnemion-control call`, selected
desktop/native-operator actions, Studio clients, browser connection/legacy UI,
explicitly configured local stdio, fresh local source/capture work and automatic
desktop updater cycles, plus explicit local model preparation. Shared budgets,
opportunistic delivery owners, senders,
collector and publisher components also exist; their scoped evidence does not
establish production qualification. **Collection remains unavailable; destination
and release route address are null.** No production product analytics is active.
All 66 requirement texts and the other 65 states remain unchanged; V08 stays Building.

The [generated source-coverage inventory](../../mnemion/product_telemetry/workflow-coverage.json)
now makes all 94 categories visible in app/browser and native format inspection:
87 have mapped source boundaries and seven remain unmeasured. It is generated
from these maps and verified by the release checker. This reconciles catalog
references without claiming complete per-action, sensor or installed coverage;
the [initial coverage report](../validation/2026-10-26-telemetry-coverage.md)
preserves its 86-mapped/eight-unmeasured checkpoint. The
[action-owner follow-up](../validation/2026-10-26-telemetry-action-coverage.md)
records the later preparation boundary and remaining gaps.

The [current action inventory](../validation/2026-10-26-workspace-telemetry-ownership.md)
lists **622 actions and fixed variants: 348 mapped, 267 excluded,
seven delegated and zero unmeasured among the represented declarations**. The
[action generator](../../deploy/telemetry_actions.py) independently reads the
control contract, native action declarations, SDK class methods, legacy API
declarations and desktop preload request channels before applying the reviewed
maps. These are five interfaces. Other owners use source-route
maps and do not gain independent call-site proof. A newly declared interface
action without a mapping appears as unmeasured even if its category has another
owner. Fixed exclusion reasons and delegation are visible separately; none of
these rows authorizes collection or represents activity history.

Eight earlier evaluated observations and retained commands from actual Chrome
verify the action view on changed compiled assets based on `93eb300`, using package
4.46.19 metadata before 4.46.20 preparation. Pagination, search, exclusions,
delegation and refresh clearing passed with empty browser storage and no
observed report or foreign requests. This evidence precedes the 4.46.22 additions
and does not qualify installed/native or production behavior; the
[action-preview report](../validation/2026-10-26-telemetry-action-preview.md)
retains the exact asset binding and cleanup receipt.

Current [wire v2 and report v3](../validation/2026-10-26-telemetry-review-selection.md)
retain a four-byte body and 23 permitted views. Automatic packets use the
randomized encoder. Manually reviewed packets use a constant body for the first
permitted view, coordinate zero and flags `2`, with no category data or random
draw. They contribute only to the coarse closed-week global volume range;
categorical estimates, counts and precision use automatic reports exclusively.
The thresholds remain 64 total reports per window and 4,096 automatic reports per
view. No separate manual count is published. Legacy wire v1 is rejected; immutable
aggregate reports v1/v2 remain readable. Manual review has no general categorical
privacy-loss claim, and neither mode establishes participation or network anonymity.

The [published 4.46.13 control qualification](../validation/2026-10-26-44613-native-acceptance.md)
passed all six native targets. It does not qualify these later review, storage or
wire changes. The failed 4.46.14 Windows ARM fixture remains recorded in the
selection report; the later 4.46.15 failures and 4.46.17 source corrections are
retained in the [release-guard report](../validation/2026-10-26-telemetry-release-guards.md).
Use [release status](../RELEASE_STATUS.md) for current availability. Full ownership
coverage, installed production delivery, resource/wire limits, utility and
anonymity acceptance remain open.

## Earlier component checkpoints — 24–25 October 2026

The original [delivery components](anonymous-product-telemetry-delivery.md)
defined the earlier four-byte randomized wire format, weekly aggregation and a
bounded private publisher. Their [24 October validation](../validation/2026-10-24-telemetry-delivery.md)
included publisher checks and a 12-check actual plain-loopback HTTP journey.
Those receipts preceded shared delivery budgets and application-owner integration;
they did not qualify TLS/provider logging, deployed ingress or useful fine-grained
statistics in small populations.
The later [Python TLS component](../validation/2026-10-24-telemetry-transport.md)
has passing source and isolated loopback checks for transport and handoff ownership.
That checkpoint preceded application-owner wiring and selected no endpoint. Its
component results remain separate from the earlier evidence; charged TLS bytes
do not establish total TCP/IP wire cost or public-ingress qualification.
The subsequent [native and browser transport checkpoint](../validation/2026-10-24-telemetry-client-transports.md)
records **32 actual Electron passes with two Windows-only skips**, **65 browser
source passes**, a final native build and corrected frontend type checks. Earlier
results and failures remain preserved. Actual loopback TLS/collector journeys
passed **22 browser checks and 18 native checks**, with verified cleanup.
Both new senders claim the
whole attempt; those receipts preceded the current application-owner wiring. Browser Fetch does not
inherit the native static-header, no-DNS/proxy or charged-TLS-byte controls.
Its listeners are armed before Fetch while lock polling waits for handoff
release; it requires status 204 and `Content-Length: 0` without reading the body.

The [24 October application-owner batch](../validation/2026-10-24-telemetry-app-owners.md)
connected committed local observations to opportunistic desktop/browser
delivery and a registered Python service or maintained local stdio loop. Its
source checks and **19-assertion Chromium owner fixture** passed; CPU admission
was synthetic, with real heap readings and normal browser networking.
Connection mode and resource gauges gate an attempt; they add no catalog metric,
network identity or server recounting. That checkpoint used SQLite storage
version 5/browser choice version 4; both retained the spent allowance, and a stale
opt-out preserved a newer connection choice. Production collection and the
release route remain disabled.

The later [browser company-policy refresh](../validation/2026-10-24-telemetry-company-refresh.md)
checks fresh restrictions before an already-reserved report, then intersects
them with that page's earlier restrictions. This is delivery admission, not a
catalog workflow or a second measurement of the original action. It adds no
account lookup, analytics identifier or server recounting. Focused checks passed;
the **25 October Chromium journey passed 20 assertions**, with seven policy reads
and one report, synthetic CPU admission and verified fixture cleanup. These
component results do not establish production privacy or platform acceptance.

The earlier [privacy controls](../guides/product-telemetry-controls.md) retain
their dated evidence: the 19-check core browser journey and eight further
browser policy/fault checks passed, and
[source-input qualification](../validation/2026-10-24-telemetry-controls.md) passed
at **01:12:30 UTC**. That checkpoint does not qualify this later aggregate batch.
Both remain excluded from the isolated 4.46.6 dependency-security release.
The later [catalog/aggregate source checks](../validation/2026-10-24-telemetry-aggregates.md)
record the 28 Python, 11 browser/codec and 12 bridge checks, builds and nine-check
built-browser catalog journey. They do not qualify workflow instrumentation or
active collection.
The subsequent local-generation correction passed **29 Python and 12
browser/codec checks** plus both builds; its original test-placement failure is
retained in the same validation report.
The actual built-Chromium generation journey subsequently passed **11 checks**,
including stale UI fencing, legacy opt-out and a 390-pixel layout. Its original
pre-open runner failure and verified fixture cleanup remain recorded separately.
The later native-store follow-up retains the preliminary checks, then records
**24 Studio/browser checks, six desktop source guards and 11 actual Windows
checks with zero skips**. A copied built-Chromium fixture passed **19 checks**
for owned search and opt-out; only that fixture enabled local counters. The final
combined Electron 44.9.3 selection passed **27 with two Windows-only skips** and
its build passed; the earlier eight-pass/one-skip store run remains historical.
These results do not establish packaged-app or all-six-native acceptance.
The following browser/legacy UI and local stdio batch passed **20 Python MCP and
30 UI checks**, a corrected TypeScript/Vite build, a **14-check built-Chromium
fixture journey** and a **22-check real stdio journey**. The initial 19-test run
and failed build remain recorded. These isolated fixtures do not activate source
collection or establish release/resource acceptance.
The 24 October maintenance checkpoint records separate **41- and 49-test Python
passes**, **104 source-controller and 20 updater Node passes**, and **nine
Electron store passes with two Windows skips**. Its original runner failures are
retained. Its corrected isolated app-main probe completed; final builds/input
inventory, integration and CI were pending at that checkpoint. Those historical
limits do not mean maintenance owners are absent from current source. Later
[source checks and builds](../validation/2026-10-26-telemetry-review-selection.md)
also passed, without establishing installed production delivery or full resource acceptance.

The scope remains all app, agent and headless workflows. An unresolved row is
unfinished V08 coverage, not permission to collect without choice or an assertion
that client-only instrumentation completes “Full telemetry.”

## Implemented local schema and limits

The [versioned catalog](../../mnemion/product_telemetry/catalog.json) supplies
fixed workflow, surface, outcome, reason and metric enums to the
[Python encoder](../../mnemion/product_telemetry/catalog.py) and
[TypeScript encoder](../../studio/electron/telemetry-catalog.ts). They turn
approved numeric primitives into fixed numeric cell coordinates; those numbers
describe catalog positions, not people, devices or records. Unknown fields,
arbitrary objects, booleans, negative/non-finite numbers and values above
`2^53 - 1` are rejected. Only metrics allowed for that workflow family pass.
The encoder validates input shape; it does not establish the caller's consent
or ownership. The owned CLI, desktop and Studio boundaries enforce their explicit
maps below; further hooks need the same ownership review.

The [Python aggregate store](../../mnemion/product_telemetry/aggregate.py) and
Electron's [NativeTelemetryStore](../../studio/electron/telemetry-store.ts) use
the same private [SQLite policy store](../../mnemion/product_telemetry/policy.py).
The [browser aggregate store](../../studio/frontend/src/workspace/telemetry-aggregate.ts)
uses bounded local storage under the [browser privacy policy](../../studio/frontend/src/workspace/telemetry-policy.ts).
Current state formats are native/Python SQLite version 6, browser choice version 5
and browser budget version 2; their fences prevent older senders from bypassing
manual review. These are separate from catalog version 1 and wire version 2.
Both reject recording before storage access while collection is unavailable.
When permitted, they recheck current choice, disclosure, company groups and the
`revision`/`store_generation` pair captured by the originating work. Recreating
a deleted store assigns a new private generation, so old work cannot add data
or clear the new queue even if revision numbers repeat. Enabling a preference
also checks the pair; an explicit opt-out still wins over stale input. Busy
native writes and unavailable browser Web Locks drop the observation without
waiting or failing memory work.

Python's `record_many` now commits a workflow's submission/outcome pair in one
current-policy transaction. The native writer reuses prepared statements and
the occupied-cell set within that transaction, without retaining a connection,
statements or policy afterward. Individual contribution and capacity limits
still apply; one transaction does not promise that both observations are admitted.

Electron reads and writes the existing database through `node:sqlite`; it does
not initialize a replacement store or spawn Python for each observation. Explicit
privacy controls still use the native Python policy. On Windows, Python creates
private settings only during an explicit supported choice and verifies existing
permissions before use. Electron uses a small
[read-only owner/DACL helper](../../studio/electron/native/telemetry-private-store.c),
[compiled with MSVC](../../studio/electron/scripts/build-telemetry-private-store.ps1).
The [helper wrapper](../../studio/electron/telemetry-private-store.ts) has a
one-second deadline and no settings-repair behavior. Both runtimes reject
publicly readable, linked or otherwise unsafe stores. POSIX uses owner/mode
checks. These are source implementations, not cross-platform release acceptance.

The later [storage-ownership correction](../validation/2026-10-26-telemetry-storage-slot.md)
takes one process-wide, nonwaiting slot before asynchronous native permission or
SQLite work and releases it only after the database actually closes. Competing
optional samples are dropped; cross-process SQLite and current-policy fences
remain in force. The Windows helper wrapper retains its one child until actual
exit, including after a deadline or live-process error, and never borrows another
path's approval. This limits concurrent ownership; it is not a measured RSS bound.

`store_generation` is a private random token for local compare-and-set control.
It appears in private status and is supplied as `expected_generation`; it is
never an analytics identity, measurement cell or outbound field. Reading a
missing or supported legacy store does not silently create a token. Explicit
legacy opt-out stays off; a generation-less enabled preference requires fresh
disclosure before collection. An explicit supported choice creates/migrates the
local generation and clears old pending data. Damaged settings still fail closed.

| Local source bound | Behavior |
| --- | --- |
| Native storage | At most 512 pending cells and 512 contribution counters; the SQLite database is capped at 96 KiB with delete-mode journaling. This is not a measured total-process RAM bound. |
| Browser storage | At most 512 cells and 512 contribution counters, 131,072 string characters and 256 KiB encoded for the pending document. Invalid or oversized storage fails closed. |
| Workflow contributions | At most 64 observations per workflow/surface per day; a submission and its observed outcome consume separate contributions. |
| Resource contributions | At most 24 observations per resource metric per day. These are local scope limits, not counts of unique contributors. |
| Cells and counts | At most 16 cells per observation; each cell's daily count saturates at 255. New cells are dropped when the queue is full. |
| Age and clock changes | Only today's and yesterday's cells are eligible. Aggregation removes expired or future-dated cells; preview omits them. There is no active background expiry service. |

Successful preference changes clear aggregates and contribution counters. These
local limits are not an irreversible global privacy budget across choice changes
or installations. The 48-hour age rule is eligibility/pruning behavior; idle
physical deletion at a deadline is not established. The full contract's CPU,
RAM, wire, sampling and collector requirements still need acceptance evidence.
An exploratory Electron component run grew RSS by **3,784,704 bytes (3.61 MiB)**
after 32 workflows, exceeding the contract's unchanged **2 MiB** added-RAM target.
This is an unresolved optimization/qualification result, not a resource pass;
whole-app and all-platform resource qualification remain open.
A later phase diagnostic measured **3,424,256 bytes (3.27 MiB)** total added RSS,
including a 1,802,240-byte rise around the first SQLite snapshot/load. It is a
separate component observation, not a replacement for the earlier result or
proof that the 2 MiB target has been met.
After transaction reuse, a further component diagnostic recorded **3,235,840
bytes (3.09 MiB)** added RSS. It also remains above 2 MiB and does not replace the
earlier measurements or establish whole-app/all-platform resource acceptance.
A corrected headless main-process probe after actual app `client-ready` bootstrap
recorded **1,249,280 bytes (1.19 MiB)** added RSS over 32 paired workflows. This
narrow activation diagnostic does not replace the cold 3.61/3.27/3.09 MiB results
or establish whole-app, all-platform or CPU acceptance against the unchanged target.
The later [fixed six-case compiled-app attribution](../validation/2026-10-26-telemetry-attribution.md)
observed enabled matched main-process maxima of **3,608,576 and 3,391,488 bytes**
above their unavailable baselines, still above 2 MiB. All outcomes remain retained;
overlapping initialization windows do not attribute the whole difference to SQLite.
The [storage follow-up](../validation/2026-10-26-telemetry-storage-followup.md)
subsequently completed all six journeys on 26 October, matching **1,998 source
files per variant**. Enabled matched main-process maxima of **3,121,152 and
3,235,840 bytes** and endings of **2,125,824 and 2,207,744 bytes** remain above
2 MiB. All opted-out, renderer and GPU variation is retained. The result does not
establish a causal improvement or resource acceptance; the next step is an
explicit architecture review, without another benchmark or budget revision.
Deletion/recreation now has source generation-fencing checks. This does not
protect against an unobservable whole-machine snapshot rollback that restores
the old token and choice together. The full product delivery path must still prove
cancellation of queued/in-flight work at opt-out; the new Python, native and
browser application-owner source checks do not establish all-platform or full
resource/privacy acceptance.

`schema` and `preview` expose `measurement_catalog`, including the exclusions.
Preview can describe valid local cells without raw inputs or local day numbers;
it is not an event history or a serialized outbound report. In the current
unavailable state, `local_aggregates` is empty, `outbound_body` is null,
`outbound_bytes` is zero and `transport_available` is false.
The read-only format preview separately shows a fixed synthetic wire-v2 example
(`AgAHAA==`), explicitly marked `synthetic_example` and `not_inspected`. It is not
the next packet. Explicit manual inspection stages exact bytes only after
authorized observations exist; see the [review controls](../guides/product-telemetry-controls.md).
Local `schema` also exposes `transport_catalog`. Source delivery owners already
connect eligible queues to encoding and shared reservations; reading schema or
preview neither reserves a packet nor enables transport.

## Owned headless control coverage

The [control-origin map](../../mnemion/product_telemetry/control-origins.json)
covers all **161 operations** in the API control contract: **82 map to optional
owned measurements and 79 are excluded**. These counts describe API operations;
they map into the separate 94-workflow catalog above. The owner is specifically
[`mnemion-control call`](../../mnemion/control_cli.py), with surface `headless`.
Generic SDK calls, direct `agent_control.execute` calls and remote MCP requests
do not acquire a measurement owner. Native privacy `schema` now exposes the
complete map as `owned_control_coverage` through
[`control_specification()`](../../mnemion/product_telemetry/catalog.py).

| Fixed operation exclusion | Count | Reason |
| --- | --- | --- |
| `state_inspection` | 60 | Discovery, configuration reads, polling and inspection of earlier outcomes are not new uses. |
| `producer_transport` | 6 | Capture/source transport substeps belong to their originating producer. |
| `configuration_preview` | 5 | Preview and intermediate authorization steps do not establish completed setup, import or sign-in. |
| `recovery_transport` | 7 | Chunks and continuation/status calls belong to the enclosing recovery workflow. |
| `session_maintenance` | 1 | Credential refresh is not a new sign-in. |

Two operations select only reviewed enums: `librarian.decide` reads `body.action`
and maps `accept`, `reject`, `undo` to the corresponding librarian workflow.
`embedding.control` reads `parameters.action`: `pause` maps to `models.pause`,
`resume`/`retry` to `models.resume`, `cancel` to `models.cancel`, and `activate`
to `models.configure`. Unknown selectors produce no measurement. Other request
fields, event/result objects, names and private values never enter the encoder.

The [CLI adapter](../../mnemion/control_measurement.py) supplies only fixed
outcomes/reasons and permitted numeric response-body byte counts to the
[workflow boundary](../../mnemion/product_telemetry/workflow.py). That boundary
captures the disclosed local generation/revision once, measures monotonic
duration and rechecks policy when recording. Optional measurement errors cannot
change the ordinary call's result. Unavailable collection returns before local
policy/queue access, so these hooks remain inactive in this build.

For the ten mapped keyed-write operations, a successful response contributes
only with **`X-Mnemion-Idempotency: new`**. Cached `replayed`, legacy/missing or
unknown receipts discard both submission and outcome contributions; telemetry
does not retry a mutation to obtain a fresh receipt. The
[request-local server metadata](../../mnemion/service/request_replay.py) follows
existing receipt lookup, and [agent-control metadata](../../mnemion/agent_control.py)
accepts only `new`/`replayed`. This change needs no database migration and makes
the server no measurement owner for the caller's traffic. Its separate local
delivery-loop wiring does not change that boundary. Asynchronous acknowledgements are `accepted`,
with no server completion backfill. Internal retries remain one logical call;
response-body bytes are application payload, not wire bytes.

The [source follow-up](../validation/2026-10-24-telemetry-aggregates.md) preserves
the initial schema-reference test failure and the corrected focused pass.
Remaining surfaces, resource/privacy measurements and release acceptance remain open.

## Owned desktop, native-operator and Studio coverage

These hooks are implemented in source and remain inactive under the unavailable
collection contract. Their maps describe eligible boundaries, not proof that all
94 catalog workflows have producers or that an installed app collects data.

| Boundary | Current source ownership |
| --- | --- |
| Desktop and native operator | The [desktop-origin map](../../mnemion/product_telemetry/desktop-origins.json) contains **77 top-level operations: 44 eligible and 33 excluded**. The eligible `host.request` entry separately classifies nine typed mutations and four read exclusions. The [dispatcher](../../studio/electron/service-bridge.ts) measures selected local IPC actions as `desktop` and fresh operator execution as `native_agent`. |
| Desktop preload requests | The same map's `ipc` section classifies **72 actual preload request channels**, including fixed `hosts:action` and `sources:control` variants. The runtime dispatcher and action inventory read these reviewed mappings; inspection, privacy, transport and automatic connection exclusions remain visible. The 4.46.22 source follow-up passed 54 distinct Python and 26 Node tests plus both source builds. |
| Studio UI | The [Studio method map](../../mnemion/product_telemetry/studio-methods.json) selects **64 methods** and explicitly excludes **66**. The [Studio-only wrapper](../../studio/frontend/src/workspace/measured-client.ts), installed at connection/sign-in creation, reuses the reviewed control-origin workflows and fixed selectors. Browser sessions use their origin's policy; desktop sessions use the OS-account store. |
| Reusable SDK | The [TypeScript client](../../packages/client/src/index.ts) weakly associates exact response/error objects with `new` or `replayed` receipt metadata. It adds no owner hook, persistent identifier or telemetry collection. Generic requests and other SDK consumers remain unmeasured. |

The [workspace ownership follow-up](../validation/2026-10-26-workspace-telemetry-ownership.md)
excludes automatic `workspaces:resume` before telemetry policy/observation access:
Connect invokes it automatically and it can return an already active session.
Explicit `workspaces:restore` remains owned as `workspace.open`; explicit
`workspaces:reset` now owns one `workspace.forget` acknowledgement. Workspace
changes use their chosen connect, sign-in or open boundary, with no additional
synthetic switch. `workspace.switch` remains an unmeasured catalog category;
the taxonomy does not create an extra observation owner.

Compiled workspace fixtures verified zero policy reads/observations for automatic
resume and one workflow for each tested explicit control, without identity in
cells. They use a synthetic cipher and local stubs, not installed Electron or a
real provider. Catalog, wire-v2, disclosure and route bytes remain unchanged;
release preparation passed, while native and production qualification remain
pending. The Python total includes one real HTTP/PostgreSQL regression after a
test-only correction for the intentionally transient capture count. The linked
report retains the original 4.46.21 Python 3.13 equality-assertion failure; the
correction preserves exact equality of all other fields and changes no runtime.

The top-level desktop exclusions are 15 state inspections, six configuration
previews, nine privacy controls and three recovery transports. Typed
[`host.request` ownership](../validation/2026-10-26-telemetry-host-requests.md)
now requires a successful authenticated reply whose request-scoped
`result.request_disposition` is `new`. The receiver derives `new`/`replayed`
inside the authority transaction, without changing the protocol-v1 outer
envelope or stored operation. Legacy/missing, replayed, refused, lost and
unrecognized replies contribute nothing. The four typed reads (`host.status`,
`operations.get`, `operations.list`, `operators.list`) are excluded.
All nine selected mutations record an **accepted intake**, with no inference of
queued work's terminal success or later server recounting. Only the fixed action
selects the workflow; host identities, request bodies and result objects never
enter the numeric encoder. These mappings are not nine newly qualified workflows.
The source follow-up passed 47 Python and 17 Node checks plus its Electron build;
it is excluded from frozen 4.46.15 and does not establish installed/platform,
resource or privacy acceptance. Collection remains unavailable.
The [operator's cached reply](../../studio/electron/desktop-operator.ts) returns
before execution and adds no new measurement. Studio excludes 55 automatic
queries, four transport helpers, three configuration previews, three continuation
transports and its generic request method. Polling, privacy controls and unowned
continuations do not become workflow use.

The shared [TypeScript workflow boundary](../../studio/electron/telemetry-workflow.ts)
captures the private generation/revision, finishes at most once and submits fixed
submission/outcome primitives together. Native and browser writers copy the
stamp and validate primitives before yielding, then recheck policy in their
serialized write. Each observation still consumes its own contribution allowance;
batching does not guarantee both observations survive a full queue or exhausted cap.
The trusted renderer bridge accepts only a paired `desktop` workflow; it cannot
claim `native_agent` ownership or submit resource samples. Optional snapshots
have a short wait budget, and measurement failures do not change the action's
result.

Keyed Studio writes require `X-Mnemion-Idempotency: new`; replayed, missing or
uncertain receipts are discarded without repeating the effect. Async replies
remain `accepted`. Only reviewed primitive selectors, fixed outcomes/reasons,
duration and narrowly allowed numeric sensors reach the encoder. Exceptions,
request/result objects, vault values and private labels never enter it. Observed
payload lengths are not wire-byte measurements. Native and Studio wrappers do
not instrument nested SDK/transport calls or backfill server completion.
The Studio method wrapper does not own enclosing connection/sign-in workflows
merely because it is constructed there. The following source additions provide
explicit owners. The maintenance section below covers selected fresh local work;
it does not authorize server jobs or complete all background ownership.

## Browser connection, legacy UI and local stdio coverage

The [UI-origin map](../../mnemion/product_telemetry/ui-origins.json) and
[MCP-origin map](../../mnemion/product_telemetry/mcp-origins.json) supplement the
unchanged 94-workflow catalog. They classify eligible source paths, not deployed
collection or completed all-platform coverage.

| Boundary | Source mapping |
| --- | --- |
| Browser connection controls | Five explicit actions: connect, sign in, open, disconnect and forget. The [UI action wrapper](../../studio/frontend/src/workspace/measurement-action.ts) skips desktop connections already owned by IPC. |
| Legacy Studio client | All 29 methods are classified: 11 selected, 17 automatic-query exclusions and one external-application handoff exclusion. The [legacy client](../../studio/frontend/src/api/client.ts) wraps only the selected methods. |
| Maintained local stdio gateway | 29 classified paths, including two compatibility path labels: 18 direct workflow mappings, two control dispatch paths and nine exclusions. This is not a claim of 29 separately exposed tools. |
| Legacy local stdio loop | All 48 tools are classified: 33 selected and 15 excluded, including the privacy control itself. Imported handlers have no implicit owner. |

Browser/legacy UI measurement keeps inputs and results inside the original
callback. Company sign-in cancellation uses the abort signal, not exception
text. Only a mapped boolean result flag distinguishes success/failure where
required; an unfamiliar flag discards the measurement. Automatic route queries,
credential rotation/previews and external-app handoffs add no use. The same
generation/revision checks and optional no-throw behavior still apply.

The [MCP adapter](../../mnemion/mcp_measurement.py) is called only by an explicitly
configured local stdio runtime under its disclosed OS-account policy. The
[maintained gateway](../../mnemion/service/mcp.py) distinguishes stdio from HTTP
request context; a process-wide stdio key never authorizes HTTP telemetry. The
[legacy loop](../../mnemion/mcp_server.py) marks its own local dispatch explicitly;
an imported handler or caller-supplied JSON field cannot acquire ownership.
Aliases delegate to one inner owner, and `mnemion_read`/`mnemion_write` reuse the
reviewed control-origin map. Keyed writes require the fixed fresh-receipt marker;
cached or unknown receipts add nothing. SDK callbacks observe only the bounded
`new`/`replayed` disposition for that tool's client and are removed afterward.
They do not turn the reusable SDK or server into another measurement owner.

The local `mnemion_telemetry` tool exposes offline `status`, `schema`, `preview`,
`configure` and the explicit `review_status`, `review_mode`, `inspect_report`,
`approve_report` and `discard_report` controls under the same private policy. It is
absent from the ordinary HTTP gateway, and HTTP calls are refused even on a
server configured with a stdio key. Privacy controls themselves never produce
measurements. See the [local-tool guide](../guides/product-telemetry-controls.md#from-local-stdio-mcp).
Local `schema` now also returns `owned_origin_coverage` with the `desktop`,
`studio`, `ui`, `mcp` and later `maintenance` maps, while retaining the CLI's
`owned_control_coverage`.
An optional observer import failure falls back to exactly one original action;
the fallback does not retry an action that already ran.
The collection gate remains false and the destination null. The earlier isolated
stdio/browser receipts covered their recorded source boundaries; they did not
establish later integration. Current source includes these owners, but anonymous
ingress, complete ownership coverage, resource limits and installed production
delivery still require acceptance.

## Fresh local maintenance coverage

The [maintenance-origin map](../../mnemion/product_telemetry/maintenance-origins.json)
is the fifth schema map: **six source/updater origins, 13 capture-control
classifications, two preparation kinds, five sensor descriptions and 13
exclusions**. These are selected local owners under the same disclosure,
generation/revision and company policy; collection is still unavailable. Existing
[desktop](../../studio/electron/telemetry-activity.ts) and
[Python service/stdio](../../mnemion/product_telemetry/activity.py) lifetimes can
offer eligible committed observations to delivery. They add no telemetry daemon,
CLI keepalive or new measurement owner for nested work.

| Fresh owner | Observed boundary and limits |
| --- | --- |
| Desktop scheduled source/capture | [DesktopSources](../../studio/electron/desktop-sources.ts) starts an observer only for automatic work. Explicit Sync continuations already have a request owner. Successful empty scans, paused work and mere status inspection add no use. |
| Standalone source/capture | The [connector entrypoint](../../mnemion/connectors/runner.py) owns its fresh local execution. Reusable sync calls, remote-requested work and host-managed child processes do not inherit this owner. |
| Standalone capture controls | The [connector entrypoint](../../mnemion/connectors/runner.py) separately observes ten eligible actions; status, preview and key generation are excluded. Managed/reporting children and reusable control helpers acquire no owner. |
| Explicit model preparation | The [service CLI](../../mnemion/service/cli.py) owns direct `prepare-model` and `librarian-models --prepare` invocations as `models.prepare`. The observer receives only `embedding` or `librarian_tokenizer`; model/profile identifiers and normal output remain outside telemetry. |
| Desktop update download | The [updater](../../studio/electron/updates.ts) keeps download, verification and bounded retries in one cycle with one terminal success, failure or cancellation. Current-version and safe-restart polls add no use. Unfinished cycles are discarded on quit. |
| Installer handoff | `update.apply` records only an **accepted handoff**, if observed. Its optional snapshot has a 25 ms wait budget before the original guarded action. It does not assert an installed version or completed restart, and there is no shutdown flush or wait for telemetry. |

The [preparation adapter](../../mnemion/maintenance_measurement.py) records only
the permitted workflow, bounded timing and fixed outcomes/reasons. Both automatic
[deployment/startup calls](../../mnemion/service/deployment.py) explicitly set
`preparation_owner=False`; listing and registry helpers acquire no owner.
Preparation resource/sensor qualification remains open. Source ownership does
not authorize model downloads or inference for telemetry.

The [native](../../studio/electron/maintenance-measurement.ts) and
[headless](../../mnemion/maintenance_measurement.py) source adapters extract only
reviewed numeric changed/accepted/pending counts and local capture-store size,
plus fixed outcome/reason values from fresh work. They do not export saved scan
history, source identifiers, paths, content or raw errors. Existing native
request acknowledgements remain separate workflow categories; they cannot be
summed with observed maintenance outcomes as independent uses.

The [4.46.21 capture-delivery follow-up](../validation/2026-10-26-capture-delivery-telemetry.md)
adds `capture` to the existing `result_items` allowed families, retaining its
bucket coordinates and wire views. Native/headless adapters use only verified
fresh stored-event counts from the current delivery call, excluding duplicate
and fenced events. `remote_committed_events` can include receipt reconciliation
and repeated items, so it is not the fresh metric. This adds no metric, packet,
sampled view or second `capture.deliver` owner. Earlier reports retain their
then-current exclusion of capture from `result_items`.

The shared cycle preserves acknowledged partial progress after later failures;
uncertain POSTs leave the fresh total unknown. Replay/readback-only completed
cycles add no fresh use. Receipt bodies stay separate from the existing
`X-Mnemion-Idempotency` header and new `X-Mnemion-Capture-Stored` header, whose
fresh count is bounded to 50 events per page. Optional SDK `RequestReceipt`
metadata is per call and adds no owner. Live `newly_stored_events` is excluded
from `CaptureReport` serialization and saved source history. The scoped source
validation passed 172 distinct Python and 111 Node controller/wire cases and
both source builds; original fixture failures remain recorded. Category coverage
stays 94 total, 87 mapped and seven unmeasured; installed and full V08 acceptance
remain separate.

Resource cells describe only the owned process. Native source work can use the
maximum RSS supplied by its actual child callback and that worker's configured
limit; no callback sample means unavailable. Headless work uses its own ending
RSS and CPU-time delta over the work interval, with its configured capture limit
when measured. These are coarse buckets, not host totals, continuous monitoring,
or proof of the telemetry component's overhead. Service-worker activity and
mixed-host CPU/RAM stay excluded. Every resource write retains the originating
policy fence; resource samples and the workflow pair are separate bounded writes.

## Measurement ownership

Count a logical workflow at one disclosed origin. A fixed surface enum describes
how it was invoked; it is not a user, installation or request identifier.

| Surface | Owner and source implementation boundary | Remote and nested work |
| --- | --- | --- |
| Desktop workspace UI | Selected [local IPC actions](../../studio/electron/desktop-measurement.ts) and the [Studio client wrapper](../../studio/frontend/src/workspace/measured-client.ts), under the shared installation policy. Collection is inactive under the current release gate. | [Native fetch](../../studio/frontend/src/workspace/native.ts), transport retries and the remote API add no second usage count. |
| Browser workspace UI | The Studio wrapper plus explicit [connection actions](../../studio/frontend/src/workspace/measurement-action.ts), under browser-local disclosure, choice, GPC and company restrictions. | Desktop connections skip the browser owner because IPC already owns them. Authentication is not product telemetry consent. The source sender omits credentials and referrer; production ingress and browser transport metadata still need qualification. |
| Legacy Studio UI | Selected methods of the [legacy client](../../studio/frontend/src/api/client.ts), using the same app/browser policy and explicit UI-origin map. | Automatic queries and external-app handoffs are excluded; callbacks retain private inputs/results. |
| Native agent controlling the desktop | Fresh mapped execution at the [desktop dispatcher](../../studio/electron/service-bridge.ts), with the fixed `native_agent` surface and the same private OS-account store. | The agent pipe, cached reply and renderer do not add another measurement. No operation UUID enters telemetry. Typed host mutations require a verified new intake; replayed, readback and legacy replies remain unmeasured. |
| Owned `mnemion-control call` | Source hook at the [CLI boundary](../../mnemion/control_cli.py), under the shared local policy and explicit operation map above; collection remains inactive. | The reusable SDK and `agent_control.execute` carry no owner hook. Nested requests, retry attempts and cached receipts do not add uses. |
| Local stdio-MCP | Explicit source owner at the [maintained gateway](../../mnemion/service/mcp.py) or [legacy stdio loop](../../mnemion/mcp_server.py), under local OS-account policy. | HTTP context, imported handlers and JSON arguments cannot acquire this owner. Aliases and nested SDK calls do not add another count. Other headless entrypoints still need review. |
| Third-party remote MCP or direct API client | **Excluded without a disclosed local owner.** The [remote MCP gateway](../../mnemion/service/mcp_transport.py#L441) creates the ordinary [Python SDK Client](../../mnemion/sdk.py#L614); that shared SDK is not a measurement owner. | A token, client name, session or host-owner preference cannot stand in for the originating user's choice. Future owned adapters need their own disclosure and policy. |
| Fresh local maintenance | The selected desktop/standalone source and automatic updater owners described above, under local policy. | Empty scans, explicit Sync continuations, reusable helpers and remote/managed work do not acquire another owner. |
| Server jobs and other autonomous host work | No server export or terminal backfill for client-derived work. Other autonomous maintenance still needs a reviewed owner. | [Index/purge jobs](../../mnemion/service/worker.py#L290), saved scan history and mixed-host resource totals cannot supply a fallback feed. A `background` label does not make user-derived work autonomous. |

Version 1 declares seven privacy coverage exclusions:

| Excluded path | Required boundary |
| --- | --- |
| Unowned remote clients | No direct API/remote MCP product collection without a disclosed local owner; authentication is not telemetry consent. |
| Derived server jobs | No server recounting or completion backfill. A terminal result the origin never sees stays unobserved. |
| Mixed-host resources | No process/host totals containing other users' undisclosed activity. |
| Private operational records | No audit rows, diagnostics, evaluation cases, source histories or recovery receipts. |
| Polling and replay | No extra usage counts for automatic polling, retries, cached mutation receipts or inspecting earlier outcomes. |
| Privacy controls | No event for choice, disclosure, preview, opt-out or shutdown. |
| Unavailable sensors | Missing values stay unavailable; application payload bytes cannot stand in for wire bytes. |

These exclude product measurement under unsafe or unowned conditions; they do
not remove connectors, remote clients, background work or any of the 66 product
requirements. Full workflow coverage still needs explicit hook/owner review,
with permitted measurements or visible justified exclusions for every surface.

Future collection is enabled by default after the contract's required disclosure.
Per-installation choice does not imply an account-wide preference across other
installations. A persistent opt-out stops that installation's new collection and
emission, clears pending memory/disk aggregates, cancels retries and prevents a
shutdown flush. Every local producer and the final sender recheck effective
policy. Re-enable starts empty. Company policy may further restrict collection;
it cannot override user opt-out. Invalid or unreadable state suppresses emission.
These controls must work before sign-in, offline and through native-agent setup
and status. Already transmitted bytes cannot be recalled.

Under the originating-client boundary, services must never export a replacement
count for the client's request or its derived jobs. Thus offline opt-out does not
depend on informing a remote server. Extending measurement to those services
would require a separate private choice/revocation and pending-data-clearing
design; a new header alone would not solve queued work or offline changes.
Existing authentication identities may remain in the operational control plane,
but never enter product queues, even hashed.

## Common bounded measurements and outcomes

The implemented schema enumerates the exact workflow/surface combinations.
Arbitrary API paths, command names, labels and catch-all metadata are forbidden.
A producer may supply only selected numeric primitives and catalog enums,
never a request, result, exception, receipt or audit object. Version 1's numeric
upper edges are below; values above the last edge share the last bucket.
Exact input values are discarded by the encoder. Selected source owners have
hooks for the bounded counts, durations and resource samples described above;
the encoder does not sample those sensors. Collection remains unavailable,
and an unavailable sensor produces no observation.

| Metric | Unit and bucket upper edges |
| --- | --- |
| `latency_ms` | Monotonic milliseconds: 9, 49, 199, 999, 4,999, 29,999, 119,999, 900,000. |
| `result_items`, `work_items`, `queue_items`; resource `queue_drops` | Observed items/local discarded observations: 0, 1, 9, 99, 999, 9,999, 1,000,000. |
| `payload_bytes_sent`, `payload_bytes_received`, `stored_bytes` | Application or stored bytes: 0, 1 KiB, 16 KiB, 256 KiB, 4 MiB, 64 MiB, 1 GiB, 16 GiB. No content/file rereading merely to measure length. |
| `wire_bytes_sent`, `wire_bytes_received`, `throughput_bytes_per_second` | Measured wire bytes or measured wire bytes/second, using the same numeric edges as the byte metrics. No payload substitution for unavailable wire sensors. |
| `reported_tokens` | Model-reported tokens: 0, 1, 99, 999, 9,999, 99,999, 1,000,000; estimates are not reported usage. |
| Resource `cpu_millicores` | Process CPU milliseconds per elapsed second: 0, 1, 10, 100, 500, 1,000, 4,000, 16,000. CPU can exceed one core. |
| Resource `rss_bytes`, `resource_budget_bytes` | Process resident/configured memory bytes: 0, 64 MiB, 256 MiB, 1 GiB, 4 GiB, 16 GiB, 64 GiB, 256 GiB. |

Submission, outcome and fixed-reason cells use the same bounded daily counters.
The separate resource cells carry no workflow or surface label. Platform/release
cohorts remain unimplemented and must not become a joinable profile. Fixed
closed-week aggregation, publication and retention are implemented in source;
production collection and reporting remain unqualified. Missing sensors or
terminal outcomes produce no substitute zero/success observation. Sampling
placement and usefulness still need review.

The catalog fixes eight outcomes:

| Outcome | Meaning |
| --- | --- |
| `success` | The named boundary completed and its stated result was confirmed. |
| `accepted` | A submission was acknowledged; background completion is not implied. |
| `deferred` | Work is explicitly queued/paused or waiting on a known guard. |
| `cancelled` | Cancellation was confirmed, rather than inferred from a lost connection. |
| `denied` | The product operation was refused by its authorization or approval boundary. Telemetry opt-out itself produces no event. |
| `unsupported` | The current client/host lacks that operation. |
| `failed` | A failure was confirmed at the named boundary. |
| `unconfirmed` | The result of a submitted effect is uncertain and needs inspection. |

A separate, fixed reason enum contains `none`, `invalid_input`,
`authorization`, `conflict`, `host_busy`, `resource_pressure`, `offline`,
`network_timeout`, `readiness_timeout`, `integrity_check`,
`recovery_required` and `other_failure`. Map reviewed domain codes to these
values; do not pass through arbitrary server codes or classify by parsing raw
exception text. A timeout after submission can be `unconfirmed`; it must not
become a claim that no effect occurred. A successful/accepted outcome cannot
carry a failure reason, and `none` does not create a redundant reason cell.

Count retries, status polling, cached replays and restored receipt inspection as
neither new submissions nor new completions. An asynchronous acknowledgement
is only `accepted`. If the origin does not observe terminal completion, leave
that measurement unavailable; do not backfill it from private server histories.
The future design must settle completion ownership across process restarts
without adding an operation identifier to product telemetry.

## Workflow catalog

The 15 workflow families below expand to the 94 catalog operations; separate
resource cells are not extra workflows. The ownership maps above record the
implemented CLI, app, stdio and selected maintenance boundaries. The broader
integration points below still need full coverage qualification. Only version 1's fields are accepted today;
additional modes, quality views and sensors mentioned below remain proposals.
“Origin” means the disclosed app/agent owner above, not an arbitrary caller of
a shared SDK. Unowned host/background paths remain excluded from measurement.

| Family and fixed operation variants | Proposed measurements and exclusions | Owner and current source |
| --- | --- | --- |
| `setup`: `create`, `configure`, `agent_install`, `agent_remove` | Submissions, confirmed completions and duration of local setup or agent configuration. Exclude owner/workspace names, settings bodies and credential provisioning data. | Origin, with local setup counted at its shared controller. [LocalSetup.perform/open](../../studio/frontend/src/workspace/LocalSetup.tsx#L49), [DesktopAgentSetup.install](../../studio/frontend/src/workspace/DesktopAgentSetup.tsx#L76). |
| `workspace`: `connect`, `sign_in`, `open`, `switch`, `disconnect`, `forget` | Connection/open outcomes and latency; a fixed local/remote mode only if needed in an approved view. Exclude addresses, identity providers, account names and saved-connection IDs. | Explicit [Connect](../../studio/frontend/src/workspace/Connect.tsx) and [workspace controller](../../studio/electron/service-bridge.ts) boundaries. Automatic resume is excluded; restore owns open and reset owns a forget acknowledgement. Changing workspace adds no synthetic switch observation. |
| `memory`: `list`, `read`, `recall`, `context`, `knowledge`, `core_read` | Logical retrieval use, latency, result-count buckets and fixed empty/fallback/incomplete-index observations. Mode may be lexical/semantic/hybrid; no query, snippet, score vector, citation ID or search-filter values. | Origin; [SearchMemory.search](../../studio/frontend/src/workspace/Workspace.tsx#L1180), [Knowledge](../../studio/frontend/src/workspace/Knowledge.tsx#L17). [RetrievalService._measured](../../mnemion/service/retrieval.py#L118) is currently private operational measurement, not an export source. |
| `memory`: `save`, `revise`, `review`, `forget`, `core_write`, `import`, `export` | Submission/terminal outcomes, latency and bounded item/transfer totals. Distinguish accepted write from indexing readiness; preserve uncertain deletion outcomes. Exclude contents, review reasons, paths and idempotency keys. | Origin; [save/revise/forget UI](../../studio/frontend/src/workspace/Workspace.tsx#L753), [API write routes](../../mnemion/service/api.py#L616). Index/purge completion coverage remains open when the origin is absent. |
| `capture`: `configure`, `preview`, `collect`, `deliver`, `pause`, `drain`, `remove` | Separate local acceptance from remote delivery; bucket accepted/delivered counts, backlog, bytes and elapsed time. Fixed partial/fence/authorization reasons map into the common vocabulary. No conversation, file, device, grant or checkpoint identifiers. | Disclosed local capture owner; [shared native/headless cycle](../../mnemion/connectors/capture_cycle.py#L21), [DesktopSources](../../studio/electron/desktop-sources.ts#L362). The service must not recount accepted pages. |
| `sources`: `configure`, `scan`, `sync`, `pause`, `resume`, `repair`, `remove` | Scan/control outcomes, elapsed time and changed/removed/backlog buckets. Never export repository names, provider identities, paths, commits or per-source histories. | Origin for explicit controls; separately owned scans need local policy. [Connections](../../studio/frontend/src/workspace/Connections.tsx#L57), [runner._scan](../../mnemion/connectors/runner.py#L81), [managed status](../../mnemion/connectors/managed.py#L71). Shared-host scans remain unresolved. |
| `librarian`: `configure`, `run`, `cancel`, `accept`, `reject`, `undo` | Submission versus completion, duration, processed/skipped/proposal-count buckets and available reported-token totals. Exclude memory IDs, proposals, model/profile names and decision text. | Origin for controls; [Librarian.act](../../studio/frontend/src/workspace/Librarian.tsx#L145). [Scheduled runner](../../mnemion/service/librarian_runner.py#L81) completion and unattended work require the background ownership decision. |
| `models`: `configure`, `prepare`, `reindex`, `pause`, `resume`, `cancel` | Preparation/cache availability, downloads where measured, latency, admitted/deferred work and reported-token buckets. Use a reviewed local/remote execution class, not custom model IDs, endpoints, dimensions or exact hardware. | Origin for controls and owned local preparation; [EmbeddingModels](../../studio/frontend/src/workspace/EmbeddingModels.tsx#L33), [pinned model files](../../mnemion/service/model_files.py#L6), [ModelWorker](../../mnemion/service/model_worker.py#L25). Remote inference/background totals remain unresolved. |
| `backup`: `configure`, `create`, `list`, `verify`, `prune`; `recovery`: `inspect`, `restore`, `finish`, `discard` | Distinct submission, delivery, verified-readback and restore boundaries; duration and size buckets. Delivery includes upload/readback, and later verification downloads again. No destinations, key IDs, digests, archive names or operation IDs. | Origin through [local backup/recovery dispatch](../../studio/electron/service-bridge.ts#L650) or [HostBackups.request](../../studio/frontend/src/workspace/HostBackups.tsx#L24). [Native backup worker](../../mnemion/host_control/backup_jobs.py#L12) and [Git transfer stages](../../mnemion/host_control/backup_git.py#L263) are private evidence; remote completion ownership stays open. |
| `update`: `check`, `download`, `verify`, `apply`, `restart`, `rollback` | Confirmed stage outcomes, duration, transfer buckets and fixed restart/deadline reasons. A downloaded candidate is not an installed update; a rollback remains separate from success. Exclude exact version pairs, journal contents and idle/activity timelines. | Shared desktop updater policy: [check](../../studio/electron/updates.ts#L263), [guarded restart](../../studio/electron/updates.ts#L310). [Managed service update](../../mnemion/service/service_updates.py) requires a separately disclosed host owner and cross-restart completion qualification. Local administrator consent and private journal backfill do not supply that ownership. |
| `host`: `adopt`, `enroll`, `inspect`, `start`, `stop`, `plan_upgrade`, `resolve`, `revoke` | Typed control use and confirmed outcomes, including busy/no-effect versus uncertain effects. Backup and update operations use their own rows, not another host mutation total. Never export host/operator identity, SSH fingerprints, signed plans or service paths. | Origin at [hostAction](../../studio/electron/service-bridge.ts#L304)/[HostProfiles.request](../../studio/electron/host-profiles.ts#L268); headless typed operations map through the [host protocol](../../mnemion/host_control/protocol.py#L153). |
| `evaluation`: `create_dataset`, `run`, `cancel`, `assess`, `compare`, `export`, `remove_dataset` | Workflow use, duration and case-count buckets. Quality-metric aggregation requires a separate reviewed view and remains undecided. No questions, reference labels, dataset names/IDs, per-case results or human notes; no extra evaluations or model calls for telemetry. | Origin at [Evaluations](../../studio/frontend/src/workspace/insights/Evaluations.tsx#L178). [EvaluationRunner._case](../../mnemion/service/evaluation_runner.py#L309) invokes retrieval with evaluation origin; those calls must not inflate interactive recall usage. [Ranking metrics](../../mnemion/service/evaluation_metrics.py#L13) remain private today. |
| `journal`: `configure`, `push`, `organize`, `backfill`, `recover` | Submissions, observed completion, duration and item-count buckets. No journal entries, repository destinations, source dates or replay identifiers. | Origin at [Journal.act](../../studio/frontend/src/workspace/Journal.tsx#L47), [JournalBackfill.act](../../studio/frontend/src/workspace/JournalBackfill.tsx#L35) and [recovery client methods](../../packages/client/src/index.ts#L192); unattended publication has the same unresolved background boundary. |
| `access`: `configure`, `invite`, `grant`, `revoke`; `vault`: `configure`, `read`, `write`, `delete`, `import`, `export` | Only fixed workflow/outcome counts and duration. Exclude values and value lengths, roles, identity/provider details, key names and all audit records. | Origin at [Team actions](../../studio/frontend/src/workspace/Workspace.tsx#L1944) and [SecretsVault.run](../../studio/frontend/src/workspace/SecretsVault.tsx#L45). Necessary private security records remain independent. |
| Separate resource cells: `cpu_millicores`, `rss_bytes`, `resource_budget_bytes`, `queue_drops` | Coarse local CPU/RSS/budget and discarded-observation buckets. Wire metrics attach only to allowed workflows; pressure/expiry views remain proposals. No uptime, process IDs, exact timestamps, hardware profile or opt-out event. | Selected fresh source/capture owners now supply the limited process samples described above. A general sampler and full resource qualification remain open. [Process resources](../../mnemion/service/resources.py#L75), [memory budget](../../mnemion/service/memory_budget.py#L181) and [inference queue](../../mnemion/service/inference_limits.py#L65) remain private facilities, not export feeds. Mixed-host totals and unmeasured wire traffic are excluded. |

A named subworkflow can have its own measurement, but its counts must not be
summed with its parent's as total independent uses. Background polling is not
feature adoption. The explicit CLI, desktop and Studio maps do not finish the
remaining action-by-action coverage reconciliation or qualify their producers.
The local preview now has category and individual-action views. For its five
independently enumerated interfaces, an action without a reviewed mapping is
shown as unmeasured even when another action maps to the same category. Other
owners are represented by their reviewed source-route maps; the preview does
not prove every call site or discover all unlisted interfaces. The requirement
to make every unmapped supported action visible remains in force, and the
remaining interface/action reconciliation stays open. No unmapped action may
fall into an arbitrary “other operation” event.

## Private operational metrics and remaining decisions

Current [Telemetry.record](../../mnemion/service/telemetry.py#L101) buffers
authenticating identity, tenant/space/generation IDs and minute timestamps.
[Identity](../../mnemion/service/db.py#L27) carries authorization, not telemetry
choice. Operational histories, source reports, host receipts and evaluations
are private product features governed by their own permissions. They cannot be
forwarded, scrubbed into a fallback feed or used to reconstruct opted-out use.
V08 disablement does not disable required access, recovery or security audit.
Even numeric process totals without identity labels can include opted-out users.

The following implementation and acceptance work remains open:

- **Remote-client coverage:** the catalog excludes unowned MCP/API traffic.
  Future disclosed owned adapters need an explicit local policy boundary; any
  service-side extension would need a new choice/revocation design. A server
  owner's preference or bearer token cannot authorize another user's collection.
- **Deferred and shared-host coverage:** client-derived jobs and mixed-user
  totals remain excluded. Instrument only outcomes observed by the disclosed
  origin; define ownership before measuring autonomous librarian/source work.
  Preserve the broader connector/host requirements and visible coverage gaps.
- **Metrics and budgets:** finite buckets, local contribution caps, delivery
  owners, shared reservations, cancellation fences and manual review are
  implemented in source. The [budget design](anonymous-product-telemetry-budget.md)
  distinguishes native/Python SQLite from browser-origin coordination. Installed
  sampling and complete application-owner/delivery qualification across platforms
  remain unfinished; actual transport upper bounds are unqualified. Verify useful
  measurements and the existing queue/RAM/CPU/batch/wire ceilings under load;
  local numeric limits alone are not a privacy mechanism. Evaluation-quality
  views, cross-restart completion, end-to-end recovery boundaries and all-platform
  final-send cancellation still need review and acceptance. Local store-generation
  checks do not establish whole-machine snapshot rollback protection.
- **Anonymity and output:** substantiate ingress/provider log behavior, transient
  source-IP handling, metadata stripping and absence of retained raw events.
  Wire v2 automatic randomization has a conditional per-report `ln(3)` bound;
  report v3 categorical estimates assume conforming automatic reports and
  packet-independent inclusion, with a 4,096-automatic-report per-view gate and
  rare-cell suppression. The constant manual body carries no category and
  contributes only to the coarse global range after 64 total reports; its preview
  makes no per-report privacy-loss claim. Eight-window output retention is
  implemented, but deployment and backup-retention qualification remain open.
  Participation, composition and lifetime privacy, attack resistance, publisher
  qualification and useful statistics remain open.
  Its 4,096-report threshold cannot prove distinct contributors; a clean payload
  cannot prove network anonymity. No stable IDs may be introduced to fill these gaps.

Before launch, the contract requires actual sentinel/outbound and ingress-log
evidence, opt-out races and queue clearing across all producers, no nested SDK
or server recounting, unknown-client and deferred-job cases, resource/wire
measurements and cohort/linkage attacks. Published 4.46.13 has six-target installed
control evidence; all six targets and web still need qualification for the newer
review and full production delivery path. Source checks qualify only their
recorded boundaries; they do not establish full V08 or anonymous ingress. The
collector implementation and isolated staging evidence do not configure a
production collector or paid tooling through this catalog.
