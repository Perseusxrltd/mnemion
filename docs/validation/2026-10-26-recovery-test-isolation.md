# Recovery checks with an isolated queue

The frozen [4.46.10 release run](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798)
failed its [Python 3.12 service job](https://github.com/Perseusxrltd/mnemion/actions/runs/40245659798/job/121326661609)
before the recovery operation began. After draining available work, the test
saved a new memory and expected the next globally claimed job to have that
memory's operation ID. The worker returned another operation. The job finished
with **2,275 passed, one failed and nine skipped**; coverage was **86.22%**, above
the existing 75% requirement.

The service fixture shares a database across tests. The production scheduler
deliberately claims jobs across tenants; delayed work or an older lease can
become eligible after a drain. The retained failure does not identify which
earlier test created the returned operation.

Follow-up source uses the existing per-test PostgreSQL fixture for recovery
checks. It retains real non-owner database roles, migrations and the normal
scheduler, while separating the backup and leased-job assertions from other
tests' queue state. No production worker or recovery behavior changed, and no
assertion was removed.

On Linux with Python **3.12.3**, the complete recovery module passed **12 tests
in 71.75 seconds**. This includes deletion reconciliation, revoked grants and
keys, key rotation, and resetting the intended leased job during restore.

The original frozen release remains failed. This source correction does not
qualify the separate [Windows installed restart failure](2026-10-26-windows-host-restart.md),
published updates, or telemetry. Product collection stays disabled and V08
remains Building.
