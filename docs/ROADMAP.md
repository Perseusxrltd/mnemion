# Mnemion product roadmap

Current distribution: **4.0.9**. Updated: **2026-10-11**.

Version 4.0.9 adds OS-encrypted saved desktop connections, authenticated
reconnection after app restart, durable disconnect, device-only forgetting and
clear session choices. The complete native/product gates are required before
publication; the product page continues to select only published builds.

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
known limitations are recorded in [the current patch notes](releases/4.0.9.md),
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

## Implemented for the first shared-platform release

| Area | Available behavior | Documentation |
| --- | --- | --- |
| Shared memory | PostgreSQL transactions, tenant/space boundaries, scoped agent identities, revision history, durable receipts and deletion | [Service](service/README.md), [organizations](service/organizations.md) |
| Retrieval | Pinned local multilingual E5, lexical and semantic search, cited context, chunk/index identity and bounded context packs | [Service](service/README.md) |
| Model choice | E5/BGE CPU profiles, approved Ollama/OpenAI endpoints, per-space candidate indexes, progress/pause/retry, preview/evals and atomic activation/rollback | [Embedding models](service/embeddings.md) |
| Librarian | Approved local/cloud models, optional schedules, call budgets, exact source revisions, organization proposals, review findings and guarded undo | [Librarian](service/librarian.md) |
| Sources | Git, selected folders, Google Drive, Slack, rclone and custom adapters; immediate sync requests, timestamped results, checkpoints, leases, review proposals and pauses | [Connectors](service/connectors.md) |
| Agent compatibility | HTTP/OpenAPI, Python/TypeScript SDKs, authenticated MCP, 84-operation discovery and CLI/MCP administration, bounded private results, safe retries, conversation capture | [Agents](service/agents.md), [administration](service/agent-control.md), [capture](service/capture.md) |
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

This is **not complete in 4.0.9**: the desktop client joins an existing service;
database/runtime installation and several host-only settings still need operator
setup. Secure resumable connections are implemented in 4.0.9 and require the
native release gate. Native runtime provisioning and guided host operations
remain the next implementation steps. See the [full acceptance requirements](implementation/app-onboarding.md).
Do not count a setup guide, mock success or disabled button as an implemented flow.

## Next patches: reliability and operational confidence

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
  rollouts, maintenance windows and migration-bearing upgrades (11). Verify a
  public service-feed upgrade after its first signed baseline is published.
  Rehearse the 4.0.7 supervision setup (6) and 4.0.6 bundled Studio (7) in existing
  deployments, including their actual boot, network and database startup order.
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
  Separate API/worker model caches and idle unloading remain open. Review policy for an author's
  own deletions (14), improve source-space onboarding (8), extend 4.0.5's durable
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
