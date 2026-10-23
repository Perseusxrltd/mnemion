# Backup inventory throughput: source comparison

**23 October 2026, 16:20:20 UTC; UNRELEASED.** The chosen source change computes
the collated JSON representation once while retaining PostgreSQL tuple-sort
memory accounting. This report compares **`legacy` with
`single_json_tuple_sort` only**. It does not establish live backup acceleration
or installed acceptance of the optimization.

## Chosen implementation

The [recovery inventory](../../mnemion/service/recovery.py) selects the JSON text
with `COLLATE "C"`, names it `row`, and sorts by that alias. A constant second
column, **`TRUE AS _inventory_row`**, keeps PostgreSQL on its tuple-sort path.
Only `row` enters the existing newline-delimited SHA-256 calculation; the
constant is not part of the inventory payload.

This removes the second full JSON representation previously carried for sorting
while preserving complete-row coverage and byte ordering. Inventory format 1
retains all stored columns; format 2 still excludes only the regenerated
`search_text` column from `memory_revisions`.

The simpler, single-column `single_json` variant was **rejected**. Its sampled
backend RSS grew with inventory size despite small sort-space figures in
`EXPLAIN`. Its faster timing results are not results for the chosen source and
are not used below. The constant column retains the observed accounting and
disk-spill behavior rather than relying on those misleading memory figures.

## Synthetic resource measurements

The isolated native **PostgreSQL 18.6** database used **`work_mem=1MB`** and
**`shared_buffers=32MB`**. Three fixture/format combinations were measured at
their original and **4×** sizes; the larger query repeats the fixture rows.
Every legacy/chosen pair has identical **row count, serialized byte count and
SHA-256**. The v1/v2 labels below identify inventory formats.

| Synthetic case | Rows | Serialized bytes | Seconds, legacy → chosen | Backend RSS growth (MiB), legacy → chosen |
| --- | ---: | ---: | ---: | ---: |
| `memory_revisions` v1, 1× | 2,000 | 37,335,734 | 0.869 → 0.534 | 2.84 → 2.63 |
| `memory_revisions` v1, 4× | 8,000 | 149,342,936 | 4.627 → 1.947 | 3.84 → 3.32 |
| `memory_revisions` v2, 1× | 2,000 | 17,314,000 | 0.492 → 0.311 | 3.21 → 2.95 |
| `memory_revisions` v2, 4× | 8,000 | 69,256,000 | 1.992 → 1.274 | 3.48 → 3.21 |
| `connector_pages` v1, 1× | 8,000 | 18,400,000 | 0.370 → 0.215 | 3.01 → 2.34 |
| `connector_pages` v1, 4× | 32,000 | 73,600,000 | 1.181 → 0.940 | 2.48 → 2.25 |

All six chosen plans used **external merge sorting on disk**. Sampled peak
backend RSS growth stayed about **2.25–3.32 MiB**. This is growth above each
backend's baseline after a warm-size read, not total server RAM or a hard
process-memory ceiling. The separate measurement safety cap was 512 MiB.

Elapsed time covers the cursor query, streamed rows and hashing, with one timed
observation per variant/case in a fixed order. RSS was sampled every 5 ms and
continued through the subsequent `EXPLAIN ANALYZE` pass. These observations do
not measure complete snapshot creation, encryption, Git transfer, readback or
restore, and do not predict a production backup's duration.

## Evidence and remaining acceptance

The production-query regression and existing portability selection passed
**9 tests in 47.78 seconds**. The regression compares both inventory formats
with the released query, including Unicode, NULLs, duplicate rows and an
additional table without a primary key. Formatting changes were applied after
that run; the query and behavior are unchanged.

The authoritative private resource receipt is `resources/receipt.json`, SHA-256
`c6126dcab34a03c5c7ae6443c0747d2bb292cb942610681bca3a4b3fb905631c`,
under the dated `2026-10-23-backup-inventory-throughput` evidence directory.
It retains the exact counts, bytes, hashes, timings, RSS samples and plans.
`resources/process-receipt.json`, SHA-256
`9192e99572bde3084e27b9c0b2ad58d35fceb85e58f9114e92210eb025aa7995`,
records successful start/stop and **`isolated_database_stopped: true`**.
The earlier `measure.py` and top-level `receipt.json` are superseded for this
chosen implementation; their timings are not used in this report.

Release and actual-host performance qualification remain separate. No live
backup acceleration, fresh backup delivery or independent restore is claimed
by this source measurement. The [accepted custody journey](2026-10-23-4463-custody-acceptance.md)
has its own installed evidence. All [66 requirement texts and states](../PRODUCT_REQUIREMENTS.md)
are unchanged, and
[V08 product telemetry](../implementation/anonymous-product-telemetry.md) remains
Planned and inactive.
