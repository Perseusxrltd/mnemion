# Collector serving-process crash checks — 27 October 2026

This tests-only follow-up is based on
`62b9ab71e761a4e759e55d67ba9fc4e875e90eb8`. The existing
[Linux startup protection](2026-10-27-telemetry-crash-boundary.md) is unchanged.
The full [collector test file](../../tests/test_product_telemetry_collector_server.py)
passed **21 cases in 17.98 seconds**, with no failures or skips; Ruff passed.
The total includes the earlier 19 cases and two new actual serving-process
crashes, not 21 additional cases.

Both new cases ran on Linux kernel **6.6.87.2-microsoft-standard-WSL2**, whose
core handler was piped. One collector opened its own listener; the other used
the real inherited-socket path with descriptors supplied by the fixture.
This did not install or exercise a systemd service unit.

Each owned child received an incomplete synthetic request over real TLS, then
`SIGABRT` through its PID file descriptor. Kernel `waitid` reported
**`CLD_KILLED`, never `CLD_DUMPED`**, and the child exited for `SIGABRT`.
The isolated fixture retained no core file, TLS key log or stdout/stderr output;
the canary was absent from retained SQLite state. A fresh report-export process
returned an empty report list. These checks exercise a serving collector,
extending the earlier probe that replaced the serving function.

The deliberately faulted children had isolated environments without user or
provider credentials and temporary working directories. No global kernel
policy, live service or provider setting changed. The runtime already disabled
dumpability; this batch changes tests only. The WSL2 piped-handler observation
is separate from the earlier read-only production-host observation.

All **435 selected inputs** were verified unchanged, digest
`4630dc1c5fec0e438ba7d01f0187e8c9d06d8fbbd2523c4838412ca445298f8d`.
Retained `collector-qualification.json` has SHA-256
`a56d0e3d6dadc0abf57265ea999227dbaffe556aeb321e5caa0d8af98b1f8875`;
it records the original checks and input verification without another test run.

This qualifies the stated Linux process-crash boundary. It does not qualify
privileged host/provider snapshots, production logs/backups/retention, an
installed collector, macOS or Windows. The production collector remains absent.
Resource, whole-wire, platform and aggregate-usefulness acceptance remain open
in the [ledger](2026-10-27-telemetry-acceptance-ledger.md). All 66 requirement
states and **V08 Building** remain unchanged; production collection/destination/
route remain **false/null/null**, with empty release CAs.
