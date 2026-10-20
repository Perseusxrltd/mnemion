# Windows database backup file paths

Validated on 20 October 2026 for source **4.30.2**. The
[automatic release status](../RELEASE_STATUS.md) separately records installed
platform and published-update acceptance.

The 4.30.1-r2 native Windows installed-app test reached a database dump path of
exactly 260 characters inside its owner-protected temporary profile. The bundled
`pg_dump.exe` refused to open it. A native Windows reproduction showed that a
259-character conventional path opened, while a 260-character path failed
before a database connection was attempted. The unpublished release was withheld.

The fix supplies absolute Windows extended-length paths for `pg_dump` output
and `pg_restore` input. Drive paths, UNC shares, relative paths and existing
extended prefixes preserve their selected file. POSIX arguments retain their
previous behavior. No machine-wide registry setting, weaker file permissions
or shorter test profile is needed.

## Focused evidence

- The actual bundled Windows tools opened 260- and 320-character paths with
  the extended prefix. The dump probe reached its deliberately unavailable,
  bounded loopback connection; the restore probe read its deliberately invalid
  archive header. These prove native file handling, not a successful restore.
- Both committed Windows path regression checks passed against the installed
  PostgreSQL tools. They also cover relative, UNC and already-prefixed arguments.
- Linux path behavior and a real complete PostgreSQL snapshot/restore passed,
  including reconciliation of later deletion, principal grants and API keys.
  The Windows-only file probe is skipped on Linux.
- Backup errors now retain only the existing validated diagnostic structure:
  category, numeric OS codes, SQLSTATE and up to eight Mnemion code locations.
  Paths, SQL text, provider errors and secrets are rejected. The next operation
  clears the prior diagnostic; private agents and optional app support details
  can inspect it, and native release failures record it.

Both web and desktop builds and 69 focused desktop backup/workspace checks passed.

Tests: `client_tests/test_native_paths.py`,
`service_tests/test_recovery.py::test_complete_recovery_reconciles_later_deletion_grants_and_keys`
and `studio/electron/scripts/test-local-workspace.mjs`. The existing installed
backup/recovery gate keeps its long private profile and verifies the complete
packaged flow on Windows x64 and ARM64 before release.

No production memory, agent setting, Windows policy or hosted model was changed
by the focused reproduction. Temporary synthetic files were removed.
