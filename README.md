<div align="center">

<img src="assets/mempalace_logo.png" alt="MemPalace" width="280">

# MemPalace — PerseusXR High-Fidelity Distribution

### Hybrid Retrieval · Memory Trust Layer · Auto-Save · Live Sync

<br>

This is a specialized distribution of MemPalace maintained by **PerseusXR**. It preserves the verbatim-first philosophy of the original while adding four production-grade layers: hybrid lexical-semantic retrieval, a human-like memory trust lifecycle, AI-independent auto-save hooks, and an automated palace sync system.

<br>

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]

<br>

[What We Added](#what-perseusxr-added) · [Quick Start](#quick-start) · [MCP Tools](#mcp-tools) · [Auto-Save Hooks](#auto-save-hooks) · [Palace Sync](#palace-sync) · [Benchmarks](#benchmarks) · [Architecture](#architecture)

</div>

---

## What PerseusXR Added

The upstream MemPalace is excellent foundational work. This fork addresses four production gaps:

### 1. Hybrid Lexical-Semantic Retrieval (`hybrid_searcher.py`)

Vector search alone has a "Vector Blur" problem: exact technical identifiers (git hashes, function signatures, hex addresses) carry low semantic weight and get outranked by thematically related but wrong results.

We added a **SQLite FTS5 lexical mirror** alongside ChromaDB, and fuse both result sets using **Reciprocal Rank Fusion (RRF)**. Benchmarked result:

| Metric | Vector Only | Hybrid RRF | Improvement |
|--------|-------------|------------|-------------|
| Mean Reciprocal Rank (MRR) | 0.5395 | 0.8833 | **+63.7%** |
| Hit@1 Accuracy | 46.7% | 80.0% | **+33.3%** |

*4,344-drawer production palace, 15-target Gold Standard. Reproduce: `python eval/benchmark.py`*

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
- **Stage 2**: For ambiguous cases — pulls additional palace context, second LLM pass to resolve.

Save speed: unchanged (detection is async, daemon threads). Fetch speed: improved (superseded memories excluded by default, confidence weights scores).

Uses a local vLLM-served model. No cloud calls, no API key.

### 3. AI-Independent Auto-Save Hook (`hooks/mempal_save_hook.py`)

The original hook asks the AI to save memories at intervals — which means it depends on the AI cooperating. We replaced it with a Python hook that:

- Reads the transcript directly
- Extracts memories via `general_extractor.py` (pure patterns, no LLM)
- Saves to ChromaDB with hash-based dedup
- Triggers a git sync in the background
- **Always outputs `{}` — never blocks the AI, never interrupts the conversation**

Covers: decisions, preferences, milestones, problems, emotional notes.

### 4. Palace Sync (`sync/SyncMemories.ps1`)

The ChromaDB palace is ~860MB — too large for git. The sync system:

1. Exports all drawer content to `archive/drawers_export.json` (~24MB)
2. Commits and pushes the JSON to your private memory repo
3. Runs automatically via Task Scheduler (Windows) or cron (macOS/Linux)

On a new machine: `git clone <repo>` → `mempalace mine archive/drawers_export.json` → full palace restored.

---

## Quick Start

### Windows (one-shot installer)

```powershell
git clone https://github.com/Perseusxrltd/mempalace
cd mempalace
pip install .

# Sets up hooks, Task Scheduler sync, vLLM auto-start, backfills trust records
powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1
```

Then add the MCP server:
```bash
claude mcp add mempalace -- python -m mempalace.mcp_server
```

Restart Claude Code. In your first conversation, call `mempalace_status` — it loads the palace overview and teaches the AI the AAAK dialect automatically.

### Manual / macOS / Linux

```bash
pip install .

# Mine a project or conversation history
mempalace init ~/projects/myapp
mempalace mine ~/projects/myapp

# Add MCP server
claude mcp add mempalace -- python -m mempalace.mcp_server

# Install the auto-save hook (add to .claude/settings.local.json)
# See hooks/README.md for full instructions

# Backfill trust records for existing drawers
py sync/backfill_trust.py
```

### LLM backend (contradiction detection — optional)

Contradiction detection works with any local LLM. Configure it interactively:

```bash
mempalace llm setup
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
mempalace llm status   # show config + ping
mempalace llm test     # send a test prompt
```

**vLLM on WSL** (for GPU users):
```bash
cp sync/run_vllm.sh ~/run_vllm.sh
bash ~/run_vllm.sh &
# ~60s to load, then: mempalace llm setup → choose vllm → http://localhost:8000
```

The Windows installer registers vLLM as a Task Scheduler task that starts on login.

---

## MCP Tools

The MCP server exposes 24 tools across four categories.

### Read

| Tool | What it does |
|------|-------------|
| `mempalace_status` | Palace overview — drawer counts, wing breakdown, AAAK spec |
| `mempalace_list_wings` | All wings with drawer counts |
| `mempalace_list_rooms` | Rooms within a wing |
| `mempalace_get_taxonomy` | Full wing → room → count tree |
| `mempalace_get_aaak_spec` | Get the AAAK compressed memory dialect spec |
| `mempalace_search` | Hybrid search (vector + lexical RRF). Filters out superseded memories. Flags contested with ⚠ |
| `mempalace_check_duplicate` | Check if content already exists before filing |

### Write

| Tool | What it does |
|------|-------------|
| `mempalace_add_drawer` | File content into a wing/room. Creates trust record + spawns background contradiction detection |
| `mempalace_delete_drawer` | Soft-delete a drawer (trust record marked `historical`, never hard-removed) |

### Knowledge Graph

| Tool | What it does |
|------|-------------|
| `mempalace_kg_query` | Query entity relationships with optional temporal filter |
| `mempalace_kg_add` | Add a typed fact (subject → predicate → object, with valid_from) |
| `mempalace_kg_invalidate` | Mark a fact as no longer true |
| `mempalace_kg_timeline` | Chronological fact history for an entity |
| `mempalace_kg_stats` | Knowledge graph overview |
| `mempalace_traverse` | Walk the palace graph from a room — find connected ideas |
| `mempalace_find_tunnels` | Rooms that bridge two wings |
| `mempalace_graph_stats` | Graph topology overview |

### Trust

| Tool | What it does |
|------|-------------|
| `mempalace_trust_stats` | Trust layer overview — counts by status, avg confidence, pending conflicts |
| `mempalace_verify` | Confirm a drawer is accurate (+0.05 confidence) |
| `mempalace_challenge` | Flag a drawer as suspect (−0.1 confidence, marks contested) |
| `mempalace_get_contested` | List unresolved contested memories for review |
| `mempalace_resolve_contest` | Manually pick the winner of a conflict |

### Agent Diary

| Tool | What it does |
|------|-------------|
| `mempalace_diary_write` | Write a diary entry in AAAK format — agent's personal journal |
| `mempalace_diary_read` | Read recent diary entries |

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
        "command": "python3 /path/to/hooks/mempal_save_hook.py",
        "timeout": 15
      }]
    }]
  }
}
```

See [hooks/README.md](hooks/README.md) for full installation, Codex CLI setup, and configuration options.

---

## Palace Sync

Automatic hourly backup to a private git repo. Works across machines.

**Setup (Windows):**
```powershell
# Copy sync script
Copy-Item sync/SyncMemories.ps1 $env:USERPROFILE\.mempalace\

