# Classic CLI ownership and visible gaps — 27 October 2026

This source follow-up is based on
`bc4d6e0892af35e5952f14a4d18e35924c2a0157`. The
[CLI entrypoint](../../mnemion/cli.py) now uses a
[bounded observer](../../mnemion/cli_measurement.py) and
[reviewed command map](../../mnemion/product_telemetry/cli-origins.json)
for nine command paths under the local OS account's acknowledged policy:

| Command path | Fixed workflow |
| --- | --- |
| `search`, `source search` | `memory.recall` |
| `wake-up` | `memory.context` |
| `reconstruct` | `memory.knowledge` |
| `restore` | `memory.import` |
| `source list` | `memory.list` |
| `source read` | `memory.read` |
| `obsidian sync`, `obsidian setup` | `memory.export`; dry-run previews excluded |

Arguments, paths, queries, output and returned contents remain outside telemetry.
The observer preserves stdout, `main()`'s `None` return and original exceptions,
and invokes the command once. Read-only command exceptions are classified as
failed; mutation exceptions remain unconfirmed, and interruption is cancellation. Direct handlers
and invocations with `telemetry_owner=False` add no owner. Opt-out, company
restrictions, unreadable policy and the original revision/generation fence remain
authoritative. The inactive process does not import policy, workflow or delivery
runtime. Recorded work can offer delivery only to an existing eligible local
owner; this adds no CLI keepalive, sender or shutdown flush.

## Inventory and source checks

The [static extractor](../../deploy/telemetry_cli_actions.py) reads literal
`argparse` paths without importing the CLI or handlers, and rejects unsupported
declaration syntax. Its **49 leaf paths become 51 rows** with two preview variants:
**nine mapped, 13 excluded and 29 unmeasured**. Unreviewed commands remain visible;
hand-parsed options, other entrypoints and their runtime behavior still need
reconciliation.

The [generated inventory](../../mnemion/product_telemetry/workflow-coverage.json)
now has **688 rows: 373 mapped, 278 excluded, eight delegated and 29 unmeasured**,
from eight interfaces across seven checked owners. All **94 categories** remain
mapped. The preceding 637-row inventory (364 mapped, 265 excluded, eight delegated,
zero unmeasured) is historical; its category coverage did not establish coverage
of these CLI paths.

Two original regressions are retained: classic search emitted no observation,
and classic commands were absent from the action inventory. The corrected source
passed **66 Python checks in 6.47 seconds** across CLI ownership, coverage, MCP
inventory and CLI smoke, plus **one targeted browser-source preview check**.
The [CLI checks](../../tests/test_product_telemetry_classic_cli.py) cover original
results/exceptions, refusal and nested controls, opt-out/re-enable/storage loss
before completion, preview exclusions, inactive imports and equality with the
actual `argparse` tree. These are source/component checks, not an installed CLI
or browser journey. SDK, Electron and frontend builds now passed. The separate
[delivery-opportunity follow-up](2026-10-27-telemetry-delivery-opportunity.md)
records 50 actual Electron owner/transport and five browser-activity source checks;
the earlier preview remains one test, not an additional repeated pass.

The final qualification confirms **690 CLI/Python/frontend inputs** unchanged
after the checks, with inventory digest
`154b2ce0ffed2cfd0a0ae2cbd0966ddde109c425c8c158db307ec33eecb28a1f`.
The linked delivery report records the separate final 851-file inventory that
also covers the native changes.
Dependency graphs matched cached dependencies; **zero installations** were made.

The [original catalog comparison](2026-10-27-telemetry-catalog-comparison.md)
remains failed: the second enabled case made no reservation or delivery, and the
summary was absent. No app rerun or RSS/CPU saving is credited. The unchanged
**2 MiB / 0.5%** resource ceilings and installed, wire, provider/privacy and
aggregate requirements remain open in the
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) and
[canonical contract](../implementation/anonymous-product-telemetry.md#required-acceptance-evidence).
All 66 requirement states are retained; V08 remains **Building**, production
collection/destination/route **false/null/null**, and release CAs empty.
