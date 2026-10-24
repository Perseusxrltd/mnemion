# Browser telemetry delivery coordination: source validation

**24 October 2026, 06:43:00 UTC; unreleased source, V08 Building.** The browser
budget and cancellation coordinator passed at **component scope**. The
[budget design](../implementation/anonymous-product-telemetry-budget.md#browser-origin-budget)
describes its origin-local Web Locks, localStorage spending and persisted queue
clear intent. This is not production-sender or released-telemetry acceptance.

The reviewed source comprises the
[budget schema](../../studio/frontend/src/workspace/telemetry-budget.ts),
[delivery coordinator](../../studio/frontend/src/workspace/telemetry-delivery.ts)
and [browser policy](../../studio/frontend/src/workspace/telemetry-policy.ts).
The [focused delivery tests](../../studio/frontend/scripts/test-telemetry-delivery.mjs)
exercise the same source through controlled fixtures.

| Check | Result and scope |
| --- | --- |
| Focused browser tests | **44 passed, zero failed or skipped**, in 1.484 seconds: 30 preceding tests plus 14 delivery tests. |
| TypeScript check | Passed; its saved log is empty. |
| Actual Chromium 144.0.7559.96 journey | **20 checks passed**, using real tabs, Web Locks, localStorage and an isolated plain-loopback HTTP server. |

The separate fixture bundle overrides only its in-memory disclosure and supplies
a controlled loopback handoff. The repository disclosure remains
`collection_available: false`, `destination: null`. Its input manifest binds
nine repository inputs and the fixture bundle; all nine source hashes, the
bundle hash and the journey's referenced manifest/log hashes matched on review.
The fixture is not a production frontend or installed sender.

The actual journey verified:

- Two tabs racing to reserve obtained exactly one shared attempt. Reservation
  consumed old cells while retaining contributions and spending. Reload and
  explicit re-enable did not refund the allowance.
- Cross-tab opt-out blocked a final handoff before an HTTP request. A separate
  isolated profile then started one guarded fetch; the server received the
  **original four body bytes** before local erasure. Another tab's opt-out aborted
  the outstanding fetch once, without retry, and cleared the lease/queue while
  preserving spending. This did not retract the bytes already received.
- An injected quota failure retained spending and the clear intent. Another tab
  and a reload stayed closed until an owned mutation reconciled the queue under
  its Web Lock. Consumed samples were discarded, contribution limits survived
  and the spent attempt could not be replayed.

Across the three journeys there was **exactly one report request**, **zero
production-memory calls**, **zero cloud-model calls** and **zero non-fixture
requests observed in the test contexts**. No uncaught browser errors occurred.
Cleanup was separately verified at **06:45:17 UTC**: all three isolated contexts,
the owned browser session and the loopback server closed.

This evidence qualifies the tested browser coordinator and controlled fetch
cancellation. It does not qualify a production sender, canonical owner wiring,
actual whole-wire cost, TLS/provider metadata handling, whole-app resource
limits, all platforms or V08 release acceptance. Four body bytes exclude HTTP
and transport overhead. The 65,536 bytes are a fixed reservation; the actual
transport upper bound remains unqualified. The existing targets of 2 MiB added
RSS and 0.5% of one core, privacy/utility limits and all 66 requirement states
are unchanged. Earlier
native/Python evidence remains preserved in the budget design.

| Original evidence | SHA-256 |
| --- | --- |
| Focused browser tests | `945aa3c836b4cf4f697c232670300d960908612a253acf3d900f4d3349777739` |
| TypeScript check log | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Actual Chromium journey receipt | `fd7fd8b875824b91270e4faa27e2fd9435c6181991af17d488d0d70b5287f2da` |
| Actual journey log | `db1db9b50fc9d3ef1fe85c4fac7441f4183498840e9f89aca652059c09daab93` |
| Fixture input manifest | `60608b97d49feba5264d48e59979f258e4a988321dbc1c8bf774e99e0f6c7520` |
| Separate fixture bundle | `5d63fe32d5611e26125dda828cc3327908e104e981b36693ff12b176e6dd21b7` |
| Verified cleanup receipt | `6fabf7699769bad64df9adcb95d2f5add15a1c92951cc3973691d224ff2438fb` |
