# Mnemion Hooks — Auto-Save for Terminal AI Tools

These hooks make Mnemion save automatically. Two modes available: AI-assisted (original) and direct Python extraction (new, recommended).

---

## Hook Comparison

| | `mnemion_save_hook.sh` | `mnemion_save_hook.py` |
|---|---|---|
| **Method** | Blocks AI, asks it to save | Extracts directly, never blocks |
| **Requires AI cooperation** | Yes | No |
| **Interrupts conversation** | Yes (once per N messages) | Never |
| **Memory quality** | High (AI understands context) | Good (pattern-based: decisions, preferences, milestones) |
| **Speed** | Slow (AI round-trip) | Fast (<100ms) |
| **Recommended for** | Rich, contextual saves | Continuous background extraction |

Use the Python hook for always-on extraction, and the shell hook when you want the AI to do a deep, structured save.

---

## Hook 1 — Python Direct Extraction (Recommended)

**`mnemion_save_hook.py`** — extracts memories from the transcript without AI involvement.

### What it does

Every N exchanges (default: 3), it:
1. Reads the JSONL transcript
2. Runs `general_extractor.py` (pattern-based, no LLM, no API key)
3. Saves matched memories to ChromaDB with SHA1-based dedup
4. Triggers `SyncMemories.ps1` (git commit + push) in the background
5. Outputs `{}` — never blocks the conversation

### Install — Claude Code

Add to `.claude/settings.local.json`:

```json
{
  "hooks": {
    "Stop": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 /absolute/path/to/hooks/mnemion_save_hook.py",
        "timeout": 15
      }]
    }]
  }
}
```

### Configuration

Edit the top of `mnemion_save_hook.py`:

```python
SAVE_INTERVAL = 3           # exchanges between auto-saves
MNEMION_SRC = "~/projects/mnemion"   # path to this repo
SYNC_SCRIPT   = "~/.mnemion/SyncMemories.ps1"   # auto-sync script (optional)
```

Set `SYNC_SCRIPT = ""` to disable git sync (saves only, no push).

### Memory types extracted

| Type | Example pattern |
|------|----------------|
| `decision` | "decided to", "going with", "we'll use" |
| `preference` | "prefer", "like", "hate", "always use" |
| `milestone` | "finished", "deployed", "shipped", "completed" |
| `problem` | "bug", "issue", "broken", "failing" |
| `emotional` | "frustrated", "excited", "worried", "happy" |

---

## Hook 2 — AI-Assisted Save (Shell, Original)

**`mnemion_save_hook.sh`** — blocks the AI every N messages and asks it to file memories.

| Hook | When It Fires | What Happens |
|------|--------------|-------------|
| **Save Hook** | Every 15 human messages | Blocks AI, tells it to save key topics/decisions/quotes |
| **PreCompact Hook** | Right before context compaction | Emergency save — forces the AI to save EVERYTHING |

### Install — Claude Code

```json
{
  "hooks": {
    "Stop": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "/absolute/path/to/hooks/mnemion_save_hook.sh",
        "timeout": 30
      }]
    }],
    "PreCompact": [{
      "hooks": [{
        "type": "command",
        "command": "/absolute/path/to/hooks/mnemion_precompact_hook.sh",
        "timeout": 30
      }]
    }]
  }
}
```

Make them executable:
```bash
chmod +x hooks/mnemion_save_hook.sh hooks/mnemion_precompact_hook.sh
```

### Install — Codex CLI (OpenAI)

Add to `.codex/hooks.json`:

```json
{
  "Stop": [{
    "type": "command",
    "command": "/absolute/path/to/hooks/mnemion_save_hook.sh",
    "timeout": 30
  }],
  "PreCompact": [{
    "type": "command",
    "command": "/absolute/path/to/hooks/mnemion_precompact_hook.sh",
    "timeout": 30
  }]
}
```

### Configuration

Edit `mnemion_save_hook.sh` to change:
- **`SAVE_INTERVAL=15`** — messages between saves
- **`MNEMION_DIR`** — set to a conversations directory to auto-run `mnemion mine` on each trigger

---

## Debugging

Check the hook log:
```bash
cat ~/.mnemion/hook_state/hook.log
```

Example Python hook output:
```
[2026-04-09 14:30:15] Session abc123: 3 exchanges | extracted 2 memories | saved 2 new | types: {'decision', 'preference'}
[2026-04-09 14:33:22] Session abc123: 6 exchanges | extracted 1 memories | saved 1 new | types: {'milestone'}
[2026-04-09 14:35:01] Session abc123: 9 exchanges | no memories matched patterns
```

---

## Using Both Hooks Together

Run the Python hook on `Stop` (always-on, low friction) and the shell PreCompact hook on `PreCompact` (deep save before context loss):

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
    }],
    "PreCompact": [{
      "hooks": [{
        "type": "command",
        "command": "/path/to/hooks/mnemion_precompact_hook.sh",
        "timeout": 30
      }]
    }]
  }
}
```
