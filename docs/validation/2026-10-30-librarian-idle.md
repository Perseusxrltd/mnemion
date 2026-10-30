# Librarian idle backoff and committed-work wake

30 October 2026. Actual Windows Grok source `f44806c5` adds a bounded idle
backoff and a process-local wake. Test correction `baea9334` was reviewed by
Astra. The combined, formatted source was checked at `df9a4e4d`.

The runner sleeps for 2, 4, 8, 16, then at most 30 seconds when no job is
processed. A successful queued API response signals it only after the database
transaction commits. Clearing the signal before checking durable work prevents
a wake during that check from being lost. Active steps continue to wait on the
stop event for two seconds, so repeated wakes cannot accelerate model calls.
The existing claims, leases, initiating identity and processing budgets are
unchanged. Resource pressure, active work and cross-process submission can still
defer execution; the sleep cap is not a job-start latency guarantee.

Fourteen focused Python checks passed in 11.11 seconds. They cover bounded
idle waits, prompt wake and shutdown, a wake during an empty check, active
pacing, resource refusal, transient failure and absent providers. PostgreSQL
checks cover commit visibility, rejected/empty requests, idempotent replay,
scheduled processing, revoked identities, cancellation/pause ownership and the
Python SDK flow. All 410 service and service-test inputs remained unchanged
through verification. Formatting preserved the Python AST; lint passed.

The original Windows pytest attempt could not collect because `psycopg` was
unavailable. Astra's first Linux check exposed a race in the scripted event
helper, which waited for a brief non-waiting state. Grok corrected it to recognize
the next wait generation. The passing suite used that correction; the original
failures remain retained. Syntax checks were not counted as passing tests.

This establishes scheduler and API behavior, not CPU or RAM savings. The
[whole-product efficiency contract](../implementation/runtime-efficiency.md)
still requires representative idle, tray, active and constrained-hardware
measurements. The [separate Mac admission diagnostic](2026-10-30-telemetry-cpu-admission.md)
does not qualify those measurements or enable production telemetry.
