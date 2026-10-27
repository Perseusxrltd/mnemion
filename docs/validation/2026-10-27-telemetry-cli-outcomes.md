# CLI variants, bounded outcomes and repair preview — 27 October 2026

This source follow-up is based on
`f47ef224b8aa8572ca960e7b43cfde2471237524`. The
[reviewed CLI map](../../mnemion/product_telemetry/cli-origins.json) now represents
**63 fixed rows: 32 mapped, 29 excluded and two unmeasured**. `split` and
`llm test` still lack a reviewed telemetry category/boundary and remain visible.
The [whole action inventory](../../mnemion/product_telemetry/workflow-coverage.json)
has **700 rows: 396 mapped, 294 excluded, eight delegated and two unmeasured**.
All **94 categories** remain mapped; eight interfaces feed seven checked owners.
The [earlier 688-row/29-unmeasured checkpoint](2026-10-27-telemetry-cli-coverage.md)
retains its original scope and evidence.

The [entrypoint](../../mnemion/cli.py) and
[observer](../../mnemion/cli_measurement.py) select only fixed variants:

- Supported dry-run mutations are previews; quarantine also defaults to preview
  unless `--apply` is present.
- Librarian status and repair status are excluded. Repair scan has its own
  `sources.scan` mapping; repair application and preview remain distinct.
- Wiki compile distinguishes review from apply; explicit dry-run is excluded.
  Saved diffs/impact inspection, status and path display do not imply applied work.

Selected new mutative or possibly early-return commands deliberately finish as
`unconfirmed`; normal return does not prove all intended effects occurred.
Private arguments, content, output and result objects remain opaque to the
observer. Existing stdout, return/error behavior and the original policy fence
are retained. Nested mining, compilation and consolidation remain within their
enclosing invocation rather than adding another owner.

The global **`--no-telemetry`** option suppresses observation for that invocation
without changing the saved installation choice. Both automatic hook-generated
`mine` subprocesses in [hooks_cli.py](../../mnemion/hooks_cli.py) now use it.
Direct handlers and calls with `telemetry_owner=False` remain unowned. No CLI
sender, keepalive or shutdown flush is added.

## Product repair correction and checks

The default rebuild path previously ignored `repair --dry-run` and continued
through extraction, backup and deletion. Its retained regression reached the
backup/rebuild path. The corrected command stops after reading the collection
count: **no drawer extraction, backup, deletion or rewrite**. The
[repair preview fixture](../../tests/test_cli_repair_preview.py) guards that
boundary; this is not an installed storage qualification.

Two original defect reproductions remain: missing owned `source add` observation
and the repair dry-run failure. Focused Python checks initially returned
**125 passes and three fixture failures**, because quarantine fixtures supplied
a positional identifier instead of required `--drawer-id`. Only those three
fixtures were corrected and rerun, all passing: **128 distinct qualified cases**,
not a single all-green 128-case rerun. The original failure log is retained.

The existing on-demand preview check passed **one browser-source case, zero
skips**, with generated inventory equality and unchanged privacy state.
SDK/frontend builds and lint/format checks passed. All **584 source inputs**
were verified unchanged after the builds, with inventory digest
`b456bcc92cd00b3ac195a7417a3c6645fdd2de6e1649f36ba2fe279c512ab00d`.
No installation, model execution, real app journey or native/platform rerun was
performed for this batch.

These are source checks, not resource savings or complete workflow coverage.
The [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) retains all
resource, privacy, platform, wire, aggregate and release gates and prior failures.
All 66 requirements remain unchanged; V08 is **Building**, collection/destination/
route remain **false/null/null**, release CAs are empty, and completion
notification remains pending.
