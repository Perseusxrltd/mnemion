# Backup, recovery, and the v3 preservation boundary

The new [desktop backup and independent recovery guide](native-backups.md)
covers the app workflow published from 4.6.0. The service-level procedures
below also support independently managed servers and existing installations.

Mnemion's service backup contains its complete PostgreSQL schema and data: tenants,
principals, grants, key hashes, immutable sources/revisions, embeddings and their
generation, jobs, idempotency receipts, core-block history, audit events, aliases,
and deletion denials. It uses one exported PostgreSQL snapshot for both the dump
and the per-table count/content hashes. It does not copy database login passwords,
model-cache files, deployment secrets, or a desktop's Obsidian vault.
From source 4.12.0, snapshots also contain encrypted credential tables. Their
[vault host key](secrets-vault.md#backups-exports-and-recovery) must be kept
separately. Restoration preserves later credential deletions and clears old
vault grants for fresh administrator review; it does not recover the host key.

The commands run locally with `MNEMION_ADMIN_DATABASE_URL`. Keep that credential
out of the API and worker processes. Install PostgreSQL's `pg_dump` and `pg_restore`
from the same major version as the server or a compatible newer client; use
`--pg-bin /path/to/postgresql/bin` when they are not on PATH.

New snapshots retain the source database timezone so calendar-day constraints
remain valid when restoring across hosts and daylight-saving boundaries. For
older service archives without this metadata, use the original timezone in the
restore connection's `options` (for example `-c TimeZone=Europe/Paris`). Do not
guess another timezone when a restore reports a session-expiry constraint error.

## Service snapshot and denial ledger

```sh
mnemion-service backup --output /backups/mnemion-2026-10-09.mnemion
mnemion-service verify-backup /backups/mnemion-2026-10-09.mnemion
mnemion-service recovery-ledger --output /backups/ledger-2026-10-09T1800.json
```

Use new filenames for each run; commands never replace existing archives or
credential files. Files are privately created and atomically published. Keep
backups in a trusted, encrypted backup location with retention and access controls
appropriate for their source data. SHA-256 detects corruption; it does not
authenticate an archive whose manifest an attacker can also replace. Restore
executes a PostgreSQL archive and therefore accepts trusted operator backups.

Export the recovery ledger independently and more frequently than full snapshots.
It contains deleted memory identities and the latest principal/grant state, with
no memory content. Protect and retain it outside the database failure domain.
Recovery requires a ledger covering every backed-up organization and taken at
least as recently as the backup. Its freshness determines how recently deletions
and access revocations can be reconciled after loss of the original database.

## Restore into a new database

```sh
mnemion-service restore /backups/mnemion-2026-10-09.mnemion \
  --database mnemion_recovered \
  --ledger /backups/ledger-2026-10-09T1800.json \
  --credentials-output /private/recovered-owner.json
```

The destination must not exist. Restore verifies every archive member, restores
into a temporary database in one transaction, compares every table count and
content hash, applies compatible migrations, and reconciles the current ledger.
It erases withdrawn source/revision/vector bytes, preserves negative identities
for records created after the snapshot, reapplies current grants, and resets
interrupted worker leases. Only a successfully checked database receives the
requested destination name. An invalid archive or a failed restore cannot replace
the running database.

Every old API key is revoked. The private credentials file contains one new owner
key per organization; a single-organization file can be passed directly with
`--credentials`. Existing principals and grants remain. If an organization has no
active administrator, recovery creates an administrator with no automatic content
grants; explicitly assign the necessary space access before use.

Endpoint embedding processing is paused after restore. Candidate reindex runs
are paused too, and their previous endpoint approvals are cleared. Review the
registered destinations in Studio's **Embedding models** page, then explicitly
reapprove and resume the active endpoint or candidate. Lexical retrieval remains
available; you can build and activate a local candidate without reapproving the
old endpoint. See [embedding recovery controls](embeddings.md). Source connectors
also require access revalidation before processing resumes.

Point administration at the recovered database, provision separate API and worker
logins with a new `logins --prefix`, start an isolated API/worker, and verify fetch,
history, scoped recall, an Obsidian export, and a deletion receipt before changing
client routing. Keep the previous database and routing settings for the rollback
window. A connection failure during the final rename can leave a private key file
for inspection: check which database name exists before retrying or deleting it.

The included Compose deployment has an explicit `adopt-restored` command that
validates the recovery key and recorded recovery, stops the service, atomically
selects the verified database, and refreshes private runtime credentials. See
[the cutover runbook](deployment.md#cut-over-to-the-verified-restored-database).

A snapshot restores positive data as of its snapshot time. It does not invent
writes accepted afterward. Choose a backup schedule for the required recovery
point, and use managed PostgreSQL continuous backup/PITR when that recovery point
requires it. Keep the independent denial ledger when using PITR too.

## Preserve a v3 installation before migration

```sh
mnemion-service legacy-freeze --profile /data/legacy-mnemion
# Stop all legacy processes, scheduled hooks/capture/sync jobs, and Obsidian.
mnemion-service legacy-backup --profile /data/legacy-mnemion \
  --writers-stopped --output /backups/legacy-v3.mnemion
mnemion-service legacy-ledger --profile /data/legacy-mnemion \
  --output /backups/legacy-deletions.json
mnemion-service legacy-restore /backups/legacy-v3.mnemion \
  --path /data/legacy-rehearsal --ledger /backups/legacy-deletions.json
```

`legacy-freeze` persists a pause honored by the updated local writer entry points.
It cannot stop an already running older release, a direct SQLite/Chroma client,
or Obsidian; stop those processes before asserting `--writers-stopped`. Configured
external data directories are included in the snapshot. Use `--vault` if the
copied Obsidian vault is at another location.

The v3 archive captures the profile, configured Chroma directory, SQLite sidecar,
raw source files, wiki files, and the entire selected Obsidian vault including its
settings and personal files. SQLite uses its backup API, including committed WAL
state. Before/after source hashes reject files changed during the capture.
Git history, virtual environments, Node dependencies, and Python bytecode caches
are explicitly excluded and listed in the manifest; they are not memory backups.
Symlinks require explicit configured paths. Archives are limited to 50 GiB.

The archive also contains portable canonical drawer records, collection identity,
trust/conflict history, core blocks, source metadata/chunks, wiki state, and pending
write journals. Preservation does not require loading an embedding model.
Restoring the old Chroma binary indexes requires the optional `legacy` extra.
Restore operates in an unpublished directory, applies the newer deletion ledger,
replays durable pending work, repairs lexical/trust projections, and relocates
configured file paths. Unsupported pending embedding work fails the rehearsal
instead of silently discarding it.

The restored profile remains paused. After verifying counts, hashes, trust state,
raw source bytes, pending operations, and the copied Obsidian vault, resume it with
the exact `freeze_id` returned by restore:

```sh
mnemion-service legacy-resume --profile /data/legacy-rehearsal \
  --freeze-id THE_RETURNED_FREEZE_ID
```

Resuming the old writer is a separate routing decision. After v4 has accepted new
writes, first preserve and reconcile that tail and the current deletion ledger;
reopening a stale v3 snapshot alone is not a rollback.
