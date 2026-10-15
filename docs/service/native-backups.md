# Desktop backups and independent recovery

Backup/recovery and desktop agent controls require 4.6.0 or later; configurable
retention requires 4.7.0 or later. Check [release status](../RELEASE_STATUS.md) for
verified public availability on each platform. The
[4.6.0 publication record](../validation/2026-10-15-native-backup-release.md)
records the first complete native release of this workflow.

## Protect a local workspace

Open **Setup & this device → Backups & recovery**. These controls operate the
database owned by your OS account. They include the **complete local database**,
including every organization it contains. A remote workspace login does not
grant control over that computer's files, encryption keys or processes.

1. Choose a backup folder outside the workspace's data directory. Use a separate
   drive or a folder synchronized by your existing cloud/storage application.
2. Generate a recovery key and copy it into a password manager or another safe
   location separate from the backups. Confirm that you saved it. Losing both
   the computer's protected copy and your exported key makes these files unreadable.
3. Keep automatic backups enabled and choose a full snapshot every 6, 12, 24 or
   168 hours. Refresh the deletion/access ledger every 15, 30, 60 or 240 minutes.
4. Leave **Backup retention → Keep all copies**, or choose how many recent
   snapshots and access ledgers to retain. Limits take effect after a successful
   full backup and may propagate deletions through your storage application.
5. Save the settings and choose **Back up now**. A successful run records the
   verified snapshot and ledger, their dates, sizes and organization counts.

Automatic schedules keep their key encrypted by the OS credential store. A
locked or unavailable store requires unlocking, or manual backups with the key
provided for that run. Mnemion refuses an automatic plaintext-key fallback.
You can change the folder and schedule or rotate the key. Older backups retain
their original keys, so keep those keys until you retire those files.

The folder receives only encrypted snapshot and ledger files inside
`Mnemion backups/<workspace ID>/`. Temporary plaintext and administrator recovery
credentials stay in private local staging. Snapshots use a consistent PostgreSQL
snapshot and a verified archive; the portable encryption format uses
AES-256-GCM with a randomly generated 256-bit recovery key.

## Background work, availability and retention

Schedules run while the app and local host are running, including background
mode. Missed intervals coalesce into one due run after sleep or restart. The
schedule cannot wake a powered-off computer. Failures and the 15-minute retry
deadline survive app restart; **Back up now** remains available for a manual retry.
Only one local recovery operation runs at a time. Cancellation drains its owned
database work and cleans private temporary files before the updater can restart.

Status checks whether the last recorded files are present with their expected
sizes. Missing, resized or unavailable files are shown explicitly and become
due again. This lightweight check does not reauthenticate every stored byte;
creation, inspection and restoration perform full authentication. A recorded
verification date describes that completed operation.

Mnemion verifies the local files. Your existing storage application handles
uploading them. A successful local receipt does **not** prove that Git, Drive,
another cloud, or an offline replica has received the files. Confirm remote
availability using that storage system. Native provider delivery receipts remain
on the roadmap.

### Retention and inventory (4.7.0 source)

**Keep all copies is the default**, including when upgrading existing settings.
**Keep recent recovery points** accepts 2–365 full snapshots and 2–10,000 recent
access ledgers. Defaults for limited mode are seven snapshots and 96 ledgers.
Ledgers paired with retained snapshots and the latest recorded recovery files
are also protected, so these counts are not an exact disk-space ceiling.

After a successful full capture, cleanup verifies the exact saved bytes of two
recent snapshot/ledger pairs and the newest access ledger before removing older
copies. Ledger-only runs do not perform cleanup. One run removes at most 200
eligible files. Missing, changed, linked or locked files are retained; a damaged
retained recovery point blocks cleanup. Keep keys separately even when cleanup
limits are enabled.

Choose **Review stored copies** for recorded counts, bytes, eligibility and the
latest 100 files. This works with the database stopped and needs no recovery key.
For immediate cleanup, review the plan, confirm the removal and choose **Clean
up reviewed copies**. Changing files, captures or settings can invalidate the
plan; review again when asked. Cancellation stops remaining work and records
completed removals in the latest cleanup result; it cannot undo files already
removed. The latest result is an operation summary, not a permanent per-file
audit history.

