# Windows native startup and migration line endings

Diagnosed **2026-10-11** in native run
[38166021029](https://github.com/Perseusxrltd/mnemion/actions/runs/38166021029)
at source `f32905695e940b1f30834cd6bdb5a447d2d95450`.

The installed Windows app initialized its private database, provisioned access
and prepared the real model, then failed when starting the API. Bounded
diagnostics identified the migration-identity check in `Database.open`, without
printing provider errors, credentials or private source content.

## Cause and correction

All 13 SQL migrations in that run's frozen Windows engine archive used CRLF
line endings. `migrate()` reads universal-newline UTF-8 text and records the
checksum of the SQL it actually executes. `Database.open()` instead hashed the
raw packaged bytes. It therefore rejected its own correctly initialized
database on Windows.

Startup now checks the same UTF-8 text identity used by migration. Git attributes
also keep packaged SQL at LF across build platforms. No migration is edited,
reapplied or assigned a replacement database checksum. Signed release and
package-file verification continue to authenticate their exact artifact bytes.

## Regression and native evidence

- A real PostgreSQL test builds LF and CRLF copies of every migration, creates a
  new database from each, opens it with separate restricted API/worker logins,
  reruns migration, and changes the on-disk newline representation.
- Before the fix, LF passed and CRLF reproduced the startup mismatch.
- After the fix, both pass. Appending a real script change is rejected by both
  migration and startup checks. Combined with the independent-administration
  scenarios, the targeted run completed **4 tests** successfully.
- At `f329056`, Linux x64, Linux ARM64 and Mac ARM64 completed the installed
  create/save/search/reopen/address-repair gate and their full native jobs.
  Windows x64 failed at the mismatch described above. That run's Windows ARM
  and Mac Intel checks were still underway when the correction was prepared.

Run [38167935399](https://github.com/Perseusxrltd/mnemion/actions/runs/38167935399)
at `0cc51e82abfb554a4e3ff4f194c47faed77c026c` then passed real installed setup on
Windows x64 and ARM64: model preparation, authenticated semantic save/recall,
clean database shutdown, automatic reopen, preserved data/credentials/RAM policy,
and recovery from an occupied API port. Both Macs and both Linux architectures
also completed their full native jobs.

Both Windows jobs failed afterward when NSIS's temporary self-deletion helper
still held their disposable installation folders. The correction adds a finite
retry budget for transient cleanup locks; a persistent failure still fails the
gate. Fresh complete release acceptance of that correction and the integrated
administration changes remains required. Installed-workspace success alone is
not a published installer or a completed updater gate.
