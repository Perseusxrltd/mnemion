# Mnemion product roadmap

Reviewed source distribution: **4.46.33**.
Public distribution: [current release status](RELEASE_STATUS.md). Roadmap updated: **2026-10-26**.

Download from the [Perseus XR product page](https://www.perseusxr.com/mnemion).
[Release status](RELEASE_STATUS.md) and the [maintenance board](MAINTENANCE_STATUS.md)
update automatically. This page sets delivery order; the [66 requirements](PRODUCT_REQUIREMENTS.md)
preserve every requested outcome and its evidence.

Strict full-scope completion is **17/66 shipped (25.8%)**: 42 partial,
1 building, 2 planned, 3 ongoing and 1 external. Requirements differ greatly in size.
This measures complete requested capabilities, not time spent or the usability
of the released app. A hotfix does not finish a broader requirement.

Every release starts with current GitHub reports from real deployments. Batch
the ready fixes and add a verified roadmap improvement when possible; urgent
repairs take precedence. Preserve failed reports and unfinished scope until
their actual acceptance passes. The [release process](MAINTENANCE.md) keeps
issue review, publication and version-linked closure together.

## Current delivery checkpoint

These entries preserve dated source and acceptance evidence as historical
snapshots. The generated [release status](RELEASE_STATUS.md) owns current public
availability and release gates; each deployment requires its own acceptance.

**26 October 2026, V08 browser pressure:** [Bounded startup and OS-sample freshness](validation/2026-10-26-telemetry-browser-pressure.md) passed nine unit tests and the frontend build, but the final-source browser refused at 3,002.1 ms without a usable signal, so nominal-browser/full-app/resource acceptance remains open with no further trial selected, all 66 states unchanged and V08 Building/inactive.

**26 October 2026, source-app report review and approval handoff:**
[The completed journey](validation/2026-10-26-telemetry-app-review.md) passed
nine review checks in the compiled Linux app, including one TLS report matching
inspection and opt-out/manual-mode/spending persistence across restart. All
2,172 source and compiled inputs matched. A shared owner fix gives explicit
approval a bounded opportunity after recent automatic activity; privacy and
spending gates remain unchanged. Separately, 24 Electron-runtime and 14
browser-source tests passed without skips; original failures remain retained.
No new resource run was selected, and the
[scoped-trust result](validation/2026-10-26-telemetry-scoped-trust-results.md)
still fails 2 MiB. All 66 states remain unchanged; V08 stays Building and inactive,
with actual web-browser, installed-platform, resource and privacy acceptance open.

**26 October 2026, release-owned telemetry TLS trust source:**
[The scoped trust follow-up](validation/2026-10-26-telemetry-scoped-trust.md)
limits native/Python trust to at most two bounded release CA certificates while
retaining certificate/hostname verification and existing privacy, review and
budget fences. Browser TLS is unchanged. 78 distinct Python cases, 54 checks in
the actual local Electron binary running Node mode, Ruff and the Electron build
passed; original fixture failures and corrections are retained. No RSS saving
or resource acceptance is claimed; one fixed changed-source follow-up is planned
after integration. All 66 states remain unchanged, V08 stays Building, collection
is off, destination/address are null and authorities are empty. Resource,
whole-wire, provider/privacy and installed-platform gates remain open.

**26 October 2026, scanner recovery and fixed resource follow-up:**
[Scanner initialization](validation/2026-10-26-linux-package-recovery.md) now has
one narrowly classified acquisition retry and fixed safe failure diagnostics.
37 focused tests and a fresh pinned local scanner run passed, including six
canaries and 625 generated files with zero findings. The original hosted Linux
cause and future native release acceptance remain open. The
[six-case resource follow-up](validation/2026-10-26-telemetry-allocation-followup.md)
completed, but both enabled main RSS maxima and endings still exceed 2 MiB.
All original outcomes remain; no causal improvement, rerun or budget change is
claimed. All 66 states remain unchanged; V08 stays Building with collection off.

**26 October 2026, installed 4.46.22 privacy-review controls:**
[Original artifact qualification](validation/2026-10-26-telemetry-installed-review.md)
passes eight telemetry fields on all six targets, including review choice before
permission, app/native mode changes and opt-out/manual-mode restart persistence.
Five targets come from attempt 1; Mac ARM alone comes from the later capacity
retry. No new build, app run or model call was needed. Report staging, approval,
delivery, later owners, 4.46.25 installed behavior and actual PC/VPS upgrades are
not qualified. All 66 states remain unchanged; V08 stays Building with collection
off and resource/provider privacy gates open.

**26 October 2026, saved-workspace and backup-list telemetry source:**
[The selection follow-up](validation/2026-10-26-telemetry-workspace-selections.md)
lets explicit saved restore choose open or switch from the verified transition,
using one original privacy snapshot and clock. Automatic resume remains excluded;
explicit app/native backup inventory owns list success without backup-validity
or cloud-delivery claims. Current coverage is 93 mapped/one unmeasured category
and 632 declared action rows; independent `update.verify` stays inside the existing
download cycle. Source checks passed 30 distinct Python cases, 69 compiled Node
cases plus one Node/Python SQLite policy case, and 25 browser-source cases, with
both builds passing and no Node skips. Two initial Python fixture failures and
their test-only corrections are retained. All 66 requirement states remain
unchanged; V08 stays Building and inactive, with resource, provider privacy and
installed acceptance open.

**26 October 2026, capture action ownership and CI capacity recovery:**
[The source follow-up](validation/2026-10-26-telemetry-capture-actions.md) keeps
one capture-cycle owner while distinguishing verified delivery-only work, and
maps explicit conversation preview and standalone capture pause. Current coverage
is 91 mapped/three unmeasured categories and 630 declared actions. Capture checks
passed 109 distinct Python, 154 compiled desktop/store Node and 120 browser-source
cases, with two Windows-only skips and both builds passing. The narrow latest-main
CI capacity retry passed 41 separate mocked guard tests. Original failures and
test corrections are retained. All 66 requirement states remain unchanged;
V08 stays Building and inactive, with resource, provider privacy and installed
acceptance open. These source results do not establish publication.

**26 October 2026, automatic host-update telemetry source:**
[The dedicated server updater](validation/2026-10-26-telemetry-host-updates.md)
now owns fresh staging, compatible apply and rollback under its own acknowledged
host-account policy. Its existing waits can offer bounded queued or approved
reports, with no extra periodic wake or shutdown flush. 164 distinct Python
cases and frontend/Electron builds passed; original fixture failures are retained.
The current inventory has 88 mapped/six unmeasured categories and 628 declared
actions. This also batches the transaction metadata optimization after 4.46.22;
V08 remains Building with resource, provider privacy and installed acceptance open.

**26 October 2026, source coverage checkpoint:** the
[telemetry privacy inventory](validation/2026-10-26-telemetry-coverage.md)
distinguishes 86 mapped categories from eight unmeasured categories in the app,
browser and native agent controls. Its contents are generated and checked from
Git source maps. The [pinned SQLite allocator experiment](validation/2026-10-26-telemetry-private-sqlite.md)
was rejected after the fixed component results showed higher CPU and peak RSS.
No backend or resource budget changed. V08 remains Building; these catalog
counts do not change the full-roadmap percentage or establish active telemetry.

**26 October 2026 publication checkpoint:** [4.46.13 is public](releases/4.46.13.md),
with [all six installed targets, artifact verification and website sync passed](validation/2026-10-26-44613-native-acceptance.md).
Public automatic-update checks remain in progress at this checkpoint. The last
separately verified actual Windows/shared-host pair remains
[4.46.6](validation/2026-10-26-issue45-acceptance.md). V08 stays Building with
collection unavailable and destination/route null; publication does not close
its resource, privacy or remaining acceptance gates.

At **26 October 2026, 03:55 UTC**, the [one six-case attribution run](validation/2026-10-26-telemetry-attribution.md)
has completed with all functional journeys and reviewed source matches. Both
enabled matched main-process RSS maxima exceed 2 MiB. Cold initialization and
storage-runtime ownership review is next; no benchmark repeat or budget revision
is selected. V08 remains Building, with the 2 MiB / 0.5% gates unaccepted and
production collection disabled. Frozen 4.46.13 remains a separate native/public
acceptance gate at that earlier checkpoint.

- **V08 renderer and IPC — 26 October 2026; source evidence.** The
  [development-app journey](validation/2026-10-26-telemetry-renderer.md) passed
  all three variants, each with 387 real fixture API requests through onboarding
  and the sandboxed renderer/IPC path. Opt-out collected nothing; enabled sent
  one four-byte TLS report. The descriptive CPU difference was 1.143% of one
  core; the unchanged 2 MiB RSS / 0.5% CPU targets remain unaccepted. V08 stays
  Building, production collection disabled, and installed acceptance open.

- **Native telemetry deadline check — 25 October 2026; source validation.**
  The [Windows release assertion](validation/2026-10-25-native-telemetry-deadline.md)
  mixed the transport lifetime with later cleanup. The corrected check observes
  the peer's real connection close against the reservation deadline and holds
  cleanup completion independently. Final Windows and Linux selections each
  passed all 15 cases; the timing allowance and production transport are unchanged.
  [4.46.10](releases/4.46.10.md) retains the other unreleased repairs and adds
  coarse weekly report volume. Native release and installed acceptance remain
  required; production collection stays disabled.

- **Coarse weekly telemetry volume — 25 October 2026; source validation.**
  The [reporting follow-up](validation/2026-10-25-telemetry-weekly-volume.md)
  retains one global power-of-two contribution range after 64 accepted reports.
  Detailed views still require 4,096 each; older immutable report-v1 records
  remain readable alongside v2. All 67 focused checks passed. This supplies
  limited volume information, not people/adoption counts or qualified detailed
  launch statistics. Collection remains disabled; V08 stays Building.

- **Windows test-helper recovery — 25 October 2026; 4.46.9 candidate.**
  [Windows readiness records](validation/2026-10-25-windows-telemetry-test-lifecycle.md)
  exposed an LF-only assertion and waiting helpers that stalled the unpublished
  4.46.8 release. Bounded, complete-line handling now accepts LF/CRLF and stops
  helpers before removing their SQLite fixtures; desktop tests have a ten-minute
  step limit. Focused Windows checks passed **31/31**; Linux passed **29 with
  two Windows-only skips**. [4.46.9](releases/4.46.9.md) retains the managed-backup
  correction and collector isolation. Native release and installed acceptance
  remain separate gates; production telemetry stays disabled.

- **Collector host isolation — 25 October 2026; isolated VPS acceptance.**
  The [collector service check](validation/2026-10-25-telemetry-collector-service.md)
  exposed a port restriction that the host did not enforce. A service-manager
  listener now permits blocking every collector bind and outbound connection.
  Both denials, configured resource limits, synthetic TLS requests and absence
  of request details in checked storage/logs passed on the VPS; the temporary
  service and listener stopped cleanly. Eleven local collector checks passed.
  Production ingress/privacy, client resources, reporting usefulness and
  installed release acceptance remain open; V08 is Building and collection off.

- **Dedicated telemetry collector — 25 October 2026; source implementation.**
  The [separate TLS service](implementation/anonymous-product-telemetry-collector.md)
  strips request metadata before aggregation and uses a locked three-package
  HTTP runtime. [Verification](validation/2026-10-25-telemetry-collector-service.md)
  records 45 scoped passes, seven clean-runtime passes and an additional real
  HTTP-header leak check. CI now verifies that minimal runtime automatically.
  The deployment template, production ingress/privacy, resources and installed
  telemetry release remain unqualified; V08 stays Building and disabled.

- **Native build portability — 25 October 2026; 4.46.8 source candidate.**
  [Windows launcher and Linux C11 failures](validation/2026-10-25-native-build-portability.md)
  prevented 4.46.7 native qualification. The unpublished candidate is superseded
  by [4.46.8](releases/4.46.8.md), which retains the managed backup-capture fix.
  The normal Linux/Node command compiled the helper and passed **417 tests with
  three existing Windows-only skips**. Native release and installed acceptance
  remain pending; public and installed 4.46.6 remain the last verified baseline.
  No requirement state or production telemetry gate changes.

- **Managed backup contention — 25 October 2026; 4.46.7 source hotfix.**
  [Scheduled snapshot/ledger failures](validation/2026-10-25-host-backup-capture.md)
  prompted a bounded operator-lock wait for managed captures, with fresh
  settings and runtime-transition checks afterward. Targeted verification records
  **17 passes across retained logs**; original fixture failures remain preserved.
  The unpublished [4.46.7](releases/4.46.7.md) candidate is superseded by
  [4.46.8](releases/4.46.8.md), whose native and installed acceptance remain
  pending. The existing ledger job's natural completion and independently
  verified delivery preserve an older snapshot plus a newer ledger; they are
  separate evidence.
  All 66 requirement states and the V08 production gates remain unchanged.

- **Active feature — V08, 24 October 2026; Building/source implementation.**
  [Fresh backup and independent restore](validation/2026-10-24-4465-backup-acceptance.md)
  passed at **00:01:45** and **00:15:23 UTC**. Work now advances the complete
  [anonymous product telemetry contract](implementation/anonymous-product-telemetry.md).
  Source privacy controls, the **19-check core browser journey** and **eight
  browser policy/fault checks** passed; [source-input qualification](validation/2026-10-24-telemetry-controls.md)
  passed at **01:12:30 UTC**. Later source adds bounded transport components and
  [application-owner/connection controls](validation/2026-10-24-telemetry-app-owners.md);
  its source checks and **19-assertion Chromium owner fixture** passed, with
  synthetic CPU admission. A subsequent [browser company-policy refresh](validation/2026-10-24-telemetry-company-refresh.md)
  checks restrictions before reserved reports; focused source checks and its
  **20-assertion Chromium journey on 25 October** passed, with synthetic CPU
  admission, a passing frontend build and verified fixture cleanup.
  Later [native network-admission source work](validation/2026-10-25-telemetry-native-conditions.md)
  adds OS cost flags and eligibility checks before gauges; focused network and
  packaging checks passed. Later [macOS Python/Node component probes](validation/2026-10-25-telemetry-native-conditions.md#macos-component-follow-up)
  passed; Electron and installed-client qualification remain open. Final Windows
  Node/Linux Electron components measured **2.11/2.23 MiB added RSS**, above the
  unchanged 2 MiB full-feature target; this is not full resource acceptance.
  [Producer denial hints](validation/2026-10-25-telemetry-producer-overhead.md)
  passed focused source checks and reduced repeated denied work in a synthetic
  desktop/TLS diagnostic. Opted-out/enabled RSS remained **3.27/6.40 MiB**, above
  that same target; representative-workload and all-platform acceptance remain open.
  A subsequent [denial-allocation and real-memory diagnostic](validation/2026-10-25-telemetry-memory-profile.md)
  adds fixed SDK/API/PostgreSQL transactions. Focused source checks passed;
  all three variants completed **384 requests each**, but enabled ending RSS
  growth exceeded unavailable by **4.41 MiB**. The default synthetic mode still
  measured **6.59 MiB** enabled growth. The 2 MiB and 0.5% CPU targets remain open.
  The next [denial-I/O source change](validation/2026-10-25-telemetry-denial-io.md)
  reuses negative observations for up to **250 ms**, allowing brief sample loss
  after re-enable while retaining fresh checks for admitted work. Focused Python
  and corrected native checks passed; the first burst measured
  **2.41/4.83 MiB** opted-out/enabled RSS, above the unchanged target.
  Later synchronous native snapshot refusals avoid an extra Promise/await;
  their final source checks and second burst passed, measuring **1.89/4.43 MiB**
  opted-out/enabled RSS. A single opted-out observation does not qualify the full
  resource target; enabled RSS and all-platform acceptance remain open.
  Collection is unavailable,
  with no active collector, qualified public ingress or all-six-native acceptance.
  This work is excluded from the isolated 4.46.6
  dependency-security release. Only V08 moves from Planned to Building; all 66
  requirement texts and all other states are preserved. Earlier failures and
  dated Planned checkpoints below remain historical evidence.

- **New planned scope — 23 October 2026.** V08 retains the user's
  [anonymous product telemetry request](implementation/anonymous-product-telemetry.md):
  aggregate usage and performance/resource/bandwidth measurements, disclosed
  default enablement, persistent opt-out/re-enable, company policy and native-agent
  controls. The anonymity and native/web acceptance contract excludes contents,
  stable identifiers and identifying collector logs. This is queued after the
  current live-update/independent-host milestone; it is not shipping or included
  in frozen 4.46.1. The previous 65 requirement texts and states are preserved.

- **4.46.4 native qualification — 23 October 2026, 18:37:18 UTC.**
  [All six installed targets](validation/2026-10-23-4464-native-acceptance.md)
  passed 59 required observations each on workflow attempt 1, bound to frozen
  source `4e64aad4` and the saved job/artifact evidence. Artifact verification
  was still running at 18:38 UTC; public-upgrade and actual Windows/shared-host
  4.46.4 acceptance require separate evidence. No fresh backup delivery or
  independent restore is accepted. The later 4.46.5 transfer diagnostics are
  excluded from this source; all 66 requirement states and V08 remain unchanged.

- **Backup transfer diagnostics — 23 October 2026; UNRELEASED.** The
  [source change and local measurement](validation/2026-10-23-backup-transfer-diagnostics.md)
  preserve delivery intent, bounded progress and fixed failure guidance, and
  disable compression/delta search with one Git packing thread. Four synthetic
  local trials measured about 2.1× faster processing with exact file hashes;
  this is not a WAN or live result. Nineteen focused checks passed, with two
  local SSH-fixture skips, and the frontend build passed. Frozen 4.46.4 excludes
  this work. The original backup remains uncertain; no retry/resume action,
  fresh delivery or independent restore is accepted. Requirement states and
  V08's Planned, inactive status remain unchanged.

- **4.46.3 two-custodian lifecycle — 23 October 2026, 16:25:34 UTC.** The
  [actual host-control journey](validation/2026-10-23-4463-custody-acceptance.md)
  passed using both original permanent custodians: Windows stopped memory,
  both clients inspected with its API down, deliberate stop survived a manager
  restart and two scheduled watchdog ticks, and the native-agent custodian
  started the original service. Final readiness, saved human connection and
  the unchanged 15-request content/access/MCP comparison passed. Original
  observation/import failures remain preserved; no service action or enrollment
  was replayed. Fresh backup and independent restore remain pending. No
  whole-machine boot, separate physical-device custody, provider wake or
  controller-authority escrow is claimed, and no requirement state is promoted.

- **Backup inventory throughput — 23 October 2026; UNRELEASED.** The
  [chosen source comparison](validation/2026-10-23-backup-inventory-throughput.md)
  selects collated JSON once and retains a constant second column for tuple-sort
  memory accounting. All six synthetic original/4× cases preserve exact row
  counts, bytes and SHA-256 at 1 MB `work_mem` and 32 MB shared buffers; chosen
  backend RSS growth stayed about 2.25–3.32 MiB. No live backup acceleration or
  fresh backup/restore acceptance is claimed. Requirement states and
  V08's Planned, inactive status are unchanged.

- **Legacy vendor-telemetry correction — 23 October 2026; UNRELEASED.** A
  [separate source fix](validation/2026-10-23-legacy-vendor-telemetry.md) explicitly
  disables Chroma's vendor telemetry for legacy clients. The no-send baseline
  recorded five SDK capture calls, not network transmissions. The corrected
  subprocess recorded zero vendor calls, network attempts or new identifiers;
  52 focused checks and lint/format checks passed. Frozen 4.46.3 is unchanged,
  and V08 product telemetry remains Planned and inactive.

- **4.46.3 actual paired acceptance — 23 October 2026, 15:54:32 UTC.** The
  [actual Windows/shared-host pair](validation/2026-10-23-4463-live-acceptance.md)
  passed after the compatible host operator completed at **15:27:40 UTC**.
  Three identities, exact sampled memories and protected login/preferences
  were retained; the 15-request external comparison and fresh 42-request lab
  passed with complete cleanup and zero production memory writes or cloud
  calls. The original access interruption and failed deletion cycle remain
  preserved. The final continuation requested no additional update, restart
  or lab cycle. Full custody operations, fresh backup and independent restore
  remain pending; #44/#45 stay open and the local-note publisher stays paused.
  The [release-description synchronization](validation/2026-10-23-release-description-sync.md)
  also passed its real workflow and public readback. All 66 requirement states
  are unchanged; V08 remains Planned and inactive.

- **4.46.3 native/public-update qualification — 23 October 2026, 15:03 UTC.**
  [All six installed targets](validation/2026-10-23-4463-native-acceptance.md)
  passed 59 required fields each on fresh workflow-attempt-two jobs. The first
  attempt's unassigned macOS ARM database job and original recorder refusal
  remain preserved. Publication completed at **14:50:04 UTC**, and independent
  artifact verification passed. Public-update run `39973022163` completed
  successfully across all six platform/architecture jobs; the result was
  verified at **15:03 UTC**. [Release status](RELEASE_STATUS.md) tracks evolving
  gates. The host still reported 4.46.1 at 14:56:53 UTC. Its existing guarded
  update job was dispatched at **15:02:27 UTC** and was active/running, with no
  accepted host-update receipt yet. Actual 4.46.3 paired acceptance, the full
  custodian lifecycle, fresh backup and independent
  production restore remain pending. The later legacy privacy correction is
  excluded from this frozen release; V08 remains Planned and inactive.

- **4.46.3 source checkpoint — 23 October 2026; unreleased at this checkpoint.** The
  [combined change](releases/4.46.3.md) adds explicit backup creation and
  verification through Host controls and native-agent actions, and corrects
  controller shutdown observation. Updated transition code also allows 180
  seconds for full startup readiness, retaining the 90-second stop bound and
  every readiness/identity check. An older running updater keeps its own
  60-second deadline until new code owns the transition. Backup/shutdown source
  checks passed, alongside 22 focused startup checks and 46 full updater/desktop
  regression checks. At this source checkpoint, all six native
  4.46.3 targets, public release and actual backup/custodian acceptance remained
  pending; no parent requirement was completed by these source results.

- **4.46.2 publication and actual host rollback — 23 October 2026, 12:41:16 UTC.**
  Native, artifact-verification and public installed-update gates passed;
  4.46.2 remains published. The actual host exhausted its 60-second startup
  readiness window despite API/worker `RUNNING` states and restored 4.46.1.
  HTTP, instance and child readiness were not confirmed. Windows remains
  4.46.2, and paired acceptance stopped for inspection. The
  [retained failure](validation/2026-10-23-independent-host-adoption.md#4462-actual-host-rollback--23-october-2026)
  preserves the original diagnostics. The last accepted pair remains 4.46.1;
  the new 4.46.3 source grace has no installed or actual-host acceptance yet.

- **4.46.2 source hotfix — 23 October 2026; unreleased at this checkpoint.**
  [Native host operations](releases/4.46.2.md) now use the existing five-minute
  source-drain window and preserve active scans. A fixed `host_busy` outcome
  explains a still-blocked operation. Real-lock source regressions passed:
  completion after 75 simulated seconds allowed exactly one authorized stop;
  a held lease returned `host_busy` at 300 simulated seconds with no effect,
  intent change or scan interruption. The 99 focused Python checks and six
  desktop host-profile checks passed, with two environment-dependent Python
  cases skipped. Native/public qualification and actual operational acceptance
  remain unproven. This is source evidence; V08 remains Planned and inactive.

- **4.46.1 independent-host setup — 23 October 2026, 11:01:48 UTC.** Native
  adoption and backup configuration passed, followed by OS integration at
  **10:58:01 UTC** and two protected custodian enrollments at **10:58:40 UTC**.
  The [operational journey failed](validation/2026-10-23-independent-host-adoption.md)
  at its first Windows stop at **11:00:26 UTC**, before any effect, behind a
  source scan. Manager restart, watchdog checks, start and retained-data
  acceptance were not reached. A fresh status read found memory ready/running
  with no pending work or recovery; no second stop or restart was requested.
  The earlier paired update remains accepted. Fresh native host-control backup
  delivery/restore, whole-machine boot, separate physical-device custody and
  provider wake remain unproven. All 66 requirement states are unchanged.

- **4.46.1 actual paired acceptance — 23 October 2026, 09:55:28 UTC.** The
  actual Windows x64 app and shared Linux service passed their
  [paired check](validation/2026-10-23-4461-live-acceptance.md). The host completed
  its compatible normal update; Windows retained the earlier guarded update.
  Three identities, exact sampled memories, login/preferences, MCP and deletion
  checks passed. The [interruption history](validation/2026-10-23-4461-live-interruption.md)
  preserves both stopped attempts and the independently reviewed restoration of
  four source-role entries. The existing 54-request lab passed with no cleanup
  remaining, production memory writes or cloud model calls. At that checkpoint,
  fresh independent backup, OS/controller adoption and both custodians'
  operations remained pending; the later setup and failed first stop are recorded above.
  All 66 requirement states remain unchanged; V08 remains Planned and inactive.

- **4.46.1 publication — 23 October 2026, 08:46:59 UTC.** All six
  [native targets](validation/2026-10-23-4461-native-acceptance.md), independent
  artifact verification, all six public installed updates and automatic website
  synchronization passed. The generated
  [release status receipt](validation/releases/4.46.1-status.json) records all
  five gates. The actual Windows app reached 4.46.1; the shared host was still
  creating its pre-update backup. Paired acceptance, fresh off-host backup,
  production controller adoption and two-custodian operations remain unproven
  at this checkpoint. All 66 requirement states remain unchanged.

- **4.46.1 managed-startup hotfix — 23 October 2026.** The
  [source change](releases/4.46.1.md) defers unrelated command initialization
  and preserves bounded readiness diagnostics through runtime rollback. The
  [isolated one-CPU-host measurement](validation/2026-10-23-managed-startup.md)
  reduced worker setup CPU time before database access by about 81%; 59 focused
  CLI/update checks passed. The first frozen attempt subsequently failed Windows
  x64 journal setup. The [journal-form timing correction](validation/2026-10-23-windows-journal-form.md)
  reproduces the form closing after its first click and verifies the corrected
  behavior in an actual Chromium browser with synthetic data. Same-host draft
  preservation, changed-host draft clearing and frontend/Electron builds passed.
  A new frozen native attempt is pending at that checkpoint. Full native/public and renewed actual-update
  acceptance remain separate. The startup deadline,
  identity, backup and integrity checks are unchanged.

- **4.46.0 publication and actual host rollback — 23 October 2026.** All six
  native targets, all 38 artifact checks and all six public installed-update
  targets passed. The actual Windows app updated to 4.46.0, but the canonical
  host missed the managed-readiness deadline and restored 4.45.1 without
  database rollback. The [retained rollout record](validation/2026-10-23-4460-live-rollout.md)
  distinguishes these results. Dependent backup/adoption jobs stopped before
  making changes. At that checkpoint the last complete pair was 4.45.1;
  production host-controller adoption and two-custodian acceptance remained
  open. All 65 requirement states and open #44/#45 remain unchanged.

- **4.45.1 public updates and actual acceptance — 23 October 2026.** Publication
  at **00:14:17 UTC** followed six passing native targets and verification of all
  38 unchanged assets from source `70ec58d8`. All six
  [public installed-update targets](https://github.com/Perseusxrltd/mnemion/actions/runs/39876903393)
  passed at **00:26:21 UTC**, and public website HTML verification passed.
  The actual Windows x64 app and Hostinger Linux service completed their
  [paired acceptance](validation/2026-10-23-4451-live-acceptance.md) at
  **00:33:04/05 UTC**: compatible automatic host update, guarded Windows agent
  restart, the same three identities and exact memory evidence, retained login,
  bookmarks and preferences, and 51 isolated lab requests with no cleanup
  remaining, production writes or cloud model calls. This does not establish
  unattended idle restart or a fresh post-update backup. The 4.46.0 source/native
  gates and production independent-host adoption remain separate. All 65
  requirement states and open #44/#45 remain unchanged.

- **Independent company-host control source — 22 October 2026.** The
  [development guide](guides/company-host-control.md) covers `/hosts` before
  sign-in and equivalent native-agent actions, protected per-device Ed25519
  logins, pinned restricted SSH with observer/operator/custodian roles, and
  durable approved operations. Managed Unix hosts gain reviewed signed upgrades
  with independent encrypted Git backup readback and local OS-owner custodian
  recovery that preserves the host pin.

  [Source validation](guides/company-host-control.md#qualification-and-remaining-work)
  passed 20 profile/agent/process cases including archives and refused replay,
  two repeated real Node/Python/SSH journey cases, three owner-recovery cases
  and three backup-retention cases. Electron/frontend builds and lint/format
  passed. A visual fixture checked plan-digest approval and 960px layout; this
  is not live acceptance. New native gates for actual OS-protected keys,
  transport refusal, recovery archives and offline `/hosts` are written but
  have not run. Production adoption, boot registration, replacement-host
  recovery, provider wake and safe takeover remain open in the
  [continuity contract](implementation/workspace-continuity.md).

  A **23 October source follow-up** adds [durable stop policy](guides/company-host-control.md#preserve-approved-stops-in-os-supervision)
  and requires OS-owner replacement of unconditional memory jobs/watchdog
  restarts with the foreground manager and guarded repair path. Adoption does
  not start a stopped service. Store format 2 retains approved intent beyond
  receipt pruning or revocation; experimental format 1 is refused without reset.
  [New policy checks](validation/2026-10-22-independent-host-control.md#durable-service-policy--23-october-2026)
  and the frontend build passed; the original two fixture setup errors and their
  targeted passing rerun remain recorded. Actual OS integration and all six
  installed gates remain pending. No 4.46 release was dispatched by the stopped
  pre-freeze waiter.

  At the initial 22 October checkpoint, **4.45.0** remained public while **4.45.1-r2**
  was still running; this independent-host batch is unreleased. Current availability
  follows release status above. All 65 requirement states and open #44/#45 remain
  unchanged.

- **4.45.1 hardening source — 22 October 2026.** The combined
  [hotfix](releases/4.45.1.md) improves provider deadlines and byte handling,
  recovery subprocess isolation, private validation diagnostics and spreadsheet
  policy consistency. It adds required source/distribution secret scans and an
  optional company browser connection policy. [Focused acceptance](validation/2026-10-22-provider-recovery-hardening.md)
  passed within its stated scope. The initial [Mac ARM native job](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596/job/120095732920)
  failed in `backup-resume` after the local engine reached ready; the Electron
  parent remained alive and the exact cause is unknown. The original failure
  and refused same-job retry remain in the [validation record](validation/2026-10-22-provider-recovery-hardening.md#native-qualification-and-exit-diagnostics).
  A source revision adds bounded engine exit diagnostics; its TypeScript build
  and 84 focused component tests passed. The original release run ended in
  failure at **22:21:53 UTC on 22 October 2026**. [Mac Intel](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596/job/120095732809)
  progressed to `capture-headless` before its **60-minute job timeout**; no
  installed-hosting receipt was uploaded. [Main Product CI](https://github.com/Perseusxrltd/mnemion/actions/runs/39859826761)
  passed, and immutable `release/4.45.1-r2` source `70ec58d8` started
  [release run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559)
  after queueing. It remained in progress at this checkpoint; corrected native
  qualification, public and actual-update gates remain separate.
  A separate source correction raises the Intel Mac job budget to 90 minutes
  for future runs, preserving individual probe limits and required observations;
  the active immutable r2 retains 60 minutes for Intel Mac. The original Mac ARM
  engine-stop cause remains unknown.
  All 65 requirement states and open #44/#45 remain unchanged.

- **4.45.0 public updates and actual acceptance — 22 October 2026.** All six
  [public installed-update targets](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077)
  and automatic website synchronization passed. The actual Windows app and
  shared Linux host completed their [paired acceptance](validation/2026-10-22-4450-live-acceptance.md)
  at **20:24:17 UTC**: the guarded schema upgrade, independently verified
  pre/post backups, retained identities and saved access, and 42 isolated lab
  requests with complete cleanup passed. This used the app's guarded agent
  restart; unattended idle restart remains unproven. Broader provider, fleet,
  recovery and paused-publisher acceptance remain in the full audit.

- **4.45.0 publication — 22 October 2026, 19:47 UTC.** The first retained local
  Codex conversation journey is available in the [published release](releases/4.45.0.md).
  Its [publication receipt](validation/releases/4.45.0-publication.json) binds
  38 verified assets to source `d8083b06`. Public installed-update checks and the
  actual Windows/shared-host migration have separate acceptance; current release
  outcomes are supplied by the generated status above.

- **4.45.0 frozen native qualification — 22 October 2026, 19:27 UTC.** All six
  versioned installers passed their [installed hosting and capture contract](validation/2026-10-22-l1-release-native-acceptance.md)
  on source `d8083b06`. The retained receipt records 59 required observations
  per target and separate Windows/macOS update steps. Public artifact, feed,
  website and actual-deployment acceptance remain separate evidence.

- **4.45.0 candidate qualification — 22 October 2026.** The first approved local
  Codex
  JSONL journey has completed its [implementation acceptance](validation/2026-10-22-l1-candidate-acceptance.md).
  All six installed targets passed on source `d3587263`, alongside exact-source
  Product checks and an independent actual-Codex shared-host journey. The
  original failed native and harness attempts remain preserved. Final versioned
  release, public-update and actual-deployment gates remain separate.

  Studio and native agents share capture preview, Selected/Conversation/Detailed
  presets, file/field selection, audience review, encrypted offline intake and
  restart-safe queues. Coverage distinguishes unknown history, accepted records,
  pending delivery and indexing. Bounded backfill, fair intake and configurable
  RAM, history, pending-byte and database limits need no model for local capture.
  [App instructions](service/durable-capture.md) and the
  [independent headless workflow](service/headless-capture.md) describe enrollment,
  paused operation, encrypted archives, new-device recovery, reviewed policy
  replacement and permanent forgetting decisions.

  Approved server expiry has visible cleanup progress and deadlines that retries
  or replacement keys cannot extend. Offline pending content, producer files and
  archives have separate retention. Interrupted recovery records its intent
  before retiring a grant and reconciles lost replies before retrying. Five
  capture migrations use the existing reviewed host-upgrade and backup path.

  The [complete implementation history](research/2026-10-21-durable-capture-implementation.md)
  and [acceptance checklist](research/2026-10-21-durable-capture-implementation.md#required-before-l1-can-be-released)
  retain all evidence and limits. Broader provider/plugin capture, inaccessible
  history, attachment retrieval, text-secret redaction, wider migrations, fleet
  measurements and L2–L7 remain explicit work. No full requirement is promoted
  by this candidate, and the separately paused PC publisher remains paused.

- **4.44.2 publication and paired acceptance — 22 October 2026.** The Codex-format
  and Windows startup hotfix
  passed its six-platform native gates, artifact verification and all six public
  update checks. Website synchronization passed automatically. Download links,
  release notes and current availability continue to follow Git; this public
  hotfix does not include the durable-capture milestone. Its actual Windows/shared
  host [paired acceptance](validation/2026-10-22-4442-live-acceptance.md) passed
  with 41 isolated lab requests and complete cleanup. Separate Grok Bot cloud
  and broader deployment acceptance remain tracked by
  [the maintenance board](MAINTENANCE_STATUS.md).

- **4.44 publication and paired acceptance — 21 October 2026.** Certifi 2026.10.19 and
  Pillow 13.0.0 address the reported dependency advisories while preserving the
  pinned text models. [Dependency and offline E5/BGE validation](validation/2026-10-21-security-dependencies.md)
  passed within its recorded scope. All six native targets, artifact verification
  and public update checks passed; the website synchronized automatically.
  [Paired acceptance](validation/2026-10-21-444-acceptance.md) confirmed ordinary
  4.43→4.44 updates, retained identities/login/bookmarks/preferences and 50 isolated
  lab requests with complete cleanup. Unattended idle restart remains unproven.
  This is a standalone security hotfix; capture/L1 delivery and all requirement
  statuses remain unchanged.

- **4.43 publication and paired acceptance — 21 October 2026.**
  The [paired acceptance](validation/2026-10-21-443-acceptance.md) retained
  identities, protected login and preferences, then passed 47 of 47 synthetic
  requests with complete cleanup. The host used compatible automatic updating;
  Windows used a guarded agent restart. All six native and public upgrade
  targets passed. Fresh post-upgrade snapshot and ledger delivery passed
  independent manifest verification at 00:41 UTC after a bounded private-mirror
  quota correction; this was not a new restore drill. The
  earlier 4.41 semantic HTTP 503 remains unexplained under issue 45.

- **4.43 shares local inference between indexing and waiting queries.**
  [Cooperative batches](service/memory-resources.md#search-during-long-local-indexing)
  retain one native execution, adapt within RAM limits and recheck evicted models.
  [Seventy focused checks and one offline pinned-BGE comparison](validation/2026-10-20-inference-fairness.md)
  passed: the concurrent query changed from a two-second admission failure to
  success in 0.269 seconds while all 512 chunks finished. The 250 ms batch target
  and cumulative 30-second wait remain bounded controls, not latency guarantees.
  A [bounded live cycle](validation/2026-10-21-443-acceptance.md) also passed two
  semantic queries during the same indexing operation, followed by document
  readiness and full synthetic cleanup. Native batches were not instrumented;
  broader hardware/workload acceptance remains open and R04 is partial.

- **4.43 includes the folder and conversation reconnection repairs.** Studio retains
  the original filesystem namespace instead of creating a second source and
  suspending the original source. App/agent settings retain the verified identity;
  ambiguous or mismatching catalogs stop before import. [Focused validation](validation/2026-10-20-source-identity-recovery.md)
  passed. The combined [conversation repair](validation/2026-10-20-conversation-identity.md)
  also verifies copied prefixes before retaining their original record identities.
  These component checks remain separate from full source/conversation
  reconnection acceptance. The withheld 4.42 setup failure and its unresolved
  cause remain in the [native-gate record](validation/2026-10-20-inference-fairness.md#withheld-442-native-gate-and-diagnostic-addendum).

- **Actual office access now passes.** [Issue 46 acceptance](validation/2026-10-20-office-access.md)
  verifies genuine source scans and list/fetch/lexical reads with both unchanged
  agent credentials. Issue 46 is closed. The deliberately paused local-note
  publisher still requires its independent guard and quality-control approval.

- **4.41 completes the selected live-capture choice.** The app and agents can
  choose complete exposed records or supported messages only, with provenance,
  bounded checkpoints and ordinary permission/deletion protections. This is a
  foundation for the broader librarian, not a completed parent requirement.
  [Capture guide](service/live-conversations.md#choose-how-much-to-capture) and
  [validation](validation/2026-10-20-capture-policy.md) retain its exact scope.

- **Work now follows the complete-milestone acceptance audit.** All 65 IDs and
  their full scope remain retained. The [42-partial audit](implementation/completion-audit.md)
  records missing acceptance work, dependencies and evidence without invented
  estimates. Finish one feature journey alongside urgent bugs; keep current
  releases running. Shared administration, capture freshness, ordinary memory,
  recovery and updates precede further independent advanced-feature work.

- **4.40 adds measured librarian coverage and app update diagnostics.**
  [Organization/review coverage](service/librarian.md#coverage-and-processing)
  distinguishes successful responses, skips, attempts and pending revisions;
  30-day usage and a JSON export are available in the app and to agents.
  [Update controls](service/desktop-operator.md#app-updates-and-startup) expose
  actual idle seconds without changing restart safeguards. The
  [source and Electron checks](validation/2026-10-20-librarian-coverage.md)
  passed. Layered consolidation and quality improvements still require their
  own implementation and evidence; the complete shipped count is unchanged.

- **4.39 source combines connectors with the busy-host and container repairs.**
  A [bounded operator turn](service/managed-upgrades.md) prevents continuous
  new scans from starving an explicit upgrade. The container frontend now
  receives the canonical logo; missing input withheld both 4.38 container gates.
  4.39 supersedes that unpublished candidate and carries its native profiles
  and packages. [Source validation](validation/2026-10-20-operator-turn-research.md)
  stays separate from the full release and private deployment checks.
  A [free weekly research watch](research/RESEARCH_WATCH.md) preserves dated
  paper/tool candidates and failed feeds without adopting dependencies.

- **Expanded librarian requirement R07 is planned and preserved.**
  The [scientific study and delivery contract](research/2026-10-20-layered-librarian.md)
  covers configurable raw capture, layered consolidation, deep review, statistics,
  resurfacing, policy-controlled retention, visual monitoring and native agent controls.
  TypeSafe AI Jev is assessed as an optional decision router; the free local path
  remains required. Seven implementation slices and a recurring research watch
  have explicit acceptance criteria. This added scope changes the denominator,
  not the number of shipped requirements.

- **The combined source adds native Hermes/OpenClaw setup and Perseus XR packages.**
  [Native profiles](service/desktop-agents.md) preserve settings and distinct
  workspace identities. [Connection packages](service/agent-packages.md) are
  downloadable in the app and generated through the API, SDKs and native CLI.
  Provider-specific plugin, configuration and guide types stay explicit.
  [Focused checks and actual Grok/Claude manifest validation](validation/2026-10-20-native-connectors.md)
  passed. GitHub **44/45** retain real cloud-history and reliability work;
  issue **46** closed with the actual office-access proof above. The upstream
  local-note publisher's security pause is preserved.
  Native release and live update gates remain separate.

- **Published 4.37.0 combines queue improvements with a local setup correction.**
  A [reproduced state-publication race](validation/2026-10-20-state-publication.md)
  briefly made a new settings file appear linked to its own staging name.
  Status readers now wait briefly for publication while retaining link checks.
  All six native release gates, independent artifacts, the live website and
  all six public-update rehearsals passed. Actual shared-host migration and
  Windows lab acceptance remain separate. Unpublished 4.35/4.36 are superseded.

- **The combined release makes queue workload visible.**
  [The pipeline view](service/insights.md) separates indexing and physical
  cleanup, with waiting text sizes, retries, due jobs and oldest age. The same
  scoped metrics reach agents and exports, with fallback for older servers.
  [Real database and browser checks](validation/2026-10-20-queue-visibility.md)
  passed; this is visibility into measured work, not a completion-time estimate.

- **The combined release fixes indexing dispatch under a source backlog.**
  [Purges take priority and organizations/spaces receive persistent turns](service/indexing-queues.md).
  Eighteen database/reindex cases passed with existing model and authorization
  policies retained. Migration 029 requires the normal backup/upgrade path.
  [Actual 4.33 updates preserved access, but the lab stopped with queued work](validation/2026-10-20-433-live-updates.md);
  that failure remains visible pending cleanup and new acceptance.

- **4.34.0 is published with Slack and Google Drive setup through the app.**
  [Cloud sources](service/desktop-cloud-sources.md) accept existing approved
  credentials and selected resources, with separate OS-protected keys and
  read-only Drive token renewal. Actual provider permissions govern capture.
  Offline controls and equivalent local-agent setup share the bounded source
  runner. [All six native targets and artifact verification passed](validation/2026-10-20-desktop-cloud-sources.md).
  Interactive OAuth enrollment and live customer-provider acceptance
  remain open; complete source onboarding is still partial.

- **4.33.0 is published with model-provider setup through the app.**
  [Local hosting controls](service/desktop-models.md) enroll embedding and librarian
  endpoints, private keys, CA trust and capacity settings. Saved profiles remain
  separate from per-space processing approval; equivalent local-agent controls
  and damaged-file recovery are included. [All six native targets and uploaded
  artifact verification passed](validation/2026-10-20-desktop-models.md).
  The shared inference queue now respects the strictest approved endpoint limit.

- **4.32.0 is published with guided local agent installation.**
  [Agent setup](service/desktop-agents.md) supports reviewed named connections,
  dedicated application keys, preserved client settings and offline removal.
  The private runtime keeps agents independent of a running Studio window and
  follows its updates. Grok Build has an observed native profile; separate
  vendor plugins and hosted provider acceptance remain open.
  The corrected candidate also [handles temporary Windows status-file locks](validation/2026-10-20-windows-state-locks.md),
  after the first attempt's installed backup check found an atomic-write failure.
  [All six native gates and actual Windows/shared-host updates passed](validation/2026-10-20-432-live-updates.md),
  preserving access and completing the isolated lab without production writes.

- **4.31.0 is published with folder and conversation setup through the app.**
  [Desktop sources](service/desktop-sources.md) have folder selection, scoped
  protected keys, bounded background scans, RAM/file limits and matching agent
  controls. Saved-source controls work while signed out. Contributing to a
  shared workspace needs no local database or model. [All six native gates and
  actual Windows/shared-host automatic updates passed](validation/2026-10-20-431-live-updates.md),
  preserving access and completing the isolated lab. Other provider enrollment
  and fleet acceptance remain open; strict full-scope coverage is unchanged.

- **4.30.2 is published and updated the actual Windows app and shared host.**
  [All six native gates and live update acceptance](validation/2026-10-20-4302-live-updates.md)
  passed, preserving identities, memories, protected login and preferences.
  The isolated Windows lab passed 42 requests with no pending cleanup.

- **4.30.2 fixes Windows backup paths and protects agent setup files.**
  [Database tools accept long private backup paths](validation/2026-10-20-windows-backup-paths.md)
  without changing Windows settings; the app and agent status retain safe failure
  diagnostics. Configuration backups
  and staged replacements now receive explicit private ownership and permissions
  before writing. [Focused Linux and native Windows checks](validation/2026-10-20-agent-setup-private-files.md)
  preserve existing client policies, exact backups and unrelated files.

- **4.30.2 includes server-backup recovery in the desktop app.** The
  [app and local-agent workflow](service/desktop-host-recovery.md) authenticates
  the full package, reviews included or newer access state and creates a separate
  native database with preserved identities and fresh access. Full host/provider
  configuration remains a separate workflow. The unpublished 4.30.0/4.30.1
  candidates were withheld when release checks found fixture and Windows path
  failures. Strict scope coverage is unchanged.

- **4.29 is published with resumable large-journal recovery.** The [app, SDKs and
  private agent controls](service/journal-recovery.md) accept complete journals
  up to 2 GiB, one million records and 100,000 identities. Uploads survive
  interruption, complete review precedes approval, and bounded restoration
  preserves denials and local edits. All six public installed-update checks passed.

- **4.28 is published for all six targets.** [Private desktop controls](service/desktop-operator.md#select-a-team-workspace-from-a-local-agent)
  let a trusted local agent verify/select a remote account, sign in as a person,
  inspect/reopen protected bookmarks, disconnect and return to the local host.
  Actual installed tests passed on Windows, macOS and Linux, each on x64 and
  ARM64. Automatic release status tracks subsequent public upgrades.
- **Issues 38 and 39 closed against verified 4.27.** An [independent-computer restore](validation/2026-10-19-portable-host-recovery.md)
  exposed and fixed a PostgreSQL locale mismatch. Existing identities, exact
  memories, deletion and native Windows access survived the tested restore.
  [Legacy-buffer import](service/legacy-buffer.md), native Git backfill and
  [editable journal recovery](service/journal-recovery.md) complete the bounded
  reported paths. Source 4.29 extends journal capacity; broader host provisioning remains.
- **The real shared host now uses managed updates.** [Controlled adoption and migration](validation/2026-10-20-shared-workspace-adoption.md)
  retained agent keys, roles, notes, public OAuth and both Git sources. The actual
  Windows app and shared server then updated automatically to 4.28. A subsequent
  [guarded server upgrade and normal Windows update](validation/2026-10-20-shared-workspace-429.md)
  brought both to 4.29, with unchanged access and a passing automatic lab cycle.
  The app now
  uses the independent human administrator's protected login. Browser sign-in/
  sign-out and independently confirmed encrypted off-host backup also passed.
  Its [isolated Windows lab](validation/2026-10-20-windows-shared-lab.md) passed a
  42-request memory cycle and 27-request concurrency check, with automatic
  bounded checks after app/server version changes.
- **Issue 18 now has actual signed-in ChatGPT acceptance.**
  [OAuth, permission review, installation, all 16 tools and a profile-only request](validation/2026-10-20-chatgpt-acceptance.md)
  passed. The [issue plan](implementation/github-issues.md) links release closure
  evidence. Native named-client packages must use Perseus XR authorship; broader
  provider/capture work remains. General OAuth issue 4 is closed. Remote-access issue 3 closed
  against [reviewed acceptance and verified 4.29](validation/2026-10-20-remote-access-issue.md).
  Live managed-ngrok account/lifecycle testing remains
  separate roadmap work.

History lives in [release notes](https://github.com/Perseusxrltd/mnemion/releases) and [implementation progress](implementation/v4_progress.md).
Historical validation retains its original version/environment and is not a
current operating instruction.

## Product direction

Mnemion is **100% free forever**, including organizations and updates. There are
no paid seats or feature tiers. Optional one-time PayPal support starts at €5
and permits higher amounts without changing access. See [support](SUPPORT.md).

One organized memory infrastructure serves people, teams, programs and agents
across devices and providers. Organizations choose their hosting, sources,
permitted spaces and outbound model access. Obsidian remains compatible with
portable Markdown, citations, links and personal annotations.

The shared server owns consistency and indexing. A connected desktop needs no
local model or GPU. Local hosting uses cooperative RAM budgets, small CPU models
and pressure controls; minimum-hardware claims require actual measurements.

Human administration and recovery must survive an unavailable or out-of-tokens
agent. Membership, host-operator authority and provider-account access are
separate. A saved connection or source mirror does not become a running replica
when its host stops. Follow the [continuity contract](implementation/workspace-continuity.md).

Every necessary workflow must also work through authorized API, CLI, MCP or
private local controls, with explicit targets, bounded outputs, durable receipts
and safe retries. Administrative credentials do not belong in ordinary memories.

## Available capabilities

| Area | Available behavior | Guide |
| --- | --- | --- |
| Shared memory | Transactions, tenant/space grants, scoped identities, revisions, deletion and receipts | [Service](service/README.md), [organizations](service/organizations.md) |
| Retrieval | Lexical/semantic search, cited excerpts, passage chronology, recent/relevance ordering and bounded context | [Retrieval](service/retrieval.md) |
| Embeddings | Pinned CPU and approved remote profiles, candidate indexes, evaluation, activation/rollback | [Models](service/embeddings.md) |
| Librarian | Approved local/cloud profiles, schedules, budgets, evidence-linked proposals, review/undo | [Librarian](service/librarian.md) |
| Sources and capture | Git, folders, Drive, Slack, rclone/custom adapters, selected chat formats, live JSONL and source health | [Connectors](service/connectors.md), [capture](service/capture.md), [live capture](service/live-conversations.md) |
| Native Git journal | Opt-in capture/backfill, SSH host pins, receipts, rollover, Markdown filing, archives and reviewed recovery | [Git journal](service/git-journal.md), [recovery](service/journal-recovery.md) |
| Agent controls | HTTP/OpenAPI, Python/TypeScript SDKs, MCP/CLI and private desktop operator access | [Agents](service/agents.md), [administration](service/agent-control.md), [desktop](service/desktop-operator.md) |
| Human access | Independent admins, passwords/invitations, revocable sessions, OAuth and company OIDC | [Sign-in](service/sign-in.md), [company sign-in](service/company-sign-in.md) |
| Secrets | Separate encrypted values, host-key setup/recovery and reviewed KeePass transfer | [Vault](service/secrets-vault.md), [KeePass](service/keepass.md) |
| Knowledge and monitoring | Wiki, live 3D map, evidence, six insight views, evaluation datasets/runs/comparisons and exports | [Map](service/memory-map.md), [insights](service/insights.md) |
| Obsidian | Managed Markdown, stable paths, wikilinks, citations, conflict checks and preserved annotations | [Studio](../studio/README.md) |
| Local desktop | Bundled engine/database, guided setup, RAM controls, startup, background operation and verified updates | [Local workspace](service/local-workspaces.md), [updates](service/updates.md) |
| Recovery | Encrypted snapshots, later denial ledgers, independent host packages, source-runner restoration and native controls | [Host recovery](service/host-recovery.md), [native backups](service/native-backups.md) |
| Shared service | Unix Supervisor, registered sources, signed compatible patches and guarded migration upgrades | [Supervision](service/supervision.md), [managed updates](service/managed-updates.md) |
| Workspace connections | Protected bookmarks, checked identities, dated offline details and local-agent selection | [Workspaces](service/workspaces.md) |
| Design and docs | Perseus XR theme/logo, responsive navigation, offline help and automatic website release metadata | [Design](STUDIO_DESIGN.md), [branding](BRANDING.md), [maintenance](MAINTENANCE.md) |

Each validation report states the actual provider/environment exercised. Generic
infrastructure alone does not establish live authentication, capture or recovery.
Keep incomplete capture and source health visible.

## Delivery order

Ship coherent access, installation, update, data-safety and RAM fixes before
optional expansion. New [issues](https://github.com/Perseusxrltd/mnemion/issues)
join this queue without erasing unfinished requirements. Independent work
continues while an external account or publisher prerequisite is unavailable.

V08 [anonymous product telemetry](implementation/anonymous-product-telemetry.md)
is the active feature milestone after the accepted 4.46.5 paired update, custody,
fresh backup and independent restore. Source controls, transport components and
application-owner wiring remain Building;
complete workflow measurement, reviewed anonymity, bounded transport and native/
web release acceptance remain open. Urgent hotfixes continue alongside it,
including the separate 4.46.6 dependency-security release. The unfinished
delivery outcomes below retain their relative order and full acceptance scope.

| Priority | Next outcome | Acceptance and requirements |
| --- | --- | --- |
| 1 | Current real-deployment reports and remaining live connections | ChatGPT acceptance closed #18. New #44/#45 require actual Grok Bot cloud acceptance and completion of the guarded shared-host/Windows update, including backup, semantic access, cleanup and explicitly paused upstream publishing. Source 4.38 supplies Perseus XR packages and Hermes/OpenClaw native profiles. Continue real provider/directory and free ngrok lifecycle acceptance. Preserve existing HTTPS, local and scoped-key paths. C04–C07, A05/A08. |
| 2 | Continuous operation and recovery from another device | Guided organization hosting, registered recovery hosts, delegated operators, key custody, off-host delivery visibility and complete app-based replacement-host setup. Source 4.30.2 supplies desktop database import; provider/OS configuration remains. Expand beyond the bounded 4.29 journal recovery where needed. Verify host loss and current denials without the original agent; distinguish mirrors, snapshots and replicas. A01/A06/A07/A09/A11–A13, U01/U02/U04/U06/U11. |
| 3 | Source and agent onboarding | Guided consent, credentials, permission mapping, exclusions, reconnect and capture coverage. Validate actual Grokbot, Dot/OpenAI, Anthropic, Hermes and OpenClaw paths before claiming native plugins. Expand adapters with provider contracts and real acceptance. C01–C09, F08. |
| 4 | Govern several workspaces | Explicit personal/employer/client contexts, independent memberships, queued-work destinations and policies. Reviewed cross-workspace search/transfer without company access to personal data. Bookmarks alone are incomplete. F02/F08, A03/A04/A12, C09. |
| 5 | Capacity and model choices | Modest hardware, native OS versions, RAM peaks, bandwidth, ingestion queues, concurrency, model quality and recovery-time measurements. Fleet resource views and useful budgets, preserving CPU-only/remote clients. F05–F07, R01–R04, V01/V02. |
| 6 | Knowledge quality and visibility | Held-out retrieval/librarian evaluations, provenance-aware relationships, contradiction/staleness review, larger-map clustering, incremental activity and replay. Visible capture gaps and uncertainty. R06, V01–V05. |
| 7 | Organization policy and legacy coverage | Lifecycle provisioning, company-device/update policy, audit retention/export, key custody/rotation, shared-source ownership, uncommon Obsidian layouts and interrupted large migrations. F03/F04/F07, A03/A04/A08–A10, U04/U06. |

The [multiple-workspace design](implementation/multiple-workspaces.md),
[app-onboarding acceptance](implementation/app-onboarding.md) and
[complete requirements](PRODUCT_REQUIREMENTS.md) expand these batches. A screen
or passing source test alone does not complete a requested workflow.

## Complete setup from the app

A clean supported computer must create a local workspace, join a team, configure
organization hosting or restore a backup through a resumable UI. Sources,
access, agents, models, RAM, Obsidian and recovery belong in the same flow,
with real readiness checks and equivalent native agent operations. The [agent setup contract](service/agent-setup.md) requires structured discovery, configuration, repair and lifecycle controls for every setup workflow. [Perseus XR](BRANDING.md#connector-and-plugin-authorship) is the author/developer for all new connector and plugin packages.

Local setup, protected remote connections, personal sign-in, local provider
configuration and native backup/recovery controls are available. Complete remote
host provisioning, provider approvals, source enrollment, independent custody/
delivery and replacement-hardware recovery remain. A guide or mock success does
not count as an implemented step.

## Selectable embeddings and controlled reindexing

Retain pinned E5/BGE CPU profiles and approved Ollama/OpenAI-compatible endpoints,
per-space outbound consent, bounded inference, candidate generations, pause/retry,
evaluation, atomic activation and rollback.

Next: measured language/domain/hardware recommendations, broader held-out model
comparisons, provider rate-limit/cost instrumentation and old-generation retention.
Model choice balances quality, latency, RAM, privacy and cost; there is no
universal best model. Basic use requires no paid model call.

## Configurable librarian

Approved local/cloud profiles, optional schedules, daily call budgets and
reviewable evidence-linked proposals already exist. Models may suggest titles,
tags, summaries, links, duplicates or stale claims; they cannot grant access,
delete evidence or turn a claim into verified truth.

Next: held-out team-data usefulness, acceptance/rejection analysis, broader
grouping and domain policies, calibrated findings and reliable undo. Synthetic
responses test protocol/permissions, not reasoning quality. Model-free Git filing
remains a separate explicit option.

## Organization operations and secured vaults

Tenant/space authorization and separate encrypted credentials are available,
including KeePass transfer. Ordinary searchable memory and Obsidian exports keep
their documented storage/plaintext boundaries; secret-value encryption is not
end-to-end encryption of the memory index.

Next: named-provider enrollment, lifecycle provisioning, device policy, quotas,
shared-source ownership, audit export/retention and managed key rotation/custody.
Verify current permissions, revocation across projections and recovery before
broadening automatic administration.

## Source ecosystem and interoperability

Keep the open adapter contract for Git, mounted folders, rclone clouds and
company-defined systems. Drive and Slack have direct adapters. Teams, Confluence,
Notion and other platforms need their own adapters and permission/retention
tests before being called supported.

Next: guided consent, incremental visibility, conflict handling, provider quotas,
restartable ingestion, bounded bandwidth, cross-source identity, deletion and
representative live-provider checks. Preserve ownership, exclusions and citations.
Sharing a folder does not grant access to every memory space.

## Legacy preservation and compatibility

The [v3 audit](implementation/v3-feature-parity.md) and [feature decisions](implementation/feature-review.md)
retain the preservation ledger. Useful capture, curation, wiki, trust, context
and Obsidian workflows need tested equivalents, migration paths or explicit
retirement reasons. Unsafe Git database union and destructive implicit
replacement remain retired.

Continue uncommon layouts, large/interrupted migrations, post-cutover rollback
and personal annotations. Available source text is not a complete workspace
backup; unavailable original data must never be inferred or fabricated.

## Release completion gates

1. Validate the frozen commit through maintained service, legacy, SDK, frontend,
   permission, dependency and repository-hygiene checks.
2. Require native installation, local operation and authenticated update/relaunch
   for every offered OS/architecture. Preserve verified targets and publish a
   ready set while other targets are tested when necessary.
3. Verify immutable artifacts, signatures, complete feeds, inventories, checksums,
   licenses and versioned release notes before publication.
4. Run public installed-update checks through actual release feeds. Keep source,
   candidate-native and a customer's actual update evidence distinct.
5. Automate product-page/download/status updates and reviewed issue closures.
   Update affected guides, requirements and bundled help with substantive changes.

No new paid program, subscription, certificate or converting trial is permitted.
Mac uses independently signed Sparkle updates, with the documented first-install
OS approval. SignPath publisher approval remains external. See [code signing](CODE_SIGNING.md),
[Windows updates](implementation/free-windows-updates.md) and [Mac updates](implementation/free-macos-updates.md).
Do not claim approval or support for an untested company-device policy.

## Keeping the plan current

Use requirements for scope, this page for delivery order, release notes for
changes and validation reports for evidence. Generated status owns current
build/download/issue state. Every material batch updates affected guides and
remaining acceptance; historical reports are preserved. Follow [release maintenance](MAINTENANCE.md).
