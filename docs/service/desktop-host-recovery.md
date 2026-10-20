# Open a server backup in the desktop app

From **4.30.2**, Mnemion Studio can recover the database in an encrypted
`.mnemion-host` server package on Windows, macOS or Linux. The installed app
provides the database tools. The source server and the agent that created it
can be offline.

This creates a separate local workspace with the original organization and
memory identities. It does not install the previous server's source runners,
provider credentials, company sign-in, network settings, vault host keys or OS
services. Keep the original encrypted package for those settings. For a complete
supervised Linux/macOS replacement, use [host recovery](host-recovery.md).

## Recover through the app

1. Obtain the complete encrypted server package and its independently held
   recovery key. Obtain the newest encrypted `.mnemion-ledger` file too, if it
   was saved after the package. The app accepts local files, including files
   downloaded from your storage provider; selecting a cloud-synchronized file
   does not independently verify its remote delivery.
2. From the workspace welcome screen, choose **Recover a workspace**, then
   **Choose snapshot**. Select the `.mnemion-host` file, enter its recovery key
   and choose **Inspect snapshot**. The app authenticates the encryption and
   checks both the complete server-package inventory and its database archive.
   It displays dates, organization and memory counts, and the number of saved
   source connections and private configuration files.
3. Choose and inspect the newest access ledger. If the package contains the
   newest copy available, explicitly choose **Use included ledger**. A separate
   ledger can use its own recovery key. It must be at least as recent as the
   ledger already included in the package; the app never substitutes an older
   access record silently.
4. Review the organization to open first, the backup and ledger dates, and the
   recovery scope. Confirm that you trust the backup and selected the newest
   available ledger. Also confirm database recovery with separate configuration
   of sources, models, sign-in and sharing.
5. Choose **Create verified recovery copy**. The app authenticates the selected
   bytes again, creates a new private data directory and database, verifies the
   restored table inventory, reconciles the selected deletions and access state,
   and issues fresh administrator access. **Use this recovery copy** appears
   only after that succeeds. The current workspace and input files are retained.
6. Open the verified copy and review its configuration before sharing it. The
   existing backup, model, vault and connection screens remain available.
   Additional organizations' recovery administrator credentials stay in the
   new directory's private `recovery-administrators.json` file. The recovery
   details identify that directory without displaying those credentials.

Existing application keys, browser sessions and assistant authorizations are
revoked in this new copy. Current deletion and permission records are applied;
changes after the newest available ledger remain outside its recovery window.
The old server is not changed or stopped by local recovery. Coordinate a real
team cutover before making the recovered copy the authoritative writer.

## Configuration and resource boundaries

The private source-host files are inspected in protected temporary storage and
removed afterward. They are not copied into the running desktop configuration.
Saved commands, provider tokens and network listeners are not activated. The
original encrypted package remains the source for a later supervised-host
reconstruction. Imported credential-vault values still require their independent
vault key and newly reviewed grants.

The app uses its normal CPU profile for a separate recovery-check space, with
its existing RAM policy. Saved embedding generations remain part of the
database; their provider/model availability must be reviewed before reindexing
those spaces. Inspection and database restoration do not call a hosted model.

The encrypted and archive readers keep their existing 50 GiB bounds and disk
admission checks. Server metadata is limited to 1 MiB, at most 64 source runners
and 128 private files totaling 64 MiB. The inner database setup inventory is
limited to 1 MiB. These are format bounds, not a measured 50 GiB throughput or
minimum-hardware claim. PostgreSQL and schema compatibility checks still apply.

Cancellation removes private temporary extraction and leaves any incomplete
destination separate from the current workspace. Incomplete copies cannot be
selected. This desktop workflow can be retried into a new destination; it does
not resume a partially created database in place. A server's existing
[journaled host restore](host-recovery.md) retains its separate resume contract.

## Local-agent equivalent

The same private [desktop operations](desktop-operator.md) handle this workflow:

- `backup.inspect` accepts a server package and returns `kind: "host"`, the
  package facts and `embedded_ledger_sha256`. It returns no provider settings or
  credentials.
- `backup.restore` adds `source_kind: "host"` and
  `host_data_only_confirmed: true` to the existing reviewed restore input.
  `snapshot_sha256` is the inspected encrypted package's hash.
- For a separate ledger, pass its `ledger_source`, inspected encrypted hash in
  `ledger_sha256`, and its `ledger_key` when different.
- For the included ledger, pass `ledger_source: null`, omit `ledger_key`, and
  use `embedded_ledger_sha256` as `ledger_sha256`. That hash identifies the
  authenticated plaintext ledger member inside the already hashed package.
- `recovery.list` and `recovery.use` retain the same identity checks, protected
  connection handling and unsaved-work guards as the app.

Direct native CLI callers use the same fields with `local backup-inspect` and
`local backup-restore`. The CLI additionally requires a new absolute
`destination`; the desktop chooses its own fresh recovery directory. Recovery
keys travel through private standard input and never through a command-line
argument or generic memory tool.

See [validation](../validation/2026-10-20-desktop-host-recovery.md) and the
[native backup guide](native-backups.md) for ordinary desktop snapshots.
