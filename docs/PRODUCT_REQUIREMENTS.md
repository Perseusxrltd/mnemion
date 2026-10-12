# Complete product requirements

Updated **2026-10-12**. This is the persistent checklist for the Mnemion rebuild,
including additions made during implementation. The [roadmap](ROADMAP.md)
explains delivery order; this file preserves the complete requested scope.
The current published distribution and release evidence are linked there.

**Shipped** means an available, documented capability. **Partial** means useful
behavior is available but the complete request remains open. **Building** means
implementation or validation is underway, not released. **Planned** means the
requirement is retained without a completed implementation. **External** means
a provider or publisher prerequisite is unresolved. **Ongoing** identifies a
standing product or maintenance commitment. A passing prototype, mock
test or source commit is not a shipped feature.

## Foundation and compatibility

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| F01 | Study the entire existing repository; use MemPalace and comparable memory tools to inform an update or rebuild. | Shipped | [Study, evidence and architecture](research/2026-10-09-mnemion-study/README.md). Revisit comparisons when they inform a concrete decision. |
| F02 | One organized memory infrastructure for individuals, teams, applications and AI systems across providers and hardware. | Partial | [Shared platform](service/README.md) is available. Complete the access, hosting, onboarding and integration rows below. |
| F03 | Preserve valuable features from previous versions instead of losing them during the rebuild. | Partial | [V3 parity audit](implementation/v3-feature-parity.md) and [migration](service/migration.md). Continue native migration/recovery validation and explicitly record retained, replaced and deferred behavior. |
| F04 | Keep Obsidian compatibility for visualization and ordinary Markdown use. | Shipped | [Managed export, annotations and conflicts](../studio/README.md), [knowledge views](service/knowledge.md). All new graph/capture work must preserve this boundary. |
| F05 | Support Windows, macOS and Linux, including Intel/AMD and ARM hardware. | Partial | Six desktop distributions and their bundled local engine/database are published. [Installed setup/reopen and public updates passed on all six targets](validation/2026-10-11-v412-release.md). Restricted company devices and broader OS-version coverage remain open; Windows ARM currently uses the documented x64 backend. |
| F06 | Work on modest computers without requiring a GPU or a model on every client. | Partial | Remote clients require no local model. Published native setup includes small CPU profiles, automatic RAM budgets and pressure controls. Broader hardware measurements and explicit minimum requirements remain; an unsupported OS or unlimited data at fixed RAM is not promised. |
| F07 | Use durable, portable formats and a maintainable architecture that can evolve safely. | Partial | Versioned API, PostgreSQL, Markdown, source evidence and migration contracts exist. Continue upgrade compatibility, recovery and large-workspace tests. |
| F08 | Keep every required workflow usable end to end by agents as well as people. | Partial | [87 published operations, CLI and MCP](service/agent-control.md). Local status, RAM changes/repair and stopped-workspace API-port recovery also have operator commands. New sign-in, host and recovery workflows still need complete agent parity. |

