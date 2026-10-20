# Queue workload visibility — 20 October 2026

Source candidate: 4.36.0. The existing reviewer-scoped insights response now
includes at most six numeric groups for pending, leased or failed indexing and
purge jobs. Historical state totals remain available.

**Six PostgreSQL diagnostics checks passed**. The expanded scope test verifies
current reviewer access, denial to readers and unscoped administrators, and
revocation after a cached request. A separate workload case verifies:

- UTF-8 byte totals and the largest input, excluding a larger different space.
- Separate purge counts with no reported indexing input bytes.
- Future retry backoff, retry counts and the age of an older pending job.
- A current lease is not due; an expired lease is due; failed work is not due.
- Cancelled embedding work remains in history without appearing as outstanding.

**One real browser flow passed against the actual API and PostgreSQL**, showing
two indexing jobs and one physical cleanup job with the measured sizes. The
desktop layout and 390-pixel viewport were visually inspected; the table scrolls
within its panel and the page does not overflow. No browser exceptions or
external requests occurred. Omitting only the new optional response field in
the browser transport retained the original queue view; this is response-contract
compatibility, not a claim of a second installed historical server.

TypeScript client and frontend builds passed. The fixtures used deterministic
embedding interfaces without invoking a local or cloud model. They establish
scope, workload semantics and rendering, not production throughput, remaining
latency, a hardware minimum or fleet coverage. Native publication remains a
separate release gate. No database migration or dependency was added after 029.
