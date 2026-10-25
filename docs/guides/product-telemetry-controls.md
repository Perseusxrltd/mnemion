# Product telemetry privacy controls

**Source checkpoint, 25 October 2026; V08 is Building.** Local choice, disclosure,
catalog, aggregate queues and selected owned CLI, desktop/native-operator,
Studio/browser, local stdio and selected maintenance hooks are implemented in
source. Bounded senders and opportunistic owners also exist in source, but there
is no active product sender or deployed collector: `collection_available` is
`false`, the destination and release route address are `null`, and
`effective_enabled` stays `false`. Saving an enabled preference does not activate
analytics. The core browser journey passed **19 checks at 00:51:17 UTC**, followed
by **eight browser policy/fault checks**. [Source-input qualification](../validation/2026-10-24-telemetry-controls.md)
passed at **01:12:30 UTC**. The later [catalog/aggregate checks](../validation/2026-10-24-telemetry-aggregates.md)
include a nine-check browser catalog journey; fresh package and native release
acceptance for that batch remain pending.
The later actual Chromium generation journey passed **11 checks**, including
stale UI conflicts, preserved legacy opt-out and a 390-pixel layout. This remains
source-browser evidence, with no active collection or native release acceptance.
The later copied built-browser journey passed **19 owned-search/opt-out checks**;
only its isolated fixture enabled local counters. Source/build collection remains
unavailable. Native Windows source-store checks now passed **11 with zero skips**,
without qualifying a packaged telemetry release.
These controls and this documentation update are excluded from the isolated
4.46.6 dependency-security release. The [contract](../implementation/anonymous-product-telemetry.md)
records the dated source evidence and full remaining scope.
The separate [delivery components](../implementation/anonymous-product-telemetry-delivery.md)
are also source-only: their packet encoder and private weekly publisher do not
enable sending. An isolated **12-check plain-loopback HTTP journey passed**;
this did not enable product collection or qualify TLS/provider logging. The later
[shared native/Python budget](../implementation/anonymous-product-telemetry-budget.md)
has source reservation and cancellation controls, with focused checks passed
and two Windows-only ACL cases skipped. Deployed ingress, resources/platforms
and installed delivery acceptance remain open.

The later [application-owner checkpoint](../validation/2026-10-24-telemetry-app-owners.md)
adds connection controls and already-awake delivery owners; its actual Chromium
fixture passed 19 assertions with synthetic CPU admission. The subsequent
[company-policy refresh](../validation/2026-10-24-telemetry-company-refresh.md)
adds a fresh restriction check before each reserved browser attempt. Its focused
checks and **20-assertion Chromium journey on 25 October** passed, with seven
policy reads and one report. CPU admission was synthetic; fixture cleanup and
the frontend build passed. Neither checkpoint activates collection or qualifies
public ingress, sensors or a telemetry release.

## In the app

Open **Privacy & product telemetry** from the connection screen or visit
`/privacy`. The page works before workspace sign-in and without a live memory
service. The desktop bundles it; a browser still needs the app assets available
to use the page offline.

**Share anonymous product statistics** changes the saved preference, which
defaults to enabled. **Disable product telemetry** saves an opt-out and clears
pending local aggregates. **Refresh privacy status** reads the current choice.
**Show payload preview** currently reports no queued request, a null outbound
body and zero outgoing payload bytes. Expand **Workflow coverage and exclusions**
to inspect the fixed **15 families, 94 operations and seven privacy exclusions**.
The schema and numeric encoding exist; collection remains inactive. Selected
desktop/browser and native-operator actions now have source hooks. Remaining
workflow and resource/platform qualification are still unfinished.
A later build capable of collection must present its current disclosure before
anything can be sent; today's enabled preference cannot acknowledge that future
destination.

**Telemetry connection settings** offers `auto`, `unmetered` and `metered`.
Automatic mode pauses delivery when metering is unknown; an unmetered declaration
resolves only that uncertainty, while metered mode pauses delivery. Detected data
limits, resource pressure and privacy restrictions still take priority. The
choice persists without a network name or address. Editing it keeps an existing
opt-out and does not acknowledge an unseen disclosure.

