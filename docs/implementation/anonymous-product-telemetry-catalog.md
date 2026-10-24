# Anonymous product telemetry catalog — V08

**Building/source implementation, 24 October 2026.** This supplements the
[V08 contract](anonymous-product-telemetry.md). Version 1 now defines **94
workflows in 15 families**, four invocation surfaces, 11 workflow metrics and
four separate resource metrics. Python and TypeScript encoders, bounded native
and browser queues, revision/generation checks and local preview are implemented
in source, along with owned `mnemion-control call`, selected desktop/native-operator
actions, Studio client hooks, browser connection/legacy UI actions and explicitly
configured local stdio hooks. Fresh local source/capture work and automatic desktop
updater cycles now have source owners; remaining workflow and resource/platform
qualification are unfinished. **No sender or collector is implemented.** Collection remains
unavailable and the destination is null; no product measurements are collected.
Native release, resource and anonymity acceptance remain open. All 66 requirement
texts and the other 65 states remain unchanged; V08 stays Building.

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
The following maintenance batch records separate **41- and 49-test Python
passes**, **104 source-controller and 20 updater Node passes**, and **nine
Electron store passes with two Windows skips**. Its original runner failures are
retained. The corrected isolated app-main probe completed; final builds/input
inventory, integration and CI remain pending.

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
whole-app and all-platform measurements remain open.
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
Deletion/recreation now has source generation-fencing checks. This does not
protect against an unobservable whole-machine snapshot rollback that restores
the old token and choice together. The eventual sender must still prove
cancellation of queued/in-flight work at opt-out; no sender exists yet.

`schema` and `preview` expose `measurement_catalog`, including the exclusions.
Preview can describe valid local cells without raw inputs or local day numbers;
it is not an event history or a serialized outbound report. In the current
unavailable state, `local_aggregates` is empty, `outbound_body` is null,
`outbound_bytes` is zero and `transport_available` is false.

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
the server no telemetry owner. Asynchronous acknowledgements are `accepted`,
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
| Desktop and native operator | The [desktop-origin map](../../mnemion/product_telemetry/desktop-origins.json) contains **72 operations: 43 eligible and 29 excluded**. The [dispatcher](../../studio/electron/service-bridge.ts) measures selected local IPC actions as `desktop` and fresh operator execution as `native_agent`. |
| Studio UI | The [Studio method map](../../mnemion/product_telemetry/studio-methods.json) selects **64 methods** and explicitly excludes **66**. The [Studio-only wrapper](../../studio/frontend/src/workspace/measured-client.ts), installed at connection/sign-in creation, reuses the reviewed control-origin workflows and fixed selectors. Browser sessions use their origin's policy; desktop sessions use the OS-account store. |
| Reusable SDK | The [TypeScript client](../../packages/client/src/index.ts) weakly associates exact response/error objects with `new` or `replayed` receipt metadata. It adds no owner hook, persistent identifier or telemetry collection. Generic requests and other SDK consumers remain unmeasured. |

The desktop exclusions are 15 state inspections, six configuration previews,
four privacy controls, three recovery transports and one secondary receipt owner.
In particular, generic `host.request` cannot safely claim a fresh remote effect.
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

