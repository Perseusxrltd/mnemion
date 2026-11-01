# Managed update retry verification — 1 November 2026

Source `1ebf50dddfd5a0c26d5099e103bc120ac7cd518d` passed **165 tests in
27.29 seconds** across the transport, persisted schedule, managed updater and
host-observation privacy suites. This was one focused source run using the
existing release environment. Formatter changes preserved the Python AST.

The checks cover temporary DNS/network/timeout classification, safe error
history, local write errors, both jitter endpoints, two-attempt exhaustion,
persisted restarts, disabled updates and operation-lock contention. A
nontransient check exception clears the spent allowance; a later temporary
failure starts a new bounded retry episode. Certificate, HTTP, integrity,
staging and apply failures retain the ordinary schedule.

Signed-manifest cases exercise the real compatibility check, including a
successful retry and an operator-required schema boundary. Stage and apply
are controlled fixtures in these cases. Existing signature, immutable-version,
replay, backup and recovery checks remain in the focused updater suite. The
privacy cases verify that credential-bearing exception text does not enter
the new fixed transport diagnostics or host observations.

The implementation adds no background worker or polling loop. It schedules at
most two earlier checks after a qualifying failure, using the existing wait,
deadline, lease and saved-preference controls. This does not establish measured
whole-product CPU/RAM budgets, a real network-outage recovery, or next-release
automatic adoption. Those operational observations remain separate.

The source suites are [transport](../../service_tests/test_update_transport.py),
[schedule](../../service_tests/test_update_schedule.py),
[updater](../../service_tests/test_service_updates.py) and
[host observations](../../tests/test_product_telemetry_host_updates.py).
See the [managed update guide](../service/managed-updates.md) and
[schema-boundary upgrade guide](../service/managed-upgrades.md) for operation.
All 66 requirement states remain unchanged; V08 is Building and production
telemetry collection remains off.
