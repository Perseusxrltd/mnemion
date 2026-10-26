# Anonymous product telemetry — V08

**Building/source implementation; current checkpoint 26 October 2026.** V08
retains the full scope in the [66-requirement inventory](../PRODUCT_REQUIREMENTS.md);
all requirement texts and the other 65 states are unchanged. The
[shared disclosure](../../mnemion/product_telemetry/disclosure.json) remains
`collection_available: false` with `destination: null`, and the
[release route](../../mnemion/product_telemetry/transport-route.json) has a null
address. Source controls, owners, senders and collector components exist.
**No production product collection or qualified anonymous ingress is active.**

The [six-target installed privacy-control evidence](../validation/2026-10-26-44613-native-acceptance.md)
and public auto-update gates qualify their recorded release. They do not
qualify later review/delivery changes or full V08. Consult the automatically
maintained [release status](../RELEASE_STATUS.md) for current availability;
source implementation and full telemetry acceptance remain separate.

Use the [app/native control guide](../guides/product-telemetry-controls.md),
[catalog and ownership map](anonymous-product-telemetry-catalog.md),
[delivery/budget design](anonymous-product-telemetry-budget.md) and
[collector design](anonymous-product-telemetry-collector.md) for implementation
detail. The [evidence index](../validation/telemetry-evidence-index.md) preserves
dated qualifications, original failures, source boundaries and resource results.
The requirements below remain the acceptance contract.

## Current implementation

### Choice and private state

The pre-login/offline `/privacy` page and private-stdin
`mnemion-service telemetry` controls expose schema, status, synthetic preview,
configuration and explicit report review. App and native processes share the
persistent default-enabled preference under the same OS account and application
data configuration. Browser choice is local to its site/browser, honors GPC and
served company restrictions. An enabled preference is not completed disclosure;
company policy cannot override opt-out. Damaged or unreadable settings fail
closed, with no automatic repair or repair command.

Read-only schema/status/format preview does not randomize or reserve reports,
change queues, spending or consent, or make network requests. While unavailable,
local aggregates are empty, the actual outbound body is null and inspected bytes
are zero; the synthetic example is separate. Local counts are labeled snapshots.
Choice changes, status refresh and window focus clear previews; late replies are
discarded. `transport_available` describes a valid configured release route,
not consent or a live send, and remains false here.

Every successful opt-out advances revision even when already off. The private
`store_generation` fence rejects old work after store recreation, including a
repeated revision; it is never an analytics identity or outbound value. Legacy
opt-outs remain off; missing generation requires fresh disclosure before
collection. Explicit choices clear measurement/contribution counters, while
spent delivery allowance remains. Expiry prunes on activity, not an idle timer.
Generation checks do not detect an unobservable whole-machine snapshot rollback
restoring the old token and choice.

Persistent `connection_mode` is `auto`, `unmetered` or `metered`. Automatic
mode refuses unknown metering; an unmetered declaration resolves only unknown
cost, never detected limits or another veto. Metered mode pauses delivery.
Omitting the field preserves it; stale opt-out retains a newer connection choice.
Changing it, or supplying disclosure version `0` through local stdio, does not
acknowledge unseen disclosure. No network name or address is stored.
Explicit native configuration may wait **250 ms per busy SQLite lock**, not
250 ms for the whole action. Producers/delivery remain nonwaiting; selected
desktop actions allow at most **25 ms** for an optional snapshot before the
original action.

### Owned observations and storage

The catalog defines **94 workflows in 15 families**, fixed numeric buckets and
matching Python/TypeScript coordinates. Only reviewed primitives enter encoding;
event/input/result objects, free text and identifying values do not.
The generated [coverage inventory](../validation/2026-10-26-telemetry-coverage.md)
marks 86 categories with declared source mappings and eight unmeasured. It is
available in app/browser format inspection and native schema/preview, with no
new collection owner. Release checks reject stale inventories. A source mapping
does not qualify every screen, sensor or installed client.
Payload-byte observations are not whole-wire traffic measurements.
Owners cover the control CLI, desktop/native operator, Studio/browser, explicit
local stdio and selected fresh maintenance. The control CLI classifies all
**161 operations: 82 eligible and 79 excluded across five reasons**. The catalog
records the detailed maps and remaining action-by-action coverage.

