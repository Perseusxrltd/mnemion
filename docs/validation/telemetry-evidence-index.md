# Telemetry evidence index

The [local v3 systemd check](2026-10-30-telemetry-v3-systemd-local.md) passed
socket activation, TLS delivery, credential isolation and cleanup.
The [installed diagnostic qualification](2026-10-30-telemetry-installed-driver.md)
preserves the first two failures. Third run 41013868878 (`c8f75870`) passed
scoped delivery on Linux x64 and both Macs: 21 memory API calls, one inspected
25-byte report and opt-out/manual-review persistence across two launches each.
The r3 Windows `no_observations` and Linux ARM64 `connection_pending` failures
remain retained. Fourth run 41022011070 (`497af0ab`) selected those three targets.
Linux ARM64 completed 21 successful API calls, delivered one matching inspected
25-byte report, and passed all 11 review controls with persistence across two
launches. Fifth run 41028940251 (`d8dc845e`) selected only Windows x64 and ARM64.
Windows x64 passed 21 successful API calls, six admitted/committed observations,
one matching inspected 25-byte report, all 11 review controls and two clean
launches with persisted opt-out/manual-review mode. Sixth run 41036977655
(`46d4f730`) passed Windows ARM64 with the same 21 successful API calls,
six committed observations, matching 25-byte report, all 11 controls and
opt-out/manual-review persistence across two clean launches. All six targets
now have scoped passing evidence across four original sources, not a complete passing
matrix on one source; the earlier passes were not repeated.

In the fourth run, both Windows targets completed 9 successful API calls and
sent no reports. Each
recorded two snapshot admission deadlines, two successful ACL checks below 50 ms
and zero observation-write attempts. This proves loss at the 25 ms admission
deadline. The timing buckets cannot determine whether ACL work alone exceeded
25 ms or separate process startup, IPC, scheduling and store-open costs. Original
artifact/source bindings and package/collector evidence limits are recorded in
the report. Fifth-run Windows ARM64 failed with `The installed privacy page did
not open` after 3 successful API calls, at cycle 0 with all observation and ACL
counters zero. This neither reproduces nor clears its earlier admission failure.
The cause is unproven. The reviewed correction waits for the workspace's settled
route before opening Privacy and preserves a bounded failure gate. The original
failure is retained. Corrected source and declarations passed the combined
Electron build; the frontend build also compiled the optional resource client
entry. Resource controller corrections are reviewed, including acknowledged
case boundaries, normal input-handle release and exact global packet totals.
The corrected ARM64 journey passed, with no snapshot admission deadline loss.
Original installed resource comparison 41039553671 on `15715800` failed
preparation on five targets by the 10:43 UTC observation; Mac Intel was still
running. The controller checks the inactive installer against the active
baked source tree. A correction must bind each package to its exact staged
source while retaining native verification. Execution, accounting and budgets
remain unqualified; partial counters cannot become a resource pass.
Full installed, production and resource acceptance remain open;
there are no qualified fleet statistics. Public collection is disabled and
production hosting unresolved. The
[Firefox/WebKit journey evidence](2026-10-30-telemetry-browser-journeys.md)
retains the original failures and the successful fourth run: real memory
actions, two matching 25-byte reports, opt-out/reload persistence and cleanup.
Production trust, native Safari and resource acceptance remain outside that
qualification.
Collection stays disabled.

The [owned-launch accounting review](2026-10-30-telemetry-owned-launch.md)
records the corrected native measurement adapter, 13 focused source checks,
six successful native launch/cleanup jobs, and the first owned Linux compiled
workload. Its six cases completed 768 memory cycles and all cleanup, with two
25-byte reports sent only by enabled cases. CPU/RSS results, the incomplete
terminal phase count and high-water limits are retained. Installed-overhead
and resource-budget qualification remain open.

**Index checkpoint: 30 October 2026.** The
[canonical V08 contract](../implementation/anonymous-product-telemetry.md)
owns current scope, invariants and acceptance ceilings. This index links the
dated reports that own original receipts, source hashes, failed attempts,
corrections, cleanup and qualification limits. A pass qualifies only its recorded
source and fixture; a dated “pending” statement remains historical. No failed
evidence is deleted or reclassified by this reorganization.

The [30 October resource-budget revision](../implementation/telemetry-resource-budget-2026-10-30.md)
sets the current RAM allowance to 8 MiB for new installed acceptance work,
with CPU still 0.5%. All older 2 MiB results retain their original criteria
and outcomes. No result is converted into a resource pass.

Current category and action totals are in the generated
[Git coverage inventory](../../mnemion/product_telemetry/workflow-coverage.json),
under `summary` and `action_coverage.summary`. Inventory numbers in the dated
entries below describe those checkpoints, not the current source or installed
qualification.

The [27 October acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md)
reconciles implemented behavior, scoped qualifications and remaining gates;
the original reports below retain their source bindings and failed evidence.

