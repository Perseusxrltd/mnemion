# Complete-milestone acceptance audit

Reviewed 22 October 2026 against all **42 partial requirements** in the
[complete inventory](../PRODUCT_REQUIREMENTS.md). All 65 requirement IDs, the
expanded librarian, scientific/Jev work and every open issue remain retained.
This audit changes work order; it neither narrows scope nor marks a parent done.

Continue frozen releases and finish the selected capture-controls journey already
under implementation. Keep one feature milestone alongside urgent operational
bugs. Next prioritize independent shared administration, source freshness,
ordinary memory operations, backup/recovery and updates; then complete company
onboarding/provider journeys before expanding advanced librarian/visual work.
Each milestone must include its app and agent journey, supported platforms,
error/recovery behavior, documentation and observed completion proof.

Remaining effort and estimate confidence are **unknown for every row below**.
The missing acceptance work is identified from current documented gaps; its
individual implementation, provider waiting time and representative workload
have not yet been measured. The 26.2% full-requirement count is not a linear
schedule estimate. The earlier provisional 4–8 week estimate is not a commitment.

The [issue plan](github-issues.md) and live GitHub review retain **#44 and #45
as open**. **#46 closed on 20 October** after genuine source revalidation and
[unchanged-client access acceptance](../validation/2026-10-20-office-access.md).
A separate 22 October 12:06 UTC receipt found both filesystem access leases
expired and normal/admin reads unavailable again. Genuine provider scans
subsequently resumed independently. At **15:48:54 UTC**, unchanged Codex and Grok
Build identities passed list, fetch and lexical recall in all four combinations
with the two filesystem spaces, each returning its sampled memory. This restores
observed reader access while preserving the earlier expiry episode. A subsequent
20-minute observer completed at 16:11:54 UTC: all 21 samples had current leases,
with renewals beyond their initial expiry. C01/C09 still require longer-term
availability, source-host custody and complete-inventory acceptance. The separate
administrator setup restored the existing cloud source runners; this verifier
made no source, grant or scan changes. The intentionally paused local
publisher has a separate guard/QC prerequisite. An unavailable source host cannot
be repaired by inventing a permission lease.
Complete an unblocked part or the next independent milestone while retaining
that dependency and resuming it after an observed change.

