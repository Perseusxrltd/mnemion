<div align="center">

<img src="assets/mempalace_logo.png" alt="MemPalace" width="280">

# MemPalace (High-Fidelity Hybrid Fork)

### Augmented with Hybrid Lexical-Semantic Retrieval (RRF)

<br>

This is a specialized distribution of MemPalace maintained by **PerseusXR**. It preserves the "Verbatim-First" philosophy of the original project while introducing a structural upgrade to the core retrieval architecture to ensure precision in professional engineering and systems environments.

**Hybrid Retrieval Protocol** — We have augmented the vanilla ChromaDB (Vector) store with a parallel **SQLite FTS5** (Lexical) mirror. By fusing these result sets using the **Reciprocal Rank Fusion (RRF)** algorithm, this version achieves significantly higher accuracy for technical identifiers, symbols, and code snippets.

**Objectively Verified** — This implementation has been benchmarked on a local palace of 4,300+ drawers using a 15-target Gold Standard evaluation set. Results show a **+63.7% improvement** in Mean Reciprocal Rank (MRR) for technical string retrieval.

<br>

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]
[![][discord-shield]][discord-link]

<br>

[The Contribution](#senior-engineering-contribution) · [Quick Start](#quick-start) · [Benchmarks](#verified-benchmarks) · [MCP Tools](#mcp-server)

</div>

---

## Senior Engineering Contribution

This fork exists to advance the retrieval fidelity of the MemPalace ecosystem. While the original project provides an excellent foundation for conceptual memory, we observed a "Vector Blur" effect where critical technical symbols were lost in high-dimensional space. 

**Our additions to this distribution include:**

1.  **Fused Hybrid Engine (`hybrid_searcher.py`):** A custom retrieval module that orchestrates simultaneous Lexical and Semantic queries.
2.  **Lexical Mirror (SQLite FTS5):** A structural schema update to `knowledge_graph.py` that indexes every memory drawer for exact keyword matching.
3.  **RRF Fusion Algorithm:** A mathematical fusion layer that prioritizes exact matches (lexical) without losing conceptual context (semantic).
4.  **Dual-Indexing Middleware:** Updates to `mcp_server.py` to ensure atomic writes to both data stores for all incoming AI memories.
5.  **Formal Evaluation Suite (`/eval`):** A verifiable benchmarking framework including a Gold Standard dataset and an automated researcher tool.

---

## Verified Benchmarks

We believe in empirical proof. The following metrics were recorded on a production-density memory palace (4,344 drawers) comparing the **Vanilla Baseline** (Vector-only) with this **High-Fidelity Fork** (Hybrid RRF):

| Metric | Vector Only (Baseline) | Hybrid (RRF) | Delta |
|---|---|---|---|
| **Mean Reciprocal Rank (MRR)** | 0.5395 | 0.8833 | **+63.7%** |
| **Hit@1 Accuracy** | 46.7% | 80.0% | **+33.3%** |

*To reproduce these results, run `python eval/benchmark.py` in this repository.*

---

## Why this fork exists

In high-entropy technical environments (Cryptography, Systems Architecture, Large-scale Refactoring), AI agents must be able to retrieve exact, non-semantic identifiers like:
- Git Commit Hashes (`e8c6ed0`)
- Memory Addresses or Hex Keys (`0x8004...`)
- Case-Sensitive Function Signatures (`verifyAgentKey`)

Standard vector-based RAG often fails these "Hard Tests" because identifiers possess low semantic weight. This fork provides the structural **Lexical Anchor** required for these tasks.

---

## Quick Start

```bash
# Install this high-fidelity fork
pip install .

# Setup and Mining (standard MemPalace commands)
mempalace init ~/projects/myapp
mempalace mine ~/projects/myapp

# Search with High-Fidelity Precision
mempalace search "0x8004210B"
```

---

*(The documentation below is the original project guide by Milla Jovovich & Ben Sigman)*

---

## A Note from Milla & Ben — April 7, 2026

> The community caught real problems in this README within hours of launch and we want to address them directly.
>
> **What we got wrong:**
>
> - **The AAAK token example was incorrect.** We used a rough heuristic (`len(text)//3`) for token counts instead of an actual tokenizer. Real counts via OpenAI's tokenizer: the English example is 66 tokens, the AAAK example is 73. AAAK does not save tokens at small scales — it's designed for *repeated entities at scale*, and the README example was a bad demonstration of that. We're rewriting it.
>
> - **"30x lossless compression" was overstated.** AAAK is a lossy abbreviation system (entity codes, sentence truncation). Independent benchmarks show AAAK mode scores **84.2% R@5 vs raw mode's 96.6%** on LongMemEval — a 12.4 point regression. The honest framing is: AAAK is an experimental compression layer that trades fidelity for token density, and **the 96.6% headline number is from RAW mode, not AAAK**.
>
> - **"+34% palace boost" was misleading.** That number compares unfiltered search to wing+room metadata filtering. Metadata filtering is a standard ChromaDB feature, not a novel retrieval mechanism. Real and useful, but not a moat.
>
> - **"Contradiction detection"** exists as a separate utility (`fact_checker.py`) but is not currently wired into the knowledge graph operations as the README implied.
>
> - **"100% with Haiku rerank"** is real (we have the result files) but the rerank pipeline is not in the public benchmark scripts. We're adding it.
>
> **What's still true and reproducible:**
>
> - **96.6% R@5 on LongMemEval in raw mode**, on 500 questions, zero API calls — independently reproduced on M2 Ultra in under 5 minutes by [@gizmax](https://github.com/milla-jovovich/mempalace/issues/39).
> - Local, free, no subscription, no cloud, no data leaving your machine.
> - The architecture (wings, rooms, closets, drawers) is real and useful, even if it's not a magical retrieval boost.
>
> **What we're doing:**
>
> 1. Rewriting the AAAK example with real tokenizer counts and a scenario where AAAK actually demonstrates compression
> 2. Adding `mode raw / aaak / rooms` clearly to the benchmark documentation so the trade-offs are visible
> 3. Wiring `fact_checker.py` into the KG ops so the contradiction detection claim becomes true
> 4. Pinning ChromaDB to a tested range (Issue #100), fixing the shell injection in hooks (#110), and addressing the macOS ARM64 segfault (#74)
>
> **Thank you to everyone who poked holes in this.** Brutal honest criticism is exactly what makes open source work, and it's what we asked for. Special thanks to [@panuhorsmalahti](https://github.com/milla-jovovich/mempalace/issues/43), [@lhl](https://github.com/milla-jovovich/mempalace/issues/27), [@gizmax](https://github.com/milla-jovovich/mempalace/issues/39), and everyone who filed an issue or a PR in the first 48 hours. We're listening, we're fixing, and we'd rather be right than impressive.
>
> — *Milla Jovovich & Ben Sigman*

---

## The Palace
... (rest of the original guide)

<!-- Link Definitions -->
[version-shield]: https://img.shields.io/badge/version-3.0.0-4dc9f6?style=flat-square&labelColor=0a0e14
[release-link]: https://github.com/milla-jovovich/mempalace/releases
[python-shield]: https://img.shields.io/badge/python-3.9+-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8
[python-link]: https://www.python.org/
[license-shield]: https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14
[license-link]: https://github.com/milla-jovovich/mempalace/blob/main/LICENSE
[discord-shield]: https://img.shields.io/badge/discord-join-5865F2?style=flat-square&labelColor=0a0e14&logo=discord&logoColor=5865F2
[discord-link]: https://discord.com/invite/ycTQQCu6kn