Keyed API writes require `X-Mnemion-Idempotency: new`; typed
[host mutations](../validation/2026-10-26-telemetry-host-requests.md) require the
request-scoped `result.request_disposition: new`. Cached, replayed, legacy,
unknown or lost replies add no use. Async queueing is `accepted`, not completed
work. SDK response metadata adds no owner, identifier or server recounting;
its request-local metadata needs no database migration. Aliases and nested calls
have one owner, and optional observer failure preserves exactly one original
action. Generic SDK/remote MCP requests, derived server jobs, mixed-host totals,
private operational rows, polling/replay, privacy controls and unavailable
sensors are excluded. These privacy exclusions do not abandon product scope.
The local stdio `mnemion_telemetry` tool works offline and refuses HTTP use.

Native Python and Electron share private SQLite; the browser uses origin-local
storage/Web Locks. **SQLite schema 6 / browser choice 5 / budget 2** fence older
senders; migrations preserve spent delivery accounting. Unsafe stores fail closed
under fresh ownership/permission checks. Measurements cannot initialize or repair
settings. Unavailable collection returns from producers before policy/queue
access. Workflow pairs use one current-policy transaction with per-observation
limits; batching does not guarantee both contributions fit. Native writes use
`node:sqlite`, without
spawning Python per observation or retaining a connection/positive policy cache.
One process-wide storage slot is claimed before asynchronous checks and released
only after actual closure. Windows permission helpers remain owned until actual
process exit, including after a refusal deadline.

Denial-only hints for opt-out/exhausted scopes retain the original file/day and
at-most-**60-second** expiry; merging scopes cannot renew it. Negative file
observations can be reused for **250 ms**, so a recent re-enable may lose optional
samples during that interval. Synchronous denials avoid Promise/SQLite work.
Actual choice/status and admitted observations, reservations and handoffs still
use fresh checks; negative hints never grant permission.

Fresh automatic desktop scans/capture and standalone connector execution have
owners. Empty/paused scans, explicit Sync continuations, remote-requested or
host-managed scans, reusable helpers and server-worker activity do not acquire
another owner. Native resource samples require a real child callback; headless
RSS is an ending observation, with its own CPU delta and configured capture
limit. No source history or mixed-host totals are exported. Updater download,
verification and retries form one cycle; polls add no use, unfinished cycles
are discarded on quit, and installer handoff is only accepted. Native request
acknowledgements remain separate categories, not extra completed uses.

### Admission, delivery and reporting

Owners offer delivery after a committed observation within an already-awake
desktop, page or registered Python service/local stdio loop. There is no new idle
sampler, telemetry daemon, one-shot CLI keepalive or shutdown flush. OS cost
checks precede gauges, use fixed flags without an Internet probe or network
identifiers, and reject late cancelled results with freshness measured from
query start. Linux/macOS aggregate CPU admission avoids per-core enumeration;
changed/reset counters require comparable readings and preserve the **20% CPU
admission threshold**. Windows retains the existing fallback.

Without a packaged network helper, source Windows can use its documented local
OS hint; Linux/macOS cost stays unknown. A present broken helper is not bypassed.
Unsupported browser pressure/heap sensors refuse delivery. Browser attempts also
read bounded, credential-free same-origin `/studio/telemetry-policy`, recheck
local choice/pressure and only narrow permission until reload. Reading privacy
status neither fetches policy nor enables collection. Component fixtures with
synthetic CPU admission do not qualify actual sensors or pressure behavior.

Shared native/Python accounting and browser-origin coordination enforce **seven
attempts per rolling week**, at least **24 hours plus jitter** between attempts,
**64 KiB reserved per attempt** and a **256 KiB rolling-day guard**. Reservation
consumes the queue; opt-out clears measurements/lease but does not refund spending.
These reservations do not establish actual whole-wire cost. The native sender
drains its own watcher before the mandatory fresh handoff check, then resumes
watching; the five-second deadline, opt-out, one storage handle and final cleanup
remain enforced. Full installed cancellation/resource qualification is still open.

Current **wire v2/report v3** retains four-byte packets. Automatic reports use
the randomized encoder; manual reports use the first permitted view, coordinate
zero and flags two, without category data or a random draw. Reviewed reports
contribute only to a coarse global power-of-two volume range after **64 total
reports**. Categorical sums, per-view counts and precision use automatic reports
exclusively, retaining the **4,096-report per-view threshold**. No separate manual
count is published. Wire v1 is rejected; immutable aggregate reports v1/v2 remain
readable. Volume is unauthenticated and is not a count of people/installations;
fine-grained statistics can remain unavailable. Exact review and its privacy
limits are specified below.

