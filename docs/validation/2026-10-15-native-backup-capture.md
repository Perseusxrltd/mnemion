# Native encrypted capture and inspection

This is **unreleased source work** following the published 4.4.0 remote-access
batch. It implements local operator capture/inspection toward the
[guided native recovery workflow](../implementation/native-backup-recovery.md).
The follow-on [desktop workflow](../service/native-backups.md) implements app
screens, protected scheduled keys and independent native restore in source.
Configurable retention and complete native release acceptance remain open.

`mnemion-service local backup`, `backup-ledger` and `backup-inspect` accept a
bounded JSON request on private stdin. Capture requires the selected local
workspace identity and the native database ownership/TLS checks; an ordinary
memory administrator key is not sufficient. The caller supplies the random
recovery key in memory. The destination receives only encrypted files inside
a workspace-specific directory; secrets never enter routine receipts.

A full capture uses the existing consistent PostgreSQL snapshot, then records
a newer access/deletion ledger. Both files are encrypted and read back for
authentication before success is recorded. Inspection authenticates encrypted
bytes and verifies the full archive inventory without executing SQL. The
snapshot context permits only explicit nonsecret setup fields. Existing
workspace configuration and credentials are preserved.

On Python 3.12/Linux, **20 local-backup and existing recovery tests passed**.
The principal integration test used a real isolated PostgreSQL database,
captured a memory, deleted it after the snapshot, exported a newer encrypted
ledger, decrypted both files and restored into a separate database. The deleted
memory stayed deleted, its historical revisions were purged, old API keys
were rotated, and original configuration/credentials remained byte-identical.
The destination held only the three expected encrypted files and private
operation staging was cleaned up. This fixture substitutes only the native
owner adapter; native TLS/process ownership retains its separate installed gates.

Other checks cover busy/cancelled work preserving the prior successful receipt,
refusal of destinations inside the live data directory or managed directory
links, secret-free CLI errors, one-shot stdin, and cancellation/deadlines for
real owned child processes and SQL connections. PostgreSQL child output is
discarded instead of accumulated, preventing SQL/credential diagnostics from
crossing the operator pipe.

Follow-on work extends cancellation through archive packing, extraction and
hashing, keeps archive verification in private staging and adds disk admission
and guided isolated restoration. Streaming encryption alone does not establish
a whole-workspace RAM bound. This capture run does not validate a real cloud
sync destination, Windows or macOS app recovery, or company failover, and does
not close the broader roadmap requirements. See the
[current native workflow guide](../service/native-backups.md) for implementation
status and the retained limits.

The first complete CI run exposed a test-isolation assumption: its shared
database already contained 165 memories from other tenant fixtures, while the
new test expected one. The backup correctly reported the complete database.
The test now compares memory counts and reconciled deletions with the actual
source inventory and ledger. All 20 recovery/capture tests passed in the
focused rerun, including the reversed file order. The original Python 3.12 CI
run passed 1009 other tests and measured 85.71% service/native coverage; fresh
CI must confirm the corrected assertion across supported Python versions.
