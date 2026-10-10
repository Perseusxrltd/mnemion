# Implementation, migration, and validation roadmap

[Study overview](README.md) · [Architecture](ARCHITECTURE.md) · [Evidence](EVIDENCE.md)

This is a proposed sequence for implementation. The study itself changes documentation and diagnostic artifacts only. The target is shared memory infrastructure for applications and teams, with **Obsidian visualization preserved as a required integration**.

## Delivery order

Estimates below are planning ranges in engineer-weeks for experienced contributors, not measured delivery commitments. They assume a self-hosted PostgreSQL service, Python/TypeScript SDKs, a bounded set of integrations, reuse of the existing interface, and no initial high-availability or peer-to-peer replication project. Approximately **12–22 engineer-weeks** reaches a small team pilot; calendar duration depends on staffing, migration complexity, and the adoption comparison. Existing customer data size and deployment obligations are unknown.

| Phase | Effort | Deliverable and dependency | Exit gate |
| --- | --- | --- | --- |
| 0. Stabilize and preserve v3 | 1–2 weeks | Review current local changes, repair urgent correctness paths, produce complete legacy backup/export inventory | First-save recall, retry completeness, quarantine enforcement, and restore validation regressions pass; dependency issues are fixed or explicitly dispositioned |
| 1. Contract and adoption comparison | 1–2 weeks | Domain/API schema, identity model, migration fixture, comparable PostgreSQL/Hindsight/Mem0 prototypes | Choose components against the same lifecycle and cost requirements; document decisions and licensing |
| 2. Authoritative service core | 3–5 weeks | PostgreSQL migrations, scoped auth, versioned evidence, idempotent ingest, durable workers | Two clients share authorized memory; crash/retry tests preserve acknowledged writes; an Obsidian export can address the same stable record |
| 3. Retrieval and truth lifecycle | 2–4 weeks | Lexical/vector baseline, versioned embedding generation, evidence hydration, corrections, deletion receipts | Held-out evaluation works; all projections obey live policy; no stale job revives a withdrawn revision |
| 4. Clients, Obsidian, and migration | 3–5 weeks | SDKs, maintained MCP gateway, compatibility aliases, vault migration, native Obsidian visualization | Existing IDs/links resolve; manual notes survive refresh; an isolated v3 copy migrates and restores successfully |
| 5. Operator console and team pilot | 2–4 weeks | Ingestion/review/export UI, observability, recovery drills, release pipeline | Pilot workload and recovery objectives met on declared hardware; required desktop/native checks complete |

Some work can overlap after the contracts stabilize: SDK generation, console adaptation, and Obsidian fixture preparation. Identity and lifecycle decisions must precede broad connector implementation. Advance by exit gates rather than treating the dates as automatic approval to cut over.

## Immediate v3 backlog

| ID | Priority / owner role | Concrete change | Acceptance evidence |
| --- | --- | --- | --- |
| B01 | P0 / storage engineer | Centralize save completion and reconcile existing partial writes; route sweeper/miner/capture through it | Fail after each persistence step, retry, and confirm exactly one complete logical record with lexical and trust state; R02/R03 |
| B02 | P1 / backend engineer | Refresh or initialize collection handles safely; eliminate concurrent lazy-create races | Empty-install save/search works through MCP and Studio; concurrent startup requests succeed; R01 |
| B03 | P0 / retrieval engineer | Apply current trust/source checks to reconstruction, evidence trails, graph injection, and exports; enforce scope and final limit | Quarantine after consolidation, cross-wing graph source, and deleted evidence fixtures remain excluded from ordinary retrieval; R04/R05 |
| B04 | P1 / retrieval engineer | Re-sort after weighting, separate similarity from fused relevance, order lexical matches, enforce FTS row replacement | Correct top-1 after weighting; documented score contract; no old lexical row after re-mining; R06/R07/R08 |
| B05 | P0 / storage engineer | Introduce a complete versioned backup manifest; reject malformed/partial restores; document Git sync limitations | Round-trip sources, trust, history, and core blocks; truncated or corrupt input fails; deletion cannot be resurrected; R09/R10/R11 |
| B06 | P1 / evaluation owner | Fix query-specific ground truth and NDCG; run actual baselines; revise unsupported README claims | Wrong needle scores zero; missed relevant documents reduce NDCG; baseline call counts are nonzero; R12/R13/R15 |
| B07 | P0 for network use / backend engineer | Retain local token-on-read improvements, redact secrets, and review the network boundary | Anonymous reads blocked when configured; provider keys absent from read/update responses; authorization is not represented as CORS alone |
| B08 | P1 / release engineer | Update dependency locks deliberately; run current advisory gates and packaged smoke checks | Resolved or explicitly investigated advisories with runtime/build exposure rationale; successful native release checks |
| B09 | P1 / integration engineer | Snapshot Obsidian compatibility and preserve edited generated notes through conflicts/manual sections | Existing paths and wikilinks survive; both exporter variants preserve annotations and unmanaged notes |
| B10 | P2 / maintainer | Isolate prediction/grooming experiments and clarify capture/startup behavior | Normal installation and documentation make no unsupported guarantee; R14 |

