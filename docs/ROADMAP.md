# Mnemion product roadmap

Reviewed source distribution: **4.30.2**. Roadmap updated: **2026-10-20**.

Download from the [Perseus XR product page](https://www.perseusxr.com/mnemion).
[Release status](RELEASE_STATUS.md) and the [maintenance board](MAINTENANCE_STATUS.md)
update automatically. This page sets delivery order; the [64 requirements](PRODUCT_REQUIREMENTS.md)
preserve every requested outcome and its evidence.

Strict full-scope completion remains **17/64 shipped (26.6%)**: 41 partial,
2 planned, 3 ongoing and 1 external. Requirements differ greatly in size.
This measures complete requested capabilities, not time spent or the usability
of the released app. A hotfix does not finish a broader requirement.

## Current delivery checkpoint

- **4.30.2 source fixes Windows backup paths and protects agent setup files.**
  [Database tools accept long private backup paths](validation/2026-10-20-windows-backup-paths.md)
  without changing Windows settings; the app and agent status retain safe failure
  diagnostics. Configuration backups
  and staged replacements now receive explicit private ownership and permissions
  before writing. [Focused Linux and native Windows checks](validation/2026-10-20-agent-setup-private-files.md)
  preserve existing client policies, exact backups and unrelated files.

- **4.30.2 source includes server-backup recovery in the desktop app.** The
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
- **Issue 18 retains the remaining ChatGPT UI acceptance.** The
  [issue resolution plan](implementation/github-issues.md) records the current
  checks. General delegated OAuth issue 4 is closed. Remote-access issue 3 now
  has [reviewed acceptance and a verified 4.29 association](validation/2026-10-20-remote-access-issue.md)
  for automatic closure. Live managed-ngrok account/lifecycle testing remains
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

| Priority | Next outcome | Acceptance and requirements |
| --- | --- | --- |
| 1 | Remaining live connections | Actual supported ChatGPT registration, consent and tool list for #18; separate free ngrok account/lifecycle acceptance and named-agent plugins. The bounded remote-access and delegated-authentication reports have verified evidence. Preserve existing HTTPS, local and scoped-key paths. C04–C07, A05/A08. |
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
with real readiness checks and equivalent agent operations.

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
