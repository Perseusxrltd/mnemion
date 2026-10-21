# Mnemion product roadmap

Reviewed source distribution: **4.44.0**. Roadmap updated: **2026-10-21**.

Download from the [Perseus XR product page](https://www.perseusxr.com/mnemion).
[Release status](RELEASE_STATUS.md) and the [maintenance board](MAINTENANCE_STATUS.md)
update automatically. This page sets delivery order; the [65 requirements](PRODUCT_REQUIREMENTS.md)
preserve every requested outcome and its evidence.

Strict full-scope completion remains **17/65 shipped (26.2%)**: 42 partial,
2 planned, 3 ongoing and 1 external. Requirements differ greatly in size.
This measures complete requested capabilities, not time spent or the usability
of the released app. A hotfix does not finish a broader requirement.

Every release starts with current GitHub reports from real deployments. Batch
the ready fixes and add a verified roadmap improvement when possible; urgent
repairs take precedence. Preserve failed reports and unfinished scope until
their actual acceptance passes. The [release process](MAINTENANCE.md) keeps
issue review, publication and version-linked closure together.

## Current delivery checkpoint

- **Durable conversation capture is in development, not yet released.**
  The [implementation checkpoint](research/2026-10-21-durable-capture-implementation.md)
  records encrypted local intake before network delivery, current permission and
  forgetting checks, persistent app/agent observations, and explicit retirement
  when a device key is lost. Encrypted prefix accounting now distinguishes
  selected, omitted and unsupported lines, retained history gaps, queue age and
  confirmed workspace contact in development source. Bounded, resumable source
  index sweeps now report text/vector indexing, waiting, failed, withheld,
  forgotten and unknown events under the observed model generation. App and
  agents now share explicit capture presets, filename filters, size/retention
  choices and a bounded local preview. Saved status preserves unknown values;
  recovery ledgers preserve the approved policy. Source and migration checks
  passed. The Linux app source journey passed preview, enrollment, offline
  intake, restart, delivery and administrator-assisted removal; its evidence is
  separate from the later policy-recovery checks. Portable encrypted inbox
  export and inspection now have a Linux app/agent journey covering offline
  export, restart and inspection after source removal; bounded archive and
  migration checks passed. New-device recovery now retains the original source
  and capture policy, rotates the protected inbox key and grant, confirms old
  grant retirement, and installs a paused source. App and agent controls expose
  pending recoveries with explicit finish/discard; component/controller checks
  passed. The final Linux source journey now covers app recovery, reopening the
  new protected key after restart, reconciling old queued memories without
  duplicates and capturing new memories. Three earlier UI/controller failures
  and their corrections remain in the validation record. The independent
  [headless source journey](service/headless-capture.md) now covers explicit
  enrollment, offline intake, interrupted-process recovery, pause/resume,
  encrypted backup and new-grant recovery. Its CLI, protected-file, resource,
  managed-runner and shared desktop regressions passed, along with migration
  and updater checks. Bounded disk cleanup now returns unused database pages
  while preserving every capture record, receipt and deletion fence. App and
  agent status report actual reclaimed space and any deferred cleanup; retained
  history limits remain explicit. A new [bounded backfill delta](research/2026-10-21-durable-capture-implementation.md#bounded-retained-backfill-source-delta)
  saves verified prefixes at existing fragment boundaries and resumes unchanged
  files on later scans. The app now labels verified partial progress **Backfilling**
  and preserves prior success/failure observations and the next scan time.
  Focused source/controller and migration checks, the app/documentation build
  and an isolated Linux intake measurement passed; all 12 CI jobs passed on `763a8341`.
  A further [unreleased source batch](research/2026-10-21-durable-capture-implementation.md#connection-intake-budget-and-rotation-source-delta)
  adds cooperative connection-wide intake budgets, encrypted rotation across
  file attempts and a five-second follow-up for healthy unfinished intake or delivery.
  Scoped service/controller and migration checks plus the real headless watcher
  passed. Current full CI, coordination across separate connections/devices and
  full-history acceptance remain open; that scheduling delta leaves event and scope caps unchanged.
  A separate [deletion-at-capacity correction](research/2026-10-21-durable-capture-implementation.md#deletion-fences-and-history-limits-source-delta)
  now preserves held-data forgetting above lowered quotas and pauses intake when
  additional deletion history cannot fit. App/headless history usage and local
  quota controls are implemented; 167 distinct focused service cases, 77 native
  controller cases and 30 migration checks are qualified after four reproduced
  failures. This batch also corrects the preceding CI's memory/speed-dependent
  test assumptions without changing product limits. All 12 CI jobs passed for
  that correction on `c18a439c`; later source and packaged acceptance remain
  separately observed. The native boundary gate now covers incomplete Unicode,
  rotation gaps, a lost commit reply, current reader/policy revocation and
  fragment-family forgetting through two real app launches. Its Linux source
  preview passed 19 checks. The [independent engine lifecycle](research/2026-10-21-durable-capture-implementation.md#independent-native-engine-capture-lifecycle)
  adds `connect` to the service and bundled-engine CLI, with a 13-check Linux
  source journey for offline process restarts, protected inbox failures,
  encrypted recovery and later deletion fences. The 20 CLI/control cases and
  30 migration checks passed. The [damage-control correction](research/2026-10-21-durable-capture-implementation.md#damaged-inbox-controls-and-lightweight-client-correction)
  preserves pause and accepted evidence with missing or damaged enrollment or
  inbox files; the expanded Linux source journey passed 24 checks. The first
  six-target run failed before packaging on a shared client import; the corrected
  locked client suite passed 235 cases with 13 platform skips and now runs in
  ordinary CI. All 12 CI jobs passed on `d9b40cca`; the next six-target run
  reached installed hosting but failed before capture enrollment completed.
  The [new source batch](research/2026-10-21-durable-capture-implementation.md#json-field-exclusions-and-installed-capture-navigation)
  corrects capture navigation after the packaged Help check and adds optional
  literal JSON field exclusions, preserving old policy fingerprints and
  encrypted archive/recovery bindings. Focused field, service, native controller
  and migration checks passed. The Linux source journey passed 31 checks across
  three real app launches, including field exclusions through archive recovery
  and the corrected Help-to-workspace transition.
  All 12 ordinary CI jobs passed on `8aacc859`. The subsequent six-target run
  completed the installed journeys on both Linux architectures and Apple
  Silicon, but failed on both Windows targets and Intel macOS. The
  [saved-key control batch](research/2026-10-21-durable-capture-implementation.md#saved-key-controls-and-platform-validation)
  preserves inspect/pause and administrator retirement when saved credentials
  are lost, without replacing accepted evidence or restoring cached keys to
  disk. Exact-key recovery also refreshes that source's matching saved queue
  observations while it stays paused. Its 80 service, 88 controller and 30
  migration checks passed. The native probe's Windows credential-backend
  mismatch is corrected; Intel Mac connector
  diagnostics are improved while its failure remains unresolved. The expanded
  Linux source boundary preview passed all 29 checks across two app launches;
  all six current-source packaged targets remain pending. The prior policy
  checkpoint's failed health-response CI and its later test correction
  remain recorded. This remains unreleased source. Reviewed identity/policy
  migration, complete capture policy and coverage, headless installed acceptance,
  bounded history and all six packaged targets remain required before L1 ships.

- **4.44 is published and accepted on the actual Windows app and shared host.** Certifi 2026.10.19 and
  Pillow 13.0.0 address the reported dependency advisories while preserving the
  pinned text models. [Dependency and offline E5/BGE validation](validation/2026-10-21-security-dependencies.md)
  passed within its recorded scope. All six native targets, artifact verification
  and public update checks passed; the website synchronized automatically.
  [Paired acceptance](validation/2026-10-21-444-acceptance.md) confirmed ordinary
  4.43→4.44 updates, retained identities/login/bookmarks/preferences and 50 isolated
  lab requests with complete cleanup. Unattended idle restart remains unproven.
  This is a standalone security hotfix; capture/L1 delivery and all requirement
  statuses remain unchanged.

- **4.43 is published and accepted on the actual Windows app and shared host.**
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
