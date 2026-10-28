# GitHub issue resolution plan

Reviewed 28 October 2026; earlier dated checkpoints remain below. Every open
report remains part of the product work.
The [automatic maintenance board](../MAINTENANCE_STATUS.md) supplies current
GitHub state and new comments; this file records engineering scope and evidence.
The [full requirements](../PRODUCT_REQUIREMENTS.md) remain broader than these
individual reports. Closing a bounded issue does not finish its entire product
requirement or prove a customer's installation upgraded.
The generated [release status](../RELEASE_STATUS.md) records current published
availability and release gates. The [delivery checkpoint](completion-audit.md)
keeps dated public-release and actual-deployment acceptance separate.

| Issue | Implemented evidence | Remaining acceptance or work |
| --- | --- | --- |
| [#47 · Multi-agent field reliability](https://github.com/Perseusxrltd/mnemion/issues/47) | [4.46.43 source qualification](../validation/2026-10-28-field-reliability.md) covers statement-scoped search/audit permissions, bounded inventories, MCP response-size control, activity pages/filters, no-op journal suppression and tenant-role hints. | **Open.** Publish and validate the reporter's scopes/latency, source diagnostics, duplicate-source handling, vault access and claim/librarian adoption. The [complete field plan](multi-agent-field-readiness.md) preserves every item. |
| [#48 · Standalone office and vault interoperability](https://github.com/Perseusxrltd/mnemion/issues/48) | Reuses the reported #47 baseline and its partial source repairs; existing revision, vault and KeePass paths are retained. | **Open.** Native tasks with owner/next action/due/state, accepted ledger/dispatch migration, immediate index criteria, per-key metadata-only vault access, all four named format families, 50-entry lossless round trips and ten-conflict bidirectional sync remain in the [field plan](multi-agent-field-readiness.md). Working files remain authoritative. |
| [#46 · Existing office corpus access](https://github.com/Perseusxrltd/mnemion/issues/46) | [20 October access acceptance](../validation/2026-10-20-office-access.md) passed on 4.41 after genuine complete source scans. All six Codex/Grok client-space combinations passed list, fetch and lexical recall with unchanged credentials; source identities, intended bindings and the original failed receipt were retained. On 22 October at 15:48:54 UTC, unchanged Codex/Grok Build identities again passed list, fetch and lexical recall for both filesystem spaces: four combinations, all HTTP 200, each with the sampled memory in recall, after independent genuine provider revalidation. | **Closed** at 15:42:24 UTC on 20 October. The 22 October 12:06 UTC expiry and unavailable reads remain historical evidence; reader access recovered at 15:48:54 UTC. The independently verified 16:40 UTC VPS source-storage/capture cutover resolved the former unavailable cloud-source-host dependency. Continuing availability across lease windows, broader source-host/client platform journeys and complete original inventory remain C01/C09 work; full cloud history remains #44. No source fix or restart is attributed to this read-only verification. |
| [#45 · Guarded live upgrade and paused note publishing](https://github.com/Perseusxrltd/mnemion/issues/45) | [4.41 eventual paired acceptance and backup delivery](../validation/2026-10-20-441-acceptance.md), [4.43 paired/contention acceptance and independent backup delivery](../validation/2026-10-21-443-acceptance.md), and [4.44 paired acceptance](../validation/2026-10-21-444-acceptance.md) passed within their recorded scope. Earlier stopped drivers, the unexplained 4.41 semantic HTTP 503 and the repaired backup-mirror limit remain preserved. The 22 October 4.44.2 publication is a historical checkpoint. Windows moved from the recorded 4.44.1/ready state to actual 4.44.2 through a normal guarded agent restart. [Paired acceptance completed at 16:35:34 UTC](../validation/2026-10-22-4442-live-acceptance.md): three unchanged identities, exact witness memories, protected login/bookmarks/preferences and 41 isolated requests with complete cleanup. The VPS was also on 4.44.2. The later 4.45.0 publication and six public-update targets passed. [Paired acceptance completed at 20:24:17 UTC](../validation/2026-10-22-4450-live-acceptance.md), retaining identity/access, exact witnesses and protected human login/settings, verifying fresh pre/post-schema backups and completing 42 isolated requests with no cleanup remaining. | **Closed on 26 October at 01:21:46 UTC** against the [five original deployment criteria](../validation/2026-10-26-issue45-acceptance.md). [Actual 4.46.6 paired acceptance](../validation/2026-10-24-electron-security-4466.md) retained identities, exact evidence and settings through 45 isolated requests with complete cleanup. Fresh native backup and [independent isolated restore passed on 24 October](../validation/2026-10-24-4465-backup-acceptance.md); the supported runbook is updated. Earlier stopped observers, reviewed role additions and failures remain historical evidence. Broader fleet/recovery, representative-load and provider acceptance remain open. The PC note publisher remains deliberately paused pending its separate guard/QC review; healthy API/journal state does not prove new local-note freshness. Unattended idle restart is not claimed. |
| [#44 · Actual Grok Bot cloud integration](https://github.com/Perseusxrltd/mnemion/issues/44) | Public HTTPS/OAuth and Grok Build have separate evidence. The native packages and accurately labeled Bot guide introduced in 4.39 are available. The independent 22 October 16:40 UTC source-storage/capture cutover to the VPS passed copied-root checksums, defined source inventories and existing team-principal data operations, preserving source and principal identities. | **Open.** Finish actual cloud-client scoped authentication, native tool/read/save and restart acceptance; existing team-principal data-operation proof does not complete those client journeys. Source storage and capture now run on the VPS, while Grok execution, native session databases and app connections remain on the original computer. Continuous availability, additional client/platform enrollment and complete cloud/native-history inventory remain open. Grok Build TOML or an ordinary Grok web connector does not establish cloud Bot acceptance. The former unavailable source host is historical, not the current storage dependency. |
| [#43 · Bad text file stops an entire source](https://github.com/Perseusxrltd/mnemion/issues/43) | 4.21 isolates invalid UTF-8/binary/oversized ordinary text and reports scoped source health through the app, recall, health, SDK and agents. [94 focused Python cases and UI evidence](../validation/2026-10-19-source-health.md). | **Closed** against published 4.22 after all six public installed-update checks passed. The frozen 4.21 candidate was withheld after outdated migration expectations failed CI. Structured journals intentionally retain complete-inventory checks. |
| [#42 · Native SSH journal and local receipt wording](https://github.com/Perseusxrltd/mnemion/issues/42) | Published 4.20 adds scoped deploy keys, pinned hosts, private snapshots and explicit destination kinds. [Real OpenSSH/Git/API read-back, revocation, conflict and retry evidence](../validation/2026-10-19-journal-ssh.md). | **Closed** after public release and all six installed-update checks passed. Native SSH credential/provider enrollment remains broader platform acceptance. |
| [#41 · Growing JSONL capture](https://github.com/Perseusxrltd/mnemion/issues/41) | Published 4.17 supplies a separate bounded adapter, complete-record checkpoints, per-file scopes, provenance, truncation/rotation handling and permission/deletion checks. [Real HTTP/PostgreSQL cases](../validation/2026-10-19-live-conversations.md). | **Closed** against verified 4.17. Full fleet throughput and zero-read append proofs remain roadmap work. |
| [#40 · Grok Build session/update format](https://github.com/Perseusxrltd/mnemion/issues/40) | Published parser/live-capture work recognizes ACP message chunks, retains session/source identity and excludes non-message events. 4.17 [tests repeated event IDs across fragments and scans](../validation/2026-10-19-live-conversations.md). | **Closed** against verified 4.17. A native Grok plugin is a separate requirement. |
| [#39 · Additive Git write-back](https://github.com/Perseusxrltd/mnemion/issues/39) | 4.15–4.20 provide transactional capture, scans, scheduled/important delivery, exact event receipts, filing/archive, rollover, source replay and host setup. 4.22 adds [existing native-memory backfill](../service/git-journal.md#including-existing-native-memories). Source 4.27 carries 4.25's [reviewed older-buffer import](../service/legacy-buffer.md) and 4.26's [editable native journal recovery](../service/journal-recovery.md), with actual publisher-to-recovery checks, original IDs or explicit copies, withdrawals/quarantines and private app/SDK/agent controls. | **Closed** against published 4.27 after all six public installed-update checks passed. The 4.27 recovery limit was 1 MiB/1,000 identities. Source 4.29 adds resumable complete uploads up to 2 GiB/100,000 identities; broader provider adoption remains product roadmap work; the requested bounded write-back/recovery path is implemented. The unavailable original office database/vault is a separate data-recovery incident. |
| [#38 · Full host loss and independent recovery](https://github.com/Perseusxrltd/mnemion/issues/38) | [Host packages, encrypted custody and restore](../service/host-recovery.md) preserve identities, apply later denials and recreate selected source runners. Source 4.27 fixes locale portability after a [real Git-to-independent-PC restore](../validation/2026-10-19-portable-host-recovery.md). Existing Codex/Grok keys, exact memories, API/MCP access, native Windows access and restart continuity passed. | **Closed** against published 4.27 after all six public installed-update checks passed. Source 4.30.2 adds [desktop database import from server packages](../service/desktop-host-recovery.md). Provider/OS provisioning, alert delivery, broad custody UX and the original office's missing recovery inputs remain separate requirements; they do not negate the documented idempotent host-package path requested here. |
| [#32 · Encrypted secrets vault](https://github.com/Perseusxrltd/mnemion/issues/32) | The reporter confirmed the 4.12 vault. Published 4.24 carries [KDBX 4 transfer](../service/keepass.md), reviewed entry/field/custom-property mapping, default name masking and no plaintext temporary files, with independent fixtures and actual permission/transaction checks. | **Closed** against published 4.24 after all six public installed-update checks passed. The frozen 4.23 candidate was withheld for an Intel Mac dependency issue. Broad key custody/rotation remains a separate product requirement. |
| [#31 · Recency and superseded answers](https://github.com/Perseusxrltd/mnemion/issues/31) | Published 4.24 makes recent ordering honor archive preferences within comparable matches and preserves strong historical evidence. [Actual pinned-model comparison](../validation/2026-10-19-retrieval-archives.md) covers the reported pattern before and after indexing, alongside existing passage chronology. | **Closed** against published 4.24 after all six public installed-update checks passed. The current private encrypted corpus was not replayed; timestamps and version labels still do not prove truth. Broader authoritative supersession remains roadmap work. |
| [#17 · Natural-language retrieval](https://github.com/Perseusxrltd/mnemion/issues/17) | Published 4.24 retains keyword support in recent comparisons for questions with little cross-language token overlap. [Thirteen labeled questions over fifty synthetic documents](../validation/2026-10-19-retrieval-archives.md) use the real pinned multilingual model, including an eight-decision Markdown row. | **Closed** against published 4.24 after all six public installed-update checks passed. All thirteen target documents reached the top four with the full index; one recent-order target remains second. Broader held-out model/language/provider quality remains separate. |
| [#18 · ChatGPT OAuth acceptance](https://github.com/Perseusxrltd/mnemion/issues/18) | [Actual signed-in ChatGPT acceptance](../validation/2026-10-20-chatgpt-acceptance.md) passed on 20 October against service 4.33: OAuth setup, personal login, explicit account/space permission review, installed plugin, 16 tools and an authenticated profile-only request. Earlier separate scoped protocol tests retain denied-write, refresh and revocation evidence. | **Closed** by automatic reconciliation against verified public 4.37. Public Perseus XR plugin distribution, other clients, capture and broader identity policy remain roadmap work. |
| [#4 · Hosted-agent delegated access](https://github.com/Perseusxrltd/mnemion/issues/4) | OAuth and browser authorization coexist with scoped bearer and local stdio paths. [Actual public HTTPS sign-in](../validation/2026-10-20-live-hosted-signin.md) passed PKCE, consent, scoped MCP discovery/read, refresh rotation and immediate grant/session revocation. [The shared host and Windows app](../validation/2026-10-20-shared-workspace-429.md) retained access through 4.29. | **Closed** against verified 4.29. The report asks for general delegated access, which the live protocol proof establishes. The separate ChatGPT UI acceptance for #18 subsequently passed on 20 October; see its own dated record. |
| [#3 · Native remote access](https://github.com/Perseusxrltd/mnemion/issues/3) | Published 4.4 provides [app-managed ngrok and existing HTTPS routes](../service/remote-access.md), private operator controls, supervised reconnection, route diagnostics and public sign-in addresses. [Actual TLS/proxy and native SDK validation](../validation/2026-10-15-native-remote-access.md), the independently hosted public workspace and a fresh real scoped diagnostic fulfill the [original scope and diagnostic follow-up](../validation/2026-10-20-remote-access-issue.md). | **Closed** against verified 4.29 at 02:54:56 UTC on 20 October. Live ngrok-account enrollment and provider outage recovery remain separate A05/A08 acceptance, alongside host wake/failover. This association does not claim those provider tests or ChatGPT UI acceptance. |

`deploy/issue-releases.json` contains only reviewed associations for addressed
reports. The status workflow closes them only after matching public release and
upgrade evidence. Reopened reports remain open for new investigation. No issue
body is executed, and no generated status script decides feature completion.

The 20 October signed-in client check completed **#18**'s acceptance. The reviewed
4.37 association closed it through verified-release reconciliation. Subsequent
real-deployment report **#44 remains open** with the acceptance above.
**#45 closed on 26 October at 01:21:46 UTC** against its
[five original deployment criteria](../validation/2026-10-26-issue45-acceptance.md),
including the explicit publisher pause and its separate review prerequisite.
**#46 is closed**
after its independently observed 20 October access acceptance. The 22 October
lease expiry and subsequent reader recovery preserve the need for sustained
availability, broader source-host/client platform journeys and complete-inventory
acceptance under C01/C09. The independent 16:40 UTC VPS cutover resolved the former
source-storage dependency without changing that historical issue state. Current GitHub state remains on
the automatic board.
#3 is closed against reviewed evidence for its original remote-access and
diagnostic scope; live ngrok-account/lifecycle acceptance stays
on the broader roadmap. #4 is closed against its completed general OAuth proof.
Current [ChatGPT setup instructions](../service/hosted-agent-sign-in.md#chatgpt-custom-mcp-connection)
follow the official Plugins/DCR flow reviewed on 20 October; no browser result is invented.
Issues #38 and #39 joined #17, #31, #32, #40, #41, #42 and #43 as closed through
the verified-release workflow. Current counts continue to come from the
automatic maintenance board, not this dated checkpoint.

The earlier 4.37 pre-migration failures, bounded snapshot timeout/busy repairs,
separate Git delivery repair and independent verification remain historical
evidence for #45. The [bounded operator turn](../service/managed-upgrades.md)
introduced in 4.39 remains part of the guarded update path; neither version
label describes the current public or installed state.

The 22 October deployment observations are retained privately in
`Agent-Shared/data/2026-10-22-1206-mnemion-grokbot-access.json` (VPS 4.44.2,
source scopes and read outcomes at 12:06 UTC) and
`2026-10-22-windows-capture-capacity/windows-installed-observation-1533.json`
(Windows app status at 15:32:08 UTC). The former found current Git source leases
and 754 accessible indexed records, alongside two expired filesystem leases;
that accessible subset does not establish the complete office or cloud inventory.

The subsequent `2026-10-22-source-lease-recovery/current-reader-access.json`
records the passing four-combination reader check at **15:48:54 UTC**. Both
filesystem scopes had current leases and completed inventories. Valid scope/sync
observations in `source-access-before.json` show genuine scans completing around
15:42–15:43 UTC with requested and completed generation **2**. That preliminary
file's list HTTP 404 values used an unregistered URL and are invalid access
evidence; its valid scope/sync observations remain retained. The corrected reader
receipt uses registered routes and retains the observer corrections. This
verification requested no grants, source scans or runtime changes and made no
source fix or source restart; the observed recovery occurred independently.
The 20-minute observer finished at **16:11:54 UTC** with **21 samples**, all
scopes current and renewed beyond their initial expiry, recorded in
`freshness-watch.receipt.json`. At that observation checkpoint, the separately
authorized administrator setup had restored the cloud source runners; this
reader observer made no changes. Those observations predate the source-storage
cutover below. Longer-term availability, broader client/platform coverage and the
complete original inventory remain unproven. The PC note publisher remains
deliberately paused.

The independent source-storage/capture cutover completed by **16:40 UTC** on
22 October. Private `grok-vps-migration-20261022/REPORT.md` and shared note
`2026-10-22-1640-grok-memory-vps-cutover.md` retain zero checksum differences across
four moved roots, 1,409 operations and 16 office-file records, and the unchanged
four curated records. Existing team-principal search/create/read/revise/forget
and cross-reader checks passed. Source capture now runs on the VPS; old cloud
capture is disabled, and original paths remain through an authenticated,
supervised mount. Existing source and principal identities were preserved.
Grok execution, native sessions and app connections remain on the original
computer. Its running-app native-state copy is not a transactional database
snapshot; new memory folders outside the mounted paths still need enrollment.
The 249 archive-only operations records were already absent before cutover and
remain in encrypted history. Defined copied-root inventories do not establish
complete provider/native history or continuous future availability.

The actual Windows 4.44.2 transition is retained in
`2026-10-22-shared-host-4442/guarded-resume-20261022-1604.log` and
`guarded-windows-restart.accepted.json`. Its follow-up stopped on an unrecorded
authority addition: separate authorized Hermes/Grok setup created new spaces
after the 09:09 UTC baseline. Their original setup documents and dated grants
were verified, alongside the reappearing historical filesystem reader bindings.
Only those exact additions were allowed. The resumed paired acceptance passed
at 16:35:34 UTC without repeating the update. The original baseline and stopped
observer remain; additional visible spaces are not described as unchanged
authority. The release automation now generates its public report from the
validated receipt for subsequent updates.

The **4.45.0 publication on 22 October at 19:47:33 UTC** is recorded in its
[38-asset publication receipt](../validation/releases/4.45.0-publication.json),
for frozen source `d8083b068ea0d6866747b8128b1edd8b5f256f69`.
[Public update run 39843181077](https://github.com/Perseusxrltd/mnemion/actions/runs/39843181077)
passed all six targets and reconciliation; the
[automatic website run 39843176416](https://github.com/Perseusxrltd/mnemion/actions/runs/39843176416)
also passed. Current availability continues to follow generated release status.

The private `2026-10-22-shared-host-4450/host-upgrade.receipt.json` records the
reviewed 4.44.2→4.45.0 host upgrade from **19:53:07 to 19:58:10 UTC**, applying
migrations **030–034** without database restoration. Fresh encrypted pre-schema
backup delivery passed independent verification at **19:53:04 UTC**.
`live-after.json` passed the identity, witness, access and protected human-login
checks at **20:14:15 UTC**. `guarded-windows-restart.verified.json` records the
actual Windows app and service on **4.45.0 at 20:15:18 UTC**, retaining the
protected human login, bookmarks and preferences through the app's normal
restart guards. This is not unattended idle-restart evidence.

The observer stopped at **20:01:01 UTC** on roles that differed from its
**18:28 UTC** baseline. Independent authorized administration had made those
ten exact promotions at **18:38–18:45 UTC**, before the **19:53 UTC** upgrade.
`authorized-config-observations.json` reconciled the original grants, mutation
records and effective-role readback at **20:13:55 UTC**; the matching
`authorized-access-expansion.json` binds that evidence by digest. This review
made no remote mutations. The resumed access check preserved identities,
stronger existing roles, exact witnesses and the human login, permitting only
the recorded promotions. The original baseline and
`inspected-failure-200101/` observations remain historical evidence, separate
from the earlier 4.44.2 observer's reviewed additions. No uncertain host upgrade
was replayed to resolve the comparison.

The [final 4.45.0 paired acceptance](../validation/2026-10-22-4450-live-acceptance.md)
completed on **22 October 2026 at 20:24:17 UTC**. The earlier controller checkpoint,
`observing-after-schema-backup` at **20:16:05 UTC**, remains historical evidence.
The final `2026-10-22-shared-host-4450/acceptance.receipt.json` records **42**
isolated lab requests, **zero pending cleanup**, **zero production memory writes**
and **zero cloud model calls**, with all three identities, exact witnesses and
the protected human login/bookmarks/preferences retained.
`post-upgrade-delivery.json` verifies fresh **4.45.0** snapshot and ledger delivery
at **20:24:17 UTC**, including the remote commit and independent GitHub manifest
read. Fresh pre/post backup verification for this migration is complete.
The historical 4.44.2 41-request pass remains separate from this update's lab.
At that 22 October checkpoint, independent restore/recovery, representative load,
provider acceptance and the publisher's review remained open, as did #44/#45.
The later [isolated restore passed on 24 October at 00:15:23 UTC](../validation/2026-10-24-4465-backup-acceptance.md),
following accepted native backup creation and independent verification.
[#45 closed on 26 October](../validation/2026-10-26-issue45-acceptance.md);
#44, broader fleet/recovery, representative-load and provider acceptance remain
open. The PC note publisher remains deliberately paused pending its separate
guard/QC review; API and source health do not establish fresh local-note publication.
