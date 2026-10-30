# Anonymous product telemetry — V08

**Building/source implementation; current checkpoint 30 October 2026.** V08
retains the full scope in the [66-requirement inventory](../PRODUCT_REQUIREMENTS.md);
all 66 requirement texts and states are unchanged. The
[shared disclosure](../../mnemion/product_telemetry/disclosure.json) remains
`collection_available: false` with `destination: null`, and the
[release route](../../mnemion/product_telemetry/transport-route.json) has a null
address and an empty certificate-authority list. Source controls, owners,
senders and collector components exist.
**No production product collection or qualified anonymous ingress is active.**

The [local v3 systemd check](../validation/2026-10-30-telemetry-v3-systemd-local.md)
passed socket activation, TLS delivery, credential isolation and cleanup.
The [installed delivery journeys](../validation/2026-10-30-telemetry-installed-driver.md)
preserve the first two failures. Third run 41013868878 on `c8f75870` passed
scoped delivery on Linux x64 and both Macs: each completed 21 memory API calls,
one inspected 25-byte report and opt-out/manual-review persistence across two
launches. Fourth run 41022011070 on `497af0ab` selected only the two Windows
targets and Linux ARM64. Linux ARM64 passed the same scoped journey: 21 successful
API calls, one matching 25-byte report, all 11 review controls and persistence
across two launches. Fifth run 41028940251 on `d8dc845e` selected only Windows
x64 and ARM64. Windows x64 passed: 21 successful API calls, six admitted and
committed observations, one matching inspected 25-byte report, all 11 review
controls, two clean launches and persisted opt-out/manual-review mode. Sixth
run 41036977655 on `46d4f730` passed Windows ARM64: 21 successful API calls,
six admitted and committed observations, one matching inspected 25-byte report,
all 11 controls and opt-out/manual-review persistence across two clean launches.
All six targets have scoped passing evidence across four original sources;
this is not a complete passing matrix on one source.