The local `mnemion_telemetry` tool exposes offline `status`, `schema`, `preview`
and `configure`, using the existing private policy and schema version. It is
absent from the ordinary HTTP gateway, and HTTP calls are refused even on a
server configured with a stdio key. Privacy controls themselves never produce
measurements. See the [local-tool guide](../guides/product-telemetry-controls.md#from-local-stdio-mcp).
Local `schema` now also returns `owned_origin_coverage` with the `desktop`,
`studio`, `ui`, `mcp` and later `maintenance` maps, while retaining the CLI's
`owned_control_coverage`.
An optional observer import failure falls back to exactly one original action;
the fallback does not retry an action that already ran.
The collection gate remains false and the destination null. Passing source and
isolated stdio/browser checks do not establish anonymous ingress,
remaining ownership, resource limits or native release. Final source
inventory and integration are not established by these receipts.

## Fresh local maintenance coverage

The [maintenance-origin map](../../mnemion/product_telemetry/maintenance-origins.json)
adds the fifth schema map: **six origins, five sensor descriptions and nine
exclusions**. These are selected local owners under the same disclosure,
generation/revision and company policy; collection is still unavailable.

| Fresh owner | Observed boundary and limits |
| --- | --- |
| Desktop scheduled source/capture | [DesktopSources](../../studio/electron/desktop-sources.ts) starts an observer only for automatic work. Explicit Sync continuations already have a request owner. Successful empty scans, paused work and mere status inspection add no use. |
| Standalone source/capture | The [connector entrypoint](../../mnemion/connectors/runner.py) owns its fresh local execution. Reusable sync calls, remote-requested work and host-managed child processes do not inherit this owner. |
| Desktop update download | The [updater](../../studio/electron/updates.ts) keeps download, verification and bounded retries in one cycle with one terminal success, failure or cancellation. Current-version and safe-restart polls add no use. Unfinished cycles are discarded on quit. |
| Installer handoff | `update.apply` records only an **accepted handoff**, if observed. Its optional snapshot has a 25 ms wait budget before the original guarded action. It does not assert an installed version or completed restart, and there is no shutdown flush or wait for telemetry. |

The [native](../../studio/electron/maintenance-measurement.ts) and
[headless](../../mnemion/maintenance_measurement.py) source adapters extract only
reviewed numeric changed/accepted/pending counts and local capture-store size,
plus fixed outcome/reason values from fresh work. They do not export saved scan
history, source identifiers, paths, content or raw errors. Existing native
request acknowledgements remain separate workflow categories; they cannot be
summed with observed maintenance outcomes as independent uses.

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
| Desktop workspace UI | Selected [local IPC actions](../../studio/electron/desktop-measurement.ts) and the [Studio client wrapper](../../studio/frontend/src/workspace/measured-client.ts), under the shared installation policy. Both are source-only inactive hooks. | [Native fetch](../../studio/frontend/src/workspace/native.ts), transport retries and the remote API add no second usage count. |
| Browser workspace UI | The Studio wrapper plus explicit [connection actions](../../studio/frontend/src/workspace/measurement-action.ts), under browser-local disclosure, choice, GPC and company restrictions. | Desktop connections skip the browser owner because IPC already owns them. Authentication is not product telemetry consent; a future sender still needs a credential/referrer-free boundary. |
| Legacy Studio UI | Selected methods of the [legacy client](../../studio/frontend/src/api/client.ts), using the same app/browser policy and explicit UI-origin map. | Automatic queries and external-app handoffs are excluded; callbacks retain private inputs/results. |
| Native agent controlling the desktop | Fresh mapped execution at the [desktop dispatcher](../../studio/electron/service-bridge.ts), with the fixed `native_agent` surface and the same private OS-account store. | The agent pipe, cached reply and renderer do not add another measurement. No operation UUID enters telemetry; generic remote host requests remain excluded. |
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
Exact input values are discarded by the encoder, and no sensor is sampled yet.

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
cohorts and outbound reporting windows remain unimplemented; they must not become
a joinable profile. Missing sensors or terminal outcomes produce no substitute
zero/success observation. Sampling placement and usefulness still need review.

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
| `workspace`: `connect`, `sign_in`, `open`, `switch`, `disconnect`, `forget` | Connection/open outcomes and latency; a fixed local/remote mode only if needed in an approved view. Exclude addresses, identity providers, account names and saved-connection IDs. | Origin; [Connect.connect](../../studio/frontend/src/workspace/Connect.tsx#L145) and [workspace controller dispatch](../../studio/electron/service-bridge.ts#L784). |
| `memory`: `list`, `read`, `recall`, `context`, `knowledge`, `core_read` | Logical retrieval use, latency, result-count buckets and fixed empty/fallback/incomplete-index observations. Mode may be lexical/semantic/hybrid; no query, snippet, score vector, citation ID or search-filter values. | Origin; [SearchMemory.search](../../studio/frontend/src/workspace/Workspace.tsx#L1180), [Knowledge](../../studio/frontend/src/workspace/Knowledge.tsx#L17). [RetrievalService._measured](../../mnemion/service/retrieval.py#L118) is currently private operational measurement, not an export source. |
| `memory`: `save`, `revise`, `review`, `forget`, `core_write`, `import`, `export` | Submission/terminal outcomes, latency and bounded item/transfer totals. Distinguish accepted write from indexing readiness; preserve uncertain deletion outcomes. Exclude contents, review reasons, paths and idempotency keys. | Origin; [save/revise/forget UI](../../studio/frontend/src/workspace/Workspace.tsx#L753), [API write routes](../../mnemion/service/api.py#L616). Index/purge completion coverage remains open when the origin is absent. |
| `capture`: `configure`, `preview`, `collect`, `deliver`, `pause`, `drain`, `remove` | Separate local acceptance from remote delivery; bucket accepted/delivered counts, backlog, bytes and elapsed time. Fixed partial/fence/authorization reasons map into the common vocabulary. No conversation, file, device, grant or checkpoint identifiers. | Disclosed local capture owner; [shared native/headless cycle](../../mnemion/connectors/capture_cycle.py#L21), [DesktopSources](../../studio/electron/desktop-sources.ts#L362). The service must not recount accepted pages. |
| `sources`: `configure`, `scan`, `sync`, `pause`, `resume`, `repair`, `remove` | Scan/control outcomes, elapsed time and changed/removed/backlog buckets. Never export repository names, provider identities, paths, commits or per-source histories. | Origin for explicit controls; separately owned scans need local policy. [Connections](../../studio/frontend/src/workspace/Connections.tsx#L57), [runner._scan](../../mnemion/connectors/runner.py#L81), [managed status](../../mnemion/connectors/managed.py#L71). Shared-host scans remain unresolved. |
| `librarian`: `configure`, `run`, `cancel`, `accept`, `reject`, `undo` | Submission versus completion, duration, processed/skipped/proposal-count buckets and available reported-token totals. Exclude memory IDs, proposals, model/profile names and decision text. | Origin for controls; [Librarian.act](../../studio/frontend/src/workspace/Librarian.tsx#L145). [Scheduled runner](../../mnemion/service/librarian_runner.py#L81) completion and unattended work require the background ownership decision. |
| `models`: `configure`, `prepare`, `reindex`, `pause`, `resume`, `cancel` | Preparation/cache availability, downloads where measured, latency, admitted/deferred work and reported-token buckets. Use a reviewed local/remote execution class, not custom model IDs, endpoints, dimensions or exact hardware. | Origin for controls and owned local preparation; [EmbeddingModels](../../studio/frontend/src/workspace/EmbeddingModels.tsx#L33), [pinned model files](../../mnemion/service/model_files.py#L6), [ModelWorker](../../mnemion/service/model_worker.py#L25). Remote inference/background totals remain unresolved. |
| `backup`: `configure`, `create`, `list`, `verify`, `prune`; `recovery`: `inspect`, `restore`, `finish`, `discard` | Distinct submission, delivery, verified-readback and restore boundaries; duration and size buckets. Delivery includes upload/readback, and later verification downloads again. No destinations, key IDs, digests, archive names or operation IDs. | Origin through [local backup/recovery dispatch](../../studio/electron/service-bridge.ts#L650) or [HostBackups.request](../../studio/frontend/src/workspace/HostBackups.tsx#L24). [Native backup worker](../../mnemion/host_control/backup_jobs.py#L12) and [Git transfer stages](../../mnemion/host_control/backup_git.py#L263) are private evidence; remote completion ownership stays open. |
| `update`: `check`, `download`, `verify`, `apply`, `restart`, `rollback` | Confirmed stage outcomes, duration, transfer buckets and fixed restart/deadline reasons. A downloaded candidate is not an installed update; a rollback remains separate from success. Exclude exact version pairs, journal contents and idle/activity timelines. | Shared desktop updater policy: [check](../../studio/electron/updates.ts#L263), [guarded restart](../../studio/electron/updates.ts#L310). [Managed service update](../../mnemion/service/service_updates.py#L883) needs a disclosed host owner and background scope decision. |
| `host`: `adopt`, `enroll`, `inspect`, `start`, `stop`, `plan_upgrade`, `resolve`, `revoke` | Typed control use and confirmed outcomes, including busy/no-effect versus uncertain effects. Backup and update operations use their own rows, not another host mutation total. Never export host/operator identity, SSH fingerprints, signed plans or service paths. | Origin at [hostAction](../../studio/electron/service-bridge.ts#L304)/[HostProfiles.request](../../studio/electron/host-profiles.ts#L268); headless typed operations map through the [host protocol](../../mnemion/host_control/protocol.py#L153). |
| `evaluation`: `create_dataset`, `run`, `cancel`, `assess`, `compare`, `export`, `remove_dataset` | Workflow use, duration and case-count buckets. Quality-metric aggregation requires a separate reviewed view and remains undecided. No questions, reference labels, dataset names/IDs, per-case results or human notes; no extra evaluations or model calls for telemetry. | Origin at [Evaluations](../../studio/frontend/src/workspace/insights/Evaluations.tsx#L178). [EvaluationRunner._case](../../mnemion/service/evaluation_runner.py#L309) invokes retrieval with evaluation origin; those calls must not inflate interactive recall usage. [Ranking metrics](../../mnemion/service/evaluation_metrics.py#L13) remain private today. |
| `journal`: `configure`, `push`, `organize`, `backfill`, `recover` | Submissions, observed completion, duration and item-count buckets. No journal entries, repository destinations, source dates or replay identifiers. | Origin at [Journal.act](../../studio/frontend/src/workspace/Journal.tsx#L47), [JournalBackfill.act](../../studio/frontend/src/workspace/JournalBackfill.tsx#L35) and [recovery client methods](../../packages/client/src/index.ts#L192); unattended publication has the same unresolved background boundary. |
| `access`: `configure`, `invite`, `grant`, `revoke`; `vault`: `configure`, `read`, `write`, `delete`, `import`, `export` | Only fixed workflow/outcome counts and duration. Exclude values and value lengths, roles, identity/provider details, key names and all audit records. | Origin at [Team actions](../../studio/frontend/src/workspace/Workspace.tsx#L1944) and [SecretsVault.run](../../studio/frontend/src/workspace/SecretsVault.tsx#L45). Necessary private security records remain independent. |
| Separate resource cells: `cpu_millicores`, `rss_bytes`, `resource_budget_bytes`, `queue_drops` | Coarse local CPU/RSS/budget and discarded-observation buckets. Wire metrics attach only to allowed workflows; pressure/expiry views remain proposals. No uptime, process IDs, exact timestamps, hardware profile or opt-out event. | Selected fresh source/capture owners now supply the limited process samples described above. A general sampler and full resource qualification remain open. [Process resources](../../mnemion/service/resources.py#L75), [memory budget](../../mnemion/service/memory_budget.py#L181) and [inference queue](../../mnemion/service/inference_limits.py#L65) remain private facilities, not export feeds. Mixed-host totals and unmeasured wire traffic are excluded. |

A named subworkflow can have its own measurement, but its counts must not be
summed with its parent's as total independent uses. Background polling is not
feature adoption. The explicit CLI, desktop and Studio maps do not finish the
remaining action-by-action coverage reconciliation or qualify their producers.
Any unmapped action must appear as unmeasured in the local preview and remain a
coverage item; it must not fall into an arbitrary “other operation” event.

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
- **Metrics and budgets:** finite buckets and local contribution caps are now
  implemented. Remaining producer placement, sampling rates, outbound reporting windows,
  allowed cohort views and aggregate retention remain undecided. Verify useful
  measurements and the existing queue/RAM/CPU/batch/wire ceilings under load;
  local numeric limits alone are not a privacy mechanism. Evaluation-quality
  views, cross-restart completion, end-to-end recovery boundaries and final
  sender cancellation still need review and acceptance. Local store-generation
  checks do not establish whole-machine snapshot rollback protection.
- **Anonymity and output:** substantiate ingress/provider log behavior, transient
  source-IP handling, metadata stripping and absence of retained raw events.
  Decide suppression/complementary-cell controls and whether local differential
  privacy, trusted aggregation or secure aggregation is needed. Protected unit,
  composition, privacy budget, minimum cohort rule and utility are not chosen
  here. Report counts cannot prove distinct contributors; a clean payload cannot
  prove network anonymity. No stable IDs may be introduced to fill these gaps.

Before launch, the contract requires actual sentinel/outbound and ingress-log
evidence, opt-out races and queue clearing across all producers, no nested SDK
or server recounting, unknown-client and deferred-job cases, resource/wire
measurements and cohort/linkage attacks. All six native targets and web need
their own policy journeys. The source checks qualify only their recorded local
boundaries; they do not establish full V08, anonymous ingress or release
acceptance. No collector or paid tooling is configured by this catalog.
