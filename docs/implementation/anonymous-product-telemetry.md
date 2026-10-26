# Anonymous product telemetry — V08

**V08 is Building/source implementation; checkpoint 26 October 2026.** The full scope
recorded on 23 October remains the acceptance contract in the
[66-requirement inventory](../PRODUCT_REQUIREMENTS.md). Local privacy controls,
the fixed catalog, bounded aggregate queues, selected owned workflow hooks,
bounded transport components and opportunistic application-owner wiring are
implemented in source;
product collection is unavailable. V08 is the
active feature milestone after [fresh backup and independent restore](../validation/2026-10-24-4465-backup-acceptance.md)
passed at **00:01:45 and 00:15:23 UTC**. V08 remains Building; all requirement
texts and the other 65 states remain unchanged. Local privacy controls ship in
4.46.13; the later CPU admission and exact-report review changes documented
below remain source-only and under validation.

The [dedicated collector source](anonymous-product-telemetry-collector.md) now
provides a bounded TLS entrypoint, metadata removal, private report access and
a minimal locked runtime. Its [actual TLS, clean-runtime and isolated VPS checks](../validation/2026-10-25-telemetry-collector-service.md)
passed. The service manager supplies its sole listener, and the collector cannot
make outbound connections or bind another port. The finite VPS check confirmed
these restrictions, resource limits, request-data exclusion and clean shutdown.
No production collector is deployed; provider/ingress privacy, client
resources, useful reporting and full installed acceptance still gate release.

The [closed-week volume follow-up](../validation/2026-10-25-telemetry-weekly-volume.md)
adds one global power-of-two report range after 64 accepted contributions, with
the existing 4,096-per-view precision threshold unchanged. New report schema v2
preserves immutable v1 reading and the original four-byte wire format. The
67 focused source checks passed. Volume is not a count of people or installations
and is not authenticated; detailed statistics can remain unavailable. This
source follow-up does not activate collection or close the remaining privacy,
resource, deployment and installed-platform requirements.

The [app and native usage guide](../guides/product-telemetry-controls.md)
describes the pre-login/offline `/privacy` page and private-stdin
`mnemion-service telemetry` actions: `schema`, `status`, `preview` and
`configure`. App and native processes share a persistent default-enabled
preference under the same OS account and application data configuration.
Browser choice is local to that browser and site, honors Global Privacy Control
and uses the served company restriction. Company policy can restrict collection
but cannot override a user opt-out. Damaged or unreadable settings fail closed;
there is no automatic repair or repair action in this source checkpoint.
Each successful opt-out advances the local revision, including when already off,
so an earlier enable request cannot override that newer choice.
Native and browser controls also compare the private `store_generation` token,
preventing old work from matching a recreated store whose revision repeats.
This token belongs only to local control state; it is never an analytics identity
or outbound measurement. Supported legacy opt-outs remain off, and a missing
generation requires fresh disclosure before collection can become effective.

The current [app-owner source batch](../validation/2026-10-24-telemetry-app-owners.md)
adds a persistent `connection_mode` through app, native/private-stdin and browser
controls. `auto` refuses unknown metering; `unmetered` declares an unlimited
connection only where metering is unknown; `metered` pauses delivery. Detected
limits, resource pressure, disclosure and company/user restrictions still win.
The setting stores no network name or address and persists until changed.
SQLite storage version **5** and browser choice version **4** preserve spent
delivery accounting when migrating. A stale opt-out still disables collection
without replacing a newer connection choice; omitting the field preserves it.
Changing this setting does not acknowledge an unseen disclosure.
Explicit native `configure` now permits up to **250 ms per busy SQLite lock**
to accommodate a brief reader; this is not a single 250 ms action deadline.
Producers and delivery retain zero lock waiting. The maintained local stdio
`mnemion_telemetry` choice also accepts `connection_mode` and disclosure version
`0`, without treating that value as acknowledgement of an unseen disclosure.

