<div align="center">

<img src="assets/mnemion_logo.png" alt="Mnemion" width="280">

# Mnemion

### Persistent AI Memory · Hybrid Retrieval · Trust Lifecycle · Behavioral Protocol

<br>

**Mnemion** is a production-grade AI memory system built by **PerseusXR**. Give any AI a persistent, searchable memory Anaktoron — hybrid lexical-semantic retrieval, a human-like trust lifecycle, background contradiction detection, intelligent LLM lifecycle management, and a behavioral protocol so your AI actually knows to use its memory.

Inspired by the original mempal project. Built far beyond it.

<br>

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]

<br>

[Architecture](#architecture-layers) · [Quick Start](#quick-start) · [Moat](docs/moat.md) · [MCP Tools](#mcp-tools) · [Studio](#studio--connect-agents) · [System Prompt](#behavioral-protocol-bootstrap-system_promptmd--mcp-prompts) · [Auto-Save Hooks](#auto-save-hooks) · [Librarian](#6-librarian--daily-background-tidy-up-librarianpy) · [Anaktoron Sync](#anaktoron-sync) · [Benchmarks](#benchmarks) · [Changelog](#changelog)

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

### 2. Memory Trust Layer (`trust_lifecycle.py` + `contradiction_detector.py`)

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

### 9. Cognitive Reconstruction, Memory Guard, and Moat Evaluation

Mnemion now adds a structured cognitive graph above raw vector drawers. `mnemion consolidate` extracts proposition, causal, preference, objective, event, and prescription units from stored drawers. `mnemion reconstruct` searches those units first, follows recurring topic tunnels, and only then hydrates raw drawers with an evidence trail.

The security path is part of the memory system, not an afterthought: `mnemion memory-guard scan --quarantine` detects obvious instruction-injection and privacy-exfiltration memories, then moves risky drawers into the quarantined trust state so retrieval excludes them until review.

The moat harness is executable:

```bash
mnemion consolidate --limit 1000
mnemion reconstruct "why did the pricing dashboard move to GraphQL?"
mnemion memory-guard scan --quarantine
mnemion eval moat --suite all
```

For the design thesis and operational workflow, see [docs/moat.md](docs/moat.md).

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

**Or use Studio's one-click connector** (Claude Code, Claude Desktop, Cursor, Codex, Gemini CLI, Windsurf, Zed — see [Studio → Connect Agents](#studio--connect-agents)).

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
mnemion mine ~/projects/myapp --consolidate

# Add MCP server
claude mcp add mnemion -- python -m mnemion.mcp_server

# Install the auto-save hook (add to .claude/settings.local.json)
# See hooks/README.md for full instructions

# Backfill trust records for existing drawers
py sync/backfill_trust.py
```

### Retrieval and Ingestion Catch-Up Commands

```bash
# Message-granular Claude/Codex JSONL ingestion with cursor resume
mnemion sweep ~/logs/codex --wing codex --consolidate

# Build or refresh the cognitive graph over recent drawers
mnemion consolidate --limit 1000

# Active reconstruction over cognitive units, topic tunnels, and raw evidence
mnemion reconstruct "what did we decide about retrieval scoring?"

# Scan stored memories for prompt-injection or privacy bait
mnemion memory-guard scan --quarantine

# Run deterministic moat cases for structure, causality, forgetting, and security
mnemion eval moat --suite all

# Repair storage metadata and Chroma max_seq_id issues
mnemion repair --mode status
mnemion repair --mode max-seq-id --dry-run
```

`mnemion sweep` accepts JSONL records shaped like Claude Code/Codex messages:
top-level `role` + `content`, or a nested `message` object with `role` and
`content`. It preserves `session_id`/`sessionId`/`conversation_id`, message
`uuid`/`id`, timestamp, role, and source file metadata. Malformed JSON lines
and records without both role and content are skipped and reported in the
summary; existing deterministic IDs are skipped idempotently.

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

The MCP server exposes 25 tools across six categories.

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
powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1 `
    -MemoryRepoUrl https://github.com/OWNER/PRIVATE-MEMORY-REPO.git `
    -MemoryBranch main `
    -AgentId laptop
```

The memory repo URL, branch, local repo path, task name, sync interval, and agent ID are installer parameters. Omit `-MemoryRepoUrl` if you prefer to add the git remote manually.

**Restore on new machine:**
```bash
git clone https://github.com/OWNER/PRIVATE-MEMORY-REPO.git ~/.mnemion
cd ~/.mnemion
py -m mnemion restore archive/drawers_export.json
py ~/.mnemion/backfill_trust.py
```

> **Large archives (>10k drawers):** restore computes embeddings for every drawer. If the process is killed (OOM), reduce the batch size: `mnemion restore archive/drawers_export.json --batch-size 20`

See [sync/README.md](sync/README.md) for full details including macOS/Linux cron setup.

---

## Studio — Connect Agents

Mnemion Studio is a local web dashboard that visualises your Anaktoron and — as of v3.5.0 — wires Mnemion into every MCP-capable AI client on your system with one click.

```bash
uv sync --extra studio
uv run uvicorn studio.backend.main:app --port 7891
cd studio/frontend && npm ci && npm run dev
```

Open **http://localhost:5173** (Vite may bump the port if busy) and navigate to **Connect Agents** (or press `G C`). Studio scans for known clients, shows which ones are already connected, and installs Mnemion into the ones that aren't:

| Client | Vendor | Format |
|---|---|---|
| Claude Code | Anthropic | `~/.claude.json` |
| Claude Code (project) | Anthropic | `./.mcp.json` |
| Claude Desktop | Anthropic | platform-specific |
| Cursor | Cursor | `~/.cursor/mcp.json` |
| Windsurf | Codeium | `~/.codeium/windsurf/mcp_config.json` |
| Codex CLI | OpenAI | `~/.codex/config.toml` (TOML) |
| Gemini CLI | Google | `~/.gemini/settings.json` |
| Zed | Zed Industries | `~/.config/zed/settings.json` |

Legacy `mempalace` entries are detected and auto-replaced. Every install writes a timestamped backup to `.mnemion_backups/` next to the config. The installed command uses the absolute path of the Python interpreter that Studio itself is running in, so there are no PATH surprises.

Any client not in the list (OpenClaw, Nemoclaw, Hermes, Cline, custom agents…) can connect using the universal JSON snippet shown at the bottom of the Connect view.

Studio's local API is intentionally narrow: CORS allows the Vite dev ports (`localhost`/`127.0.0.1` 5173-5179), the backend docs port 7891, and Electron's `file://`/`null` origins. If `MNEMION_STUDIO_TOKEN` is set, every mutating `/api` request must send `X-Mnemion-Studio-Token`; packaged Electron generates the token and forwards it through the preload bridge automatically.

See [`studio/README.md`](studio/README.md) for the full view tour.

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

# Mnemion-specific moat behavior: trust, reconstruction, and memory guard
python benchmarks/moat_benchmark.py --suite all
```

The upstream raw LongMemEval result, **96.6% R@5** with no LLM, is real and independently reproduced. In the May 2, 2026 local comparison, official MemPalace `develop` and this Mnemion branch tied on reproduced raw LongMemEval retrieval; do not treat raw vector recall as Mnemion's edge. Mnemion's differentiator is the cognitive/trust moat: trust lifecycle, contradiction handling, reconstruction evidence trails, memory guard, and the deterministic moat eval.

AAAK mode trades recall for token density — use raw mode for maximum retrieval accuracy, and use `mnemion eval moat` / `benchmarks/moat_benchmark.py` to verify Mnemion-only behavior.

---

## Origins

Mnemion began as a fork of mempalace, which introduced the memory Anaktoron metaphor and the AAAK dialect. The hybrid retrieval engine, trust lifecycle, contradiction detection, intelligent LLM lifecycle, knowledge graph, and behavioral protocol bootstrap were all built from scratch by PerseusXR. The name changed when what we built stopped resembling where we started.

---

## Changelog

### v3.5.5 — Live follow-up safety

- Made `mnemion librarian --dry-run` avoid conflict writes while previewing.
- Fixed cognitive consolidation batching so repeated `--limit` runs advance through unconsolidated drawers.
- Added `mnemion memory-guard review --out <dir>` to write report-only Markdown/CSV from existing findings without rescanning or quarantining.

### v3.5.4 — Clean install transitive dependency hardening

- Added explicit OpenTelemetry/protobuf compatibility bounds so user-level installs cannot keep or resolve the old `opentelemetry-exporter-otlp-proto-grpc 1.11.x` stack that crashes with modern protobuf.

### v3.5.3 — Clean install dependency hardening

- Tightened the public Chroma dependency range to the known-good `0.6.x` line so a clean user-level install does not resolve to incompatible Chroma/OpenTelemetry/protobuf combinations.

### v3.5.2 — Windows install smoke hardening

- Fixed console-script launches on Windows terminals that default to cp1252 by forcing UTF-8 stdout/stderr before CLI output.
- Added `mnemion --version` so installed users can verify the global command without importing Python manually.

### v3.5.1 — MemPalace catch-up + release hardening

- Added typed Chroma backend wrappers, safer collection metadata, embedding-device selection, and read-only repair visibility for max-seq-id/HNSW/stale-segment state.
- Added query sanitization, message-granular sweeper ingestion, corpus-origin detection, project scanning, i18n entity-pattern loading, and init auto-mine UX.
- Preserved Mnemion's moat while tightening benchmark claims: raw LongMemEval parity is documented separately from trust lifecycle, contradiction handling, reconstruction, memory guard, and moat eval evidence.
- Added conservative tests and proof-copy smoke coverage for storage repair, MCP registry, real-data search/reconstruct/memory-guard, and deterministic moat benchmarking.

### v3.5.0 — Studio: Connect Agents + systematic bug fixes

#### Repo stabilization — reproducible quality gates
- Added lockfile-backed verification for Python (`uv.lock`), Studio frontend (`npm ci`), and Electron (`package-lock.json`).
- CI now checks `uv lock --check`, Ruff lint/format, tracked shell scripts with `bash -n`, frontend build/audit, and Electron build/audit.
- `.coverage` is no longer tracked, generated caches are ignored, and `.gitattributes` pins LF line endings for source, docs, lockfiles, and shell scripts.
- Preserved Python 3.9+ support with an `onnxruntime==1.20.1` constraint for Python `<3.11`.

#### Studio — local API hardening and build hygiene
- `MNEMION_STUDIO_TOKEN` now protects mutating Studio API calls when configured; callers must send `X-Mnemion-Studio-Token` on `POST`, `PUT`, `PATCH`, and `DELETE` requests under `/api`.
- Packaged Electron generates or inherits the Studio token, passes it to the backend process, and exposes it to the renderer through a minimal preload IPC bridge.
- Electron moved to the current secure major line (`electron` 41 / `electron-builder` 26) and now has an audited lockfile.
- Studio routes are lazy-loaded so the initial Vite bundle no longer pulls in the graph view.

#### Studio — one-click MCP setup for eight AI clients
Studio now ships a **Connect Agents** view (`/connect`, `G C`) that detects installed MCP clients and wires Mnemion into each one's config — safely, with timestamped backups. Supports JSON configs (Claude Code, Claude Desktop, Cursor, Windsurf, Gemini CLI, Zed) and TOML (OpenAI Codex). Detects and replaces legacy `mempalace` references. The installed command uses the absolute path of Studio's own Python interpreter (`sys.executable`), so no PATH-resolution surprises. Any unlisted client (OpenClaw, Nemoclaw, Hermes, Cline, custom agents) can copy the universal JSON snippet. New module: `studio/backend/connectors.py`. New endpoints: `GET/POST /api/connectors[/{id}][/install|/uninstall]`.

#### Studio — graph hover highlight (Obsidian-style)
Hovering a node in the Memory Graph now dims non-neighbours and brightens adjacent edges. Wing Map and Knowledge Graph both use Sigma.js `nodeReducer`/`edgeReducer` via a `<HoverHighlight />` component that lives inside the SigmaContainer. ForceAtlas2 is imported statically (the previous dynamic `import()` caused 2–5s Vite compilation delays on first use).

#### Studio — Dashboard recent drawers + quick capture
Dashboard now shows the 7 most recently added drawers (new `GET /api/drawers/recent` endpoint, sorts by `filed_at`). A **+ New Drawer** button in the header opens the create modal via `LayoutContext`, deduplicating state across `LeftSidebar` and `Dashboard`.

#### Studio — search `wing:`/`room:` operators + trust badges
Typing `wing:legal tax` in the search box parses out the wing filter and searches "tax" within legal. The wing pill is auto-surfaced in the UI. Results with `trust_status: contested` are flagged with an orange warning badge. `api.search()` now typed as `Promise<{ results: SearchHit[] }>` — the previous `DrawerSummary[]` typing hid a systematic field mismatch (see below).

#### Studio — critical bug fixes
Every one of these silently broke a user-visible feature before v3.5.0:

- **Timestamp field mismatch** — all Python writers save `filed_at`, all Studio readers queried `timestamp`. Result: every drawer's "Created" row blank, Recently Added sort order random, Agent activity last-seen never populated. Fixed across four readers in `main.py` with `meta.get("filed_at") or meta.get("timestamp", "")`.
- **DrawerCreateModal didn't navigate** — backend returns `drawer_id`, frontend read `data?.id`. User saw a toast but never reached the new drawer. Now reads `data?.drawer_id ?? data?.id`.
- **Search result previews empty** — `hybrid_searcher` returns `text`, Studio rendered `content`. Backend now maps `text → content` in `/api/search` and `/api/drawer/*.related` before returning to clients.
- **Vault export crashed on click** — `_col.get(...)` referenced an undefined global. Now uses `_get_collection()` and streams the ZIP via `FileResponse` with a temp file (bounded memory regardless of vault size) instead of materialising the whole archive in a `BytesIO`.
- **CORS rejected valid dev/Electron origins** — tightened to the expected local surface: `localhost`/`127.0.0.1` ports 5173-5179 and 7891, plus `file://`/`null` for Electron.
- **CommandPalette rendered literal "undefined"** when a search hit had no content — operator-precedence bug in a chained `+ ... || hit.id` fallback.
- **Hardcoded port 5173** in SettingsView, Electron dev mode, and `start.bat` — SettingsView now shows `window.location.host`, Electron probes 5173–5179 via `findDevPort()`, `start.bat` notes Vite may bump.
- **`~/projects/mnemion` hardcoded in `hooks/mnemion_save_hook.py`** — replaced with `_discover_mnemion_src()` (env var → installed package → legacy fallback).
- **`setState` during render** in `SettingsView` LLM hydration — now `useEffect` with a `hydrated` flag so user edits aren't clobbered.
- **`LeftSidebar` wing didn't auto-expand on deep-link reload** — `useState(isCurrentWing)` only read the initial value; added a `useEffect` that expands when `isCurrentWing` becomes true.
- **`useState<any[]>`, `as any` casts, unused `import hashlib`, duplicate `ChevronRight` import** — various type-safety cleanups. New typed shapes: `StudioConfig`, `LLMConfig`, `RecentDrawer`, `ConnectorStatus`, `SearchHit.trust_status`.

#### Studio — resilience
- **`<ErrorBoundary>`** wraps `<Outlet />` in Layout so one bad render shows a retry button instead of blanking the shell.
- **Dead code removed**: `RightSidebar.tsx` (162 lines, never imported), `/ws` WebSocket stub + `broadcast()` (never called from anywhere), `api.getDrawer` alias.

#### Studio — UX consistency
- Shortcut modal now reflects only wired shortcuts (removed the advertised-but-never-bound `Ctrl+C` and `Backspace` chords); added `G C → Connect Agents`.
- Command Palette now navigates to Connect.

### v3.4.x — LeWM, Entity Registry, Plugins, Anaktoron Rename

#### Palace → Anaktoron rename
All internal references to "palace" renamed to "anaktoron". Storage path: `~/.mempalace/palace` → `~/.mnemion/anaktoron`. Config class: `MempalaceConfig` → `MnemionConfig`. MCP server arg: `--palace` → `--anaktoron`. Env var: `MNEMION_ANAKTORON_PATH` (legacy `MNEMION_PALACE_PATH` still accepted). Config file key: `anaktoron_path` (legacy `palace_path` still accepted).

#### LeWM — Latent Embedding Weight Manifold (`lewm.py`, optional `pip install mnemion[lewm]`)
- **`SIGReg`**: Sketch Isotropic Gaussian Regularizer — measures embedding distribution deviation from isotropic Gaussian using the Epps-Pulley test statistic. Verified **+40% Recall@5** improvement (0.600 → 1.000) in A/B benchmark on a 2,000-drawer test Anaktoron.
- **`groom_embeddings()`**: lightweight `LatentAdapter` (identity-initialized linear layer) trained in the background during ingestion — spreads embeddings across the latent manifold without destroying semantic structure. Contrastive preservation + diversity penalty + SIGReg loss. Safe to call without torch: returns embeddings unchanged.

#### JEPA Predictor (`predictor.py`, requires `mnemion[lewm]`)
- **`predict_next_context()`**: LSTM-based next-context predictor. Maintains a singleton model, fine-tunes online from session history, predicts the next embedding for pre-fetch or room suggestion. Exposed as `mnemion_predict_next` MCP tool.
- **`record_activity()`**: thread-safe session history log at `~/.mnemion/session_history.json`.

#### Personal Entity Registry (`entity_registry.py`)
- Persistent registry at `~/.mnemion/entity_registry.json` — three priority sources: onboarding > learned > wiki.
- Wikipedia disambiguation via REST API: detects person/place/concept for unknown capitalized words, caches results, flags words that are also common English (e.g. "Grace", "Max", "May").
- Context-pattern disambiguation: 14 person-context vs. 9 concept-context patterns decide "Riley said" (person) from "if you ever" (adverb).
- `learn_from_text()`: discovers entity candidates from session text at configurable confidence threshold.

#### Interactive Onboarding (`onboarding.py`)
- Guided first-run: mode (work/personal/combo), people + nicknames, projects, wings. Auto-detects additional names from project files; warns about ambiguous names.
- Generates `~/.mnemion/aaak_entities.md` + `~/.mnemion/critical_facts.md` so the AI knows the user's world from session one.

#### Multi-format Chat Normalizer (`normalize.py`)
- Converts any chat export to Mnemion transcript format (`>` markers). No API key, fully local.
- Supports: Claude Code JSONL, OpenAI Codex CLI JSONL, Claude.ai JSON (flat + privacy export), ChatGPT `conversations.json` (mapping tree), Slack JSON, plain text (pass-through).

#### AAAK Dialect Compression (`dialect.py`)
- **`mnemion compress [--wing W] [--dry-run]`**: compresses drawers using AAAK notation (~30x token reduction). Stores in a separate `mnemion_compressed` collection.

#### Spellcheck (`spellcheck.py`)
- Corrects typos in user messages before Anaktoron filing. Preserves technical terms, CamelCase, URLs, known entity names. Optional dep: `autocorrect`.

#### Unified Hook Dispatcher (`hooks_cli.py`)
- **`mnemion hook run --hook <name> --harness <claude-code|codex>`**: Python hook dispatcher replacing standalone shell scripts.
- `stop`: blocks every 15 exchanges for auto-save. `precompact`: always blocks with comprehensive save. `session-start`: initializes tracking.
- `MNEMION_DIR` env triggers background `mnemion mine` on stop, synchronous on precompact. Path-traversal-safe session ID sanitization.

#### Instructions CLI (`instructions_cli.py`)
- **`mnemion instructions <name>`**: prints skill instructions from `mnemion/instructions/`. Available: `init`, `mine`, `search`, `status`, `help`.

#### Claude Code Plugin (`.claude-plugin/`)
- First-class Claude Code plugin: `plugin.json`, `marketplace.json`, 5 slash commands (`/mnemion:init`, `/mnemion:mine`, `/mnemion:search`, `/mnemion:status`, `/mnemion:help`), stop + precompact hooks, MCP server registration.

#### Codex Plugin (`.codex-plugin/`)
- First-class OpenAI Codex CLI plugin: `plugin.json`, 5 skills (`/init`, `/mine`, `/search`, `/status`, `/help`), stop hook, MCP server registration. `.agents/plugins/marketplace.json` for local marketplace discovery.

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
- **MCP argument whitelisting**: undeclared keys are stripped from tool args before dispatch, and public `mnemion_add_drawer` no longer exposes `added_by` — prevents audit-trail spoofing by injected `wait_for_previous`, `added_by`, or other rogue parameters.
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
- Auto-migration: on first startup, existing `.mempalace` config is detected and migrated to `.mnemion` with confirmation prompt
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
[version-shield]: https://img.shields.io/github/v/release/Perseusxrltd/mnemion?style=flat-square&labelColor=0a0e14&color=4dc9f6
[release-link]: https://github.com/Perseusxrltd/mnemion/releases
[python-shield]: https://img.shields.io/badge/python-3.9--3.14-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8
[python-link]: https://www.python.org/
[license-shield]: https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14
[license-link]: https://github.com/Perseusxrltd/mnemion/blob/main/LICENSE