The v3 bridge should fix urgent behavior without attempting to grow a second team architecture inside the old sidecar design. First review the existing local changes and preserve their intent; do not reset or overwrite them as part of the rebuild.

## The first v4 vertical slice

Use two applications, two spaces, two credentials, and a synthetic v3 fixture. An application saves a project decision with a source and idempotency key. Another authorized assistant recalls it and follows a citation. An unrelated-space credential cannot search, fetch, enumerate, export, or infer its evidence. A reviewer records a changed decision. The original remains traceable while ordinary recall prefers the current approved state.

Export the same records through the local Obsidian client. Existing wing/room/entity links remain valid; the decision links to its source and correction. Append a personal annotation, refresh, and verify preservation. Delete or quarantine the source, then verify the service and the appropriate export view enforce that transition. Kill a worker during processing and retry. Restore the fixture into a fresh environment and repeat the assertions.

This slice tests the product's defining behavior before committing to richer graph algorithms, dozens of connectors, or expensive automatic reflection.

## Migration from v3

1. **Inventory and preserve.** Record the application version, active profile paths, all writer entry points, Chroma collections, SQLite schema/tables, raw sources/attachments, core blocks, trust history, wiki pages/manual sections, export manifests, and the entire Obsidian vault including its settings. Hash the inventory. Capture a consistent source snapshot using supported backup methods or a planned write pause; a file copy of a live WAL database is insufficient.
2. **Prove recovery before transformation.** Restore the snapshot into an isolated v3 environment and compare records, source hashes, trust states, and vault paths. Keep this verified snapshot immutable. Do not rely only on the current drawer JSON export.
3. **Assign ownership explicitly.** Map the legacy profile to an owner organization and private space by default. Do not infer public/team access from wing names or an author field. Flag ambiguous owners/entities instead of silently merging them.
4. **Import canonical evidence first.** Preserve original IDs as aliases, raw bytes, timestamps, content hashes, trust/quarantine states, and correction relationships. Missing trust/source records become visible migration exceptions or unverified records; do not invent verification. Record counts and rejected items.
5. **Build derived state in parallel.** Recreate lexical indexes, embeddings with a declared fingerprint, and scoped knowledge projections. Keep legacy and v4 stores separate. Compare searches against a fixed representative query set with expected evidence, not only counts.
6. **Migrate Obsidian in a copied vault.** Preserve the old path map and manifest. Compare current files against the old generated output where possible; retain edited originals and create conflicts where ownership is uncertain. Keep manual sections, unmanaged files, attachments, and settings. Resolve wikilinks and block citations, then inspect the native graph. No automatic folder renaming or blanket regeneration.
7. **Cut over through one controlled writer boundary.** Either pause all legacy writers briefly or capture every writer's changes in a durable journal. Account for MCP, Studio, hooks, miner, sweeper, capture, and sync scripts. A dual-write patch covering only the API is insufficient. Import the final delta and record a cutover watermark before switching clients.
8. **Keep rollback actionable.** Retain the verified old snapshot and routing configuration. If v4 accepts new writes, rollback requires replay/export of that tail and the latest deletion ledger; simply reopening the older database loses new information. Rehearse rollback with the fixture before a real cutover.
9. **Observe and reconcile.** Track missing projections, stale jobs, rejected records, authorization errors, and Obsidian refresh conflicts during the pilot. Retire the old writer paths only after the compatibility period and successful reconciliation.

