# Native telemetry SQL reads — 27 October 2026

Source follow-up based on `d72b90d6e182ddeb022ddf65dcfa3a895a059c3b`.
The [preference reader](../../studio/electron/telemetry-store.ts) now reads
current-schema preferences and schema/application/journal metadata through
one fixed SQL statement returning an array. Only a SQL compilation error
(`ERR_SQLITE_ERROR`, code 1) permits the fixed legacy query, whose result must
be schema 3 or 4. Busy, corrupt and I/O errors do not select that fallback.
Legacy connection mode remains `auto`.

Pending-row reads take a complete array snapshot before removing disallowed
groups. The 513th-row overflow sentinel still enforces the 512-row limit, and
cell/count/day validation remains. [Delivery](../../studio/electron/telemetry-delivery.ts)
reuses validated cell/count pairs. Fresh transaction, private-file, company
policy, consent, generation and final-handoff checks remain; no database handle
or positive permission is cached across transactions.

The Electron build passed. The four store/delivery/owner/transport test scripts
ran in **Node 22.22 on Linux x64**: **125 total, 123 passed, zero failures and
two Windows-only skips**, in 87.84 seconds. These are source/component checks;
they did not run an actual Electron application journey or qualify installed
platform behavior. Results are retained in `source-checks.json` and
`native-privacy.log`.

All **708 selected inputs** were verified unchanged after the source tests,
with digest
`99661e85a78d7f5fe1f31ca952aa1dc3cc466c95a3b989d02d7d49fba0b6885c`.
The subsequent fast-forward from `d72b90d6` to
`56bb40a01f5736c742be0d95add5a54beb605971` changed only the two selected
generated status snapshots, `deploy/maintenance-status.json` and
`deploy/release-status.json`. `upstream-input-transition.json` confirms that
application and test inputs were unchanged; the native tests were not rerun.
Release preparation then verified six version-only changes among the 708
selected inputs (`4.46.41` to `4.46.42`); all other selected bytes were unchanged.
The generated agent contract remained byte-identical. The separately qualified
publisher change is recorded in the [publication report](2026-10-27-release-publication-status.md).

No RSS or CPU saving is established. The [earlier actual-app comparison](2026-10-27-telemetry-delivery-comparison.md)
and all failed resource results remain retained against the unchanged
**2 MiB added RSS / 0.5% of one core** ceilings. A changed-source app comparison
was planned at this source-stage checkpoint. The subsequent
[original Electron run](2026-10-27-telemetry-sql-comparison.md), 40523504727,
completed all six functional cases with source/ownership/cleanup qualification;
both enabled main-process matched RSS maxima still exceeded 2 MiB. That later
app evidence does not reclassify these earlier Node checks or qualify resources.

All 66 requirements and **V08 Building** remain unchanged. Production
collection/destination/route remain **false/null/null**, with empty release CAs.
Resource, installed/platform, provider/privacy and full telemetry acceptance
remain open in the [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md).
