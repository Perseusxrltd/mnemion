# mempalace/ — Core Package

The Python package that powers MemPalace. All modules, all logic.

## Modules

| Module | What it does |
|--------|-------------|
| `cli.py` | CLI entry point — routes to mine, search, init, compress, wake-up |
| `config.py` | Configuration loading — `~/.mempalace/config.json`, env vars, defaults |
| `normalize.py` | Converts 5 chat formats (Claude Code JSONL, Claude.ai JSON, ChatGPT JSON, Slack JSON, plain text) to standard transcript format |
| `miner.py` | Project file ingest — scans directories, chunks by paragraph, stores to ChromaDB |
| `convo_miner.py` | Conversation ingest — chunks by exchange pair (Q+A), detects rooms from content |
| `searcher.py` | Semantic search via ChromaDB vectors — filters by wing/room, returns verbatim + scores |
| `hybrid_searcher.py` | **Hybrid retrieval engine** — fuses vector + FTS5 lexical results via RRF; trust-aware (filters superseded, weights by confidence, flags contested) |
| `layers.py` | 4-layer memory stack: L0 (identity), L1 (critical facts), L2 (room recall), L3 (deep search) |
| `dialect.py` | AAAK compression — entity codes, emotion markers |
| `knowledge_graph.py` | Temporal entity-relationship graph — SQLite, time-filtered queries, fact invalidation |
| `palace_graph.py` | Room-based navigation graph — BFS traversal, tunnel detection across wings |
| `drawer_trust.py` | **Memory Trust Layer** — SQLite trust records per drawer; status lifecycle (current→superseded\|contested→historical); confidence scoring; conflict registry; append-only audit trail |
| `contradiction_detector.py` | **Two-stage conflict detection** — Stage 1: fast vLLM judge (auto-resolves at ≥0.8 confidence); Stage 2: palace-context enriched resolve for ambiguous cases; runs in daemon threads, never blocks saves |
| `llm_backend.py` | **Pluggable LLM backend** — abstract adapter supporting ollama, lmstudio, vllm, custom OpenAI-compatible endpoints, or none. Configured via `mempalace llm setup`. |
| `mcp_server.py` | MCP server — 24 tools, AAAK auto-teach, Palace Protocol, agent diary, trust management |
| `general_extractor.py` | Pattern-based extraction — classifies text into 5 memory types (decision, preference, milestone, problem, emotional) without any LLM |
| `onboarding.py` | Guided first-run setup — asks about people/projects, generates AAAK bootstrap + wing config |
| `entity_registry.py` | Entity code registry — maps names to AAAK codes, handles ambiguous names |
| `entity_detector.py` | Auto-detect people and projects from file content |
| `room_detector_local.py` | Maps folders to room names using 70+ patterns — no API |
| `spellcheck.py` | Name-aware spellcheck — won't "correct" proper nouns in your entity registry |
| `split_mega_files.py` | Splits concatenated transcript files into per-session files |

## Architecture

```
User → CLI → miner/convo_miner → ChromaDB (palace)
                                       ↕
                              knowledge_graph (SQLite)
                              drawer_trust    (SQLite, same DB)
                                       ↕
User → MCP Server → hybrid_searcher → trust-filtered results
                  → kg_query         → entity facts
                  → diary            → agent journal
                  → trust tools      → verify / challenge / resolve

Save path (auto-hook, no AI required):
Transcript → general_extractor → ChromaDB → drawer_trust.create() → contradiction_detector (background thread)
                                          → FTS5 mirror
```

## Trust Lifecycle

Every drawer has a trust record. Status transitions are one-way (never hard-deleted):

```
current → superseded   (LLM or manual: newer info replaces it)
current → contested    (LLM ambiguous, or AI/user challenge)
contested → current    (resolved: this one wins)
contested → superseded (resolved: the other one wins)
any → historical       (drawer deleted: ghost record remains for audit)
```

Confidence starts at 1.0. Verifications raise it (+0.05), challenges lower it (−0.1).
Search excludes `superseded` and `historical` by default; `contested` drawers surface with a `⚠` warning.

## Storage layout

```
~/.mempalace/
├── palace/                  ← ChromaDB vector store
│   └── chroma.sqlite3
├── knowledge_graph.sqlite3  ← KG triples + FTS5 mirror + trust tables
│   ├── triple (entity→rel→entity, bitemporal)
│   ├── drawers_fts (FTS5 lexical mirror)
│   ├── drawer_trust (trust records)
│   ├── drawer_conflicts (pairwise conflict log)
│   └── drawer_trust_history (audit trail)
└── archive/
    └── drawers_export.json  ← portable export for new-machine restore
```
