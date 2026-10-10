# Mnemion product roadmap

Current distribution: **4.0.0**. Updated: **2026-10-10**.

The rebuilt shared-memory platform is product v1; its package version is 4.0.0
to upgrade correctly from the earlier 3.x product. This is a living delivery
plan, not a claim that every planned capability is available. Release status and
known limitations are recorded in [the release notes](releases/4.0.0.md) and
[validation report](validation/2026-10-10.md).

## Product direction

One organized, evidence-backed memory system for people, teams, applications and
agents across devices and providers. Companies control where the service runs,
which sources are connected, who can recall each space, and what leaves their
infrastructure. Obsidian remains a portable visualization and annotation surface.

The server owns shared consistency and indexing. Desktop clients stay small and
can connect to an organization server without downloading an embedding or
language model. Resource limits must be explicit; memory capacity depends on the
server configuration rather than every employee owning a powerful computer.

## Implemented for the first shared-platform release

| Area | Available behavior | Documentation |
| --- | --- | --- |
| Shared memory | PostgreSQL transactions, tenant/space boundaries, scoped agent identities, revision history, durable receipts and deletion | [Service](service/README.md), [organizations](service/organizations.md) |
| Retrieval | Pinned local multilingual E5, lexical and semantic search, cited context, chunk/index identity and bounded context packs | [Service](service/README.md) |
| Model choice | E5/BGE CPU profiles, approved Ollama/OpenAI endpoints, per-space candidate indexes, progress/pause/retry, preview/evals and atomic activation/rollback | [Embedding models](service/embeddings.md) |
| Sources | Git, selected folders, Google Drive, Slack, rclone and custom adapters; checkpoints, leases, review proposals and pauses | [Connectors](service/connectors.md) |
| Agent compatibility | HTTP/OpenAPI, Python and TypeScript SDKs, MCP stdio and HTTP, conversation capture | [Agents](service/agents.md), [capture](service/capture.md) |
| Human organization | Studio memory review, source evidence, team access, wiki/graph, core context and operations | [Knowledge](service/knowledge.md) |
| Obsidian | Markdown, stable paths, citations, wikilinks, managed refresh, conflict detection and preservation of personal annotations | [Studio](../studio/README.md) |
| Reliability | Durable jobs, retries and leases, ingestion/resource limits, verified backup/recovery, v3 archive/import/cutover/rollback | [Recovery](service/recovery.md), [migration](service/migration.md) |
| Observability | Six visual insight views, private evaluation sets and runs, comparisons, case inspection and exports | [Insights and evaluations](service/insights.md) |
| Desktop lifecycle | Background operation, login startup, update preferences and safe idle restart; updater enabled by default in supported packages | [Updates](service/updates.md) |
| Documentation | In-app offline library generated from repository Markdown, version-specific notes and this roadmap | [Maintenance](MAINTENANCE.md) |

Implementation does not by itself certify every deployment. Provider tests use
fixtures unless a validation report explicitly identifies a live test. Native
release artifacts require the platform checks and publisher requirements below.

## Release completion gates

1. Pass service, legacy, SDK, security and frontend checks on the release commit.
2. Build and launch native desktop packages on Windows, macOS and Linux, for
   x64 and ARM64, including their sandboxed bridges and local Obsidian client.
3. Supply valid Windows publisher and Apple Developer ID/notarization credentials.
   Unsigned validation packages are not production automatic-update releases.
4. Rehearse a signed upgrade, rollback/recovery, startup and safe restart. Record
   the environments and results rather than inferring them from compilation.
5. Verify all immutable artifacts, architecture-specific feeds, inventories,
   checksums, release notes and public repository hygiene before publication.
6. Publish the matching Perseus XR product page with simple platform downloads,
   setup guidance, release notes and roadmap links. Download buttons must target
   the verified published release; drafts and validation builds are not downloads
   for end users.

Missing credentials or failed platform checks remain release blockers; the
release notes must state the actual shipping status.

Release operations have a no-spend constraint: do not buy certificates, enroll
in paid programs or start trials that convert to paid subscriptions. Evaluate
free open-source signing and sponsorship without claiming approval in advance.
The standard Apple Developer ID program is paid; without an eligible free route,
trusted macOS signing/notarization and its production automatic updates remain
blocked. Keep source, web and local development paths documented. See the
[code signing policy](CODE_SIGNING.md).

## Next patches: reliability and operational confidence

Priority is defects found in installation, access control, recovery, migration,
update behavior and routine team use. Patches retain the service/API contract
where possible and include migration/rollback instructions when needed.

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

An optional local or cloud language model will propose organization and hygiene
work: titles, tags, links, duplicates, contradictions, stale facts and summaries.
This shared-service librarian is planned; legacy curation tools are not evidence
that an autonomous organization-wide librarian is finished.

- Assign any supported model/provider within administrator policy; expose its
  context, memory, token/cost and scheduling limits.
- Use bounded jobs and evidence-linked proposals with provenance, confidence and
  reproducible configuration. Start with human review for substantive changes.
- Separate model suggestions from authoritative facts. Treat source instructions
  as untrusted input; tools obey the same access boundaries as ordinary agents.
- Provide dry runs, queues, diffs, approvals, undo, cancellation and audit history.
- Never allow a librarian to grant access, remove evidence or bypass deletion and
  review policy just because generated text requests it.

Acceptance: measurable usefulness, reliable undo, adversarial-input tests,
permission isolation and explicit resource/egress budgets.

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
