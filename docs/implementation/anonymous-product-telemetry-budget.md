# Shared telemetry delivery budget — V08

**Unreleased source checkpoint, 24 October 2026; V08 remains Building.** The
[full contract](anonymous-product-telemetry.md) retains its scope. The
[Python delivery component](../../mnemion/product_telemetry/delivery.py) and
[native TypeScript component](../../studio/electron/telemetry-delivery.ts) now
share private reservation accounting and cancellation fences. The focused
[source checks](#source-validation) passed. There is **no product sender, network integration or
production activation**; `collection_available: false`, `destination: null`
and the empty outbound preview remain unchanged.

This follows the [codec/collector/publisher checkpoint](anonymous-product-telemetry-delivery.md).
Its earlier passing checks do not qualify these new budget components, actual
wire usage or installed sender cancellation.

## One private native/Python allowance

[Policy storage version 4](../../mnemion/product_telemetry/policy.py) adds a
seven-slot attempt ledger and one delivery-state row to the existing private
SQLite policy database. Native and Python processes using the same OS account
and configured store serialize reservations with the same database transactions
used for choice changes. This is not a person-wide allowance across independent
installations, browser profiles or copied stores. The public control schema
version is unchanged.

| Source reservation bound | Meaning |
| --- | --- |
| Seven attempts per rolling week | Each committed reservation spends one slot, regardless of its later outcome. |
| At least 24 hours plus jitter between attempts | The next eligible time adds a fresh random delay from zero through one hour. There is no scheduler or idle wake. |
| 65,536 reserved bytes per attempt | Fixed reservation; actual transport upper bound remains unqualified. |
| 262,144 reserved bytes per rolling day | The 256 KiB daily guard applies to the same shared ledger; it does not qualify a transport's actual cost. |
| Five-second prepared-report validity | Both the shared wall-clock lease and a process-local monotonic deadline must remain valid. This is not a network-completion guarantee. |

Reservations require current disclosure and enabled policy, matching revision
and private `store_generation`, a permitted metric group, usable queued cells,
and an explicitly unmetered, unconstrained connection observation. Unknown or
metered connectivity and pressure conservatively refuse the attempt. The future
sender must provide fresh observations; these components do not detect a network
or start a connection themselves.

Backward wall-clock movement refuses reservations rather than pruning spending
or restoring allowance. The ledger reader also checks that its latest attempt
matches the saved time, cooldown is 24–25 hours later, any live lease ends five
seconds after that attempt, and an empty ledger has only pristine initial state.
Busy, damaged, unsafe or unsupported storage fails closed. Reading status does
not initialize or migrate a store; older supported controls stores report
`upgrade_required` for delivery accounting. Supported
Python policy writes migrate them within the existing transaction, preserving
the choice and existing generation rules. This is not automatic repair of
damaged settings.

## Reservation consumes the queue

Within one write transaction, reservation rechecks policy, clock, cooldown,
active lease and both spending limits. It selects permitted bounded cells and
prepares one [four-byte randomized body](anonymous-product-telemetry-delivery.md).
Encoding and entropy must succeed before spending is committed. The transaction
then records the attempt and reservation, sets the cooldown and private lease,
and consumes the entire pending measurement queue.

Every returned reservation is spent. Failure, cancellation, crash, a lost result
or an unused report does not refund it or restore the queue. An explicit opt-out
clears pending measurements, local contribution counters and the stored lease,
but **retains spent attempts and cooldown**. Re-enabling cannot revive those
measurements or buy a fresh delivery allowance. The attempt ledger is private
control accounting, not product usage data.

The local [status interface](../guides/product-telemetry-controls.md) exposes
bounded attempt counts, reserved-byte totals and fixed states through
`delivery_budget`. It does not expose exact attempt times or lease tokens.
Those values and the local generation never enter the report body or analytics
identity. Counters describe reservations, not successful uploads; `ready` is an
accounting state and does not enable collection.

## Cancellation and the final handoff

A prepared report is a process-local, one-use body with a private lease and the
originating revision/generation. Revalidation checks current choice, disclosure,
company groups, clock and lease deadline. A process-local monotonic deadline
also limits eligibility to five seconds from preparation's start, so stalled
wall time cannot extend it. Cancellation retains the token for
matching stored-lease cleanup while clearing the reusable local report. Invalid
checks and failed or expired handoffs use that same cancellation path after
closing their transaction. Spending remains consumed. Busy or unreadable storage
can prevent immediate durable cleanup, but an expired lease does not authorize a
later handoff.

The final `guarded_write` / `guardedWrite` operation takes the SQLite write lock,
rechecks permission and consumes the local handle before invoking one reviewed
**synchronous, nonblocking socket handoff**. That same lock serializes an explicit
choice change. DNS, TLS setup, response waiting, arbitrary callbacks and awaited
work do not belong inside this critical section. The source currently has no
transport to hand bytes to. Bytes already handed to a transport cannot be
recalled by a later opt-out; installed cancellation still requires its own proof.

The optional watcher checks the current report at a nominal 25 ms interval only
during an already active attempt. It can request abortion when permission or the
lease is lost. It is not an idle task, a scheduler, a shutdown flush or a substitute
for the final handoff check. The future transport must own watcher cleanup on
success, cancellation and shutdown. The interval alone is not a measured
cancellation-latency guarantee. A throwing synchronous abort callback is
suppressed without a retry or second invocation; report cleanup still runs.

## Source validation

| Final source check | Result and scope |
| --- | --- |
| Python | **55 passed in 10.95 seconds** across delivery, policy, aggregate and MCP cases. |
| Actual Electron 44.9.3 / Node 24.22.0 on Linux | **19 passed, two Windows-only ACL skips**, 21 total, in 8.908 seconds: ten delivery and nine existing store successes. |
| Native source build | Passed; no installed-package or all-platform acceptance follows. |

The focused checks cover shared reservations between real Python and Electron
processes, crash/restart spending, contention, opt-out before the final callback,
one-use handoff, lease cleanup without refunds and a stalled wall clock bounded
by the monotonic deadline. Both watcher outcomes now run: a successful abort
callback and one that throws, with no second invocation or forwarded fault.
They use synthetic queues and controlled callbacks, not an installed sender or a
qualified network transport. The preceding **54 Python / 18 Electron** results
and earlier **44/53 Python passes and 17 Electron passes with two Windows-only
skips** remain historical;
the initial TypeScript row-narrowing compile failure is also retained. Selected
Ruff checks passed before this final callback follow-up. The final runtime runs
include cleanup, ledger-invariant, monotonic-deadline and abort-fault handling.

| Original evidence | SHA-256 |
| --- | --- |
| Final Python abort-fault selection | `161c843074568c4d6d00d58062bcbee724c32069f66b571025760dca4524599d` |
| Final actual Electron abort-fault selection | `a7720ea447a021eb1356cde90b28557cf533b8b3eb589bee0f66c9196ba8cfcf` |
| Final native source build | `873b841c25f2b8da83857d248087de185ea22e1986b5fb6eb43f96e70e00896b` |
| Earlier Python monotonic-deadline selection | `399a76b383d7cd5934aca5b04f55951bbf6b17bdf6c8c00fe735f6883d6559a2` |
| Earlier actual Electron monotonic-deadline selection | `e48f9dd09639bf1df24149ea9449cb8c4cfa74410096d480e5fab09408bc8e85` |
| Earlier Python cleanup selection | `d6bb33fb1f37c75435e7c716b5b47c3590d1fa435527754f7c8d68a85f040112` |
| Earlier actual Electron selection | `e15ec9ff989c8cec7ef1fc9365fe21f2fd5432bc8caf8c0e30a974cb73864d9c` |
| Original TypeScript compile failure | `7887ed8c125489e4ef87d5857d704c8b123148b4b337f1d80aed2dbc86ba46a6` |

## Remaining acceptance

The conditional per-report `ln(3)` bound still protects only the sampled category
in a chosen permitted view. A seven-report composition bound depends on every
actual attempt using this shared allowance; no sender integration establishes
that yet. These local controls do not establish participation, policy-choice,
person-wide or lifetime privacy. They do not recover spending after a store is
lost or recreated, or detect an unobservable whole-machine snapshot rollback.
Rejection of an older prepared report after recreation has a
[source test](../../tests/test_product_telemetry_delivery.py). That
is distinct from recovering lost allowance: the generation/disclosure rules
cannot reconstruct a missing attempt ledger.

Wiring the canonical owners to this allowance, browser delivery coordination,
actual sender integration and cancellation, conservative accounting of all
connection/retry overhead, qualified ingress and retention, and all six native
targets plus web remain open. Earlier component resource diagnostics do not
qualify the unchanged **2 MiB added-RSS** and **0.5% of one core** limits. The
codec's small-population utility limits are unchanged. No requirement is closed
by these source components.