The fourth run's Windows failures remain: each completed 9 successful API calls
but lost both snapshot admissions to the 25 ms deadline and sent no report.
Both native ACL checks succeeded in the below-50-ms bucket; those timings cannot
isolate ACL/process startup, IPC, scheduling or store-open latency. In the fifth
run, Windows ARM64 instead failed with `The installed privacy page did not open`
after 3 successful API calls, before any observation cycle or ACL check. That
stop neither reproduces nor clears its fourth-run admission failure.
The reviewed correction waits for the settled workspace before opening Privacy
and retains a bounded failure gate. The original ARM64 failure's cause remains
unproven; the corrected sixth journey passed without changing the 25 ms
admission deadline. The reviewed resource
controller now acknowledges each case before the next begins, reconciles all
collector packets and releases its input handle on completion. The combined
Electron and diagnostic frontend builds passed. Original installed resource
comparison [41039553671](https://github.com/Perseusxrltd/mnemion/actions/runs/41039553671)
on `15715800` ended in preparation failure on all six targets before any
workload: the controller checks the inactive installer against the active
baked source tree. All six logs record `ValueError: Native engine was frozen
from different source files`. Six artifact ZIP digests and 74 extracted files
were verified, with zero completed workload cases. All 36 placeholder receipt cases
incorrectly claim `owned.present` and `owned.launched`; those claims are rejected.
Receipt serialization is corrected: absent and withheld records stay absent,
metadata alone leaves launch unknown, and conversion from JavaScript to Python
preserves that state. The correction passed 19 focused Python checks and five
Node checks. Package-to-source binding remains in progress; its correction is
not yet accepted. The fixed 128-cycle workload, accounting and budgets
remain unqualified; the earlier delivery passes retain their scope.
Full installed, production and resource acceptance remain open;
there are no qualified fleet statistics. Public collection remains off and
production hosting unresolved. The
[Firefox/WebKit journeys](../validation/2026-10-30-telemetry-browser-journeys.md)
retain their original failures. The fourth run passed real memory actions,
matching inspected-report delivery, opt-out/reload persistence and cleanup in
both engines. This uses disposable loopback TLS and does not qualify production
trust, native Safari or fleet statistics. The
[owned-launch accounting source](../validation/2026-10-30-telemetry-owned-launch.md)
passed launch-ownership and cleanup checks on all six native targets. The first
owned Linux compiled-workload run, 41013901369 on source `c8f75870`, completed
768 cycles and 2,322 successful fixture API calls, delivered two reports totaling
50 bytes, and passed all cleanup. Its CPU/RSS observations remain descriptive:
polled terminal accounting counts stop at 96 despite functional proof of 128
cycles per case, and high-water coverage remains partial. It does not qualify
installed or all-platform overhead or the 8 MiB/0.5% resource budgets.

Release 4.46.55 includes the v3 clients, collector and private reporting tools.
Its installed controls have the scoped qualification below; production
collection stays off. The 25-byte report uses
[wire v3](../../mnemion/product_telemetry/wire-v3.json), described below and in
the [v3 reference](anonymous-product-telemetry-v3.md). Current publication and
public update results are maintained in [release status](../RELEASE_STATUS.md).
The earlier compiled-app
comparison, [run 40967691671](../validation/2026-10-29-telemetry-v3-resource.md),
failed the initial 2 MiB and 0.5% gates. The
[30 October budget revision](telemetry-resource-budget-2026-10-30.md)
sets an 8 MiB RAM allowance for new installed acceptance work, retaining the
0.5% CPU ceiling. No prior failure is rescored and no resource pass is claimed.
All 66 requirements stay.

The [4.46.13 installed privacy-control evidence](../validation/2026-10-26-44613-native-acceptance.md)
and public auto-update gates qualify their recorded release. The later
[4.46.22 installed review-control qualification](../validation/2026-10-26-telemetry-installed-review.md)
passes eight telemetry fields on all six targets: format/default/no-consent
controls, app/native choice and review-mode changes, focus clearing, zero recorded
delivery attempts, and opt-out/review-mode persistence across the probe's restart.
Five targets use fresh attempt-1 artifacts; Mac ARM alone uses its fresh
capacity-retry artifact from attempt 2. No new build, app run or model call was
needed for this evidence qualification. It does not qualify staged-report
approval/delivery, later owners or 4.46.25 installed behavior, resource/provider
privacy, actual PC/VPS upgrades or full V08. Consult the automatically maintained
[release status](../RELEASE_STATUS.md) for current availability.

The [4.46.55 installed-control qualification](../validation/2026-10-30-telemetry-v3-installed-controls.md)
now binds the same eight control fields to current v3 source and all six
original attempt-1 installer artifacts. It includes the exact 25-byte synthetic
preview and opt-out/manual-mode persistence across a clean restart, with no new
build or app run. These control-only checks do not qualify staging, approval or
delivery of an actual report; the later installed journeys above own that scoped
evidence. Resource and production ingress gates remain.

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

The [first-time setup source](../validation/2026-10-27-telemetry-setup-disclosure.md)
adds a local disclosure dialog on app entry when collection is available and
an enabled preference has not acknowledged the current disclosure. This includes
an updated disclosure; saved opt-outs, company restrictions, GPC and unreadable
state remain authoritative. The checkbox starts checked, but only **Save and
continue** explicitly saves it and, when enabling, acknowledges the displayed
version using its original revision/generation. An unchecked save or direct
**Disable product telemetry** saves an opt-out. **Not now**, Escape and the
details link leave the choice and acknowledgement unchanged.

`App.tsx` gates the lazy setup import and its status request on release
availability/destination, excluding privacy, help and OAuth-consent routes.
While displayed, focus/storage refreshes share one in-flight read. Completion
or dismissal removes those listeners and prevents further setup checks until the
next app load; no polling timer is added. The current false/null/null release with
empty CAs loads no setup UI and performs no setup status request. The current
SDK/frontend builds, 29 policy checks and ten compiled-browser UI checks passed.
A subsequent actual compiled Linux x64 Electron source-app journey passed ten
checks across two launches, including deferred disclosure without permission,
exact report review and opt-out/restart persistence. Its qualification binds
2,100 source files, 12 successful fixture API calls and one four-byte loopback TLS
report matching inspection, with fixture cleanup.
Existing installed evidence and all remaining privacy, resource and release
gates retain their original scope.

The [setup recovery follow-up](../validation/2026-10-27-telemetry-setup-recovery.md)
replaces hidden read failures and stale enable controls with visible retry,
continue and privacy-page choices. Uncertain save replies trigger a status read,
never an automatic write retry. The saved policy stays authoritative; a failed
UI read alone does not prove an existing enabled preference is off. All 11 actual
compiled-browser recovery checks, 29 policy-control tests and SDK/frontend builds
passed. These controlled native-reply fixtures do not qualify installed storage,
resources or full privacy acceptance.

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
and unmetered modes permit a bounded attempt on an unknown or unmetered
connection only when every other gate passes. Unknown cost stays unknown; it
does not establish free or unlimited data. Observed metering vetoes both modes,
and metered mode pauses delivery regardless of the observation. Python, desktop
and browser apply this rule at reservation and again at final send.
Omitting the field preserves it; stale opt-out retains a newer connection choice.
Changing it, or supplying disclosure version `0` through local stdio, does not
acknowledge unseen disclosure. No network name or address is stored.
Explicit native configuration may wait **250 ms per busy SQLite lock**, not
250 ms for the whole action. Producers/delivery remain nonwaiting; selected
desktop actions allow at most **25 ms** for an optional snapshot before the
original action.

The [app review and approval follow-up](../validation/2026-10-26-telemetry-app-review.md)
fixes an approved report being ignored after an earlier automatic preflight.
The shared app/browser owner preserves the automatic once-per-awake-minute
cadence and permits at most one additional explicit approval preflight per
minute. Only one copied policy stamp can wait for active cleanup; pause/close
clears it. Fresh eligibility, consent, spending, sensors and transport remain
mandatory, with no timer or idle wake added.

The completed compiled Linux x64 app journey passed **nine review checks**, with
two launches, three save/fetch/recall cycles, nine operations and 12 successful
HTTP requests. Exactly one accepted four-byte TLS report matched the inspected
body; opt-out, manual mode and spent allowance survived restart. All **2,172
source and compiled inputs** matched, and cleanup passed. Separately, **24 actual
Electron-runtime tests and 14 browser-source tests** passed without skips.
Original probe errors and approval failures are retained; no new resource run or
saving is claimed.

The later [compiled browser-app follow-up](../validation/2026-10-26-telemetry-browser-admission.md)
passed **ten review checks** across two launches and nine memory operations,
with **161 successful fixture HTTP requests including assets** and 2,185 matched
source/existing compiled inputs. One approved four-byte TLS report matched
inspection using real nominal pressure; cross-tab opt-out and restart persistence
passed. Browser ownership now carries cancellation through eligibility and sensor
startup; **134 browser-source tests** and the frontend build passed. Original
fixture failures and missing first Python cleanup receipt remain retained;
second/final cleanup passed. A disposable certificate SPKI exception leaves
production browser trust unqualified. Six installed delivery targets, whole-wire,
privacy and resource acceptance remain open.

### Owned observations and storage

The [versioned catalog](../../mnemion/product_telemetry/catalog.json) defines the
workflows, families, fixed numeric buckets and matching Python/TypeScript
coordinates. Only reviewed primitives enter encoding; event/input/result
objects, free text and identifying values do not. The generated
[coverage inventory](../../mnemion/product_telemetry/workflow-coverage.json) is
the canonical Git source for current category totals and mapping states
(`summary`) and declared-action totals and dispositions (`action_coverage.summary`).
The inventory is available in app/browser format inspection and native
schema/preview as read-only metadata. Release checks reject stale inventories.
A source mapping does not qualify every screen, sensor or installed client.

The [27 October catalog compatibility follow-up](../validation/2026-10-27-telemetry-catalog-compatibility.md)
adds `capture.split` and `models.test` in catalog version 2. Existing numeric
coordinates, stored meanings and contribution limits are preserved; the
four-byte wire format and collection permission are unchanged.
The earlier [27 October verification checkpoint](../validation/2026-10-27-telemetry-update-verification.md)
mapped **all 94 categories, with zero unmeasured**.
The preceding checkpoint mapped 93 categories, leaving `update.verify`
independently unmeasured, and listed 632 action rows: 360 mapped, 265 excluded
and seven delegated. Those counts remain historical.

The [action generator](../../deploy/telemetry_actions.py) independently reads
**eight shipped interfaces across seven checked owner categories**: the
maintained and legacy MCP interfaces share `local_stdio`. Other owners use
reviewed source-route maps. Missing mappings in those
interfaces remain visible as unmeasured even
when the category has another owner. Search, source/state filters and pages of
50 rows inspect fixed metadata without invoking actions or adding a producer.
The earlier update-verification checkpoint contained 634 rows, with 362 mapped;
the subsequent capture-administration additions did not change the 94 workflow
categories at that checkpoint.
The [desktop cancellation hotfix](../validation/2026-10-27-desktop-request-cancellation.md)
adds one delegated transport channel. Its local cancellation token is never a
measurement; the enclosing Studio action retains ownership.
The [27 October CLI outcomes checkpoint](../validation/2026-10-27-telemetry-cli-outcomes.md)
recorded **700 declared actions and fixed variants: 396 mapped, 294 excluded,
eight delegated and two unmeasured**, including 63 classic CLI rows: 32 mapped,
29 excluded and two paths then unmeasured (`split`, `llm test`). The later catalog
compatibility follow-up above supplies their dedicated boundaries; these earlier
counts remain historical.
Fixed preview/status/review/apply variants preserve opaque inputs and results;
selected new mutative or possibly early-return commands report unconfirmed completion.
`--no-telemetry` suppresses one invocation without changing saved policy, and
both automatic hook-mine subprocesses use it. Nested work adds no second owner.
The default `repair --dry-run` now stops after the collection count, before
extraction, backup, deletion or rewriting. Source qualification is 128 distinct
Python cases plus one browser-source preview check; SDK/frontend builds passed.
This creates no CLI sender, keepalive or installed acceptance. Hand-parsed
options, other entrypoints and actual call sites still need reconciliation.
The [earlier CLI checkpoint](../validation/2026-10-27-telemetry-cli-coverage.md)
retains its 688 total rows / 29 unmeasured and 51 classic rows; the preceding
637-row inventory also remains historical.
Earlier [Chrome verification](../validation/2026-10-26-telemetry-action-preview.md)
passed on changed compiled assets based on
`93eb300`, with package 4.46.19 metadata before 4.46.20 preparation. It confirmed
pagination, filters, delegation, on-demand loading and refresh clearing; the
linked report preserves that browser scope separately from the 4.46.22 source
additions, installed/native and production qualification.
Payload-byte observations are not whole-wire traffic measurements.

The [refused-result correction](../validation/2026-10-27-telemetry-refused-results.md)
stops Studio and legacy UI telemetry from classifying results, retry receipts or
errors when no observation was admitted. The action runs once outside the
optional-work catch; refusal, unavailable collection, failed reads and a timed-out
read preserve its original result or error. Late permission replies cannot revive
the skipped observation. Four original inspection regressions were reproduced;
all **53 owner/policy source tests** and the SDK/frontend builds passed. Existing
admitted observations and original generation/replay fences remain. This removes
known unnecessary local work without claiming a transmission defect, RSS/CPU
saving, installed qualification or a resource-budget pass.

Owners cover the control CLI, desktop/native operator, Studio/browser, explicit
local stdio, selected fresh maintenance and explicit local model preparation.
The control CLI classifies all
**161 operations: 82 eligible and 79 excluded across five reasons**. The catalog
records the detailed maps and remaining action-by-action coverage.

The [27 October capture-administration follow-up](../validation/2026-10-27-telemetry-capture-admin.md)
addresses two standalone app actions that used generic requests: approving a
capture policy change and confirming device-authorization revocation. The actual
buttons now use `changeCapturePolicy` and `revokeCaptureGrant` through the existing
Studio owner, mapping to `capture.configure` and `capture.remove`. Five capture
mutation boundaries expose response-local `new`/`replayed` metadata and require
`fresh_receipt`; replayed, missing or unknown metadata supplies no fresh use.
Generic SDK/HTTP remains unowned, and nested source enrollment/recovery keeps its
existing outer owners. No server telemetry owner is added.

The retained real PostgreSQL grant-ID race reproduction failed to reject a
binding inserted concurrently for another source. Current code rechecks the
actual source/device/policy binding and revoked state after insertion; revocation
also rereads state under the source lock. Qualification passed **106 distinct
Python tests, 22 SDK and 49 Studio/policy source checks**, with no Node skips;
SDK/frontend/Electron builds passed and **29 source inputs matched**. The agent
command layer now preserves valid response metadata without requiring an
`Idempotency-Key`, with retry authorization unchanged. The original grant-race,
five CLI and shared-type import build failures remain retained. The preceding
94-category/634-row declaration inventory did not prove these app call sites were
observed. Privacy, resource, wire, provider, aggregate and installed acceptance
remain open.

Explicit app/tray requests and standalone capture controls now have reviewed
[action boundaries](../validation/2026-10-26-telemetry-action-coverage.md).
All 13 capture controls are classified: eleven eligible actions and two
status/key exclusions. Explicit native/app conversation preview and standalone
`--capture-control` action `preview` now own `capture.preview`; standalone pause
owns one `capture.pause` acknowledgement. The separate `--inspect` path remains
unowned. Preview completion describes a bounded local inspection, not configured
capture or successful delivery; its content and source identity stay private.
Managed children and reusable helpers acquire no
second owner. Preference acknowledgements expose whether the save applied;
failed saves are not successful telemetry outcomes. Explicit `prepare-model`
and `librarian-models --prepare` commands now own `models.prepare`. The observer
receives only the fixed preparation kind; model/profile identifiers and normal
command output stay outside telemetry. Listing, registry helpers and nested
deployment/startup preparation acquire no owner. Model resource/sensor
qualification, installed rollback and complete interface/call-site coverage
remain open, alongside installed and resource acceptance gates. The action report preserves the
earlier 86-mapped/eight-unmeasured audit separately from this source follow-up.

The [4.46.22 workspace ownership follow-up](../validation/2026-10-26-workspace-telemetry-ownership.md)
passed **54 distinct Python and 26 Node tests**, plus Electron and frontend source builds.
Compiled workspace fixtures used a synthetic cipher and local stubs; they do
not qualify installed Electron or a real provider. The Python total includes one
real HTTP/PostgreSQL regression after correcting a stale live/saved-report
equality assertion; the original 4.46.21 CI failure is retained, with no runtime
change for that correction. The dispatcher and preview
share a reviewed map of all 72 preload request channels, including fixed
host/source variants and explicit inspection, privacy and transport exclusions.
Automatic `workspaces:resume` is excluded before observation/policy access;
explicit restore remains owned, and reset owns one `workspace.forget`
acknowledgement. At that checkpoint, workspace changes used the chosen explicit
connect, sign-in or open boundary, without a separate switch category. That
checkpoint did not include a managed-host rollback owner. The subsequent
host-update boundary below uses the host's own acknowledged policy; a remote
operator's preference and private journal backfill cannot provide it.
Catalog, wire-v2, disclosure and route bytes are unchanged.
Release preparation passed; native and production qualification remain pending.

The [4.46.25 saved-workspace follow-up](../validation/2026-10-26-telemetry-workspace-selections.md)
now lets only an explicit saved restore select `workspace.open` or
`workspace.switch`, retaining one original policy/generation snapshot and clock.
The verified, normalized endpoint/tenant/principal transition decides; a new
session handle for the same profile remains an open. App/native local-to-saved
selections are switches. Both choices retain the existing `accepted` outcome;
throwing restores retain failed `workspace.open` semantics.

One-use WeakMap metadata carries only the selection enum, outside JSON and saved
state. Cloned, unbranded or reused results cannot establish a new switch; automatic
resume clears the metadata and has no owner. New connect, sign-in and local-open
actions keep their existing labels. Explicit native/app backup inventory now
owns `backup.list` on controller success, without inspecting the returned backup
contents or claiming validity/cloud delivery. Status, polls and reusable helpers
remain excluded. At that 4.46.25 checkpoint, `update.verify` remained
independently unmeasured; the later observable boundaries are described below.

The follow-up passed **30 distinct Python cases, 69 compiled Node controller
cases plus one Node/Python SQLite policy case, and 25 browser-source cases**;
both source builds passed and the 70 Node cases had no skips. The original two
Python coverage-fixture failures are retained with their test-only corrections.
These results do not establish resource, provider privacy or installed acceptance.

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
The [MCP interface follow-up](../validation/2026-10-27-telemetry-mcp-interfaces.md)
aligns the legacy schema with all nine existing privacy controls and preserves
exact arguments for strict backend validation. Non-object privacy arguments
return bounded `-32602`; other legacy memory arguments retain compatibility.
Both MCP interfaces now contribute static source evidence to the shipped
inventory, building on existing independent map tests. The 46 focused checks
and 11 existing protocol/compatibility checks passed.

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

The [transaction metadata follow-up](../validation/2026-10-26-telemetry-query-ownership.md)
consolidates fresh native authority reads and reuses the checked format only
inside one transaction. A fixed 32-workflow comparison reduced statement wrappers
from 608 to 384 with identical queue and contribution state; 67 focused checks
passed with two Windows-only skips. The allocation change is retained; it
establishes no RSS/CPU saving or installed acceptance.
The dependency review did not justify splitting common imports as the resource fix.

The [fixed allocation resource follow-up](../validation/2026-10-26-telemetry-allocation-followup.md)
then completed all six source-app cases at `4779cf11`, matching 2,045 files each,
with 2,322 successful fixture API requests, 2,304 memory operations and no model
calls. Enabled main-process matched RSS maxima were **3,145,728 / 3,186,688 bytes**;
ending differences were **2,768,896 / 2,428,928 bytes**, all above 2 MiB. Both
opted-out comparisons and every sampled process role remain retained. Combined
Electron CPU differences are descriptive, not stable per-process overhead.
Resource acceptance still fails; no causal improvement, budget change or replay
of this workload is selected.

The subsequent [release-owned TLS trust change](../validation/2026-10-26-telemetry-scoped-trust.md)
uses one or two bounded public CA certificates for native/Python telemetry,
without ambient-root fallback. Route version 2 keeps the unavailable address
null and authorities empty. Minimum TLS 1.3, certificate/hostname verification,
literal routing, existing review binding and privacy/budget fences remain
mandatory; browser TLS is unchanged. Source checks passed 78 distinct Python
cases and 54 cases in the actual local Electron binary running Node mode, with
Ruff and the Electron build passing. Original fixture failures and corrections
are retained.

The [completed scoped-trust resource follow-up](../validation/2026-10-26-telemetry-scoped-trust-results.md)
at `4b8e8a3e` completed all six functional cases, matching 2,053 source files
each, with cleanup passing. Enabled main matched maxima were
**4,341,760 / 3,428,352 bytes** and endings **2,625,536 / 3,215,360 bytes**;
the unchanged 2 MiB gate still fails. All roles, opted-out controls and prior
failures remain retained. Different ambient fixture trust across revisions
prevents a causal savings claim; combined CPU is descriptive. No repeat
measurement is selected. CPU/resource, provider/privacy and installed-platform
acceptance remain open.

The later [metadata-allocation follow-up](../validation/2026-10-26-telemetry-metadata-allocation.md)
reuses fixed database path/URI strings, lazily validates each desktop owner's
copied certificate list and shares strict cell decoding for filtering and full
descriptions. Fresh authority/TLS checks, preview/wire semantics and budgets
remain unchanged. Actual Electron passed 100 checks with two Windows-specific
skips; 134 browser-source tests, all-coordinate Python comparison and both builds
passed. Original allocation failures remain retained. No RSS/CPU saving is
established.

The [completed metadata-allocation resource diagnostic](../validation/2026-10-27-telemetry-metadata-allocation-results.md)
passed six functional cases with 2,075 matched source inputs each and cleanup.
Enabled main matched maxima were **9,261,056 / 2,936,832 bytes** and ending
matched-phase differences **9,261,056 / 1,593,344 bytes**. Both maxima exceed
2 MiB; the first enabled renderer comparison is unavailable because its initial
role is ambiguous. All roles and both orders are retained. Profiled CPU is
descriptive, and these observations do not establish a causal regression or
production-only overhead. Resource acceptance remains false; prior failures,
the 2 MiB / 0.5% ceilings and privacy/platform gates are unchanged. At that
checkpoint, no new resource run or budget change was selected.

The [completed process-role comparison](../validation/2026-10-27-telemetry-resource-roles.md),
run **40453953300** on `6ac77003`, passed six 128-cycle functional cases with
2,114 matched source files each, 2,322 successful fixture API requests and
cleanup. Development DevTools auto-opening was disabled, app main/renderer
identities were verified and allocation attribution was off. Both enabled main
and all enabled/opted-out renderer comparisons exceeded 2 MiB at matched phases;
the report retains both orders, endings and descriptive CPU deltas. The old
run's second `Tab` remains unidentified. No causal saving, general CPU or
resource/platform/privacy acceptance follows. Prior failures and strict
budgets remain; no new resource run is selected.

The [source-kernel control diagnostic](../validation/2026-10-27-telemetry-probe-controls.md)
retains original run **40470335733** on `d56d578f` as **failed**. Each of its
three cases completed 128 memory cycles and 387/387 API requests, with cleanup.
The real opted-out status correctly cleared disclosure acknowledgement; the new
diagnostic wrongly required it to remain set. Correcting that expectation
passed 35 report tests and Ruff without changing product policy or rerunning
the app. Independent retained-evidence analysis matched 2,130 source inputs per
case and confirmed all three recorded control states. The original receipts
and failed workflow remain unchanged; full-workflow, resource, installed-platform
and full privacy acceptance remain unqualified.

The [catalog lookup follow-up](../validation/2026-10-27-telemetry-catalog-residency.md)
reuses fixed release metadata without caching privacy, generation or queue
state. Its 128-iteration fixture removes the measured recurring enumerations,
family splits and bucket callbacks; native/browser-source parity checks and all
builds passed. This establishes no RSS/CPU saving. Its
[original six-case comparison](../validation/2026-10-27-telemetry-catalog-comparison.md),
run **40477197149** on `bc4d6e08`, completed with failure. All six cases completed
memory work, but only five journeys completed; the second enabled case reserved
and delivered nothing. Summary generation was skipped and qualification rejected
the missing summary. Its cause remains unestablished; no app rerun or resource
acceptance is credited.

The [confirmed-opt-out follow-up](../validation/2026-10-27-telemetry-disabled-hint.md)
forwards only a bounded negative hint from a successful current-schema status or
configure reply with `user_enabled: false`. A later-created native owner receives
the original monotonic expiry, avoiding a duplicate SQLite read without creating
authorizing permission. No worker, timer, sideband file or network is added.
Actual Electron component checks passed 116 of 118 cases, with two Windows-only
skips and no failures; SDK/native builds passed and 623 runtime/test inputs were
unchanged. No enabled-mode optimization, measured resource saving or new app/
platform qualification is established.

Denial-only hints for opt-out/exhausted scopes retain the original file/day and
at-most-**60-second** expiry; merging scopes cannot renew it. Negative file
observations can be reused for **250 ms**, so a recent re-enable may lose optional
samples during that interval. Synchronous denials avoid Promise/SQLite work.
Actual choice/status and admitted observations, reservations and handoffs still
use fresh checks; negative hints never grant permission.

Fresh automatic desktop scans/capture and standalone connector execution have
owners. Completed empty scans and paused work contribute nothing. Explicit Sync
continuations, remote-requested or host-managed scans, reusable helpers and
server-worker activity do not acquire another maintenance owner.
Native resource samples require a real child callback; headless
RSS is an ending observation, with its own CPU delta and configured capture
limit. No source history or mixed-host totals are exported. Desktop updater download
and retries retain one enclosing cycle; polls add no use, unfinished cycles
are discarded on quit, and installer handoff is only accepted. Native request
acknowledgements remain separate categories, not extra completed uses.

The [27 October verification source](../validation/2026-10-27-telemetry-update-verification.md)
adds `update.verify` at observable stages. Windows starts at its validation event
and macOS at extraction/verification; ready, error or cancellation closes that
stage. Linux requires fresh `download-progress` in the current attempt followed
by `update-downloaded`, using policy captured at download start. Same-session
cached readiness can follow an existence-only check and does not qualify as
verification. No separate verification duration or classification of opaque
errors is inferred. Download and
verification observations must not be summed as unique user actions.
`TelemetryWorkflow` captures its monotonic start before the asynchronous policy
read and its actual end in the completion callback before awaiting that policy;
completion without an observable phase start explicitly omits latency.
All **91 Python host/service-update/coverage checks, 48 compiled Node controller/
workflow checks and 29 browser-source checks** passed, with no Node skips; the
current SDK and Electron builds also passed. These source checks do not qualify
installed updates, resource limits or production privacy.

The [Python action-timing correction](../validation/2026-10-27-telemetry-agent-timing.md)
likewise starts before optional contribution and privacy-policy reads. Controlled
clock regressions through real SQLite queues reproduced an omitted 650 ms in
both fixed and selected workflows; both now record the complete interval.
Invalid/backward clocks drop the observation instead of reporting zero.
All **135 focused Python owner checks** passed, including existing opt-out,
receipt and original-generation fences. This is source measurement accuracy,
not a resource saving, new collection authority or installed qualification.

The [managed-host update follow-up](../validation/2026-10-26-telemetry-host-updates.md)
owns fresh headless staging, compatible apply and rollback under the watcher's
own OS-account acknowledged policy. Both the baseline supervised child and the
isolated standalone watcher establish this boundary. Manual/API/library calls,
ordinary checks, ready-runtime reuse and held/incompatible apply acquire no
automatic owner. The live updater observes service readiness before successful
apply; a candidate failure is confirmed only after rollback returns. The new
`update.verify` stage wraps final installed-package and runtime-wheel integrity
checks in fresh staging; check failure is conclusive, while other mutation
exceptions remain unconfirmed. Ready-runtime reuse and manual helpers gain no
verification owner. Interrupted unfinished work is discarded; a
later watcher can observe its own fresh rollback, never reconstruct the earlier
apply from a journal. Only fixed workflow/outcome values and bounded timing
enter telemetry; versions, paths, operational records and mixed-host resources
do not. This is source ownership, with installed update/recovery qualification
still open.

The [4.46.21 capture-delivery source follow-up](../validation/2026-10-26-capture-delivery-telemetry.md)
preserves receipt bodies and separates request-local fresh/replayed metadata
from a verified fresh stored-event count. A later delivery failure retains this
call's earlier acknowledgements; an uncertain POST leaves the fresh total
unavailable. Native/headless owners now use existing `result_items` for verified
fresh capture counts, excluding duplicates and fenced events. Replay/readback-only
completed cycles add no fresh use. The live count is excluded from saved source
status; SDK metadata remains per call without ownership. There is no second
`capture.deliver` owner or change to metric coordinates or wire views.
The follow-up passed 172 distinct Python and 111 Node controller/wire cases
and both source builds, with the original frontend-fixture failures retained.
These checks do not qualify an installed 4.46.21 release or full V08.

The [4.46.24 capture-action follow-up](../validation/2026-10-26-telemetry-capture-actions.md)
lets the existing cycle owner choose `capture.deliver` when it accepted no local
items and observed a positive verified fresh stored count. Cycles accepting local
items remain `capture.collect`, including mixed collection/delivery work. One
original policy/generation snapshot and start time govern that choice; final
write fences and contribution limits still apply. The category does not change
whole-cycle outcome or latency. Completed cycles without fresh work remain
suppressed; incomplete/denied outcomes and unknown-count handling are preserved.
There is no second SDK, HTTP or mixed-cycle owner.

This follow-up passed **109 distinct Python, 154 compiled desktop/store Node
and 120 browser-source cases**, with two Windows-only Node skips and both source
builds passing. Three initial Python failures and one Node failure remain
recorded with their test-only corrections. The related narrow source-CI
capacity recovery passed 41 separate mocked guard tests. These source checks
do not qualify installed/native behavior, production telemetry or resource gates.

### Admission, delivery and reporting

Owners offer delivery after a committed observation within an already-awake
desktop, page or registered Python service/local stdio loop. There is no new idle
sampler, telemetry daemon, one-shot CLI keepalive or shutdown flush. OS cost
checks precede gauges, use fixed flags without an Internet probe or network
identifiers, and reject late cancelled results with freshness measured from
query start. Linux/macOS aggregate CPU admission avoids per-core enumeration;
changed/reset counters require comparable readings and preserve the **20% CPU
admission threshold**. Windows retains the existing fallback.

The [delivery-opportunity correction](../validation/2026-10-27-telemetry-delivery-opportunity.md)
lets later awake desktop work reoffer one prior committed policy stamp when new
collection is refused, at both valid scoped workflow snapshots and recording
boundaries. Snapshot refusal remains unchanged; unscoped inspection and unknown
categories do not offer delivery. This addresses both separately reproduced
paths that could strand an earlier deferred queue after saturation.
Defensive copies retain no authorizing permission; existing cadence and fresh
policy, sensors, spending and final-send gates remain. No timer, contribution or
wire allowance is added. Actual Electron component checks sent once after
readiness returned and zero times after opt-out or close. This separately
reproduced bug is not the established cause of the failed app comparison.
The [changed-source comparison](../validation/2026-10-27-telemetry-delivery-comparison.md),
run **40483350394** on `29dcd70d`, completed all six functional journeys with
2,143 matched source inputs each, actual setup/process controls and cleanup.
Both enabled cases delivered one four-byte report. Resource acceptance still
fails: enabled main-process matched RSS maxima were **3,768,320 / 3,129,344
bytes**. Both orders, opted-out controls, renderer results and endings are
retained in the report; CPU remains descriptive. Original run 40477197149 stays
failed with cause unproved. The subsequent
[SQL-read app comparison](../validation/2026-10-27-telemetry-sql-comparison.md),
run 40523504727 on `3034bc0b`, qualified six functional cases, 2,171 source
bindings each and cleanup. Both enabled main matched maxima still exceed
2 MiB (**2,572,288 / 2,859,008 bytes**), as do the first renderer/GPU comparisons.
All roles and both orders remain in the report; resources still fail, CPU is
descriptive and no allocation cause or saving is established.

The later [phase-memory comparison](../validation/2026-10-29-telemetry-v3-resource.md),
run 40967691671 on `1adc472af8874ccdb261f7532eeab0463d888a40`, completed the same
six-case shape with 2,301 matched inputs per case and one 25-byte report in
each enabled case. Enabled main matched maxima are **5,271,552** and
**2,887,680** bytes, still above 2 MiB. File-backed pages of about 1.5–1.9 MiB
remain after first delivery in both enabled repeats. The r1 96-cycle spike and
the r1 opted-out final checkpoint are not repeated by r2. No callsite or safe
source change is established. Run 40965218896 stays failed with no measurement.

The later [browser/Python owner follow-up](../validation/2026-10-27-telemetry-owner-saturation.md)
reoffers prior committed work after browser Web Lock release and through Python
completion/resource/early-exhaustion paths. Python keeps one immutable stamp
under the existing lock and cadence, cleared on close; only an already-loaded,
registered owner can receive a pulse. Standalone collection no longer imports
activity/`asyncio` merely to offer work. Fresh permission and all budgets remain.
Qualified source checks are 137 distinct Python and 96 browser-source cases,
with SDK/frontend builds passing. Browser fetch/locks/admission are mocked;
the earlier app comparison does not include these changes or qualify them.

The managed updater can also offer an existing bounded queue or still-valid
approved held report during its already scheduled five- or ten-second waits.
Fresh eligibility checks occur at most once per minute in that watcher lifetime;
this is not a new wake schedule or a global limit across restarts. An approved
report can be eligible even with zero ordinary pending records, without waiting
for the next six-hour update check. The temporary delivery context is cancelled
and closed before synchronous update work resumes. Shutdown adds no flush or
keepalive. Choice, company policy, review approval/expiry, pressure, metering,
spending and final-send fences still control whether anything is sent.

Without a packaged network helper, source Windows can use its documented local
OS hint; Linux/macOS cost stays unknown. A present broken helper is not bypassed.
An absent browser pressure API or a recognized unsupported/permission-denied
capability response leaves that sensor unavailable, without inventing a nominal
reading. A supported sensor requires bounded initialization and a fresh nominal
observation; stale or malformed readings, unexpected failures, startup timeouts
and observed pressure refuse delivery. An absent heap API adds no heap-pressure
veto or fabricated reading. A present API must pass numeric validation and the
existing 80% threshold; throwing getters or malformed data refuse delivery.
Losing a capability or closing its observer cannot clear a previously observed
restriction; a valid fresh observation must clear it.

Offline or hidden pages, page exit, data-saving mode, cellular or otherwise
known metered connections, slow links and cancellation remain restrictive.
Observers accompany offered work in an already-awake page; there is no new
idle service or identifying capability field on the wire. Missing measurements
retain their existing missing-sensor representation. Browser attempts also read
bounded, credential-free same-origin `/studio/telemetry-policy`, recheck local
choice/pressure and only narrow permission until reload. Reading privacy status
neither fetches policy nor enables collection. The
[browser/network admission design](telemetry-browser-admission-2026-10-30.md)
does not qualify real browser sensors or resources; WebKit-engine evidence alone
cannot qualify native Safari.

Shared native/Python accounting and browser-origin coordination enforce **seven
attempts per rolling week**, at least **24 hours plus jitter** between attempts,
**64 KiB reserved per attempt** and a **256 KiB rolling-day guard**. Reservation
consumes the queue; opt-out clears measurements/lease but does not refund spending.
These reservations do not establish actual whole-wire cost. The native sender
drains its own watcher before the mandatory fresh handoff check, then resumes
watching; the five-second deadline, opt-out, one storage handle and final cleanup
remain enforced. Full installed cancellation/resource qualification is still open.

The [27 October native wire measurement](../validation/2026-10-27-telemetry-native-wire.md)
passed **seven component scenarios without skips** in Electron **44.9.3** Node
mode (**24.22.0**, Linux x64), including ordinary-owner delivery, Python opt-out
and response refusal. Two IPv4/TCP counters agreed with zero capture drops; the
maximum burst was **53,683 frame bytes**, below the **65,536-byte** reservation.
All **2,111 source and 92 compiled inputs** matched. The client and synthetic
loopback TLS peer shared one process. These observations do not establish a
universal wire bound or installed, physical-link, IPv6, retransmission, browser,
rolling-day, resource or provider acceptance. Earlier failed resource results
and the **2 MiB / 0.5%** limits remain unchanged.

The published [wire v2 format](../../mnemion/product_telemetry/wire-v2.json)
uses four-byte locally randomized packets. Automatic reports use the randomized
encoder; manual reports use the first permitted view, coordinate zero and flags
two, without category data or a random draw. Reviewed reports contribute only
to a coarse global power-of-two volume range after **64 total reports**.
Categorical sums, per-view counts and precision use automatic reports
exclusively, retaining the **4,096-report per-view threshold**. No separate
manual count is published. The
[catalog compatibility follow-up](../validation/2026-10-27-telemetry-catalog-compatibility.md)
adds the new feature labels in aggregate report schema 4; immutable aggregate
reports v1/v2/v3 remain readable under their original labels. Aggregate report
schema v3 is not wire version 3. Wire v1 packets are rejected. Volume is
unauthenticated and is not a count of people or installations; fine-grained
statistics can remain unavailable. Those limits are the wire v2 contract the
dated checks measured. They are not the pending report. Exact wire v2 review
behavior is specified below.

The dedicated collector implements bounded TLS intake, metadata removal,
private immutable closed-week publication and **eight-window retention** in a
minimal locked runtime. Systemd supplies its sole listener; the service cannot
connect outbound or bind another port. Isolated TLS/VPS checks establish those
recorded boundaries, not provider/ingress privacy or a production deployment.

The [aggregate privacy assessment](../validation/2026-10-27-telemetry-aggregate-privacy.md)
adds a reusable offline check of the complete released document under known
background information. All **46 scenarios across 23 views** preserve the
conditional single-category likelihood-ratio bound of three; the rare fixture
cells expose no point value or interval. Competing SQLite publishers retain one
immutable week, and attempted filtered/difference routes are refused. **70
distinct source tests** qualify this scope, including eight new attack checks.
Exact linked-report calculations and explicit participation/policy-choice
counterexamples prevent extending that bound to identity, lifetime or network
anonymity. This source-only assessment changes no collection behavior or budget;
full privacy, resource, platform, provider and useful-population acceptance remain open.

The pending report is the gated
[wire v3 contract](../../mnemion/product_telemetry/wire-v3.json), specified in
[anonymous product telemetry v3](anonymous-product-telemetry-v3.md). One report
is 25 bytes and carries 19 bounded metrics. Each report securely chooses either
a full semantic release coordinate or one coarse operating-system marginal,
before the observations are read. Both axes can appear in one published week.
There is no joined release-by-OS profile. A policy-disabled category is
`group_disabled`. A missing sensor is `sensor_missing`. Raw memories, prompts,
tokens as text, keys and identifiers are excluded. The collector sees the
bounded summary, then drops the bytes. Publication-side report-level
differential privacy is applied after that trusted first-party aggregation.
The add-or-remove-one-report bound on the released vector is `ln(3)`, including
admission and clipping. That bound is not network anonymity, collector
blindness, a unique-user count, or an exact uncapped event total.

The integrated client source uses disclosure version 3. An enabled installation
that acknowledged version 2 requires a fresh explicit acknowledgement before
the changed automatic network behavior can apply. Editing connection settings
does not acknowledge it, and old held reports or approvals cannot authorize the
new behavior. Acknowledgement clears old pending/held data through the normal
configuration path without refunding spent attempts. The client checks metric
groups again at final send and invalidates a stored wire v2 manual approval
instead of sending it. Real opt-outs, company restrictions, manual controls and
the minimum request budget stay: seven attempts per rolling week, at least 24 hours
plus jitter, 64 KiB reserved per attempt, and a 256 KiB rolling-day guard.
`default_enabled` stays true. `collection_available`, destination and route
stay false/null. Synthetic format examples are labelled examples, not sent
reports. Private maintainer HTML, CSV and JSON exist on the accepted combined
source. Ordinary Privacy settings do not show fleet data. This source does not
turn collection on. Installed v3 delivery is not qualified. The current
8 MiB and 0.5% acceptance gates remain open. V08 is not complete.
All 66 requirements stay.

## Remaining acceptance gates

The [27 October acceptance ledger](../validation/2026-10-27-telemetry-acceptance-ledger.md)
links implemented behavior, scoped qualifications and the evidence still
required below. It preserves all requirements and failed results.

- **Coverage and installed behavior:** finish the action-by-action ownership and
  exclusion review, including autonomous work and unknown remote clients. All
  six native targets still need installed staged-report approval/delivery,
  current-owner, cancellation, storage-loss and pressure/sensor journeys. Web has
  [scoped compiled-app review/delivery and restart evidence](../validation/2026-10-26-telemetry-browser-admission.md);
  production trust and remaining owner, cancellation, storage-loss, sensor/resource
  and privacy qualification remain open. The 4.46.22 mode/opt-out restart evidence
  does not qualify later source changes or the full restart/update lifecycle.
- **Resources and architecture:** the fixed compiled-app comparisons failed
  the initial **2 MiB / 0.5%** acceptance gates. Run
  40967691671: enabled main maxima **5,271,552 / 2,887,680** bytes, with no
  evidence-supported patch at that checkpoint. The
  [8 MiB RAM revision](telemetry-resource-budget-2026-10-30.md) requires new
  installed evidence and retains the 0.5% CPU ceiling. Ending RSS, matched maxima, other process roles and
  profiled CPU are retained in the evidence index; no causal improvement or
  favorable-run selection is accepted. The subsequent
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
implements one private wire v2 four-byte stage, app controls and local agent
actions. That recorded stage is not the pending 25-byte wire v3 summary. A
stored wire v2 manual approval is invalidated rather than sent.
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
measurement is transmitted. `ln(3)` describes automatic wire v2 randomization, not
arbitrary human inclusion. Aggregate report schema v3 estimates only correctly marked automatic reports under
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

## Resource and reliability ceilings

These are engineering acceptance ceilings, measured with memory work active.
The [30 October revision](telemetry-resource-budget-2026-10-30.md) changes the
initial 2 MiB RAM allowance to 8 MiB, with no accepted measurement yet.
Any further increase requires a documented design revision and new measurements;
saturation must drop telemetry rather than delay canonical memory work.

| Resource | Current ceiling and behavior |
| --- | --- |
| Local pending queue | At most 256 KiB or 512 aggregate records, whichever is reached first; maximum age 48 hours; bounded eviction and full opt-out clearing |
| Added resident working memory | At most 8 MiB per participating process in declared installed workloads, including cold activation, delivery and helpers; no model loading or new persistent service solely for telemetry |
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
