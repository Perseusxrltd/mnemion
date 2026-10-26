# Complete product requirements

Updated **2026-10-26**. This is the persistent checklist for the Mnemion rebuild,
including additions made during implementation. The [roadmap](ROADMAP.md)
explains delivery order; this file preserves the complete requested scope.

The [complete-milestone audit](implementation/completion-audit.md) decomposes all
42 partial requirements into missing acceptance work, dependencies and evidence.
It retains every requirement and keeps effort estimates unknown until inspected.
The generated [release status](RELEASE_STATUS.md) records the current published
distribution and release gates. The audit preserves dated publication and
actual-deployment evidence as historical snapshots. At the **22 October 2026
review**, the first durable-capture L1 journey had
[qualified for 4.45.0 release preparation](validation/2026-10-22-l1-candidate-acceptance.md);
publication and actual-deployment acceptance remain separate gates. Broader
provider capture and the complete layered librarian remain open.
The [frozen 4.45.0 native qualification](validation/2026-10-22-l1-release-native-acceptance.md)
subsequently passed all six installed targets at **19:27 UTC**; it does not
establish publication, public-update or actual-deployment acceptance.

**Shipped** means an available, documented capability. **Partial** means useful
behavior is available but the complete request remains open. **Building** means
implementation or validation is underway, not released. **Planned** means the
requirement is retained without a completed implementation. **External** means
a provider or publisher prerequisite is unresolved. **Ongoing** identifies a
standing product or maintenance commitment. A passing prototype, mock
test or source commit is not a shipped feature.

Current strict completion: **17 of 66 requirements shipped (25.8%)**; 42 partial,
1 building, 2 planned, 3 ongoing and 1 external. These broad requirements are
not equally sized. This is coverage of the full requested scope, not a measure
of engineering effort or the usability of the published app. Hotfixes to a
partial feature do not automatically mark its whole requirement complete.

**26 October 2026, 03:55 UTC, current V08 — Building/source implementation:** bounded
sender components, owned workflow hooks and a dedicated collector now exist in
[source](implementation/anonymous-product-telemetry.md).
[Isolated TLS and collector-service checks](validation/2026-10-25-telemetry-collector-service.md)
passed; production collection remains unavailable (`false`, destination and
route `null`). [Five installed privacy-control targets](validation/2026-10-26-telemetry-preview.md)
from frozen 4.46.12 passed all 64 required fields. The overall release run failed
in Intel Mac packaging and supervision; it does not establish publication or
complete V08 acceptance. As of this checkpoint, frozen 4.46.13 still awaits
native/public acceptance. The [one six-case attribution run](validation/2026-10-26-telemetry-attribution.md)
completed with all six functional journeys and reviewed source matches;
enabled matched main-process RSS maxima of **3,608,576 / 3,391,488 bytes** remain
above 2 MiB. The decision selects cold initialization/storage-runtime ownership
review, with no repeat benchmark or budget revision. Exact-next-packet inspection
remains unimplemented; the **2 MiB / 0.5%** resource gates stay unchanged and
unaccepted. No requirement text or state changes in this checkpoint.

**24 October 2026 historical source checkpoint — V08, Building:** the
[fresh backup and independent restore](validation/2026-10-24-4465-backup-acceptance.md)
passed at **00:01:45** and **00:15:23 UTC**. V08 then had source-only
[app/native privacy controls](guides/product-telemetry-controls.md) and a
**19-check core browser journey** accepted at **00:51:17 UTC**, followed by
**eight browser policy/fault checks**. The later [source-input qualification](validation/2026-10-24-telemetry-controls.md)
passed at **01:12:30 UTC**.
At that checkpoint, no sender or collector existed and production analytics
were unavailable. Anonymous ingress and all-six-native acceptance remained
unqualified.
That work was excluded from the isolated 4.46.6 dependency-security release.
That checkpoint changed only V08's state; all 66 requirement texts and the other
65 states were preserved.
The dated entries below retain earlier states and delivery decisions.

**23 October 2026 historical scope addition — V08:** retain the new
[anonymous product telemetry request](implementation/anonymous-product-telemetry.md)
as a separate planned requirement. It covers aggregate app/agent usage,
performance, resources, bandwidth and fixed error codes, with disclosed default
enablement and persistent user opt-out/re-enable. The contract preserves the
exact request and defines anonymity, collector, policy and native/web acceptance.
It is queued after the current live-update/independent-host milestone and is
not included in frozen 4.46.1. All previous 65 requirement texts and states are
unchanged; the added scope changes the denominator, not completed work.

