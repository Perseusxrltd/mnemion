# Guided native backups and recovery

Status: **Building**, following the 4.4.0 remote-access batch. This contract
implements the backup/recovery portion of A04, A06, A09, U01 and U02 in the
[complete requirements](../PRODUCT_REQUIREMENTS.md); those broader requirements
remain open until their own acceptance evidence is available.

The [streaming encryption and publication foundation](../validation/2026-10-15-backup-foundation.md)
is implemented. [Local operator capture and inspection](../validation/2026-10-15-native-backup-capture.md)
now pass real PostgreSQL snapshot, later-deletion ledger and isolated recovery
checks in unreleased source. Desktop scheduling, protected keys, cancellation,
inspection, isolated restoration and persistent copy selection are now implemented;
see the [user guide](../service/native-backups.md). Installed acceptance is being
extended across all six targets. The full workflow remains in progress and is
not shipped from these module checks alone.

## User workflow

1. **Setup & this device → Backups & recovery** identifies the local workspace
   and lets its host operator choose a backup folder. A folder synchronized by
   Git, Drive, a company cloud client or another storage service is an option;
   synchronization completion must not be inferred from a successful local write.
2. Generate a high-entropy recovery key, explain its role, and export/copy it
   deliberately for storage separately from the backup. Keep the scheduled
   job's copy in the OS protected store. Refuse a plaintext fallback if that
   store is unavailable; manual operations can use a supplied key in memory.
3. Choose a schedule and retention, create the first encrypted snapshot, and
   verify its authentication and full archive inventory before recording success.
   Refresh the deletion/access ledger independently and more often than snapshots.
   Show actual snapshot/ledger ages, bytes, verification and failures.
4. Run schedules while the host/app is available, including background mode.
   Coalesce missed runs and avoid simultaneous snapshots. Make cancellation,
   unavailable destinations, locked key stores, resource pressure and updates
   explicit. A schedule does not wake a powered-off computer.
5. **Recover a workspace** selects an encrypted backup, its recovery key and the
   latest available authenticated ledger. Show workspace identity, snapshot time,
   memory/table counts, ledger age and the original runtime version before use.
   A source-only Git mirror must never be presented as a complete database backup.
6. Restore and verify in a new private location. Preserve the current workspace,
   authenticate every encrypted byte, validate every archive member, compare
   restored table inventories and reconcile current deletions/access. Use the
   existing recovery contract to revoke old keys and invalidate historical
   passwords/sessions; provide fresh administrator enrollment.
7. Show the verified recovery copy before an explicit switch. Retain the previous
   data location. Do not automatically copy old public routing, provider tokens,
   endpoint approvals or source permissions into the recovered host. Explain the
   need to stop/fence the prior writer before a shared-workspace cutover.

An app login or memory administrator key does not authorize operating-system
backup paths, decryption keys or service control. The native bridge admits only
the trusted local application. Every operation also has a typed local operator
equivalent with secrets on private stdin, bounded output and retained receipts.

## Storage and resource contract

Use a versioned streaming AES-256-GCM envelope and a randomly generated 256-bit
key. Authenticate the complete format header, bound all lengths and publish
only complete authenticated output. Do not invent a cipher or use a human
password directly as an encryption key. One-megabyte buffers keep encryption
independent of the workspace size; snapshot work still needs disk and database
resources and must report their actual limits.

Only ciphertext and nonsensitive delivery receipts may enter the chosen backup
folder. Plaintext database dumps, ledgers and restored administrator credentials
stay in private staging. The recovery key never appears in routine status,
logs, model context, searchable memory, source synchronization or public docs.
Archive names and retention are owned and scoped to this backup configuration;
unrelated files and uncertain/in-progress output are never removed as cleanup.

The existing PostgreSQL snapshot and ledger formats remain the canonical data
contract. Model caches, host/database passwords, ngrok credentials, native OS
store material and ordinary Obsidian files are not silently added to snapshots.
They require explicit reconfiguration or their separate backup procedure.

## Acceptance before describing this workflow as shipped

- Real PostgreSQL save/index/search, snapshot, later deletion and access change,
  independent ledger, encrypted restore and fresh login into the recovered copy.
- Wrong key, altered header/body/tag, truncated or excessive input, malicious
  archive paths, interrupted output and an already-existing destination are
  refused without exposing plaintext or replacing working data.
- Native creation, OS-protected key persistence/reopen, scheduled/manual runs,
  cancellation, update coordination, inspection and restoration on all six
  supported desktop targets. Include paths with spaces and non-ASCII names.
- Responsive app controls, keyboard/error/progress behavior, clear recovery ages,
  offline help and equivalent local agent commands.
- Retention and a disconnected/reconnected cloud-synchronized folder, without
  claiming remote durability from a local filesystem receipt.

Independent host inventory, operator delegation, provider power management,
continuous replication and automatic failover retain their own requirements in
[workspace continuity](workspace-continuity.md). A successful local restoration
alone is not proof that those features exist.

## Remaining acceptance and scope

The current implementation keeps every backup; configurable automatic retention
is still open. Metadata checks detect missing/resized files, while native cloud
delivery receipts and real disconnected-provider acceptance remain separate.
The [following desktop operator source](../service/desktop-operator.md) implements
schedule configuration and persistent desktop copy selection through the same
controllers, with private OS-pipe access and separate native acceptance.
Additional organizations retain private administrator
credentials, with guided distribution still open. Native OS-store and installed
capture/restore/reopen checks must pass before public release claims.