V08 remains Building with collection/destination/route false/null/null and an
empty release certificate-authority list. The
[29 October v3 reference](2026-10-29-telemetry-v3-reference.md) describes the gated
v3 collector used by the current clients. Legacy v2 evidence remains below.
The corrected implementation keeps both axes in
one week, freezes each closed report's domain, labels quantiles only inside a
conservative envelope, stores the supported 32-release domain, and admits a
report without evicting another one. It does not complete V08.
The 4.46.13 basic controls and 4.46.22 review-mode/opt-out controls have scoped
installed evidence; the 4.46.17 candidate passed all
12 [source CI jobs](https://github.com/Perseusxrltd/mnemion/actions/runs/40299183411)
before its native release driver continued. Consult [release status](../RELEASE_STATUS.md)
for current availability. All 66 requirement texts and states remain unchanged.
The current [engineering budget decision](../implementation/telemetry-resource-budget-2026-10-30.md)
sets 8 MiB / 0.5% for new installed acceptance; historical 2 MiB results retain
their original outcomes without rescoring.

The [29 October v3 client release checks](2026-10-29-telemetry-v3-release-checks.md)
record the integrated current-format fixtures, native probe and automated parity
entry, with original failures and corrected local build results.

The [4.46.55 installed controls](2026-10-30-telemetry-v3-installed-controls.md)
qualify the v3 synthetic preview, app/agent choice, review controls and clean
restart persistence on all six targets from their original attempt-1 artifacts.
No build or app run was repeated. These control-only checks do not qualify
installed report delivery; the later journeys above own that scoped evidence.
Resources and production collection remain unqualified.

The [29 October probe staging fix](2026-10-29-telemetry-probe-staging.md)
retains the failed first phase-memory run and the focused correction that loads
the controller's helper. Its 30 October follow-up retains the separate
canonical-helper import failure from main CI and the corrected single-test
Linux result. Neither failed staging run produced a resource measurement.
The corrected [phase-memory comparison](2026-10-29-telemetry-v3-resource.md),
run 40967691671, completed six cases. Enabled main maxima are 5,271,552 and
2,887,680 bytes. The 2 MiB and 0.5% gates stay unaccepted.

The later original attribution run
[40976743563](https://github.com/Perseusxrltd/mnemion/actions/runs/40976743563)
completed all six compiled Linux cases on `7ee617691ead16c17bbdb9eb797e03f20f186325`.
Both enabled first-read guards were `allowed`, and each delivered one 25-byte
v3 report; unavailable and opted-out controls sent none. All 2,309 source inputs
matched each case and cleanup passed. These instrumented windows do not qualify
resource budgets or installed delivery, and they do not establish the cause of
the retained failed run 40971963055. See the same resource report for the
originals and their limits.

The [explicit v3 service setup](2026-10-30-telemetry-collector-v3-service.md)
adds a mode-only drop-in to the shared Linux collector template, retaining the
legacy default and both report stores. Three focused template/CLI and real TLS
checks passed. The operator guide includes mode changes and private exports;
no deployed systemd, provider, resource or fleet-collection acceptance follows.

The [30 October compiled Linux app review](2026-10-30-telemetry-v3-app-review.md)
records original run 40981256191 on `e36b51a72ca16ec0692d427bbeee912e098d21ef`.
Ten review controls passed in
the unpackaged Electron 44.9.3 / Node 24.22.0 x64 app, including one inspected
25-byte v3 fixture delivery. A private reader that required `comparison: false`
in `source.json` was corrected to the three-field review schema; the same
original artifact qualified with no app rerun. Installed delivery, resources,
whole-wire measurement and hosting or provider acceptance stay outside that scope.

The [30 October SQLite lifecycle probes](2026-10-30-telemetry-sqlite-lifecycle.md)
reject an idle retained connection for this release. Both retained Windows
handles blocked atomic replacement with `EPERM`. Linux held connections kept
the old generation until reopen. These are standalone Node probes, not Electron
builds or resource measurements. These observations do not justify repeating
the unchanged resource workload. The 2 MiB and 0.5% gates stay unaccepted.

The [30 October validation allocation follow-up](2026-10-30-telemetry-validation-allocation.md)
removes discarded encoded objects and cell arrays from desktop/browser
prevalidation without moving rejection past IPC, locks or partial writes.
It records 134 passing native/browser/client checks, two Windows-only skips,
27 v3 parity cases, and the retained missing-client-build prerequisite failure.
No measured RSS/CPU saving or new installed qualification is claimed.

The [30 October browser admission checks](2026-10-30-telemetry-browser-admission.md)
qualify implemented unknown-network admission, unavailable-sensor handling and
version-3 fresh acknowledgement. Python qualification combines 80 original
passes and one corrected real deadline case; browser qualification combines
89 untouched original passes and 83 corrected focused passes, without claiming
a full rerun. The native delivery/choice regression selection passed 85 checks,
and updated frontend typecheck passed. Original failures remain retained.
Actual Firefox/WebKit, installed delivery, resources and production acceptance
remain open. Installed diagnostic `42808919` has read-only review only, awaiting
its first six-target run.

## Controls, ownership and report review

| Date | Original evidence | Scope and boundary |
| --- | --- | --- |
| 30 October | [Compiled Linux v3 app review](2026-10-30-telemetry-v3-app-review.md) | Run 40981256191 on `e36b51a72ca16ec0692d427bbeee912e098d21ef`: 10 controls passed, two launches, three save/fetch/recall cycles, 12/12 API requests, one inspected 25-byte v3 packet, opt-out and manual mode held across restart, cleanup passed, 2,311 source inputs matched. First reader rejection of missing `comparison: false` retained; corrected reader accepted the same original and rejected nine negative cases. No installed, resource, whole-wire or provider acceptance. |
| 30 October | [SQLite handle lifecycle](2026-10-30-telemetry-sqlite-lifecycle.md) | Standalone Node 22.22.0 Linux and Node 25.2.1 Windows probes. Other-process commits were visible. Baseline replacement was visible after reopen on both. Both retained Windows handles returned `EPERM` and kept the old generation. Linux retained handles read the old generation until reopen. Idle-handle proposal rejected. Not an Electron build or a resource measurement. |
| 27 October | [Catalog compatibility and the remaining declared CLI paths](2026-10-27-telemetry-catalog-compatibility.md) | Catalog v2 appends capture.split and models.test while preserving stored coordinates, counts and contribution limits. Checkpoint inventory: 96 mapped categories; 701 actions (398 mapped, 295 excluded, eight delegated, zero unmeasured). All 322 scoped checks passed without failures or skips; Electron build and frontend typecheck passed. New report schema 4 adds feature labels while wire v2 and immutable report schemas 1–3 retain their original meanings. Earlier failures, resource limits and remaining privacy, installed and full telemetry acceptance are unchanged. |
| 27 October | [CLI variants, outcomes and repair preview](2026-10-27-telemetry-cli-outcomes.md) | Checkpoint inventory: 700 rows (396 mapped, 294 excluded, eight delegated, two unmeasured); classic CLI has 63 rows (32 mapped, 29 excluded, split and llm test unmeasured). Invocation-only suppression leaves saved policy unchanged and covers both automatic hook-mine subprocesses. Fixed variants and unconfirmed outcomes retain opaque results; repair dry-run stops before extraction/backup/delete/rewrite. Two defect reproductions and three malformed quarantine fixtures retained. Qualified 128 distinct Python cases: 125 unchanged passes plus three corrected fixtures; one existing browser-source preview passed, SDK/frontend builds and lint/format passed. All 584 source inputs unchanged. No model/app/native run, resource saving, collection activation or full acceptance. |
| 27 October | [Classic CLI ownership and visible gaps](2026-10-27-telemetry-cli-coverage.md) | Two original regressions retained; 66 Python checks and one targeted source-preview check passed. Nine reviewed commands share the local installation choice, with no CLI sender or keepalive. Static extraction exposes 49 leaf paths / 51 rows, including 29 unmeasured paths. Checkpoint total: 688 rows (373 mapped, 278 excluded, eight delegated, 29 unmeasured), eight interfaces / seven checked owners; 94 categories remain mapped. All 690 CLI check inputs remained unchanged; no dependencies installed. SDK/Electron/frontend builds passed. No installed or resource acceptance; the failed catalog comparison remains retained. |
| 27 October | [Refused observations and result handling](2026-10-27-telemetry-refused-results.md) | Four original local-inspection regressions retained. All 53 owner/policy tests and SDK/frontend builds passed; unavailable, synchronous/asynchronous refusal, failed and timed-out reads preserve opaque results/errors and exact-once callbacks on desktop/browser owner paths. Late replies do not revive an observation. No transmission or retention defect, resource saving, installed journey or full V08 pass is claimed. |
| 27 October | [Visible setup recovery](2026-10-27-telemetry-setup-recovery.md) | Three original compiled-UI failures retained; 11 actual Chromium recovery checks and 29 policy tests passed. Read failures clear stale controls; uncertain saves read status without write retries. SDK/frontend builds and fixture cleanup passed. Controlled native replies do not qualify actual installed storage, resources or provider privacy. |
| 27 October | [Python agent action timing](2026-10-27-telemetry-agent-timing.md) | Start precedes optional contribution/policy reads in fixed and selected workflows; two reproduced omissions corrected, four invalid-clock cases and 135 focused owner checks passed. Original choice fences remain; no resource or installed qualification. |
| 27 October | [Native telemetry wire measurement](2026-10-27-telemetry-native-wire.md) | Seven scenarios passed without skips using unchanged compiled Electron 44.9.3 / Node 24.22.0 transport; 2,111 source and 92 built inputs matched. Independent segmented counters agreed, including owner delivery, two Python opt-outs and a refused 256 KiB peer burst observed at 53,683 frame bytes. Cleanup passed. Same-process Linux IPv4 loopback scope; no full installed, browser, physical-link, IPv6, retransmission, rolling-day, resource or provider acceptance. |
| 27 October | [Capture administration and replay receipts](2026-10-27-telemetry-capture-admin.md) | Qualified 106 distinct Python, 22 SDK and 49 Studio/policy source tests; SDK/frontend/Electron builds passed and 29 inputs matched. Two app buttons use scoped owners; five capture mutations distinguish fresh/replayed results. A real PostgreSQL grant-ID race is reproduced and fixed, with locked revocation state and unchanged retry rules. Original failures retained. Inventory: 94 mapped categories, 636 rows (364 mapped, 265 excluded, seven delegated). Selected for 4.46.36; no installed, resource, provider or full telemetry acceptance. |
| 27 October | [Update verification and timing](2026-10-27-telemetry-update-verification.md) | 91 Python, 48 compiled Node and 29 browser-source checks passed; SDK/Electron builds passed and 17 recorded inputs matched. Explicit Windows/macOS stages, fresh Linux transfer plus untimed successful completion, and fresh managed-host final package integrity checks have scoped owners. Cached Linux readiness, opaque failures, manual calls and ready-host reuse do not infer new verification. Privacy fencing and shutdown are preserved; timing captures both operation boundaries before waiting for policy reads. Inventory: 94 mapped categories, 634 rows (362 mapped, 265 excluded, seven delegated). No native installed, resource or production acceptance; no separate native release requested. |
| 27 October | [First-time setup disclosure](2026-10-27-telemetry-setup-disclosure.md) | 29 policy checks, four new cases, and ten compiled Chrome UI checks passed. Explicit save/disable preserves the original privacy fence; Not now/Escape/details do not acknowledge; saved opt-outs, company restrictions and GPC remain authoritative. Inactive release loads no setup chunk. Original stale local SDK build failure retained; current SDK/frontend builds passed after isolated dependency correction. Browser and loopback servers closed; zero external or network-write requests. No new native release, collection enablement or resource/provider/full acceptance. |
| 27 October | [Setup disclosure through the desktop bridge](2026-10-27-telemetry-setup-disclosure.md#compiled-electron-follow-up) | Source `e03513df`: 2,100 source files matched; ten review checks passed across two Linux x64 Electron 44.9.3 source-app launches. Initial deferral granted no permission; opt-out, exact review, empty re-enable, discard, approved four-byte loopback TLS delivery and restart persistence passed. Twelve fixture API calls succeeded, queue emptied and cleanup passed. No model calls or dependency install; this does not qualify an installed platform, resource budgets or production privacy. |
| 27 October | [Local MCP privacy schema and coverage](2026-10-27-telemetry-mcp-interfaces.md) | Legacy schema exposes all nine existing offline privacy actions and preserves exact inputs for strict validation; non-object privacy arguments return bounded -32602. Static generation now reads both MCP registries without importing servers: seven interfaces, six checked owners; 632 action rows and 94/93/one workflow counts unchanged. Existing independent map tests retained. Original collection stopped for missing chromadb before tests; the qualified environment reproduced 18 failures. Corrected source: 46 focused and 11 existing protocol/compatibility checks passed. Follow-up retains both Windows 4.46.33 Unicode fixture failures; explicit UTF-8 passed 40 actual Windows x64 storage checks, no skips. Known release-receipt CI classification passed 30 checks; original runs were not cancelled/retried. No resource, installed or production qualification. |
| 27 October | [Company-policy path refusal](2026-10-27-telemetry-company-path.md) | Original 4.46.30 Windows x64/ARM64 failures and Linux reproductions retained. Missing policy paths now check up to 32 ancestors; invalid paths and failed reads after stat deny, without a positive cache. Python: 22 passes; actual Electron: 57 passes/two Windows-specific skips; build and Ruff passed. Actual Windows x64 Node 25.2.1 passed two cold checks; Python 3.13.11 passed six filesystem cases, including real invalid-ancestor errno 2. Its 91-file fixture was removed. Native dispatch for 4.46.32 was held and pending 4.46.31 cancelled; original 4.46.30 preserved. Component evidence only; installed/resource/privacy gates remain open. |
| 26 October | [Source-app review and approval handoff](2026-10-26-telemetry-app-review.md) | Working patch based on `4b8e8a3e`: 2,172 source and compiled inputs matched. Nine checks passed in the actual compiled Linux x64 app across two launches and three save/fetch/recall cycles (nine operations, 12 successful HTTP requests); exactly one accepted four-byte TLS report matched inspection, with opt-out/manual mode/spending persistence and cleanup. Separately, 24 Electron-runtime owner/delivery tests and 14 browser-source tests passed, no skips. Shared owner retains automatic cadence plus at most one extra explicit approval preflight per awake minute, with one pending policy stamp and unchanged final gates. Three probe errors, the real approval failure and deterministic old-owner failure remain retained. Web-browser delivery, six installed targets, resource/privacy acceptance and the new diagnostic mode's remote execution remain open. |
| 26 October | [Installed 4.46.22 review controls](2026-10-26-telemetry-installed-review.md) | Original run 40351425614/source `2d48ace8`: five targets from failed workflow attempt 1, Mac ARM alone from the capacity retry in attempt 2; each artifact is fresh in its own attempt. All six pass 67 required hosting fields, including eight telemetry fields for default/format/no-consent controls, app/native choices, focus clearing, zero recorded attempts and opt-out/review-mode restart persistence. Qualification used existing artifacts, with no new build, app run or model call. Staging/approval/delivery, later owners, 4.46.25 installed behavior, resource/provider privacy and actual PC/VPS upgrades remain outside scope. |
| 26 October | [Saved-workspace selection and backup inventory ownership](2026-10-26-telemetry-workspace-selections.md) | 4.46.25 source follow-up: only explicit saved restore chooses open/switch from verified private transition metadata, with one original snapshot/clock; automatic resume stays unowned. App/native backup inventory owns list success without validity or delivery claims. Inventory: 94/93/one categories and 632 rows (360 mapped, 265 excluded, seven delegated); independent `update.verify` remains unmeasured. 30 distinct Python, 69 compiled Node plus one Node/Python SQLite policy case, and 25 browser-source cases passed; both builds passed, no Node skips. Initial two Python fixture failures and test-only corrections retained. No installed/native, resource or production acceptance. |
| 26 October | [Capture action ownership and source-CI capacity recovery](2026-10-26-telemetry-capture-actions.md) | 4.46.24 source follow-up: one original cycle owner selects collect or verified delivery-only; explicit conversation preview and standalone pause gain their fixed categories. Inventory: 94/91/three categories and 630 rows (356 mapped, 267 excluded, seven delegated). 109 distinct Python, 154 compiled desktop/store Node and 120 browser-source cases passed, with two Windows-only skips and both builds passing; initial three Python/one Node failures and test-only corrections are retained. A separate 41-case mocked guard selection passed for the narrow latest-main CI capacity retry. No installed/native, resource or production acceptance. |
| 26 October | [Automatic managed-host update ownership](2026-10-26-telemetry-host-updates.md) | Both dedicated watch entrypoints use the host account's acknowledged policy for fresh stage/apply/rollback. Existing waits can offer queued or approved held reports, with cleanup before update work resumes. 164 distinct Python cases passed, including four actual local TLS cases and real API/worker recovery; frontend and Electron builds passed. Original fixture/bundle/build-directory failures and the initial browser CI stale-count assertion are retained; 120 browser cases passed after correcting the preview expectation. Inventory: 94/88/six categories and 628 actions (351 mapped, 270 excluded, seven delegated). No journal backfill, mixed-host sensors, resource or installed/production acceptance. |
| 24 October | [Privacy controls and source inputs](2026-10-24-telemetry-controls.md) | Core 19-check browser journey, eight further policy/fault checks, wheel controls and source matching. Original parsing failure retained; no full native/collector qualification. |
| 24 October | [Catalog, aggregates, generation and workflow owners](2026-10-24-telemetry-aggregates.md) | Python/TypeScript parity, private SQLite, desktop/Studio/UI/local-stdio and maintenance checkpoints. Includes test-placement/schema-reference errors, UNC discovery, browser/build/runner failures and inspected corrections. Later results do not erase earlier source boundaries. |
| 24 October | [Application owners and connection choice](2026-10-24-telemetry-app-owners.md) | Existing-lifetime delivery, connection modes, opt-out locking and the 19-assertion browser fixture. Historical SQLite 5/browser choice 4 preceded current 6/5/2. CPU admission was synthetic. |
| 24–25 October | [Fresh browser company policy](2026-10-24-telemetry-company-refresh.md) | Policy route/source tests and the 25 October 20-assertion actual Chromium journey. Preserves lease-cleanup and fixture failures; no production-ingress proof. |
| 26 October | [Synthetic format preview and initial clocks](2026-10-26-telemetry-preview.md) | Read-only synthetic preview and five successful 4.46.12 installed targets; Intel Mac failed separately. [Clock foundation](2026-10-26-telemetry-preview.md#review-clock-foundation) preserves Linux/Windows/macOS component boundaries and earlier failures. |
| 26 October | [Published 4.46.13 native qualification](2026-10-26-44613-native-acceptance.md) | Six targets, 64 required fields each, installed privacy/app-agent controls and public upgrade gates. Windows ARM uses a native ARM desktop with emulated x64 engine/database. Does not qualify later exact review or full production delivery. |
| 26 October | [Exact report review](2026-10-26-telemetry-report-review.md) | 306 Python, 116 browser-source and two Python/Node handoff checks, isolated browser review and builds. [Compiler-free macOS clocks](2026-10-26-telemetry-report-review.md#compiler-free-headless-review-clock) are components, not installed/resource qualification. |
| 26 October | [Review-selection correction](2026-10-26-telemetry-review-selection.md) | Original finite selection-bias evidence, intermediate marker-only results and final wire-v2 fixed manual body/report-v3 checks: 149 Python, 113 browser-source, 41 native Node. Preserves obsolete-wire fixtures and Windows ARM clock-fixture failure. |
| 26 October | [Typed host-request intake](2026-10-26-telemetry-host-requests.md) | Nine mutations require a verified new intake; four reads excluded. 47 Python and 17 Node checks, original missing-disposition failure, no terminal-effect or installed coverage claim. |
| 26 October | [Visible source coverage](2026-10-26-telemetry-coverage.md) | Generated inventory distinguishes 86 mapped categories from eight unmeasured. App/browser filters and native schema/preview share the inventory; stale source coverage blocks release validation. No new owner or collection permission. |
| 26 October | [Individual-action preview](2026-10-26-telemetry-action-preview.md) | 525 declared actions/fixed variants: 296 mapped, 224 excluded, five delegated and zero unmeasured within represented declarations; categories remain 87/seven. Four interfaces are independently enumerated; other owners use reviewed maps. 22 distinct Python, 16 Electron/bridge and 42 browser-source/client checks passed, plus eight actual Chrome observations on changed compiled assets based on `93eb300` before 4.46.20 preparation. Asset binding and cleanup retained; no complete call-site, sensor or installed qualification. |
| 26 October | [Workspace ownership and desktop request inventory](2026-10-26-workspace-telemetry-ownership.md) | 4.46.22 source follow-up based on `279017c1`: automatic resume excluded, explicit restore retained and reset owns one forget acknowledgement. All 72 preload channels use the reviewed dispatcher map, the fifth independently enumerated interface. Inventory: 622 actions/fixed variants, 348 mapped, 267 excluded, seven delegated, zero unmeasured among represented declarations; categories stay 94/87/seven. 54 distinct Python cases (53 plus one corrected real HTTP/PostgreSQL regression), 26 Node tests, builds and preparation passed. Retains the original 4.46.21 Python 3.13 stale assertion failure, coordinator timeout and capacity cancellation. Original 4.46.19 native run succeeded; public artifact verification is still running. No 4.46.22 native/production or publication claim. |

The original core browser receipt remains identified by SHA-256
`758778a6590ad1925f050def54c63df0eadefdd5bf7a77235cb07783eba8d93f`.
The later 24 October source-input qualification at 01:12:30 UTC did not retroactively
qualify subsequent owners, senders or release artifacts.

The current catalog retains detailed source maps for
[classic CLI](../implementation/anonymous-product-telemetry-catalog.md#owned-classic-cli-coverage),
[headless control](../implementation/anonymous-product-telemetry-catalog.md#owned-headless-control-coverage),
[desktop/native operator/Studio](../implementation/anonymous-product-telemetry-catalog.md#owned-desktop-native-operator-and-studio-coverage),
[browser/legacy UI/local stdio](../implementation/anonymous-product-telemetry-catalog.md#browser-connection-legacy-ui-and-local-stdio-coverage)
and [fresh maintenance](../implementation/anonymous-product-telemetry-catalog.md#fresh-local-maintenance-coverage).
Their operation/path counts are not counts of fully qualified workflows.

## Delivery and collector

The [28 October certificate renewal qualification](2026-10-28-telemetry-certificates.md)
records 23 passing source tests, a real collector TLS request, 445 bound inputs
and successful preparation of the exact helper/private bundle/Certbot hook on
the existing free host. Its unchanged-material hook invocation left the memory
service running and no collector listener. This does not qualify public ingress,
provider privacy, actual running-service renewal or client resources/platforms.

The later [actual systemd rotation](2026-10-28-telemetry-systemd-rotation.md)
completed eight recorded checks with 440 bound source files and synthetic
certificates. Two reports returned 204; changed credentials restarted the
service, unchanged credentials did not, and an inactive service stayed
inactive. The original fixture's `200/CHDIR` parent-permission failure remains
retained. This is isolated loopback lifecycle evidence; issuer renewal,
public/provider privacy, resources and installed delivery remain open.

The [29 October systemd crash qualification](2026-10-29-telemetry-systemd-crash.md)
records six scoped checks with the same 440-file archive: one owned-process
`SIGABRT`, no kernel core-dump flag or matching core artifact, one configured
automatic restart and two successful synthetic TLS reports across the restart.
Cleanup was independently verified. This host used a file-based core handler;
the earlier WSL piped-handler results remain separate. Public/provider,
resource, whole-wire, installed/workflow and full privacy acceptance stay open.

| Date | Original evidence | Scope and boundary |
| --- | --- | --- |
| 29 October | [Joint-category consistency](2026-10-29-telemetry-joint-consistency.md) | Three original assertion failures retained. Unrounded intervals must admit probabilities summing to one; the publisher rejects impossible visible intervals while leaving withheld cells unknown. All 75 selected tests passed without failures or skips; Ruff check and format passed. Valid historical schemas, immutable reports, wiping, ln(3), wire parameters and count buckets remain unchanged. Sender authentication, general poisoning resistance and full population utility remain open; no production activation or full V08 acceptance. |
| 27 October | [Collector serving-process crashes](2026-10-27-telemetry-collector-crash.md) | Tests-only follow-up on `62b9ab71`: 21 passes, no failures/skips, including two real TLS-process crashes with standalone/fixture-inherited listeners. Linux/WSL2's piped core handler produced no kernel core dump; fixture logs/state and fresh report export stayed clean. 435 inputs matched. Earlier 19-case source evidence remains; production/provider, installed and non-Linux qualification stay open. |
| 27 October | [Browser/Python owners after saturation](2026-10-27-telemetry-owner-saturation.md) | Two original real Python TLS failures, an unwanted standalone activity import and one browser-source POST failure retained. Python: 137 distinct passes (136 unchanged plus the corrected MCP schema case); browser-source: 96 passes, zero skips, with mocked fetch/locks/admission. The legacy CI schema failure reproduced locally; its test now includes classic_cli and proves inspection adds no measurement. SDK/frontend builds passed; 852 inputs matched. Existing owners alone can reoffer prior work, with unchanged cadence, permission and budgets. The prior app comparison excludes these changes; no release, activation or full acceptance. |
| 27 October | [Deferred delivery after collection saturation](2026-10-27-telemetry-delivery-opportunity.md) | Two original actual Electron regressions retained: an exhausted recording path and an earlier cached snapshot refusal stranded queued work. Later awake work reoffers one prior committed stamp only through reviewed boundaries at the existing cadence; inspection/unknown categories do not offer. No timer, extra budget or cached authorization. Ready sends once; opt-out/close send zero. Final Electron Linux owner/TLS: 50 passes, no skips, including the earlier 47; browser-source: five browser-activity checks using the shared owner plus the same one preview. Builds passed; final inventory binds 851 files, with 690 CLI inputs unchanged. The failed app comparison is unchanged, its cause unproved. The [completed six-case app comparison](2026-10-27-telemetry-delivery-comparison.md) passed functional qualification but still failed resources. It predates the browser/Python follow-up; no original-run replay, causal saving or full acceptance. |
| 27 October | [Aggregate inference and difference attacks](2026-10-27-telemetry-aggregate-privacy.md) | Reusable offline assessment: 46 exact document-distribution scenarios across 23 views, known-background and rare/coincident-category fixtures, linked-report inference and explicit participation/policy counterexamples. Seventy distinct source tests include competing SQLite connections and rejected filtered routes; eight affected checks rerun after exact-fraction output correction, with 62 unchanged runtime checks reused. No production code, threshold, budget, collection or resource change; full privacy, useful-population, provider and platform qualification remains open. |
| 27 October | [Aggregate utility at current settings](2026-10-27-telemetry-aggregate-utility.md) | Source-bound arithmetic across all 23 views / 280 aggregate categories and four deterministic Python mean fixtures; no statistical coverage trial. At default weights, family/feature detail needs 26,215/65,536 total automatic reports in expectation. The 4,096-report simultaneous radius is about 13.49 percentage points; rare fixture cells remain suppressed. Linked-report composition is a conditional worst-case bound, not identity or participation privacy. Initial-adoption utility, poisoning resistance and ingress/privacy remain unqualified; no thresholds, budgets or production settings changed. |
| 27 October | [Python receive-window correction](2026-10-27-telemetry-receive-window.md) | The original burst charged 21,683 TLS bytes but produced 123,053 frame bytes, exceeding the unchanged 65,536-byte reservation. The corrected Linux Python case requested a 4,096-byte receive buffer before connect, required readback within 1–8,192 bytes, and observed 23,110 frame bytes. Both counters agreed without capture drops; malformed-response refusal, retained spending and lease cleanup passed. 32 transport tests passed, including four new OS-refusal cases. Original failure and five-case observation limits remain; no overall wire/retransmission, IPv6, other-platform, Electron/browser, resource, collector or installed qualification. |
| 27 October | [Python loopback wire accounting](2026-10-27-telemetry-loopback-wire.md) | Five segmented IPv4/TCP/TLS transport cases passed in a dedicated user/network namespace. TSO/GSO/GRO were disabled only there; aggregate packet and interface counters agree, with zero drops or unexpected frames. Observed frames total 798–6,717 bytes per case; every frame fits MTU 1,280 plus its link header. Spent reservations and lease cleanup passed; fixtures removed and disclosure unchanged. Earlier preflight errors and the first coalesced observation are retained. No physical-link/retransmission, native/browser, other-platform, rolling-day, RSS/CPU or production/privacy qualification. |
| 26 October | [Read-only ingress and retention review](2026-10-26-telemetry-ingress-review.md) | Production collector/listener absent. Existing free certificate and active renewal timer provide a candidate; one TLS 1.3/HTTP1.1-ALPN handshake using only bounded ISRG X1/X2 roots verified the existing memory listener without HTTP/report traffic or a route change. Corrected inventory found ten IPv4/IPv6 logging targets missed initially; UFW weekly/four-rotation logging and persistent journal presence remain unqualified. Public provider policies and backup metadata do not verify VPS logging/snapshot privacy. Both public memory health endpoints report 4.46.22; authenticated source/client and auto-update acceptance remain unestablished. No host mutation, private-key/network-log/backup-content read, production launch or full V08 qualification. |
| 26 October | [Release-owned TLS trust](2026-10-26-telemetry-scoped-trust.md) | Source follow-up based on `d2e55fbf`: route v2 permits at most two public CA certificates of at most 4 KiB each; native/Python trust has no ambient-root fallback, browser TLS unchanged. 78 distinct Python cases, 54 checks in the actual local Electron binary running Node mode, Ruff and Electron build passed. Python one-authority store: x509=1/crl=0/x509_ca=1, with certificate/hostname verification retained. Initial three lint collisions, the synthetic issuer-collision failure and fixture-only corrections remain retained; the independent repeated negative case is not counted twice. Existing approval/budget binding unchanged, no CA digest in reports. No RSS saving, resource pass, installed or production qualification; the completed resource result is recorded below. |
| 24 October | [Original delivery components](2026-10-24-telemetry-delivery.md) | Earlier codec/collector/publisher checks, 47 Python checks, six Node and six Electron codec checks, and 12-check plain-loopback HTTP journey. Not a product-sender or TLS/provider qualification. |
| 24 October | [Shared native/Python and browser budgets](../implementation/anonymous-product-telemetry-budget.md) | Original accounting, monotonic deadline, cleanup and browser-coordination receipts are retained in the design. Early 54-Python/18-Electron results preceded subsequent corrections. |
| 25 October | [Dedicated collector service](2026-10-25-telemetry-collector-service.md) | Actual TLS, minimal runtime and isolated VPS socket/sandbox checks. Initial staging failures remain; no production-provider privacy or client resource acceptance. |
| 25 October | [Closed-week report volume](2026-10-25-telemetry-weekly-volume.md) | Historical report v2 added a coarse global range after 64 reports, retaining the 4,096 per-view gate and immutable v1 reading; 67 source checks. Later report v3 restricts estimates to automatic reports. |
| 26 October | [Native handoff and release-resource guards](2026-10-26-telemetry-release-guards.md) | 37 Linux and 17 actual Windows x64 checks. Preserves six failed 4.46.15 native jobs, held 4.46.16 dispatch, watcher/slot reproduction and active-wire packaging correction. Six-target release qualification remains separate. |
| 26 October | [Installed model action diagnostics](2026-10-26-native-model-action-diagnostics.md) | Preserves the 4.46.17 Mac ARM librarian-save failure and 4.46.18 hold before dispatch. Eight source checks qualify closed operation/error classification. A focused Mac ARM installed journey passed on package 4.46.18/source `95c2000c`, including a real model download; the original cause remains unknown and the newer 4.46.19 batch is not thereby qualified. |
| 26 October | [Action ownership audit and completed boundaries](2026-10-26-telemetry-action-coverage.md) | Preserves the pre-fix 86-mapped/eight-unmeasured audit; adds menu, headless-control and explicit preparation owners with confirmed preference outcomes. Checkpoint inventory: 87 mapped/seven unmeasured. 64 Python, 24 distinct Electron/agent and 25 browser-source checks; local preparation uses stubs without inference or model downloads. Resource, current-batch native and production acceptance remain open. |
| 26 October | [Capture delivery and fresh telemetry](2026-10-26-capture-delivery-telemetry.md) | 4.46.21 source follow-up from baseline `28747e87`: unchanged receipt bodies, request-local fresh counts, preserved partial acknowledgements and capture in existing `result_items`. 172 distinct Python cases passed: 161 initially, then ten real PostgreSQL/HTTP cases after correcting the stale Studio fixture and one headless-history case; original guard failures retained. 111 Node controller/wire cases and both source builds passed. No second delivery owner or new coordinates/wire views; categories remain 94/87/seven. No browser journey, model calls, resource or installed-platform qualification. |

Current format and API details live in the
[delivery design](../implementation/anonymous-product-telemetry-delivery.md),
including [automatic categories and fixed reviewed reports](../implementation/anonymous-product-telemetry-delivery.md#automatic-categories-and-fixed-reviewed-reports),
and the [collector design](../implementation/anonymous-product-telemetry-collector.md).
Historical wire/report versions remain named in their own reports; they are not
claims about the current packet format.

## Admission, resource observations and architecture

| Date | Original evidence | Scope and boundary |
| --- | --- | --- |
| 29 October | [Phase-memory resource comparison](2026-10-29-telemetry-v3-resource.md) | Run 40967691671 on `1adc472` completed six Linux compiled-Electron cases, 2,301 inputs each, 128 cycles and one 25-byte report when enabled. Enabled main matched maxima 5,271,552 and 2,887,680 bytes stay above 2 MiB. File-backed growth of about 1.5–1.9 MiB is stable after first delivery and is not a named callsite. The r1 96-cycle and r1 opted-out final spikes are not repeated by r2. CPU is descriptive. No source change. Run 40965218896 and the original schema-3 verifier failure stay failed. Resource acceptance stays false. |
| 29 October | [Shared v3 client encoder](2026-10-29-telemetry-v3-client-encoder.md) | Shared Python and TypeScript encoding of the 25-byte summary, including disabled groups, missing sensors, release and OS axes, and unlisted coordinates. Sender integration, disclosure and transport switching, manual review, the compiled Electron bundle, installed resources and a live collector were not run. This does not accept the fleet or stand in for native release qualification. Production collection stays off. |
| 29 October | [V3 qualification probe listeners](2026-10-29-telemetry-v3-probes.md) | Probe listeners follow CollectorV3, `/v3/report` and the fixed 25-byte packet. Review retains only that exact synthetic packet. Unlabelled receipts stay historical v2. This does not qualify the pending client integration or rerun a resource comparison. Production collection stays off. |
| 29 October | [Opt-in phase-memory counters](2026-10-29-telemetry-phase-memory.md) | Client-only diagnostic for a future comparison. At the existing nine checkpoints it can record five Linux residency counters and four numeric V8 heap counters. Missing values stay null. It does not replace working-set RSS, pass the 2 MiB or 0.5 percent gates, or remeasure run 40523504727. Enabled maxima 2,572,288 / 2,859,008 bytes and every earlier resource failure remain failed. Pinned Linux report tests passed 44; the Windows chromadb import failure is an environment mismatch. Node parser tests passed 5. No source optimization and no new app comparison. |
| 27 October | [Completed SQL-read app comparison](2026-10-27-telemetry-sql-comparison.md) | Original run 40523504727 on `3034bc0b` passed six actual Electron journeys, 128 memory cycles / 387 successful API requests and 2,171 source bindings per case, with ownership/cleanup qualified. Each enabled case delivered one four-byte report; controls sent none. Enabled main matched RSS maxima 2,572,288 / 2,859,008 bytes and first renderer/GPU comparisons exceed 2 MiB. Resource acceptance stays false; CPU is descriptive and reservation allowance is not a wire measurement. No rerun or causal saving. |
| 27 October | [Confirmed opt-out negative hint](2026-10-27-telemetry-disabled-hint.md) | Two original regressions retained: missing disabled-reply callback and redundant native SQLite read. Confirmed user opt-out now carries its original monotonic expiry into later owner creation; existing file/day checks and 250 ms / 60 s bounds remain. No positive permission cache, extra SQLite read, timer, worker or sideband file. Actual Electron with the real Python helper: 116 passes, zero failures, two Windows-only skips; SDK/native builds passed and 623 inputs unchanged. Inventory rows unchanged. No enabled-mode optimization, RSS saving, new app comparison or installed/platform/resource acceptance. |
| 27 October | [Completed desktop delivery comparison](2026-10-27-telemetry-delivery-comparison.md) | Run 40483350394 on 29dcd70d succeeded, qualifier 0: six 128-cycle journeys, 387 successful API requests and 2,143 matched source files per case, actual setup/process controls and cleanup. Each enabled case delivered one four-byte report; unavailable/opted-out sent none. Enabled main matched RSS maxima 3,768,320 / 3,129,344 bytes still exceed 2 MiB. Both orders, renderer/opted-out comparisons, endings and descriptive CPU are retained. No causal savings or current browser/Python qualification; original 40477197149 remains failed with cause unproved. No further comparison selected. |
| 27 October | [Catalog comparison: failed original](2026-10-27-telemetry-catalog-comparison.md) | Run 40477197149 on `bc4d6e08` failed. All six cases completed 128 memory cycles and 387 successful API requests each, with recorded process/setup controls, no page errors and cleanup. Five journeys completed. First enabled reserved/sent one four-byte report; second enabled recorded 65 telemetry writes but reserved/sent none. Cause unestablished. Summary was skipped and the qualifier rejected its absence. Original evidence retained without an app rerun; no full runtime-input/privacy qualification or RSS/CPU saving is inferred. |
| 27 October | [Fixed catalog lookup residency](2026-10-27-telemetry-catalog-residency.md) | A 128-iteration fixture reduced recurring metric/resource enumerations, family splits and bucket-callback searches from 128/384/640/384 to zero after construction. Only fixed release metadata is reused. Actual Electron passed 47 checks with two Windows permission skips; 30 browser-source checks, Python parity for 65,536 cells/six invalid inputs/981 observation and bucket cases, and all builds passed; 771 checked inputs retained. Initial fixture error and genuine original regression remain separate. Its [original six-case comparison](2026-10-27-telemetry-catalog-comparison.md) completed with failure and incomplete enabled delivery; no RSS/CPU saving or resource acceptance. |
| 27 October | [Source-kernel controls and retained diagnostic failure](2026-10-27-telemetry-probe-controls.md) | Original run 40470335733 on `d56d578f` failed after three cases completed 128 memory cycles and 387/387 API requests each, with cleanup. Unavailable made no status call; opted-out/enabled each received one actual reply. Opt-out correctly had no acknowledgement, writes or reports; enabled sent one four-byte synthetic report to the isolated collector. Correcting the diagnostic expectation passed 35 report tests and Ruff. Independent retained analysis matched 2,130 source inputs per case and verified all three control states, with four additional private mutation assertions. Earlier 33 tests/19 assertions remain historical. No app rerun or original rewrite; the workflow remains failed and full-workflow/resource/installed/privacy acceptance remains unqualified. |
| 27 October | [Resource process-role controls and completed comparison](2026-10-27-telemetry-resource-roles.md) | Run 40453953300, source `6ac77003`: six 128-cycle functional cases, 2,114 matched source files each, 2,322 successful fixture API requests, verified main/renderer identities and cleanup. Allocation attribution was disabled. Enabled main matched maxima were 3,579,904/3,366,912 bytes; renderer maxima were 5,664,768/5,193,728 enabled and 5,111,808/5,136,384 opted out. Both orders, opted-out main, endings and CPU deltas are retained in the report. Old run 40416923461's second `Tab` remains unidentified. Resource acceptance remains false; no causal saving or general CPU/platform/privacy qualification. All failures and budgets retained; no new run selected. |
| 27 October | [Metadata-allocation resource result](2026-10-27-telemetry-metadata-allocation-results.md) | Source `192b0df9`, run 40416923461: six functional cases, 2,075 matched source inputs each and cleanup passed. Enabled main matched maxima 9,261,056/2,936,832 bytes and ending matched-phase differences 9,261,056/1,593,344; both maxima exceed 2 MiB. Both orders and all roles retained; first enabled renderer comparison is unavailable due to initial-role ambiguity. CPU remains descriptive. These profiled diagnostics establish no causal regression, production-only overhead or resource/platform/privacy acceptance. Prior failures and budgets retained; no new resource run selected. |
| 26 October | [Repeated metadata allocation](2026-10-26-telemetry-metadata-allocation.md) | Fixed tests reduced URL derivations/filter descriptions/certificate decodes from 5/3/130 to 1/0/1; unavailable trust remains zero. Only fixed metadata is reused; authority checks stay fresh. Actual Electron passed 100 checks with two Windows-specific skips; 134 browser-source tests and both builds passed. All 65,536 numeric cell classifications agree with Python; six other invalid inputs are rejected. Original failures retained. The [completed six-case diagnostic](2026-10-27-telemetry-metadata-allocation-results.md) still exceeds the RSS ceiling; no RSS/CPU saving or resource/platform/privacy acceptance. |
| 26 October | [Browser admission and review](2026-10-26-telemetry-browser-admission.md) | Cancellation now follows the page owner through eligibility and sensor startup; 134 browser-source tests and the frontend build passed. Actual Chromium passed ten compiled-app review checks across two launches, three memory cycles/nine operations and 161 successful fixture HTTP requests including assets; 2,185 source/existing compiled inputs matched. One approved four-byte TLS report matched inspection, with real nominal pressure, cross-tab opt-out and restart persistence. Temporary-certificate SPKI exception leaves production trust unqualified. Prior timeout remains unexplained; original fixture failures and missing first Python cleanup receipt are retained, while second/final cleanup passed. No resource, installed-platform or provider/privacy acceptance. |
| 26 October | [Cold-start allocation corrections](2026-10-26-telemetry-cold-start.md) | Original compiled runtime reproduced one bundled TLS-list load and 32 missing-policy exceptions. Source selects only required TLS APIs and uses nonthrowing absent-policy reads, without broadening trust or caching permission. Two ordinary-Node tests passed; actual Electron passed 95 checks with two platform skips, and its build passed. One fixed corrected two-case diagnostic completed 128 cycles/384 operations and 387 HTTP successes per case, one enabled four-byte report, no unavailable report/models/forbidden metadata, matched input manifests and cleanup. Weighted enabled samples: bundled-root getter 169,872→0 bytes; lstat 277,364→7,252. Allocation samples are not RSS/CPU savings or acceptance. Prior failures and budgets retained; no additional resource trial selected. |
| 26 October | [Browser pressure startup and sample freshness](2026-10-26-telemetry-browser-pressure.md) | Source uses a three-second initial wait and the actual OS sample time for the unchanged two-second freshness ceiling. Nine unit tests and the separately completed frontend build passed. Final-source Chromium 155.0.8059.12 refused at 3,002.1 ms without a usable signal; cause unknown, nominal qualification open. Original 1,002.6 ms refusal, separate 1,055 ms reference and historical startup-only 2,089.3 ms pass remain retained, as do both unit reproductions and the pre-launch dependency error. Actual probes used no sensor override, report or model call; cleanup passed. No further pressure trial, resource trial, TLS/allocator replacement or budget increase selected; full-app/delivery and resource acceptance remain open. |
| 26 October | [Scoped-trust resource result](2026-10-26-telemetry-scoped-trust-results.md) | Source `4b8e8a3e`, run 40386632526: six functional cases, 2,053 matched source files each, cleanup passed. Enabled main matched maxima 4,341,760/3,428,352 bytes and endings 2,625,536/3,215,360 still exceed 2 MiB. All roles, opted-out controls and prior failures remain retained. Ambient fixture trust differed across revisions, preventing isolated causal savings; combined CPU is descriptive, not per-process acceptance. Budgets unchanged, resource gate fails, no repeat measurement selected and no platform/privacy acceptance. |
| 26 October | [Fixed allocation resource follow-up](2026-10-26-telemetry-allocation-followup.md) | Source `4779cf11`, run 40372901181: all six cases match 2,045 files each; 2,322 successful fixture API requests, 2,304 memory operations, no model calls, cleanup passed. Enabled main matched maxima 3,145,728/3,186,688 bytes and endings 2,768,896/2,428,928 exceed 2 MiB. Both opted-out comparisons and other process roles retained; combined CPU differences are descriptive. Resource gate fails; no causal improvement claim, budget change or workload replay. |
| 25 October | [Native network conditions](2026-10-25-telemetry-native-conditions.md) | Windows/Linux OS cost components, retained COM/D-Bus failures and corrections; 2.11/2.23 MiB component RSS observations exceed the full-feature target. [Mac ARM64/x64 follow-up](2026-10-25-telemetry-native-conditions.md#macos-component-follow-up) is Node/Python, not installed Electron. |
| 25 October | [Producer saturation/opt-out overhead](2026-10-25-telemetry-producer-overhead.md) | Denial-only hints and actual headless source/TLS fixtures. Preserves above-target 3.27 MiB opted-out and 6.40 MiB enabled results, prior outcomes and packaging-fixture CI failures. |
| 25 October | [Memory workload and denial allocation](2026-10-25-telemetry-memory-profile.md) | 384 actual API requests per variant, main-process Studio wrapper; 4.41 MiB enabled ending difference and 6.59 MiB default-mode growth remain unaccepted. Not renderer/IPC qualification. |
| 25 October | [Denial I/O and synchronous refusal](2026-10-25-telemetry-denial-io.md) | Bounded 250 ms negative-observation reuse, retained first test/run failures, and later 1.89/4.43 MiB opted-out/enabled diagnostic. One lower observation is not a resource pass. |
| 26 October | [Actual renderer/IPC journeys](2026-10-26-telemetry-renderer.md) | Three development-app variants, 387 requests each; original harness failures and later compiled-run outcomes remain retained. The 1.143% CPU difference is descriptive, not stable overhead. |
| 26 October | [SQLite cleanup and compiled follow-up](2026-10-26-telemetry-sqlite-cleanup.md) | Mechanism diagnostics plus source `b9a2988` run 40260081248: ending main difference 1,875,968 bytes versus sampled peak 3,440,640. No causal improvement or resource pass. |
| 26 October | [Fixed six-case attribution](2026-10-26-telemetry-attribution.md) | Source `dc98218c`, run 40265207114: enabled matched maxima 3,608,576/3,391,488 bytes. Both triplets, other roles, original offline findings and first-call overlap limits retained. |
| 26 October | [Storage ownership review](2026-10-26-telemetry-storage-ownership.md) | Cold initialization/runtime ownership choices, shared private state and existing desktop lifetime; no new daemon or performance acceptance. |
| 26 October | [Storage slot and helper ownership](2026-10-26-telemetry-storage-slot.md) | Separate concurrent burst went from 32 live handles to one; ownership lasts through actual close/exit. This is not evidence that concurrency caused all earlier RSS growth. |
| 26 October | [Fixed storage follow-up](2026-10-26-telemetry-storage-followup.md) | Source `de53ba46`, run 40290150459: six journeys, 1,998 files each, 2,322 API requests/2,304 operations, no models, cleanup passed. Enabled maxima 3,121,152/3,235,840 and endings 2,125,824/2,207,744 bytes remain above 2 MiB; all other roles/outcomes retained. |
| 26 October | [Private storage-adapter feasibility](2026-10-26-telemetry-storage-adapter.md) | 39 functional passes/two Windows-only skips across original selection and corrected isolated case. Original v1/v2/staging failures and shutdown review retained. Unmapping is not RSS savings; backend remains unadopted. |
| 26 October | [Pinned private SQLite allocator](2026-10-26-telemetry-private-sqlite.md) | 60 functional passes/two platform skips across the retained original and isolated corrected case. Exactly four resource launches, one pre-measurement fixture failure; incomplete counterbalance. Higher CPU and sampled peak RSS do not justify adoption. No product backend or budget change. |
| 26 October | [Transaction metadata and dependency ownership](2026-10-26-telemetry-query-ownership.md) | Common dependency splitting is not justified for the existing resource gate. Later transaction-local source uses fewer statement wrappers (608 to 384) and query rows (571 to 347) over 32 accepted pairs, with identical queue/budget and one live handle. 67 Node checks passed with two Windows-only skips; no resource benchmark, installed or RSS/CPU acceptance. Follows frozen 4.46.22 and awaits the next release batch. |
| 26 October | [Aggregate CPU admission](2026-10-26-telemetry-cpu-admission.md) | Linux/macOS fixed aggregate reads retain admission checks; 2,883,584-byte component RSS observation is not full resource acceptance. |
| 26 October | [Headless Windows network cost](2026-10-26-telemetry-headless-network.md) | 82 focused checks and direct Python/native-helper agreement on Windows x64. Original fixture failure retained; no installed/resource or production qualification. |

The older aggregate report also retains the **3.61/3.27/3.09 MiB** component
observations and later **1.19 MiB** headless activation result. None replaces
the others or qualifies whole-app, all-platform or CPU overhead. Ending growth,
sampled maxima, phase-matched differences and profiled CPU remain separate
quantities; shared pages, unsampled helpers and run/allocator variation limit
causal interpretation. The pinned allocator experiment ended at its fixed stop
rule. A further optimization needs a new evidence-supported implementation
hypothesis; no unchanged benchmark or budget revision is selected.

## Prior milestone and interpretation

V08 became the active milestone after
[fresh backup and independent restore](2026-10-24-4465-backup-acceptance.md)
passed at 00:01:45 and 00:15:23 UTC on 24 October. Those operational acceptances
do not qualify telemetry. Existing
[private workspace metrics and security audit](../implementation/observability-and-evaluations.md)
remain separate from optional product collection.

Use each report's original hashes and source/run bindings when reviewing a
claim. Local tests, isolated synthetic inputs, real loopback TLS, compiled
development apps and installed release targets have different scopes.
Publication of disabled controls is not production telemetry activation.

Release-gate evidence: [27 October scanner-boundary correction and 4.46.29 publication](2026-10-27-release-scan-boundary.md).
Corrected verifier 40423232306 passed; 4.46.29 was published at
2026-10-27T00:03:26Z with all 38 original assets unchanged. The original rejection
is retained; later-source and full telemetry qualification remain separate.

The [Sparkle metadata correction and 4.46.37 publication](2026-10-27-sparkle-metadata-scan.md)
retain the original verifier failure. Corrected normal verifier **40473744894**,
on source `8c7d5847`, passed with **zero scan findings**. Version 4.46.37 was
published at **2026-10-27T08:34:37Z**, with all **38 original assets unchanged**
and the tag matching release source `629a7afc`. The
[artifact](releases/4.46.37-artifacts.json) and
[publication](releases/4.46.37-publication.json) receipts retain the source and
inventory bindings and their initial follow-up dispatches. The later retained
release observer confirms website run **40474480217** succeeded at
**2026-10-27T08:35:19Z** and public-updates run **40474484566** at
**2026-10-27T08:46:37Z**. These workflow results do not establish an upgrade on a
particular PC or VPS. Telemetry runtime, V08 Building and all requirement/
acceptance states remain unchanged.
