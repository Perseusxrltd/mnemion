---
title: "Mnemion"
category: "Tool"
status: "active"
version: "3.5.5"
summary: "Frontier AI memory. Hybrid retrieval (MRR 0.54→0.88), Trust Lifecycle, SIGReg Latent Grooming (+40% Recall@5), and JEPA Predictive Context."
description: "Mnemion is a production-grade AI memory system by PerseusXR. Named after Mnemosyne — Greek goddess of memory, mother of the Muses. Featuring Hybrid lexical-semantic retrieval, a human-like Trust Lifecycle, and SIGReg (Sketched Isotropic Gaussian Regularization) latent grooming that prevents embedding collapse and delivers a verified +40% Recall@5 improvement over raw vector search. An LSTM-based JEPA-style predictor enables session-aware proactive retrieval. No API key required."
tags: ["AI", "Memory", "RAG", "Hybrid-Search", "MCP", "LeWorldModel", "JEPA", "SIGReg", "ChromaDB", "SQLite", "Plugins", "Entity-Registry", "AAAK-Dialect", "Claude-Code", "Codex", "PyTorch"]
source_url: "https://github.com/Perseusxrltd/mnemion"
demo_url: "https://www.molthub.info/artifacts/mnemion"
collaboration_open: true
skills_needed: ["Python", "SQLite", "ChromaDB", "Information Retrieval", "MCP", "PyTorch"]
help_wanted: "GraphRAG contextual expansion, CRDT-based cross-device sync, cross-encoder reranking, LeWM online fine-tuning pipeline."
latest_milestone: "v3.5.5 — Live follow-up safety for memory guard review, consolidation batching, and librarian dry-run (May 2026)"
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

### Memory Trust Layer (`trust_lifecycle.py`)
- Every drawer has a trust record: `current → superseded | contested → historical`
- Background contradiction detection: Stage 1 fast LLM judge, Stage 2 Anaktoron-context enriched
- 5 trust MCP tools: verify, challenge, get_contested, resolve_contest, trust_stats

### Hybrid Retrieval (hybrid_searcher.py)
- ChromaDB (semantic) + SQLite FTS5 (lexical) fused with Reciprocal Rank Fusion
- Solves "Vector Blur": exact identifiers (git hashes, function signatures) now retrieved reliably

### Palace → Anaktoron Rename (v3.4.x)
- Storage path: `~/.mempalace/palace` → `~/.mnemion/anaktoron`
- Config class: `MempalaceConfig` → `MnemionConfig`
- MCP server arg: `--palace` → `--anaktoron`
- Legacy keys (`palace_path`, `MNEMION_PALACE_PATH`) still accepted for backward compat

### Personal Entity Registry (`entity_registry.py`)
- Persistent registry at `~/.mnemion/entity_registry.json`. Three sources (priority order): onboarding > learned > wiki.
- **Wikipedia disambiguation**: looks up unknown capitalized words via Wikipedia REST API — detects person/place/concept, caches results, flags words that are also common English (e.g. "Grace", "Max", "May").
- **Context-pattern disambiguation**: 14 person-context vs. 9 concept-context patterns disambiguate "Riley said" (person) from "if you ever" (adverb).
- `learn_from_text()`: discovers new entity candidates from session text at configurable confidence threshold.

### Interactive Onboarding (`onboarding.py`)
- Guided first-run setup: mode (work/personal/combo), people + nicknames, projects, wings.
- Auto-detects additional names from project files; warns about ambiguous names.
- Generates `~/.mnemion/aaak_entities.md` + `~/.mnemion/critical_facts.md` so the AI knows the user's world from session one.

### Multi-format Chat Normalizer (`normalize.py`)
- Converts any chat export to Mnemion transcript format (`>` markers). No API key, fully local.
- Supports: Claude Code JSONL, OpenAI Codex CLI JSONL (`event_msg` entries only), Claude.ai JSON (flat + privacy export with nested `chat_messages`), ChatGPT `conversations.json` (mapping tree traversal), Slack JSON (alternating-role assignment), plain text (pass-through).

### AAAK Dialect Compression (`dialect.py`)
- `mnemion compress [--wing W] [--dry-run]` — compresses drawers using AAAK notation (~30x token reduction).
- Stores compressed versions in separate `mnemion_compressed` collection.
- `Dialect.from_config(entities.json)` loads entity codes from onboarding config.

### Spellcheck (`spellcheck.py`)
- Corrects typos in user messages before Anaktoron filing.
- Preserves technical terms (digits, hyphens, underscores), CamelCase, ALL_CAPS, URLs, known entity names.
- Optional dep: `autocorrect`. Integrated into `normalize.py` `_messages_to_transcript()`.

### Hook System (`hooks_cli.py`)
- `mnemion hook run --hook <name> --harness <claude-code|codex>` — unified Python hook dispatcher.
- `session-start`: initializes session tracking. `stop`: blocks every N (default 15) exchanges for auto-save. `precompact`: always blocks with comprehensive save instruction.
- `MNEMION_DIR` env var triggers background `mnemion mine` on stop, synchronous mine on precompact.
- Path-traversal-safe session ID sanitization. Loop prevention via `stop_hook_active` flag.

### Instructions CLI (`instructions_cli.py`)
- `mnemion instructions <name>` — prints markdown skill instructions from `mnemion/instructions/` package.
- Available: `init`, `mine`, `search`, `status`, `help`.

