# The current memory infrastructure landscape

[Study overview](README.md) · [Architecture](ARCHITECTURE.md) · [Roadmap](ROADMAP.md)

Research was performed on **9 October 2026**, using live public GitHub metadata, documentation, release notes, and selected implementation files. Repository links below pin the inspected commit. These products were not installed or benchmarked in this study. A documented feature is not an independently verified reliability guarantee.

## The strategic change

Persistent memory, local execution, vector search, and MCP connectivity are now common capabilities. Several projects also offer hybrid retrieval, derived knowledge, user profiles, temporal graphs, and application SDKs. Mnemion cannot differentiate simply by adding these features to a larger tool list.

Its strongest opportunity is **shared, inspectable memory with dependable access and lifecycle semantics**: applications can determine what was saved, why a claim is returned, who can read it, how it changed, and whether its deletion or correction has propagated. This combines the useful direction already present in Mnemion's source/wiki and trust work with infrastructure that the current implementation lacks.

## Comparison

| Project | What the inspected sources describe | Most useful pattern for Mnemion | Boundary to verify before adoption |
| --- | --- | --- | --- |
| [MemPalace](https://github.com/MemPalace/mempalace/blob/d439d1e6d01e2680d79fe3f5de5a336722cec779/README.md) | Local verbatim memory, multiple storage backends, server deployment, daemon routing, MCP, agent coordination | Storage contracts, compact agent tools, explicit repair/recovery behavior | Shared-palace coordination and device replication do not establish the required end-user authorization model |
| [Mem0](https://github.com/mem0ai/mem0/blob/b7ad69afda6b6ed030347c66d48a13e4de9dec08/README.md) | Memory API/SDK, ADD-only extraction, semantic/BM25/entity retrieval, temporal support, managed platform | Developer experience, immutable extracted evidence, scoped API usage | Hosted benchmark optimizations and graph features are not equivalent to the open-source SDK |
| [Hindsight](https://github.com/vectorize-io/hindsight/blob/d29b842de948cf714274e3c97d471010ed55c685/README.md) | Retain/recall/reflect service, memory banks, evidence-backed observations, mental models, workers and SDKs | Durable processing, simple operations, cheap recall plus optional synthesis | Bank/tag conventions, authenticated tenant boundary, workload cost, and permission propagation need contract tests |
| [Graphiti / Zep](https://github.com/getzep/graphiti/blob/6ba19a1b4d860c1b72aec8f099f458d424bac90f/README.md) | Temporal knowledge graph with episodes, entities, relationships, hybrid retrieval; separate commercial Zep service | Valid time and recorded time, episode provenance, typed relationships | Graphiti requires an external graph backend; Zep's current engine is a different product |
| [Letta](https://github.com/letta-ai/letta-code/blob/253a3bc812b6d0dd2f4273194c4ab78f9ad9542b/README.md) | Stateful agent runtime, editable memory blocks, MemFS, periodic dreaming, multiple clients | Explicit working context and versioned, inspectable memory | An agent runtime is a different product boundary from assistant-independent memory infrastructure |
| [QMD](https://github.com/tobi/qmd/blob/93d211f9ef4a869a9aed0d075ca767dda552627f/README.md) | Local document retrieval with lexical/vector search, expansion, reranking, and compact MCP | A measurable retrieval pipeline and economical tool surface | Document retrieval alone does not provide team identity, correction, and deletion semantics |
| [Supermemory](https://github.com/supermemoryai/supermemory/blob/02474bb73289a6ddb45891bfda9ec88386053be7/README.md) | Unified memory/document API, static and dynamic profiles, connectors, local service option | Context-oriented API, fast profiles, integration simplicity | Validate which features and processing paths run locally and which depend on hosted services |
| [OpenViking](https://github.com/volcengine/OpenViking/blob/7967eca5845a03320b87f48be7336233a69d42bc/README.md) | Hierarchical context database for resources, memory, and skills; summaries; accounts and optional ACLs | Browseable context and progressive disclosure from summaries to evidence | Current core license is AGPLv3; enterprise deployment capabilities differ from the open-source offering |

## MemPalace: what to learn from upstream

Mnemion's history and retained license notice reflect its MemPalace lineage. Studying upstream is therefore particularly useful, but the versions are not directly comparable just because both use a 3.x number.

At the inspected commit, MemPalace's default branch is `develop` and the README advertises **3.11.0**. The latest release returned by GitHub was **[v3.10.0, published 16 September 2026](https://github.com/MemPalace/mempalace/releases/tag/v3.10.0)**. Treat development documentation, released behavior, and draft RFCs separately.

The September release notes describe a three-tool alternative to the 45-tool server: `palace_query`, `palace_exec`, and `palace_coordinate`. They accept a query language or structured input and reuse existing handlers. Mnemion should adopt the principle of a small stable tool surface. It does not need a new query language or an agent task-coordination subsystem to achieve that goal.

The [storage plugin specification](https://github.com/MemPalace/mempalace/blob/d439d1e6d01e2680d79fe3f5de5a336722cec779/docs/rfcs/001-storage-backend-plugin-spec.md) is marked accepted and includes implementation status. It documents collection isolation, embedder ownership and identity, capability declarations, lifecycle, health, conformance, and maintenance. The inspected README lists Chroma, SQLite exact search, native Rust exact search, Milvus, Qdrant, and pgvector. The important lesson is a precise contract and conformance tests; supporting six engines immediately would multiply Mnemion's migration and operational burden.

The [HTTP transport implementation](https://github.com/MemPalace/mempalace/blob/d439d1e6d01e2680d79fe3f5de5a336722cec779/mempalace/mcp_server/http.py) includes Host/Origin checks and token requirements for network exposure. The [daemon](https://github.com/MemPalace/mempalace/blob/d439d1e6d01e2680d79fe3f5de5a336722cec779/mempalace/daemon.py) and release notes describe centralized write routing and recovery work. These address the same class of local concurrency problems that Mnemion's independent writers create.

Two attractive proposals must not be presented as completed team infrastructure:

- [RFC 004: replicated palace](https://github.com/MemPalace/mempalace/blob/d439d1e6d01e2680d79fe3f5de5a336722cec779/docs/rfcs/004-replicated-palace.md) is **draft, awaiting review**. Its replication boundary trusts admitted devices with the whole personal palace. It explicitly says delegated, family, team, and partial-access workflows require a separate capability layer.
- [RFC 005: agent identity routing](https://github.com/MemPalace/mempalace/blob/d439d1e6d01e2680d79fe3f5de5a336722cec779/docs/rfcs/005-agent-identity-routing.md) is also **draft**. Its `host:agent:project` identity addresses coordination. The released rules use `host:harness:project`. Neither naming convention by itself authenticates a person or authorizes access to another person's memory.

Recommended upstream work: compare a small number of concrete fixes and contracts, retain attribution for any ports, and add Mnemion-specific invariants. Avoid merging a large upstream change set merely to obtain a newer version number. Even the upstream release describes some module refactoring as a physical split using shared package globals; Mnemion needs actual domain boundaries behind its new transports.

## Mem0 and Hindsight: the closest service references

Mem0's current README describes **ADD-only extraction**: one extraction call, accumulating memories instead of destructive UPDATE/DELETE decisions at extraction time. It also describes entity linking and combined semantic, BM25, and entity retrieval. This is a useful correction to systems that let an LLM overwrite evidence while “updating memory.” Mnemion should preserve source revisions and express correction as an explicit new claim with a relationship to the previous one.

The [Mem0 migration guide](https://github.com/mem0ai/mem0/blob/b7ad69afda6b6ed030347c66d48a13e4de9dec08/docs/migration/oss-v2-to-v3.mdx) documents API changes and the removal of graph memory from the open-source implementation in favor of the platform. Its [server authentication code](https://github.com/mem0ai/mem0/blob/b7ad69afda6b6ed030347c66d48a13e4de9dec08/server/auth.py) implements keys and token handling. This makes Mem0 a candidate component, not proof that a hosted feature or benchmark is available simply by importing its SDK.

Hindsight provides a useful separation between `retain`, `recall`, and `reflect`. It distinguishes world facts, experiences, observations synthesized from evidence, and more expensive mental models or knowledge pages. Recall combines several retrieval channels; optional reflection produces a reasoned answer. Mnemion should similarly let an application request evidence without paying the latency or model cost of synthesis every time.

Hindsight's [per-user design guide](https://github.com/vectorize-io/hindsight/blob/d29b842de948cf714274e3c97d471010ed55c685/hindsight-docs/blog/2026-08-04-per-user-multi-tenant-agent-memory.md) distinguishes banks, which bound recall, from tags used for selection. Its [tenant extension](https://github.com/vectorize-io/hindsight/blob/d29b842de948cf714274e3c97d471010ed55c685/hindsight-api-slim/hindsight_api/extensions/tenant.py) maps authenticated tenant context to database schemas. Its [worker poller](https://github.com/vectorize-io/hindsight/blob/d29b842de948cf714274e3c97d471010ed55c685/hindsight-api-slim/hindsight_api/worker/poller.py) uses PostgreSQL job claiming with `FOR UPDATE SKIP LOCKED`. These are materially closer to infrastructure than a background daemon thread.

A bounded adoption comparison should require both candidates to support the same Mnemion contract: evidence links, authenticated scope, idempotent writes, versioned corrections, prompt deletion enforcement, export, and failure recovery. Adoption wins if it lowers maintenance and operating cost while satisfying those requirements. A higher recall number alone is insufficient.

## Graphiti, Letta, and context-oriented tools

Graphiti's episodes and temporal relationships are a better model for “Alice joined Team B in June” than injecting any currently marked graph triple at maximum score. Distinguish **when something was true** from **when the system learned it**, preserve the supporting episode, and allow conflicting sources to coexist. A graph can be introduced as a derived retrieval channel without making it the authoritative permission or evidence store.

Zep's current comparison describes a proprietary Context Graph Engine; older descriptions of Zep as merely a hosted Neo4j setup are stale. Graphiti itself remains a bring-your-own-graph library. The inspected README also marks Kuzu support deprecated. Dependency and deployment assumptions must therefore be dated and pinned.

Letta has also changed: [the original repository](https://github.com/letta-ai/letta/blob/5bcdd177d70fa2b31a754cfcd801e77b2e1ab16a/README.md) now points active development to `letta-code`, with the retired V1 API server on an archive branch. Current Letta Code emphasizes stateful agents, programmatically edited memory blocks, MemFS versioning, and dreaming. Borrow explicit editable working context and visible revisions. Keep the assistant runtime outside Mnemion so unrelated programs can use the same memory service.

QMD demonstrates that lexical search, dense retrieval, expansion, reranking, and concise MCP tools form a useful product without speculative prediction. Its local models and retrieval stages also provide an understandable baseline for evaluating Mnemion's more complex paths.

Supermemory's static/dynamic profiles suggest a good application interface: obtain a compact profile plus query-relevant evidence through one context operation. Its local-service documentation explicitly notes that URL ingestion uses a hosted reader. Mnemion should expose processing policy and connector dependencies instead of treating “local” as an attribute automatically inherited by every input type.

OpenViking's L0 abstracts, L1 overviews, and L2 original content offer a useful navigation pattern for Mnemion's wiki and source archive. Generated summaries should help users choose evidence, while retaining access to the original. The inspected main project is **AGPLv3**, with separately licensed CLI and examples; this matters before incorporating code into the current MIT project. These recommendations concern design patterns and do not copy its implementation.

## Benchmark claims: interpret the units

| Source | Claim in the inspected material | Required interpretation |
| --- | --- | --- |
| MemPalace README | 96.6% raw Recall@5 on LongMemEval; 98.4% hybrid Recall@5 on 450 held-out questions after tuning on 50 | Retrieval coverage, not end-to-end answer accuracy; upstream-reported results |
| Mem0 README | 92.5 on LoCoMo and 94.4 on LongMemEval | Managed-platform scores; README explicitly says proprietary optimizations are absent from the open-source SDK |
| Supermemory README | 95% Recall@15 on LongMemEval with about 720 context tokens; roughly 50 ms profiles | Vendor claims under their configuration; different retrieval cutoff and operating conditions |
| Mnemion README | Recall@5 0.600 to 1.000 for LeWM grooming | Current A/B metric accepts the wrong needle, so it cannot substantiate this claim |

There is no defensible common leaderboard from these numbers. Recall@5, Recall@15, answer scores, context reduction, and profile latency measure different things. Corpus preparation, benchmark split, embeddings, rerankers, models, token budget, and hosted-only processing also differ. No competitor performance claim was reproduced here.

Mnemion should publish its own reproducible evaluation with these variables fixed and disclosed. The evaluation must include authorized scope, changed facts, removed evidence, abstention, multilingual queries, and cost as well as retrieval relevance. Those are central to the user's intended product.

## Source and licensing record

The [machine-readable source index](evidence/sources.json) records repository commits, access times, additional files inspected, and the MemPalace release. At those snapshots, Mnemion, MemPalace, Hindsight, QMD, and the Supermemory repository use MIT; Mem0, Graphiti, and Letta use Apache-2.0; OpenViking's main project uses AGPL-3.0. A repository's license does not establish the rights or feature availability of separately distributed hosted or commercial components. Recheck relevant files when selecting an implementation to incorporate.
