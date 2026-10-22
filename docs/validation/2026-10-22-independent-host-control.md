# Independent host-control source qualification

Recorded **22 October 2026** for the 4.46.0 source candidate. This is source
qualification, not installed-client, production-adoption or publication proof.
The [guide](../guides/company-host-control.md) describes the supported workflow;
the [continuity contract](../implementation/workspace-continuity.md) retains the
remaining company-hosting and recovery scope.

## Observed behavior

- **75 Python integration cases passed** across the new host-control suite,
  managed-command custody and update retention. They include the restricted SSH
  listener and real Git-over-SSH exchanges, current role/revocation checks,
  operation identities and restart recovery, compatible-runtime retention,
  signed-plan boundaries, explicit OS-owner recovery, and backup deletion
  acknowledgement recovery. The complete run took 63.01 seconds.
- **20 desktop component cases passed** across protected host profiles, native
  agent dispatch and credential subprocess handling. Lost replies retain the
  exact request; a refused replay cannot replace the original unknown or
  completed outcome. Explicit archival preserves public recovery information
  before removing a key or clearing the local pending slot. These component
  cases use an authenticated fixture cipher, not a real OS key store.
- The integration run includes a real built Node desktop profile calling the
  native Python pipe and independent SSH controller while the memory API is
  stopped. It enrolls a generated key, observes status, submits a stop request,
  reopens the desktop profile and reads the same completed operation without
  starting the memory service. This journey also passed its focused rerun.
- Electron and frontend builds, Python lint/format and release preparation
  passed. A browser fixture confirmed that the update button remains disabled
  before approval, submits the displayed plan digest after approval, and fits
  a 960-pixel desktop window. It did not execute a real host update.

The reproducible source checks use `service_tests/test_host_control_*.py`,
`service_tests/test_managed_command_custody.py`,
`service_tests/test_update_cleanup.py`, and the Electron scripts
`test-host-profiles.mjs`, `test-desktop-agents.mjs` and
`test-credential-process.mjs`. The SSH fixture is required through
`MNEMION_REQUIRE_SSH_TESTS=1`; its configured executable and libraries must be
available. `MNEMION_REQUIRE_HOST_CLIENT_TESTS=1` refuses to skip the desktop
journey if Node or its compiled desktop modules are missing. Product CI runs
that journey after building Studio.

## Pending acceptance

New packaged-client gates require actual OS-protected host-key generation and
reopening, bounded unavailable-host transport, public recovery retention, and
opening `/hosts` through the sandboxed preload before memory sign-in. These
gates have not run for this candidate. They are assigned to the packaged-client
stage so unrelated installed capture and backup phases do not repeat native
engine startup for the same checks.

Successful source exchanges do not establish clean installed-client acceptance
on all six platforms or production host adoption. Whole-machine wake, automatic
boot registration, browser host control, Windows/container host adoption,
independent authority-state backup, replacement-host provisioning and old-writer
fencing remain open. No production host was adopted or new listener exposed by
these checks. The separate PC publisher pause and administrator-owned stopped
client tests were preserved.

At this checkpoint 4.45.1-r2 had completed its existing native release workflow;
that workflow does not contain this candidate. Its artifacts, publication and
actual Windows/shared-host update acceptance remain separate. Current public
availability comes from [release status](../RELEASE_STATUS.md). All 65 requirement
states and issues #44/#45 remain unchanged.
