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