The [shared disclosure](../../mnemion/product_telemetry/disclosure.json) has
`collection_available: false` and `destination: null`. Saving an enabled
preference does not complete disclosure or activate collection. The current
source preview returns the measurement catalog, an empty local aggregate list
while unavailable, and a fixed synthetic four-byte
[report-format example](anonymous-product-telemetry-delivery.md#one-randomized-category-per-report).
It reports `outbound_state: "not_inspected"`, with a null actual body and zero
inspected outgoing bytes. No report is randomized or reserved by viewing the
example; queue contents, spent allowance and consent remain unchanged, and no
network request is made. The app clears previews on choice changes, status
refresh or window focus and discards late responses. Any displayed local counts
are separately labeled snapshots. The
[preview evidence](../validation/2026-10-26-telemetry-preview.md) preserves the
five-target 4.46.12 result. The later
[4.46.13 qualification](../validation/2026-10-26-44613-native-acceptance.md)
passed all six installed targets: Linux, Windows and macOS, each on x64 and
ARM64. Each passed all 64 required fields, including actual
privacy controls, app/native choice visibility, inspection without spending,
preview clearing and opt-out persistence through restart. Windows ARM used an
ARM desktop with emulated x64 engine/database components. Version 4.46.13 is
published after artifact verification, and all six public automatic-update
targets passed. Those release checks do not qualify the newer clock source.
This qualifies the privacy controls, not active collection or full V08.
`transport_available` describes valid configured release-route capability,
separate from consent and a live send; it remains false here.
Owned CLI, desktop/native-operator, Studio/browser and
explicit local stdio and selected fresh-maintenance hooks exist in source.
Python, native and browser senders and application-owner wiring remain inactive;
the release-owned [transport route](../../mnemion/product_telemetry/transport-route.json)
also has a null address. No collector, production analytics or qualified anonymous
ingress is deployed.

The new owners offer delivery after an owned observation is committed, within an
already awake desktop, browser page or registered Python service/local stdio loop. They do
not add an idle scheduler, one-shot CLI keepalive or shutdown flush. Active
owner/lifecycle source checks and a **19-assertion actual Chromium journey**
passed in the [current report](../validation/2026-10-24-telemetry-app-owners.md).
That journey used synthetic CPU admission, real heap readings and normal browser
networking; it does not qualify actual pressure sensors. Unknown native metering requires
an explicit unmetered declaration, and unsupported browser pressure/heap sensors
refuse delivery. Full workflow/owner coverage, whole-wire/resource measurements
and native/web release acceptance remain open.

The subsequent [browser company-policy refresh](../validation/2026-10-24-telemetry-company-refresh.md)
adds one bounded, credential-free read of the Studio page's own
`/studio/telemetry-policy` before an already-reserved report can be sent. It
rechecks local choice and pressure before that read and the final report handoff;
observed restrictions can only narrow permission until the page reloads. Reading
privacy status does not fetch policy or enable collection. The **90 browser and
25 Python source checks** passed; on **25 October**, the actual Chromium journey
passed **20 assertions** with seven policy reads, one four-byte TLS report and
one real preflight. CPU admission was synthetic. The final frontend build and
fixture cleanup passed. Neither endpoint's production ingress/log privacy nor
full resource/platform acceptance is qualified.

The subsequent [native network-admission source batch](../validation/2026-10-25-telemetry-native-conditions.md)
adds a shared OS-cost helper and read-only eligibility checks before desktop or
Python owners start gauges. It reads fixed cost/constraint flags without an
Internet probe or network identifiers. A user declaration can resolve unknown
metering, never observed metering or constraints. Missing compiled support stays
unknown. Preparation and refresh occur only inside an already-awake opportunity;
late cancelled results are rejected, with freshness measured from query start.
Focused network and packaging checks passed. Final component observations were
**2.11 MiB added RSS on Windows Node and 2.23 MiB on Linux Electron**, both above
the unchanged 2 MiB full-feature target. Later
[macOS ARM64/x64 component probes](../validation/2026-10-25-telemetry-native-conditions.md#macos-component-follow-up)
compiled and passed under Python 3.12.10 and Node 22.23.2; they are not Electron
or installed-client acceptance. All-six-native and full resource/wire/collector
acceptance remain open.

The [producer-overhead source follow-up](../validation/2026-10-25-telemetry-producer-overhead.md)
adds denial-only hints for explicit opt-out and exhausted contribution scopes.
They expire lazily within 60 seconds and cannot authorize collection; accepted
work retains the current-policy and storage fences. Focused checks passed. A real
headless desktop/TLS diagnostic measured **3.27 MiB added RSS when opted out and
6.40 MiB when enabled**, both above the unchanged 2 MiB full-feature target.
Its synthetic burst and after-bootstrap baseline do not qualify representative
app performance or installed platforms.

The next [denial-allocation and real-memory diagnostic follow-up](../validation/2026-10-25-telemetry-memory-profile.md)
reduces native snapshot allocations and carries the fixed UI workflow through
the desktop snapshot bridge. Merged exhausted scopes retain their original
bounded expiry; accepted work still requires fresh policy. The new fixed
save/fetch/lexical-search fixture uses real SDK/API/PostgreSQL transactions with
the Studio wrapper in the main process. Focused source checks passed; measured
workload results verified **384 requests per variant**. Enabled ending RSS growth
exceeded unavailable collection by **4.41 MiB**; negative CPU differences remain
run variation. The default synthetic mode still measured **6.59 MiB** enabled
RSS growth. At that checkpoint, renderer/IPC and full resource acceptance
remained open.

The subsequent [bounded denial-observation reuse](../validation/2026-10-25-telemetry-denial-io.md)
can skip repeated file-stat/SQLite work for up to **250 ms**. File changes need
not invalidate the negative hint immediately; newly re-enabled work may lose
optional samples during that interval. Choice/status and admitted work retain
fresh checks, with no positive consent cache. The original 60-second expiry and
day invalidation remain. Focused checks and the first burst diagnostic passed;
opted-out/enabled RSS remained **2.41/4.83 MiB**, above the 2 MiB target.
Later source returns immediate native snapshot refusals synchronously to avoid
their extra Promise/await work; eligible reads retain fresh asynchronous policy
checks. Its final source checks and second burst completed, measuring
**1.89/4.43 MiB** opted-out/enabled RSS. The single opted-out observation does not
qualify the full resource target; enabled RSS and platform acceptance remain open.

The subsequent [real renderer/IPC source journey](../validation/2026-10-26-telemetry-renderer.md)
passed all three variants through the development app's onboarding, sandboxed
preload, native session handle and default measured renderer client. Each
completed **387 real fixture API requests**; unavailable/opted-out variants
collected nothing, while enabled recorded 66 writes and one four-byte TLS report.
The memory cycles were scripted renderer SDK calls. The descriptive enabled
Electron CPU difference was **1.143% of one core** over the baseline interval;
ending and sampled-peak RSS observations differ and are not stable overhead
estimates. The **2 MiB RSS / 0.5% CPU** targets remain unchanged and unaccepted,
as do installed-platform, whole-wire and production privacy qualification.

The 26 October [SQLite cleanup source follow-up](../validation/2026-10-26-telemetry-sqlite-cleanup.md)
requests `PRAGMA shrink_memory` before closing native telemetry connections,
without retaining a connection or positive policy cache. The Electron build and
44 focused checks passed, with two Windows-only skips. Later compiled renderer
run **40260081248** matched all **1,961 reviewed source hashes** across three
successful journeys and **1,161 real fixture API requests**. Enabled main-process
ending RSS growth exceeded unavailable collection by **1,875,968 bytes**, below
2 MiB in that observation, while sampled-peak growth exceeded it by
**3,440,640 bytes**, above the target. The descriptive Electron CPU difference
was **180 ms / 0.2171447873% of one core**. These results and the retained small
allocation diagnostics do not establish a causal improvement or stable
resource/platform acceptance. Changed source `b9a29886830b63fac75c863e57d55287cc9bd321`
remains separate from already-frozen 4.46.12; production collection is unavailable.

The [one six-case attribution run](../validation/2026-10-26-telemetry-attribution.md)
completed on 26 October; qualification matched all **1,966 reviewed files per
variant**, with **2,322 successful API requests** and no model calls. All six
original outcomes remain retained. Enabled main-process matched maxima were
**3,608,576 / 3,391,488 bytes**; endings were **3,125,248 / 1,933,312 bytes**.
The profiled CPU differences of **0.295167% / 0.307298%** are descriptive,
not acceptance. Earlier report checks and offline findings remain preserved.
The stop-rule decision selects a cold initialization and storage-runtime
ownership review: overlapping first-call windows suggest file-backed residency,
without proving SQLite alone caused the difference. No repeat benchmark or
budget revision is selected. The **2 MiB / 0.5%** gates remain unchanged and
unaccepted. That diagnostic remains separate from the now-published 4.46.13
native-control qualification; collection stays false/null/null.

The resulting [CPU admission change](../validation/2026-10-26-telemetry-cpu-admission.md)
removes the per-core allocation path on Linux and macOS by reading fixed
aggregate counters through the existing native helper. The upstream Linux
`os.cpus()` implementation allocates a 458,752-byte scratch array per call;
the new reader uses a 512-byte stack buffer for `/proc/stat`. Windows and
unavailable helpers retain the existing Node fallback. Provider/count changes,
unknown samples, counter resets and clock rollback require two new comparable
readings, preserving the 20% idle threshold and other admission restrictions.
The build, focused admission/transport checks and actual Linux Electron ABI
probe passed. Its **2,883,584-byte component RSS observation** still exceeds
2 MiB and does not qualify the full resource limit. This source change is
excluded from published 4.46.13; no renderer benchmark was repeated.

The later [delivery components](anonymous-product-telemetry-delivery.md) implement
a four-byte randomized body, fixed weekly aggregation, an ASGI adapter and a
bounded private publisher in source. Their conditional per-report privacy bound
does not establish participation or network anonymity. Sender integration and
deployed qualification remain open; the
[delivery validation](../validation/2026-10-24-telemetry-delivery.md) records
47 Python checks, six Node and six actual Electron codec checks, and a
12-check isolated plain-loopback HTTP journey. The final Python selection and
frontend build passed; full resource/platform acceptance remains pending. These
checks do not qualify a product sender or TLS/provider logging. Material limits
on small-population statistics remain.

The subsequent [shared native/Python budget](anonymous-product-telemetry-budget.md)
adds persistent private attempt accounting and cancellation fences in source:
seven attempts per rolling week, at least 24 hours plus jitter between attempts,
64 KiB reserved per attempt and a 256 KiB rolling-day guard. Reservation consumes
the queue; opt-out retains spent allowance while clearing measurements and the
lease. Its final source checks passed **54 Python cases and 18 actual Electron
cases, with two Windows-only ACL skips**, including the monotonic deadline. It
adds no sender or network activation and does not prove installed cancellation,
actual wire usage or full resource/platform acceptance.

The [versioned catalog and local queues](anonymous-product-telemetry-catalog.md)
now encode **94 workflows in 15 families** with fixed numeric buckets and
matching Python/TypeScript coordinates. Native SQLite and browser queues enforce
bounded cells, local scope/day contribution caps, company-group restrictions
and the originating revision/generation pair. Measurement/contribution counters
clear on explicit choice; spent delivery accounting is retained. Queue expiry
prunes on activity. Generation fencing covers store deletion/recreation;
it cannot detect an unobservable whole-machine snapshot rollback restoring the
old token and choice. Final sender cancellation remains a full-feature check.
Declared exclusions cover unowned remote clients, derived server work, mixed-host
totals, private operational rows, polling/replay, privacy controls and unavailable
sensors. These privacy boundaries do not abandon connector or roadmap requirements.

The later [aggregate source validation](../validation/2026-10-24-telemetry-aggregates.md)
records **28 Python, 11 browser/codec and 12 bridge checks**, both builds and a
**nine-check built-browser catalog journey**. No fresh package build qualifies
this batch. Remaining workflow hooks, full coverage, measured resource ceilings,
all-platform behavior and outbound/collector/privacy acceptance remain open.
The following generation correction passed **29 Python and 12 browser/codec
checks** and both builds. Its initial test-placement `NameError` remains failed
and preserved separately from the corrected passing run.
The actual built-Chromium generation journey then passed **11 checks** for
stale UI state, legacy opt-out, damaged generation and narrow-screen behavior;
the retained first runner attempt stopped before any UI action.

The existing [owned control-CLI hook](anonymous-product-telemetry-catalog.md#owned-headless-control-coverage)
is limited to `mnemion-control call`: all **161 API operations** have an explicit
mapping, with **82 eligible actions and 79 exclusions across five reasons**.
It snapshots local generation/revision and passes only fixed enums, duration and
permitted numeric payload-byte counts to the encoder. Keyed writes require the
server's `X-Mnemion-Idempotency: new`; cached, legacy or unknown receipts contribute
nothing. Asynchronous work is acknowledged as `accepted`, without claiming
completion. The request-local metadata change requires no database migration.
Generic SDK and remote MCP calls never acquire a telemetry owner. The corrected
focused contract check passed after the retained initial schema-reference test
failure; the final focused Python selection then passed **51 tests**, and a
fresh private wheel passed its isolated offline journey. These source checks
do not qualify the published 4.46.6 artifact or native telemetry release.
Collection remains off. The mapped hooks do not finish remaining autonomous-work
ownership, workflow qualification, the sender/collector or full
resource/privacy/platform acceptance.

The current [desktop/Studio source batch](anonymous-product-telemetry-catalog.md#owned-desktop-native-operator-and-studio-coverage)
adds Electron's private SQLite writer, shared with native Python policy, and a
read-only Windows owner/DACL check compiled with MSVC. Unsafe stores fail closed;
measurement cannot initialize or repair settings. A shared TypeScript workflow
captures generation/revision and submits only reviewed numeric primitives.
Explicit native-operator/IPC actions and a Studio-only client wrapper own their
mapped uses. The reusable SDK only weakly tags response-bound `new`/`replayed`
metadata; it starts no analytics. Polling, generic requests, uncertain/replayed
keyed writes, privacy controls and unowned continuation transports are excluded.

Preliminary checks passed **32 Python tests with two Windows skips**, **ten local
native-store/bridge tests with one Windows-only skip**, and **nine actual Windows
store tests with zero skips**. The first Windows run compiled its helper but
failed Node test discovery on a UNC path before tests; the inspected continuation
used and cleaned local temporary fixtures. These results predate the latest
batching and hook changes. Subsequent targeted checks passed **24 Studio/browser,
six desktop source guards and 11 Windows tests with zero skips**. The final
combined Electron 44.9.3 selection passed **27 tests with two Windows-only skips**
and its build passed, superseding the earlier eight-pass/one-skip Electron store
selection for current source coverage.

A copied built-Chromium fixture passed **19 owned-workflow checks**, including
search, private-input exclusion and cross-tab opt-out during an outstanding
request. Only the copied fixture's disclosure enabled local counters with an
`example.invalid` destination; source/build collection stays unavailable and no
sender exists. The original browser runner's desktop-only control timeout is
preserved. No production memory writes or outbound collection occurred. The
[validation report](../validation/2026-10-24-telemetry-aggregates.md) records both
the passing checks and an exploratory Electron component result of **3.61 MiB
added RSS**, above the unchanged **2 MiB** target. Optimization, whole-app and
all-platform resource qualification remain open. At that desktop/Studio
checkpoint, browser sign-in/connect, legacy UI and stdio ownership were still
unfinished. None of these results qualifies packaged telemetry or anonymous
ingress. The accepted 4.46.6 security release excludes this work.

The next [UI/local stdio source batch](anonymous-product-telemetry-catalog.md#browser-connection-legacy-ui-and-local-stdio-coverage)
adds five browser connection actions and classifies all 29 legacy Studio methods
(11 selected, 18 excluded). Desktop connection IPC retains its existing owner;
the browser wrapper skips those calls. Company sign-in cancellation and reviewed
boolean result flags produce only fixed outcomes, without private inputs/results.
The MCP map classifies 29 maintained gateway paths, including two compatibility
labels, and all 48 legacy stdio tools (33 selected). Only explicitly configured
local stdio observes the disclosed OS-account choice. HTTP never becomes a
server telemetry owner, even when the process holds a stdio key; aliases and
nested SDK calls are not counted again.

The local `mnemion_telemetry` tool provides offline `status`, `schema`, `preview`
and `configure` through the existing policy. It is absent from the ordinary HTTP
gateway and refuses HTTP calls. Local schema now exposes `owned_origin_coverage`
for desktop, Studio, UI and MCP, retaining the existing CLI map. The final source
selection passed **20 Python MCP and 30 UI tests**; the added import-failure check
preserves exactly one original action. The corrected TypeScript/Vite build passed.
A copied built-Chromium fixture passed **14 checks**, and a real stdio
`ClientSession` with the maintained CLI passed **22**, including opt-out after
the fake workspace was shut down. Only isolated fixtures enabled local counters;
the schema version and unavailable source collection gate are unchanged.

The [validation report](../validation/2026-10-24-telemetry-aggregates.md) retains
the initial checks, original build failure and verified browser cleanup. A later
**3.27 MiB** component phase diagnostic does not replace the original **3.61 MiB
versus 2 MiB** resource gap or establish resource acceptance. At that checkpoint,
background/updater owners were still unfinished. Optimization, sender/collector,
final-send cancellation and all-platform
release acceptance remain open. Source inventory and integration qualification
are not established by these journey receipts.

The next [maintenance source batch](anonymous-product-telemetry-catalog.md#fresh-local-maintenance-coverage)
adds the fifth `owned_origin_coverage` map, `maintenance`. Fresh automatic desktop
source/capture work and the standalone connector entrypoint own their observed
work; empty successful scans, paused work, explicit Sync continuations,
remote-requested/host-managed scans, reusable sync and server-worker activity are
excluded. Numeric work/queue/store-size fields and coarse own-process resource
samples do not export source history or mixed-host totals. Native RSS/budget
requires a real child callback; headless RSS is an ending observation, with its
own CPU-time delta and configured capture limit where available.

Automatic updater download, verification and retries form one observed cycle.
Current-version and safety polls add no use; unfinished cycles are discarded on
quit. Installer handoff is only `accepted`, with no installed-version claim or
shutdown flush/wait. Its optional snapshot can wait up to **25 ms** before the
original guarded action. Existing native request acknowledgements retain separate
workflow categories. Python now commits each workflow pair in one current-policy
transaction, and the native writer reuses statements within that transaction;
the generation fence and per-observation limits remain unchanged.

The [validation report](../validation/2026-10-24-telemetry-aggregates.md) records
separate **41- and 49-test Python passes**, **104 source-controller and 20 updater
Node passes**, and **nine Electron store passes with two Windows skips**. The
original runner failures remain preserved. A **3.09 MiB** component diagnostic
after optimization still exceeds the unchanged **2 MiB** target and does not
replace the prior 3.61/3.27 MiB observations. The corrected isolated app-main
probe then recorded **1.19 MiB** added RSS across 32 paired workflows after
`client-ready`. This headless activation diagnostic does not qualify whole-app,
all-platform or CPU overhead, or replace the cold measurements. The background
batch's final builds/input inventory, main integration and source CI passed;
full resource/platform acceptance remains pending.
Those earlier checks did not qualify the later senders or application-owner
wiring. Collection is still unavailable, no collector is deployed, and V08
remains Building.

Saved source checks passed **10 policy tests** after the opt-out revision change,
**12 native bridge/operator tests, 26 web/CSP tests and seven browser policy
tests**; frontend and Electron TypeScript builds passed. The built
browser's **19-check core privacy journey passed at 00:51:17 UTC on 24 October**:
default/disclosure gating, persistent and cross-tab/offline opt-out, re-enable,
preview, storage loss/damage, GPC and small-screen access, without external
requests or a workspace API. The original driver's compact-JSON parsing failure
remains preserved; acceptance inspected the completed journey without replaying it.
Its receipt SHA-256 is
`758778a6590ad1925f050def54c63df0eadefdd5bf7a77235cb07783eba8d93f`.
Eight further actual-browser checks passed for served company restriction,
opt-out precedence, unavailable tab coordination, denied storage reads and failed
writes with fixed errors. [Source-input qualification](../validation/2026-10-24-telemetry-controls.md)
subsequently passed at **01:12:30 UTC**, including final browser journeys and
actual wheel controls with matching disclosure resources. These source
observations do not establish all-six-native, collector, anonymity or release
acceptance.

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
Linux/Windows x64 comparisons passed; the new direct macOS path remains pending.

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
