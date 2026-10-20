# Windows atomic status writes under temporary file locks

Recorded 20 October 2026 for corrected source **4.32.0**. The first frozen
candidate was withheld after its Windows ARM installed-app backup check failed.
Publication and all native results remain separate gates in
[release status](../RELEASE_STATUS.md).

The failure occurred at atomic replacement of the local backup status record,
after the encrypted snapshot and ledger had been verified and cataloged.
Windows returned access denied (`winerror=5`). The preceding published 4.31
release and its actual app/host updates remain verified.

An actual Windows x64 reproduction held an ordinary read handle on a private
JSON record. The original implementation returned the same Windows error while
retaining the original bytes. Windows read handles and filesystem scanners may
briefly prevent deletion/replacement even when the owning account has permission.
The CI diagnostic alone does not identify which process held that particular file.

The local-state writer now retries only the same atomic replacement for Windows
errors 5, 32 and 33, with at most **1.26 seconds of backoff**. Other errors and
Unix behavior retain their previous path. The writer never deletes the existing
record, relaxes its permissions or repeats the backup operation. Exhausted retries
return a specific `state_file_locked` message, retaining the original Windows
error as its diagnostic cause.

Focused validation passed **9 Linux cases** with 5 Windows-only skips and
**11 actual Windows cases** with 3 privilege/platform-specific skips. The two new
native Windows cases exercise a real open reader: a released handle allows the
atomic write to finish, while a held handle causes a bounded failure. Both verify
the reader's original bytes, the expected final record, private ACLs and complete
temporary-file cleanup. Existing interruption, unsafe-file and ownership checks
remain. No live workspace or user credentials were used in these fixtures.

The corrected candidate still requires its complete native release gates.
The obsolete live-update waiter was stopped with zero update actions; the next
candidate uses a new evidence directory and the accepted 4.31 baseline.