**22 October 2026 independent-host source progress:** the
[development host-control guide](guides/company-host-control.md) now covers
`/hosts`, protected per-device logins and equivalent native-agent controls,
pinned restricted SSH roles, durable operations, reviewed signed upgrades with
independent encrypted Git backups, and local OS-owner custodian recovery. Its
[focused source/fixture checks](guides/company-host-control.md#qualification-and-remaining-work)
passed within their stated scope; new native gates are written but unrun.
Installed-client and production acceptance, provider wake, boot registration,
independent authority custody and safe takeover remain open in the
[continuity contract](implementation/workspace-continuity.md). This progress
changes none of the 65 requirement texts or states and does not close #44/#45.

The expanded **R07 librarian workstream** is [documented separately](research/2026-10-20-layered-librarian.md), including available reasoning traces, background consolidation, all layers, vault boundaries, statistics, scientific evidence and TypeSafe AI Jev. It adds one planned requirement; the lower percentage reflects added scope.

**22 October 2026 candidate snapshot:** the **4.45.0 release candidate**
qualifies the first approved local Codex JSONL journey in the app and native
agent controls, plus independent headless capture on all six installed targets.
It advances C03/C08/F08 and the R07 foundation with
offline custody, recovery, reviewed policies and bounded resources. Preparing
this candidate does not change the strict shipped count or close provider,
fleet, broader migration or L2–L7 requirements. Availability follows
[live release status](https://github.com/Perseusxrltd/mnemion/blob/main/docs/RELEASE_STATUS.md).

Source **4.41** advances **C03/C08/F08** with [capture selection in the app and
native agent controls](service/live-conversations.md#choose-how-much-to-capture):
complete exposed records or supported user/assistant messages only, explicit
provenance and mode-aware progress. [Source and actual app acceptance](validation/2026-10-20-capture-policy.md)
passed. This supplies an R07 capture foundation; broader provider histories,
cross-layer consolidation and the remaining acceptance work stay open.

Source **4.39** carries [native Hermes/OpenClaw setup](service/desktop-agents.md)
and [Perseus XR connection packages](service/agent-packages.md) through the app,
API, SDKs and standalone CLI. C07 moves from planned to partial after
implementation and focused/native-manifest validation. C04/C05/F08 advance
without changing the strict shipped count. **Issues 44/45 remain open** for
actual cloud-client and guarded deployment acceptance. **Issue 46 closed on
20 October** after [genuine source revalidation and unchanged-client reads](validation/2026-10-20-office-access.md).
The [current issue plan](implementation/github-issues.md) separately records
the 22 October 12:06 UTC lease-expiry episode and the successful unchanged-reader
checks at 15:48:54 UTC after independent provider revalidation. Continuing
availability, source-host custody and complete inventory remain unproven. A
deliberately paused upstream note publisher remains distinct from the API and
native memory journal.
The combined candidate also fixes container branding inputs and gives explicit
host upgrades a bounded turn under frequent source scans. Its free
[research watch](research/RESEARCH_WATCH.md) supplies review candidates for R07;
the full layered librarian remains planned.

Published 4.37.0 combines the unpublished 4.35/4.36 work and corrects a
[first-setup state publication race](validation/2026-10-20-state-publication.md).
The same error was reproduced with the existing code on native Windows;
focused Linux and Windows checks passed with the correction. All six native
release gates, independent artifacts, the live website and all six public-update
rehearsals passed. Actual shared-host acceptance remains separate.

**Standing setup and publishing requirements:** every Mnemion setup/configuration
workflow must have a discoverable native agent path, as well as the relevant app
flow; see [agent setup](service/agent-setup.md). All connector/app/plugin artifacts
and listings must identify **Perseus XR** as author/developer. Native Grok/Grokbot,
Claude, Hermes, OpenClaw and OpenAI/Codex/Dot integrations remain explicit C04–C07
work; generic MCP configuration alone does not complete those integrations.

**Standing delivery requirement:** every update reviews current GitHub reports,
groups the ready fixes and advances the roadmap when possible. Production
failures take precedence; fixed issues close only against their verified public
release. Real-agent reports remain actionable even when automated checks pass.

[Actual signed-in ChatGPT acceptance](validation/2026-10-20-chatgpt-acceptance.md)
completed issue 18: OAuth, permission review, installation, 16 discovered tools
and a successful profile-only request. C05/A08/F08 remain partial because their
scope also includes other clients, provider policy and complete native setup.

The combined release advances **F08/R04/V01** with
[scoped queue workload monitoring](service/insights.md): separate indexing and
physical cleanup, pending/leased/failed counts, retries, due jobs, oldest age
and logical text volume in the app, API, SDKs and agent interface. Existing
scope checks and bounded snapshot collection remain. [Database and browser
acceptance](validation/2026-10-20-queue-visibility.md) passed; native release and
representative fleet capacity remain separate. No complete requirement is promoted.

The combined source advances **R04/A09/C09/U11** with
[priority purges and persistent organization/space indexing turns](service/indexing-queues.md).
[Eighteen database/reindex cases passed](validation/2026-10-20-fair-indexing.md).
The [actual 4.33 update/lab observation](validation/2026-10-20-433-live-updates.md)
retains the failed cycle, pending physical cleanup and the successful update
identity checks separately. Schema migration, native release and real-host
acceptance remain distinct; no complete requirement is promoted.

Published 4.34.0 advances **F08/C01/C02/U01** with
[guided desktop Slack/Drive sources](service/desktop-cloud-sources.md): selected
resources, separate OS-protected provider credentials, short-lived read-only
Drive tokens, current provider permissions and matching private-agent controls.
Offline pause/removal and scan/RAM limits are shared with folder sources.
[Focused acceptance](validation/2026-10-20-desktop-cloud-sources.md) uses controlled
provider responses; interactive provider enrollment, fleet policy and actual
customer-account acceptance remain open. No complete requirement is promoted.

Published 4.32.0 advances **F08/C04/C05/U01** with
[guided native agent installation](service/desktop-agents.md): reviewed named
entries, dedicated application keys, private backups, preserved client policies,
offline removal and matching local-agent operations. A versioned private runtime
continues outside Studio and follows app updates without rewriting client files.
[Focused validation](validation/2026-10-20-desktop-agents.md) and native delivery
remain distinct. Grok Build uses its observed native TOML contract; this does not
complete the separate Grokbot, Dot, Hermes or OpenClaw plugin requests. No broad
requirement is promoted by configuration support alone.
The corrected candidate also includes [bounded Windows atomic-write retries](validation/2026-10-20-windows-state-locks.md)
for a backup-status failure found before publication. Lasting denials preserve
existing data and private permissions; this is a base reliability fix.

Published 4.31.0 advances **F08/C01/C03/U01** and extends **R03/R04** with
[desktop folder, Obsidian and JSONL source setup](service/desktop-sources.md).
People and local agents can manage protected dedicated keys, background capture,
RAM/file limits and saved-source controls before sign-in or during an outage.
A contributing app needs no local database. The existing permission/inventory
contracts remain in force. [Focused validation](validation/2026-10-20-desktop-sources.md),
all six native release gates and [actual Windows/shared-host updates](validation/2026-10-20-431-live-updates.md)
passed; separate public-update rehearsals remain automatically tracked. Other provider enrollment and
fleet coverage remain open; no broader requirement is marked complete.

Published 4.30.2 advances **F08/A10** with explicit Windows ownership and private
ACLs for agent-configuration backups and staged replacements. Existing client
policies, other servers and failed-write recovery retain their contract.
[Linux and native Windows checks passed](validation/2026-10-20-agent-setup-private-files.md);
[publication and actual automatic updates passed](validation/2026-10-20-4302-live-updates.md). No new provider profile or full requirement
is claimed by this fix.
It also fixes [Windows PostgreSQL backup paths at the 260-character boundary](validation/2026-10-20-windows-backup-paths.md),
without shortening private workspace paths or changing the machine's settings.
Bounded failure diagnostics survive into the app and private agent status.

Published 4.30.2 advances **F08/A06/A09/U02** with
[server-package database recovery through the desktop app](service/desktop-host-recovery.md).
The complete encrypted inventory, included or newer ledger, explicit recovery
scope and a new private database are reviewed through the same app and local
agent controls. Existing organization/memory identities, current denials and
fresh administrator access are retained. Source/provider/OS configuration stays
separate; this does not finish full host reconstruction or independent cloud
delivery. [Focused validation](validation/2026-10-20-desktop-host-recovery.md)
and the [native release and live continuity evidence](validation/2026-10-20-4302-live-updates.md)
have passed. Public update rehearsals are tracked separately. Strict coverage stays 17/64.

Published 4.28.0 advances F08/A12/U01/U02 with [private desktop connection controls](service/desktop-operator.md#select-a-team-workspace-from-a-local-agent).
Trusted local agents can verify the intended person/organization, select a key or
password account, inspect/reopen saved connections and return to the local host.
The same draft, permission and OS-protection rules apply while the app is in the
background. [Focused validation and all six installed targets](validation/2026-10-20-desktop-workspace-control.md)
passed before publication. The [actual Windows app and shared host](validation/2026-10-20-shared-workspace-adoption.md)
updated automatically to 4.28, and the app selected the independent human login
with protected persistence. A separate
[actual hosted HTTPS OAuth exercise](validation/2026-10-20-live-hosted-signin.md)
preserved existing agent keys and verified off-host configuration backup;
[signed-in ChatGPT acceptance](validation/2026-10-20-chatgpt-acceptance.md) later passed. Other provider acceptance remains open. Strict coverage is unchanged.

The [actual Windows shared lab](validation/2026-10-20-windows-shared-lab.md)
advances U11/R04 with isolated contributor authority, 42 successful cycle
requests, complete synthetic cleanup and 27 successful read-only requests up to
ten in flight. A user-level scheduled task checks new app/server versions and
runs one bounded cycle, preserving measured receipts without an agent session.
This is a short connection-specific baseline, not a saturation or fleet claim.

Source 4.29.0 advances F03/F08/A09/A13/U01 with [resumable native journal recovery](service/journal-recovery.md):
complete uploads up to 2 GiB, durable progress across restarts, private staged
history, original-byte resume checks, negative decisions before positives,
reviewed batches, preserved local changes, automatic staging cleanup and app/SDK/
agent parity. This extends the earlier bounded path without claiming full host
provisioning, cross-admin delegation or unavailable original-office state.
Strict full-scope coverage remains unchanged.

Source 4.27.0 advances host continuity with [portable backup recovery](validation/2026-10-19-portable-host-recovery.md).
A Git-downloaded encrypted package was restored on a different physical computer,
retaining the original application identities and exact memories. Actual Ubuntu
and Windows clients passed API/MCP checks and restart continuity. Locale-aware
legacy restoration and a portable inventory remove the discovered keyword-index
mismatch. Full OS/provider provisioning, original-office data recovery and broader
availability remain partial; the strict count is unchanged.

Source 4.26.0 advances F03/F08/A09/A13/U01 with [native journal recovery](service/journal-recovery.md):
complete inventory review, original IDs or independent copies, editable current
content, durable withdrawals and content-free quarantine identities, local-edit
preservation and app/SDK/agent parity. The guided limit is 1 MiB and 1,000
identities. Source 4.29 extends this with resumable uploads; the original
office's unavailable full state remains separate work. Later quarantine state survives older full-backup
restoration through the current recovery ledger; newer positive text still
needs a full snapshot or complete journal review. The batch also carries the
withheld 4.25 importer and fixes recovery-screen update guards. Strict full-scope
completion is unchanged.

Source 4.25.0 advances F03/F08/A09/A13 with [reviewed legacy-buffer recovery](service/legacy-buffer.md)
in Studio, SDKs and private agent controls. Available records become writable
native memories with stable identities and retained provenance. Reconciliation
preserves edits and withdrawals, checks current access and refuses existing Git
publication. It does not reconstruct missing history, original accounts or the
unavailable office database/vault. Source 4.26 adds the bounded native-journal
path above; larger recovery and broader provider adoption remain open.

Source 4.23.0 advances A04/A09/F08 with [KeePass transfer](service/keepass.md):
exact import preview, default masked labels, encrypted original field mapping,
grant-checked export and matching app/SDK/private-agent controls. Independent
KDBX fixtures and actual database tests protect values, current access, recovery
and atomic imports. This addresses issue 32's remaining portability request;
broader company policy, managed key rotation and custody still keep A04 partial.

Source 4.22.0 advances F08/C01/A09 with [existing native-memory backfill](service/git-journal.md#including-existing-native-memories)
for issue 39. Separate approval, bounded persistent scanning, privacy rejection,
administrator takeover and app/SDK/agent controls protect current identity and
publication policy. [Validation](validation/2026-10-19-journal-backfill.md) includes
real Git, current access and full restore. Source 4.25 adds legacy-buffer
reconciliation and 4.26 adds bounded native-journal reconstruction. Larger
inventories and provider/recovery acceptance remain separate work;
the full requirement count is unchanged. [All current GitHub reports](implementation/github-issues.md)
remain part of this scope.

Source 4.21.0 advances F08/C01/C08 with [isolated text failures and source health](service/connectors.md#text-file-failures-and-source-health)
for issue 43. It keeps healthy updates flowing, protects missing-file reconciliation
and stable identities, and reports source gaps through the app, recall, SDKs and
agent controls. [Validation](validation/2026-10-19-source-health.md) retains
fail-closed journal and access handling. This does not complete provider onboarding,
fleet adoption or the broader advanced-monitoring requirement; the count is unchanged.

Source 4.20.0 advances F08/C01/A09 with [pinned SSH journal access](service/git-journal.md#ssh-deploy-keys-and-host-pins)
for issue 42. App and local-agent setup use the same private credential references;
receipts distinguish local repositories from HTTPS/SSH destinations. The
[real SSH/API evidence](validation/2026-10-19-journal-ssh.md) does not complete
provider onboarding, native platform acceptance or independent office recovery.

Source 4.19.0 advances F08/R04/U04 with [bounded journal rollover](service/git-journal.md#file-rollover-and-version-compatibility)
and [private local agent update controls](service/desktop-operator.md#app-updates-and-startup).
It also fixes native connections dropping server-version metadata and hiding
supported features; the installed Git-setup check caught this before 4.18 publication.
The [focused evidence](validation/2026-10-19-journal-rollover-updates.md) includes
more than 20 MB of real Git publication, cached retries and guarded update control.
Full inventory/fleet capacity, provider sign-in, backfill and independent hosting
remain separate acceptance; no broad requirement is promoted by this batch.

Source 4.18.0 advances F08/C01/A09/U01 with [local app Git journal registration](service/git-journal.md#a-workspace-hosted-by-the-desktop-app)
and a matching private local agent control. [Focused validation](validation/2026-10-19-journal-host-setup.md)
covers approval, queue preservation and restart contracts. Native delivery, provider
sign-in, remote-host setup and independent recovery remain separate acceptance;
this addition does not promote those broad requirements to shipped.

## Foundation and compatibility

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| F01 | Study the entire existing repository; use MemPalace and comparable memory tools to inform an update or rebuild. | Shipped | [Study, evidence and architecture](research/2026-10-09-mnemion-study/README.md). Revisit comparisons when they inform a concrete decision. |
| F02 | One organized memory infrastructure for individuals, teams, applications and AI systems across providers and hardware. | Partial | [Shared platform](service/README.md) is available. Complete the access, hosting, onboarding and integration rows below. |
| F03 | Preserve valuable features from previous versions instead of losing them during the rebuild. | Partial | [V3 parity audit](implementation/v3-feature-parity.md) and [migration](service/migration.md). Continue native migration/recovery validation and explicitly record retained, replaced and deferred behavior. |
| F04 | Keep Obsidian compatibility for visualization and ordinary Markdown use. | Shipped | [Managed export, annotations and conflicts](../studio/README.md), [knowledge views](service/knowledge.md). All new graph/capture work must preserve this boundary. |
| F05 | Support Windows, macOS and Linux, including Intel/AMD and ARM hardware. | Partial | Six desktop distributions and their bundled local engine/database are published. [Installed setup/reopen and public updates passed on all six targets](validation/2026-10-12-managed-connectors.md). Restricted company devices and broader OS-version coverage remain open; Windows ARM currently uses the documented x64 backend. Source 4.24 pins compatible Intel Mac Argon2 bindings and adds early binary availability checks; Mac local-model minimums are documented separately from remote-client use. |
| F06 | Work on modest computers without requiring a GPU or a model on every client. | Partial | Remote clients require no local model. Published native setup includes small CPU profiles, automatic RAM budgets and pressure controls. Broader hardware measurements and explicit minimum requirements remain; an unsupported OS or unlimited data at fixed RAM is not promised. |
| F07 | Use durable, portable formats and a maintainable architecture that can evolve safely. | Partial | Versioned API, PostgreSQL, Markdown, source evidence and migration contracts exist. Continue upgrade compatibility, recovery and large-workspace tests. |
| F08 | Keep every required workflow usable end to end by agents as well as people. | Partial | [103 reviewed operations from 4.3.0, CLI and MCP](service/agent-control.md). Published 4.2.0 adds [13 private personal-access operations](validation/2026-10-13-personal-access-release.md); local status, RAM repair and stopped-workspace port recovery already have operator commands. [Published 4.1.6](validation/2026-10-13-agent-ingestion-release.md) adds query-only MCP defaults with current authorization and small version diagnostics. Published [4.6.0](validation/2026-10-15-native-backup-release.md) adds [19 private local desktop operations](service/desktop-operator.md), with all six native delivery gates and [actual source-app schedule, restore and selection evidence](validation/2026-10-15-desktop-operator.md). Published 4.7.1 extends this to 21 operations with [inventory and reviewed retention cleanup](validation/2026-10-15-backup-retention.md); [native release and publication evidence](RELEASE_STATUS.md) passed. Remote host delegation and complete provider/recovery workflows remain open. Published 4.8.0 adds [two administrator recovery operations and local encrypted-kit creation](service/recovery-directory.md); its native release gates, publication and all six public automatic updates passed. The 4.9.0 source adds seven [company-access operations](service/company-sign-in.md), including private one-use login handling. The 4.10.0 source adds company-account assistant consent through the standard OAuth/browser flow; its private handoffs stay outside generic memory tools. Source 4.11.0 adds `local.company-discover` and `local.company`, for 23 private desktop operations, with the same provider review and restart controls as the app. Source 4.13.0 adds six private host CLI actions for encrypted custody, inspection, journaled restoration and status; see the [host operator guide](service/host-recovery.md). Source 4.30.2 adds [reviewed database import from server packages](service/desktop-host-recovery.md) through the app and existing private agent controls. Complete host/provider adoption and delegated provider actions remain open. Published 4.28 adds private desktop account verification/selection, personal sign-in, protected bookmark restore/inspection and local-host reopening. [All six installed targets and actual Windows selection passed](validation/2026-10-20-desktop-workspace-control.md); remote-host delegation remains separate. Published 4.33 adds [private desktop embedding/librarian enrollment](service/desktop-models.md), reviewed keys and limits, controlled host restart, repair and matching agent controls; per-space cloud approval and external model-server resource ownership remain explicit. [All six native targets and artifact verification passed](validation/2026-10-20-desktop-models.md). |

## Sources, assistants and automatic capture

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| C01 | Handle memories and vault sources from Git, Google Drive, arbitrary clouds and company-managed storage. | Partial | [Folder, Git, Drive, Slack, rclone and custom adapters](service/connectors.md). Finish provider sign-in UX, live-provider validation and reconnect/removal coverage. Provider support and permissions must be explicit. Source 4.13.0 adds registered source-runner supervision, packaged recovery of connector settings, and early adapter/policy diagnostics. Complete sign-in, provider validation and cloud delivery remain open. |
| C02 | Connect company messaging and collaboration systems, including Slack. | Partial | Slack ingestion and access mapping exist. Expand messaging adapters, event delivery and their actual permission/retention contracts. |
| C03 | Gather conversations automatically across AI applications after the user or company enables capture. | Partial | [Watchers, hooks and export normalizers](service/capture.md) exist for selected sources. Source 4.41 adds [complete or message-only live capture](service/live-conversations.md#choose-how-much-to-capture), with actual app/agent acceptance and explicit format limits. Finish native provider capture and coverage reporting; connecting MCP does not automatically expose a provider's full chat history. |
| C04 | Connect Anthropic/Claude, including relevant apps, plugins, MCP and capture paths. | Partial | Claude Code/Desktop MCP setup and Claude export normalization exist. Source 4.39 adds [Perseus XR packages](service/agent-packages.md), with actual Claude Code 2.1.59 manifest validation. Complete live provider capture and public listing acceptance remain open. |
| C05 | Connect OpenAI/ChatGPT/Codex and Dot through the supported apps/plugins and local or remote connection paths. | Partial | Codex setup and ChatGPT/Codex export normalization exist. Published 4.1.3 adds [stable authenticated MCP profile identification](validation/2026-10-12-mcp-profile.md), with all six native release gates and public package verification passed; it does not implement sign-in. The 4.3.0 [personal-agent OAuth flow](service/hosted-agent-sign-in.md) adds PKCE and consent. [Actual ChatGPT OAuth installation, 16 tools and a profile-only call](validation/2026-10-20-chatgpt-acceptance.md) passed on 20 October. Source 4.39 adds [Perseus XR portable packages](service/agent-packages.md); public directory distribution, account-controlled cloud attribution, Dot and other live provider acceptance remain open; see [current platform research](research/2026-10-11-agent-platforms.md). |
| C06 | Connect Grokbot through a supported plugin/connector and retain access independently of its model quota. | Planned | Generic authenticated HTTP/MCP works when its host is reachable. Build and validate the actual Grokbot connection/capture path and independent host ownership/recovery. |
| C07 | Support Hermes, OpenClaw and other agent platforms without inventing incompatible configuration. | Partial | Source 4.39 adds [native Hermes YAML and OpenClaw JSON5 setup](service/desktop-agents.md), profile paths, private credentials, observed status and safe removal. [Perseus XR packages](service/agent-packages.md) provide their documented OAuth configuration. Focused app/API tests passed. Actual provider runtimes, catalog/SDK extensions and complete capture still need acceptance. |
| C08 | Offer a genuinely connected system with clear capture coverage, deduplication and source provenance. | Partial | Revisions, source identity, idempotent reconciliation and evidence exist. [Published 4.1.6](validation/2026-10-13-agent-ingestion-release.md) fixes unnecessary Git revisions after unrelated commits and preserves managed scan reasons; native, artifact, website and all six public automatic-upgrade checks passed. Show per-provider last capture, gaps, exclusions, failures and removal state. Never silently label partial imports complete. Published 4.8.1 [groups matching imported document parts across search, context and evaluations](service/retrieval.md#results-from-distinct-documents); source-aware candidate selection is not a claim of complete capture coverage. Source 4.14.0 retains unchanged passage dates across source revisions, with query-specific chronology and an explicit date basis; this does not reconstruct missing historic Git blame. Source 4.42 combines [folder reconnection](validation/2026-10-20-source-identity-recovery.md) with [conversation identity and verified copied captures](validation/2026-10-20-conversation-identity.md), retaining original memories and reader access. Focused source/app checks passed; native delivery and live acceptance remain separate. |
| C09 | Preserve access boundaries when several agents, people, devices and configurations share sources. | Partial | Tenant/space grants, mapped source access and leases exist. Complete individual hosted sign-in, policy-managed source approval and fleet tests. The 4.10.0 source adds company-account consent with browser/request binding, current permission review, bounded lifetimes and immediate local revocation; [real Dex/MCP SDK acceptance](validation/2026-10-15-company-agent-consent.md) is separate from named-provider acceptance. Source 4.42 [source-identity checks](validation/2026-10-20-source-identity-recovery.md) preserve original readers, revalidate newly mapped readers against the actual folder and refuse ambiguous or mismatching catalogs before import. [Issue 46 access acceptance](validation/2026-10-20-office-access.md) is now closed after genuine provider scans and unchanged-client list/fetch/lexical checks. These operational results are separate from the source tests and the remaining company/fleet scope. |

## Organization access, hosting and safety

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| A01 | Let an organization set up a workspace once and make joining straightforward for its users. | Partial | [Personal sign-in, scoped invitations and remembered connections](service/sign-in.md) ship in 4.2.0. Finish guided company hosting and identity-provider onboarding. The 4.9.0 source adds company sign-in and invitation acceptance; remote-host provider onboarding and fleet acceptance remain. Source 4.11.0 adds [guided provider setup for an app-owned local host](service/company-sign-in.md#a-workspace-hosted-by-the-desktop-app). Guided remote-host setup, provisioning and fleet/provider acceptance remain. |
| A02 | Provide specific individual logins or an equivalent simple, secure sign-in, rather than shared administrator credentials. | Shipped | Published 4.2.0 provides [personal passwords, invitations, revocable device sessions and private CLI controls](service/sign-in.md). [All six installed personal-access and migration/recovery gates, public packages and the live website passed](validation/2026-10-13-personal-access-release.md). Company SSO and hosted consent remain separate work under A08 and the [implementation contract](implementation/individual-sign-in.md); scoped machine and recovery credentials are retained. |
| A03 | Give administrators clear control over people, agents, permitted spaces and connections. | Partial | [People, applications, keys and space grants](service/organizations.md) and [individual device sessions/revocation](service/sign-in.md) ship. 4.3.0 adds [personal agent consent and revocation](service/hosted-agent-sign-in.md). Company connection policy and delegated recovery/host controls remain. The 4.9.0 source adds [company identity links and immediate revocation](service/company-sign-in.md) in the app and agent interface. The 4.10.0 source extends these controls to company-authorized assistants, including app/link/person revocation and a visible absolute expiry. |
| A04 | Compartmentalize private, team, project and company memory in secured vaults. | Partial | Tenant/space authorization is enforced. Source 4.12.0 adds a [separate encrypted credentials vault](service/secrets-vault.md), with app key setup, person/key read/write/list grants, auditing, encrypted export/import, explicit MCP exposure and recovery that clears historical grants while preserving later deletions. [Focused service, desktop and app evidence](validation/2026-10-15-secrets-vault.md) is separate from native publication acceptance. This advances [issue 32](https://github.com/Perseusxrltd/mnemion/issues/32); source 4.23 adds [KeePass current-field transfer](service/keepass.md), while independent key custody, broader company policies and managed rotation remain. Ordinary memory/Obsidian exports are not covered by credential-value encryption. |
| A05 | Make remote workspaces reachable through stable, supported connection options. | Partial | Published 4.4.0 adds [guided native sharing, owned ngrok supervision, existing HTTPS proxy checks and public invitation links](service/remote-access.md), with [real local TLS/controller outage and recovery validation](validation/2026-10-15-native-remote-access.md). All 30 release jobs, independent uploaded-artifact verification and the live website update passed. Live provider acceptance and broader private-network configurations remain open. [Issue 3](https://github.com/Perseusxrltd/mnemion/issues/3). |
| A06 | Keep access and configuration available when an agent is unavailable or out of tokens. | Partial | Independent human administration and provider operator wake were exercised without the original agent session; the actual Windows app reconnects as a separate administrator. Encrypted snapshot/ledger restoration, managed host adoption and signed automatic service patches passed with preserved access. The original host also completed the [controlled 4.1.0 migration and automatic 4.1.1 patch](validation/2026-10-12-model-idle-release.md), with a fresh Windows-verified encrypted backup and independent administrator reconnect. The [15 October independent provider wake and guarded 4.3.2 → 4.4.0 upgrade](validation/2026-10-15-shared-host-upgrade.md) preserved the actual Windows administrator and enrolled connector configuration. Native encrypted backup scheduling is published in 4.6.0. Finish the product-managed host inventory, recovery entry point and independent delivery verification. A stopped computer still requires its host-management channel. Published 4.8.0 implements [shared host/recovery references, protected desktop copies and an independent encrypted HTML kit](service/recovery-directory.md), with [focused restoration and offline evidence](validation/2026-10-15-recovery-directory.md). Native delivery and all six public updates passed. Delegated host actions and independent backup delivery verification remain. Source 4.13.0 adds [host reconstruction from independent encrypted files](service/host-recovery.md), with actual repeated database/role loss and CLI runtime-loss checks. Host wake, independent delivery and guided takeover remain open. The new independent shared host passed [managed adoption, a real automatic 4.27→4.28 update and personal browser/Windows access](validation/2026-10-20-shared-workspace-adoption.md), preserving existing agent keys and backed-up state. This is one deployment, not general provider wake or failover. |
| A07 | Provide an online workspace entry point and management UI as well as the desktop app. | Partial | Web Studio ships with the service, including [personal sign-in and invitations](service/sign-in.md) in 4.2.0. Finish company SSO and independent host/recovery management; use company-controlled hosting rather than requiring a central paid service. Published 4.8.0 adds a portable encrypted recovery viewer that can be served from independently controlled HTTPS hosting. Company SSO and delegated host management remain separate requirements. The 4.9.0 source implements company sign-in in web and desktop Studio, with [actual Dex/browser acceptance](validation/2026-10-15-company-sign-in.md); independent host control remains. [Actual public browser acceptance](validation/2026-10-20-shared-workspace-adoption.md) verified the existing independent administrator, all eight spaces, account controls and confirmed sign-out. |
| A08 | Support hosted-agent OAuth and consent, including safe authorization, expiry and revocation. | Partial | The [optional trusted-issuer resource-server foundation](service/oauth.md) is published in 4.0.11. Personal passwords and invitations are published in 4.2.0. 4.3.0 adds [personal-account PKCE, consent, registration, refresh, reauthorization and revocation](service/hosted-agent-sign-in.md), with browser and recovery checks. Published 4.4.0 exposes [local-host HTTPS and consent configuration in the app](service/remote-access.md). Company identity onboarding, provider-specific acceptance and guided remote-host adoption remain required. [Issues 4 and 18](https://github.com/Perseusxrltd/mnemion/issues/18). The 4.9.0 source adds company-account Studio sessions. The 4.10.0 source implements [company-account assistant consent](service/hosted-agent-sign-in.md), with [PostgreSQL upgrade/recovery and actual Dex/browser/MCP SDK evidence](validation/2026-10-15-company-agent-consent.md). Automatic provisioning, company-only policy, guided remote-host provider setup and named-provider acceptance remain open; installer/publication evidence is tracked separately. Source 4.11.0 supplies local-host provider discovery, registration guidance, session/certificate settings and repair; guided remote-host setup and named-provider acceptance remain. |
| A09 | Keep memories reliable, recoverable and auditable as hosts and providers change. | Partial | [Backups, recovery ledger and restored-access reconciliation](service/recovery.md) exist. The [native backup/recovery workflow](service/native-backups.md) ships desktop scheduling, protected keys, independent restoration and copy selection in [4.6.0](validation/2026-10-15-native-backup-release.md), with all six native backup/recovery and public update gates passed. Published 4.6.0 also adds [agent schedule, restore and selection controls](service/desktop-operator.md). Published 4.7.1 implements [opt-in retention, private inventory and reviewed cleanup](validation/2026-10-15-backup-retention.md), with actual Windows file operations, PostgreSQL recovery and a source-app walkthrough. Complete cloud delivery verification, permanent per-file cleanup audit history, host migration and independent disaster recovery; source checks alone do not close this requirement. Published 4.8.0 adds backup/ledger/source references and a directory that survives a real database restoration; references alone do not verify recovery contents or provider delivery. Source 4.13.0 adds encrypted host snapshots and newer ledgers, stable identities, guarded resume and explicit application-key continuity. [Focused and compatibility checks](validation/2026-10-19-host-recovery.md) passed; actual provider delivery and full disaster-recovery UX remain open. |
| A10 | Keep the repository clear, documented and safe to publish. | Partial | Public release inventories, license notices and secret/dependency checks exist. Repeat relevant checks on every release; no private endpoints, keys or personal account material in public evidence. |
| A11 | Let several authorized owners/admins govern the workspace independently of the agent that created it, with explicit levels of authority. | Partial | [Independent administrator setup](service/organizations.md), an organization roster without a content grant, named retirement and [final-admin protection](validation/2026-10-11-administrator-lockout.md) are published. A separate human administrator joined the original workspace through the Windows app and [reconnected after restart](validation/2026-10-11-v412-release.md). [Individual sign-in and invitations](validation/2026-10-13-personal-access-release.md) now ship. Finish recovery-custodian policy and delegated host operators. Git access does not silently promote a memory key. |
| A12 | Keep administration and recovery understandable from another enrolled device when the primary agent, computer or tunnel is offline. | Partial | Version 4.0.11 adds [offline saved-workspace details](validation/2026-10-11-offline-workspace-details.md), including encrypted, dated role observations, locked/legacy states and fresh authorization on reconnection. Published 4.1.0 corrects [macOS Keychain startup and exit waits](validation/2026-10-12-macos-upgrade-startup.md), with bounded access, an isolated helper and explicit retry; all six installed upgrade/recovery targets passed. The [continuity contract](implementation/workspace-continuity.md) still requires the independent entry point, registered hosts/backups, approved operator actions, agent parity and safe takeover without divergent writers. Joining does not imply a local replica. Published 4.8.0 adds [protected desktop recovery references and an independent encrypted kit](service/recovery-directory.md), plus HTTP/SDK/CLI/MCP directory parity. Native release gates and all six public updates passed. Approved operator actions and safe takeover without divergent writers remain. Source 4.13.0 supplies a private host recipe and agent-readable restore/status/startup instructions. External hosting authority, boot registration and safe takeover still require their independent controls. Published 4.28 provides local-agent selection and offline inspection through the actual protected desktop store; the real Windows app joined the independent shared workspace without a live original-agent session. Host wake and delegated provider authority remain separate. |
| A13 | Recover available memory from Git or any configured provider without confusing source copies with complete workspace backups. | Partial | Existing source ingestion and verified database restoration cover separate scopes. Finish guided inventory, backup/ledger verification, source-only recovery labeling and reconciliation of writes, permissions and deletion state. Published 4.8.0 labels source mirrors separately from complete backups and access/deletion ledgers in the app and offline kit. Inventory references are not content verification or write/deletion reconciliation. Source 4.13.0 packages complete database and access state with host settings, keeping it distinct from inbound source copies. Git write-back and guided source-only reconciliation remain open. |
| A14 | Let people and agents withdraw their own untouched memories without granting broad reviewer authority. | Shipped | Published 4.1.0 adds [scoped author withdrawal](service/withdrawal.md), current permission observations and atomic cleanup of protected librarian findings. [Source/browser, all six installed migration/recovery checks and the exact restored-host contributor exercise](validation/2026-10-12-v410-release.md) passed. Separately hosted 4.0.x workspaces require the checked migration. The original shared host completed it, then automatically patched to 4.1.1; its [actual Windows contributor cycle](validation/2026-10-12-model-idle-release.md) passed with all synthetic memories withdrawn and no production writes. This addresses [issue 14](https://github.com/Perseusxrltd/mnemion/issues/14). |

## Installation, lifecycle and updates

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| U01 | Complete installation and configuration from scratch through a simple app UI. | Partial | Published 4.0.11/4.0.12 include the local engine/database, workspace creation, CPU model setup, RAM controls and occupied-port recovery. [Installed save/search, shutdown and reopen passed on all six targets](validation/2026-10-11-v412-release.md). Published 4.4.0 adds guided local-host sharing and public invitation addresses; 4.6.0 adds [guided encrypted backup and restoration](service/native-backups.md). Company hosting, provider approval and independent host recovery remain under the [app onboarding acceptance contract](implementation/app-onboarding.md). Source 4.11.0 adds company-provider setup, discovery, private client/certificate settings, removal/repair and local agent parity; broader onboarding requirements remain open. The actual Windows app completed an unattended 4.15→4.20 update and relaunch on 19 October, retaining automatic updates, login startup and background operation; [evidence](validation/2026-10-19-windows-live-update.md). Published 4.33 adds [private desktop embedding/librarian enrollment](service/desktop-models.md), reviewed keys and limits, controlled host restart, repair and matching agent controls; per-space cloud approval and external model-server resource ownership remain explicit. [All six native targets and artifact verification passed](validation/2026-10-20-desktop-models.md). |
| U02 | Configure sources, agents, models, access, Obsidian, resources, backups and recovery from the app. | Partial | Published workspace screens include RAM-policy repair and [occupied API-port recovery](service/local-workspaces.md), with agent parity and preserved private state. Published 4.4.0 adds [local remote-access configuration, restart and route checks](service/remote-access.md) with private operator equivalents. Published 4.6.0 adds app and agent controls for encrypted backup schedules, verified independent copies and restoration. Provider approval, remaining host operations and independent host takeover still need complete, resumable UI flows. Published 4.28 closes the desktop account-selection agent-parity gap; intended identity, current selection and unsaved-work guards apply to the existing app workflows. |
| U03 | Run in the background and system tray/menu bar where supported. | Shipped | [Desktop lifecycle](service/updates.md). Linux shells without a tray retain an accessible minimized window. |
| U04 | Start automatically and recover after restart on every supported OS. | Partial | Desktop login startup, Unix service supervision and native local workspace automatic reopen are available. [Installed restart checks passed on all six targets](validation/2026-10-11-v412-release.md). Broader machine-boot, unattended server startup and fleet policy acceptance remain. Source 4.13.0 restores registered source runners with Supervisor and returns cron/launchd instructions after host recovery. It does not claim to register or verify the replacement OS startup task. |
| U05 | Enable automatic verified updates by default and restart safely without losing work. | Shipped | Verified updates are enabled by default in supported desktop packages. The public [4.6.0 upgrade/relaunch passed on all six targets](validation/releases/4.6.0-status.json), with unchanged public packages and preserved profiles. The preceding 4.1.0 release also passed separate installed schema-migration/recovery checks. Normal idle, draft and transfer guards remain. A [reproduced false unsaved-work blocker after space navigation](validation/2026-10-12-navigation-update-safety.md) is corrected in published 4.1.4, with the fixed browser scenario, all six native gates and artifact/public-feed checks passed. [Bounded failed-check retries](validation/2026-10-12-update-retries.md) are published in [4.1.5](validation/2026-10-13-update-retry-release.md), with all six native release gates and public artifact/feed verification passed. Older affected AppImages may need one normal Quit or current download; organization deployment policies and shared-server updates are separate. Published 4.2.0 also handles [retained window focus behind the OS lock screen](validation/2026-10-13-locked-desktop-updates.md), with 129 local desktop checks and all six native release targets passed. Its [public automatic-update rehearsals](validation/2026-10-13-personal-access-release.md) also passed on all six targets, separately from installed schema-migration/recovery acceptance. The 4.7.0 source also [keeps failed engine shutdown visible and blocks update readiness](validation/2026-10-15-native-clock-shutdown.md), with two new desktop regressions and verified fixture teardown. |
| U06 | Deliver hotfixes to shared servers as well as desktop clients. | Partial | [Managed Unix service patches](service/managed-updates.md) exist after explicit host adoption. The original shared server completed a [verified automatic 4.0.12 → 4.0.13 patch](validation/2026-10-12-v413-release.md), including backup/runtime verification and preserved access. Setup shows separate app/server versions. Published 4.0.14 corrects the [host-clock readiness finding](validation/2026-10-12-host-clock-readiness.md); the original host passed an [operator-applied patch and current-runtime verification](validation/2026-10-12-v414-release.md) with preserved access. The original host subsequently completed its [controlled 4.1.0 migration and automatic 4.1.1 patch](validation/2026-10-12-model-idle-release.md), preserving the independent Windows administrator. Published 4.1.3 adds [managed connector lifecycle and version visibility](service/managed-connectors.md) for issue 22. [Source, signed-runtime, all six native release gates, automatic artifact verification and public delivery checks](validation/2026-10-12-managed-connectors.md) passed. The [actual shared connector was subsequently adopted and completed a 4.1.4 scan](validation/2026-10-13-managed-connector-adoption.md), preserving its existing configuration and source identity; the independent Windows administrator reauthenticated on 13 October. The original reporter confirmed automatic API/worker updates, closing issue 11. [4.2.4 adds a guarded schema/minor-version upgrade, older-bootstrap bridge, retained recovery state and visible blockers](service/managed-upgrades.md); [real candidate installation, PostgreSQL migration, retained keys and enrolled source checks passed](validation/2026-10-14-managed-upgrade-automation.md). The [4.7.1 source](validation/2026-10-15-compatible-minor-updates.md) permits compatible stable minor updates with identical schemas/models, rechecks cached eligibility and tolerates short supervisor delays within the restart deadline. The actual shared host completed the [guarded 4.3.2 → 4.4.0 upgrade](validation/2026-10-15-shared-host-upgrade.md); older patch-only hosts need one operator upgrade to obtain the new policy. Windows/fleet/Compose policy, app-managed operator entry points and automatic migration-bearing upgrades remain. Source 4.13.0 defaults restored Unix hosts to managed updates, preserves an explicit pause, and includes registered source runners in the supervised lifecycle. Windows/Compose/fleet adoption remains open. A second real Unix host passed [managed adoption from 4.17, migration to 4.27 and automatic 4.28 delivery](validation/2026-10-20-shared-workspace-adoption.md), retaining both registered Git sources, keys and OAuth. Fleet/Windows/Compose acceptance remains. |
| U07 | Ship ready platforms promptly while validating the remaining platforms. | Shipped | [Release process](MAINTENANCE.md) publishes only complete verified installer/update sets and preserves already available targets. |
| U08 | Keep `main` current with tested work, monitor issues, and keep implementing through new user requests. | Ongoing | New requests extend this checklist and the active queue; they do not silently replace unfinished requirements. Preserve uncommitted work, commit validated milestones and record regressions. |
| U09 | Keep documentation, release notes, roadmap and in-app help current with updates. | Partial | Offline docs are generated from repository Markdown. [Release preparation, publication, website follow-ups and retained evidence are automated](implementation/release-automation.md); the first live 4.2.3 cycle passed all public gates. [Issue/build status](MAINTENANCE_STATUS.md) now refreshes from GitHub events, and reviewed issue fixes receive release labels after verified publication. Affected feature guides, requirement IDs and limitations still require engineering review with every relevant release. The 4.13.0 operator recovery guide, source/recovery contracts, validation, release notes and affected requirement rows are included in the app documentation build. **20 October addition:** maintain all Mnemion documentation, including website product/setup/platform text and homepage/Lab Notes, from Git so updates need no duplicate website maintenance. The [Git documentation contract](website/README.md) retains schema/release validation, last-good content on failures and release-bound operating guides. [Live Git-only acceptance](validation/2026-10-20-git-owned-website-content.md) passed on 20 October: a canonical content update reached the product page, homepage and Lab Notes without another website deployment. U09 remains partial because affected guides, roadmap claims and release evidence still require engineering review. |
| U10 | Deliver an official first release, then continue improving the complete roadmap. | Partial | Shared-platform v1 is published as package series 4.x. The complete requested product remains in progress; a version label does not close this checklist. |
| U11 | Use the actual Windows installation as a connected, bounded stress-test client for the shared workspace and live automatic updates. | Partial | The actual Windows [4.0.13 → 4.1.0 automatic install/relaunch](validation/2026-10-12-windows-v410-auto-update.md) passed with preserved preferences and a verified independent administrator reconnect. The actual Windows app completed an [unattended 4.0.12 → 4.0.13 installation and relaunch](validation/2026-10-12-v413-release.md), preserving its human administrator connection and background/startup settings. The shared server patched automatically to 4.0.13 and later passed the [operator-applied 4.0.14 clock correction and Windows administrator reconnect](validation/2026-10-12-v414-release.md). The [isolated lab](validation/2026-10-12-workspace-administration.md) passed save/idempotency, indexing, lexical/semantic search, revision/conflict and deletion using a separate restricted key. After [live server migration](validation/2026-10-12-managed-workspace-upgrade.md), the cycle passed again with 40 requests and no production writes or cloud calls. Encrypted off-host backup, Windows decryption and isolated restoration also passed. Following the original host’s controlled 4.1.0 migration and automatic 4.1.1 patch, the [actual Windows contributor cycle](validation/2026-10-12-model-idle-release.md) passed 41 requests with complete synthetic cleanup, no production writes and no cloud calls. The [subsequent read-only concurrency check](validation/2026-10-12-windows-concurrency.md) passed 27 requests with 10 in flight after independent provider wake, with no writes. It did not reach saturation. Larger workloads and guided recovery remain. The actual Windows app subsequently completed [automatic 4.1.4 → 4.1.6 → 4.1.7 installation and relaunch](validation/2026-10-13-locked-desktop-updates.md), exposing the locked-screen focus case addressed in published 4.2.0. On 15 October, [nine read-only requests from Windows](validation/2026-10-15-shared-host-upgrade.md) authenticated the unchanged protected administrator profile against the upgraded 4.4.0 host and compared three queries. This is connection evidence, not a new app-installation or saturation claim. On 20 October, the actual Windows x64 app completed [ordinary 4.20→4.27→4.28 updates](validation/2026-10-20-shared-workspace-adoption.md) and joined the current shared host with its independent human administrator password session, protected persistence and prior bookmark retained. This new setup is not a saturation measurement. The same enrolled app subsequently passed [ordinary 4.31→4.32 updates and the 41-request isolated lab](validation/2026-10-20-432-live-updates.md), retaining its protected human login and both bookmarks. The private acceptance driver verifies each frozen release and predecessor receipt before requesting normal update checks; it retains failed or incomplete cycles and prevents overlapping upgrades. |

## Models, RAM and memory bandwidth

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| R01 | Offer current, optimized embedding models and meaningful user choice. | Partial | [Pinned CPU and approved remote profiles, candidate indexing and rollback](service/embeddings.md). Continue measured model/language/domain comparisons; no universal “best model” claim. Published 4.33 adds [private desktop embedding/librarian enrollment](service/desktop-models.md), reviewed keys and limits, controlled host restart, repair and matching agent controls; per-space cloud approval and external model-server resource ownership remain explicit. [All six native targets and artifact verification passed](validation/2026-10-20-desktop-models.md). |
| R02 | Adapt resource use to the hardware, especially available RAM. | Partial | Automatic local working budgets, pressure-aware admission, smaller batches and idle unloading are published with the native runtime. Six installed local-workspace gates passed. Published 4.1.1 adds idle model-session cleanup to API/worker processes and visible cache statistics, with [real E5/BGE measurements on Linux and both Mac architectures](validation/2026-10-12-model-idle-cleanup.md); [4.2.5 adds managed worker ownership and an offline comparison](validation/2026-10-14-shared-model-runtime.md) measuring 37% lower combined model-process RSS. Published 4.7.1 fixes [native database RAM accounting and ownership after Linux clock adjustments](validation/2026-10-15-native-clock-shutdown.md), with a real PostgreSQL check. Broader actual minimums, hardware measurements and fleet resource policy remain. |
| R03 | Let both users and agents change Mnemion's RAM allocation at any time. | Shipped | Published [app and local operator controls](service/local-workspaces.md) change the persisted local working budget, expose current policy and repair invalid settings. [Native policy recovery](validation/2026-10-11-native-policy-recovery.md) and all six installed gates passed. This is a cooperative application budget, not an OS memory reservation or a universal remote-host limit. |
| R04 | Treat memory bandwidth, ingestion, retrieval and concurrency as part of the core pipeline. | Partial | Bounded requests, ingestion limits, leases, context budgets and inference admission exist. Published 4.1.2 adds [explicit keyword fallback during inference saturation](service/embeddings.md), including byte-bounded context, app/agent controls, current authorization checks and fallback counters. [Native gates, artifact verification, public delivery and all six public automatic upgrades](validation/2026-10-12-busy-fallback-release.md) passed. The [actual Windows lab](validation/2026-10-12-windows-concurrency.md) passed 27 read-only requests and 10 in flight against 4.1.1, without reaching saturation. [Published 4.1.6](validation/2026-10-13-agent-ingestion-release.md) removes unnecessary Git memory revisions and embedding work; it retains complete inventory transfer. Finish representative throughput, queue, working-set and recovery measurements. Published 4.2.0 adds [matching excerpts and exact source offsets](service/retrieval.md), with [13 focused checks](validation/2026-10-13-matched-evidence.md) and [complete release and installed-migration acceptance](validation/2026-10-13-personal-access-release.md). Published 4.8.1 diversifies bounded candidate windows before limiting returned parts of each imported document; it adds no model call or re-index. [Focused source and evaluation checks](validation/2026-10-15-source-grouping.md) passed; representative capacity remains open. Source 4.14.0 bounds chronology to 2,048 units per revision and 250 candidates per search, with visible fallbacks and no additional model call or re-embedding. Representative live capacity measurements remain required. Source 4.43 adds [cooperative local inference and adaptive CPU batches](service/memory-resources.md#search-during-long-local-indexing), preserving admission, RAM and model ownership. [Seventy focused checks and one offline pinned-BGE comparison](validation/2026-10-20-inference-fairness.md) verify waiting-query progress and unchanged evidence/vector output; native delivery, live acceptance and broader capacity measurements remain. |
| R05 | Allow a small local model or approved cloud model to act as the memory librarian. | Shipped | [Librarian configuration, schedules, budgets, review and guarded undo](service/librarian.md). Models remain bounded by source evidence and permissions. |
| R06 | Make organization and verification useful and trustworthy, with explicit quality evidence. | Partial | Findings and proposals exist. Expand held-out quality evaluations, relationships, contradiction/staleness handling and calibrated verification; model output is not proof of truth. Source 4.14.0 adds [passage chronology, identifier-question support and comparable-match recency](service/retrieval.md), with [source and migration evidence](validation/2026-10-19-passage-chronology.md). Source dates and query coverage are not proof of truth; historical blame, ambiguous/undated corrections and broader held-out quality remain. Source 4.24 adds archive-aware recent ordering and a [measured real-model comparison](validation/2026-10-19-retrieval-archives.md) for current/historical and bilingual questions; no universal accuracy claim. |
| R07 | Continuously capture permitted raw experience and maintain layered episodic, knowledge, procedural and working memory with a model-driven librarian, statistical resurfacing, controlled retention and ongoing scientific/tool review. | Planned | [Research, architecture, Jev assessment and seven delivery slices](research/2026-10-20-layered-librarian.md) preserve the expanded 20 October requirement. Existing capture, proposals and model setup, the 4.40 [coverage/usage dashboard](service/librarian.md#coverage-and-processing), 4.41 [user/agent capture choices](service/live-conversations.md#choose-how-much-to-capture) and free weekly research watch are foundations; they do not complete autonomous cross-layer consolidation. Evidence, current permissions, resource limits, recovery and measured quality are required. Jev is an optional paid-provider candidate, disabled under the no-spending rule. |

## Visibility, design and knowledge maps

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| V01 | Provide a deep, visual graphics and statistics page for advanced monitoring. | Partial | [Six insights views](service/insights.md) exist; 4.2.5 adds separate managed-worker RSS, queue and cache gauges. Source 4.40 adds [librarian coverage and processing](service/librarian.md#coverage-and-processing), current-revision outcomes, pending age, 30-day calls/traffic and exportable data with matching agent access. Extend fleet, capture coverage, bandwidth and resource-policy views with measured data. |
| V02 | Include an evaluation system with useful comparisons, reproducibility and exports. | Partial | Datasets, runs, comparisons and case review exist. [4.3.3](validation/2026-10-14-question-retrieval.md) adds saved question/age/archive settings and execution-version tracking, with focused comparison checks and an explicitly reused public-corpus regression. Expand representative live model/provider/hardware baselines and failure/recovery drills. Published 4.8.1 records per-document retrieval limits and fixes [validation of narrowed excerpts from long sources](validation/2026-10-15-source-grouping.md), retaining hash and citation-bound checks. Native delivery and broader live baselines remain separate. Source 4.14.0 records recent/relevance ordering and its comparison threshold in app/API runs, with execution-version and retrieval-implementation evidence. A PostgreSQL evaluation compares strict-date and comparable-support outcomes. Source 4.24 supplies a repeatable 50-document/13-query real-model probe with per-case JSON, before/after indexing, and correct execution identity for queued evaluations. |
| V03 | Show memory relationships, topics, subjects, words, ideas and their supporting evidence. | Partial | [Wiki and graph](service/knowledge.md) exist. Extend relationships and terminology with provenance, ambiguity and uncertainty visible. |
| V04 | Provide a futuristic, useful, live **3D memory map**, online and in the app. | Partial | [Published in 4.0.10](service/memory-map.md): stable 3D orbit/zoom, full screen, filters/focus, clickable evidence, 20-second authorized refresh, bounded rendering and 2D/list fallback. [Browser, desktop and all six package gates passed](validation/2026-10-11-memory-map.md). Larger-scale clustering and incremental subscriptions remain. |
| V05 | Make agentic work understandable while watching the map. | Partial | Published 4.0.10 includes creator/time filters, administrator-visible person/app names and real reviewer-scoped creation/revision/review events. Keep event attribution separate from geometry. Extend the recent event window with replay, cross-space aggregation and capture coverage. |
| V06 | Match the Perseus XR website theme throughout the app. | Shipped | [Studio design system](STUDIO_DESIGN.md). Preserve readability, responsive layouts and accessibility for new screens. |
| V07 | Use the existing connected M logo everywhere and keep it readable. | Shipped | [Canonical logo and generated assets](BRANDING.md) ship in 4.0.10 across the browser, all six native packages, installers and system tray. The product page, homepage and Lab Notes use the same mark; native asset and live website checks passed. |
| V08 | Provide anonymous product telemetry for app and agent usage, performance, resources and bandwidth, enabled by default with clear disclosure and persistent user opt-out/re-enable. | Building | [Full contract](implementation/anonymous-product-telemetry.md): privacy controls, fixed aggregate measurements, owned workflow hooks, bounded transports and the dedicated collector are implemented in source. [Actual TLS, clean-runtime and isolated VPS checks](validation/2026-10-25-telemetry-collector-service.md) passed. No contents or stable identity/device tracking is permitted; company policy, bounded resources and full app/native-agent/web coverage remain required. Collection stays unavailable. Production ingress/privacy, representative client resources and wire measurements, useful reporting and all installed-platform/release acceptance remain open. The [closed-week volume follow-up](validation/2026-10-25-telemetry-weekly-volume.md) adds a 64-report global bucket, unchanged 4,096-per-view precision and immutable report-v1 reading; 67 scoped source checks passed. This is unverified contribution volume, not people or adoption. Production and complete V08 acceptance remain open. |

## Website, distribution and funding

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| W01 | Provide a proper live Perseus XR product page with simple downloads, benefits, setup and documentation. | Shipped | [Product page](https://www.perseusxr.com/mnemion). It offers verified published platforms. |
| W02 | Update the existing homepage Mnemion feature and link it to the product page. | Shipped | Homepage and Lab Notes point to the same product page; the shared logo is live. |
| W03 | Automatically update version numbers, downloads, notes and roadmap links. | Shipped | Release inventory, webhook and scheduled reconciliation maintain availability; normal hotfixes need no website edit/deployment. The 20 October [Git-owned website text extension passed live acceptance](validation/2026-10-20-git-owned-website-content.md), retaining all six published downloads while verifying the new Git content digest on all three surfaces without redeployment. The broader documentation request remains tracked under **U09** and the [documentation contract](website/README.md). |
| W04 | Recommend the visitor's OS/hardware while retaining clear manual download choices. | Shipped | Local browser hints, manual overrides, all six links and no-JavaScript/mobile fallbacks; ambiguous hardware is not guessed. |
| W05 | Keep Mnemion 100% free forever for individuals and organizations. | Ongoing | [Funding policy](SUPPORT.md). No paid tiers, seats or feature gates. |
| W06 | Offer optional PayPal support from €5, with higher amounts allowed. | Shipped | [Support policy](SUPPORT.md) and live product page. Support never changes access; payment-provider fees/settlement remain the provider's terms. |
| W07 | Use a free release/hosting/signing pipeline and incur no paid subscriptions, trials or certificates. | Ongoing | [Code-signing policy](CODE_SIGNING.md). Existing free infrastructure and independent update signatures; no spending authorization is inferred. |
| W08 | Complete Windows signing where free publisher approval is available and keep Mac software usable without paid enrollment. | External | SignPath sponsorship review remains external. Mac installation and independent signed updates exist; paid Apple publisher identity is not purchased. |
| W09 | Provide clear launch communication with the download link and remaining roadmap. | Shipped | Initial release communication was sent. Continue accurate public release notes; do not send repeat emails without a new instruction. |

## Current implementation queue

**Hotfix-first cadence:** prioritize a working base across connection/admin
access, installation, automatic updates, data safety and RAM stability. Ship
related verified fixes together, then advance the feature queue below. A passing
release does not close unfinished provider or recovery requirements.

**Active feature milestone:** V08 [anonymous product telemetry](implementation/anonymous-product-telemetry.md)
follows the accepted 4.46.5 paired update, custody, fresh backup and independent
restore. Local privacy controls are Building/source implementation; complete
measurement coverage, reviewed anonymity, bounded collection/transport and all
six native plus full web acceptance remain open. Urgent hotfixes and every
existing queue item remain in scope.

**19 October reports retained:** [issue 38](https://github.com/Perseusxrltd/mnemion/issues/38)
covers reproducible host installation/recovery after home or system-layer loss,
off-host state/key custody, restored update/remote configuration and clearer
connector setup errors. It advances the existing access/continuity and lifecycle
requirements rather than creating a replacement organization silently.
[Issue 39](https://github.com/Perseusxrltd/mnemion/issues/39) requests opt-in additive
Git journals for native saves, scanning hooks, scheduled/urgent delivery, librarian
folding and stable replay. It is retained under sources/continuity with explicit
permission, deletion, provenance and secret-exclusion requirements. The existing
import connectors remain one-way. Source [4.15.0](releases/4.15.0.md) implements
the separate opt-in [journal path](service/git-journal.md), with transactional
capture, scoped publication, app/SDK/agent controls and source replay. It advances
F08, C01/C08, A12/A13 and U01. Source [4.16.0](releases/4.16.0.md) adds scheduled
filing into Markdown, intact archival, deletion-safe derived views and the
matching app/SDK/agent controls, with [focused validation](validation/2026-10-19-journal-filing.md).
Complete app enrollment,
large-history/provider acceptance and writable-space reconstruction remain open.
The strict complete-requirement count stays **17/64 (26.6%)**.

**19 October capture follow-ups retained:** [issue 40](https://github.com/Perseusxrltd/mnemion/issues/40)
requests Grok Build's native ACP normalization; 4.16.0 adds its bounded complete-file
parser and stable companions. [Issue 41](https://github.com/Perseusxrltd/mnemion/issues/41)
tracks live/large transcripts. Source 4.17.0 adds the dedicated
[live JSONL adapter](service/live-conversations.md): complete-record checkpoints,
bounded fragments/offsets, per-file scopes, rotation/removal, current access and
app/agent progress. Unchanged fragments retain exact revisions without body
uploads; older bytes are still verified when a file grows. This advances
C03/C07/C08 and V01 without claiming native plugin installation, fleet capacity
or complete cross-app capture. The strict count remains **17/64 (26.6%)**.
Issue 39's older external prototype now has a checked private import in source
4.25. Native enrollment still uses a separate prefix: importing available records
does not convert the original files into native catalogs or acknowledge delivery.

1. **Reported stabilization:** the [published 4.1.7 update-scheduler fix](validation/2026-10-13-managed-update-schedule.md)
   for suspended hosts (issue 33) passed source, native package, independent
   artifact, public-feed, live website and all six public automatic-upgrade checks.
   4.1.6 delivers Git commit-wide re-ingestion and managed scan
   label fixes (issue 30), MCP search defaults (24), connection migration guidance
   (23) and bounded version diagnostics (29). Published 4.2.2 closes exact-ID
   ranking issue 27. The 4.2.3 batch implements compact discovery/session options
   (25–26), match filters (28), and recency with per-file Git dates (31), with
   focused validation and normal release gates. Issue 31 was reopened with
   fresh 4.2.5 examples; [4.3.1](releases/4.3.1.md) adds bounded age/archive
   preferences with visible factors and a pure-relevance option.
   [4.3.2](releases/4.3.2.md) adds the last completed Git snapshot to app/API/host
   status for misleading bare-cache freshness (37), without revising unchanged files.
   Source [4.14.0](releases/4.14.0.md) adds passage chronology and identifier-question
   support for the latest 4.11.0 reproductions, plus recorded recent-order evaluations.
   Historical Git blame, ambiguous/undated history, authoritative contradiction
   handling and broader natural-language/model calibration remain open.
   Published 4.2.0 closes issue 35 with the matching-excerpt correction, after
   complete release and six-platform installed migration/recovery acceptance.
2. **Access and continuity:** A01–A09, A11–A13, C04–C07. Build on verified independent
   human access, personal sign-in/invitations and native reconnection; finish
   provider acceptance of the 4.3.0 hosted OAuth flow, company identity onboarding and independently
   managed remote access. Preserve tenant/space isolation and existing credentials.
3. **Native onboarding and hardware:** U01–U02, U04, R02–R04. Extend published
   local-runtime/RAM setup with broader hardware measurements, company-host onboarding, browser/desktop
   recovery journeys and fleet startup policy.
4. **Release reliability:** U05–U09, V07. Maintain the passing public update
   rehearsals, publish validated changes for every platform, and keep `main`,
   release evidence and documentation aligned.
5. **Connected capture:** C01–C09, R06. Finish per-provider capture, reconnect,
   exclusions, review and durable incremental synchronization with clear coverage.
6. **Live knowledge visibility:** V01–V05. Build the 3D/browser/desktop view on the
   authorized knowledge and activity contracts, then validate usefulness and
   hardware budgets with real workloads.

Dependencies can be advanced independently. An interruption may add or reorder
items; it must not erase unfinished work. If scope changes, retain the ID and
record what replaced it. Completion percentages must state their denominator
and distinguish source implementation, native validation and public delivery.

## Maintenance rule

For every release or material hotfix, update affected rows, the roadmap and the
release notes with evidence and remaining limits. New requests get stable IDs.
Provider integrations need separate evidence for protocol compatibility,
successful authentication, permitted reads/writes, capture behavior and a live
provider test. No row closes merely because an agent reports success.
