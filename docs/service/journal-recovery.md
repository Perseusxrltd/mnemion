# Restore editable memories from a native journal

Source **4.26.0** adds reviewed recovery from a complete
[native Git journal](git-journal.md). Check the automatic
[published release status](../RELEASE_STATUS.md) for installer availability.
The same recovery is available in Studio, the Python/TypeScript clients and
private agent operations.

This restores the current memory projection. Use a
[complete workspace backup](recovery.md) to recover the original organization,
accounts, keys, grants, attachments, vault, evaluations and full native revision
history. A journal and its catalog cannot establish that an unavailable remote
host had no newer unpublished changes.

## In the app

1. Obtain a trusted, complete copy of the journal from the correct repository,
   branch and prefix. Keep the original bytes. Include `catalog.json`, all
   dated JSONL files, numbered continuations and `_archive`.
2. Create or select a **private native space** with only your administrator
   grant and no Git publication configuration. Open **Git journal → Restore a
   native journal**. Organization and space administration are both required.
3. Leave **Keep original memory IDs** selected for a replacement host. If those
   IDs already belong to memories or held identities in this organization,
   choose **Create independent copies** in a new private space instead. A
   collision never overwrites an existing record or grants access to it.
4. Select the directory that directly contains `catalog.json`. Supply original
   memory IDs withdrawn after this snapshot, including IDs absent from its
   files. Leave the withdrawal field empty only after checking the latest
   available history. Secret checks always run; recognizable personal-data
   checks default on.
5. Review counts and identity decisions, acknowledge the complete inventory and
   recovery scope, then select **Restore reviewed memories**.
6. Inspect the recovered records. They are editable and available to keyword
   search immediately; normal semantic indexing follows. Share or publish the
   space separately after review.

An interrupted request retains the same idempotency key for retry. If the
destination or input changes before applying a preview, Mnemion requires a new
review. A failed batch leaves no partial memories, origin records, withdrawals
or indexing jobs.

## Identity, versions and withdrawals

Original-ID mode preserves each original memory UUID across replacement
organizations and hosts. The original tenant, space, event ID, writer, timestamp,
version, metadata and important flag remain provenance. The importing
administrator creates local revisions; old writers do not become principals.
Original metadata is retained under `metadata.journal_recovery.metadata`.
Original claims are not promoted to verified facts.

Copy mode derives IDs from the destination space and complete original identity.
Repeat the same mode and destination to retain those IDs. Choosing a new copy
destination creates new identities; reconcile its withdrawals separately.

Complete projection applies every permanent forget before any positive record,
regardless of input order or a later claimed upsert. Native deletions and
physically purged memories stay withdrawn. Explicit additional withdrawals are
retained even when no positive record was present.

Quarantines are retained even if the available journal has no earlier content.
Such an origin has no fabricated memory text and is not searchable. An older
snapshot cannot release it. A newer complete journal can supply a reviewed
release. Existing recovered memories become quarantined without losing local
text. Local changes made before a quarantine remain protected after a later
source release.

Newer source revisions can update an untouched recovered memory after a fresh
review. Local edits or manual review decisions are preserved. The same source
version with different canonical bytes is a conflict. Older source versions
are ignored. These rules are recovery reconciliation, not a background sync
policy or a complete replay of historical native revisions.

## Completeness, privacy and capacity

The catalog's unique event count must match the whole submitted inventory.
Duplicate event IDs must have identical canonical records. Conflicting
origin/version claims, truncated lines, unexpected namespaces, incorrect file
paths, missing files and incompatible continuation catalogs stop the recovery.
Schema 1 and schema 2 journals are supported.

This guided path is bounded to **1 MiB of catalog and JSONL text, 256 files,
10,000 physical records and 1,000 memory identities**, including additional
withdrawals. The existing 2,000,000-byte HTTP envelope limit also applies.
Heavily escaped input can reach that envelope limit sooner.
**Never split a native journal or reduce its catalog to fit:** omitted history
could contain the only withdrawal. Larger journals require full workspace
backup recovery while resumable large-inventory upload remains roadmap work.
The older external-buffer format has a separate [importer](legacy-buffer.md).

Selected text stays in the page until review. Projection uses a bounded
in-memory SQLite index; it creates no plaintext staging files or retained
uploads. Import checks the complete current payload, including original
metadata, for secrets. If wrapping metadata would exceed native limits, the
whole batch is refused rather than silently truncating provenance.

Input files are user-supplied evidence. Catalog completeness is not proof of
authenticity, remote Git delivery, current hosting, or the absence of later
withdrawals. Every receipt says `source_only: true` and
`remote_delivery_verified: false`. No Git push, external fetch, decryption,
scanner executable or source-supplied instruction runs during recovery.

## API, SDKs and agents

| Interface | Preview | Restore |
| --- | --- | --- |
| HTTP | `POST /v1/spaces/{id}/journal-recovery/preview` | `POST /v1/spaces/{id}/journal-recovery` |
| Python | `preview_journal_recovery(id, input)` | `restore_journal(id, input, idempotency_key=key)` |
| TypeScript | `previewJournalRecovery(id, input)` | `restoreJournal(id, input, key)` |
| Private agent catalog | `memory.journal.preview` | `memory.journal.restore` |

Preview accepts `identity_mode` (`original` by default, or `copy`), the complete
catalog as a string, `files` with relative `path` and complete UTF-8 `text`,
explicit `withdrawn_ids`, and optional `reject_personal_data`.
Restore adds the returned `preview_sha256`, literal `true` for
`reviewed_complete_inventory`, `reviewed_withdrawals` and
`acknowledge_source_only`, and an `Idempotency-Key` header.
Discover the exact schemas through [agent control](agent-control.md).
File contents use private transport and do not belong in a shared prompt.

Migration 027 adds a private origin registry for version reconciliation and
content-free quarantine state. Full database backups include that registry.
Current recovery ledgers also retain subsequent source quarantines and manual
quarantines of recovered memories, including a hold created in a space absent
from an older backup. Restore keeps that negative identity without creating a
missing space, permission or memory text. A ledger never restores newer positive
content or releases a backed-up quarantine; review the complete newer journal
or restore a newer full snapshot for that content.

A ledger containing these holds uses format version 2 and requires Mnemion
4.26 or newer. Older readers reject it. Recovery of a populated origin registry
requires a current journal-aware ledger. Conflicting identities or source
versions stop restoration before the new database becomes available. Local
edits after the backup can be protected from source overwrite, but their lost
text still requires a newer full snapshot.

No cloud service, paid dependency or model call is added.