The new [native network-admission source](../validation/2026-10-25-telemetry-native-conditions.md)
can read OS cost flags on supported Windows and Linux systems. Its macOS path is
written but not yet compiled or qualified. A source/pip installation without the
compiled helper remains unknown, so automatic mode keeps delivery paused.
Declaring an unmetered connection cannot override an OS-reported metered or
constrained path. These checks run only for an eligible, already-awake opportunity;
they add no idle sampler, Internet connectivity probe or network-setting change.
They remain unreleased and do not activate collection. Focused source checks and
actual Windows/Linux flag/deadline probes completed; these do not qualify an
installed telemetry release. The measured Windows Node and Linux Electron
components still exceed the 2 MiB full-feature RSS target. macOS and full
platform/resource qualification remain pending.

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

## From a native agent or terminal

A runtime built with these source controls accepts one JSON line on private
stdin, without a memory API connection, credentials or a running desktop:

```sh
printf '%s\n' '{"action":"schema"}' | mnemion-service telemetry
printf '%s\n' '{"action":"status"}' | mnemion-service telemetry
printf '%s\n' '{"action":"preview"}' | mnemion-service telemetry
```

`schema` describes the four local actions, disclosure and `measurement_catalog`,
including fixed numeric buckets, contribution limits and exclusions. It also
returns `owned_control_coverage`, the full owned-CLI operation map, and
`owned_origin_coverage` for the desktop, Studio, UI, MCP and maintenance boundaries.
It exposes the source delivery format as `transport_catalog`, with
`transport_available: false`; no destination is configured by reading it.
`status` distinguishes `user_enabled`,
`effective_enabled`, `reason`, `storage`, `connection_mode`, company restriction, `revision` and
`store_generation`. The generation is a private local control token, never an
analytics identity or outbound field. Missing or supported legacy stores report
`null`; reading status does not silently initialize them.
Native `status` also exposes `delivery_budget`: fixed states, bounded attempt
counts and reserved-byte totals, without exact attempt times or private lease
tokens. These are local reservations, not measured traffic or successful uploads.
The budget state `ready` does not enable collection.
`preview` returns `outbound_body: null`, `outbound_bytes: 0` and
`transport_available: false`, plus the catalog and an empty `local_aggregates`
list while collection is unavailable. A decoded local aggregate preview is
private inspection, not an outbound payload or event history. Success returns
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
it. Reading or changing these controls starts no network activity. The desktop agent
exposes the same typed `telemetry.schema`,
`telemetry.status`, `telemetry.preview` and `telemetry.configure` actions without
requiring a workspace.

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

The reusable SDK does not collect product telemetry. Its response-bound receipt
metadata lets the Studio wrapper exclude replayed or uncertain keyed writes;
generic SDK/API requests, polling, privacy controls and unowned continuation
transports remain unmeasured. Async acknowledgement is not completion. See the
[explicit ownership maps](../implementation/anonymous-product-telemetry-catalog.md#owned-desktop-native-operator-and-studio-coverage)
for the selected actions and exclusions. These hooks remain inactive: no sender
is active, and no deployed collector or production collection is available. The new UI map adds five
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

Automatic update download, verification and bounded retries form one cycle.
Current-version and safe-restart polls add no use. An unfinished cycle is
discarded on quit, and installer handoff is only `accepted`; it does not prove
the new version installed. Its optional snapshot can wait up to **25 ms** before
the original guarded action. There is no shutdown flush or wait for telemetry.

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
retains preliminary failures and the later passing native-store/Studio checks;
Electron packaging and all-six-native acceptance remain open.

Optional product telemetry is separate from private workspace operational and
security records. These controls do not change memory access or disable those
records. The [full V08 contract](../implementation/anonymous-product-telemetry.md)
and [versioned catalog](../implementation/anonymous-product-telemetry-catalog.md)
retain app, agent, headless and remote-workflow coverage. Remaining workflow
qualification, other autonomous-work ownership, installed sender integration,
deployed collector and anonymity
proof remain unfinished. Expiry
prunes on activity. Local generation checks cannot detect a whole-machine
snapshot rollback that restores both the old token and choice; final sender
cancellation still needs full-feature acceptance. See the
[privacy policy](../service/privacy.md) for existing service and model traffic.
An exploratory Electron component measurement exceeded the existing **2 MiB**
added-RAM target; optimization and whole-app/all-platform resource qualification
remain unfinished. No target has been relaxed by these source checks.
A later 3.27 MiB phase diagnostic is not resource acceptance and does not replace
the retained 3.61 MiB result against the 2 MiB target.
The subsequent 3.09 MiB component observation and corrected **1.19 MiB** headless
app-main activation probe remain diagnostic. The latter does not replace the
cold measurements; whole-app, all-platform and CPU qualification remain open
against the same resource contract.
