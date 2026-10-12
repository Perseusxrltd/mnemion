# Independent encrypted workspace backup

Validation date: **2026-10-12**. This operator exercise covers the original shared
4.0.0 service and its independently connected Windows administrator. It is not
acceptance of a completed in-app backup or disaster-recovery wizard.

The host created a consistent PostgreSQL snapshot and a separately captured,
newer deletion/access ledger. Mnemion's archive verifier checked the complete
snapshot of **49 tables** and the ledger before encryption. PostgreSQL 17.11 was
the source database; its reported size was approximately 119 MB.

Both files were encrypted with standard **age 1.3.2 X25519** to two independent
recipients: a protected Windows administrator identity and a separate host-held
identity. Official utility downloads were checked against their GitHub release
asset digests. The two ciphertext files total **49,476,494 bytes**.

A new branch in an existing **private** repository stores only ciphertext,
integrity metadata and a recovery explanation. The memory-source branch was
unchanged. No plaintext database, ledger, private key or provider credential was
uploaded. An independently checked manifest digest binds this transfer to the
verified host snapshot.

## Independent verification

The remote Git copy was fetched on another computer and every ciphertext size
and digest was verified. Decryption using the independently held Windows
recipient matched both original plaintext digests. Mnemion then independently
verified the database archive and newer recovery ledger off the source host.

The actual Windows account also retained its own protected ciphertext copies and
used **current-user DPAPI** to unlock its recovery identity. Native `age.exe`
decrypted both files through bounded streams, again matching the original sizes
and digests. No plaintext recovery identity or backup file was written to
Windows. Peak Windows verification-process memory was **36,741,120 bytes**.

## Isolated restoration and migration

At **23:32:45 UTC on 11 October** (12 October local time), the verified 4.0.12
runtime restored the snapshot into a **new database**, using the newer external
ledger. The operation verified all 49 original table inventories before running
the two newer migrations and reconciling five deletion records. It completed in
**7.214 seconds**. The destination contained one organization, six principals,
three spaces, 391 memory rows and the expected 13 migrations.

Checks confirmed the reconciled administrator states and explicit grants,
rotation of copied credentials, rejection of the copied original key and a
working new recovery-administrator login through a restricted database role.
Copied source scopes require fresh provider permission checks; copied librarian
schedules remain disabled. Original live identity, key, grant and schema hashes
were unchanged. No new listener or model request was started during the rehearsal.

The [managed-host rehearsal](2026-10-12-administrator-diagnostics.md) also verified
real API/worker/updater readiness and clean shutdown. It exposed and reproduced
an administrator space-accounting bug in the connection doctor; the corrected
candidate client passed authenticated API/MCP checks against the unmodified
signed server. The [later live cutover](2026-10-12-managed-workspace-upgrade.md)
used a second fresh encrypted snapshot/ledger, independently verified on Windows,
and passed post-upgrade client checks. A routinely scheduled off-host backup
remains separate acceptance work.

## Scope and remaining acceptance

The snapshot covers the database, canonical memories and database-held
permissions/state. Database logins, provider tokens, model caches and unmanaged
Obsidian vaults have separate recovery requirements. The existing Markdown/Git
source mirror is useful but has a different scope from this full snapshot.

The Windows copy requires the Windows account's protected identity; a different
recovery custodian must retain their own usable identity. A backup does not
establish a running replica or transfer write ownership automatically. Product
backup scheduling, recovery-custodian onboarding, an independent host inventory
and a complete in-app restoration flow remain on the
[continuity plan](../implementation/workspace-continuity.md).