The dedicated collector implements bounded TLS intake, metadata removal,
private immutable closed-week publication and **eight-window retention** in a
minimal locked runtime. Systemd supplies its sole listener; the service cannot
connect outbound or bind another port. Isolated TLS/VPS checks establish those
recorded boundaries, not provider/ingress privacy or a production deployment.

## Remaining acceptance gates

- **Coverage and installed behavior:** finish the action-by-action ownership and
  exclusion review, including autonomous work and unknown remote clients. All
  six native targets and web need the newer review/delivery, restart/update,
  cancellation, storage-loss and pressure/sensor journeys. Published control
  evidence does not transfer to those additions.
- **Resources and architecture:** the fixed compiled-app comparisons still exceed
  the unchanged **2 MiB / 0.5%** acceptance gates. Ending RSS, matched maxima,
  other process roles and profiled CPU are retained in the evidence index; no
  causal improvement or favorable-run selection is accepted. The subsequent
  [pinned private SQLite experiment](../validation/2026-10-26-telemetry-private-sqlite.md)
  has **60 functional passes / two platform skips**, but is **not adopted**:
  its fixed component sequence showed higher CPU and sampled peak RSS, with an
  incomplete counterbalanced design. Library unmapping and lower ending RSS
  do not establish a resource pass. Keep the existing backend; a new optimization
  needs an evidence-supported implementation hypothesis before new measurements.
- **Whole transport and reliability:** substantiate total wire cost, native/web
  resource ceilings and tail latency with real memory work, offline/metered and
  saturation conditions. Prove opt-out at the final send boundary across owners
  and processes; scoped loopback tests alone do not close these gates.
- **Privacy and usefulness:** qualify the actual endpoint, ingress/provider logs,
  monitoring and backup retention; test linkage, rare cohorts, repeated
  contributions, suppression and attack resistance. Establish honest utility and
  interactive-selection limits without unique-user claims or identifying
  workarounds. No production collector or default-enabled launch is qualified.
- **Release:** qualify the final implementation through the normal native/public
  gates. Source components, historical control releases and private experiments
  do not establish full V08 readiness.

The user's request, verbatim:

> - Full telemetry
> - Anonymous
> - Users can opt in or out (opt in by default)
> - It’s just so we can get data from the app and get usage and things like that.

“Opt in by default” means enabled by default with clear disclosure and an easy,
persistent opt-out and re-enable control. “Full” means coverage of product
workflows through bounded aggregate measurements; it does not authorize
collecting user content or identifying people, organizations or devices.

## Measurement and anonymity contract

Maintain a versioned, reviewed catalog covering desktop, browser, native-agent
and headless workflows: setup, connections, retrieval, capture, models, backup,
updates and host controls. Instrument fixed workflow boundaries without reading
their content for telemetry. Each supported workflow must have an explicit
measurement or a documented exclusion, also visible in the local payload preview.

The [versioned metric catalog and ownership map](anonymous-product-telemetry-catalog.md)
maps this scope to current source boundaries and records unresolved coverage.

| Include as bounded aggregates | Exclude from collection, queue, transport and collector logs |
| --- | --- |
| Feature use, completion/failure counts and sampled latency histograms | Memory/chat/prompt contents, responses, snippets, embeddings, transcripts and screenshots |
| Coarse CPU/process-RAM, configured resource-budget and pressure buckets | Exact hardware inventory, serials, installed software/fonts or other fingerprints |
| Coarse transmitted/received byte counts, throughput and queue/drop buckets | File/directory paths, filenames, URLs, hosts, addresses, custom labels and arbitrary metadata |
| Fixed public error-code categories such as `network_timeout` or `readiness_timeout` | Exception text, stacks, crash dumps, credentials, tokens, keys or private diagnostics |
| Coarse platform, architecture, release-family and resource cohorts | Account, organization, workspace, memory, operation, session, device or advertising IDs; hashes/pseudonyms of these values |

Strings must come from fixed enums; numeric values need explicit ranges,
clipping and buckets. Unknown fields, nested arbitrary objects and free text are
rejected at both producer and collector. Resource/bandwidth figures identify
their unit and sampling basis; unavailable sensors remain unknown, not zero.
Do not infer physical memory bandwidth from request throughput.

