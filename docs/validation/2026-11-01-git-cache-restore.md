# Git cache checks during host recovery — 1 November 2026

The reviewed change checks configured remote Git cache paths during
[host recovery](../service/host-recovery.md). An absent cache is acceptable
when the invoking account can create it through an existing writable ancestor.
Existing bare repositories, working trees and directory symlinks retain their
supported behavior; inspection checks the real Git metadata and configured
origin using the same filtered environment as the managed runner.

Inspection uses fixed error categories and does not clone, fetch, create a
cache or authenticate a remote. An explicitly disabled connection, or one
absent from the authenticated current recovery ledger, cannot block restoration
because of an unused cache path. For an enabled connection, an unusable cache
is checked against the actual saved-key eligibility in the restored database.
The read-only decision preserves the existing key-issuance order under both
`preserve_applications` and `rotate_all`.

Eligible cache failures stop before source-key issuance, connector publication
or runner preparation. They can occur after the database and archived private
assets have been restored. The journal remains at `database_restored` with its
original path selection. Repairing the same cache path permits an ordinary
resume; changing the mapping requires a separately reviewed destination.
Ineligible cache failures preserve the existing `already_restored` result.

Validation used actual local Git commands, temporary files and a disposable
PostgreSQL database. **All 22 selected cases passed:** 19 cache-preflight cases
and three recovery cases, including both key policies. The production service
and its database were not used.

The first run retained 19 passes and three failures. Two failures were in the
new test fixture, which attempted to overwrite an exclusively published
plaintext ledger. The corrected fixture keeps that export and encrypts a new
private file. The existing recovery case failed at `pg_restore` with system
PostgreSQL 17.11 clients against the fixture's PostgreSQL 16.2 server; its raw
client stderr was not retained, so no particular SQL error is claimed. The
test fixture now selects its own server's bundled tools when it creates that
server, preserving explicit overrides and external-database behavior. Only
the three failed cases were rerun; they passed in 42.91 seconds. Production
code was unchanged between the two runs.

Selected checks:

- `service_tests/test_git_cache_restore_preflight.py`
- `service_tests/test_host_recovery.py::test_newer_encrypted_ledger_preserves_deletions_and_does_not_rekey_revoked_sources`
- `service_tests/test_host_recovery.py::test_newer_ledger_omits_ineligible_git_caches_and_keeps_the_pinned_restore` (both policies)

The changed Python files also passed lint. Mechanical formatting preserved the
parsed Python syntax. These results establish the reviewed local recovery
behavior; they do not establish remote authentication, completed source scans,
Windows ACL behavior or recovery of the two separately unavailable live
filesystem scopes. Release qualification remains a separate step.
