# PerseusXR Research Notes — MemPalace High-Fidelity Distribution

This document records the engineering decisions and empirical findings behind the PerseusXR fork of MemPalace.

---

## Contribution 1: Hybrid Lexical-Semantic Retrieval (v3.0)

### Problem

In high-entropy technical environments, vector-only retrieval exhibits a "Vector Blur" effect: exact string identifiers (git hashes, function signatures, hex addresses) carry low semantic weight and are routinely outranked by thematically related but inexact results.

### Implementation

**Dual-engine architecture:**

1. **Lexical layer** — SQLite FTS5 virtual table mirrors every drawer's content, enabling BM25-ranked keyword search.
2. **Semantic layer** — ChromaDB vector store (unchanged from upstream), providing conceptual similarity search.
3. **Fusion** — Results merged using Reciprocal Rank Fusion (RRF): `Score(d) = Σ 1/(k + rank(d,r))` across both result sets, where k=60 (smoothing constant).

**Atomicity** — `mcp_server.py` performs dual-writes to both stores on every `add_drawer` call. Inconsistency between stores is impossible by construction.

**Latency overhead** — RRF fusion adds <5ms to retrieval. The FTS5 write is synchronous and adds <1ms to save.

### Benchmark (4,344-drawer production palace, 15-target Gold Standard)

| Metric | Vector Only | Hybrid RRF | Delta |
|--------|-------------|------------|-------|
| Mean Reciprocal Rank (MRR) | 0.5395 | 0.8833 | **+63.7%** |
| Hit@1 Accuracy | 46.7% | 80.0% | **+33.3%** |

*Reproduction: `python eval/benchmark.py`*

---

## Contribution 2: Memory Trust Layer with Contradiction Detection (v3.1)

### Problem

AI memory systems accumulate contradictions over time. Without a lifecycle model:
- Outdated facts coexist with current ones (e.g., old address vs. new address)
- Contradictory preferences both surface in search
- There is no audit trail — you cannot know when a belief changed or why

Human memory handles this through a trust-decay + supersession model: new information doesn't erase old memories, it demotes them.

### Design Principles

1. **Never hard-delete** — memories are soft-invalidated (status: `historical`), not destroyed. Audit trail is append-only.
2. **Pre-compute at save time** — trust status is resolved in the background when a drawer is saved, so fetch speed is unaffected.
3. **Two-stage LLM arbitration** — fast resolution for clear cases, context-enriched resolution for ambiguous ones.
4. **Confidence is continuous** — verifications push confidence up, challenges push it down. Status is a coarse label; confidence is the fine-grained signal.

### Status Lifecycle

```
current → superseded   (clear update: newer fact wins)
current → contested    (LLM uncertain, or explicit challenge)
contested → current    (resolved: this one is correct)
contested → superseded (resolved: the other one is correct)
any → historical       (drawer deleted — ghost record for audit)
```

### Contradiction Detection: Two-Stage Architecture

**Stage 1 — Fast Judge (always runs)**
- New drawer → find top-k similar drawers via hybrid search
- Single LLM prompt: compare new vs. existing, classify conflict type, return confidence
- Conflict types: `direct_contradiction`, `temporal_update`, `partial_overlap`, `none`
- If confidence ≥ 0.8 → auto-resolve (mark loser as `superseded`)
- If confidence < 0.8 → escalate to Stage 2

**Stage 2 — Context-Enriched Resolve (ambiguous cases only)**
- Pull 3 additional palace context snippets for each conflicting drawer
- Second LLM pass with enriched context
- Resolves or marks both as `contested` if still ambiguous

**Implementation details:**
- Runs in daemon threads — save call returns immediately, detection happens in background
- LLM backend is pluggable — Ollama, LM Studio, vLLM, or any OpenAI-compatible endpoint (configured via `mempalace llm setup`, no hardcoded URLs)
- Stage 1 prompt budget: 512 tokens; Stage 2: 768 tokens
- Detection is throttled: 2-minute global cooldown, 5s inter-request sleep, `nice -n 19` / `ionice -c 3` to stay anecdotal on system load
- Disable entirely with `mempalace llm setup → None` for zero-overhead saves

### Trust-Aware Search

`hybrid_searcher.py` is trust-aware at fetch time:
- `superseded` and `historical` drawers are excluded by default
- Confidence weights the RRF score: `weighted_score = rrf_score × confidence`
- `contested` drawers surface with a `⚠` warning field
- `include_superseded=True` opt-in for archaeology / debugging

### Storage

Trust tables live in the same SQLite file as the knowledge graph (`knowledge_graph.sqlite3`):

```sql
drawer_trust        -- status, confidence, valid_from/to, superseded_by, verifications, challenges
drawer_conflicts    -- pairwise conflict records (pending/resolved)
drawer_trust_history -- append-only audit trail of every state change
```

### New MCP Tools (v3.1)

| Tool | Purpose |
|------|---------|
| `mempalace_trust_stats` | Trust layer overview — counts by status, avg confidence, pending conflicts |
| `mempalace_verify` | Confirm a drawer is accurate (+0.05 confidence) |
| `mempalace_challenge` | Flag a drawer as suspect (−0.1 confidence, marks contested) |
| `mempalace_get_contested` | List unresolved contested memories for review |
| `mempalace_resolve_contest` | Manually pick the winner of a conflict |

---

## Contribution 3: Direct Auto-Save Hook (v3.1)

### Problem

The original save hook works by nudging the AI at intervals, asking it to save to the palace. This has two failure modes:
1. The AI may not cooperate (ignores the instruction, or the block gets swallowed)
2. The AI interrupts the conversation, which creates friction

### Solution

A Python hook (`hooks/mempal_save_hook.py`) that:
1. Runs on every `Stop` event (after each assistant response)
2. Reads the transcript directly
3. Extracts memories using `general_extractor.py` (pattern-based, no LLM)
4. Saves directly to ChromaDB
5. Triggers a git sync in the background
6. Always outputs `{}` — **never blocks the AI**

Result: fully automatic, zero-interruption, AI-independent memory extraction.

The pattern-based extractor covers: decisions, preferences, milestones, problems, emotional notes. For richer LLM-powered extraction from historical logs, use `llm_miner.py`.

---

## Contribution 4: LLM History Mining (`llm_miner.py`)

A standalone script that processes all historical AI conversation logs (Claude JSONL, Gemini JSON, Codex session files) through a local LLM (vLLM/Ollama) to extract structured memories and file them into the palace.

Used to bootstrap a palace from months of prior conversation history. Not a real-time tool — run once, or periodically on new log dumps.

Output: `distilled` wing, rooms: `decision | preference | project_fact | tech_fact | milestone | personal`.
