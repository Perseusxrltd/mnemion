# Product telemetry privacy controls

**V08 remains in development; updated 26 October 2026.** Product
telemetry is unavailable. Basic choice, status and format controls shipped in
4.46.13. Installed 4.46.22 controls also have evidence for review-mode changes
and persistence, as described below. Saving an enabled preference does not start
collection: `collection_available`
and `effective_enabled` remain `false`, with no destination or release route.
Use [release status](../RELEASE_STATUS.md) to check availability in your version.

The source includes local choice, disclosure, a fixed measurement catalog,
bounded queues and senders, and selected app, agent and maintenance hooks.
A [dedicated collector](../implementation/anonymous-product-telemetry-collector.md)
also has passing isolated TLS checks; it has not been deployed or qualified as
a production destination. Full resource, transport/privacy and installed-platform
acceptance remain unfinished. The [implementation contract](../implementation/anonymous-product-telemetry.md)
preserves the detailed source evidence and remaining scope.

The [4.46.13 privacy-control qualification](../validation/2026-10-26-44613-native-acceptance.md)
passed all six installed targets: Linux, Windows and macOS, each on x64 and
ARM64, with 64 required fields per target. Windows ARM used an ARM desktop with
emulated x64 engine/database components. The version is published after artifact
verification, and all six public automatic-update targets passed. This qualifies
the controls, not active telemetry or full V08; actual user installation checks
remain separate.
The earlier [five-target 4.46.12 evidence](../validation/2026-10-26-telemetry-preview.md)
remains retained with that candidate's original failures.

The [4.46.22 installed review-control evidence](../validation/2026-10-26-telemetry-installed-review.md)
passes eight telemetry fields across all six targets. It covers format/default
controls without consent, app/native preference and review-mode changes, focus
refresh and opt-out/manual-mode persistence across a clean app restart. Five
targets retain their first-attempt artifacts; Mac ARM passed in the separate
capacity retry. No new app run was needed to qualify this evidence. Report
staging, approval and delivery, later owners and 4.46.25 installed behavior remain
outside this acceptance.

## In the app

Open **Privacy & product telemetry** from the connection screen or visit
`/privacy`. The page works before workspace sign-in and without a live memory
service. The desktop bundles it; a browser still needs the app assets available
to use the page offline.

**Share anonymous product statistics** changes the saved preference, which
defaults to enabled. **Disable product telemetry** saves an opt-out and clears
pending local aggregates. **Refresh privacy status** reads the current choice.
**Show report format** displays a fixed synthetic four-byte example as Base64.
Published 4.46.13 uses `AQAHAA==` (`01 00 07 00`); the newer wire v2 source uses
`AgAHAA==` (`02 00 07 00`), marked automatic. It is not sampled from your counts or
presented as a queued or sent report. Opening it makes no reservation, consumes
no queue or delivery allowance, acknowledges no disclosure and sends no telemetry.
No actual outgoing packet is inspected. Expand **Workflow coverage and exclusions**
to inspect the source coverage and explicit privacy exclusions. New source
provides a filterable [coverage inventory](../validation/2026-10-26-telemetry-workspace-selections.md):
93 of 94 categories have a declared measurement source. The separate
`update.verify` category remains unmeasured; verification stays part of download.
These counts describe catalog mappings, not complete screens, sensors or active
collection. Choose a feature family or **Unmeasured** to inspect the gaps. The
inventory is generated from Git source maps and checked for staleness at release.
Older versions that lack the inventory say so instead of implying full coverage.
The native `schema` and `preview` responses expose the same `workflow_coverage`
object for agents. Opening the browser view may load its bundled metadata asset;
it does not transmit usage. Any
**Private local aggregate preview** is a snapshot of permitted local counts at
the time it was opened, separate from the report example. Choice changes, status
refresh, window focus and cross-tab choice notifications clear the preview;
late responses cannot restore an older display.
The schema and numeric encoding exist; collection remains inactive. Selected
desktop/browser and native-operator actions now have source hooks. Remaining
workflow and resource/platform qualification are still unfinished.
A later build capable of collection must present its current disclosure before
anything can be sent; today's enabled preference cannot acknowledge that future
destination.

