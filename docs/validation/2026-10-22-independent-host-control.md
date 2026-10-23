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
  starting the memory service. This journey also passed its focused rerun. The
  new native loopback-peer fixture separately passed **one case in 4.30 seconds**;
  the underlying 75 integration and 20 desktop results remain retained.
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

## Linux source Electron preview — 23 October 2026

A stronger host probe replaces the earlier key-generation/unavailable-host
check. The Linux **source Electron preview** passed its `save` and `resume`
phases initially at **00:07:43 UTC**. After the final UI-wait refinement, the
preview passed again at **00:12:21 UTC**, with both complete process phases
exiting **0**; the Electron rebuild also passed. It used the actual app renderer,
native agent pipe, **libsecret** and a pinned loopback SSH peer while the product
memory API was absent:

1. The app's `/hosts` UI created a protected login, saved the reviewed host pin
   and authenticated as an operator. The UI submitted an explicitly approved
   `service.stop` request and retained its queued UUID.
2. The complete app process exited and reopened using the same libsecret-protected
   key. The actual native agent pipe inspected the original queued operation
   without replaying it.
3. The host denied that operator access to the custodian-only `operators.list`
   action. Local forgetting without acknowledgement of outstanding work was
   also refused.
4. The real UI acknowledged retaining the request, archived its exact public
   recovery document and removed the saved local key. Agent readback confirmed
   the archive retained the original request without private-key material.

The latest probe waits for the read-only UI refresh to settle before finishing.
Its save receipt records `actualQueuedRequestVisible: true`, and its resume
receipt records `actualRecoveryRequestVisible: true`: the original queued UUID
and retained recovery request were visible in the actual app before closing.

The peer deliberately had **no worker**: the approved stop was queued, never
executed. No product memory service was started; **production writes and paid
calls were both zero**. This qualifies the source app/client path against an
isolated authority/transport fixture, not service-stop execution, production
adoption or an installed platform package. The phase receipts and screenshots
remain preserved privately.

Earlier preview setup failures are also retained: a missing local Electron
binary and a harness deadlock caused by awaiting app readiness at top level.
They were setup/harness failures, not product qualification failures. The first
passing preview remains separate from the final passing run with visible
receipts; neither rewrites the original failed setup attempts.

## Durable service policy — 23 October 2026

A pre-freeze review found that the actual host's unconditional memory-service
job and external watchdog could restart memory after an approved stop. The
pre-freeze waiter was stopped **before any 4.46 dispatch**; no release was
cancelled, and earlier CI was left running. Production changes to that job and
watchdog remain unapplied.

The subsequent source revision uses authority-store **format 2** to retain
desired `running`/`stopped` state independently of receipt pruning and later
revocation. Adoption observes the existing service and never starts it merely
by adopting it. Intent changes at the authorized guarded effect, or through an
explicit resolution accepting observed state. Experimental format-1 state is
refused without a silent migration or authority reset; no production controller
has been adopted.

The local `service-policy` read and foreground `memory-run` manager separate a
deliberate pause from a crash. `memory-repair` rechecks that policy under both
worker and update locks; an external check followed by `systemctl restart` is
not equivalent. Pending work, migrations and unconfirmed automatic starts block
automatic starting. Start/repair intent is recorded before effects, with no
automatic replay of an uncertain start. The source UI shows saved stops and
flags observed drift or an unconfirmed automatic start.

The copied launcher resolves verified current runtime pins for the memory,
policy and repair modes; policy/repair modes do not consume controller fallback
attempts. Startup output includes memory-manager, policy and repair arguments
and a hashed, generated memory launchd file. Nothing is registered automatically.
The [OS-owner integration steps](../guides/company-host-control.md#preserve-approved-stops-in-os-supervision)
require replacement of the unconditional memory job, separate controller
registration, policy-aware watchdog repair, the official supervision stop action
and avoidance of duplicate jobs.

The initial focused policy run passed **44 cases in 41.08 seconds**, including
restart of a real `memory-run` process while the saved approved stop remained
in effect. The broader host-suite attempt recorded **87 passed and two fixture
errors in 78.21 seconds**. All source policy cases passed in that attempt. Both
errors were real Git-over-SSH cases whose shell omitted the already installed
OpenSSH fixture configuration; no product assertion failed.

Reusing the existing executable and libraries, with no source correction or
test skip, the **two missing cases passed in 5.16 seconds**. These attempts
cover **89 cases combined**, not one 89-case green invocation. The original
44-case receipt and the full attempt with fixture errors remain preserved.
The frontend build also passed. The earlier 75 integration cases, 20 desktop
cases and Linux source preview above remain separate historical evidence.

This is source/fixture acceptance. Actual job/watchdog integration and boot/login
acceptance remain pending, as do all six installed-platform gates below.

## Pending acceptance

The expanded packaged-client gate requires the actual UI, OS-protected key,
pinned SSH exchange, process restart, original queued-request inspection,
authority/refusal checks and acknowledged public recovery archival described
above. Opening `/hosts` through the sandboxed preload before memory sign-in
remains required. **All six installed-platform gates remain unrun for 4.46.0**;
the Linux source preview does not substitute for them. The packaged-client
smoke stage now has a finite **180-second** readiness deadline for the expanded
cold-start agent/SSH work; individual helpers retain their bounds. The gate
stays in that stage so unrelated installed capture and backup phases do not
repeat native engine startup for the same checks.

Successful source exchanges do not establish clean installed-client acceptance
on all six platforms or production host adoption. Whole-machine wake, automatic
boot registration, browser host control, Windows/container host adoption,
independent authority-state backup, replacement-host provisioning and old-writer
fencing remain open. No production host was adopted or new listener exposed by
these checks. The separate PC publisher pause and administrator-owned stopped
client tests were preserved.

At this checkpoint 4.45.1-r2 had completed its existing native release workflow;
that workflow does not contain this candidate. At the 23 October follow-up,
corrected [artifact verifier 39876232059](https://github.com/Perseusxrltd/mnemion/actions/runs/39876232059)
passed against unchanged source `70ec58d8dbf4018ee35a9a57bd0a4677ee45cdf1`, and
4.45.1 was published at **00:14:17 UTC**. That release does not contain the new
host-control feature. Its actual Windows/shared-host update acceptance remains
separate. Current public availability comes from
[release status](../RELEASE_STATUS.md). All 65 requirement states and issues
#44/#45 remain unchanged.
