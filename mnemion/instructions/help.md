# Mnemion

AI memory system. Store everything, find anything. Local, free, no API key.

---

## Slash Commands

| Command              | Description                    |
|----------------------|--------------------------------|
| /mnemion:init      | Install and set up Mnemion   |
| /mnemion:search    | Search your memories           |
| /mnemion:mine      | Mine projects and conversations|
| /mnemion:status    | Anaktoron overview and stats      |
| /mnemion:help      | This help message              |

---

## MCP Tools

### Anaktoron (read)
- mnemion_status -- Anaktoron status and stats
- mnemion_list_wings -- List all wings
- mnemion_list_rooms -- List rooms in a wing
- mnemion_get_taxonomy -- Get the full taxonomy tree
- mnemion_search -- Search memories by query
- mnemion_reconstruct -- Rebuild answers from cognitive graph evidence trails
- mnemion_get_evidence_trail -- Inspect cognitive units and edges for a drawer
- mnemion_check_duplicate -- Check if a memory already exists
- mnemion_get_aaak_spec -- Get the AAAK specification

### Anaktoron (write)
- mnemion_add_drawer -- Add a new memory (drawer)
- mnemion_consolidate -- Extract cognitive graph units from drawers
- mnemion_memory_guard_scan -- Scan and optionally quarantine risky memories
- mnemion_delete_drawer -- Delete a memory (drawer)

### Knowledge Graph
- mnemion_kg_query -- Query the knowledge graph
- mnemion_kg_add -- Add a knowledge graph entry
- mnemion_kg_invalidate -- Invalidate a knowledge graph entry
- mnemion_kg_timeline -- View knowledge graph timeline
- mnemion_kg_stats -- Knowledge graph statistics

### Navigation
- mnemion_traverse -- Traverse the Anaktoron structure
- mnemion_find_tunnels -- Find cross-wing connections
- mnemion_graph_stats -- Graph connectivity statistics

### Trust and Safety
- mnemion_trust_stats -- Trust layer status overview
- mnemion_verify -- Confirm a drawer as accurate
- mnemion_challenge -- Challenge a drawer and lower confidence
- mnemion_get_contested -- List unresolved contested drawers
- mnemion_resolve_contest -- Resolve a contested memory

### Prediction
- mnemion_predict_next -- Predict likely next relevant context

### Agent Diary
- mnemion_diary_write -- Write a diary entry
- mnemion_diary_read -- Read diary entries

---

## CLI Commands

    mnemion init <dir>                  Initialize a new Anaktoron
    mnemion mine <dir>                  Mine a project (default mode)
    mnemion mine <dir> --mode convos    Mine conversation exports
    mnemion sweep <jsonl-or-dir>        Ingest Claude/Codex JSONL messages with skip counts
    mnemion search "query"              Search your memories
    mnemion consolidate                 Extract cognitive graph units; repeated --limit runs advance through unconsolidated drawers
    mnemion reconstruct "query"         Search evidence trails and topic tunnels
    mnemion memory-guard scan           Scan for prompt-injection/privacy risks
    mnemion memory-guard review         Write report-only Markdown/CSV from existing findings
    mnemion eval moat                   Run deterministic moat eval cases
    mnemion split <dir>                 Split large transcript files
    mnemion wake-up                     Load Anaktoron into context
    mnemion compress                    Compress Anaktoron storage
    mnemion status                      Show Anaktoron status
    mnemion repair --mode status        Check Chroma/HNSW repair status
    mnemion hook run                    Run hook logic (for harness integration)
    mnemion instructions <name>         Output skill instructions

---

## Auto-Save Hooks

- Stop hook -- Automatically saves memories every 15 messages. Counts human
  messages in the session transcript (skipping command-messages). When the
  threshold is reached, blocks the AI with a save instruction. Uses
  ~/.mnemion/hook_state/ to track save points per session. If
  stop_hook_active is true, passes through to prevent infinite loops.

- PreCompact hook -- Emergency save before context compaction. Always blocks
  with a comprehensive save instruction because compaction means the AI is
  about to lose detailed context.

Hooks read JSON from stdin and output JSON to stdout. They can be invoked via:

    echo '{"session_id":"abc","stop_hook_active":false,"transcript_path":"..."}' | mnemion hook run --hook stop --harness claude-code

---

## Architecture

    Wings (projects/people)
      +-- Rooms (topics)
            +-- Closets (summaries)
                  +-- Drawers (verbatim memories)

    Halls connect rooms within a wing.
    Tunnels connect rooms across wings.

The Anaktoron is stored locally using ChromaDB for vector search and SQLite for
metadata. No cloud services or API keys required.

---

## Getting Started

1. /mnemion:init -- Set up your Anaktoron
2. /mnemion:mine -- Mine a project or conversation
3. /mnemion:search -- Find what you stored
