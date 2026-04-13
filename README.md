<div align="center">

<img src="assets/mnemion_logo.png" alt="Mnemion" width="280">

# Mnemion

### Persistent AI Memory · Hybrid Retrieval · Trust Lifecycle · Behavioral Protocol

<br>

**Mnemion** is a production-grade AI memory system built by **PerseusXR**. Give any AI a persistent, searchable memory Anaktoron — hybrid lexical-semantic retrieval, a human-like trust lifecycle, background contradiction detection, intelligent LLM lifecycle management, and a behavioral protocol so your AI actually knows to use its memory.

Inspired by the original [mempalace](https://github.com/milla-jovovich/mempalace) project. Built far beyond it.

<br>

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]

<br>

[Architecture](#architecture-layers) · [Quick Start](#quick-start) · [MCP Tools](#mcp-tools) · [System Prompt](#behavioral-protocol-bootstrap-system_promptmd--mcp-prompts) · [Auto-Save Hooks](#auto-save-hooks) · [Librarian](#6-librarian--daily-background-tidy-up-librarianpy) · [Anaktoron Sync](#anaktoron-sync) · [Benchmarks](#benchmarks) · [Changelog](#changelog)

</div>

---

## Architecture Layers

### 1. Hybrid Lexical-Semantic Retrieval (`hybrid_searcher.py`)

Vector search alone has a "Vector Blur" problem: exact technical identifiers (git hashes, function signatures, hex addresses) carry low semantic weight and get outranked by thematically related but wrong results.

Mnemion runs a **SQLite FTS5 lexical mirror** alongside ChromaDB, fusing both result sets using **Reciprocal Rank Fusion (RRF)**. Benchmarked result:

| Metric | Vector Only | Hybrid RRF | Improvement |
|--------|-------------|------------|-------------|
| Mean Reciprocal Rank (MRR) | 0.5395 | 0.8833 | **+63.7%** |
| Hit@1 Accuracy | 46.7% | 80.0% | **+33.3%** |

*4,344-drawer production Anaktoron, 15-target Gold Standard. Reproduce: `python eval/benchmark.py`*

### 2. Memory Trust Layer (`drawer_trust.py` + `contradiction_detector.py`)

Human memory has a lifecycle — beliefs get superseded, contradicted, verified. Without this, an AI memory system accumulates conflicting facts indefinitely.

Every drawer now has a **trust record**:

```
current → superseded   (newer fact wins — old one is kept but excluded from search)
current → contested    (conflict detected — surfaces with ⚠ warning in search)
contested → resolved   (AI or user picks the winner)
any → historical       (drawer deleted — ghost record remains for audit)
```

**Contradiction detection runs in the background** when a new drawer is saved:

- **Stage 1**: Fast LLM judge — compares new drawer against top-k similar existing drawers. Auto-resolves if confidence ≥ 0.8.
- **Stage 2**: For ambiguous cases — pulls additional Anaktoron context, second LLM pass to resolve.

Save speed: unchanged (detection is async, daemon threads). Fetch speed: improved (superseded memories excluded by default, confidence weights scores).

Works with any local LLM — configure once with `mnemion llm setup` (Ollama, LM Studio, vLLM, or any OpenAI-compatible endpoint). No cloud calls, no API key. Disable entirely for zero-overhead saves.

### 3. Intelligent LLM Lifecycle (`llm_backend.py` — `ManagedBackend`)

Running a local LLM (vLLM, Ollama, etc.) for contradiction detection shouldn't require manual startup. `ManagedBackend` wraps any OpenAI-compatible server with full lifecycle management:

- **Auto-start on demand** — when contradiction detection fires and the server is down, it starts automatically (WSL or native Linux)
- **Auto-stop on idle** — after configurable idle timeout (default: 5 minutes), the server shuts down to free GPU memory
- **Auto-restart on failure** — 3 consecutive chat failures trigger a stop + relaunch + wait cycle
- **Manual control** — `mnemion llm start` / `mnemion llm stop` for explicit lifecycle management

Configure during setup:
```bash
mnemion llm setup
# → prompts for start_script (e.g. wsl:///home/user/run_vllm.sh), idle_timeout
```

### 4. Behavioral Protocol Bootstrap (`SYSTEM_PROMPT.md` + MCP prompts)

The hardest problem with AI memory isn't storage — it's ensuring the AI *knows to use it*. Without explicit instructions, an AI connected to mnemion will ignore it entirely.

This fork solves it with three layers:

| Layer | Mechanism | Covers |
|-------|-----------|--------|
| **MCP tool descriptions** | `mnemion_status` description says "CALL THIS FIRST" | All MCP clients |
| **MCP prompts capability** | `prompts/get?name=mnemion_protocol` returns the full behavioral rules | Clients supporting MCP prompts |
| **`SYSTEM_PROMPT.md`** | Copy-paste template for every major AI platform | Claude Code, Cursor, ChatGPT, Gemini |

The result: any AI connecting to this MCP server receives clear instructions on *when* (startup, before answering, when learning, at session end), *which tool* to call, and *why*.

### 5. AI-Independent Auto-Save Hook (`hooks/mnemion_save_hook.py`)

The original hook asks the AI to save memories at intervals — which means it depends on the AI cooperating. We replaced it with a Python hook that:

- Reads the transcript directly
- Extracts memories via `general_extractor.py` (pure patterns, no LLM)
- Saves to ChromaDB with hash-based dedup
- Triggers a git sync in the background
- **Always outputs `{}` — never blocks the AI, never interrupts the conversation**

Covers: decisions, preferences, milestones, problems, emotional notes.

### 6. Librarian — Daily Background Tidy-Up (`librarian.py`)

Even with contradiction detection running per-save, a Anaktoron accumulates noise over time: misclassified rooms, redundant drawers, entity facts buried in prose but never extracted into the knowledge graph. The Librarian runs as a daily background job that reviews every drawer that has never been verified or challenged.

For each drawer it performs three tasks using the configured local LLM:

| Task | What it does |
|------|-------------|
| **Contradiction scan** | Checks the drawer against similar Anaktoron content for conflicts; flags contested if found |
| **Room re-classification** | Suggests a better wing/room if the current taxonomy is wrong; moves silently |
| **KG triple extraction** | Pulls structured facts (subject → predicate → object) from the drawer's text and adds them to the knowledge graph |

The Librarian is cursor-based — it saves its position to `~/.mnemion/librarian_state.json` and resumes where it left off. It processes one drawer at a time with an 8-second inter-request sleep to stay polite to the local GPU. At 3 AM via Windows Task Scheduler (or cron) it's invisible during working hours.

```bash
# Run manually
mnemion librarian

# Dry-run — shows what would change without writing
mnemion librarian --dry-run

# Schedule daily 3 AM run (Windows)
powershell -ExecutionPolicy Bypass -File scripts/setup_librarian_scheduler.ps1
```

Requires the LLM backend to be configured (`mnemion llm setup`). Without it, the Librarian skips LLM tasks and only runs room re-classification using the local rule-based detector.

### 7. Anaktoron Sync (`sync/SyncMemories.ps1`)

The ChromaDB Anaktoron is ~860MB — too large for git. The sync system:

1. Exports all drawer content to `archive/drawers_export.json` (~24MB)
2. Commits and pushes the JSON to your private memory repo
3. Runs automatically via Task Scheduler (Windows) or cron (macOS/Linux)

On a new machine: `git clone <repo>` → `mnemion restore archive/drawers_export.json` → full Anaktoron restored.

### 8. LeWorldModel (LeWM) Upgrade — Self-Organizing Intelligence

Based on LeWorldModel (Maes et al., 2026), Mnemion uses SIGReg to prevent embedding collapse and an LSTM-based predictor for proactive context retrieval.

| Feature | What it does | Verified Impact |
|---------|--------------|------------------|
| **Latent Grooming (SIGReg)** | Uses the Epps-Pulley test statistic to spread embeddings across the latent manifold, preventing cluster collapse. | **+40% Recall@5** (0.600→1.000 in A/B benchmark) |
| **Predictive Context (JEPA)** | LSTM-based predictor tracks session latent trajectories. Use `mnemion_predict_next` to anticipate the next information need. | Proactive pre-fetch |
| **Latent Health Suite** | Diagnostic tools (`benchmarks/latent_health.py`) to measure Anaktoron density and Gaussian normality. | Monitoring |

*A/B benchmark: 2,000-drawer Anaktoron, 20 planted needles. Raw ChromaDB R@5=0.600, SIGReg groomed R@5=1.000. Reproduce: `python tests/benchmarks/bench_ab_test.py`*

Enable grooming in `~/.mnemion/config.json`:
```json
"lewm": {
  "groom_iterations": 10,
  "sigreg_weight": 0.1
}
```

---

## Quick Start

### Windows (one-shot installer)

```powershell
git clone https://github.com/Perseusxrltd/mnemion
cd mnemion
pip install .

# Sets up hooks, Task Scheduler sync, vLLM auto-start, backfills trust records
powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1
```

Then add the MCP server:
```bash
claude mcp add mnemion -- python -m mnemion.mcp_server
```

Then copy the behavioral protocol into your AI's system instructions so it knows to use its memory:
```bash
# For Claude Code — copy into your global CLAUDE.md:
cat SYSTEM_PROMPT.md
# See SYSTEM_PROMPT.md for Cursor, Claude.ai Projects, ChatGPT, Gemini templates
```

Restart Claude Code. The AI will automatically call `mnemion_status` on startup, load the AAAK dialect, and follow the memory protocol.

### Manual / macOS / Linux

```bash
pip install .

# Mine a project or conversation history
mnemion init ~/projects/myapp
mnemion mine ~/projects/myapp

# Add MCP server
claude mcp add mnemion -- python -m mnemion.mcp_server

# Install the auto-save hook (add to .claude/settings.local.json)
# See hooks/README.md for full instructions

# Backfill trust records for existing drawers
py sync/backfill_trust.py
```

### LLM backend (contradiction detection — optional)

Contradiction detection works with any local LLM. Configure it interactively:

```bash
mnemion llm setup
```

```
  1. None (disabled)    — no conflict detection, saves instantly
  2. Ollama             — local, easy: ollama pull gemma2
  3. LM Studio          — local GUI with model browser
  4. vLLM               — local, fast, needs GPU (WSL/Linux)
  5. Custom             — any OpenAI-compatible endpoint
```

Check and test at any time:
```bash
mnemion llm status   # show config + ping
mnemion llm test     # send a test prompt
```

**vLLM on WSL** (for GPU users — auto-start recommended):
```bash
cp sync/run_vllm.sh ~/run_vllm.sh
# mnemion llm setup → choose vllm → http://localhost:8000
# → enter start_script: wsl:///home/user/run_vllm.sh
# → mnemion will auto-start/stop the server as needed
```

With `start_script` configured, mnemion starts vLLM on demand (when contradiction detection fires) and stops it after the idle timeout. No manual management needed. You can also control it explicitly:
```bash
mnemion llm start   # boot the server now
mnemion llm stop    # shut it down
```

---

## MCP Tools

The MCP server exposes 25 tools across five categories.

### Read

| Tool | What it does |
|------|-------------|
| `mnemion_status` | Anaktoron overview — drawer counts, wing breakdown, AAAK spec |
| `mnemion_list_wings` | All wings with drawer counts |
| `mnemion_list_rooms` | Rooms within a wing |
| `mnemion_get_taxonomy` | Full wing → room → count tree |
| `mnemion_get_aaak_spec` | Get the AAAK compressed memory dialect spec |
| `mnemion_search` | Hybrid search (vector + lexical RRF). Filters out superseded memories. Flags contested with ⚠. Optional `min_similarity` threshold. |
| `mnemion_check_duplicate` | Check if content already exists before filing |

### Write

| Tool | What it does |
|------|-------------|
| `mnemion_add_drawer` | File content into a wing/room. Creates trust record + spawns background contradiction detection |
| `mnemion_delete_drawer` | Soft-delete a drawer (trust record marked `historical`, never hard-removed) |

### Knowledge Graph

| Tool | What it does |
|------|-------------|
| `mnemion_kg_query` | Query entity relationships with optional temporal filter |
| `mnemion_kg_add` | Add a typed fact (subject → predicate → object, with valid_from) |
| `mnemion_kg_invalidate` | Mark a fact as no longer true |
| `mnemion_kg_timeline` | Chronological fact history for an entity |
| `mnemion_kg_stats` | Knowledge graph overview |
| `mnemion_traverse` | Walk the Anaktoron graph from a room — find connected ideas |
| `mnemion_find_tunnels` | Rooms that bridge two wings |
| `mnemion_graph_stats` | Graph topology overview |

### Trust

| Tool | What it does |
|------|-------------|
| `mnemion_trust_stats` | Trust layer overview — counts by status, avg confidence, pending conflicts |
| `mnemion_verify` | Confirm a drawer is accurate (+0.05 confidence) |
| `mnemion_challenge` | Flag a drawer as suspect (−0.1 confidence, marks contested) |
| `mnemion_get_contested` | List unresolved contested memories for review |
| `mnemion_resolve_contest` | Manually pick the winner of a conflict |

### LeWM

| Tool | What it does |
|------|--------------|
| `mnemion_predict_next` | Predict the user's next information need based on session latent trajectory (LSTM predictor) |

### Agent Diary

| Tool | What it does |
|------|-------------|
| `mnemion_diary_write` | Write a diary entry in AAAK format — agent's personal journal |
| `mnemion_diary_read` | Read recent diary entries |

---

## Auto-Save Hooks

Two hooks are included. Use the Python hook for always-on extraction; combine with the shell PreCompact hook for deep saves before context compaction.

**Python hook (recommended — never blocks):**
```json
{
  "hooks": {
    "Stop": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 /path/to/hooks/mnemion_save_hook.py",
        "timeout": 15
      }]
    }]
  }
}
```

See [hooks/README.md](hooks/README.md) for full installation, Codex CLI setup, and configuration options.

---

## Anaktoron Sync

Automatic hourly backup to a private git repo. Works across machines.

**Setup (Windows):**
```powershell
# Copy sync script
Copy-Item sync/SyncMemories.ps1 $env:USERPROFILE\.mnemion\

# Schedule hourly sync
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -File $env:USERPROFILE\.mnemion\SyncMemories.ps1"
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At (Get-Date)
Register-ScheduledTask -TaskName "MnemionMemorySync" -Action $action -Trigger $trigger -RunLevel Highest -Force
```

**Restore on new machine:**
```bash
git clone https://github.com/YOUR_USERNAME/personal-ai-memories ~/.mnemion
cd ~/.mnemion
py -m mnemion restore archive/drawers_export.json
py ~/.mnemion/backfill_trust.py
```

> **Large archives (>10k drawers):** restore computes embeddings for every drawer. If the process is killed (OOM), reduce the batch size: `mnemion restore archive/drawers_export.json --batch-size 20`

See [sync/README.md](sync/README.md) for full details including macOS/Linux cron setup.

---

## Architecture

```
User → CLI → miner/convo_miner ─────────────────┐
                                                  ↓
                                        ChromaDB Anaktoron (vectors)
                                        FTS5 mirror (lexical)
                                        drawer_trust (status/confidence)
                                                  ↕
Auto-save hook → general_extractor ──────────────┘
                                         ↑ trust.create()
                                         ↑ contradiction_detector (background thread)
                                                  ↕
MCP Server → hybrid_searcher → trust-filtered, confidence-weighted results
           → kg tools        → entity facts, temporal queries
           → trust tools     → verify / challenge / resolve
           → diary           → agent journal
                                                  ↕
Task Scheduler → SyncMemories.ps1 → archive/drawers_export.json → git push
```

**Storage layout:**
```
~/.mnemion/
├── anaktoron/                ← ChromaDB (vectors, ~860MB, git-ignored)
├── knowledge_graph.sqlite3   ← KG triples + FTS5 + trust tables (git-ignored)
├── archive/
│   └── drawers_export.json   ← portable JSON export (~24MB, committed to git)
├── hooks/
│   └── mnemion_save_hook.py   ← Python auto-save hook
└── SyncMemories.ps1          ← hourly sync script
```

---

## Benchmarks

Benchmarks and a full reproduction suite are in `/benchmarks` and `/eval`.

```bash
# Reproduce the RRF benchmark
python eval/benchmark.py

# Full LongMemEval benchmark (500 questions)
python benchmarks/longmemeval_bench.py /path/to/longmemeval_s_cleaned.json
```

The upstream project's **96.6% R@5 on LongMemEval** (raw mode) is real and independently reproduced. AAAK mode trades ~12 points of recall for token density — use raw mode for maximum accuracy.

---

## Origins

Mnemion began as a fork of [milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace), which introduced the memory Anaktoron metaphor and the AAAK dialect. The hybrid retrieval engine, trust lifecycle, contradiction detection, intelligent LLM lifecycle, knowledge graph, and behavioral protocol bootstrap were all built from scratch by PerseusXR. The name changed when what we built stopped resembling where we started.

---

## Changelog

### v3.3.5 — Restore: streaming JSON, O(batch) peak memory

The previous restore called `json.load()` on the full export before processing. For a 58 MB / 33k-drawer archive this materialises as ~500 MB–1 GB of Python objects, which — on top of ChromaDB's sentence-transformer (~90 MB) — triggers OOM/SIGKILL before even 3% of the archive is written.

- **`_stream_json_array()`**: yields one drawer at a time using `JSONDecoder.raw_decode()` with a 512 KB rolling file buffer. Peak memory is now `O(batch_size)` regardless of archive size.
- **`_count_json_objects()`**: fast byte scan (`b'"id":'`) counts drawers in ~20 ms without any JSON parsing, so `%` progress still works.
- The full export never exists as a Python list during restore.

### v3.3.2 — Restore: OOM fix, progress output, --batch-size

- **Restore batch size reduced from 500 → 50** (default). ChromaDB embeds every document on write; large batches on big archives (33k+ drawers, 22k chars average) caused SIGKILL from OOM on memory-constrained hosts.
- **`--batch-size` flag**: operators can tune further — `mnemion restore archive/drawers_export.json --batch-size 20` for very tight environments.
- **Memory freed per batch**: processed entries are cleared from the in-memory list and `gc.collect()` is called after every ChromaDB write, so peak memory is bounded to one batch at a time instead of the full export.
- **All output flushed**: `flush=True` on every `print()` so progress is visible before any OOM event.
- **Progress shows `%` + file size**: agents can now see `[35%] 11700/33433 ...` and know it's still running.

### v3.3.0 — `restore` command + collection name resolution

- **`mnemion restore <file.json>`** — new command for importing a JSON export into a fresh Anaktoron. The previous `mnemion mine archive/drawers_export.json` path in the README was broken (`mine` expects a directory). Supports `--merge` and `--replace` flags.
- **Collection name resolved from config in all commands**: `searcher.py`, `layers.py`, `miner.py`, `convo_miner.py`, and `cli.py` (repair/compress) previously hardcoded `"mnemion_drawers"`, ignoring `collection_name` in `config.json`. Fixed across all read/write paths.

### v3.2.7 — Behavioral Protocol Bootstrap + MCP Prompts

The "how does the AI know to use it" problem, solved at every layer:

- **MCP `prompts` capability**: server now advertises `prompts: {}` in `initialize` and handles `prompts/list` + `prompts/get`. Requesting `mnemion_protocol` returns the full behavioral protocol + AAAK spec as an injectable message. Clients that support MCP prompts receive the protocol automatically.
- **Directive tool descriptions**: `mnemion_status` now reads "CALL THIS FIRST at every session start" — any AI reading the tools list is immediately instructed. Key tools (`search`, `add_drawer`, `kg_query`, `diary_write`) now say *when* to use them, not just *what* they do.
- **`SYSTEM_PROMPT.md`**: copy-paste template for all major AI platforms — Claude Code `CLAUDE.md`, Cursor `.cursorrules`, Claude.ai Projects, ChatGPT Custom Instructions, Gemini, OpenAI-compatible APIs.
- **`~/.claude/CLAUDE.md` support**: Claude Code reads this file at every session start, before any tool is available — the most reliable bootstrap for Claude Code users.

### v3.2.23 — Multi-Agent Anaktoron Sync

- **`sync/merge_exports.py`** (new): pure-Python merge utility that produces a clean union of two `drawers_export.json` files — local and remote — without git merge markers. Deduplicates by drawer ID; when the same ID exists in both, the one with the newer `filed_at` timestamp wins (remote wins on tie).
- **`sync/SyncMemories.ps1`** (rewritten): now fetches before pushing, merges remote export if remote is ahead, uses `git push --force-with-lease`, and retries up to 5 times with random 2–9 s jitter on rejection. Lock file prevents concurrent runs on the same machine (stale locks > 10 min auto-cleared). Agent ID (`MNEMION_AGENT_ID` env, default: hostname) is stamped in every commit message.
- **`sync/SyncMemories.sh`** (new): same algorithm for Linux/macOS agents (bash implementation).
- **`sync/README.md`** (rewritten): documents multi-agent design, environment variables, merge algorithm, `.gitignore` requirements, and known v1 limitation (drawer deletions don't propagate across agents).

### v3.2.22 — Entity Detection Quality, Search Ranking, Makefile

- **Entity detector — stopword expansion** (`entity_detector.py`): ~120 additional generic words added to `STOPWORDS` covering status adjectives (`current`, `verified`, `pending`, `active`…), common tech/business nouns (`stage`, `trust`, `hybrid`, `call`, `notes`, `auto`…), and adjective-nouns that appear capitalised in project docs (`lexical`, `semantic`, `abstract`…). Directly addresses reported false positives.
- **Entity detector — frequency threshold**: minimum occurrence count raised 3 → 5; words that appear fewer than 5 times no longer become candidates, reducing sentence-start capitalisation noise.
- **Entity detector — uncertain list filter**: zero-signal uncertain entries (frequency-only, confidence < 0.3) are now filtered out before presentation. The uncertain cap is also tightened from 8 → 6.
- **Search ranking — keyword FTS fallback** (`hybrid_searcher.py`): `_fts_search` previously ran only a strict phrase-match (whole query in double-quotes). For conversational or multi-word queries the phrase never matched anything, leaving ranking entirely to vector search and pulling broad overview docs ahead of specific operational ones. Now runs a second tokenised keyword pass (stop-words stripped, AND-of-terms) and merges candidates before RRF fusion. Phrase results retain positional priority.
- **Makefile**: new top-level `Makefile` with `install`, `test`, `test-fast`, `lint`, `format`, and `clean` targets. All test targets invoke `$(VENV_PY) -m pytest` so pytest always runs in the project venv — fixes the `ConftestImportFailure: No module named 'chromadb'` error caused by using a system-level `pytest` binary.

### v3.2.20 / v3.2.21 — Version bump only

Automated version bumps. No code changes.

### v3.2.19 — Upstream Cherry-Picks: BLOB Compat, KG Thread Safety, Security Hardening

- **ChromaDB BLOB migration** (`chroma_compat.py`): upgrading from chromadb 0.6.x to 1.5.x left BLOB-typed `seq_id` fields that crash the Rust compactor on startup. New `fix_blob_seq_ids()` patches the existing `chroma.sqlite3` in-place before `PersistentClient()` is called. Called from `miner.py`, `hybrid_searcher.py`, and `mcp_server.py`. No-op on clean installs.
- **Knowledge graph thread safety**: `add_entity`, `add_triple`, and `invalidate` are now protected by a `threading.Lock`. Prevents data races when the Librarian daemon and the main thread write to the KG concurrently.
- **MCP argument whitelisting**: undeclared keys are stripped from tool args before dispatch — prevents audit-trail spoofing by injected `wait_for_previous` or other rogue parameters.
- **Parameter clamping**: `limit` (≤50), `max_hops` (≤10), `last_n` (≤100) are clamped before queries to prevent resource abuse.
- **Epsilon mtime comparison** (`miner.py`): float equality `==` for file mtimes could miss identical values due to float representation; replaced with `abs(a - b) < 0.001`.
- **`--source` tilde expansion** (`cli.py`): `~/...` and relative paths now correctly resolved via `expanduser().resolve()`.

### v3.2.18 — Headless / CI Safety

- `mnemion init` no longer raises `EOFError` when stdin is not a terminal (CI pipelines, agent harnesses, pipes). `entity_detector.py` and `room_detector_local.py` now check `sys.stdin.isatty()` and auto-accept in non-interactive environments.
- `__main__.py` now reconfigures `stdout`/`stderr` to UTF-8 at startup on Windows, preventing `UnicodeEncodeError` from Unicode characters in Anaktoron output.

### v3.2.17 — Bug Audit: Trust NullRef + FTS5 Escaping + BLOB Crash

- **`contradiction_detector.py`**: `trust.get(candidate_id)["confidence"]` crashed with `TypeError: 'NoneType' is not subscriptable` for drawers with no trust record. Fixed to `(trust.get(candidate_id) or {}).get("confidence", 1.0)`.
- **`hybrid_searcher.py`**: FTS5 phrase queries now escape embedded `"` characters (doubled) — prevents `sqlite3.OperationalError` on queries containing quotes. `sqlite3.connect()` timeout set to 10s in `_fts_search` and `_get_trust_map`.
- **`mcp_server.py`**: None checks on trust records in `tool_verify_drawer`, `tool_challenge_drawer`, `tool_resolve_contest` — changed `if not rec:` to `if rec is None:` to correctly handle zero-confidence records. Error handling upgraded to `logger.exception()` in 5 places for full stack traces in logs.

### v3.2.15 — Librarian: Daily Background Anaktoron Tidy-Up

New `mnemion librarian` command — a cursor-based background agent that tidy-ups the Anaktoron nightly using the configured local LLM:

- **Contradiction scan** on unreviewed drawers (verifications=0, challenges=0)
- **Room re-classification** — moves misclassified drawers to the correct wing/room silently
- **KG triple extraction** — pulls structured facts from drawer text and writes them to the knowledge graph
- 8-second inter-request sleep; resumes from cursor on next run
- `--dry-run` flag to preview changes without writing
- `scripts/setup_librarian_scheduler.ps1` registers a daily 3 AM Windows Task Scheduler job

### v3.2.9 — Project Renamed: mnemion → Mnemion

- Package, CLI command, MCP server name, and all internal references renamed from `mnemion` to `mnemion`
- Auto-migration: on first startup, existing `~/.mempalace/` config is detected and migrated to `~/.mnemion/` with confirmation prompt
- `startup_timeout` default raised from 90s → 300s to handle cold GPU start
- WSL `start_script` now strips CRLF from the script path before execution

### v3.2.5 — Intelligent LLM Lifecycle (`ManagedBackend`)

Local LLM management should be transparent — configure once, never think about it again:

- `ManagedBackend` wraps any OpenAI-compatible server: auto-start on demand, auto-stop after idle timeout, auto-restart on 3 consecutive failures
- WSL support: `start_script: wsl:///home/user/run_vllm.sh` spawns a Windows-detached process that survives shell exit
- `mnemion llm start` / `mnemion llm stop` for explicit control
- Contradiction detector auto-starts the backend if it's down when detection fires
- `save_llm_config()` extended with `start_script`, `startup_timeout`, `idle_timeout` parameters

### v3.2.0 — Community Fixes

Eight upstream bugs fixed, sourced from the milla-jovovich/mnemion community:

| Fix | Impact |
|-----|--------|
| Widen chromadb to `<2.0` | Python 3.14 compatibility |
| Add `hnsw:space=cosine` on all collection creates | Similarity scores were negative L2 values, not cosine. All new Anaktorons fixed automatically. Existing Anaktorons benefit after `mnemion repair`. |
| Guard `results["documents"][0]` on empty queries | ChromaDB 1.x returns `{documents:[]}` on empty results; was crashing with `IndexError` |
| Redirect `sys.stdout → sys.stderr` at MCP import | chromadb/posthog startup chatter was corrupting the JSON-RPC wire, causing `Unexpected token` errors in clients |
| Paginate taxonomy/list tools | Anaktorons with >10k drawers were silently truncated at 10k; now pages through all drawers |
| Drop `wait_for_previous` arg | Gemini MCP clients inject this undocumented arg; was crashing with `TypeError` |
| `min_similarity` on `mnemion_search` | Results below threshold are omitted — gives agents a clean "nothing found" signal instead of returning negative-score noise |
| `CODE_KEYWORDS` blocklist in entity detector | Rust types, React, framework names (String, Vec, Debug, React...) were being detected as entities during `mnemion init` |

### v3.1.0 — Trust Layer + LLM Backend

- Memory trust lifecycle: `current → superseded | contested → historical`
- Two-stage background contradiction detection (Stage 1: fast LLM judge; Stage 2: Anaktoron-context enriched)
- Pluggable LLM backend: Ollama, LM Studio, vLLM, custom OpenAI-compatible, or none — configure with `mnemion llm setup`
- Resource-throttled detection: `nice -n 19`, `ionice -c 3`, 2-minute global cooldown, 5s inter-request sleep
- One-shot Windows installer (`sync/install_windows.ps1`) — sets up hooks, Task Scheduler, optional vLLM auto-start
- 5 new trust MCP tools: `trust_stats`, `verify`, `challenge`, `get_contested`, `resolve_contest`

---

## License

MIT — see [LICENSE](LICENSE).

<!-- Link Definitions -->
[version-shield]: https://img.shields.io/badge/version-3.3.4-4dc9f6?style=flat-square&labelColor=0a0e14
[release-link]: https://github.com/Perseusxrltd/mnemion/releases
[python-shield]: https://img.shields.io/badge/python-3.9--3.14-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8
[python-link]: https://www.python.org/
[license-shield]: https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14
[license-link]: https://github.com/Perseusxrltd/mnemion/blob/main/LICENSE
