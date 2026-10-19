# Mnemion product roadmap

Reviewed source distribution: **4.18.0**. Roadmap updated: **2026-10-19**.
The [current published distribution and release gates](RELEASE_STATUS.md) are updated automatically.
The [official product page](https://www.perseusxr.com/mnemion) lists verified
published downloads; source and release preparation can precede publication.

The [4.18.0 source](releases/4.18.0.md) adds local desktop
[Git journal host registration](service/git-journal.md#a-workspace-hosted-by-the-desktop-app):
repository choices, private derived paths, controlled service restart, concurrent
edit checks, removal/repair and the same private local agent operation. Registration
does not publish memories or grant space access. [Validation](validation/2026-10-19-journal-host-setup.md)
includes actual PostgreSQL approval/queue checks and desktop controls; the new
installed UI flow awaits native release acceptance. Provider sign-in, guided
remote-host setup, independent custody, backfill and writable reconstruction remain
open under issue 39 and F08/C01/A09/U01. The strict count remains **17/64 (26.6%)**.

The [4.17.0 source](releases/4.17.0.md) adds the dedicated
[live conversation adapter](service/live-conversations.md) for issue 41:
complete-record checkpoints, bounded JSONL fragments, per-file scopes, deferred
tails, exact source references and app/agent progress. Source replacements and
truncation start a new generation; mapping removal and complete-catalog rules
remain enforced. Prefix verification still reads older bytes on append. Native
plugin installation, fleet-scale capture scheduling and a producer-backed append
protocol remain separate work. [Validation](validation/2026-10-19-live-conversations.md)
also covers a reproduced desktop control-process quit gap and its bounded drain.
The full-requirement count remains **17/64 (26.6%)**.

The [4.16.0 source](releases/4.16.0.md) adds scheduled
[journal filing and archival](service/git-journal.md#automatic-filing-and-archival):
current records become ordinary Markdown notes, and old day files move intact
into `_archive` only after the notes are ready. Complete projection applies later
revisions and denials first; generated notes never replay as independent memory.
Filing is a separate opt-in with bounded batches, current permissions, app/SDK
controls and the `journal.organize` agent operation. Migration 023 preserves
existing publisher settings and defaults filing off.
[Validation](validation/2026-10-19-journal-filing.md) covers real Git conflicts,
archive retention, PostgreSQL permissions and upgrade compatibility. Issue 39
still needs full app host enrollment, old-memory backfill, writable reconstruction
and large-history/live-provider acceptance. The strict complete count remains
**17/64 shipped (26.6%)** pending those full requirements.

The same batch adds [Grok Build/ACP transcript normalization](service/capture.md)
for [issue 40](https://github.com/Perseusxrltd/mnemion/issues/40), retaining session
identity, streamed text, time bounds, raw provenance and explicit event identity.
[Issue 41](https://github.com/Perseusxrltd/mnemion/issues/41) is addressed separately
by the 4.17.0 adapter above. Native format support alone does not solve ongoing
capture; complete Git-journal inventories and source limits remain mandatory.
Issue 39's newer adoption comment also adds checked reconciliation of its older
external buffer format and exact per-event/remote-byte acknowledgment; use a
separate native prefix until that migration is available. Issue 38 retains
independently retrieved custody and two-client external recovery acceptance.

The [4.15.0 source](releases/4.15.0.md) adds optional
[Git journals for native changes](service/git-journal.md): transactional capture,
pre-publication secret checks, durable local receipts, important-save Git
acknowledgments, a scoped scheduled publisher, app/SDK/agent controls and complete
inventory replay. Deletion and quarantine are applied before source projection;
Git history retention is explicit. Recovery pauses publication and requires
fresh host registration. [Validation](validation/2026-10-19-git-journal.md)
covers real Git operations and PostgreSQL boundaries. Issue 39 remains open for
full app enrollment, large-history capacity,
old-memory backfill and direct writable-space reconstruction. This advances
F08, C01/C08, A12/A13 and U01 without changing the strict full-scope count:
**17/64 shipped (26.6%)**.

The [4.14.0 source](releases/4.14.0.md) addresses the latest concrete examples in
issues 17 and 31 with [question coverage and passage chronology](service/retrieval.md#passage-chronology).
Unchanged lines and numbered decisions retain their dates across revisions;
recent ordering compares query support before dates, with a visible strict-date
option. Search explains the date basis, and evaluations retain the order and
threshold for comparison. Migration 021 preserves historical data with an empty
chronology default and requires no re-embedding. [Validation](validation/2026-10-19-passage-chronology.md)
covers actual retrieval, source updates, SDK compatibility, recorded evaluations
and historical schema/recovery boundaries. Historical Git blame, undated or
ambiguous history, contradiction resolution and broader live model baselines
remain open. The strict full-scope count remains **17/64 shipped (26.6%)**.

The [4.13.0 source](releases/4.13.0.md) implements
[encrypted host packages and resumable reconstruction](service/host-recovery.md)
for supervised Linux/macOS hosts: a complete database snapshot, newer encrypted
access ledgers, stable workspace identities, restricted database logins, explicit
application-key continuity and restored source-runner supervision. Managed updates
default on while preserving a deliberate pause. Status returns startup instructions
and distinguishes local readiness from external-route verification.
[Actual PostgreSQL, process and CLI checks](validation/2026-10-19-host-recovery.md)
cover repeated loss and interrupted restoration. This advances issue 38 and
F08, C01, A06/A09/A12/A13 and U04/U06. Verified off-host delivery, delegated
provider wake, guided app import, Windows/Compose adoption and multi-host takeover
remain open; the strict full-scope count remains **17/64 shipped (26.6%)**.

Published [4.12.0](releases/4.12.0.md) adds a separate
[encrypted credentials vault](service/secrets-vault.md): app setup, scoped
person/key grants, audited explicit reads, encrypted import/export and independent
key recovery. Restored databases preserve later deletions and require fresh vault
grants. [Validation](validation/2026-10-15-secrets-vault.md) records focused tests
and source-app acceptance; the normal native release gates remain separate.
This advances A04, A09, F08 and U01 without claiming complete company policy,
key custody/rotation or KeePass interoperability. The strict full-scope count
remains **17/64 shipped (26.6%)**.

The [19 October operator follow-up to issue 32](https://github.com/Perseusxrltd/mnemion/issues/32#issuecomment-6264307829)
reports successful vault use and manual KDBX 4 migration. Supported KeePass
import/export remains required: entries, fields and custom properties,
masked credential names, value-preservation checks and no plaintext temporary
files. The external report is not a substitute for product acceptance tests.

The [host-reset/reinstallation report, issue 38](https://github.com/Perseusxrltd/mnemion/issues/38)
retains the external deployment, independent custody and guided recovery work
beyond the operator batch above. Preserving identities and restoring access must
continue to respect the latest independently available denial ledger.
[Issue 39](https://github.com/Perseusxrltd/mnemion/issues/39) adds an opt-in durable
Git delivery journal for native saves, scanning hooks, scheduled/important pushes,
librarian folding and stable replay. Its export/deletion/permission contract must
be explicit; connecting an inbound Git source alone does not provide this backup.
The 4.15.0 batch implements capture, guarded delivery and source replay;
4.16.0 adds scheduled filing and intact archival.
The remaining work is tracked separately instead of treating the issue as closed.

Published [4.11.0](releases/4.11.0.md) adds
[company-provider setup in the app](service/company-sign-in.md): HTTPS callback
registration guidance, bounded discovery, private client settings, company CA
bundles, session duration, provider removal/repair and two private local agent
operations. Existing explicitly configured server environments are preserved.
This advances F08, A01/A08 and U01; guided remote-host configuration,
provisioning, company-only policy and fleet/provider acceptance remain open.
The strict full-scope count remains **17/64 shipped (26.6%)**.
Its native release gates, independent artifact verification, live website
update and all six public automatic-update checks passed.

Published [4.10.0](releases/4.10.0.md) adds
[company-account assistant consent](service/hosted-agent-sign-in.md): an approved
person signs in through their company provider, reviews permissions and grants
a revocable connection with a bounded company lifetime. Remembered Studio
sessions are preserved. [Validation](validation/2026-10-15-company-agent-consent.md)
includes PostgreSQL authorization/upgrade/recovery and real Dex/browser/MCP SDK
acceptance. Named-client acceptance, provisioning, company-only policy and guided
remote-host provider setup remain open. This advances F08, C09 and A03/A08 without closing
their full requirements; the strict count remains **17/64 shipped (26.6%)**.
Its native release gates, independent publication verification, live website
update and all six public automatic-update checks passed.

The [4.9.0 source](releases/4.9.0.md) adds [company OpenID Connect sign-in](service/company-sign-in.md):
private invitations and explicit identity links, system-browser desktop sign-in,
protected remembered sessions, account administration and agent controls.
[Validation](validation/2026-10-15-company-sign-in.md) records actual Dex/browser
acceptance, existing-session upgrades and focused native/service checks. Automatic
identity provisioning, company-only policy and fleet/provider acceptance remain open. This advances
F08 and A01/A03/A07/A08 without closing their complete requirements.

Versions **4.8.0 and 4.8.1 are published**: their native release gates, uploaded
package verification, live website updates and all six public automatic-update
checks passed. The release-status automation records each published artifact.

Published [4.8.1](releases/4.8.1.md) gives distinct imported documents priority
in bounded search/context windows and adds a configurable per-document result
limit across the app, agents and evaluations. It also corrects evaluation of
valid excerpts from long documents while retaining citation integrity checks.
[Focused PostgreSQL, MCP and evaluation evidence](validation/2026-10-15-source-grouping.md)
advances the repeated-file report in issue 31. Full current-state/question
quality, dated sections and representative scale measurements remain open;
the strict requirement count remains **17/64 shipped**.

Published [4.4.0](releases/4.4.0.md) adds [guided remote access for local workspaces](service/remote-access.md):
an owned ngrok connection or existing HTTPS proxy, supervised route checks,
hosted browser and consent pages, public invitation links and local operator
commands. [Focused checks and a real local TLS walkthrough](validation/2026-10-15-native-remote-access.md)
cover configuration, restart and outage/recovery. Live provider acceptance,
independent host recovery and company hosting/SSO remain open; publication and
all-platform delivery evidence are tracked automatically above.

Published [4.6.0](releases/4.6.0.md) carries [desktop backups and independent recovery](service/native-backups.md)
from the unpublished 4.5.0 batch:
encrypted snapshots and frequent deletion/access ledgers, OS-protected scheduled
keys, cancellation, persistent failure notices, disk admission, verified separate
recovery copies and selection across restarts. PostgreSQL recovery and desktop
controller checks have passed. Installed Windows checks exposed directory-owner
and path/handle timestamp differences. The corrections include an
[actual Windows encryption failure/recovery comparison](validation/2026-10-15-windows-backup-metadata.md).
[Source and desktop walkthrough evidence](validation/2026-10-15-native-backup-workflow.md)
records the checks and their limits. [All 32 release jobs, uploaded-package
verification, live website delivery and six public automatic upgrades passed](validation/2026-10-15-native-backup-release.md).
Cloud delivery verification and independent host management remain open;
configurable retention is published in 4.7.1 as described below.
The strict full-scope count remains **17 of 64 shipped (26.6%)** because these
broad requirements still have unfinished acceptance criteria.

Published 4.6.0 adds [local desktop operator controls](service/desktop-operator.md)
for agents: discovery, setup, RAM, remote access, protected backup schedules,
inspection, independent restoration and copy selection. The app supplies a
credential-free setup description; commands use an authenticated private OS pipe
under the owning account and share the UI's mutation guards. Unsaved edits block
agent-requested switches; successful switches reconnect the app to its selected
workspace. [154 desktop checks and real source-app/CLI recovery](validation/2026-10-15-desktop-operator.md)
passed, followed by the native release acceptance linked above.

Published [4.7.1](releases/4.7.1.md) adds opt-in backup retention, recorded
inventory and reviewed cleanup in both the app and local agent interface.
Keep-all remains the default. Cleanup protects two verified snapshot/ledger
pairs, the latest access state, other keys and untracked files.
[Actual Windows file operations, PostgreSQL recovery and a source-app walkthrough](validation/2026-10-15-backup-retention.md)
passed. It also fixes [native database identity after Linux clock adjustments](validation/2026-10-15-native-clock-shutdown.md)
and prevents failed shutdown from being reported as automatic-update readiness.
All 32 release jobs, independent uploaded-package verification and live website
delivery passed; public automatic-update evidence is tracked in release status.
Provider delivery, permanent per-file cleanup audit history and independent host
recovery remain open; the strict completion count is unchanged.
The unpublished 4.7.0 candidate is superseded by 4.7.1, which carries these
features together with the restart correction below.

Published [4.7.1](releases/4.7.1.md) allows managed servers to automatically
accept newer minor versions within the same stable major series when schema
hashes and model generations match. It also keeps temporary supervisor timeouts
within the existing restart deadline, with fresh instance checks and idempotent
process commands. [Focused and installed recovery evidence](validation/2026-10-15-compatible-minor-updates.md)
tracks these changes. Older patch-only installations need one explicit upgrade
to reach this policy; automatic migrations and company fleet controls remain open.
The [original shared host was independently restored and upgraded to 4.4.0](validation/2026-10-15-shared-host-upgrade.md),
with preserved access and real Windows queries. It remains a separately operated
installation; neither a source commit nor a desktop publication upgrades it by itself.

Published [4.8.0](releases/4.8.0.md) adds an administrator-managed
[recovery directory and independent encrypted kit](service/recovery-directory.md):
host/operator references, backup/ledger/source locations and independent contacts;
protected desktop copies; offline HTML viewing; and equivalent agent operations.
[Focused service, restoration, desktop and browser evidence](validation/2026-10-15-recovery-directory.md)
is separate from the normal native release and public-update gates. This advances
F08, A06–A07, A09 and A12–A13; delegated host authority, provider delivery
verification, recovery-custodian policy, company SSO and safe takeover remain open.
The strict full-scope count remains **17 of 64 shipped (26.6%)**.

[4.3.3](releases/4.3.3.md) adds explainable, optional key-term support for questions
without a full text match, plus saved evaluation ranking preferences and
protection against mixing service versions within a run. The
[60-question regression and focused checks](validation/2026-10-14-question-retrieval.md)
record measured improvement and its limits. Natural-language quality, dated
sections and actual shared-office acceptance remain open; this batch does not
mark their broader requirements complete.

Published [4.2.1](releases/4.2.1.md) returns freed
model heap pages on glibc-based Linux after idle or budget-triggered eviction.
[37 focused checks and two offline model comparisons](validation/2026-10-13-idle-heap-reclaim.md)
passed, followed by all 30 signed release jobs, 11 separate product jobs and
[independent uploaded-asset verification](validation/2026-10-13-v4_2_1-artifacts.json).
Unchanged native database builds can now be reused with fresh security/recovery
probes. [Paired hosted cache measurements](implementation/native-local-runtime.md#reusing-a-verified-database-build)
reduced the five database jobs from 261–780 seconds to 12–40 seconds; application
and release gates still run. Managed API/worker duplication is addressed by
4.2.5 below; broader peak RAM measurements remain open. [Public automatic upgrades from 4.2.0](validation/2026-10-13-v4_2_1-public-upgrades.json)
passed on all six targets, preserving profiles and ordinary idle safeguards.

Published [4.2.2](releases/4.2.2.md) lets exact task IDs and
filenames enter scoped candidates directly; subject/path matches receive higher
priority. [Regression evidence](validation/2026-10-13-exact-identifiers.md)
includes published-source comparison, access boundaries and correction races.
All six native release targets, the product checks and independent uploaded-byte
verification passed. [Publication](validation/2026-10-13-v4_2_2-publication.json)
and [automatic live website verification](validation/2026-10-13-v4_2_2-website.json)
are recorded; issue 27 is closed. General natural-language quality remains open.

Published [4.2.3](releases/4.2.3.md) combines compact MCP discovery and aliases,
optional credential-bound sessions, newest-first/recorded-since retrieval and
explicit match filters, including app controls. [Focused validation](validation/2026-10-13-search-agent-batch.md)
passed, followed by all 30 release jobs, independent uploaded-byte verification,
automatic publication, website verification and all six public upgrades.
[Automatically retained evidence](validation/releases/4.2.3-status.json) records
the result. Issues 25, 26 and 28 are closed; issue 31 was reopened with fresh
default-ranking examples on 4.2.5. Broader provider integrations,
dated-section chunking and natural-language quality remain incomplete.
Release version preparation, verified publication, follow-up dispatch and retained
per-version status are now scripted. Full native builds are no longer duplicated
on main pushes; failed gates still stop the pipeline.

[4.2.4](releases/4.2.4.md) adds the
[guarded managed-host upgrade](service/managed-upgrades.md), a bridge for older
bootstrap tools, visible migration blockers and journaled forward recovery.
[Focused and real installed-runtime validation](validation/2026-10-14-managed-upgrade-automation.md)
covers backup, PostgreSQL migration, Supervisor restart, retained keys and
enrolled source identities. The [actual shared host](validation/2026-10-14-shared-workspace-upgrade.md)
completed the guarded 4.1.7 → 4.2.4 migration and then automatically installed
4.2.5, preserving its connector and independent Windows administrator access.
The [maintenance board](MAINTENANCE_STATUS.md) now tracks issue activity
and build failures through scripts and GitHub events; normal source integration
also handles generated-metadata races without rewriting released source.

[4.2.5](releases/4.2.5.md) adds one worker-owned local model cache for managed
search and indexing, restart-safe pinned loopback transport and separate worker
resource gauges. The [offline E5 comparison](validation/2026-10-14-shared-model-runtime.md)
measured 37% lower combined model-process RSS with identical vectors and source
spans. Native engines already share a registry; independent containers and
fleet resource policy remain separate. Reviewed issue resolutions now receive
fixing-release labels and close automatically only after verified publication.
Reopened reports stay open. Public delivery evidence remains in release status.

[4.3.0](releases/4.3.0.md) adds [personal-account agent authorization](service/hosted-agent-sign-in.md):
MCP discovery, public-client registration, PKCE, a responsive consent page,
rotating credentials and connected-app revocation. Real PostgreSQL, recovery,
HTTPS browser and MCP checks cover the implemented flow. Company SSO setup,
provider-specific acceptance and full guided host configuration remain open;
publication and platform evidence are tracked in release status.

The same release adds in-app discovery of the current workspace's
personal/company agent sign-in mode, its configured public MCP address and
gateway availability. Existing application-key setup remains accessible.
The same authenticated capability is available through the agent catalog and
TypeScript client; other tenants' issuer configuration is withheld. Host
configuration and live named-provider acceptance remain separate work.

[4.3.1](releases/4.3.1.md) adds bounded source-age and configurable archive-path
preferences to default relevance ordering, with the original relevance score
preserved for thresholds and visible ordering factors. The app, API, SDKs and
MCP search/context controls share the policy. [Focused evidence](validation/2026-10-14-current-state-ranking.md)
tracks the reopened current-state issue; automatic contradiction resolution,
dated-section chunking and representative quality calibration remain open.

[4.3.2](releases/4.3.2.md) adds completed Git snapshot provenance across the app,
API, agents and managed host status, addressing misleading bare-cache branch
freshness (issue 37). It reuses durable checkpoints and preserves per-file dates,
failed-scan boundaries and older-runtime compatibility. [Validation](validation/2026-10-14-git-snapshot-freshness.md)
records source and delivery evidence without marking all source coverage complete.

Published [4.2.0](releases/4.2.0.md) implements personal
passwords, scoped invitations, revocable device sessions, protected desktop and
browser remembering, and 13 private-aware agent operations. The
[sign-in guide](service/sign-in.md) covers user, administrator and agent flows;
[release evidence](validation/2026-10-13-personal-access-release.md) records all
30 signed release jobs, 11 separate product jobs, six installed schema
migration/recovery targets, verified public assets and the updated live website.
[Public 4.1.7 → 4.2.0 automatic updates](validation/2026-10-13-v4_2_0-public-upgrades.json)
also passed on all six targets with preserved profiles and real idle safeguards.
Migration 015 requires a guarded service upgrade. The 4.3.0 OAuth flow extends
these accounts; company SSO onboarding and live named-provider acceptance remain open.

The same release corrects search excerpts from long documents: matching
passages carry exact source offsets and preserve smaller context budgets.
[Thirteen focused retrieval checks](validation/2026-10-13-matched-evidence.md)
and the release/installed-upgrade gates passed; issue 35 is closed. Subsequent
4.2.2/4.2.3 releases add exact identifiers and recency controls. Calibrated
relevance and broader natural-language ranking remain open.

The actual Windows app completed automatic 4.1.4 → 4.1.6 → 4.1.7 installation
and relaunch. That exercise identified a locked-screen focus wait; published
4.2.0 handles an OS-reported lock while preserving all other restart
guards. [Local validation](validation/2026-10-13-locked-desktop-updates.md)
passed 129 desktop checks, and all six native release targets passed.

Version [4.1.7](releases/4.1.7.md) fixes managed update scheduling after a host
resumes from suspension, adds actual next-check/overdue diagnostics, and retains
update and ingestion safeguards. [Source and release validation](validation/2026-10-13-managed-update-schedule.md)
passed: 60 focused checks, all 30 release jobs, independent verification of all
38 assets, public update feeds and the automatically refreshed live website.
[Public 4.1.6 → 4.1.7 upgrades](validation/2026-10-13-v4_1_7-public-upgrades.json)
also passed on all six targets, preserving profiles and the ordinary idle safeguards.

Version [4.1.6](releases/4.1.6.md) ships Git revisions tied to individual file
changes, accurate managed scan reasons, query-only MCP defaults with current
permission checks, small version diagnostics and connection migration guidance.
[All 80 focused tests](validation/2026-10-13-agent-ingestion-stabilization.md)
passed, along with all 30 release jobs, independent verification of 38 assets,
public feeds, the automatically refreshed live website and all six public
4.1.5 → 4.1.6 upgrade rehearsals. See the
[publication record](validation/2026-10-13-agent-ingestion-release.md).
The actual Windows app also completed an observed automatic 4.1.3 → 4.1.4
installation and relaunch after entering the tray; its saved independent human
administrator authenticated again, and its 4.1.6 download was verified.

Version [4.1.5](releases/4.1.5.md) adds [bounded desktop update retries](validation/2026-10-12-update-retries.md) after failed checks and downloads. All 106 Electron tests passed, including recovery, outage limits, cancellation and overlapping-check cases. All six native gates, independent artifact verification, public feeds and the automatically refreshed live website passed; see the [publication record](validation/2026-10-13-update-retry-release.md). [Public 4.1.4 → 4.1.5 upgrades](validation/2026-10-13-v4_1_5-public-upgrades.json) also passed on all six targets.

Version [4.1.4](releases/4.1.4.md) corrects a
[reproduced desktop restart blocker](validation/2026-10-12-navigation-update-safety.md):
the persistent memory-space selector was classified as an unsaved edit. The
change keeps ordinary navigation compatible with updates while protecting real
drafts and transfers. The built-interface browser reproduction, fixed behavior,
real draft protection, Electron tests and version checks passed. All six native
gates, independent artifact verification, publication and live website checks
also passed; see the [release record](validation/2026-10-12-navigation-update-release.md).
[Public automatic upgrades](validation/2026-10-12-v4_1_4-public-upgrades.json) also passed on all six targets.

Version [4.1.3](releases/4.1.3.md) adds the
[managed connector lifecycle](service/managed-connectors.md) for Git, filesystem,
Drive, Slack and rclone runners on adopted Unix hosts. Scans and the compatible
launcher follow the verified current runtime, with configuration preserved,
update coordination, duplicate-run protection and visible versions.
[Source/process, signed installed-runtime and six-platform release checks](validation/2026-10-12-managed-connectors.md)
passed, followed by automatic hosted artifact verification and public-feed checks.
[Public 4.1.2 → 4.1.3 desktop upgrade rehearsals](validation/2026-10-12-v413-public-upgrades.json) passed on all six targets; the actual shared
host's separately launched connector subsequently completed its
[controlled adoption and successful 4.1.4 scan](validation/2026-10-13-managed-connector-adoption.md),
preserving its configuration and source identity. The saved independent Windows
administrator authenticated again on 13 October.

Version [4.1.2](releases/4.1.2.md) adds an explicit keyword fallback when query
inference is busy, with app/agent controls, visible warnings and preserved access
checks. [Source and browser validation](validation/2026-10-12-busy-fallback.md)
passed, as did all six native gates, independent artifact/signature verification
and public-feed integrity checks. The live product page updated automatically;
see the [publication record](validation/2026-10-12-busy-fallback-release.md).
Default retry behavior is unchanged. This implements the remaining overload
option from issue 12. [Public automatic upgrades and relaunch](validation/2026-10-12-v412-public-upgrades.json)
passed on all six targets. Linux ARM passed its targeted retry after a GitHub
checksum gateway timeout; all tests used the unchanged public installers.
The new [hosted artifact verifier](validation/2026-10-12-artifact-verification.md)
also passed, moving future complete release downloads off the operator's PC.

Version 4.1.3 also ships [stable MCP profile identification](validation/2026-10-12-mcp-profile.md)
and the [individual sign-in/invitation contract](implementation/individual-sign-in.md),
with a [tested Argon2id password foundation](validation/2026-10-12-password-foundation.md).
The personal-password implementation is published in 4.2.0. Company SSO,
hosted consent and live provider acceptance remain required.

The immediate priority is coherent batches for operational reliability:
connections and administrator access, installation, verified updates, data safety
and resource stability. Broader features follow without removing requirements
from the checklist. The remaining reported stabilization work includes MCP
client/discovery compatibility and measured retrieval quality: exact identifiers,
relevance, natural-language queries and recency. Version 4.1.6 delivers the
reported Git revision/scan-label, MCP default-scope, version-diagnostic and
connection-guidance fixes.
The separate encrypted secrets-vault request under A04 is implemented in source
4.12.0. It stays outside ordinary memory search, capture and automatic context;
explicitly enabled MCP credential reads are separately authorized and audited.
Version [4.1.1](releases/4.1.1.md) ships idle local-model
cleanup and visible cache statistics, using the existing schema. Its
[local/product checks and real-model measurements](validation/2026-10-12-model-idle-cleanup.md)
passed. All six native installer/update gates, independent verification of all
38 release assets and production signatures, and all six public-feed upgrades
also passed. See the [publication record](validation/2026-10-12-model-idle-release.md).

Version [4.1.0](releases/4.1.0.md) is published on all six desktop targets. It adds [scoped author
withdrawal](service/withdrawal.md), app/agent permission observations and atomic
erasure of protected librarian findings. It also corrects Windows backup flushing
and [macOS Keychain startup and exit waits](validation/2026-10-12-macos-upgrade-startup.md).
The final packages passed release and native gates, independent signature/asset
verification, and all six installed upgrade/recovery checks. The
[publication record](validation/2026-10-12-v410-release.md) distinguishes those
completed checks, including all six public-feed upgrades, from host-specific
deployment. The original shared host completed its controlled 4.0.14 → 4.1.0
migration on 12 October, preserving all 50 existing data tables, identities,
keys and grants. Windows verified a fresh encrypted off-host backup before the
cutover and independently authenticated afterward. The host then picked up
the compatible 4.1.1 patch automatically. The Windows lab then passed its
41-request contributor cycle, including author withdrawal and complete cleanup,
without production writes or cloud calls; see the
[connected-lab acceptance](validation/2026-10-12-model-idle-release.md).
The subsequent [actual Windows concurrency check](validation/2026-10-12-windows-concurrency.md)
passed 27 read-only requests with 10 client requests in flight. It also exposed
another provider sleep, recovered through the independent Computer controls.
No busy response occurred; this is not a saturation or sustained-capacity result.
The [installed schema-upgrade workflow](../.github/workflows/installed-upgrade.yml)
provides a repeatable previous-installer, migration, contributor withdrawal and
isolated recovery gate. Compatible automatic service patches do not apply this
minor-version/database upgrade; desktop and shared-host ownership stay separate.

Version [4.0.14](releases/4.0.14.md) is published on all six desktop targets. It corrects
[Linux readiness and RAM monitoring after a host clock change](validation/2026-10-12-host-clock-readiness.md).
[Publication and the actual shared-host update](validation/2026-10-12-v414-release.md)
passed, preserving existing administrator access and all space grants.

Version [4.0.13](releases/4.0.13.md) is published on all six desktop targets.
[Signed publication, public desktop upgrades and the original shared server's
automatic patch](validation/2026-10-12-v413-release.md) passed. Setup shows the
app and authenticated workspace server versions separately, supports a fresh
server check and explains older servers without version reporting. Shared hosts
and desktop clients retain separate update ownership. It also fixes a
[reproduced administrator diagnostic failure](validation/2026-10-12-administrator-diagnostics.md)
for visible compartments without a content grant, without broadening access.

Version [4.0.12](releases/4.0.12.md) fixes desktop connections through free ngrok
endpoints and prevents cached offline/identity responses from deciding current
workspace access. Connection diagnostics also support authenticated health
gateways. [Native Windows and live-host validation](validation/2026-10-11-workspace-gateway.md)
records the reproduced failures, corrected transport and a successful bounded
40-search baseline. [Publication and public upgrade acceptance](validation/2026-10-11-v412-release.md)
are complete on all six desktop targets. The actual Windows app also joined the
original workspace as an independent human administrator and reauthenticated
its protected saved connection after a normal quit/reopen.

The [complete requirements checklist](PRODUCT_REQUIREMENTS.md) preserves every
requested product area, its delivery state and remaining acceptance checks.
New requests extend that checklist without replacing unfinished work. It covers
native onboarding and RAM controls, company sign-in and independent host access,
Dot/Grokbot/Claude/Hermes/OpenClaw integrations, automatic cross-app capture and
the requested live 3D memory/activity map.

Version 4.0.11 includes an [optional OAuth resource-server foundation](service/oauth.md):
trusted-issuer introspection, discovery/challenges and individually revocable
identity bindings. Version 4.0.11 is published for all six desktop targets. Built-in simple
personal/team sign-in, invitations, app onboarding, consent, reauthorization,
independent recovery and live agent-platform acceptance remain in the queue;
external enterprise identity is an optional deployment path.

Version 4.0.10 adds: [bounded connection diagnosis](service/connection-diagnostics.md)
and the [live 3D memory map](service/memory-map.md). The map includes browser/desktop
orbit, full-screen inspection, evidence links, creator/time filters, recorded
activity, a compact 2D/list path and periodic authorized refresh. It retains the
wiki, earlier evidence graph and Obsidian workflows. All six native targets and
the bundled web app are [published](https://www.perseusxr.com/mnemion).
The [validation report](validation/2026-10-11-memory-map.md) records the release
gates, signed asset verification and automatic live website refresh.

Version [4.0.11](releases/4.0.11.md) integrates native engine/database packaging, app and
agent RAM-policy recovery, and optional trusted-issuer OAuth with individual
bindings and revocation. All six architectures passed installed setup, real model
save/search, shutdown, automatic reopen and occupied-port recovery after fixing
[Windows packaged SQL line endings](validation/2026-10-11-windows-migration-newlines.md).
Bounded installer cleanup and a correction to the native focus-test fixture
resolved the remaining Windows gate failures. The integrated release run at
commit `0eb47cf` passed all 30 jobs, including installed workspace and automatic
update/relaunch checks on all six desktop targets. Artifact/signature verification
and publication are [also complete](validation/2026-10-11-v411-release.md).
A [Linux stale-focus correction](validation/2026-10-11-linux-update-focus.md) also
passed controlled real-updater comparisons and the unmodified public
4.0.11 → 4.0.12 automatic upgrade on both Linux architectures. Windows ARM uses a
native app with an explicitly disclosed x64 backend; see
[packaging evidence](validation/2026-10-11-native-installer-bundling.md),
[policy recovery](validation/2026-10-11-native-policy-recovery.md), and
[OAuth validation](validation/2026-10-11-oauth-foundation.md).

Version 4.0.9 adds OS-encrypted saved desktop connections, authenticated
reconnection after app restart, durable disconnect, device-only forgetting and
clear session choices. Its native encrypted-restart and product gates passed;
these capabilities remain available in 4.0.10.

Version 4.0.8 unifies Studio with the Perseus XR design system and adds signed,
compatible automatic patches for adopted Linux/macOS Python services. Updates
verify backups before cutover, preserve accepted data during runtime rollback,
and retain bounded backup/runtime history. Native Windows/macOS/Linux desktop
updates remain independent. The 84-operation agent catalog, source-sync controls,
bundled web Studio, Obsidian and previous memory reductions are retained.
Release targets include **Windows, macOS and Linux, x64 and ARM64**.
[The official product page](https://www.perseusxr.com/mnemion) lists published
downloads. Each architecture requires its complete verified installer/update set.

The rebuilt shared-memory platform is product v1; its package version is 4.x
to upgrade correctly from the earlier 3.x product. This is a living delivery
plan, not a claim that every planned capability is available. Release status and
known limitations are recorded in [the 4.1.0 release notes](releases/4.1.0.md),
[the preceding patch notes](releases/4.0.14.md),
[the published baseline](releases/4.0.0.md) and
[validation report](validation/2026-10-11-hotfixes.md).

## Product direction

Mnemion stays **100% free forever**, including organization features and updates.
There are no paid tiers or seats. Optional one-time PayPal support starts at €5,
with higher contributions available; it never changes product access. See
[free software and support](SUPPORT.md).

One organized, evidence-backed memory system for people, teams, applications and
agents across devices and providers. Companies control where the service runs,
which sources are connected, who can recall each space, and what leaves their
infrastructure. Obsidian remains a portable visualization and annotation surface.

The server owns shared consistency and indexing. Desktop clients stay small and
can connect to an organization server without downloading an embedding or
language model. Resource limits must be explicit; memory capacity depends on the
server configuration rather than every employee owning a powerful computer.

End-to-end agent operation is an explicit acceptance requirement. Agents need
documented, discoverable API, CLI and MCP routes for setup, source management,
memory organization, retrieval, model/librarian configuration, evaluations,
diagnostics, recovery and maintenance. Use scoped identities, explicit egress
policy, auditable operations and durable results that agents can inspect and
retry. A manual-only screen is a parity gap, not a completed agent workflow.
Administrative authority remains distinct from ordinary memory access.

Multiple independently governed workspaces are a core requirement: people and
agents may belong to personal, employer and client workspaces, with separate
memberships, credentials, context and policies. Every operation has an explicit
target; switching workspaces cannot redirect queued or in-flight work. Combined
search and transfers require explicit scope and policy checks, and company
administration must not expose personal workspaces. Keep every app workflow
agent-operable under the same controls. See the
[multiple-workspace implementation requirements and acceptance tests](implementation/multiple-workspaces.md).
The existing saved-connection feature does not complete these requirements.

Workspace ownership must survive the agent that installed it. The
[continuity contract](implementation/workspace-continuity.md) now explicitly
requires independent human administrators, delegated host operators, an offline
recovery view, registered recovery hosts and clearly scoped Git/backup recovery.
A member device must show whether it holds a connection, source mirror or real
replica; the product must not imply that a remembered connection can replace an
offline host. Requirements A11–A13 and U11 retain this work and actual Windows
stress/update acceptance.

Version 4.0.11 adds [independent administrator setup](service/organizations.md)
and removes Studio's accidental requirement for a content-space grant before
opening administration. [Real API/browser checks](validation/2026-10-11-independent-administration.md)
retain an independently authenticated administrator after the original identity
is disabled, preserve ordinary-member defaults and enforce tenant/content limits.
Named retirement controls, a readable mobile roster and
[final-admin protection across concurrent API/OAuth changes](validation/2026-10-11-administrator-lockout.md)
are published. The Windows dogfood setup has
[protected recovery material and one-click bounded checks](validation/2026-10-11-windows-workspace-preparation.md);
its remote host was subsequently woken through the provider's operator controls,
without an agent model session. A bounded 40-search baseline passed and the
released 4.0.12 Windows app now reconnects as a separate human administrator.
The [connected Windows lab](validation/2026-10-12-workspace-administration.md)
also passed isolated save, indexing, search, revision/conflict and deletion
checks, with no production memory changes or cloud model calls. The human's
Git reader mapping is live and preserves existing agent access. The shared
server has now [migrated from 4.0.0 to managed 4.0.12](validation/2026-10-12-managed-workspace-upgrade.md)
with verified encrypted off-host backups, preserved keys/grants and another
successful Windows lab cycle. Its subsequent [automatic 4.0.13 service patch](validation/2026-10-12-v413-release.md)
also passed with a reverified backup, preserved identities/keys and unchanged
grant memberships/roles. The host-clock finding and remaining bootstrap/recovery
work stay tracked separately.
Registered recovery hosts, a complete replica/backup path and failover remain open.

Version 4.0.11 also adds an [offline saved-workspace view](validation/2026-10-11-offline-workspace-details.md)
with the last verified identity/organization role, verification date and bundled
recovery guides. The role is encrypted and destination-bound, and viewing it
does not contact a server or authorize a session. Existing 4.0.10 connections
remain compatible. Registered host and backup records, unverified prepared
connections, independent recovery hosting, delegated operator controls and
complete agent parity are still required.

## Implemented for the first shared-platform release

| Area | Available behavior | Documentation |
| --- | --- | --- |
| Shared memory | PostgreSQL transactions, tenant/space boundaries, scoped agent identities, revision history, durable receipts and deletion | [Service](service/README.md), [organizations](service/organizations.md) |
| Retrieval | Pinned local multilingual E5, lexical and semantic search, cited context, chunk/index identity and bounded context packs | [Service](service/README.md) |
| Model choice | E5/BGE CPU profiles, approved Ollama/OpenAI endpoints, per-space candidate indexes, progress/pause/retry, preview/evals and atomic activation/rollback | [Embedding models](service/embeddings.md) |
| Librarian | Approved local/cloud models, optional schedules, call budgets, exact source revisions, organization proposals, review findings and guarded undo | [Librarian](service/librarian.md) |
| Sources | Git, selected folders, Google Drive, Slack, rclone and custom adapters; immediate sync requests, timestamped results, checkpoints, leases, review proposals and pauses | [Connectors](service/connectors.md) |
| Agent compatibility | HTTP/OpenAPI, Python/TypeScript SDKs, authenticated MCP, 87 published operations, CLI/MCP administration, bounded private results, safe retries, conversation capture | [Agents](service/agents.md), [administration](service/agent-control.md), [capture](service/capture.md) |
| Human organization | Studio memory review, source evidence, team access, wiki/graph, core context and operations | [Knowledge](service/knowledge.md) |
| Obsidian | Markdown, stable paths, citations, wikilinks, managed refresh, conflict detection and preservation of personal annotations | [Studio](../studio/README.md) |
| Reliability | Durable jobs, retries and leases, ingestion/resource limits, verified backup/recovery, v3 archive/import/cutover/rollback | [Recovery](service/recovery.md), [migration](service/migration.md) |
| Observability | Six visual insight views, private evaluation sets and runs, comparisons, case inspection and exports | [Insights and evaluations](service/insights.md) |
| Desktop lifecycle | Background operation, login startup, update preferences and safe idle restart; updater enabled by default in supported packages | [Updates](service/updates.md) |
| Service lifecycle | Private Unix Supervisor lifecycle; opt-in host adoption with automatic signed compatible patches, isolated staging, verified backups and runtime rollback | [Background service](service/supervision.md), [managed updates](service/managed-updates.md) |
| Workspace connections | OS-protected desktop bookmarks, rechecked identities, API-bound handles, durable disconnect and session-only fallback | [Workspace connections](service/workspaces.md) |
| Studio design | Perseus XR colors and local fonts across workspace, insights, settings and offline help; grouped responsive navigation | [Design system](STUDIO_DESIGN.md) |
| Documentation and web installation | Offline library generated from repository Markdown; Studio included in official Python archives, with one source-build command and verified asset/license inventory | [Setup](service/README.md#studio), [maintenance](MAINTENANCE.md) |

Implementation does not by itself certify every deployment. Provider tests use
fixtures unless a validation report explicitly identifies a live test. Native
release artifacts require the platform checks and publisher requirements below.

## Release completion gates

1. Pass service, legacy, SDK, security and frontend checks on the release commit.
2. Build and launch native desktop packages on Windows, macOS and Linux, for
   x64 and ARM64, including their sandboxed bridges and local Obsidian client.
3. Publish ready OS/architecture pairs independently using `deploy/release-targets.json`.
   Version 4.0.0 shipped macOS and Linux. Version 4.0.1 adds Windows x64;
   4.0.3 adds Windows ARM64 after native installation/update/relaunch validation.
   Each offered pair needs all its
   installer and authenticated-update checks.
   Mac uses the [validated Sparkle integration](implementation/free-macos-updates.md)
   with independently signed archives. Windows x64 uses independent manifest
   signatures; pending SignPath approval concerns OS publisher reputation.
4. Rehearse a signed upgrade, rollback/recovery, startup and safe restart. Record
   the environments and results rather than inferring them from compilation.
5. Verify all immutable artifacts, architecture-specific feeds, inventories,
   checksums, release notes and public repository hygiene before publication.
6. Keep the live [Perseus XR product page](https://www.perseusxr.com/mnemion),
   homepage feature and existing Lab Notes entry current. The site provides
   platform downloads, setup, release notes, the roadmap and optional support.
   Each platform's downloads require its complete published installer/update
   assets. Pending platforms stay visible without download links.

Missing credentials or failed platform checks remain release blockers; the
release notes must state the actual shipping status.

Release operations have a no-spend constraint: do not buy certificates, enroll
in paid programs or start trials that convert to paid subscriptions. Evaluate
free open-source signing and sponsorship without claiming approval in advance.
The standard Apple Developer ID program is paid. Apple's publisher trust remains
unavailable, but Mac compatibility does not require membership. The maintained
Sparkle updater and real Electron integration passed both native architectures
with independently signed archives and explicit first-install approval. Broader
managed-device and OS-version checks continue after this measured baseline.
Keep source, web and local development paths documented. See the
[code signing policy](CODE_SIGNING.md).

## Complete setup from the app

Priority added on 2026-10-11: every required installation, configuration and
recovery step must have a clear, resumable path in Studio. A clean supported
computer must be able to create a local workspace, join a team, configure an
organization host or restore a backup without a terminal being the required
completion path. Models, sources, access, agents, Obsidian, updates and backups
belong in the same guided flow, with real readiness checks and optional steps
that can be revisited. Keep equivalent agent/operator operations available.

Published 4.0.11 and 4.0.12 bundle the local engine/database and guide workspace
creation, CPU model setup, RAM control and occupied API-port recovery. Integrated
installed flows, shutdown and automatic reopen passed on all six targets.
Source 4.11.0 adds company-provider configuration for the locally owned host,
with discovery, session/certificate controls, repair and local agent parity.
The complete app-only setup requirement remains **partial**: organization
hosting, provider approval, full source setup and independently delivered backup recovery remain open. See the
[full acceptance requirements](implementation/app-onboarding.md) and
[current validation scope](validation/2026-10-11-local-address-recovery.md).
Do not count a setup guide, mock success or disabled button as an implemented flow.

## Next patches: reliability and operational confidence

The immediate access priority is to separate workspace reachability and operator
recovery from an agent's availability or model quota. Add clear connectivity
diagnostics, individual invitations/sign-in and hosted OAuth while continuing
the native local-runtime and resource work. See [current agent-platform research](research/2026-10-11-agent-platforms.md).

The first [live 3D map](service/memory-map.md) shipped in 4.0.10:
permission-filtered memories, topics, relationships and real recorded activity,
with evidence inspection and a lightweight mode. Follow native release validation
with larger-workspace clustering, incremental subscriptions and time replay.

Priority is defects found in installation, access control, recovery, migration,
update behavior and routine team use. Patches retain the service/API contract
where possible and include migration/rollback instructions when needed.

- Keep every published architecture in subsequent releases and integrate SignPath
  when approved. No publisher approval
  is assumed and no paid certificate purchase is planned. The
  [independent signed-update implementation](implementation/free-windows-updates.md)
  passes native Windows x64 and ARM64 installation, upgrade and relaunch. The
  public, unmodified Windows x64 4.0.1 → 4.0.2 automatic upgrade also passed;
  see [the dated evidence](validation/2026-10-10.md).
- Verify the 4.0.2 remote-agent fixes in upgraded deployments: one API/MCP
  endpoint, connection-time authentication, explicit scope diagnostics,
  described tool fields, compact structured errors and bounded inference
  admission with SDK retry guidance (issues 5, 9, 10, 12 and 16).
- Complete provider acceptance and guided setup of the 4.3.0 hosted-agent OAuth flow (issues 4 and 18), native
  remote setup (3). Extend 4.0.8 managed service patches to fleet/Compose/Windows
  rollouts, maintenance windows and migration-bearing upgrades (11). Public
  service-feed patches have passed on the original shared host, most recently
  4.1.0 → 4.1.1. Extend the verified managed supervisor and bundled Studio to
  broader deployments, including actual boot, network and database startup order.
  Desktop automatic updates do not upgrade a separately deployed memory server.
- Validate 4.0.8's malformed-cursor handling (19) and atomic librarian decision
  retries (20) in upgraded deployments. Both source-reviewed reports have local
  PostgreSQL/HTTP regression reproductions; publication and remote-host adoption
  are recorded separately.
- Extend the 4.0.4 agent catalog to new operations as they ship. Existing HTTP
  administration is discoverable and callable; host setup, recovery and service
  updates continue to require operator credentials and their separate CLI paths.
  Keep schema parity, small response budgets and unknown-write outcomes tested.
- Continue reducing API/worker resident memory (13). Version 4.0.3 shares one
  tokenizer vocabulary per local model, saving 296 MiB after loading E5 in the
  recorded comparison while preserving generation, source spans and vectors.
  Native local hosting now includes cooperative budgets and idle-model release;
  4.2.5 adds managed worker ownership and separate worker gauges, with an offline
  comparison measuring 37% lower combined model-process RSS. Independent
  containers, fleet policy and broader peak-memory measurements remain. Scoped author withdrawal (14) passed all six
  installed migration/recovery gates and the original shared host's Windows
  contributor exercise. Improve source-space onboarding (8), extend 4.0.5's durable
  sync requests and timestamped diagnostics with provider webhook verification,
  and evaluate natural-language retrieval against keyword baselines (17).
  Track [the issue queue](https://github.com/Perseusxrltd/mnemion/issues) and verify
  fixes through real deployments as well as isolated protocol tests.
- Complete signed native installation and upgrade rehearsals across supported
  OS versions, including restricted company devices, offline recovery and Linux
  desktop environments with and without a system tray.
- Expand real-provider contract checks with consented test tenants, token expiry,
  removals, reconnection, rate limits and large incremental source updates.
- Add representative held-out retrieval and answering evaluations, concurrent
  load/cost profiles and recovery drills. Publish datasets that can legally be
  shared, environment manifests, denominators and reproducible commands.
- Extend diagnostics/export and accessibility based on observed support cases;
  preserve privacy by keeping memory text out of general telemetry.
- Maintain dependency advisories, public API examples and operating-system
  support policy with each patch.

Acceptance: verified fixes, bounded resource use, explicit evidence, no access
regressions and release notes describing changed behavior and limitations.

## Selectable embeddings and controlled reindexing

Implemented: operator-approved model profiles, two small CPU choices,
Ollama/OpenAI-compatible endpoints, pinned generation/tokenizer identities,
explicit per-space egress approval, bounded inference and durable reindexing.
Studio shows coverage, pause/resume/retry, candidate search and generation-aware
evaluations. Activation checks retained revision coverage atomically; rollback
reuses existing vectors and fills missing revisions. Recovery requires renewed
endpoint consent. See [the model guide](service/embeddings.md).

Remaining improvements: measured hardware recommendations, larger multilingual
comparisons, provider-specific pricing/rate-limit instrumentation and an explicit
retention/garbage-collection policy for old generations. Current retrieval keeps
E5 as its default; model selection follows measured language/domain quality,
latency, memory, privacy and cost rather than a universal "best model" claim.

## Configurable librarian

Implemented: approved Ollama/OpenAI-compatible profiles, explicit per-space
outbound approval, manual and optional scheduled jobs, durable daily call limits,
strict evidence-linked proposals, diffs, decisions, guarded undo and run history.
Organization handles titles, additional tags and summaries one memory at a time.
Broader review finds possible links, duplicates, contradictions and stale claims
within a bounded batch. Models cannot grant access, delete evidence, merge records
or mark claims verified. Recovery pauses processing and clears endpoint consent.
See [the librarian guide](service/librarian.md).

Source 4.16.0 adds separately enabled, model-free filing of current Git journal
memories into Markdown and intact archival, with matching app/agent controls.
This does not replace the model-assisted quality work below.

Remaining improvements: measured model/hardware comparisons, calibrated quality
evaluations, acceptance/rejection analyses, organization-wide grouping and review
policies for specialized domains. Current protocol, permission and recovery tests
use synthetic HTTP model responses; they do not certify a live model's reasoning
quality. Acknowledging a finding does not modify the canonical knowledge graph.

Acceptance for broader automation: measured usefulness on held-out team data,
reliable recovery/undo, permission isolation and explicit resource/egress budgets.

## Organization operations and secured vaults

Current compartments are authorized tenant/space boundaries with scoped keys.
TLS, restricted server identities and deployment controls protect the service;
disk/backup encryption belongs to the deployment. Obsidian exports are plaintext.

Company OIDC sign-in and app-owned provider setup are implemented in 4.9–4.11;
source 4.12.0 adds separate encrypted credentials and independent key recovery.
Remaining extensions include lifecycle provisioning, policy-managed devices and
updates, stronger audit export/retention, managed key custody/rotation, organization
quotas and shared source ownership. Credential-value encryption does not change
the search/storage boundary of ordinary memory. End-to-end encrypted searchable
memory is not a current promise.

Acceptance: clear threat and recovery models, revocation across projections,
least-privilege integration tests and no misleading encryption claims.

## Source ecosystem and interoperability

Maintain the open adapter contract so storage can live in Git, mounted folders,
rclone-supported clouds or a company-defined system. Slack and Drive are the
first direct collaboration/cloud adapters; additional messaging and knowledge
systems, such as Teams, Confluence and Notion, require dedicated adapters and
permission-preservation tests before being called supported.

Next priorities: administrator-friendly connector onboarding, incremental change
visibility, source-health diagnostics, conflict resolution, bounded bandwidth
and scheduling, cross-source identity and deletion propagation. Preserve source
ownership and citations; do not treat sharing a cloud folder as granting access
to every memory space.

Acceptance: restartable ingestion, stable identities, explicit access mapping,
provider quota handling and reproducible removal/revocation tests.

## Legacy preservation and compatibility

Use the [v3 feature audit](implementation/v3-feature-parity.md) and
[feature decisions](implementation/feature-review.md) as the preservation ledger.
Useful older capture, curation, wiki, trust, context and Obsidian workflows must
have a documented equivalent, migration path or explicit retirement reason.
Unsafe Git database union and destructive implicit replacement stay retired.

Priorities include uncommon vault layouts, large migrations, interrupted cutover,
post-cutover rollback and personal Obsidian annotations. Compatibility requires
tested behavior, not simply retaining an old file or command name.

## Keeping the plan current

Every release and hotfix includes its own notes and reviews this roadmap against
what actually shipped. Move work into the implemented section only after its
acceptance evidence exists. Do not replace historical notes or measured results;
append new results with their version and environment. See
[release and documentation maintenance](MAINTENANCE.md).
