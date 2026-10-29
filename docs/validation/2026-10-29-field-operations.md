# Activity, default search and backup observations — 29 October 2026

These **4.46.44** field observations extend the
[earlier lexical comparison](2026-10-29-mcp-field-sessions.md). They provide
partial acceptance evidence; issues **44, 47 and 48 remain open**. The
[field-readiness contract](../implementation/multi-agent-field-readiness.md)
retains the full requested scope.

## Activity and default-mode requests

The normal principal read **eight initial activity pages across eight visible
scopes in 11.354684 seconds**. One additional cursor page succeeded with **zero
overlap** with its first page. This verifies that page transition, not complete
history or all eleven reported scopes. Equivalence to the reporter's principal
and accessible corpus remains unverified.

Actual default-mode searches omitted `mode`; they did not force lexical mode.
They used the same normal principal, query `mnemion`, `all_accessible: true` and
`limit: 3`. One serial client and four separately initialized concurrent
HTTP/MCP clients all returned **three hits, two warnings, `matched` and `success`**.
The concurrent starts were spread over **0.000291 seconds**.

| Request | Elapsed seconds |
| --- | ---: |
| Serial | 41.866472 |
| Concurrent client 1 | 11.483794 |
| Concurrent client 2 | 14.192541 |
| Concurrent client 3 | 19.563938 |
| Concurrent client 4 | 11.357962 |

These are individual observations with uncontrolled background load and cache
state. They do not establish the reporter's improved-hybrid criterion or explain
the reported `generation_changed` / `database_unavailable` failures.

## Scope, model policy and sampling limits

Successive scope lists contained **11 → 9 → 8 → 11** entries; the cause is
unknown. A **02:32:58 UTC** follow-up again listed eleven normal-principal scopes
and one source diagnostic. The administrator view found four published connector
scopes: **three current** (two Git, one filesystem) and **one filesystem scope
suspended with `provider_unavailable`**. No capture, sync, resume or configuration
change was made; this later state does not explain the earlier scope changes.

Model-metadata reads found eight administrator scopes reporting
local E5 execution without network egress. Configuration reads for three reviewer
scopes were forbidden (403), leaving those reads unqualified. The fixture's
`all_active_embeddings_local: false` is not evidence of remote inference.
A separate **02:14 UTC** inspection of the actual API and worker processes found
**zero configured remote profiles and offline mode in both**. Those are policy
observations, not a network capture. Metadata/policy inspection made no model
calls; the default-mode search probes allowed inference.

The fixture's `numeric_semantic_scores: 0` selected the wrong fields. Actual
`score_method` and `relevance_score` values were not sampled, although their
field names were recorded. This count establishes neither fallback nor absent
semantic ranking; that qualification remains open.

Despite its filename, `process-sample-during-hybrid.json` was recorded at
**02:19:39.958 UTC**, **63.397 seconds after** the four-client run finished at
**02:18:36.561 UTC**. The database-owner sample lacked visibility into runtime
session states. A later sample under the runtime roles could see those states,
but was also taken after the requests. These and the later background-process
classification are contextual observations, not concurrent latency attribution.
Other agents' processes were present; observation stopped no processes and
changed no settings or data.

The initial private fixture misread its credential envelope after listing nine
scopes. It made **zero model-metadata and zero activity requests**. Only its
credential reader was corrected; the failed receipt is retained and no product
code changed. The earlier zero-search, two-stream SDK fixture failure also
remains in the linked lexical report.

## Delivered backup and retained controller failure

The actual **4.46.40 → 4.46.44** upgrade succeeded. An independent GitHub manifest
read confirmed delivery at **02:20:22 UTC** of the post-upgrade snapshot captured
at **01:44:53 UTC** and ledger captured at **02:05:07 UTC**. Both captures report
4.46.44. Delivery is now verified; the earlier lexical probe's pending-backup
state remains valid for its own observation time.

The original snapshot unit nevertheless **failed at its 45-minute timeout after
delivery**. The original driver was stopped for inspection. No migration or
backup capture was replayed. Reconciliation retains the timeout and
`full_guarded_upgrade_acceptance: false`. Full guarded acceptance remains
pending. Delivery confirmation does not
erase this failure or qualify recovery.

Maintenance was installed at **03:06:04 UTC** after active backup work drained;
ledger, snapshot and cache-maintenance timers were restored, and the installed
helper readback matched. The first hourly cleanup unit exited 0 at **03:07:58**
while ledger capture was busy, but `last-cache-maintenance.json` was absent at
the **03:11:29** check. This does not qualify successful real garbage collection.
The new scheduled ledger capture succeeded at **03:08:40**, with remote delivery
verified at **03:15:59**. A separate manager receipt binds the original
**03:06:06 → 03:16:30** ledger lifecycle to `JOB_RESULT=done`; the later invocation
is distinct. That job consumed **31.012 CPU seconds over about 10 minutes
24 seconds**, with **700 MiB peak memory**. Performance, full cache maintenance
and guarded acceptance remain open; original capture/cleanup failures are retained.