## Sources, assistants and automatic capture

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| C01 | Handle memories and vault sources from Git, Google Drive, arbitrary clouds and company-managed storage. | Partial | [Folder, Git, Drive, Slack, rclone and custom adapters](service/connectors.md). Finish provider sign-in UX, live-provider validation and reconnect/removal coverage. Provider support and permissions must be explicit. |
| C02 | Connect company messaging and collaboration systems, including Slack. | Partial | Slack ingestion and access mapping exist. Expand messaging adapters, event delivery and their actual permission/retention contracts. |
| C03 | Gather conversations automatically across AI applications after the user or company enables capture. | Partial | [Watchers, hooks and export normalizers](service/capture.md) exist for selected sources. Finish native provider capture and coverage reporting; connecting MCP does not automatically expose a provider's full chat history. |
| C04 | Connect Anthropic/Claude, including relevant apps, plugins, MCP and capture paths. | Partial | Claude Code/Desktop MCP setup and Claude export normalization exist. Hosted sign-in, provider-specific packaging and live end-to-end capture remain open. |
| C05 | Connect OpenAI/ChatGPT/Codex and Dot through the supported apps/plugins and local or remote connection paths. | Partial | Codex setup and ChatGPT/Codex export normalization exist. Dot/plugin packaging, hosted OAuth and live provider acceptance remain open; see [current platform research](research/2026-10-11-agent-platforms.md). |
| C06 | Connect Grokbot through a supported plugin/connector and retain access independently of its model quota. | Planned | Generic authenticated HTTP/MCP works when its host is reachable. Build and validate the actual Grokbot connection/capture path and independent host ownership/recovery. |
| C07 | Support Hermes, OpenClaw and other agent platforms without inventing incompatible configuration. | Planned | [Current MCP/OAuth research](research/2026-10-11-agent-platforms.md). Add tested setup profiles and provider-specific instructions; generic MCP alone is not a completed native integration. |
| C08 | Offer a genuinely connected system with clear capture coverage, deduplication and source provenance. | Partial | Revisions, source identity, idempotent reconciliation and evidence exist. Show per-provider last capture, gaps, exclusions, failures and removal state. Never silently label partial imports complete. |
| C09 | Preserve access boundaries when several agents, people, devices and configurations share sources. | Partial | Tenant/space grants, mapped source access and leases exist. Complete individual hosted sign-in, policy-managed source approval and fleet tests. |

