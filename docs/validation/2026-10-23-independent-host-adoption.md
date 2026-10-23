# Independent host adoption: setup passed, operational journey failed

**23 October 2026; actual-host evidence through 11:01:48 UTC.** Native controller
adoption, backup configuration, OS integration and two protected custodian
enrollments **PASSED** on the canonical Linux host running published 4.46.1,
source `94684f002b707d6750edde2a00d7254f155f3eae`. The full deliberate-stop,
manager-restart, watchdog, start and retained-data journey **FAILED at its first
Windows stop, before any effect**. Full independent-host recovery is not accepted.
The separate [4.46.1 Windows/shared-host paired update](2026-10-23-4461-live-acceptance.md)
remains accepted.

| Stage | Recorded result |
| --- | --- |
| Native controller adoption | Passed in the preceding setup attempt. Its later backup-setup scan-lock contention remains preserved. |
| Controller reuse and backup configuration | Passed at **10:54:18 UTC**. The exact existing controller was retained; native adoption was not repeated. Configuration produced no fresh native backup delivery. |
| OS integration | Passed at **10:58:01 UTC**. This installation receipt did not establish actual-client or durable-stop acceptance. |
| Two custodian enrollments | Passed at **10:58:40 UTC**, using distinct protected keys. Enrollment had no memory-service effects and did not demonstrate separate physical devices. |
| Windows `service.stop` | **Failed at 11:00:26 UTC**, with `error: operation_failed`, `phase: failed` and `effect_started_at: null`. |
| Manager restart, two watchdog ticks, service start and retained-data comparison | **Not reached** because the first stop failed. |

The stop exhausted the adapter's **60-second operator-lock wait** behind an
active source scan. It never began its effect or changed the desired service
state. **No second stop or restart was requested.** The original failed
operation and setup receipts remain retained; the failure is not relabeled as
the newer source hotfix's `host_busy` outcome.

A fresh native status observation at **11:01:48 UTC** confirmed memory
**ready and running**, desired state **running**, no pending work and no recovery
requirement. The controller reported **4.46.1**, with no fallback, pending update
or update inspection. Its backup configuration was present, but it had no
verified native backup delivery timestamp or retained verified native backups.
This read established current service health; it did not complete the stopped
operational journey.

The existing encrypted memory snapshot and later ledger were independently
verified in private Git before OS integration. That delivery predates capture
of the new controller authority, so it does not prove a fresh native
host-control backup or restore.

## Source follow-up and remaining acceptance

The [4.46.2 source hotfix](../releases/4.46.2.md) uses the existing supported
five-minute source-drain window for adoption, backup setup, service actions,
resolution and upgrade planning. It preserves active scans and records fixed
`host_busy` if the operation remains blocked; the UI explains that outcome.
Real-lock source regressions passed with simulated time: a scan finishing after
75 seconds allowed exactly one authorized stop, while a held source lease
produced `host_busy` at 300 seconds without effect, intent change or scan
interruption. The later [focused checks and builds](../releases/4.46.2.md)
passed with 99 source tests passed, 2 skipped and six desktop host-profile tests
passed. Installed/native and public qualification, and renewed actual
acceptance, remain unproven at this source checkpoint.

The [earlier update interruptions](2026-10-23-4461-live-interruption.md), original
4.46.0 rollback, 4.46.1 paired pass and this failed first stop remain separate
evidence. No fresh native host-control backup delivery or restore,
whole-machine boot, separate physical-device custody or provider wake is
established. Independent authority recovery, broader provider/platform journeys
and full continuity requirements remain open in the
[completion audit](../implementation/completion-audit.md).

Private operation, installation, enrollment and read-only inspection receipts
remain retained; identities, keys, pins, addresses and raw logs are excluded.
All [66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) and all 42
partial-audit rows are unchanged. [V08 telemetry](../implementation/anonymous-product-telemetry.md)
remains Planned and inactive.

## Controller shutdown observation — 23 October 2026

CI on frozen **4.46.2 source `1fc96a82`** exposed a separate shutdown-observation
race: `lifecycle.stop` successfully requested independent controller shutdown,
then its status read raised `ConnectionResetError` as Supervisor closed the
socket. The [4.46.3 source correction](../releases/4.46.3.md) tolerates
`ConnectionResetError`, `BrokenPipeError` and `RemoteDisconnected` only during
that post-request observation. It retains the **20-second bound**, **one
shutdown request** and **observed absence** requirement; identity and permission
errors still propagate. Regression and real desktop checks passed **10/10 in
20.32 seconds**. This is **UNRELEASED source work**, with no native/public or
actual 4.46.3 pass. Frozen 4.46.2 continues its existing build/publication.
The earlier actual first-stop failure remains preserved, and the complete
custodian operational journey is still not accepted.

## 4.46.2 actual host rollback — 23 October 2026

Published **4.46.2**, source
`1fc96a82df8c4d7ae9420962187c4546b51ec60a`, retains its passed native,
artifact-verification and public installed-update gates. Its actual shared-host
attempt rolled back at **12:41:16 UTC**. The read-only result captured at
**12:42:38 UTC** records active version **4.46.1** and failed version **4.46.2**.
Windows remains **4.46.2**; the paired observer stopped for inspection.
Dependent custody/report jobs stopped at **12:44:30 and 12:44:36 UTC** because
the original paired update needed inspection, before any new host effects.
The [earlier 4.46.1 pair](2026-10-23-4461-live-acceptance.md) remains the last
accepted actual pair. This live failure does not withdraw the public release.

The original transition receipt records `direction: start`,
`reason: readiness_timeout` and **`budget_seconds: 60`**. API and worker states
were `RUNNING`, while `http_ready`, `instance_matches`, `children_initialized`,
`service_ready` and overall `ready` were false. The candidate API did log
application startup completion before shutdown. Those process observations
did not establish the updater's complete readiness condition.

The [4.46.3 source correction](../releases/4.46.3.md) allows **180 seconds for
startup readiness** when the transition is executed by the updated updater or
a compatible operator running that code. The **90-second stop bound** and all
HTTP, process-identity, instance and child checks remain unchanged. Existing
60-second failure receipts stay intact. An older running 4.46.1 updater retains
its 60-second deadline; publishing new candidate code does not replace that
process or retroactively alter its transition.

Focused startup regressions passed **22/22, with 22 deselected, in 0.79 seconds**,
including readiness at **105 simulated seconds** with one start per child,
finite deadlines and refusal of missing readiness or identity evidence.
The full service-update and real host-desktop regression selection passed
**46/46 in 15.37 seconds**. This source evidence does not prove the timeout's
precise cause on the actual host or a successful later update.

Release/native/deferred-pair dispatch for 4.46.3 was stopped before launch;
no 4.46.3 release branch or installed acceptance existed at this checkpoint.
The backup and controller-shutdown work, all earlier failures and their private
receipts remain preserved. Raw process logs and private identifiers are not
published. Full custody/recovery and fresh native backup delivery/restore
remain unaccepted, and V08 telemetry remains Planned and inactive.