[Optional report review](#optional-report-review) builds on the bounded clock
foundation. The 4.46.22 installed evidence qualifies mode selection and empty
report controls; source/component checks retain their separate scope. This work
is absent from 4.46.13. The current unavailable collection gate still prevents
staging an actual report, and full acceptance remains open.

**Telemetry connection settings** offers `auto`, `unmetered` and `metered`.
Automatic mode pauses delivery when metering is unknown; an unmetered declaration
resolves only that uncertainty, while metered mode pauses delivery. Detected data
limits, resource pressure and privacy restrictions still take priority. The
choice persists without a network name or address. Editing it keeps an existing
opt-out and does not acknowledge an unseen disclosure.

The new [native network-admission source](../validation/2026-10-25-telemetry-native-conditions.md)
can read OS cost flags on supported Windows, Linux and macOS systems. Later
[macOS Python/Node component probes](../validation/2026-10-25-telemetry-native-conditions.md#macos-component-follow-up)
passed; complete network-admission/resource qualification under installed
Electron remains open.
Automatic mode keeps delivery paused whenever OS cost remains unknown.
Declaring an unmetered connection cannot override an OS-reported metered or
constrained path. These checks run only for an eligible, already-awake opportunity;
they add no idle sampler, Internet connectivity probe or network-setting change.
They are included in 4.46.13 and do not activate collection. Focused source checks and
actual Windows/Linux flag/deadline probes completed; these do not qualify an
installed telemetry release. The measured Windows Node and Linux Electron
components still exceed the 2 MiB full-feature RSS target. Full platform/resource
qualification remains pending.

New source adds a [compiler-free Windows cost reader](../validation/2026-10-26-telemetry-headless-network.md)
when the packaged helper is absent. Its Windows x64 component comparison passed;
this follow-up is excluded from released 4.46.13. A present broken helper is
never bypassed. Linux/macOS source installs without the helper still require an
explicit unmetered choice to resolve unknown cost, subject to every other veto.

The [producer-overhead source follow-up](../validation/2026-10-25-telemetry-producer-overhead.md)
reduces repeated local database work when optional measurement is already denied
or capped. It does not cache permission to collect or change your saved choice.
Its desktop/TLS diagnostic still exceeded the 2 MiB full-feature RSS target when
opted out and when enabled; collection remains unavailable.
The subsequent [real-memory diagnostic](../validation/2026-10-25-telemetry-memory-profile.md)
completed fixed save/fetch/search transactions in all three variants. Its
resource measurements and the repeated synthetic diagnostic do not qualify the
unchanged limits. Later [compiled renderer journeys](../validation/2026-10-26-telemetry-sqlite-cleanup.md)
completed the actual renderer/IPC flow; full resource/platform acceptance remains
open.

The [25 October denial-I/O follow-up](../validation/2026-10-25-telemetry-denial-io.md)
can reuse an already observed denial for up to **250 ms**. In a collection-capable
build, newly re-enabled work may still lose optional samples during that interval;
your saved choice and status use fresh checks. It cannot enable collection or bypass
the checks on accepted work. Collection remains unavailable in this source build.
Its source checks and isolated burst completed; that enabled RSS observation
exceeded the 2 MiB target. Full resource/platform qualification remains open.

The exclusions cover unowned remote clients, client-derived server jobs,
mixed-user host totals, private operational records, polling/replay, privacy
controls and unavailable sensors. They restrict product collection; the related
connectors and memory workflows retain their full requirements. There is no
collection event for inspecting or changing privacy settings.

The desktop and native agent share the preference under the same OS account and
application data configuration. A browser stores its own choice for that site;
it does not synchronize it with other browsers, desktop installations or remote
hosts. Global Privacy Control keeps browser collection off. A browser without
the required coordination between tabs also keeps it off. Clearing site storage
removes the saved choice and requires fresh disclosure; no identifier or
fingerprint is used to recover it.

<a id="optional-report-review-unreleased-source"></a>

## Optional report review

In **Review reports before sending**, select **Pause reports for manual review**
if you want to approve individual reports. You can select this before granting
collection permission. Automatic delivery remains the default.

In the qualified 4.46.22 installed checks, this choice saved without granting
permission. Inspect/approve/discard stayed disabled with no report available,
and manual mode survived opt-out and restart. Those checks did not stage,
approve or send a report.

Once collection is permitted under its current disclosure, authorized local
observations exist and the allowance is ready, **Inspect next report** stages
one exact four-byte body and shows its Base64 and decoded fields. This explicitly
consumes the current pending snapshot, without spending delivery allowance.
Inspecting the held report again preserves its bytes and original expiry: at
most 15 minutes, possibly less if the observations expire sooner.

**Approve this report** permits one eligible attempt with those bytes. The app
or browser can offer it to its existing awake delivery owner; approval is not a
delivery receipt and cannot override permission, company policy, metering or
resource checks. Later reports remain paused. **Discard report**, expiry and
invalidation also keep manual mode selected. Leaving manual review explicitly
clears the held report and restores automatic delivery opportunities.

The consumed snapshot is not restored. New observations, contribution limits
and already spent delivery budgets are preserved. Closing all browser tabs
prevents reuse of that browser review. Refresh/focus clears displayed bytes;
inspect again to revalidate and reveal a still-valid report.

New [wire v2 source](../validation/2026-10-26-telemetry-review-selection.md) marks
the packet as reviewed before showing it. Its body is fixed within your
permitted metric groups and contains no categorical measurement or random draw.
Reviewed reports contribute only to
the coarse overall report-volume range; feature percentages and their sample
counts use automatic reports. The preview exposes `report_selection`,
`aggregation` and null privacy-loss fields for manual review, with
`privacy_bound_scope: "fixed_body_for_permitted_groups"`. The automatic
`ln(3)` randomization bound is not a guarantee for human inclusion, policy
choices, participation or network anonymity.
This source correction is excluded from frozen 4.46.14. Interactive privacy,
utility and installed qualification remain open despite the passing final
fixed-body source and component checks linked above.

The Chromium check used synthetic observations and an in-memory capability;
it verified controls without sending a report or spending a delivery attempt.
It does not qualify production collection, network delivery or installed apps.

## From a native agent or terminal

A runtime built with these source controls accepts one JSON line on private
stdin, without a memory API connection, credentials or a running desktop:

```sh
printf '%s\n' '{"action":"schema"}' | mnemion-service telemetry
printf '%s\n' '{"action":"status"}' | mnemion-service telemetry
printf '%s\n' '{"action":"preview"}' | mnemion-service telemetry
```

`schema` describes the available local actions, disclosure and `measurement_catalog`,
including fixed numeric buckets, contribution limits and exclusions. It also
returns `owned_control_coverage`, the full owned-CLI operation map, and
`owned_origin_coverage` for the desktop, Studio, UI, MCP and maintenance boundaries.
It exposes the source delivery format as `transport_catalog`.
`transport_available` means that this build has a valid configured collector
route; it is separate from consent, current sending and successful delivery.
It remains `false` in the current unavailable build. Reading it neither
configures a destination nor probes the network.
`status` distinguishes `user_enabled`,
`effective_enabled`, `reason`, `storage`, `connection_mode`, company restriction, `revision` and
`store_generation`. The generation is a private local control token, never an
analytics identity or outbound field. Missing or supported legacy stores report
`null`; reading status does not silently initialize them.
Native `status` also exposes `delivery_budget`: fixed states, bounded attempt
counts and reserved-byte totals, without exact attempt times or private lease
tokens. These are local reservations, not measured traffic or successful uploads.
The budget state `ready` does not enable collection.
`preview` returns `outbound_state: "not_inspected"`, `outbound_body: null` and
`outbound_bytes: 0`, plus `illustrative_packet` with `kind: "synthetic_example"`,
`body_encoding: "base64"`, `body_base64: "AgAHAA=="` and `body_bytes: 4` in the
new wire v2 source; published 4.46.13 retains its wire v1 example above.
These example bytes do not identify the next outgoing packet. The null/zero
actual-body fields are not a traffic counter or proof that another owner has
no active attempt. The catalog is included; `local_aggregates` stays empty while
collection is unavailable. When present, local counts are a private snapshot,
not a serialized outbound report or event history. The
[format-preview evidence](../validation/2026-10-26-telemetry-preview.md)
retains the earlier component and five-target results; published 4.46.13 later
qualified all six basic-control targets. Full telemetry acceptance and the new
[actual-packet inspection requirement](../implementation/anonymous-product-telemetry.md#proposed-outbound-schema-and-payload-preview)
remain open. Success returns
`{"event":"result","ok":true,"result":...}`; refusal returns a fixed error code
with `ok: false` and exit status 2.

To save a choice, first read status. Use its `revision` as `expected_revision`
and its `store_generation` as `expected_generation`. This opt-out example shows
a fresh store's `0`/`null` pair:

```sh
printf '%s\n' '{"action":"configure","enabled":false,"expected_revision":0,"expected_generation":null}' | mnemion-service telemetry
```

To save an enabled preference, use `enabled: true` and both values from the
latest status. Pass the returned generation through private JSON stdin; do not
invent or reuse a token from another store.
Omit `disclosure_version` or use `0`: this build rejects a nonzero disclosure
acknowledgement with `telemetry_disclosure_unavailable` because no collection
destination is available. Enabling with an outdated revision or generation is
refused as `telemetry_choice_changed`; disabling remains allowed with stale values.
Every successful opt-out advances the revision, even if already disabled, so an
older enable request cannot override it.
Optional `connection_mode` accepts `auto`, `unmetered` or `metered`; omitting it
preserves the current choice. A stale opt-out also preserves a newer connection
choice. Explicit native configuration may wait up to 250 ms per busy SQLite
lock; producers and delivery keep zero lock waiting. A failed save still needs
inspection and is not a confirmed preference change.
A recreated store gets a different generation, so old queued work is refused
even if its revision number repeats. Valid legacy preferences preserve explicit
opt-out. A legacy enabled preference without a generation requires fresh
disclosure; an explicit supported choice creates its new local token.
A successful change clears pending aggregates and local contribution accounting,
so re-enabling cannot revive old data. The separate delivery allowance retains
spent attempts and cooldown across opt-out; changing a choice does not refund
it. These basic read and choice actions start no network activity. The desktop agent
exposes the same typed `telemetry.schema`,
`telemetry.status`, `telemetry.preview` and `telemetry.configure` actions without
requiring a workspace.

### Report actions in the new source

These actions are unavailable in released 4.46.13. Read `schema` and
`review_status` from a runtime built with the new source:

```sh
printf '%s\n' '{"action":"review_status"}' | mnemion-service telemetry
```

Headless Python can use the documented OS review clock without compiling a
helper when that helper is absent. A broken or unavailable packaged helper
continues to refuse review; this does not enable collection. Linux/Windows x64
and [macOS Intel/ARM64 comparison checks](../validation/2026-10-26-telemetry-report-review.md#compiler-free-headless-review-clock)
passed at component scope. They do not establish installed review or full
resource acceptance.

| Local action | Behavior |
| --- | --- |
| `review_status` | Read-only stored snapshot of mode, outcome, token and expiry; `packet` is null. It does not initialize, repair, migrate or verify current report eligibility. |
| `review_mode` | Set `mode` to `review` or `automatic`; selecting manual mode does not grant collection permission. |
| `inspect_report` | Stage or revalidate one report; only this explicit mutation returns its exact `packet`. |
| `approve_report` | Approve the current held report for one eligible attempt; the standalone CLI does not send or start an owner. |
| `discard_report` | Erase the held report and remain in manual mode, without restoring its snapshot or allowance. |

Every mutation requires `expected_revision` from `status.revision`,
`expected_generation` from `status.store_generation`, and `expected_review_token`
from `review.token` in the latest review response. Add `mode` only for
`review_mode`. These are private compare-and-set values, not report fields;
refresh after `telemetry_choice_changed` or `telemetry_review_changed`.
For a genuinely new store, selecting manual mode uses the initial `0`/`null`/`null`
values below; existing stores must use their actual returned values:

```sh
printf '%s\n' '{"action":"review_mode","mode":"review","expected_revision":0,"expected_generation":null,"expected_review_token":null}' | mnemion-service telemetry
```

Use the returned values for `inspect_report`, then the latest inspection values
for `approve_report` or `discard_report`. Check `message`, `review.outcome` and
`packet`; a successful command may report `no_observations`,
`collection_not_permitted`, `transport_unavailable` or `delivery_not_ready`
without creating a report. `consumed` means claimed, not confirmed delivery.
The native desktop equivalents use the `telemetry.` prefix on these same five
names. Native CLI approval arms the next existing awake owner; the app/browser
may offer that owner an opportunity immediately. None creates a background service.

## From local stdio MCP

A runtime built with the new source exposes `mnemion_telemetry` on its explicitly
configured **local stdio** connection. Call it with `{"action":"status"}`,
`{"action":"schema"}` or `{"action":"preview"}`. These controls work without a
reachable workspace service, use the local OS account's existing preference and
never generate a measurement. Schema describes the current disclosure; collection
remains unavailable, so a saved enabled preference does not activate analytics.

For the maintained stdio gateway, `configure` nests the choice. Read current
status first and use its revision/generation; this example is only for a fresh
store's `0`/`null` pair:

```json
{
  "action": "configure",
  "choice": {
    "enabled": false,
    "expected_revision": 0,
    "expected_generation": null
  }
}
```

The maintained choice also accepts `connection_mode` and disclosure version `0`;
zero does not acknowledge an unseen disclosure. The legacy stdio tool takes its
advertised choice fields alongside `action` instead. Follow the connected tool's
input schema and omit `disclosure_version` while collection is unavailable.
Enabling still needs current private revision and
generation; opt-out, company restriction and damaged-store behavior are the same
as the native controls above.

The new maintained local stdio tool also accepts the five report actions above.
Use `{"action":"review_status"}` for a stored snapshot. Mutations put the same
compare-and-set fields in `review`, with `mode` only for `review_mode`:

```json
{
  "action": "review_mode",
  "review": {
    "mode": "review",
    "expected_revision": 0,
    "expected_generation": null,
    "expected_review_token": null
  }
}
```

That example is only for a new store. Use current response values thereafter;
do not combine `choice` and `review`. The tool itself sends no statistics.

The tool is absent from the ordinary HTTP gateway. HTTP calls cannot change
local telemetry policy or acquire a measurement owner, even if the server has a
configured stdio key. Remote MCP/API credentials are not telemetry consent.
Imported legacy handlers and a caller-supplied `local_stdio` field do not grant
ownership. A **22-check actual stdio fixture journey passed**, including opt-out
after its fake workspace shut down. Its local counters were enabled only in the
isolated test process; source collection remains unavailable and native release
acceptance remains open. The local schema now includes five ownership maps.

## Owned headless API calls

The source [agent-control CLI](../service/agent-control.md) now has optional hooks
only at `mnemion-control call`. Its map accounts for all **161 API operations**:
**82 eligible actions and 79 explicit exclusions** for inspection, producer or
recovery transport, configuration previews and session maintenance. The regular
call still uses its configured service; its generation/revision snapshot and
privacy choice govern only the optional measurement. Generic SDK and remote MCP
calls do not acquire an owner. No product data is collected in this build.

Keyed writes count only when the service confirms a fresh receipt with
`X-Mnemion-Idempotency: new`. Cached, unknown or older-server receipts are
discarded from measurement without retrying the action. Async acknowledgements
remain `accepted`; they do not prove background completion. Only fixed enums,
duration and permitted numeric response payload bytes reach the encoder. Payload
bytes are not wire traffic, and optional measurement errors do not change the
operation's result. See the [catalog](../implementation/anonymous-product-telemetry-catalog.md#owned-headless-control-coverage)
for the fixed librarian/embedding selectors and per-operation exclusions.

## Desktop and Studio ownership

Selected desktop controls, fresh native-operator actions and Studio UI methods
now have optional source hooks. The desktop/native agent uses the shared private
OS-account store; the browser uses its own site policy. They retain the choice
and generation captured when work began and recheck them before recording. An
old action cannot regain permission after an opt-out and later re-enable.

Selecting a saved workspace now distinguishes opening it from switching away
from another verified workspace/account or the selected local workspace. Opening
the same profile with a fresh session still counts as open. This uses one original
choice and clock; only the fixed open/switch decision reaches telemetry. Failed
restores retain a failed-open observation. Automatic resume remains unmeasured,
and new connections, sign-in and local-open actions keep their existing labels.

Explicit app/native **Backup inventory** now owns a backup-list observation when
the bounded list operation returns successfully. This does not prove the listed
backups are valid, restored or delivered to cloud storage. The observer does not
read the returned contents; status/polls and reusable helpers remain unmeasured.
These [source changes](../validation/2026-10-26-telemetry-workspace-selections.md)
passed focused checks and builds; installed-platform acceptance remains separate,
and collection stays inactive.

Explicit conversation preview in the app/native agent and standalone
`--capture-control` action `preview` now own `capture.preview`. Success means the
bounded preview returned, even if some files or catalog details were unavailable;
it does not mean capture was configured or delivered. The preview reads local
samples for you, but its content, paths and configuration hash are not telemetry.
Standalone capture pause owns one `capture.pause` acknowledgement. The separate
`--inspect` path, status, key generation and telemetry's own privacy/format-preview
controls remain unmeasured. Generic source pause/resume keeps its existing label.

The reusable SDK does not collect product telemetry. Its response-bound receipt
metadata lets the Studio wrapper exclude replayed or uncertain keyed writes;
generic SDK/API requests, polling, privacy controls and unowned continuation
transports remain unmeasured. Async acknowledgement is not completion. See the
[explicit ownership maps](../implementation/anonymous-product-telemetry-catalog.md#owned-desktop-native-operator-and-studio-coverage)
for the selected actions and exclusions. Hooks and sender components exist in
source, while production collection remains inactive and no production collector
is qualified or enabled. The UI map adds five
browser connection actions and 11 selected legacy Studio methods, with 18 legacy
exclusions. Browser hooks skip desktop connections already owned by IPC, respect
company sign-in cancellation and inspect only reviewed boolean result flags.
The **14-check copied built-browser journey passed** for connection, password
sign-in, logout/disconnect and legacy search, including cross-tab opt-out during
a held reply. Only the copied fixture enabled counters; it used a fake loopback
API. Selected automatic source/updater owners are described below; other
autonomous-work ownership remains unfinished.

## Automatic local work

The source now has optional owners for fresh automatic desktop scans and
standalone source/capture work. Empty successful scans and paused work add no
use. Explicit Sync continuations, remote-requested or host-managed scans,
reusable sync helpers and server-worker activity are excluded. Existing request
acknowledgements remain separate from observed maintenance outcomes.

For an owned capture cycle, no locally accepted items plus a verified positive
fresh stored count selects `capture.deliver`; accepting local items selects
`capture.collect`, including mixed collection/delivery work. This keeps one owner
and the whole cycle's outcome and latency. Completed cycles without fresh work
add no use. Incomplete or denied cycles keep their existing outcomes; an unknown
fresh count stays unavailable, and replayed receipts or saved history do not
become fresh usage. The [source validation](../validation/2026-10-26-telemetry-capture-actions.md)
does not qualify installed platforms or activate collection.

Automatic desktop update download, verification and bounded retries form one cycle.
Current-version and safe-restart polls add no use. An unfinished cycle is
discarded on quit, and installer handoff is only `accepted`; it does not prove
the new version installed. Its optional snapshot can wait up to **25 ms** before
the original guarded action. There is no shutdown flush or wait for telemetry.

The automatic managed-server watcher has a separate source boundary for fresh
staging, compatible apply and rollback. It uses its **own OS-account acknowledged
telemetry preference**, not your browser or remote operator setting. Use the
existing offline local controls under the same account and application-data
configuration to inspect or change that choice. Starting the watcher does not
initialize, repair or acknowledge it. The current unavailable release contract
cannot activate collection or acknowledge an available destination.

The live watcher observes service readiness and rollback it actually performs.
Interrupted work is discarded, without a result reconstructed from private
journals. A later watcher may offer an existing bounded queue or approved held
report during its normal five- or ten-second waits, at most once per minute in
that watcher lifetime. No independent timer or thread is added; delivery closes
before update work resumes, and shutdown does not flush it. Policy, metering,
pressure, review expiry and spending can still refuse any opportunity. This is
not a promise to send within a minute or qualification of every installed host.

Source observations use only reviewed numeric work/queue/store-size buckets and
coarse own-process resources. Desktop RSS is the maximum supplied by that child
worker's actual callback, with its configured limit; no sample means unavailable.
Standalone RSS is measured at the end of its work, alongside its own CPU delta
and capture budget where available. These are not whole-host totals or proof of
the telemetry component's overhead. The same saved choice and generation fence
govern them, and collection remains unavailable in the current build.

## Company restriction and damaged settings

The native policy reads an optional administrator file:

| Platform | Policy file |
| --- | --- |
| Windows | `%PROGRAMDATA%\Mnemion\telemetry-policy.json` |
| macOS | `/Library/Application Support/Mnemion/telemetry-policy.json` |
| Linux | `/etc/mnemion/telemetry-policy.json` |

For example, `{"schema_version":1,"enabled":false,"metric_groups":[]}` disables
collection. Policy may narrow the disclosed groups; it cannot override a user
opt-out. The service-served browser app receives an initial restriction with its
page. The new source also checks `/studio/telemetry-policy` on that page's own
origin before each already-reserved report, without credentials or a referrer.
It only tightens permission until reload; a relaxed response cannot enable a
group that this page already lost. Reading privacy status does not fetch or
relax company policy. An unreadable or invalid response prevents the report,
and local choice/pressure are checked again before sending. A remote policy
change after that read is not atomically ordered with the later report. See the
[refresh checkpoint](../validation/2026-10-24-telemetry-company-refresh.md) for
current evidence and remaining production privacy qualification.

Unreadable, damaged or inaccessible local settings fail closed with
`storage_unavailable`; status is not confirmation of a saved preference in that
state. A failed save is not a successful opt-out or re-enable. There is no
automatic settings repair or repair action yet. Do not erase settings as a
generic repair: that can erase an explicit opt-out. After a transient storage
or lock problem is resolved, refresh status and confirm the saved choice.

On Windows, explicit native configuration creates a private settings directory
and database. Native Python and the app both reject permissions that expose the
store to other accounts. The app's small owner/DACL helper only inspects existing
permissions; it does not repair them. On POSIX systems the store uses owner/mode
checks. A missing, linked or unsafe database is never replaced by the measurement
path. The [source validation report](../validation/2026-10-24-telemetry-aggregates.md)
retains preliminary failures and the later passing native-store/Studio checks.
The later five-target control qualification is linked above; full installed
delivery and resource acceptance remain open.

Optional product telemetry is separate from private workspace operational and
security records. These controls do not change memory access or disable those
records. The [full V08 contract](../implementation/anonymous-product-telemetry.md)
and [versioned catalog](../implementation/anonymous-product-telemetry-catalog.md)
retain app, agent, headless and remote-workflow coverage. Remaining workflow
qualification, other autonomous-work ownership, installed sender integration,
production collector deployment and anonymity
proof remain unfinished. Expiry
prunes on activity. Local generation checks cannot detect a whole-machine
snapshot rollback that restores both the old token and choice; final sender
cancellation still needs full-feature acceptance. See the
[privacy policy](../service/privacy.md) for existing service and model traffic.
An earlier exploratory Electron component measurement exceeded the existing **2 MiB**
added-RAM target; optimization and whole-app/all-platform resource qualification
remain unfinished. No target has been relaxed by these source checks.
A later 3.27 MiB phase diagnostic is not resource acceptance and does not replace
the retained 3.61 MiB result against the 2 MiB target.
The subsequent 3.09 MiB component observation and corrected **1.19 MiB** headless
app-main activation probe remain diagnostic. The latter does not replace the
cold measurements; whole-app, all-platform and CPU qualification remain open
against the same resource contract.

The [completed attribution checkpoint](../validation/2026-10-26-telemetry-attribution.md)
retains all six original journeys, each with 387 successful API requests.
Both enabled matched main-process maxima exceeded 2 MiB; profiled CPU results
do not establish resource acceptance. The next investigation is cold
initialization and storage-runtime ownership, with no repeated benchmark or
budget revision selected. The **2 MiB RSS / 0.5% CPU** gates remain unchanged
and unaccepted; exact-next-packet inspection, production privacy and complete
native/web acceptance are still open.

The [latest fixed resource follow-up](../validation/2026-10-26-telemetry-allocation-followup.md)
completed six source-app cases without model calls. Both enabled main-process
matched RSS maxima and ending differences remained above 2 MiB. Other process
roles and opted-out comparisons are retained; this establishes no causal
improvement or resource pass. The resource limits and inactive collection choice
remain unchanged.
