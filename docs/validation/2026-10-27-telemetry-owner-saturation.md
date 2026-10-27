# Browser and Python delivery after saturation — 27 October 2026

This source follow-up is based on
`29dcd70d79b763e274731a94a9b2948603df5250`. Original checks retained two real
Python TLS failures: queued delivery was not revisited after a refused late
finish or an exhausted early begin. A fresh standalone CLI also unnecessarily
imported the activity runtime. The original browser-source ready case made zero
mocked POSTs instead of one.

The [browser recording boundary](../../studio/frontend/src/workspace/telemetry-policy.ts)
now reoffers the shared owner's prior committed stamp after the Web Lock is
released, even when recording is refused. The
[Python activity](../../mnemion/product_telemetry/activity.py) retains one
immutable prior committed stamp under its existing lock, coalesces fresh offers
and awake refusals at the same minute cadence, and clears that stamp on close.
[Workflow completion, resource recording and early exhaustion](../../mnemion/product_telemetry/workflow.py)
can notify only an already-loaded, registered owner. A standalone CLI no longer
imports activity or `asyncio` merely to offer collected work.

These changes add no timer, process lifetime, contribution or delivery budget.
The old stamp does not authorize a send: fresh policy, generation, admission,
spending and final-send gates remain mandatory.

## Scoped checks and retained CI failure

The final Python qualification is **137 distinct checks**: 136 unchanged passes
plus one corrected MCP schema check. The
[transport tests](../../tests/test_product_telemetry_transport.py) include six
late-finish/early-begin cases for ready, opt-out and closed owners, plus the
standalone import check. Ready sends once through real local TLS; opt-out and
close send zero. No extra contribution is admitted.

[Source CI job 122118845312](https://github.com/Perseusxrltd/mnemion/actions/runs/40483312151/job/122118845312)
failed because a legacy assertion still expected five origin maps after
`classic_cli` was added. The same failure reproduced locally alongside the 136
passes. The corrected [schema test](../../tests/test_product_telemetry_mcp.py)
includes that map and verifies that schema inspection records no action; it
passed separately. This correction changes no runtime behavior, and both original
logs remain retained.

**96 browser-source checks passed, with zero skips**, including three new
ready/opt-out/page-exit cases in the
[policy tests](../../studio/frontend/scripts/test-product-telemetry.mjs).
Fetch, locks and admission are mocked; these checks do not qualify an actual
browser, TLS or platform. SDK and frontend builds passed. Earlier native tests
were not repeated.

All **852 inputs** matched inventory digest
`2f71619f939a21dd46d4557489a0239a4e921aa9558b86fb3dc059b9f763c80b`.
The closed source-qualification receipt has SHA-256
`bf11c578c0ac97acc4eab73f145a00956e1f14a96bdb6ade8da99292287875b6`.

The [completed desktop comparison](2026-10-27-telemetry-delivery-comparison.md)
predates these browser/Python changes: six functional journeys passed, but the
2 MiB resource gate still failed. It does not qualify this follow-up or prove
the cause of [original run 40477197149](2026-10-27-telemetry-catalog-comparison.md).
No additional app comparison, release or collection activation is selected here.
All 66 states, the 29 unmeasured CLI paths and the
[remaining acceptance requirements](2026-10-27-telemetry-acceptance-ledger.md)
remain unchanged. V08 is **Building**, collection/destination/route remain
**false/null/null**, release CAs are empty, and the **2 MiB / 0.5%** ceilings hold.
