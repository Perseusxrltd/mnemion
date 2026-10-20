# Mnemion v4 implementation status

For current delivery priorities and publication status, use the
[product roadmap](../ROADMAP.md), [complete requirements](../PRODUCT_REQUIREMENTS.md)
and [published downloads](https://www.perseusxr.com/mnemion).
This chronological ledger also retains earlier checkpoints and the broader
program acceptance criteria; historical counts are not final-version results.

Objective: deliver a professional shared memory product for applications, teams,
assistants, and programs, retaining Obsidian visualization. The objective remains
active until the implementation and release gates are verified.

The user additionally requires full macOS, Windows, and Linux compatibility.
Native packaging, window behavior, local Obsidian refresh, installation/update
instructions, and platform validation are release requirements for all three.

Requirements and acceptance criteria are defined by the
[study](../research/2026-10-09-mnemion-study/README.md),
[architecture](../research/2026-10-09-mnemion-study/ARCHITECTURE.md), and
[roadmap](../research/2026-10-09-mnemion-study/ROADMAP.md).

## 20 October: operator turns, corrected container and scientific watch

Source 4.39 supersedes the unpublished 4.38 candidate after both container gates
found a missing canonical branding asset. It carries all native connector work,
supplies the Docker input, and adds a bounded operator wait for the continuous
source-scan contention observed in issue 45. Entered upgrade operations are
never replayed by the wait. [Source validation](../validation/2026-10-20-operator-turn-research.md)
retains the failure and distinguishes publication from actual deployment.

The expanded [layered-librarian research contract](../research/2026-10-20-layered-librarian.md)
preserves the 20 October request as R07, with seven stages and Jev assessed as an
optional paid decision provider. A free weekly metadata watch supplies dated
candidates without model calls or automatic dependency adoption. R07 remains
planned: current strict scope is 17/65 shipped (26.2%), 42 partial, two planned,
three ongoing and one external. Earlier counts below are dated checkpoints.

## 20 October: native named clients and new deployment reports

Source 4.38 implements native Hermes YAML/OpenClaw JSON5 setup and a common
Perseus XR [connection-package generator](../service/agent-packages.md) for app,
API, SDKs and CLI. Focused configuration/API tests and actual Windows Grok Build
1.0.62 and Claude Code 2.1.59 manifest validation passed. An observed older-Claude
icon-field incompatibility was corrected before publication. Broader provider
runtime/capture and directory publication remain explicit.

The watcher detected new issues 44 and 45 after issue 18 closed. The
[issue plan](github-issues.md) keeps the real Bot cloud and guarded shared-host
acceptance open. The original failed backup/lab evidence and deliberately paused
PC note publisher are preserved. A service-ready report does not establish
fresh local-note delivery. C07 moves to partial; strict completion stays 17/64.

## 20 October: actual ChatGPT acceptance and native integration requirements

[Signed-in ChatGPT acceptance](../validation/2026-10-20-chatgpt-acceptance.md)
passed against the actual 4.33 host: OAuth registration, personal login, explicit
consent with existing account/space roles, installation, 16 discovered tools and
an authenticated profile-only request. This supplies issue 18's missing client
proof; earlier restricted-reader protocol evidence remains separate.

All six 4.37 native gates, public artifact verification, automatic website
synchronization and all six public-feed update rehearsals passed. The private
shared-host upgrade stopped before migration when its snapshot wrapper hit a
ten-minute timeout, then encountered a managed-operation lock. These retained
failures are maintenance work, not a passed live upgrade.

The user reaffirmed native agent setup for every workflow and named Grok/Grokbot,
Claude, Hermes, OpenClaw and OpenAI/Codex/Dot integrations. All distributed
connectors/apps/plugins must be authored by **Perseus XR**. The [native setup
contract](../service/agent-setup.md) and [publisher rules](../BRANDING.md#connector-and-plugin-authorship)
retain these requirements without marking unfinished named clients complete.
Strict broad-scope coverage stays 17/64 (26.6%).

## 20 October: agent-controlled desktop connections and hosted sign-in

Source 4.37 combines the following queue milestones with a
[private settings publication correction](../validation/2026-10-20-state-publication.md).
The Windows ARM installed-setup gate blocked 4.35; the same failure was
reproduced on native Windows, and 12 Linux/14 Windows state checks passed with
the correction. The 4.36 queued build was cancelled. Neither candidate was
published; their changes are retained together in 4.37. No real-host migration
was started by the stopped publication-waiting controller.

Source 4.36 adds workload visibility to the existing insights contract. Six
database/permission tests and a real browser against PostgreSQL passed: the
screen distinguishes physical purge from embedding, excludes another space's
large input, reports backoff/lease state and UTF-8 size accurately, fits a narrow
screen and keeps the original queue view against an older response. The short
snapshot cache and access recheck remain. Native publication and live capacity
are separate; see [validation](../validation/2026-10-20-queue-visibility.md).

The 4.35 source prioritizes physical purge and gives organizations/spaces
persistent indexing turns. It follows the [actual 4.33 lab backlog](../validation/2026-10-20-433-live-updates.md):
both ordinary updates preserved access, but a queued synthetic cycle did not
pass and retained cleanup. [Eighteen dispatch/reindex cases](../validation/2026-10-20-fair-indexing.md)
passed, including restart, tenant fairness, concurrent claims, unavailable
models and API-role denial. The new schema migration is not applied to the live
host at this checkpoint. Original failed lab evidence remains preserved.

The 4.34 source advances app-managed cloud capture: selected Slack channels and
Drive resources, separate OS-protected provider credentials, read-only Google
service-account token renewal, actual provider permissions and private-agent
controls. [Focused service/controller checks and the real source-app walkthrough](../validation/2026-10-20-desktop-cloud-sources.md)
passed. The app captured fixture records through both adapters without a local
database, recovered from a bad key, retained encrypted keys for agent changes
and removed sources while signed out. The walkthrough also found and fixed a
connection-selection flag that unnecessarily blocked automatic updates. All six
4.34 native gates and uploaded-artifact verification passed; publication followed
at 08:27 UTC. All six public update rehearsals subsequently passed at 08:39 UTC;
actual customer-provider acceptance remains separate.

The 4.33 model-provider release passed all six native targets and independent
artifact verification and is published. Its website update completed
automatically. Public installer updates and actual shared-host/Windows update
receipts remain distinct checks; [release status](../RELEASE_STATUS.md) records
the public workflow. Strict full-scope coverage remains 17/64 (26.6%).

Source 4.28 adds nine private desktop operations for selecting key/password team
accounts, inspecting and reopening saved connections, disconnecting/forgetting
and returning to the running local host. It requires current selection revisions,
checks intended key identities before activation, retains OS-protected storage
and shares the app's draft and mutation controls. The copied agent setup includes
connection discovery. [47 focused cases](../validation/2026-10-20-desktop-workspace-control.md)
passed; native installation/selection acceptance remains a publication gate.

The existing 4.17 shared host was separately configured for built-in OAuth after
its public discovery endpoints returned 404. [Actual public HTTPS acceptance](../validation/2026-10-20-live-hosted-signin.md)
verified reader consent, MCP access, rotation and immediate revocation, preserving
both existing agent credentials and the original memory. The temporary identity
was disabled and a fresh encrypted snapshot/ledger was verified off-host. This
was a later live configuration change, after the isolated recovery drill below;
it does not establish signed-in ChatGPT acceptance or restore the missing office.
Strict requirement coverage remains 17/64 (26.6%).

## 19 October: replacement-host acceptance and portable backups

Source 4.27 fixes the locale-dependent keyword-index mismatch discovered when
restoring an independently downloaded encrypted Git backup on a different PC.
[The complete drill](../validation/2026-10-19-portable-host-recovery.md) retained
all 69 original table hashes with the explicit legacy locale, then verified a
new portable snapshot across locales. The actual installed candidate retained
the existing Codex/Grok credentials, exact UTF-8 memories and later denials.
Ubuntu and native Windows API/MCP calls and a service restart passed; all isolated
processes were stopped afterward. Production and the user's desktop profile
were unchanged.

The batch carries the older-buffer importer and editable native journal recovery
from withheld 4.25/4.26 candidates. Issues 38 and 39 are associated with 4.27 for
automatic closure only after its public artifact and six-platform update gates.
Larger journal imports, full OS/provider provisioning and missing original office
state stay explicitly separate. Strict roadmap coverage remains 17/64 (26.6%).

## 19 October: current-answer ranking and binary preflight

Source 4.24 addresses the archive and bilingual-question patterns in issues
17/31, with preserved history, explicit ranking explanations and a repeatable
real-model probe. [The 50-document comparison](../validation/2026-10-19-retrieval-archives.md)
records all thirteen intended targets in the top four after indexing, without
claiming general accuracy. Queued evaluations now record their actual execution
implementation. Ninety focused retrieval checks and the typed client/UI checks
passed. The source carries KeePass from withheld 4.23, correcting its missing
Intel Mac dependency wheel and adding an automatic binary-only resolution gate.

[The actual Windows installation](../validation/2026-10-19-windows-live-update.md)
completed an unattended 4.15→4.20 update and relaunch, retaining its automatic
updates, background and login preferences. Release 4.22 was subsequently
published; each release's public update acceptance stays separately recorded.
The strict complete product count remains **17/64 (26.6%)**. Host continuity,
legacy buffer reconciliation, hosted client acceptance and broader quality
remain active work.

## 19 October: KeePass transfer and issue closure

Source 4.23 implements the remaining KDBX 4 request from issue 32, with reviewed
current-field import, default masked names, encrypted mapping, scoped export and
matching app/SDK/private-agent controls. [Validation](../validation/2026-10-19-keepass.md)
records 23 focused cases, 37 existing vault/agent checks, 25 migration checks and
an actual app download opened independently by PyKeePass with all 12 field hashes
and both group paths preserved. [The guide](../service/keepass.md) documents limits
and omitted history/attachments. Native publication remains separate.

Issues 40/41/42 closed through verified public release evidence. The corrected
4.22 candidate carries the source-health fix for 43 and native-memory backfill
for 39; 4.21 and the initial 4.22 attempt remain withheld. Remaining reports are
retained in the [issue plan](github-issues.md). The full 64-item requirement count
does not change merely because a bounded issue is addressed.

## Worktree and reproducibility

- Current implementation: `main`. The rebuild and free Mac updater were merged at `da74785f67f96d0fd375e7925d23284c435b6f99`. The original implementation branch was `codex/mnemion-v4`, based on `c670e3039d2f7b43dbb00a2157e420e665203979`.
- Pre-existing tracked and untracked work was preserved before implementation. A WSL restart on 10 October cleared the temporary backup and fixture directory; the working tree remained intact. A fresh private snapshot now preserves the complete current tree in persistent local validation storage.
- Local test runs use isolated temporary profiles and an environment installed from the refreshed `uv.lock`. The later authorized shared-workspace migration and Windows connection checks are recorded in the 12 October entries below.
- A real local PostgreSQL 16.2 instance with pgvector was verified through a temporary `pgserver` development installation. This binary is test tooling, not the production database distribution.

## Implemented work, 9 October 2026

- Search reacquires a collection created after startup.
- Hybrid ranking sorts after confidence weighting, applies a normalized rank threshold, and enforces the final result limit.
- Graph search checks the actual source, current trust, and requested scope; unbacked, removed, or quarantined source facts cannot enter ordinary search.
- Cognitive retrieval resolves current trust; reconsolidation replaces evidence when source text changes; reconstruction bounds topic expansion.
- Added a durable legacy ingestion journal and shared writer. MCP saves/diaries, miner, conversation miner, sweeper, capture, and autosave hooks now use it. Retries replay interrupted vector/sidecar writes; successful completion persists lexical and trust state together. Completed jobs discard their content payload.
- Idempotent trust creation preserves the existing status and avoids spurious creation history. Edited source text invalidates its older cognitive and graph projections.
- Legacy deletion now records a durable denial before deleting projections; retries cannot recreate a deleted ID. Query-specific recall and NDCG calculations were corrected, unexecuted comparison modes report no score, and Studio provider keys are redacted from configuration responses.
- Added the PostgreSQL service: authenticated principals, explicit spaces/grants, row-level isolation, immutable source and memory revisions, optimistic corrections/review, transactionally accepted writes, idempotency receipts, indexing leases/heartbeats/retries, and deletion/purge receipts. API and worker logins are separate and cannot own the schema or bypass row-level policy.
- Added local multilingual E5 retrieval with pinned model/tokenizer hashes, chunk offsets, index-generation identity, lexical and semantic readiness, temporal/filter-aware recall, cited sources, and bounded context packs. Transaction fixtures use a separate test-only embedder; the real-model integration test checks multilingual retrieval and long-input chunking.
- Added the `/v1` HTTP surface, typed Python and TypeScript clients, and an MCP 2.x gateway over that HTTP contract with stdio and Streamable HTTP transports. HTTP MCP calls use each caller's credential.
- Added scoped Obsidian ZIP export and a shared local refresh engine. Standard YAML/Markdown, source block citations, stable paths, wikilinks, and graph navigation are retained. Refresh preserves personal sections and unmanaged files, records edited-generation conflicts, handles interrupted publication, and prunes only known managed content. The service never accepts a server-side vault path.
- Split the default service installation from the optional Chroma-based `legacy` extra. Setup, API/worker commands, SDK examples, MCP configuration, and Obsidian refresh are documented in [the service guide](../service/README.md).

Additional implementation completed:

- Versioned full PostgreSQL backup/restore with manifest and per-table verification, isolated restore publication, current deletion/access-ledger reconciliation, and API-key rotation. Recovery preserves newer negative identities even when their positive record did not exist in the backup.
- Complete offline v3 profile archives include Chroma, sidecars, raw sources, core memory, wiki, and the Obsidian vault. Restores reconcile current deletions and pending writes, relocate paths, and stay paused. Updated legacy entry points honor a persistent writer pause.
- Flat JSON imports validate the entire input before opening a live backend and use the durable journal; missing lifecycle data is quarantined. Destructive replace behavior and the old Git-union sync are retired, with their historical sources retained under `docs/legacy`.
- V3 migration now creates an explicitly owned private space, retains original IDs/source bytes/trust history/correction references, reports exceptions, imports the final delta, and records a cutover boundary. Application writes use a shared transaction lock; a pause waits for acknowledged in-flight writers.
- Scoped rollback exports preserve all current v4 records, revisions, source attachments, core history, and deletion denials. Replay into a new paused v3 profile uses the legacy embedding pipeline and verifies canonical content hashes. The complete v4 tail remains available in the recovered profile.
- Studio now supports authenticated shared workspaces, save/revise/review, lexical/semantic retrieval, context packs, source evidence, original-file downloads, operations/retries, core context, credentials/grants, and Obsidian export. The default Windows package connects to the shared service through a narrow sandboxed bridge and includes a local vault refresh client.
- Native Obsidian 1.14.4 was exercised with readable note paths, wikilinks, source anchors, and a repeated refresh. The connected fixture had 17 Markdown files, 35 resolved links, zero unresolved links, and four valid source block anchors. Settings and personal annotation bytes survived refresh.

Verification completed so far:

- The latest complete regression run passed **358 tests**, skipped one, and deselected 106 benchmark/slow/stress cases. Service coverage was **83.56%**, above the required 75%. It included real PostgreSQL, real local multilingual embeddings, SDK/MCP transports, service and legacy recovery, and Obsidian refresh.
- The migration/rollback group and HTTP attachment/alias authorization checks passed in that full run, including a real Chroma rollback after new v4 writes, corrections, quarantine, deletion, and a core-block change.
- The TypeScript SDK builds and its four retry/authentication/browser-fetch tests pass. Its real HTTP integration is part of the service suite. The Studio frontend and Electron TypeScript builds pass after the desktop changes; original-file download UI also compiles.
- The supported Python 3.12/3.13/3.14 service matrix passed at the earlier core milestone; it must be rerun after the recovery/migration additions. Default service dependencies exclude Chroma; native legacy replay requires the Python 3.12 legacy environment.
- The native Windows build produced a **116 MB NSIS installer**. Payload validation and real-window rendering, sandboxed preload, local-client capability, and tray-icon checks passed. The packaged client authenticated against the real service. Native vault refresh and tray/second-instance interaction checks are being completed. The installer is **NotSigned** and has not been published.
- Advisory scans found no known advisories in the default Python production environment (57 third-party distributions), frontend, or TypeScript SDK. The Electron build dependency tree retains eight moderate affected packages from the transitive `sprintf-js` advisory; exposure/disposition and the legacy-extra audit remain to be finalized.
- OpenAPI is generated offline from the actual typed routes. Ruff checks passed on the modified service and integration files at the current milestone. Final repository formatting, CI, and runtime checks remain.

The original temporary test fixtures and raw logs were cleared by the WSL restart;
new checks use private persistent validation storage. Historical counts above
describe those earlier runs, not retained final-release evidence. Reviewable
screenshots remain under `output/playwright/mnemion-v4`. No production
profile, personal Obsidian vault, scheduled task, or GitHub release was changed.
The overall product goal remains active.

## Original program checklist (historical)

This checklist records the early rebuild checkpoint. Later entries and the
[current roadmap](../ROADMAP.md) supersede its implementation status. Broader
capacity, live-provider and answering evaluation commitments remain visible there.

- [ ] Complete memory/resource limits and observable bandwidth, selectable current embedding models with safe reindex/activation, and the configurable local/cloud librarian.
- [x] Implement and validate the detailed visual [observability and evaluations workspace](observability-and-evaluations.md), including reproducible test sets/runs, bounded execution, comparisons, exports and permission/deletion handling.
- [x] Implement complete service and legacy recovery, durable legacy writes, strict JSON imports, and replacement of unsafe Git sync.
- [ ] Finish migration/rollback edge-case and operational review, including derived legacy views and uncommon source layouts.
- [ ] Complete the bounded component/adoption decision with comparable contract and cost evidence.
- [ ] Complete the service-core release audit of the implemented PostgreSQL/auth/revision/job/readiness paths and setup commands.
- [ ] Verify tenant/space isolation, concurrent writes, retries, leases, revocations, corrections, quarantine, and deletion across every API/projection.
- [ ] Validate the implemented real embedding retrieval, fingerprinted generations, scoped fusion, citations, temporal behavior, and context budgets against the held-out and load gates.
- [ ] Complete typed OpenAPI responses, SDK integration/compatibility checks, maintained MCP transport verification, and required legacy aliases.
- [ ] Preserve Obsidian Markdown, paths, wikilinks, native graph, manifests, manual sections, and refresh/ZIP/open workflows through a copied-vault migration.
- [x] Implement and rehearse versioned recovery, v3 ownership/ID import, final delta/cutover, exception reconciliation, and replay of post-cutover writes into a new paused legacy profile.
- [ ] Adapt Studio into a coherent team/operator product with credentials, sources, ingestion, query explanation, conflicts, exports, deletion, and recovery status.
- [ ] Remediate or explicitly assess dependency advisories, update lockfiles, and pass the complete supported-runtime test/build matrix.
- [ ] Execute held-out retrieval/answering evaluation and declared load/cost/recovery benchmarks; publish the actual results and limitations.
- [ ] Verify self-hosted startup and deployment configuration, native macOS/Windows/Linux packaging and launch, supported clients, and native Obsidian visualization.
- [ ] Complete release documentation, compatibility policy, operational runbooks, support path, and requirement-by-requirement final audit.
- [ ] After product validation, audit tracked files and Git history for exposed secrets, remove temporary artifacts, organize public documentation, and leave a clean, reviewable Git state (explicit user requirement).

Completion requires evidence for the full requirements above and the detailed
gates in the linked roadmap. Passing a smaller regression suite is intermediate
progress only.


## Expanded source and feature-preservation validation — 2026-10-09

The source/identity connector contract now has Git, filesystem, rclone, Slack
and Drive adapters, scope leases, checkpoints, source conflict proposals,
operator pauses and restore-time deletion/access reconciliation. A public
adapter API supports additional company providers. Live customer-provider
authorization has not been exercised; included provider tests use explicit
fixtures plus real local Git/filesystem operations.

The [v3 feature audit](v3-feature-parity.md) now links shared conversation capture,
configuration preview/apply, source/wiki workflows, graph and curation.
[Feature decisions](feature-review.md) distinguish implemented capabilities from
optional enterprise work. Obsidian entity pages now retain evidence excerpts,
review status and revision dependencies.

The full Python 3.12 regression with real local E5, real PostgreSQL and Chroma,
and Node SDK integration passed **403 tests, 1 skipped, 106 deselected**, with
**84.96% service coverage**, in 215.35 seconds. The TypeScript SDK and Studio
production build passed. This does not certify native installers, deployment,
load performance or held-out answer quality.

Subsequent security work reproduced and fixed a check/open symlink race in the
selected-folder connector. Linux/macOS now use anchored directory descriptors;
Windows verifies the opened file handle's final path. The provider command runner
also bounds output while the process runs. Their targeted provider suite passed
11 checks before the final read-error hardening; final native verification and
a fresh publication audit remain required. Local proof logs are intentionally
kept outside the public source tree.

## Persistent release validation — 2026-10-10

The current tree is privately archived before further work. The locked Python
3.12 environment and pinned real embedding cache have been rebuilt. The public
LongMemEval source is pinned by repository revision and file SHA-256; its frozen
12-development/48-held-out question plan is versioned under `benchmarks/plans/`.
Abstention cases are identified by the dataset's `_abs` suffix, excluded from
retrieval recall, and kept for separate answering checks. The harness validates
scope, content hashes and citation offsets, compares hybrid/semantic/lexical
retrieval, and records actual bounded context coverage and uncertainty. Results
are not yet final release evidence.

Compose initialization and an explicit restore activation workflow are now
implemented and documented in the [deployment runbook](../service/deployment.md).
Activation validates the restored administrator key, completed recovery record,
migration hashes and both restricted database roles before an atomic cutover
record is written. Runtime credentials are derived and recover after interruption.
The old database and prior private operator state are retained.

The focused recovery/setup/evaluation group passed **10 tests, 1 platform-specific
skip**, including a real backup/restore, stale-key rejection, interruption after
activation publication, idempotent resumption, and preservation of the original
database. The three evaluation-metric tests passed again after adding baseline
modes and bounded-context reporting. Fresh full-suite, container, native,
performance and publication checks remain required.

The [10 October validation report](../validation/2026-10-10.md) now records the
retained full regression (421 passed), supported Python matrix, native Windows
client checks, container recovery activation, Obsidian correction/deletion refresh,
Linux payload/window checks, and the completed frozen held-out retrieval results.
It also records the indexing timeout and continuation, limited context coverage,
and the remaining answering, load, native, licensing and publication gates.

## Configurable librarian and product website — 2026-10-10

The shared librarian now supports operator-approved Ollama and OpenAI-compatible
endpoints, per-space outbound approval, optional schedules, durable call budgets,
leased low-concurrency jobs and explicit source revision dependencies. Organization
proposes titles, additional tags and summaries independently for each memory;
review proposes possible links, duplication, contradictions and stale claims in
a bounded batch. Generated output never grants access or verifies a claim.

Studio includes model/schedule controls, before/after proposals, all input
revisions and quotations, per-memory outcomes, run usage, accept/reject and guarded
undo. Applying organization preserves the canonical text, original evidence,
attachments and unrelated metadata. Deleted or quarantined inputs invalidate and
erase affected generated text, including findings influenced by uncited inputs.
Restoring a backup cancels pending jobs and requires renewed model approval.

Browser validation found and corrected premature completion of a multi-memory
run and a cramped mobile status layout. Regression tests cover complete and
mixed-size batches. Cancellation retains the database-wide slot while a request
is still in flight. The HTTP transport now enforces a total deadline across
connection, headers and body and closes interrupted requests; real loopback HTTP
tests exercise deliberately trickling responses. No live model or paid call was
used for these checks. See [the operator guide](../service/librarian.md).

The matching Perseus XR product page is prepared in a verified deployment
preview. Its existing Mnemion project card now describes shared memory and links
to the new page. The page includes platform downloads, documentation, roadmap
and optional support; download eligibility requires a complete published release.
Production promotion remains tied to the desktop publication gates. Current
validation, public scan results and remaining limits belong in the
[validation report](../validation/2026-10-10.md), not an unconditional v1 claim.


## Main integration and staged platform release — 2026-10-10

The rebuild, selectable embeddings, librarian, documentation and free Mac updater
are on `main`. Both packaged Mac architectures passed signed upgrade/relaunch
and inactivity, transfer, draft and focus guards at `873da44`; native interrupted
download, oversize, downgrade and disconnection recovery passed at `c088757`.
The [implementation report](free-macos-updates.md) links the exact workflows.

The Perseus XR product page, homepage feature and existing Lab Notes entry are
live. Ready Mac/Linux platforms are published independently while Windows release
validation continues. The release-target registry and platform-specific website
gates require complete installer/update assets for each offered platform.
Historical build counts above remain historical; the versioned release notes and
current roadmap define current availability and outstanding work.


## Platform v1 published

Version **4.0.0** is public for macOS and Linux on Intel/x64 and ARM64, from
`d66345a53329adf64c0745e599250ccddd6c8215`. Release workflow
[38077770316](https://github.com/Perseusxrltd/mnemion/actions/runs/38077770316)
passed all checks. The 26 immutable assets and their digests were verified after
upload, and the four public installer URLs returned HTTP 200. Downloads, setup,
release notes and the roadmap are available at
https://www.perseusxr.com/mnemion. Windows remains the next platform delivery;
see the current roadmap and dated validation report for the exact scope.

## Windows x64 delivery and remote-agent follow-up

The 4.0.1 release target includes Windows x64 plus both Mac/Linux architectures.
Native Windows x64 installation, authenticated upgrade and relaunch pass, with
72 installed binary hashes preserved and paths containing spaces. Windows ARM64
first installation now passes after the archive-filter correction; its automatic
relaunch remains a release blocker for that architecture. Publication proceeds
independently for the verified variants. See the
[dated evidence](../validation/2026-10-10.md#windows-x64-installer-and-updater-verification)
and [4.0.1 notes](../releases/4.0.1.md).

## Remote-agent hotfix 4.0.2

Implemented issues 5, 9, 10, 12 and 16: authenticated HTTP MCP initialization and
discovery, API/MCP on one listener, explicit invalid-scope instructions, described
tool fields, structured privacy-preserving errors, bounded inference admission
and retry hints in Python/TypeScript clients. Source and Compose deployments can
set the exact public HTTPS origin without disabling MCP host/origin protection.

The local service suite passed 221 tests with two opt-in real-model tests skipped,
at 85.68% service coverage. Both SDKs have retry behavior checks; production
release CI additionally runs real-model tests and the native platform gates.
These results do not claim a live capacity benchmark or an already-upgraded
remote host. See [4.0.2 notes](../releases/4.0.2.md) and the dated validation report.

Remaining patch work includes public-artifact upgrade rehearsals, Windows ARM64
relaunch, full discoverable agent administration, remote/OAuth setup, source
installation UI, managed server upgrades/non-systemd supervision, API/worker RSS,
source synchronization, author-deletion policy and natural-language retrieval
quality. The roadmap and issue queue track those independently.

## Hotfix 4.0.3, 11 October 2026

- Native Windows ARM64 installation, signed upgrade and relaunch passed; its
  architecture joins the complete release target set. Windows x64, both Mac
  architectures and both Linux architectures remain in every stable feed.
- Local E5/BGE reuse one tokenizer vocabulary with locked source/inference modes.
  Complete source offsets, model settings and vector generations are preserved.
  A controlled E5 comparison saved 296 MiB after load and 283.8 MiB after a
  35-chunk document, with identical vector/span checksums. The focused real-model
  and concurrency group passed 19 tests. Separate process caches remain open.
- A reusable public-package upgrade observer follows official feeds, preserves
  the default profile, observes actual new processes and reaps exited launchers.
  It does not bypass application guards or simulate inactivity.
- Release notes, roadmap, model-resource reproduction instructions, Windows and
  desktop guides now describe the patch. Full release evidence is tracked in
  [the current validation report](../validation/2026-10-11.md).

## Hotfix 4.0.4, 11 October 2026

- Reviewed operation discovery covers all 81 existing HTTP actions with strict
  input schemas, read/write classification and retry behavior. CLI and compact
  MCP tools preserve the same tenant/space authorization and version checks.
- Responses have explicit byte budgets and transfer limits; exports stream to
  private files. New API keys are issued only after reserving an owner-only
  result file and are usable directly by existing agent setup commands.
- CI regenerates the agent contract and rejects unclassified route additions.
  HTTP/MCP tests cover access denial, revoked keys, unknown write outcomes,
  preserved idempotency, retry delays, private results and bounded buffering.
- Linux login entries follow renamed AppImages while retaining OS disable flags
  and custom startup commands. The public observer checks the actual startup
  target as well as the replaced process, installed bytes and preserved profile.
- Hosted OAuth, remote setup, server supervision/updates, source triggers and
  further memory/retrieval work remain explicit roadmap items. The public
  4.0.3 release and automatic six-platform website refresh were verified.

## Hotfix 4.0.5, 11 October 2026

- Durable connector sync requests preserve requests arriving during a scan and
  leave failed inventories pending. Existing source ownership, ACL leases and
  canonical deletion safeguards remain in effect.
- Studio, Python/TypeScript SDKs and the 84-operation agent catalog expose sync
  requests/status. Runner logs and server status include UTC times, duration and
  changed/removed/unchanged counts; small control polling is configurable.
- Real PostgreSQL and HTTP tests cover concurrent requests, restricted roles,
  active-scan races, Git deletions, acknowledgements, bounded polling and older
  services. The full service group passed 243 tests with two model skips and
  86.03% coverage; all seven TypeScript SDK checks and the Studio build passed.
- Migration 012 adds one control record per connector. Release notes describe
  coordinated backup/migration/restart and separate-database rollback. Managed
  server updates and native provider webhook receivers remain separate work.

## Hotfix 4.0.6, 11 October 2026

- Official Python wheel/source archives include the matching web Studio and
  offline guides with dependency notices and a bounded SHA-256 file inventory.
  Startup discovers the bundle; source checkouts have one build command and a
  credential-free status command. Explicit paths and headless deployments remain supported.
- Failed source-bundle replacement restores the previous complete build, and
  concurrent builders cannot replace each other's dependency tree. Product CI
  and release assembly inspect both real Python artifact formats.
- Container builds now receive the repository Markdown. The frontend build
  rejects missing essential documentation or notes for the selected version.
- The container API entry point uses the current offline model-preparation
  command. A real PostgreSQL regression check exercises initialization of the
  HTTP application, Studio, readiness and authentication; failed preparation
  cannot open a listener.
- The preceding 4.0.5 release passed all product/native gates and all six public
  4.0.4 → 4.0.5 automatic upgrades. The website updated all six download links
  automatically. Issue 15 is closed; native provider webhooks remain an extension.

## Hotfix 4.0.7, 11 October 2026

- A private Supervisor instance manages API and worker processes on Linux/macOS
  without systemd. Local JSON lifecycle commands, role-specific files, a Unix
  control socket and bounded logs make the host operation available to authorized
  maintenance agents without extending the privileges of a memory API key.
- Preparation generates a quoted cron entry and a launchd plist. It does not
  overwrite existing configuration or modify the host's startup registrations.
  The guide distinguishes user-login startup, host boot, process recovery,
  PostgreSQL/source-runner lifecycle and resource isolation.
- Readiness identifies the managed API instance and PID as well as both running
  processes. A foreign or orphaned HTTP listener cannot satisfy the check.
  Shutdown waits through the supervisor's draining state; an unresponsive control
  socket is not reported as a stopped service.
- Offline schema export is independent of the selected web bundle, while actual
  serving retains its matching-version and integrity checks.
- The preceding 4.0.6 release passed both container architectures, every product
  and native release gate, and all six public 4.0.5 → 4.0.6 automatic upgrades.
  All six public downloads and automatic website metadata updates were verified.
  Issue 7 is closed. Server software auto-updates remain separate work in issue 11.

- Release 4.0.7 was published after every product, container and native gate
  passed, including both native Mac supervision/model/audit jobs. All six real
  public 4.0.6 → 4.0.7 automatic upgrades passed and preserved profiles. The
  website followed the release automatically. Issue 6 is closed; host-specific
  boot adoption and verified server software updates remain separate work.

## Hotfix 4.0.8, 11 October 2026

- Studio now shares Perseus XR's ink/ivory/gold palette, locally bundled
  Inter/Outfit fonts and license inventory across workspace, insights, settings,
  documentation and local-vault surfaces. Navigation is grouped and responsive;
  installed patch labels come from package metadata.
- Added a reload recovery screen for open web tabs whose old lazy screen bundle
  disappears during a service update. Navigation survives, and reload is explicit.
- Added independently signed compatible Unix service patches, explicit host
  adoption, default automatic checks, isolated locked staging, verified backup,
  durable recovery and runtime-only rollback. The separate publisher secret is
  configured for release assembly; private key recovery material stays outside Git.
- Backup retention preserves three updater-created verified archives. Runtime
  cleanup preserves active/previous/pending/journal references and leaves operator
  data alone. Package installation and service children do not inherit owner credentials.
- Local service checks passed 336 tests, two opt-in skips, 86.05% coverage; legacy
  passed 311 with one skip and 106 marker exclusions. Client and desktop-policy
  checks passed seven and 24 respectively. Browser checks covered connected flows,
  six insight tabs, narrow layouts and a missing-bundle recovery fault.
- Native release gates and public upgrade checks remain required. The first
  public service manifest establishes the baseline for a later real feed upgrade.
  Fleet/Compose/Windows-server updates, schema-changing unattended upgrades and
  physical host boot checks remain open under issue 11 and the deployment roadmap.

## Published workspace and administration updates, 11–12 October 2026

| Release | Delivered behavior and evidence |
| --- | --- |
| [4.0.9](../releases/4.0.9.md) | OS-protected desktop connections, destination-bound credentials and identity-checked reconnection. |
| [4.0.10](../releases/4.0.10.md) | Live 3D memory map, attributed activity, source/author filters and bounded connection diagnostics. |
| [4.0.11](../releases/4.0.11.md) | Bundled local hosting and guided setup, RAM policy/recovery, independent administrators, final-admin protection, offline workspace details and optional trusted-issuer OAuth validation. |
| [4.0.12](../validation/2026-10-11-v412-release.md) | Native ngrok/protected-health compatibility, all six installed setup and public update gates, and a real Windows human-administrator join/reopen. |
| [4.0.13](../validation/2026-10-12-v413-release.md) | Separate app/server versions and administrator diagnostics; the shared server and actual Windows client both completed signed automatic updates. |
| [4.0.14](../validation/2026-10-12-v414-release.md) | Linux clock-safe process/RAM observations, all six public desktop updates and an operator-applied shared-host patch preserving authority and its address. |

The original shared workspace was [adopted into managed hosting](../validation/2026-10-12-managed-workspace-upgrade.md)
with a fresh encrypted off-host backup and preserved identities, keys and space
grants. [Independent Windows backup decryption and isolated restoration](../validation/2026-10-12-encrypted-workspace-backup.md)
verified a separate recovery path. The [bounded Windows lab](../validation/2026-10-12-workspace-administration.md)
uses its own restricted identity and synthetic memories. These exercises do not
complete app-managed backup schedules, registered recovery hosts, operator
delegation, individual browser sign-in or failover.

## Corrected 4.1.0 candidate, 12 October 2026

[Scoped author withdrawal](../service/withdrawal.md) is implemented with a checked
schema migration, immutable authorship conditions and protected cleanup. The
[installed migration checks](../validation/2026-10-12-author-withdrawal.md) found
a Windows backup flush error and a macOS Keychain wait. Corrected source
`cbea13f49e6c23e5404d7e831cc0d23365ac3b9a` uses a writable Windows flush handle and
[bounded asynchronous Mac credential operations](../validation/2026-10-12-macos-upgrade-startup.md).

The [corrected release build](https://github.com/Perseusxrltd/mnemion/actions/runs/38203918134)
passed all 30 jobs, with independent verification of all 38 draft assets and
production update signatures. Its [installed migration/recovery run](https://github.com/Perseusxrltd/mnemion/actions/runs/38206660021)
passed both Windows and both Linux architectures. Both Macs completed migration
and restoration but hung on final exit while Keychain consent remained pending.
The next source correction isolates credential work in a private helper and
passes all 102 desktop unit checks; native acceptance remains required.

The same second candidate also passed a separate migration rehearsal against
the verified encrypted shared-host snapshot, preserving existing table contents,
revoked copied keys and recovery-administrator access. The live host remains
4.0.14/schema 13. Complete the final candidate's six installed gates, fresh backup,
shared-host migration and restricted Windows-lab acceptance before publication.

## Published 4.1.0, 12 October 2026

Final source `4b5df29131566e26b802ca8e4ef3fa77f06fc57e` resolves the macOS exit
finding with an isolated, bounded credential helper. All release/product/native
gates and all six installed migration/recovery targets passed, including clean
exit on both Macs. The independently verified 38-asset release was
[published at 06:45:13 UTC](../validation/2026-10-12-v410-release.md). Public-feed
rehearsal passed on all six targets; the release metadata fallback updated itself.
The actual product page passed desktop/mobile checks with all six current links,
guides, release notes and the matching homepage feature at 06:51:32 UTC.

The final signed runtime also passed the restored shared-host exercise, retaining
all 50 existing data-table hashes, recovery access and restricted contributor
withdrawal. The provider control relay interrupted the live operator session;
the original service remains on healthy 4.0.14 until a fresh verified backup
and controlled migration can complete. The earlier migration-before-publication
plan was adjusted to honor the standing instruction to publish verified targets
while separate deployment validation continues. This does not mark the live
host or the broader organization/recovery roadmap complete.

## Personal access and continued hotfixes, 13 October 2026

The shared host subsequently completed its controlled 4.1.0 migration and
automatic 4.1.1 patch; [Windows contributor and backup acceptance](../validation/2026-10-12-model-idle-release.md)
passed. Later verified releases added managed connector adoption, inference
fallback, MCP scope/diagnostics, Git revision stabilization and update fixes.
The [4.1.7 publication record](../validation/2026-10-13-managed-update-schedule.md)
links all six public automatic-upgrade results. Actual Windows then completed
[automatic 4.1.4 → 4.1.6 → 4.1.7 updates](../validation/2026-10-13-locked-desktop-updates.md).

Source `af7f9b795bc94b36c432810148e80a82fd1ce340` was
[published as 4.2.0 at 14:26:07 UTC](../validation/2026-10-13-personal-access-release.md).
All 30 release jobs, 11 separate product jobs and six installed schema-upgrade/
recovery targets passed. All 38 assets, public feeds and live website links
were verified. Personal sign-in, invitations, revocable device sessions,
13 additional private agent operations, matching search passages and locked-
desktop restart handling are delivered. Public automatic-update rehearsals
subsequently passed on all six targets at 14:37:29 UTC. The independent shared
host requires its own backed-up
015 migration; a desktop release does not apply it.

Published 4.2.1 reduces retained Linux/glibc model heap pages, with
[real offline measurements](../validation/2026-10-13-idle-heap-reclaim.md) and
focused/native checks passed. Source also adds exact native database cache keys,
fresh cache-hit probes and continuously current release-status/roadmap links.
It was published at 15:13:05 UTC after all 30 signed release jobs, 11 separate
product jobs and independent uploaded-byte verification passed. The
[publication receipt](../validation/2026-10-13-v4_2_1-publication.json) records
the immutable source and assets. [Anonymous live website verification](../validation/2026-10-13-v4_2_1-website.json)
passed for the current version, all six installers, guides, notes and roadmap;
[public 4.2.0 → 4.2.1 upgrades](../validation/2026-10-13-v4_2_1-public-upgrades.json)
subsequently passed on all six targets. All five
cache hits passed fresh full database probes, with
[paired job measurements](../validation/2026-10-13-native-cache.json).

Published 4.2.2 implements bounded exact-ID/filename candidates and
transparent subject/path weighting. Its
[validation record](../validation/2026-10-13-exact-identifiers.md) separates
synthetic ranking regression from general retrieval quality. All six desktop
release gates and independent artifact verification passed. It was published
at 16:06:26 UTC; the website updated automatically and issue 27 is closed.
The complete request
list remains 64 items, with 17 shipped and 40 partial; this is scope coverage,
not a weighted effort estimate or a claim that the product is ready to freeze.

## Combined search, agent and release-automation batch, 13 October 2026

Source 4.2.3 combines compact discovery, standard search/fetch aliases, native
credential-bound MCP sessions, recency and match-filter controls in the API,
SDKs, MCP and app, with a one-time Git source-date backfill. The
[validation record](../validation/2026-10-13-search-agent-batch.md) records focused
checks and limitations. No new migration is added after 015.

The user's faster-delivery direction is retained as policy: coherent batches,
focused local checks, one full release run and additional checks only for a
failure or concrete risk. Scripts maintain version/contract boundaries, freeze
already integrated source, avoid duplicate release dispatch, publish unchanged
verified assets, start downstream public checks and retain per-version evidence.
The native push matrix no longer duplicates the release matrix. These automation
changes do not remove any of the 64 product requirements or invent completion.

## Question retrieval and evaluation controls, 14 October 2026

Source 4.3.3 combines optional question-term support, app/SDK/MCP controls,
transparent matched-term explanations and saved evaluation ranking preferences.
New runs record the executing service version and cannot silently resume across
a hotfix. [Focused checks and the existing-corpus regression](../validation/2026-10-14-question-retrieval.md)
passed; the regression is not a new independent held-out claim. Broader question
quality and current shared-office acceptance remain open. The strict tracker
still records 17 of 64 requirements shipped and 40 partial.

## Guided native remote access, 15 October 2026

Source 4.4.0 combines local host sharing, an owned ngrok SDK connection,
existing HTTPS proxy checks, matching hosted browser/consent assets, public
invitation links and private operator command parity. The app serializes
configuration with restart, stop and update operations. The
[validation record](../validation/2026-10-15-native-remote-access.md) separates
focused checks and a real local TLS/CPU-model walkthrough from native release
gates and live provider acceptance. No database migration is added. Independent
hosting/recovery and named provider acceptance remain open; the strict tracker
still has 17 of 64 requirements shipped and 40 partial.

## Journal durability, live capture and host setup, 19 October 2026

The [4.15 journal batch](../validation/2026-10-19-git-journal.md) and
[4.16 filing batch](../validation/2026-10-19-journal-filing.md) add optional durable
receipts, guarded Git delivery, complete replay, Obsidian notes and intact archival.
The [4.17 batch](../validation/2026-10-19-live-conversations.md) adds bounded live
JSONL capture, exact source references and a reproduced desktop control-drain fix.
The [4.18 batch](../validation/2026-10-19-journal-host-setup.md) adds local app/agent
host registration, separate publication approval and a new installed-app acceptance
flow. Each record distinguishes source checks from native acceptance. See the
[automatic release ledger](../RELEASE_STATUS.md) for publication and public updates.
Independent custody, provider sign-in, guided remote-host setup, backfill and
complete writable reconstruction remain open. The complete requested scope is
retained at 17 of 64 shipped, with 41 partial requirements.

## Daily journal capacity and agent update control, 19 October 2026

The [4.19 batch](../validation/2026-10-19-journal-rollover-updates.md) removes the
20 MB single daily-file publication stop through numbered continuation files,
immutable-object indexing and complete active/archive retry checks. A schema-2
catalog prevents older writers/readers from silently overlooking parts; every
publisher and journal runner needs the compatible version. The batch also adds
four private desktop operations for app preferences and update status/check/restart,
with stale-state and unsaved-work guards. Native delivery remains tracked in the
automatic release ledger. Full backfill, large total inventories, provider and
fleet acceptance, and independent office availability remain open. Strict full
scope remains 17 of 64 shipped (26.6%).

The 4.18 installed Git-registration gate caught native connections stripping the
server version, hiding supported features. All six native targets refused that
release. 4.19 retains the optional, validated version through connect/resume and
keeps the complete installed registration check. Two regression checks reproduced
the old failure; all 38 workspace identity/connection checks pass after the fix.

## SSH journal access and destination receipts, 19 October 2026

The [4.20 batch](../validation/2026-10-19-journal-ssh.md) implements issue 42's
repository-specific SSH key and host-pin controls. It includes native file
selection, CLI/private-agent enrollment, bounded owner-only key snapshots,
noninteractive transport and explicit local/network receipt types. Actual
OpenSSH, Git and PostgreSQL checks cover important-save acknowledgement, revoked
access, wrong host keys, retries and concurrent writers. Existing HTTPS/local
fingerprints remain stable. Provider provisioning, additional native SSH evidence
and complete recovery remain open; full-scope completion stays 17 of 64 (26.6%).

## Text-source isolation and health, 19 October 2026

The [4.21 batch](../validation/2026-10-19-source-health.md) addresses issue 43:
one malformed Markdown file could suspend an entire source. Folder, Git and
rclone text scans now keep valid updates flowing with bounded per-file diagnostics.
Partial scans retain prior evidence, stable IDs and complete checkpoints, withhold
inferred deletion and leave requested syncs pending until a clean scan. The app,
recall/context, authenticated health, SDKs and `health.sources` agent operation
report coverage problems. Migration 024 adds only an index and scoped health
function. Structured journals, directory inventory and permissions remain
fail-closed. Broader provider/fleet acceptance and the full 64-requirement scope
remain open; this hotfix does not change the strict completion count.

## Existing native-memory backfill, 19 October 2026

The [4.22 batch](../validation/2026-10-19-journal-backfill.md) adds separate
approval, a persistent cursor, bounded privacy-scanned capture and current
administrator/publisher checks. App, Python/TypeScript SDK and named agent
operations share start, status, pause, resume and cancel controls. Original
memory identities, revision dates and authors survive without re-embedding.
Queued Git delivery remains separately observable; full database restore retains
progress and pauses publication. A narrowly scoped approval function lets the
internal publisher check the approving administrator without reading other
principals' records. Legacy external-buffer migration and complete writable
reconstruction remain under issue 39. The [issue plan](github-issues.md) retains
all 12 reports reviewed today; verified-release associations close only addressed
issues after publication/upgrade evidence. Strict scope remains 17/64 (26.6%).

## Expanded librarian workstream — 20 October 2026

R07 preserves the new [layered-memory research and delivery contract](../research/2026-10-20-layered-librarian.md): configurable raw capture and available reasoning traces, episodic/claim/procedural/working layers, continuous deep review, statistics-based resurfacing, controlled retention and vault boundaries, app/agent parity, and a recurring scientific/tool watch. TypeSafe AI Jev is a candidate typed router with published cost and data-policy limits; no paid calls or account were created. The work remains planned while open deployment issues and the connector release continue.
