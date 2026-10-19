# Supervised host recovery and source lifecycle

Source batch: **4.13.0**. This advances
[issue 38](https://github.com/Perseusxrltd/mnemion/issues/38) and the existing F08,
A06/A09/A12/A13 and U04/U06 requirements. It does not mark their full company,
UI, external-host or independent-delivery scope complete.

## Focused acceptance

**21 tests passed in 67.80 seconds** on Linux/WSL using isolated PostgreSQL,
private temporary files and synthetic organizations. The selection covers
`test_host_recovery.py`, `test_local_vault.py`,
`test_application_key_recovery.py` and `test_connector_diagnostics.py`.

- Encrypt a complete package, remove the source host configuration, and restore
  a new database with unchanged organization, principal, memory, connector and
  binding identities. The restored API and source runner actually start and
  complete a filesystem ingestion. Default automatic updates are configured;
  the fixture pauses external update checks before starting its processes.
- Repeat the same restore without recreating the workspace. Delete the restored
  database and its roles while retaining the home directory, then restore again
  with stable eligible application access and the explicitly paused update
  preference preserved.
- Invoke the real CLI from a separate Python environment, remove that environment,
  and restore with a replacement interpreter while retaining the database and its
  recovery-owner receipt. Inspect the package and create a private key through
  the CLI without exposing secrets in command output.
- Interrupt after service preparation commits. Reject a changed worker credential
  file without overwriting it, then resume after the expected file is restored.
  New setup does not absorb unrelated provider settings from the operator shell.
- Default key rotation replaces an eligible included connector's private key.
  A newer independently encrypted ledger instead suppresses revoked applications
  and sources and preserves a memory deletion made after the full snapshot.
- Application continuity excludes human, session, administrator, expired,
  disabled and revoked access, including transitions between snapshot and ledger.
  Historical credential-vault grants still require fresh approval.
- Reject the wrong key, a changed reviewed hash, an unrelated existing directory,
  and an authenticated package carrying shell execution overrides before creating
  a destination database. Rejecting the override does not execute its script.
- New runtime database routing preserves server certificate trust while omitting
  cluster-operator passwords, passfiles, client private keys and role overrides.
- Reject adapter/policy mismatches before source access. Configuration diagnostics
  explain private token references. Source ingestion excludes host/key control
  content, while an ordinary note about those settings remains importable.

All disposable database roles and supervised processes are cleaned up. The
tests neither modify the real shared host nor claim to recover its current data.
The [operator guide](../service/host-recovery.md) describes the actual custody and
deployment steps required there.

The existing recovery, encrypted vault, connector runner, Supervisor, managed
service, managed upgrade, managed connector and memory-policy recovery suites
also passed: **95 passed, 3 skipped in 80.96 seconds**. This checks default key
rotation and existing recovery/update behavior alongside the new opt-in path.
The three skipped cases are the opt-in locked-runtime installation/migration
checks. The release pipeline enables them on Python 3.12 and both Mac targets;
the new host-recovery and application-key suites are now required on both Mac
targets as well as the existing three-version Linux service matrix.

After the final continuity safeguards, the two affected host recovery cases
passed again in **28.99 seconds**. The two application-key cases passed in
**5.43 seconds**, including ledger capture against a pre-session-key table and
organization-specific recovery audit counts. The legacy-table fixture removes
the session marker inside a rolled-back transaction; it does not claim a full
installation test of every historical release.

The TypeScript client, web app and Electron builds passed at version 4.13.0.
Both Python dependency locks passed their consistency checks, and release
preparation regenerated and validated the version metadata and public contracts.

## Verification boundaries

The process acceptance above runs on Linux/WSL. The regular service, macOS
supervision and six native platform gates remain required by the release
pipeline. A passing source test is not a published installer or public update.
Publication evidence is maintained in [release status](../RELEASE_STATUS.md).

The restored host does not provision OS packages, hosting accounts, DNS, TLS,
tunnels or startup registration. It reports those boundaries explicitly. Snapshot
and ledger files are encrypted and verified locally; actual delivery to an
independent provider must be verified separately. Losses or revocations newer
than the last independently saved snapshot/ledger remain outside its recovery
window. No partitioned multi-writer takeover or universal cloud-delivery claim
is made.

The host CLI runs under an unprivileged Linux/macOS service account and requires
independent provisioning authority and recovery-key custody. Windows desktop
recovery continues through the native app. Guided app import of host packages,
Windows/Compose host adoption and company-delegated host controls remain open.
