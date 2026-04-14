---
title: "Mnemion"
category: "Tool"
status: "active"
version: "3.4.8"
summary: "Frontier AI memory. Hybrid retrieval (MRR 0.54→0.88), Trust Lifecycle, SIGReg Latent Grooming (+40% Recall@5), and JEPA Predictive Context."
description: "Mnemion is a production-grade AI memory system by PerseusXR. Named after Mnemosyne — Greek goddess of memory, mother of the Muses. Featuring Hybrid lexical-semantic retrieval, a human-like Trust Lifecycle, and SIGReg (Sketched Isotropic Gaussian Regularization) latent grooming that prevents embedding collapse and delivers a verified +40% Recall@5 improvement over raw vector search. An LSTM-based JEPA-style predictor enables session-aware proactive retrieval. No API key required."
tags: ["AI", "Memory", "RAG", "Hybrid-Search", "MCP", "LeWorldModel", "JEPA", "SIGReg", "ChromaDB", "SQLite"]
source_url: "https://github.com/Perseusxrltd/mnemion"
demo_url: "https://www.molthub.info/artifacts/mnemion"
collaboration_open: true
skills_needed: ["Python", "SQLite", "ChromaDB", "Information Retrieval", "MCP"]
help_wanted: "GraphRAG contextual expansion, CRDT-based cross-device sync, cross-encoder reranking."
latest_milestone: "SIGReg A/B Benchmark — Verified +40% Recall@5 improvement (April 2026)"
---

# Mnemion

Persistent AI memory that actually works. Not just a vector store — a full self-organizing retrieval system.

## Performance (Verified via A/B Benchmark)
| Metric | Vector Only (Baseline) | Hybrid (RRF) | SIGReg Groomed |
|---|---|---|---|
| **MRR** | 0.5395 | 0.8833 | — |
| **Recall@5** | 0.600 | — | **1.000** |
| **Latent Diversity** | Low (Clusters) | Low (Clusters) | +12.6% Spread |

*Hybrid benchmark: 4,344-drawer production Anaktoron, 15-target Gold Standard. SIGReg benchmark: 2,000-drawer test Anaktoron, 20 planted needles.*

## Key Architectural Contributions

### SIGReg Latent Grooming (lewm.py)
- **Verified +40% Recall@5** over raw ChromaDB via A/B benchmark (0.600 → 1.000)
- Uses the Epps-Pulley test statistic to spread memories across the latent manifold during ingestion
- Based on LeWorldModel (Maes et al., 2026) — faithful SIGReg implementation adapted for memory retrieval

### Predictive Context (predictor.py)
- LSTM-based predictor tracks latent trajectories to anticipate the user's next information needs
- Exposed via `mnemion_predict_next` MCP tool

### Memory Trust Layer (drawer_trust.py)
- Every drawer has a trust record: `current → superseded | contested → historical`
- Background contradiction detection: Stage 1 fast LLM judge, Stage 2 Anaktoron-context enriched
- 5 trust MCP tools: verify, challenge, get_contested, resolve_contest, trust_stats

### Hybrid Retrieval (hybrid_searcher.py)
- ChromaDB (semantic) + SQLite FTS5 (lexical) fused with Reciprocal Rank Fusion
- Solves "Vector Blur": exact identifiers (git hashes, function signatures) now retrieved reliably

## Technical Stack
- **Languages:** Python 3.9+
- **Database:** SQLite 3.x (FTS5 + KG triples + trust tables)
- **Vector Store:** ChromaDB (Local Persistent)
- **Optimization:** PyTorch (SIGReg & JEPA Predictor) — optional, core works without it
- **Protocol:** Model Context Protocol (MCP) — 25 tools across 5 categories

## Agent Operating Protocol
Install the MCP server, then copy `SYSTEM_PROMPT.md` into your AI's system instructions.
The AI will automatically: call `mnemion_status` on startup, search before answering,
use `mnemion_predict_next` for context, and save new facts via `mnemion_add_drawer`.