The current public distribution is **4.44.2**, source
`3bdb3371ccd31bcf095d2e25a4b7d8263260b735`, published on 22 October at
10:18:29 UTC; see its [publication receipt](../validation/releases/4.44.2-publication.json)
and [release status](../RELEASE_STATUS.md). Native release gates, independent
artifacts, all six public-update targets and website synchronization passed.
The [release-status reporting correction](../validation/2026-10-22-release-check-accounting.md)
confirms that all 12 Product checks already passed inside the exact-source
release workflow by **09:35:17 UTC**, before publication. The status reporter
had omitted that evidence because no separate CI run existed. The additional
[39815622908](https://github.com/Perseusxrltd/mnemion/actions/runs/39815622908)
retains its PyPI timeout, stalled runner and single retry of the two unfinished
checks; it was not the original product acceptance. The automatic
[release status](../RELEASE_STATUS.md) supplies its current outcome.
Separate main source `38eb3021d517a193b47501f902b4595a49d44178`
passed [CI](https://github.com/Perseusxrltd/mnemion/actions/runs/39795183358) and
[Git website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/39795183441);
its earlier [native attempt 2](https://github.com/Perseusxrltd/mnemion/actions/runs/39795261005/attempts/2)
finished with three installed targets passing, both Windows targets failing the
policy comparison and Apple Silicon never acquiring a runner. The
[Windows path comparison correction](../validation/2026-10-22-native-policy-path.md)
has local evidence. The corrected installed qualification is
[39814732365](https://github.com/Perseusxrltd/mnemion/actions/runs/39814732365),
on `d358726366bfef0e4cbddcb69741512de1d2fd78`; full six-target qualification
remains pending.
Those checks belong to different sources. Full durable capture
**L1 remains unreleased and unaccepted**; retain its
[remaining acceptance work](../research/2026-10-21-durable-capture-implementation.md#required-before-l1-can-be-released)
and all L1–L7 scope.

Actual installation acceptance remains separate. The VPS was observed on
**4.44.2 at 12:06 UTC** on 22 October. At **15:32:08 UTC**, the actual Windows app
still ran **4.44.1**, with 4.44.2 downloaded and ready, waiting for its configured
600 seconds of computer inactivity; only 35 seconds had elapsed. The normal
guarded agent restart subsequently installed **4.44.2**, observed at
**16:05:11 UTC**. The [paired acceptance](../validation/2026-10-22-4442-live-acceptance.md)
completed at **16:35:34 UTC**, retaining the three identities, exact witness
memories, protected human login, bookmarks and preferences. All **41** isolated
lab requests passed with complete cleanup. Its first observer stopped for
inspection of intervening authorized agent-space additions; those exact
additions were reconciled against their original setup/grant records before
resuming acceptance. The original baseline and failure remain preserved.
Unattended idle restart is not claimed. The earlier
[4.44.0 paired receipt](../validation/2026-10-21-444-acceptance.md) retains its
50-request pass, preserved identities and complete cleanup; it does not prove
the later update or unattended idle restart. The
[4.43 backup/contention receipt](../validation/2026-10-21-443-acceptance.md)
preserves independent delivery proof, its repaired mirror-capacity failure and
the still-unexplained earlier 4.41 HTTP 503. Private dated observation filenames
and the source-access/recovery receipts are recorded in the [issue plan](github-issues.md).

| Requirement | Missing acceptance work | Dependencies | Required proof |
| --- | --- | --- | --- |
| F02 | Complete shared administrator takeover, company joining and supported source/agent journeys as one organization setup. | A01, A06, A12, C01, C09, U01 | End-to-end human and agent organization journey with real source permissions. |
| F03 | Complete the remaining v3 parity inventory; exercise uncommon Obsidian layouts and interrupted/large migrations; record deferred legacy behaviors explicitly. | F07, A13 | Versioned parity matrix and native interrupted-migration/recovery receipts. |
| F05 | Exercise supported OS minimums and company-restricted devices; verify ARM backend compatibility and document measured limitations. | U04, U06, R02 | Actual OS/device matrix, installer/startup/update receipts and minimum versions. |
| F06 | Measure local and remote-client workloads on modest RAM/CPU hardware; publish supported minimums and behavior under pressure. | R01, R02, R04 | Measured RAM/CPU/latency with supported corpus and hardware sizes. |
| F07 | Exercise large-workspace upgrade compatibility and independent recovery across schema generations; maintain portable evidence and format contracts. | F03, A09, A13 | Large-corpus upgrade/restore receipts with exact revisions and deletion/access state. |
| F08 | Audit every remaining human workflow against its agent operation; finish delegated hosting, provider approval and complete recovery parity. | A06, A12, A13, C01, U02 | Paired app/CLI/API/MCP acceptance with the same identities and error/recovery paths. |
| C01 | Finish live-provider sign-in, source selection, permission mapping, restart, reconnect and removal for Git, Drive, rclone and custom company sources. | A01, C09, U02 | Actual provider receipts and revoked/changed-permission recovery, not configuration fixtures only. |
| C02 | Complete approved Slack live event/reconnect/retention acceptance; define and implement additional requested messaging adapters with their own permission contracts. | C01, C09 | Live messaging history/thread/event, revoke and retention acceptance. |
| C03 | Complete opt-in native capture journeys for supported AI apps; show gaps and unavailable record types; verify offline/restart checkpoints and source deletion. | C04, C05, C07, C08 | Provider-specific end-to-end capture and exact selected-message/trace provenance. |
| C04 | Complete actual Claude application/plugin installation, permitted capture, reconnect and public listing acceptance. | C03, C09, A08 | Actual Claude client/capture receipts; listing acceptance where required. |
| C05 | Complete public OpenAI distribution and account attribution; verify supported Dot integration from primary documentation and an actual client; finish native capture/reconnect. | C03, C09, A08 | Named OpenAI client OAuth/tool/capture receipts beyond existing ChatGPT profile proof. |
| C07 | Run actual Hermes/OpenClaw clients against installed native profiles; complete supported capture, runtime/plugin extensions and removal/recovery journeys. | C03, C09 | Actual provider runtime acceptance, beyond manifest/configuration checks. |
| C08 | Show per-source capture/delivery/indexing watermarks, gaps, exclusions and removal; prove deduplication/provenance through offline replay and failed scans. | C01, C03 | Source-to-memory accounting against an independently known source inventory. |
| C09 | Complete company-managed source approval and individual hosted identities across devices; verify live revocation during capture and subsequent source revalidation. | A01, A08, A11 | Multi-person/device permission tests, including the [completed filesystem issue 46 acceptance](../validation/2026-10-20-office-access.md) and the remaining company/fleet cases. |
| A01 | Finish guided company hosting and identity-provider onboarding from a clean device through invited-user joining and recovery. | A05, A08, U01 | Real company provider and new-member app/agent journey on supported platforms. |
| A03 | Finish company connection policy and delegated recovery/host operations with explicit operator roles and auditable revocation. | A11, A12 | Administrator UI/agent delegation and revoke/expired-authority acceptance. |
| A04 | Finish independent vault-key custody, managed rotation and company vault policies; prove recovery without reintroducing revoked access or deleted values. | A09, A11 | Multi-custodian key rotation/export/restore and current-denial receipts. |
| A05 | Complete live public-route/tunnel and private-network configurations, including proxy/firewall/outage recovery under company policies. | A01, U04 | Real endpoint reachability/reconnect with validated TLS and explicit host ownership. |
| A06 | Complete product-managed host custody and delegated wake/takeover; connect independent backup delivery evidence to recovery without the original agent. | A11, A12, A13 | Owner journey with original agent absent; real host control and fresh independent restore. |
| A07 | Finish independent online host/recovery management and company hosting acceptance, maintaining a working desktop equivalent. | A01, A06, A12 | Web and desktop admin access while the originating client is offline. |
| A08 | Complete named-provider/company onboarding and directory acceptance; verify refresh, consent, attribution, expiration and revocation in actual clients. | A01, C04, C05, C07 | Provider-specific end-to-end OAuth receipts beyond generic issuer fixtures. |
| A09 | Finish independent backup delivery verification, recovery custody and host/provider cutover under current writes, revocations and deletions. | A11, A13, F07 | Independent encrypted restore and reconciliation with no divergent live writer. |
| A10 | Complete the current publication audit and automate ongoing documentation, secret/dependency/license checks without exposing private deployment evidence. | U09 | Clean tracked public source, verified release inventory and appropriate security/license checks. |
| A11 | Finish recovery-custodian policy and delegated host operators; test loss of the creating agent, operator retirement and protected final administrator. | A03, A12 | Independent admins can complete supported host recovery with explicit authority. |
| A12 | Complete approved host actions, boot registration and safe takeover from another enrolled device, with independent location/key custody and no split writers. | A05, A09, A11 | Offline-primary recovery journey and fencing of the old writer. |
| A13 | Finish guided source-only recovery and full-backup inventory verification; reconcile writes, permissions and denials while preserving the distinction between mirrors and backups. | F03, F07, A09 | Interrupted source/journal and full-host restores with measured completeness. |
| U01 | Complete clean-device company hosting/provider approval and independent recovery entirely through the onboarding UI, with matching agent operations. | A01, A06, A13, C01, U02 | Fresh Windows/Mac/Linux user journeys without undocumented operator steps. |
| U02 | Finish remaining provider approval and host takeover flows with resumable app controls, explicit ownership and full agent parity. | A03, A12, C01, F08 | Complete setup/reconnect/removal/repair journeys for every required configuration surface. |
| U04 | Verify machine boot and unattended server startup/recovery, including company policy and restored source runners on each supported OS. | F05, A12 | Actual reboot and login/startup receipts, separate from process-only restarts. |
| U06 | Complete Windows/Compose/fleet server adoption and update policy; expose guarded migration-bearing upgrades through supported app/agent controls. | U04, A09, A12 | Actual compatible updates and guarded schema upgrades with pre/post backup and rollback evidence. |
| U09 | Keep affected guides, requirements, release notes and bundled help tied to each reviewed change; verify automatic public site/download/status propagation. | A10 | One automated release-to-website/in-app-documentation cycle with link/contract checks. |
| U10 | Complete the remaining requested product roadmap after the already published shared-platform first release. | F02, F08, U01, C01, R06, V04 | Parent completion requires all retained acceptance work; version numbers alone do not close it. |
| U11 | Extend the real Windows lab to representative workload/capacity and guided recovery while retaining bounded synthetic writes, independent credentials and live update receipts. | R04, A09, U06 | Measured capacity, recovery and actual installed-update cycles with complete cleanup. |
| R01 | Compare approved CPU/remote embeddings on representative languages, domains, latency and RAM; retain pinned model choice, rollback and explicit provider costs. | V02, R02 | Published repeatable real-model baselines with supported hardware and data provenance. |
| R02 | Measure resource policies on lower-end and mixed fleet hardware; verify dynamic pressure/limit changes and publish minimums and external-model ownership limits. | F05, R04 | Actual RSS/CPU/pressure/admission observations for API, workers, database and models. |
| R04 | Measure representative ingestion, retrieval, queue fairness, bandwidth, saturation and recovery while ordinary memory operations remain available. | R02, C08, U11 | Bounded load/recovery traces with tail latency, bytes, backlog and no accepted-data loss. |
| R06 | Complete held-out organization/contradiction/staleness evaluations, relationship effects and calibrated verification; distinguish proposals and exact evidence from truth. | V02, R01 | Versioned held-out corpus, baselines, quality/error/rejection and rollback measurements. |
| V01 | Complete fleet/capture/bandwidth/resource-policy insights and exportable measurements; connect the new librarian coverage view to broader operations. | C08, R02, R04 | App/agent measured dashboards on representative workspaces, including error and stale-data states. |
| V02 | Expand representative live model/provider/hardware baselines and interrupted-run/recovery drills; keep comparisons reproducible and exportable. | R01, R04 | Pinned corpus/model/runtime reports and recoverable evaluations on actual configurations. |
| V03 | Expand entity/term relationships with exact source provenance and visible ambiguity/uncertainty; validate resulting retrieval/graph usefulness. | R06, V02 | Evidence-linked graph/wiki cases with contradiction, deletion and revocation checks. |
| V04 | Complete large-map clustering and incremental subscriptions for online/desktop 3D views, preserving accessible 2D/list fallback and permissions. | V03, R04 | Measured large-corpus interaction/refresh and current-access tests on supported devices. |
| V05 | Add event replay, cross-space aggregation and capture coverage so map activity explains actual agent work with its attribution and evidence. | V01, V03, V04, C08 | Time/replay and current-permission proof across several agents/spaces. |

The [layered-librarian stages](../research/2026-10-20-layered-librarian.md#delivery-sequence-and-research-watch) remain additional planned scope. Capture controls, coverage statistics and the research watch do not establish autonomous cross-layer consolidation.
