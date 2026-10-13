# Mnemion product roadmap

Reviewed source distribution: **4.1.7**. Roadmap updated: **2026-10-13**.
The [current published distribution and release gates](RELEASE_STATUS.md) are updated automatically.
The [official product page](https://www.perseusxr.com/mnemion) lists verified
published downloads; source and release preparation can precede publication.

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
Complete password and company sign-in, hosted consent and live provider
acceptance remain required.

The immediate priority is short hotfix releases for operational reliability:
connections and administrator access, installation, verified updates, data safety
and resource stability. Broader features follow without removing requirements
from the checklist. The remaining reported stabilization work includes MCP
client/discovery compatibility and measured retrieval quality: exact identifiers,
relevance, natural-language queries and recency. Version 4.1.6 delivers the
reported Git revision/scan-label, MCP default-scope, version-diagnostic and
connection-guidance fixes.
The separate encrypted secrets-vault request is retained under A04; it must
never enter ordinary memory search, capture or model context.
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
The complete app-only setup requirement remains **partial**: organization
hosting, provider approval and full backup recovery remain open. See the
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
- Complete hosted-agent OAuth with PKCE and consent (issues 4 and 18), native
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
  independently deployed API/worker processes still need shared model serving
  and peak-memory measurements. Scoped author withdrawal (14) passed all six
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

Planned extensions include company identity/SSO and lifecycle provisioning,
policy-managed devices and updates, stronger audit export/retention, managed
secrets, organization quotas and shared source ownership. Evaluate encrypted
archive/vault storage and customer-managed keys with explicit recovery and search
tradeoffs. End-to-end encrypted searchable memory is not a current promise.

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