# Schedule hourly sync
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -File $env:USERPROFILE\.mempalace\SyncMemories.ps1"
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At (Get-Date)
Register-ScheduledTask -TaskName "MemPalaceMemorySync" -Action $action -Trigger $trigger -RunLevel Highest -Force
```

**Restore on new machine:**
```bash
git clone https://github.com/YOUR_USERNAME/personal-ai-memories ~/.mempalace
cd ~/.mempalace
py -m mempalace mine archive/drawers_export.json
py ~/.mempalace/backfill_trust.py
```

See [sync/README.md](sync/README.md) for full details including macOS/Linux cron setup.

---

## Architecture

```
User → CLI → miner/convo_miner ─────────────────┐
                                                  ↓
                                        ChromaDB palace (vectors)
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
~/.mempalace/
├── palace/                   ← ChromaDB (vectors, ~860MB, git-ignored)
├── knowledge_graph.sqlite3   ← KG triples + FTS5 + trust tables (git-ignored)
├── archive/
│   └── drawers_export.json   ← portable JSON export (~24MB, committed to git)
├── hooks/
│   └── mempal_save_hook.py   ← Python auto-save hook
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

## A Note from the Original Authors

> *See the [honest README correction](https://github.com/milla-jovovich/mempalace#a-note-from-milla--ben--april-7-2026) from Milla Jovovich & Ben Sigman for context on the original project's benchmark claims and corrections.*

---

## License

MIT — see [LICENSE](LICENSE).

<!-- Link Definitions -->
[version-shield]: https://img.shields.io/badge/version-3.1.0-4dc9f6?style=flat-square&labelColor=0a0e14
[release-link]: https://github.com/Perseusxrltd/mempalace/releases
[python-shield]: https://img.shields.io/badge/python-3.9+-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8
[python-link]: https://www.python.org/
[license-shield]: https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14
[license-link]: https://github.com/Perseusxrltd/mempalace/blob/main/LICENSE
