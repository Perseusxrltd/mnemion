# Agent telemetry action timing — 27 October 2026

This source correction was prepared on
`6ac7700312e9c77a9793cd6e740419f1b39e2c5e`. Python-owned action latency now
includes the optional contribution and privacy-policy reads performed before
the action. This aligns the Python boundary with the existing Studio behavior.
It improves measurement accuracy; it establishes no resource saving.

## Reproduced defect and correction

The [Python workflow owner](../../mnemion/product_telemetry/workflow.py) used to
start its clock after reading local telemetry state. A slow policy read could
therefore delay the action without appearing in its recorded latency.

The regression uses real private SQLite policy and aggregate storage with a
controlled monotonic clock. It advances by 400 ms during the contribution
read, 250 ms during the authority read and 10 ms during the action. Both the
fixed-category and selected-category paths originally persisted the 10–49 ms
bucket. They now persist the 200–999 ms bucket for the complete 660 ms interval.
These are controlled clock values, not measured storage-performance results.

The owner captures its start before those reads and retains its original
privacy revision and store generation. An invalid or backward clock drops the
measurement once, instead of manufacturing a zero-duration observation or
allowing a second completion. Unavailable collection returns before clock or
policy access. No new telemetry permission, scope, destination or payload field
is introduced.

## Verification and limits

The focused Python selection passed **135 tests**: workflow/CLI, standalone
source/capture work, automatic host updates, model preparation and local stdio
MCP owners. It includes the two reproduced timing failures after correction,
four invalid-clock cases, opt-out during work, original-generation fences,
fresh/replayed receipts, contribution limits and unchanged action results when
telemetry is unavailable. Ruff lint and formatting passed.

The private `2026-10-27-telemetry-agent-timing` evidence retains
`checks/timing-before.log` and `checks/owned-workflows.log`; the original two
failures are not replaced by their passing follow-up.

No new resource workload or native release was dispatched for this correction.
The [completed process-owned comparison](2026-10-27-telemetry-resource-roles.md)
still fails the unchanged **2 MiB added RSS** ceiling. Platform, resource,
production-ingress/privacy and aggregate-utility acceptance remain open.
All 66 requirements remain retained; V08 is **Building**, production collection
is `false`, destination and route are `null`, and release CAs remain empty.
