# Multi-agent field readiness

Reviewed **28 October 2026** against [issue 47](https://github.com/Perseusxrltd/mnemion/issues/47)
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

| Reported behavior | Current work and retained acceptance | Requirement |
| --- | --- | --- |
| Lexical recall took 18.2 seconds; hybrid averaged 8.3 seconds, with longer stalls. | Source 4.46.43 moves the existing grant/source/capture check into statement-scoped RLS sets. The [isolated query check](../validation/2026-10-28-field-reliability.md) passes; actual all-space lexical and hybrid latency, concurrency and clear bounded failures still require release and field measurement. Preserve the report's under-60-second and improved hybrid criteria. | F02, R04 |
| Activity failed for two of eleven spaces. | The same migration optimizes reviewer-scoped audit and private-note reads. Verify all eleven reported spaces in one minute with the reporter's access. A different administrator's smaller accessible corpus is not that acceptance. | A09, R04, V05 |
| Only the latest 100 audit events were reachable; 87 were empty journal filing events. | Cursor pages and exact action filters are available in source, SDK, MCP and Studio. Empty successful filing passes still update status/scheduling but add no new `journal.organized` event. Existing retained audit history is preserved. Validate the published host. | F08, A09, V05 |
| Full memory pages exceeded the MCP response limit. | `summary=true` returns bounded inventories with a subject preview and no content, evidence or arbitrary metadata. A 100-record page passes the actual MCP path. The compact tool now permits an explicitly selected response allowance up to the existing 128 KiB ceiling; its default remains 16 KiB. | F08, R04 |
| Tenant-wide operations returned an unexplained 403 to a space administrator. | The source error now names the required tenant-administrator role. The [control guide](../service/agent-control.md) explains the two scopes. No role or permission is broadened. | A03, A11 |
| A suspended connector scope could not be identified or resumed from the caller's view. | Open: provide authorized administrators a scope identity, fixed reason, responsible authority and supported resume/revalidation action. Preserve provider leases, ownership, retained-custody rules and intentional pauses. A space role alone must not grant another connector's control. | C01, C09, A03, A12 |
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
and audit over MCP. Host policy and per-entry/per-key grants must both permit
the operation. The existing `vault_mcp_disabled` operator setting is not bypassed
by this hotfix. A dedicated metadata policy and clear owner setup remain open;
secret-bearing imports/exports continue through protected private files.

## Release and field acceptance

The current hotfix is a useful operational batch, not closure of either report.
After its normal release checks, confirm installed versions, replay the bounded
reported app/agent journeys with current grants, and retain measured results.
No production memory cleanup, provider revalidation, vault synchronization or
real-secret test is authorized by this checklist alone. The deliberate PC note
publisher pause and independent [Grok Bot acceptance](github-issues.md) remain.

V08 telemetry stays **Building**. Its full resource, wire, provider/privacy and
platform/release acceptance remains required before enabling collection or
sending its completion notification.
