# Native journal recovery — 19 October 2026

Source 4.26 implements reviewed recovery of the current native journal
projection. It also carries the older-buffer importer from withheld 4.25 and
corrects its installed-check navigation race. See the [recovery contract](../service/journal-recovery.md)
and the automatic [release gates](../RELEASE_STATUS.md).

## Database, Git and agent evidence

The focused checks use real disposable PostgreSQL, separate non-owner service
and worker logins, actual Git publication, HTTP and private agent operations.
The final recovery/backup/key/migration run passed **67 cases**. A separate
existing importer/agent/client compatibility run passed **45 cases**. They verify:

- Complete schema-1/schema-2 catalogs, active files, archives, continuations,
  duplicate folding, wrong namespaces/paths, truncation and inventory limits.
- Original memory IDs in a fresh organization, explicit independent copies,
  cross-space collision refusal and no imported writers or grants.
- Exact current Unicode content and provenance, editable native revisions,
  same-input retry receipts and preservation of local corrections.
- Permanent forgets and supplied withdrawals, including absent records and
  purged memories; older positive snapshots cannot recreate those identities.
- Quarantine with no text or fabricated memory, later reviewed releases,
  version conflicts, older-source refusal and whole-transaction rollback.
- Mandatory secret checks, current organization/space authority and refusal
  of shared or already-published recovery destinations.
- Full database restoration of populated origin records and newer deletion
  state. A snapshot taken **before** later source holds retains those holds
  through its newer ledger, including an absent space and a missing-text origin.
  Later local edits and manual quarantines remain protected from source overwrite.
- Strict quarantine-ledger validation and format-2 reader compatibility.
  Ledger entries cannot carry positive content or manufacture missing access.

The actual Git case publishes native events, reads their complete files/catalog
and recovers into a fresh organization with the original memory UUID. Recovery
itself creates no Git publication events. The complete-backup checks validate
the table inventory before migrations and operational reconciliation.

```sh
python -m pytest service_tests/test_journal_recovery.py \
  service_tests/test_recovery.py service_tests/test_application_key_recovery.py \
  service_tests/test_author_withdrawal_upgrade.py \
  service_tests/test_migration_line_endings.py -q
```

## Actual browser flow

A separate Chromium session used the normal workspace-key screen and the real
HTTP/PostgreSQL fixture. Its complete schema-2 folder contained three JSONL
files, five unique events and one repeated line across active/archive files.

The app reviewed one new memory, one permanent withdrawal and one missing-text
quarantine. After both review acknowledgements, recovery completed. **Open
memory** showed the exact updated Unicode text and original memory UUID. The
same complete folder subsequently reviewed as one already-restored memory, one
already-withdrawn identity and one already-quarantined identity. Backend counts
were one active memory, one denial, two origin records and **zero** publication
events. The Perseus-styled review rendered without browser errors or warnings.

The deterministic fixture embedder establishes transaction/API integration,
not semantic-quality results. Original office data, encrypted source files,
live credentials, the shared production host and Argil were not modified.

## Limits and remaining acceptance

Migration 027 retains origin versions and quarantine identities. Current
ledgers protect later negative decisions; they do not recover later lost text,
full original accounts, original history or a missing encryption key. Source
recovery remains bounded to 1 MiB, 10,000 physical records and 1,000 identities.
Large-inventory upload and remaining issue-39 deployment acceptance remain open.

Desktop builds retain the installed setup/reopen, unsaved-editor guard and
public automatic-update gates. The 4.25 race was a broad textarea selector
matching the previous journal page during navigation; the replacement waits
for the actual memory-content field. It does not bypass the restart safeguard.
The recovery screens use explicit pending state so a saved or cleared form
does not keep updates waiting merely because its controls remain mounted.

A second actual browser flow passed **14 restart-state checkpoints** using the
compiled preload event tracker and predicate in an isolated test namespace.
Pending journal recovery, legacy withdrawals, directory edits, kit passphrases
and a native memory draft blocked restart. Completed recovery, cleared inputs,
a saved directory, a completed encrypted-kit download and a closed editor
allowed restart. This check used real app controls and the disposable API;
native IPC was stubbed and is not claimed as installed-desktop acceptance.