The later [scheduled-delivery gate report](2026-10-29-backup-pack-index-repair.md)
records successful captures followed by a **03:42:06 UTC** Git publication
failure from stale pack-index references. The guarded upgrade stopped before
actions and the observed host remained 4.46.44. After four local Git cases,
production index repair preserved refs and deleted no packs or backup archives;
publication still exited 1. All three timers were restored active. The follow-up
guard stopped at **04:09:01** with no actions or additional captures requested.
Ownership repair then completed at **04:21:38** with archive inventory preserved
and no memory-service restart. The corrected uploader was installed at
**04:24:13** after eight real Git cases and three cleanup cases passed; its first
fixture failure is retained. Fresh snapshot and ledger captures succeeded and
Git add completed, but push timed out at **05:07:49** after **600 seconds**.
The independent remote ref remained unchanged; all three timers were restored.
The original guard stopped at **05:08:28** without actions. The separate
publish-only attempt used normal snapshot priority, with no new capture or
increased Git timeout, but failed before push at **05:20:40** during optional
multi-pack bitmap generation. All three timers were restored and its guard
stopped at **05:23:02** with zero actions. Ordinary Git connectivity passed with
MIDX and bitmaps disabled. New delivery, performance and the guarded upgrade
remain pending.

The field probes made no memory writes or configuration changes. The original
requirements, feature scope and **V08 Building** state are unchanged; product
telemetry collection remains unavailable. No private contents, names, host
addresses, credentials or private identifiers are published here.

## Retained evidence

Field receipt names are relative to the retained observation bundle; delivery
and maintenance rows identify the separate backup receipts. SHA-256 values bind
the exact records, including failed and inconclusive observations.

| Receipt | SHA-256 |
| --- | --- |
| `result.json` | `508d4387a6523737c843891c7b9ffb324756d2a36982df47ee3c108270c88918` |
| `corrected-credential-shape/result.json` | `7bd34962479698fdc33dbaf581ccaaa96d1ec894635bbd348886f71ca35d4434` |
| `corrected-credential-shape/fixture-correction.json` | `7c8e9d29bd28d6a68b4c8859ddf82e6075178d57a45a191a4442fa79f7fb45f2` |
| `default-hybrid/serial-44644.json` | `a062bbdf78345345b9de385cbe4a5e85449cdb513b6efae2537df0a23d1db949` |
| `default-hybrid/concurrent-44644.json` | `e083c1562064af62afda862346b1b82655c54df8e5ec60b4b3d59d1da32e1889` |
| `normal-models/result.json` | `0457ee62f29868158dd93e4eab204a5f5a107047ed79657be3d4ead4b0e16a19` |
| `live-model-process-policy.json` | `ce8a114216732ca98aec533d25dc78ed826bb4c7b6a1b84047f26b7543491ff6` |
| `process-sample-during-hybrid.json` | `943285dad22a0df798c14e1cf7bba70f0d152e05b2909bce7b633ba6033deb3e` |
| `database-activity-sample.json` | `62fac976a2cdfd5ee043b7ce8d40b8b60674ebe8454ba6553a13dbf98db2726f` |
| `database-activity-by-runtime-role.json` | `5c221f78fc723131530294c8792aa97ced1b1f6f07ac25fe3f89a312767b79ea` |
| `background-process-classification.json` | `4935161fb185ddba3ee1868ee8503f4a2f17d40197d562be2862b3923a56acd3` |
| `source-lease-followup.json` | `73c41cae909bacea0442186d847524197e4ea899b5f3dec90ca899d44aa3d6ce` |
| `post-upgrade-delivery.json` | `b46936b74575fcd787e69fe8a791364b099d3bbbe8b6b039211f493f31be0eac` |
| `delivery-reconciliation.json` | `2235a957ebd93edcca3a92c0ddbb0d10c19de325e58fd808f8af03ac5521deea` |
| `handover-outcome.json` | `4209502b2cb3a6484b6df09825dd83e47bb30fbaca50a15cfce7fc82711e4c33` |
| `post-install-backups.json` | `149cd9bf78ac45c49f4aec1e27d0f21ab15ce468f78461f53bb3d5db59a10199` |
| `maintenance-status-0311.json` | `7e2566a720d9acf677440e8e865b1d1217ae6bd2d38ed1bd7a55f3c9d8c0f303` |
| `post-install-backups-0317.json` | `9d714872b73ab2b4f45e2a619ce65d55204f12b82954767e80f44624184cad27` |
| `post-install-ledger-lifecycle.json` | `3675bbf6a1e3b78f3311e23e2df41a72280b7e3f4a64297d046e674c2d04b87b` |