## Organization access, hosting and safety

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| A01 | Let an organization set up a workspace once and make joining straightforward for its users. | Partial | [Remembered desktop connections](service/workspaces.md) ship. Finish invitations, individual sign-in and guided organization setup. |
| A02 | Provide specific individual logins or an equivalent simple, secure sign-in, rather than shared administrator credentials. | Building | Design individual accounts, revocable sessions, invitation expiry and recovery; add company identity/SSO without removing scoped machine credentials. |
| A03 | Give administrators clear control over people, agents, permitted spaces and connections. | Partial | [People, applications, keys and space grants](service/organizations.md) exist. Add session/device visibility, consent, connection policy and independent recovery access. |
| A04 | Compartmentalize private, team, project and company memory in secured vaults. | Partial | Tenant/space authorization is enforced. Finish the app-managed encryption/key/backup experience; ordinary Obsidian exports remain plaintext and must be described accurately. |
| A05 | Make remote workspaces reachable through stable, supported connection options. | Building | HTTPS/API/MCP and proxy configuration exist. [Bounded connection diagnostics](service/connection-diagnostics.md) ship in 4.0.10; 4.0.12 adds protected-health compatibility and a [validated native fix for ngrok browser warnings and stale offline responses](validation/2026-10-11-workspace-gateway.md). Finish native remote setup, tunnel supervision, stable links and private-network options. [Issue 3](https://github.com/Perseusxrltd/mnemion/issues/3). |
| A06 | Keep access and configuration available when an agent is unavailable or out of tokens. | Partial | Independent human administration and provider operator wake were exercised without the original agent session; the actual Windows app reconnects as a separate administrator. Encrypted snapshot/ledger restoration passed, followed by [migration of the original host to managed 4.0.12](validation/2026-10-12-managed-workspace-upgrade.md), preserved keys/grants and repeated Windows checks. Finish the product-managed host inventory, recovery entry point and scheduled independent backups. A stopped computer still requires its host-management channel. |
| A07 | Provide an online workspace entry point and management UI as well as the desktop app. | Partial | Web Studio ships with the service. Finish company sign-in, invitations, connection status and management; use company-controlled hosting rather than requiring a central paid service. |
| A08 | Support hosted-agent OAuth and consent, including safe authorization, expiry and revocation. | Partial | The [optional trusted-issuer resource-server foundation](service/oauth.md) is published in 4.0.11, with discovery/challenges, bounded introspection and immutable, revocable individual bindings. Built-in personal/team sign-in, invitations/onboarding, actual PKCE/consent/registration/refresh flows, recovery/reauthorization and live-provider acceptance remain required. [Issues 4 and 18](https://github.com/Perseusxrltd/mnemion/issues/18). |
| A09 | Keep memories reliable, recoverable and auditable as hosts and providers change. | Partial | [Backups, recovery ledger and restored-access reconciliation](service/recovery.md) exist. Finish guided backup scheduling, host migration and independent disaster recovery. |
| A10 | Keep the repository clear, documented and safe to publish. | Partial | Public release inventories, license notices and secret/dependency checks exist. Repeat relevant checks on every release; no private endpoints, keys or personal account material in public evidence. |
| A11 | Let several authorized owners/admins govern the workspace independently of the agent that created it, with explicit levels of authority. | Partial | [Independent administrator setup](service/organizations.md), an organization roster without a content grant, named retirement and [final-admin protection](validation/2026-10-11-administrator-lockout.md) are published. A separate human administrator joined the original live workspace through the released Windows app and [reconnected after restart](validation/2026-10-11-v412-release.md). Finish sign-in/invitations, recovery-custodian policy and delegated host operators. Git access does not silently promote a memory key. |
| A12 | Keep administration and recovery understandable from another enrolled device when the primary agent, computer or tunnel is offline. | Partial | Version 4.0.11 adds [offline saved-workspace details](validation/2026-10-11-offline-workspace-details.md), including encrypted, dated role observations, locked/legacy states and fresh authorization on reconnection. The [continuity contract](implementation/workspace-continuity.md) still requires the independent entry point, registered hosts/backups, approved operator actions, agent parity and safe takeover without divergent writers. Joining does not imply a local replica. |
| A13 | Recover available memory from Git or any configured provider without confusing source copies with complete workspace backups. | Partial | Existing source ingestion and verified database restoration cover separate scopes. Finish guided inventory, backup/ledger verification, source-only recovery labeling and reconciliation of writes, permissions and deletion state. |

## Installation, lifecycle and updates

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| U01 | Complete installation and configuration from scratch through a simple app UI. | Partial | Published 4.0.11/4.0.12 include the local engine/database, workspace creation, CPU model setup, RAM controls and occupied-port recovery. [Installed save/search, shutdown and reopen passed on all six targets](validation/2026-10-11-v412-release.md). Company hosting, provider approval and complete backup recovery remain under the [app onboarding acceptance contract](implementation/app-onboarding.md). |
| U02 | Configure sources, agents, models, access, Obsidian, resources, backups and recovery from the app. | Partial | Published workspace screens include RAM-policy repair and [occupied API-port recovery](service/local-workspaces.md), with agent parity and preserved private state. Provider approval, remaining host operations and full backup recovery still need complete, resumable UI flows. |
| U03 | Run in the background and system tray/menu bar where supported. | Shipped | [Desktop lifecycle](service/updates.md). Linux shells without a tray retain an accessible minimized window. |
| U04 | Start automatically and recover after restart on every supported OS. | Partial | Desktop login startup, Unix service supervision and native local workspace automatic reopen are available. [Installed restart checks passed on all six targets](validation/2026-10-11-v412-release.md). Broader machine-boot, unattended server startup and fleet policy acceptance remain. |
| U05 | Enable automatic verified updates by default and restart safely without losing work. | Shipped | Verified updates are enabled by default in supported desktop packages. The unmodified public [4.0.11 → 4.0.12 upgrade/relaunch passed on all six targets](validation/2026-10-11-v412-release.md), completing the Linux stale-focus acceptance. Normal idle, draft and transfer guards remain. Older affected AppImages may need one normal Quit or current download; organization deployment policies and shared-server updates are separate. |
| U06 | Deliver hotfixes to shared servers as well as desktop clients. | Partial | [Managed Unix service patches](service/managed-updates.md) exist after explicit host adoption. The [original shared server now runs managed 4.0.12](validation/2026-10-12-managed-workspace-upgrade.md) with updates enabled after a verified migration. Source 4.0.13 shows separate app/server versions and a fresh authenticated check in Setup. Complete Windows/fleet/Compose policy, the next actual public-feed patch and migration-bearing upgrades. |
| U07 | Ship ready platforms promptly while validating the remaining platforms. | Shipped | [Release process](MAINTENANCE.md) publishes only complete verified installer/update sets and preserves already available targets. |
| U08 | Keep `main` current with tested work, monitor issues, and keep implementing through new user requests. | Ongoing | New requests extend this checklist and the active queue; they do not silently replace unfinished requirements. Preserve uncommitted work, commit validated milestones and record regressions. |
| U09 | Keep documentation, release notes, roadmap and in-app help current with updates. | Partial | Offline docs are generated from repository Markdown; release/version checks exist. Update affected requirement IDs, evidence and limitations in every relevant release. |
| U10 | Deliver an official first release, then continue improving the complete roadmap. | Partial | Shared-platform v1 is published as package series 4.x. The complete requested product remains in progress; a version label does not close this checklist. |
| U11 | Use the actual Windows installation as a connected, bounded stress-test client for the shared workspace and live automatic updates. | Partial | The actual Windows app is on 4.0.12 and reconnects to the original workspace as an individual human administrator with explicit Git reader access. [Update evidence](validation/2026-10-11-v412-release.md) distinguishes manual Check/Restart from unattended acceptance. The [isolated lab](validation/2026-10-12-workspace-administration.md) passed save/idempotency, indexing, lexical/semantic search, revision/conflict and deletion using a separate restricted key. After [live server migration](validation/2026-10-12-managed-workspace-upgrade.md), the cycle passed again with 40 requests and no production writes or cloud calls. Encrypted off-host backup, Windows decryption and isolated restoration also passed. Larger workloads, live patch observation and guided recovery remain. |

## Models, RAM and memory bandwidth

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| R01 | Offer current, optimized embedding models and meaningful user choice. | Partial | [Pinned CPU and approved remote profiles, candidate indexing and rollback](service/embeddings.md). Continue measured model/language/domain comparisons; no universal “best model” claim. |
| R02 | Adapt resource use to the hardware, especially available RAM. | Partial | Automatic local working budgets, pressure-aware admission, smaller batches and idle unloading are published with the native runtime. Six installed local-workspace gates passed. Broader actual minimums, hardware measurements and fleet resource policy remain. |
| R03 | Let both users and agents change Mnemion's RAM allocation at any time. | Shipped | Published [app and local operator controls](service/local-workspaces.md) change the persisted local working budget, expose current policy and repair invalid settings. [Native policy recovery](validation/2026-10-11-native-policy-recovery.md) and all six installed gates passed. This is a cooperative application budget, not an OS memory reservation or a universal remote-host limit. |
| R04 | Treat memory bandwidth, ingestion, retrieval and concurrency as part of the core pipeline. | Partial | Bounded requests, ingestion limits, leases, context budgets and inference admission exist. Finish representative throughput, queue, working-set and recovery measurements. |
| R05 | Allow a small local model or approved cloud model to act as the memory librarian. | Shipped | [Librarian configuration, schedules, budgets, review and guarded undo](service/librarian.md). Models remain bounded by source evidence and permissions. |
| R06 | Make organization and verification useful and trustworthy, with explicit quality evidence. | Partial | Findings and proposals exist. Expand held-out quality evaluations, relationships, contradiction/staleness handling and calibrated verification; model output is not proof of truth. |

## Visibility, design and knowledge maps

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| V01 | Provide a deep, visual graphics and statistics page for advanced monitoring. | Partial | [Six insights views](service/insights.md) exist. Extend fleet, capture coverage, bandwidth and resource-policy views with measured data. |
| V02 | Include an evaluation system with useful comparisons, reproducibility and exports. | Partial | Datasets, runs, comparisons and case review exist. Expand representative live model/provider/hardware baselines and failure/recovery drills. |
| V03 | Show memory relationships, topics, subjects, words, ideas and their supporting evidence. | Partial | [Wiki and graph](service/knowledge.md) exist. Extend relationships and terminology with provenance, ambiguity and uncertainty visible. |
| V04 | Provide a futuristic, useful, live **3D memory map**, online and in the app. | Partial | [Published in 4.0.10](service/memory-map.md): stable 3D orbit/zoom, full screen, filters/focus, clickable evidence, 20-second authorized refresh, bounded rendering and 2D/list fallback. [Browser, desktop and all six package gates passed](validation/2026-10-11-memory-map.md). Larger-scale clustering and incremental subscriptions remain. |
| V05 | Make agentic work understandable while watching the map. | Partial | Published 4.0.10 includes creator/time filters, administrator-visible person/app names and real reviewer-scoped creation/revision/review events. Keep event attribution separate from geometry. Extend the recent event window with replay, cross-space aggregation and capture coverage. |
| V06 | Match the Perseus XR website theme throughout the app. | Shipped | [Studio design system](STUDIO_DESIGN.md). Preserve readability, responsive layouts and accessibility for new screens. |
| V07 | Use the existing connected M logo everywhere and keep it readable. | Shipped | [Canonical logo and generated assets](BRANDING.md) ship in 4.0.10 across the browser, all six native packages, installers and system tray. The product page, homepage and Lab Notes use the same mark; native asset and live website checks passed. |

## Website, distribution and funding

| ID | Requested outcome | State | Evidence and remaining acceptance |
| --- | --- | --- | --- |
| W01 | Provide a proper live Perseus XR product page with simple downloads, benefits, setup and documentation. | Shipped | [Product page](https://www.perseusxr.com/mnemion). It offers verified published platforms. |
| W02 | Update the existing homepage Mnemion feature and link it to the product page. | Shipped | Homepage and Lab Notes point to the same product page; the shared logo is live. |
| W03 | Automatically update version numbers, downloads, notes and roadmap links. | Shipped | Release inventory, webhook and scheduled reconciliation maintain availability; normal hotfixes need no website edit/deployment. |
| W04 | Recommend the visitor's OS/hardware while retaining clear manual download choices. | Shipped | Local browser hints, manual overrides, all six links and no-JavaScript/mobile fallbacks; ambiguous hardware is not guessed. |
| W05 | Keep Mnemion 100% free forever for individuals and organizations. | Ongoing | [Funding policy](SUPPORT.md). No paid tiers, seats or feature gates. |
| W06 | Offer optional PayPal support from €5, with higher amounts allowed. | Shipped | [Support policy](SUPPORT.md) and live product page. Support never changes access; payment-provider fees/settlement remain the provider's terms. |
| W07 | Use a free release/hosting/signing pipeline and incur no paid subscriptions, trials or certificates. | Ongoing | [Code-signing policy](CODE_SIGNING.md). Existing free infrastructure and independent update signatures; no spending authorization is inferred. |
| W08 | Complete Windows signing where free publisher approval is available and keep Mac software usable without paid enrollment. | External | SignPath sponsorship review remains external. Mac installation and independent signed updates exist; paid Apple publisher identity is not purchased. |
| W09 | Provide clear launch communication with the download link and remaining roadmap. | Shipped | Initial release communication was sent. Continue accurate public release notes; do not send repeat emails without a new instruction. |

## Current implementation queue

1. **Access and continuity:** A01–A09, A11–A13, C04–C07. Build on verified independent
   human access and native reconnection; finish individual sign-in and hosted
   OAuth, administrator invitations, provider setup and independently managed
   remote access. Preserve tenant/space isolation and existing credentials.
2. **Native onboarding and hardware:** U01–U02, U04, R02–R04. Extend published
   local-runtime/RAM setup with broader hardware measurements, company-host onboarding, browser/desktop
   recovery journeys and fleet startup policy.
3. **Release reliability:** U05–U09, V07. Maintain the passing public update
   rehearsals, publish validated changes for every platform, and keep `main`,
   release evidence and documentation aligned.
4. **Connected capture:** C01–C09, R06. Finish per-provider capture, reconnect,
   exclusions, review and durable incremental synchronization with clear coverage.
5. **Live knowledge visibility:** V01–V05. Build the 3D/browser/desktop view on the
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