Use coarse reporting windows, discard event ordering and exact timestamps, and
allow only reviewed combinations of cohort dimensions. Send platform/version
and resource views without join keys or a persistent per-installation profile.
Avoid combining rare versions, hardware buckets and error patterns into a
fingerprint. No cookies, session replay, stable random IDs, hashed account/device
IDs or cross-session linking. Pseudonymous tracking must never be described as
anonymous. Reports measure sampled usage, not unique people/devices, retention
or individual journeys that would require such linking.

## Disclosure, user choice and company policy

Before the first possible emission, show what is measured, the destination and
purpose, the default-enabled state, limits and **Disable product telemetry**.
The same setting and payload/schema preview must be available before workspace
sign-in and during an outage, and discoverable later in app settings. Initial
headless/native-agent setup must disclose the same default and expose structured
setup, status, disable and re-enable operations; silence is not a completed
setup disclosure.

Persist the explicit choice across process/app restart and supported updates.
An unreadable or invalid preference/policy suppresses emission until repaired.
Opt-out stops new collection and emission, cancels queued sends/retries, and
clears all pending aggregates from memory and disk. Check effective policy again
at the last send boundary, including work queued by another local process.
No final opt-out event or shutdown flush may escape the disabled policy. Already
transmitted bytes cannot be recalled; do not promise individual deletion from
anonymous aggregates that contain no lookup identity. Re-enable starts a fresh
queue and never resurrects discarded history.

Company policy may disable or narrow collection and takes precedence when more
restrictive. It must not force transmission over an explicit user opt-out.
Status distinguishes the saved preference, effective state, policy reason,
schema version and bounded queue/budget status without exporting company or
user identity. Desktop, background helpers and local agents share this effective
policy; headless installations need equivalent persistent controls. No telemetry
choice may affect memory features, permissions, pricing or support access.

Browser policy must persist across normal reloads and updates, honor applicable
browser privacy signals such as Global Privacy Control as an opt-out, and send
without credentials, cookies or referrers. Document storage-clearing/private-mode
limits; do not recreate a forgotten identifier or use fingerprinting to recover
a preference. Require fresh visible disclosure before any new default-enabled
state can emit after its preference store has genuinely been removed.

Optional product telemetry is separate from the private, permission-scoped
[workspace operational metrics](observability-and-evaluations.md) and security
audit trail. Disabling it does not disable necessary local access/recovery audit
records; those records must never be forwarded as a telemetry fallback.

## Proposed outbound schema and payload preview

The following **23 October design example** is retained as a wire-format
proposal. Its labels and buckets are not the current local encoding in the
[versioned catalog](anonymous-product-telemetry-catalog.md) or the later
[delivery component format](anonymous-product-telemetry-delivery.md). That source
format defines bounded cohort views and an ingress adapter. Later source adds
senders and owner wiring, but installed delivery and a qualified endpoint remain
unaccepted. The fixed-enum requirement still
excludes arbitrary combinations, exact timestamps and identity fields. The
read-only app/native/browser format preview shows a separately labeled synthetic
example. The new explicit inspection action can stage an actual report only
after collection permission and observations exist.

```json
{
  "schema_version": 1,
  "window": "week",
  "surface": "desktop",
  "feature": "workspace.open",
  "cohort": {"platform": "windows", "version_family": "4.x"},
  "measurements": [
    {"metric": "completions", "bucket": "success", "count_bucket": "10-99"},
    {"metric": "latency_ms", "bucket": "100-499", "count_bucket": "10-99"},
    {"metric": "errors", "bucket": "network_timeout", "count_bucket": "1-9"}
  ]
}
```

Resource and bandwidth views use separately reviewed enums/buckets rather than
adding an exact machine profile to this envelope. Counts and charts must explain
sampling, clipping, bucket ranges and dropped reports. Transport metadata must
be disclosed separately; a clean body alone is not evidence that the whole path
is anonymous.

**26 October 2026 clarification:** show the format/categories and allow optional
manual review to be selected **before collection permission**. Create an actual
packet only **after authorized observations exist**, and expose its exact bytes
**before emission in manual mode**. Automatic delivery remains the default;
manual review is optional and explicitly named. This sequence supersedes the
earlier literal requirement for an actual packet before enabling: collecting
data before permission is not authorized. That earlier sequence is not claimed
as tested, and no canonical requirement text or state changes.