### Claude Code Plugin (`.claude-plugin/`)
- `plugin.json` + `marketplace.json`: registers Mnemion as a Claude Code plugin (v3.5.5).
- Skills: `mnemion/SKILL.md` (unified skill prompt). Commands: `help`, `init`, `mine`, `search`, `status`.
- Hooks: `mnemion-stop-hook.sh` + `mnemion-precompact-hook.sh`.
- MCP server: `python3 -m mnemion.mcp_server`.

### Codex Plugin (`.codex-plugin/`)
- `plugin.json`: registers Mnemion as an OpenAI Codex CLI plugin (v3.5.5).
- Skills: per-skill `SKILL.md` files for `init`, `mine`, `search`, `status`, `help`.
- Hooks: `hooks.json` + `mnemion-hook.sh`. MCP server: `python3 -m mnemion.mcp_server`.
- `.agents/plugins/marketplace.json`: local marketplace manifest pointing at `.codex-plugin/`.

### Studio + Local Runtime Hardening (`studio/`)
- FastAPI backend + React/Vite frontend for visualising the Anaktoron, browsing/searching drawers, exporting vaults, and connecting MCP-capable clients.
- Connect Agents installs Mnemion into Claude Code, Claude Desktop, Cursor, Windsurf, Gemini CLI, Zed, and Codex CLI with timestamped config backups.
- CORS is restricted to expected local dev/Electron origins. Optional `MNEMION_STUDIO_TOKEN` requires `X-Mnemion-Studio-Token` for all mutating `/api` requests.
- Electron packaging has a committed `package-lock.json`, current secure major dependencies (`electron` 41, `electron-builder` 26), and audited build gates.

### Intelligent LLM Lifecycle (`llm_backend.py` — `ManagedBackend`)
- Auto-start on demand (WSL or native), auto-stop after idle timeout, auto-restart on 3 failures.
- `mnemion llm start|stop|status|test|setup`.

### Librarian (`librarian.py`)
- Daily background tidy-up: contradiction scan, room re-classification, KG triple extraction.
- Cursor-based, resumes where it left off. `mnemion librarian [--dry-run] [--status]`.
- Scheduled via `scripts/setup_librarian_scheduler.ps1` (Windows Task Scheduler, 3 AM).

### Multi-Agent Anaktoron Sync (`sync/`)
- `SyncMemories.ps1` / `SyncMemories.sh`: fetch-before-push, merge remote export, `git push --force-with-lease`, 5 retries with random 2–9s jitter, lock file (stale > 10 min auto-cleared).
- `merge_exports.py`: pure-Python merge of two `drawers_export.json` files — deduplicates by ID, newer `filed_at` wins.

## MCP Tools (25 tools across 6 categories)

### Read
`mnemion_status` · `mnemion_list_wings` · `mnemion_list_rooms` · `mnemion_get_taxonomy` · `mnemion_get_aaak_spec` · `mnemion_search` · `mnemion_check_duplicate`

### Write
`mnemion_add_drawer` · `mnemion_delete_drawer`

### Knowledge Graph
`mnemion_kg_query` · `mnemion_kg_add` · `mnemion_kg_invalidate` · `mnemion_kg_timeline` · `mnemion_kg_stats` · `mnemion_traverse` · `mnemion_find_tunnels` · `mnemion_graph_stats`

### Trust
`mnemion_trust_stats` · `mnemion_verify` · `mnemion_challenge` · `mnemion_get_contested` · `mnemion_resolve_contest`

### LeWM
`mnemion_predict_next`

### Agent Diary
`mnemion_diary_write` · `mnemion_diary_read`

## CLI Commands
```
mnemion init <dir>                         Guided onboarding + room detection
mnemion mine <dir> [--mode convos]         Mine project files or chat exports
mnemion search "query"                     Hybrid search
mnemion restore <file.json>                Import JSON export (streaming, OOM-safe)
mnemion compress [--wing W] [--dry-run]    AAAK Dialect compression (~30x)
mnemion wake-up [--wing W]                 L0 + L1 wake-up context
mnemion split <dir>                        Split mega-files into per-session files
mnemion hook run --hook H --harness H      Run hook logic (stop/precompact/session-start)
mnemion instructions <name>               Print skill instructions
mnemion llm setup|status|test|start|stop   LLM backend management
mnemion librarian [--dry-run] [--status]   Background Anaktoron tidy-up
mnemion status                             Show Anaktoron stats
mnemion repair                             Rebuild vector index
```

## Technical Stack
- **Languages:** Python 3.9+
- **Database:** SQLite 3.x (FTS5 + KG triples + trust tables)
- **Vector Store:** ChromaDB (Local Persistent, `~/.mnemion/anaktoron/`)
- **Studio:** FastAPI, React 18, Vite 6, Electron 41
- **Optimization:** PyTorch (SIGReg & JEPA Predictor) — optional dep `mnemion[lewm]`
- **Protocol:** Model Context Protocol (MCP) — 25 tools across 6 categories
- **Reproducibility:** `uv.lock`, frontend `package-lock.json`, Electron `package-lock.json`, Ruff format/check, npm audit gates
- **Optional:** `autocorrect` (spellcheck)

## Agent Operating Protocol
Install the MCP server, then copy `SYSTEM_PROMPT.md` into your AI's system instructions.
The AI will automatically: call `mnemion_status` on startup, search before answering,
use `mnemion_predict_next` for context, and save new facts via `mnemion_add_drawer`.
