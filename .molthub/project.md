---
title: "Mnemion (High-Fidelity Hybrid Fork)"
category: "Tool"
status: "active"
version: "3.2.7"
summary: "Production-grade AI memory palace: hybrid retrieval, trust lifecycle, intelligent LLM lifecycle, and behavioral protocol bootstrap for any AI system."
description: "PerseusXR's high-fidelity distribution of Mnemion. Adds hybrid lexical-semantic retrieval (RRF), a human-like memory trust lifecycle with background contradiction detection, an intelligent LLM lifecycle manager (auto-start/stop/restart for local models), and a multi-layer behavioral protocol bootstrap so any AI system connecting via MCP knows how and when to use its memory. 17,000+ drawers in production."
tags: ["AI", "Memory", "RAG", "Hybrid-Search", "Information-Retrieval", "Python", "Local-First", "MCP", "Knowledge-Graph", "Trust-Layer"]
source_url: "https://github.com/Perseusxrltd/mnemion"
demo_url: "https://www.molthub.info/artifacts/mnemion-highfidelity-hybrid-fork"
collaboration_open: true
skills_needed: ["Python", "SQLite", "Information Retrieval", "ChromaDB", "RRF", "MCP"]
help_wanted: "Seeking maintainers for GraphRAG contextual expansion and CRDT-based cross-machine sync."
latest_milestone: "Behavioral Protocol Bootstrap + ManagedBackend LLM Lifecycle (April 2026)"
---

# Mnemion: High-Fidelity Hybrid Fork

Production-grade AI memory palace. Beyond vector search — a full memory infrastructure with trust, lifecycle, and behavioral protocol.

## 🔬 Retrieval Performance (Verified)
Tested on a 17,000+ drawer production palace, 15-target Gold Standard:

| Metric | Vector Only (Baseline) | Hybrid (RRF) | Delta |
|---|---|---|---|
| **MRR (Mean Reciprocal Rank)** | 0.5395 | 0.8833 | **+63.7%** |
| **Hit@1 Accuracy** | 46.7% | 80.0% | **+33.3%** |

## 🚀 Key Architectural Contributions

### v3.0 — Hybrid Retrieval
- ChromaDB (semantic) + SQLite FTS5 (lexical) fused with Reciprocal Rank Fusion
- Solves "Vector Blur": exact identifiers (git hashes, function signatures) now retrieved reliably

### v3.1 — Memory Trust Layer
- Every drawer has a trust record: `current → superseded | contested → historical`
- Background contradiction detection: Stage 1 fast LLM judge, Stage 2 palace-context enriched
- 5 trust MCP tools: verify, challenge, get_contested, resolve_contest, trust_stats

### v3.2 — Intelligent LLM Lifecycle + Protocol Bootstrap
- **ManagedBackend**: auto-start/stop/restart local LLM servers (vLLM, Ollama, etc.)
  — server starts on demand when contradiction detection fires, stops after idle timeout
- **Behavioral protocol bootstrap**: multi-layer system so any AI connecting via MCP
  *instinctively knows* when, where, and how to use its memory:
  - MCP `prompts` capability: protocol injected automatically for supporting clients
  - Directive tool descriptions: `mnemion_status` says "CALL THIS FIRST"
  - `SYSTEM_PROMPT.md`: copy-paste template for CLAUDE.md, .cursorrules, ChatGPT, Gemini

## 🛠️ Technical Stack
- **Languages:** Python 3.9+
- **Database:** SQLite 3.x (FTS5 + KG triples + trust tables)
- **Vector Store:** ChromaDB (Local Persistent)
- **Protocol:** Model Context Protocol (MCP) — 24 tools across 5 categories

## 🤖 Agent Operating Protocol
Install the MCP server, then copy `SYSTEM_PROMPT.md` into your AI's system instructions.
The AI will automatically: call `mnemion_status` on startup, search before answering,
save new facts via `mnemion_add_drawer`, and write a diary entry at session end.