Only successful captures create private ownership records in this installation's
backup inventory. Files are scoped to the workspace, destination filesystem
identity and key ID. Older untracked files, files using other keys and unrelated
storage files are never adopted or deleted merely because their names match.
Losing the private catalog, replacing/remounting a destination or recovering
onto another computer therefore retains existing external copies. Counts cover
the selected recorded scope, not every file your storage provider holds.

Disk admission estimates space for snapshots, decryption, archive verification
and the restored database. It cannot reserve that space against other programs.
Streaming encryption uses 1 MiB buffers; complete database work still consumes
additional RAM and disk. The archive limit is 50 GiB, not a promise that every
computer can process a workspace of that size.

## Recover without the original agent

From the welcome screen, select **Recover a workspace from an encrypted backup**.

1. Select the encrypted snapshot and enter its recovery key. **Inspect snapshot**
   authenticates the file and verifies its archive without executing database SQL.
2. Select the newest available encrypted deletion/access ledger. If its key was
   rotated, clear **Use the snapshot's recovery key** and supply the ledger's key.
3. Review the workspace, dates, memory and organization counts. The ledger must
   be at least as recent as the snapshot. Choose the organization to open first
   if the snapshot contains several.
4. Confirm that you trust the backup and selected the newest available ledger.
   Restoring database definitions executes SQL; only restore trusted operator backups.
5. Choose **Create verified recovery copy**. Mnemion authenticates the selected
   bytes again and restores into a new private directory. It leaves the original
   workspace in place and verifies table inventories and deletion reconciliation.
6. Review the result, then choose **Use this recovery copy**. The selection
   persists across app restarts. Previously verified copies remain available in
   the recovery screen, along with a return to the original workspace when it exists.

Recovery revokes old API keys, resets historical passwords/sessions and creates
fresh administrator access. The current deletion/access ledger controls which
historical content is purged and which grants survive. Changes newer than the
selected ledger cannot be reconstructed from these files. The recovered local
host gets a new identity, database credentials and a private **Recovery checks**
space for its startup verification.

Sources, remote model approvals and external connections require review. Native
routing credentials, OS-store material, model caches and ordinary Obsidian files
are not copied into the new host. Additional organizations' fresh administrator
keys are recorded in the private `recovery-administrators.json` file shown by the
recovery details; guided distribution of those keys remains separate work.

Before sharing this copy as a team's new host, stop or fence the previous writer
and update the team's connection. Recovery does not automatically take ownership
of a remote computer or prove that its old service has stopped. Interrupted
copies remain private and marked incomplete; they are not offered as verified
workspaces or allowed to replace the original.

## Local agent operations

The desktop uses the same typed operator commands as an agent running under the
owning OS account: `mnemion-service local backup`, `backup-ledger`,
`backup-inspect` and `backup-restore`, with `--root` and the bundled
`--database-runtime`. Pass their bounded JSON request on private stdin, including
the recovery key; never put the key in command-line arguments or logs.

The [capture/inspection request types](../../mnemion/local_backup.py) and
[restore request](../../mnemion/local_recovery.py) define the accepted fields.
Restore requires the selected files' inspected SHA-256 values, a new destination,
the primary organization ID and explicit trust confirmation. Automation can keep
stdin open with `watch_parent: true` and send `{"action":"cancel"}`; closing that
watched pipe also cancels owned work. One-shot JSON followed by EOF remains supported.

From 4.7.0, capture accepts optional `retention` with `mode`, `snapshots` and
`ledgers`. `local backup-inventory` and `local backup-prune` work without database
tools or a decryption key. Both take `workspace_id`, `destination`, `key_id` and
`policy` on stdin; cleanup additionally requires the inventory's current
`plan_token` and `confirm: true`. These are local owner operations, not remote
memory API capabilities. The desktop equivalents are `backup.inventory` and
`backup.prune`; they use the saved policy and its current revision.

The following [desktop operator source](desktop-operator.md) adds private
same-account commands for schedule configuration, capture, inspection, independent
restoration and persistent app selection. It shares the app controllers and
retains separate native release acceptance; it is not part of the frozen 4.5.0
release source. Company recovery custodians, independently
managed host inventory, continuous replication, provider power management and
automatic failover retain their separate
[workspace-continuity requirements](../implementation/workspace-continuity.md).
