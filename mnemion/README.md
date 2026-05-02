# mnemion/ — Core Package

The Python package that powers Mnemion. All modules, all logic.

## Modules

| Module | What it does |
|--------|-------------|
| `cli.py` | CLI entry point — routes to ingest, search, repair, reconstruct, guard, eval, compress, wake-up |
| `config.py` | Configuration loading — `~/.mnemion/config.json`, env vars, defaults |
| `backends/` | Storage backend facade — Chroma implementation, typed result shims, guarded collection creation |
| `normalize.py` | Converts 5 chat formats (Claude Code JSONL, Claude.ai JSON, ChatGPT JSON, Slack JSON, plain text) to standard transcript format |
| `miner.py` | Project file ingest — scans directories, chunks by paragraph, stores to ChromaDB |
| `convo_miner.py` | Conversation ingest — chunks by exchange pair (Q+A), detects rooms from content |
| `sweeper.py` | Message-granular Claude/Codex JSONL ingest with deterministic IDs and cursor resume |
| `searcher.py` | Legacy semantic vector search API retained for compatibility |
| `hybrid_searcher.py` | **Hybrid retrieval engine** — fuses vector + FTS5 lexical results via RRF; trust-aware (filters superseded, weights by confidence, flags contested) |
| `query_sanitizer.py` | Reduces prompt-contaminated long queries to the actual search intent |
| `layers.py` | 4-layer memory stack: L0 (identity), L1 (critical facts), L2 (room recall), L3 (deep search) |
| `dialect.py` | AAAK compression — entity codes, emotion markers |
| `knowledge_graph.py` | Temporal entity-relationship graph — SQLite, time-filtered queries, fact invalidation |
| `anaktoron_graph.py` | Room-based navigation graph — BFS traversal, tunnel detection across wings |
| `cognitive_graph.py` | Structured cognitive graph — extracts typed units, causal edges, and topic tunnels from raw drawers |
| `reconstruction.py` | Active reconstruction — searches cognitive evidence first, then hydrates raw drawers with evidence trails |
| `memory_guard.py` | Memory risk scanner — flags instruction-injection/privacy bait and can quarantine drawers |
| `moat_eval.py` | Deterministic moat eval cases for structure, causality, forgetting, and security |
| `repair.py` | Storage repair helpers — Chroma health, pruning, rebuild, and max_seq_id repair |
| `trust_lifecycle.py` | **Memory Trust Layer** — SQLite trust records per drawer; status lifecycle including quarantined drawers; confidence scoring; conflict registry; append-only audit trail |
| `contradiction_detector.py` | **Two-stage conflict detection** — Stage 1: fast LLM judge (auto-resolves at ≥0.8 confidence); Stage 2: Anaktoron-context enriched resolve for ambiguous cases; runs in daemon threads, never blocks saves |
| `llm_backend.py` | **Pluggable LLM backend** — abstract adapter supporting ollama, lmstudio, vllm, custom OpenAI-compatible endpoints, or none. Configured via `mnemion llm setup`. |
| `mcp_server.py` | MCP server — memory, KG, trust, reconstruction, guard, diary, and LeWM tools with AAAK auto-teach |
| `general_extractor.py` | Pattern-based extraction — classifies text into 5 memory types (decision, preference, milestone, problem, emotional) without any LLM |
| `entity_registry.py` | Entity code registry — maps names to AAAK codes, handles ambiguous names |
| `entity_detector.py` | Auto-detect people and projects from content using locale-aware patterns |
| `project_scanner.py` | Manifest, git-author, and prose entity discovery before regex scanning |
| `corpus_origin.py` | Corpus-origin detection and `.mnemion/origin.json` persistence |
| `entity_patterns.py` | Locale-pattern loader for entity detection |
| `room_detector_local.py` | Maps folders to room names using 70+ patterns — no API |
| `spellcheck.py` | Name-aware spellcheck — won't "correct" proper nouns in your entity registry |
| `split_mega_files.py` | Splits concatenated transcript files into per-session files |

## Architecture

```
User → CLI → miner/convo_miner → ChromaDB (Anaktoron)
                                       ↕
                              knowledge_graph (SQLite)
                              drawer_trust    (SQLite, same DB)
                                       ↕
User → MCP Server → hybrid_searcher → trust-filtered results
                  → reconstruction   → evidence trails + topic tunnels
                  → kg_query         → entity facts
                  → memory_guard     → quarantine risky drawers
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
any → quarantined      (memory guard: hidden pending review)
any → historical       (drawer deleted: ghost record remains for audit)
```

Confidence starts at 1.0. Verifications raise it (+0.05), challenges lower it (−0.1).
Search excludes `superseded`, `historical`, and `quarantined` by default; `contested` drawers surface with a `⚠` warning.

## Storage layout

```
~/.mnemion/
├── anaktoron/               ← ChromaDB vector store
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