Migration is complete only when canonical counts/hashes and lifecycle state reconcile, every exception is explained, a restore succeeds, and client/vault compatibility checks pass. A matching vector count alone is not sufficient.

## Evaluation that can guide design

Maintain two independent suites: deterministic correctness invariants and retrieval/answering evaluations. Keep fault-injection and permission tests independent of nondeterministic model quality.

| Evaluation dimension | Required cases and measurement |
| --- | --- |
| Isolation | Different tenants/spaces, subjects with the same name, guessed IDs, graph neighbors, profiles, evidence fetch, export, cache reuse, and worker context. Zero unauthorized outputs in the defined test matrix is a release gate. |
| Durability | Crash before/after commit, crash after projection write, duplicate delivery, lease expiry, repeated idempotency key with a changed payload, concurrent revisions, and out-of-order jobs. No acknowledged source revision lost in the tested scenarios. |
| Lifecycle | Quarantine after indexing, source correction, disputed facts, temporal queries, deletion after export, old backup restore, and invalidated citations. Verify every output path. |
| Obsidian | Legacy path mapping, standard YAML, duplicate/Unicode/Windows filenames, wikilink and block resolution, manual-section preservation, conflict behavior, scoped export, manifest-only pruning, interrupted refresh, and native graph inspection. |
| Retrieval | Exact IDs, paraphrases, names, time windows, multi-session evidence, changing preferences, French/English and cross-language questions, and irrelevant/ambiguous questions. Measure Recall@k, MRR, NDCG, citation precision, and abstention separately. |
| Answering | Fixed answering model and prompt, citation correctness, changed facts, evidence sufficiency, and human-reviewed samples. Report this separately from retrieval recall. |
| Performance and cost | Declared corpus/hardware/concurrency; warm and cold p50/p95 latency, ingestion lag, storage, model calls/tokens, and cost per correctly answered task. Record all retrieval and synthesis stages. |
| Recovery | Complete backup/restore and deletion-ledger reconciliation; failed/truncated/unsupported archives must not publish a partial database. Measure recovery time on the pilot workload. |

Build query-specific relevance judgments. NDCG's ideal ranking uses all ground-truth relevant items up to the cutoff. Run real vector-only, lexical-only, hybrid, and optional graph/reranker systems through the same harness. A full-context answer baseline can also be informative when its token cost is recorded.

Use public LongMemEval/LoCoMo tasks only with documented licensing, corpus preparation, and train/dev/test splits. Tune on development data and evaluate held-out questions once per declared configuration. Complement them with synthetic app/team workflows and, later, an explicitly selected representative corpus. Prevent entity/time heuristics from encoding test answers. Report per-category results and uncertainty, rather than one rounded “100% memory” figure.

A provisional pilot workload can begin around 100,000 records across several spaces with 10 concurrent clients, then change to match actual usage. Those are planning inputs, not a demonstrated capacity claim. Agree on latency, indexing-lag, recovery, and per-task cost budgets after measuring the baseline.

## Release and maintenance gates

Keep CI checks aligned with the product: domain tests, authorization/failure invariants, migration fixtures, API compatibility, SDK examples, current dependency audits, source/wiki/Obsidian fixtures, and browser save/search/review flows. Add native Windows packaging and launch validation before publishing a Windows installer. Test any additional desktop platform that is advertised as supported.

Use database migrations and release compatibility metadata connecting service, schema, SDKs, MCP adapter, Studio, and export format versions. Raise coverage expectations around critical services by testing meaningful invariants; a blanket percentage increase would not have detected the present failures by itself. Enable a working issue/support path and publish a dated capability matrix that distinguishes stable, preview, and experimental features.

Select a currently supported Python runtime for the v4 service and verify the dependency matrix on it; legacy Python 3.9 support should not determine the new server architecture. Upgrade React, routing, build tools, and Electron in reviewable groups with corresponding UI and packaging checks. A framework major-version bump is justified by maintenance or needed behavior, rather than by its version number alone.

The final pilot gate is a demonstrated workflow across an application, an assistant, and Obsidian with durable saves, scoped retrieval, correction, deletion, and recovery. That is the most direct test of the product the user wants Mnemion to become.
