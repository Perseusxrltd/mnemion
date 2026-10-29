# Multi-agent field readiness

Reviewed **29 October 2026** against [issue 47](https://github.com/Perseusxrltd/mnemion/issues/47)
and [issue 48](https://github.com/Perseusxrltd/mnemion/issues/48). Both reports
remain open. Their baseline is the reporter's **4.46.40** deployment; the
[maintenance board](../MAINTENANCE_STATUS.md) owns current GitHub state.

These reports extend the acceptance work of the
[66 retained requirements](../PRODUCT_REQUIREMENTS.md). The new native task and
handoff workflow belongs to F02/F08/A03; the named vault formats and lossless
bidirectional sync extend A04/C01/A09. These are additional requested work,
not capabilities established by the current memory or KeePass interfaces.
No original requirement text, state or completion count changes here.

## Operational repairs

The 17:01 UTC follow-up to issue 47 adds **four simultaneous read-only MCP
searches** failing on 4.46.40: two `generation_changed` and two
`database_unavailable`, after 40–92 seconds, despite no model-setting change.
Retain a four-session regression with the reporter's scope, plus serial controls;
an unchanged generation must not produce a settings-change error. Source-file
freshness also remains open. The original query improvement needs a published
host upgrade and these actual-client checks before the issue can close.

The [scope-conflict correction](../validation/2026-10-29-search-scope-conflicts.md)
reproduces one misleading error: new readable spaces or an expired source lease
previously returned `generation_changed` without a model change. Source now
returns the distinct `scope_changed` conflict while retaining both permission
checks. All 41 focused scope/reindex/retrieval tests pass. This does not identify
the cause of the reported live failures or replace their field acceptance.

The [29 October four-client comparison](../validation/2026-10-29-mcp-field-sessions.md)
records lexical requests on 4.46.40 and after the actual 4.46.44 host upgrade.
Observed mean latency fell from **55.49 to 12.70 seconds**, or **77.1%**, in this
one uncontrolled comparison using one normal principal. Post-upgrade backup was
still pending during the probe. The original fixture failure is preserved;
default hybrid, cross-user and reported search-failure acceptance remain open.

The [later field-operations report](../validation/2026-10-29-field-operations.md)
adds one serial and four concurrent default-mode searches with `mode` omitted,
eight visible activity scopes and separate offline model-policy observations.
Scope-count changes and unrecorded semantic-score values limit this evidence;
the full reported workload remains unqualified.

The [4.46.49 chronology correction](../validation/2026-10-29-selected-passage-candidates.md)
bounds passage eligibility to the already-selected candidates. Its real
PostgreSQL regression materialized one row instead of 33 for one candidate;
61 focused retrieval, chronology and permission checks passed. This removes
redundant database work. Version 4.46.49 is now public and its
[public update rehearsal](https://github.com/Perseusxrltd/mnemion/actions/runs/40820128156)
passed all six desktop targets; actual shared-host upgrade and production
latency acceptance remain pending. The separate 4.46.50 Linux x64
[backup-resume gate](https://github.com/Perseusxrltd/mnemion/actions/runs/40815491489/job/123273331148)
failed with no established cause; 4.46.49 remains the latest verified public release.

| Reported behavior | Current work and retained acceptance | Requirement |
| --- | --- | --- |
| Lexical recall took 18.2 seconds; hybrid averaged 8.3 seconds, with longer stalls. | Source 4.46.43 moves the existing grant/source/capture check into statement-scoped RLS sets. The [isolated query check](../validation/2026-10-28-field-reliability.md) passes; the 4.46.44 four-client comparison above records lower observed lexical latency under uncontrolled load. Full reported-scope lexical/hybrid latency, concurrency and clear bounded failures still require field acceptance. Preserve the report's under-60-second and improved hybrid criteria. | F02, R04 |
| Activity failed for two of eleven spaces. | The same migration optimizes reviewer-scoped audit and private-note reads. The normal principal's eight visible scopes returned eight initial pages in 11.354684 seconds. Scope lists changed from 11 to 9 to 8 to 11 without an identified cause. Verify all eleven reported spaces in one minute with the reporter's access; the smaller observed corpus does not satisfy that acceptance. | A09, R04, V05 |
| Only the latest 100 audit events were reachable; 87 were empty journal filing events. | Cursor pages and exact action filters are available in source, SDK, MCP and Studio. One additional published-host cursor page had zero overlap with its first page; complete-history acceptance remains open. Empty successful filing passes still update status/scheduling but add no new `journal.organized` event. Existing retained audit history is preserved. | F08, A09, V05 |
| Full memory pages exceeded the MCP response limit. | `summary=true` returns bounded inventories with a subject preview and no content, evidence or arbitrary metadata. A 100-record page passes the actual MCP path. The compact tool now permits an explicitly selected response allowance up to the existing 128 KiB ceiling; its default remains 16 KiB. | F08, R04 |
| Tenant-wide operations returned an unexplained 403 to a space administrator. | The source error now names the required tenant-administrator role. The [control guide](../service/agent-control.md) explains the two scopes. No role or permission is broadened. | A03, A11 |
| A suspended connector scope could not be identified or resumed from the caller's view. | Source 4.46.44 adds explicit, paged source diagnostics for tenant administrators and connector operators, with source/connector/operator identities, fixed reasons and supported recovery steps. Other callers get a clear control-scope explanation. The [qualification](../validation/2026-10-28-source-diagnostics.md) verifies privacy, current permissions and sticky pauses. Published-host and reporter acceptance remain open; a space role does not gain another connector's controls. | C01, C09, A03, A12 |
| A paused source had 40 duplicate copies and another source was mirrored in several spaces. | Open: identify shared source lineage and distinguish intentional copies from accidental duplicates. Preview changes, preserve provenance and current grants, and validate zero unintended duplicates after an approved managed-source cleanup. | C08, C09, R06 |
| All 1,342 observed claims remained `observed`; no librarian/evaluation/core-context work was visible. | Existing revision, review, librarian and evaluation interfaces remain. Open: make verification, supersession and contesting clear in app/MCP workflows; suggest revising an existing snapshot before creating another copy, with explicit provenance and approval. Nonzero counts alone are not quality evidence. | F08, R06, R07, V02 |
| A just-saved record should be immediately searchable and have zero pending records on the next search. | Lexical visibility and semantic indexing are separate current states. Retain the requested next-search/zero-pending acceptance for a declared model and workload; measure indexing completion and do not hide the pending counter. Longer model work must retain truthful status and bounded failure behavior. | C08, R01, R04 |

## Native tasks and handoffs

Issue 48 adds create, assign, update and close operations for task records with
an owner, next action, due date and state. Lists must filter by owner and state;
app and agent paths must share authorization, revision conflict checks and audit
history. Decisions retain author/date and a usable supersede/contest lifecycle.
Reports and facts should be recorded once and revised with durable identity.

This workflow is **planned**. The existing LEDGER, DISPATCH and working report
files remain authoritative until an accepted migration proves their complete
inventory, task states, ownership, links and recovery. There is no automatic
deletion or retirement of those files in the current hotfix.

## Vault interoperability and agent access

The requested formats are **1Password 1PUX/CSV, KeePass KDBX 4, Bitwarden JSON
(encrypted and unencrypted), and age-encrypted files**. Retain all of these
acceptance criteria for synthetic vaults only:

1. At least 50 entries per format, including custom fields, notes, TOTP seeds,
   attachments and folders/tags, import with 50/50 entries and zero field differences.
2. Import/export/re-import preserves entries, fields, attachment bytes and folder
   structure with zero differences. A format that cannot represent a field must
   disclose that limitation; silently discarding it cannot pass lossless acceptance.
3. One sync run carries a change from either side. Ten conflicting edits are
   surfaced with zero lost edits; no silent overwrite is acceptable.
4. Test-log inspection finds zero secret values in logs, activity, errors or
   ordinary MCP responses. An explicit, authorized, audited read is the only
   requested MCP value-disclosure path.

Existing [vault storage](../service/secrets-vault.md) and
[KeePass transfer](../service/keepass.md) are retained. They do not establish
this broader format matrix, attachment/folder round trips or bidirectional sync.
Each transport needs preview, private input/output handling, encrypted custody,
conflict recovery and its own acceptance evidence. Effort remains unestimated.

Issue 47/48 also asks for per-key vault access with metadata-only status, list
and audit over MCP. The [4.46.46 source](../releases/4.46.46.md) introduces a
separate, default-off metadata host setting, exact-key auditor grants with
optional expiry and version checks, and app/SDK/agent setup. Metadata access
does not confer read/write/manage permission over secret values. Historical
auditor grants are disabled on recovery. See the [vault guide](../service/secrets-vault.md).
Qualification, installed-host deployment and reporter acceptance remain required;
the existing MCP setting is not silently changed. Secret-bearing imports/exports
continue through protected private files, and all format/sync criteria above remain open.

## Release and field acceptance

The current hotfix is a useful operational batch, not closure of either report.
After its normal release checks, confirm installed versions, replay the bounded
reported app/agent journeys with current grants, and retain measured results.
No production memory cleanup, provider revalidation, vault synchronization or
real-secret test is authorized by this checklist alone. The deliberate PC note
publisher pause and independent [Grok Bot acceptance](github-issues.md) remain.

Independent manifest inspection now confirms post-upgrade snapshot and ledger
delivery, but the original snapshot unit failed at its 45-minute timeout after
delivery. The original driver was stopped for inspection without replaying the
migration or capture. Cleanup correction and full guarded-upgrade acceptance
remain open with [issue 44](https://github.com/Perseusxrltd/mnemion/issues/44);
the linked field report retains both delivery evidence and the original failure.

The [later scheduled-delivery gate](../validation/2026-10-29-backup-pack-index-repair.md)
held the shared host at 4.46.44 after Git pack-index damage prevented publication.
Index repair now passed in production with refs and archives preserved, but
publication exited 1. The follow-up guard stopped at 04:09:01 UTC without
requesting an upgrade action or extra capture. Ownership repair completed at
04:21:38; the corrected uploader was installed at 04:24:13. The fresh-backup
unit captured the snapshot and ledger successfully, but Git push timed out at
05:07:49 after the unchanged 600-second limit. The remote ref remained unchanged,
all three timers were restored, and the original guard stopped at 05:08:28 with
no actions requested. The publish-only follow-up at normal snapshot priority
also failed, before push, on optional multi-pack bitmap generation at 05:20:40.
Its timers were restored and guard stopped at 05:23:02 with zero actions.
Ordinary service-account Git connectivity passed with optional indexes disabled.
Fresh delivery, performance, migration 036 and installed vault-auditor acceptance
remain pending.

Ordinary Grok Bot cloud-computer wake and terminal inspection do not establish
native Bot authentication or MCP tools. The [documented connection route](../service/grok-bot.md)
still requires its separate cloud-client acceptance under issue 44.

V08 telemetry stays **Building**. Its full resource, wire, provider/privacy and
platform/release acceptance remains required before enabling collection or
sending its completion notification. Collection remains unavailable.
