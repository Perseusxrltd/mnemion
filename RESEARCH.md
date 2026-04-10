# PerseusXR Research Notes — Mnemion High-Fidelity Distribution

This document records the engineering decisions and empirical findings behind the PerseusXR fork of Mnemion.

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
- LLM backend is pluggable — Ollama, LM Studio, vLLM, or any OpenAI-compatible endpoint (configured via `mnemion llm setup`, no hardcoded URLs)
- Stage 1 prompt budget: 512 tokens; Stage 2: 768 tokens
- Detection is throttled: 2-minute global cooldown, 5s inter-request sleep, `nice -n 19` / `ionice -c 3` to stay anecdotal on system load
- Disable entirely with `mnemion llm setup → None` for zero-overhead saves

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
| `mnemion_trust_stats` | Trust layer overview — counts by status, avg confidence, pending conflicts |
| `mnemion_verify` | Confirm a drawer is accurate (+0.05 confidence) |
| `mnemion_challenge` | Flag a drawer as suspect (−0.1 confidence, marks contested) |
| `mnemion_get_contested` | List unresolved contested memories for review |
| `mnemion_resolve_contest` | Manually pick the winner of a conflict |

---

## Contribution 3: Direct Auto-Save Hook (v3.1)

### Problem

The original save hook works by nudging the AI at intervals, asking it to save to the palace. This has two failure modes:
1. The AI may not cooperate (ignores the instruction, or the block gets swallowed)
2. The AI interrupts the conversation, which creates friction

### Solution

A Python hook (`hooks/mnemion_save_hook.py`) that:
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

---

## Contribution 5: Intelligent LLM Lifecycle — `ManagedBackend` (v3.2)

### Problem

Local LLM servers (vLLM, Ollama) for contradiction detection require manual startup. On Windows + WSL, this is particularly awkward — the server lives in a different OS, and the Python process that spawns it must not own the server's lifetime. If the parent dies, the server should keep running.

### Design

`ManagedBackend` (in `llm_backend.py`) extends `OpenAICompatBackend` with three lifecycle behaviors:

**1. Auto-start on demand**
When `chat()` is called and `ping()` fails, `ensure_running()`:
1. Parses `start_script` from config (`wsl:///path/script.sh` or `/native/path/script.sh`)
2. For WSL scripts: calls `subprocess.Popen(['wsl.exe', '-d', distro, '-e', 'bash', script])` with `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` flags — the server lives at Windows process level, survives shell exit
3. Polls `ping()` up to `startup_timeout` (default: 90s)

**2. Auto-stop on idle**
A daemon watcher thread checks every 30s. If `_last_chat_time` exceeds `idle_timeout` (default: 5 min), calls `stop()` — terminates the subprocess gracefully.

**3. Auto-restart on failure**
`_fail_count` is incremented on each consecutive `chat()` error. At 3 failures, `_restart()` = `stop()` + `_launch()` + `ping()` wait.

### Key design decision: process independence

`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` (Windows) ensures the vLLM server is not a child of the Python process — it's an independent OS-level process. When mnemion exits (or the MCP server restarts), the server keeps running. Only `backend.stop()` or a manual kill terminates it.

This matters for the auto-stop feature: the server is shared state across all processes using the palace.

---

## Contribution 6: Behavioral Protocol Bootstrap (v3.2)

### Problem

Storage is not memory. An AI connected to a Mnemion MCP server has 24 tools available — but without explicit instructions, it will not call them. The behavioral gap between "having tools" and "using tools correctly" is the real problem for AI memory systems.

Specifically: the palace's behavioral protocol (when to call `status`, when to search, when to save, when to write the diary) was only returned *inside* the `tool_status` result — a circular dependency where the AI needed to already know to call the tool before it could receive the instruction to call the tool.

### Solution: three independent layers

Each layer solves the bootstrap independently. A client needs only one to work correctly.

**Layer 1 — MCP tool descriptions (universal)**

Every MCP client reads tool descriptions before taking any action. We changed:
- `mnemion_status` → "CALL THIS FIRST at every session start. Returns your behavioral protocol, AAAK memory dialect spec, and palace overview."
- `mnemion_search` → "Use BEFORE answering any question about past events, people, projects — verify, don't guess."
- `mnemion_add_drawer` → "Call when you learn a new fact or something changes."
- `mnemion_diary_write` → "Call AT END OF EVERY SESSION."
- `mnemion_kg_query` → "Use BEFORE answering questions about specific entities."

**Layer 2 — MCP `prompts` capability**

The MCP protocol supports a `prompts` capability. We register a named prompt `mnemion_protocol` that returns the full behavioral rules + AAAK spec as an injectable message. Clients that support `prompts/get` receive the complete protocol before any tool call.

**Layer 3 — `SYSTEM_PROMPT.md`**

A copy-paste template for every major AI platform:
- Claude Code: `~/.claude/CLAUDE.md` (read at every session start, before tools load)
- Cursor: `.cursorrules` or global rules
- Claude.ai Projects: Project Instructions
- ChatGPT: Custom Instructions
- Gemini: `system_instruction` at chat init

### Why CLAUDE.md is the most reliable layer for Claude Code

Claude Code reads `~/.claude/CLAUDE.md` before any conversation starts — before tools are listed, before MCP servers connect. This means the protocol is injected even in sessions where something goes wrong with the MCP connection. It's the only truly zero-dependency bootstrap path for Claude Code.