The 26 October source format example is labeled `kind: "synthetic_example"`
and its actual outbound state remains `not_inspected`. It is separate from the
new explicit `inspect_report` mutation. Source checks and an isolated Chromium
review journey passed, while interactive privacy/utility and installed acceptance
remain open. The fixed example alone does not establish actual-packet inspection.

The subsequent [review-clock foundation](../validation/2026-10-26-telemetry-preview.md#review-clock-foundation)
adds private native clock readers and a portable lifetime validator, capped at
15 minutes or the supplied observation expiry, whichever comes first. Wall-time
and elapsed-time checks reject rollback, epoch loss/change and expiry without
renewing the original age. Browser coordination keeps its epoch only among
live same-origin pages; ordinary reads never initialize it. Epochs are local
control values, not analytics identifiers or outbound fields. Later macOS
Intel/ARM component checks qualified the shared clock; their overall CI and
installed-review acceptance are separate.
Headless Python now reads the same OS clock directly when the packaged helper
is absent; a present broken or unavailable helper is never bypassed. Direct
Linux/Windows x64 comparisons passed. The [26 October macOS follow-up](../validation/2026-10-26-telemetry-report-review.md#compiler-free-headless-review-clock)
also qualified direct Python/helper agreement on Intel and ARM64 with Node
22.23.2. These component results do not establish whole-CI, Electron, installed
review or resource acceptance.

The [new report-review source](../validation/2026-10-26-telemetry-report-review.md)
implements one private four-byte stage, app controls and local agent actions.
Inspection consumes its pending snapshot without spending delivery allowance;
repeat inspection preserves the bytes and original expiry. Approval permits one
eligible attempt using those bytes. Later observations, contribution limits and
spent delivery budgets are preserved. Expiry, discard or invalidation never
leave manual mode automatically. Status and format preview remain read-only
and do not reveal the staged body. Private SQLite schema 6 and browser
choice 5/budget 2 fence older senders. Final verification passed **306 Python,
116 browser-source and two Python/Node SQLite handoff checks**, plus the isolated
Chromium review flow and both builds. The browser fixture used synthetic input,
made no report request and spent no delivery attempt. These changes are excluded
from 4.46.13; interactive privacy/utility, full resources/sensors, wire and
installed/platform acceptance remain open. Production remains false/null/null
and V08 remains Building.

The later selection correction exposes `report_selection` and `aggregation`
in exact previews. Reviewed packets show both privacy-loss fields as null and
`privacy_bound_scope: "fixed_body_for_permitted_groups"`; no categorical
measurement is transmitted. `ln(3)` describes automatic randomization, not
arbitrary human inclusion. Report v3 estimates only correctly marked automatic reports under
independent randomization and packet-independent inclusion. Neither a small
packet nor its selection marker establishes participation or network anonymity.

## Collector and release conditions

The network terminator necessarily observes a source IP transiently to handle a
connection. The reviewed collection path must neither retain nor forward it,
including in access/error logs, CDN/WAF logs, tracing, crash diagnostics or
`Forwarded`/`X-Forwarded-For` headers. Strip identifying origin, referrer,
user-agent and request/correlation metadata before aggregate processing; no
workspace authentication or credential forwarding is permitted. Verify this
through the actual ingress, proxies, collector and any monitoring/backup layer.
An infrastructure provider that retains identifying request logs fails this
contract; do not silently weaken the anonymity claim.

Process bounded contributions into coarse aggregate cells; do not retain raw
request bodies or a per-client event store. Keep only the volatile aggregation
state needed for the current window, and discard insufficient cells when it
closes. Set an explicit bounded aggregate retention period before launch.
Reporting must suppress small cohorts, rare cells, complementary cells and
filter/difference queries that could reveal a suppressed value. The architecture
review must specify and justify the minimum cohort threshold, contribution
bounds, and any required noise/privacy budget or secure aggregation. Report
counts are not distinct-user counts and cannot alone prove a cohort's anonymity.
Until those parameters and their attack tests pass, no collector launch or
analytics output is qualified.

A documented architecture/privacy review must substantiate anonymity against
payload linkage, transport metadata, rare cohorts and auxiliary information
before default-enabled collection can ship. If the proposed design requires
stable pseudonyms or identifying logs, it does not satisfy V08. Use existing
free infrastructure and tooling; no paid analytics, subscriptions, model calls
or new spending is authorized by this scope.

## Initial resource and reliability ceilings

These are acceptance ceilings for the future implementation, to be measured
with memory work active. A proposed increase requires a documented design
revision and new measurements; saturation must drop telemetry rather than
delay canonical memory work.

| Resource | Initial ceiling and behavior |
| --- | --- |
| Local pending queue | At most 256 KiB or 512 aggregate records, whichever is reached first; maximum age 48 hours; bounded eviction and full opt-out clearing |
| Added resident working memory | At most 2 MiB per participating process; no model loading or new persistent service solely for telemetry |
| CPU | At most 0.5% of one core averaged over the representative workload; bounded producer work and no synchronous telemetry network calls in memory operations |
| Batch | At most 16 KiB encoded and 64 KiB decoded; one in flight, at most hourly, with randomized timing and sampling of frequent events |
| Network | At most 256 KiB outbound wire bytes per installation per rolling day, including retries/transport overhead; reserve a safe upper bound before connecting and pause when exhausted |
| Failure/offline behavior | Five-second attempt deadline; backoff starts at one hour and is capped at 24 hours with jitter; no forced connectivity, wake or shutdown flush; pause on constrained/metered policy |

Workers on the same installation share the local traffic budget without sending
its coordination identity. Offline and suspended operation remain useful; queued
events can expire or be sampled away. Telemetry failure never interrupts memory
writes, retrieval, capture, backup, updates or recovery. Measure enabled/disabled
overhead and tail latency under pressure; a budget violation blocks release.

## Required acceptance evidence

Implement meaningful outbound and privacy tests, rather than checking only that
a serializer matches its own example:

1. Exercise real app and agent workflows against a capture endpoint. Seed unique
   sentinel contents, labels, credentials, paths, URLs and IDs; inspect serialized
   bodies, headers, URLs, local queues and collector/ingress logs. None may escape,
   including through rejected inputs, encoding, exception or crash paths.
2. Observe fresh default disclosure, explicit disable/re-enable, persistent
   choices across restart/update, unreadable settings, company-disable precedence
   and a user opt-out that company policy cannot override. Confirm identical
   app/native-agent effective status without changing memory permissions.
3. Disable while offline, during batching, during a queued retry and during an
   in-flight request. Verify pending disk/memory state is cleared and no new
   emission starts after disable completes; reconnection/re-enable cannot replay
   the old queue. Account honestly for bytes already transmitted.
4. Saturate the queue and daily budget; simulate DNS/TLS failures, timeouts,
   collector rejection, suspension and metered policy while normal memory work
   continues. Measure RAM, CPU, wire bytes and tail latency, bounded eviction,
   retry spacing and the absence of shutdown or reconnect bursts.
5. Probe collector privacy through the actual deployment configuration, including
   proxies/CDN/WAF, monitoring and backups. Trigger success and error paths with
   recognizable test metadata and verify no identifying retention or forwarding.
   Inspect aggregate storage for hidden join keys or raw-request retention.
6. Test rare/coincident cohorts, repeated contributions and difference queries
   against the reviewed suppression/privacy mechanism. Verify output cannot
   reveal a withheld cell or be misrepresented as distinct-user statistics.

| Acceptance target | Required policy journey |
| --- | --- |
| Linux x64 | Installed app, native agent and headless preference/queue persistence; restart/update, offline and outbound proof |
| Linux ARM64 | Same actual installed journey and measured resource limits |
| Windows x64 | Installed app/background helper and native-agent parity; restart/update, policy permissions and queue clearing |
| Windows ARM64 | Same journey on the supported desktop/engine architecture; record emulation and measured limits |
| macOS x64 | Installed app/background helper and native-agent parity; restart/update, offline and outbound proof |
| macOS ARM64 | Same actual installed journey and measured resource limits |
| Web | Actual supported browser flows, disclosure, reload persistence, privacy signals, company policy, storage loss and credential/referrer-free transmission through the reviewed ingress |

Do not infer one target's policy or privacy pass from another. The final evidence
must include the reviewed catalog/schema, local payload preview, collector/log
configuration, anonymization analysis, bounded-load measurements, all native/web
receipts and public documentation. V08 is **Building/source implementation**;
complete collection, privacy proof and the appropriate release acceptance must
establish the full requested behavior before it can be marked Shipped.
