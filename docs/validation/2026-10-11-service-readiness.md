# Service initialization and rollback validation

The Intel Mac Product check in [run 38132099845](https://github.com/Perseusxrltd/mnemion/actions/runs/38132099845)
accepted a candidate whose worker later failed, producing an updater-restart
error instead of the expected runtime rollback. Supervisor `RUNNING` means a
process survived `startsecs`; it does not establish application initialization.

The new API/worker startup acknowledgements bind readiness to the actual PID,
process creation time, instance, loaded version/package and model generations.
A second Supervisor snapshot rejects changes during inspection. Missing, stale,
wrong-generation and mismatched receipts cannot make a protocol-1 runtime ready.

Verified staging records the readiness protocol. Earlier runtimes without this
capability keep their previous readiness contract for adoption and rollback,
with `children_initialized: null`. The fix therefore does not strand an older
rollback target while requiring acknowledgement from capable new candidates.

## Executed evidence

On Linux/WSL, Python 3.12 with disposable PostgreSQL and separate restricted
service roles, a systemd user scope capped the suite at 2 GiB RAM, no swap and
200% CPU:

```text
MNEMION_TEST_MANAGED_INSTALL=1 MNEMION_TEST_UV=<pinned uv 0.12.24>
python -m pytest service_tests/test_supervision.py service_tests/test_service_updates.py service_tests/test_managed_service.py -q
34 passed in 123.96s
```

The suite blocks a real worker before initialization after Supervisor and HTTP
both look ready, proves that readiness stays false, and then allows startup to
finish. It checks crash/restart receipt replacement, stale process identity,
loaded version and model-generation mismatches.

Both signed-package update fixtures install actual locked environments and
verify live API/worker/updater processes, backups and source integrity. An
intentionally broken candidate accepts a memory through its still-live API;
rollback preserves that memory and one written before cutover. The test runs
with both a receipt-capable previous runtime and a protocol-zero fixture that
emulates the older no-receipt contract. The latter is a fixture compatibility
test, not a downloaded historical-release rehearsal.

Ruff formatting/lint and `git diff --check` pass. Native Intel/ARM Mac checks
and the combined-source release gates remain required. This work does not claim
to resolve the separate public Linux desktop restart stall.
