#!/usr/bin/env bash
# Mnemion Multi-Agent Sync — Linux / macOS (Bash)
# =================================================
# Exports the local Anaktoron to JSON, merges with remote if needed, commits,
# and pushes.  Safe for concurrent use by multiple agents on different machines.
#
# How it works:
#   1. Acquire a local lock file (prevents concurrent runs on the same machine)
#   2. Export local ChromaDB drawers → archive/drawers_export.json
#   3. git fetch (non-destructive peek at remote state)
#   4. If remote is ahead: merge remote export into local using merge_exports.py
#   5. git add + commit (with agent identity in message)
#   6. git push --force-with-lease
#      On rejection (another agent pushed): undo commit, sleep jitter, retry
#   7. Release lock
#
# Setup:
#   Copy to ~/.mnemion/SyncMemories.sh, chmod +x, schedule with cron.
#   See sync/README.md for full instructions.
#
# Environment variables:
#   MNEMION_AGENT_ID    — display name in commit messages (default: hostname)
#   MNEMION_BRANCH      — git branch to sync (default: auto-detected, fallback: main)
#   MNEMION_REPO_DIR    — override repo dir (default: ~/.mnemion)
#   MNEMION_SOURCE_DIR  — path to mnemion package (default: auto-detected)
#   MNEMION_PYTHON      — python binary to use (default: python3 or python)
#   MNEMION_SYNC_KG     — set to 1/true/yes to also sync knowledge_graph.sql (can be very large)

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

AGENT_ID="${MNEMION_AGENT_ID:-$(hostname)}"
REPO_DIR="${MNEMION_REPO_DIR:-$HOME/.mnemion}"
SYNC_KG="${MNEMION_SYNC_KG:-0}"
MAX_RETRIES=5

# Detect python binary
if [ -n "${MNEMION_PYTHON:-}" ]; then
    PYTHON="$MNEMION_PYTHON"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "ERROR: No python3 or python found on PATH." >&2
    exit 1
fi

# Locate the mnemion source directory (for sys.path in export script)
if [ -n "${MNEMION_SOURCE_DIR:-}" ]; then
    SRC_DIR="$MNEMION_SOURCE_DIR"
else
    # Script lives in ~/.mnemion/ — source is the mnemion repo if co-located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PARENT_DIR="$(dirname "$SCRIPT_DIR")"
    if [ -d "$PARENT_DIR/mnemion" ]; then
        SRC_DIR="$PARENT_DIR"
    else
        SRC_DIR=""
    fi
fi

# Locate merge_exports.py
MERGE_SCRIPT=""
if [ -n "$SRC_DIR" ] && [ -f "$SRC_DIR/sync/merge_exports.py" ]; then
    MERGE_SCRIPT="$SRC_DIR/sync/merge_exports.py"
elif [ -f "$(dirname "${BASH_SOURCE[0]}")/merge_exports.py" ]; then
    MERGE_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/merge_exports.py"
else
    echo "ERROR: merge_exports.py not found. Set MNEMION_SOURCE_DIR." >&2
    exit 1
fi

EXPORT_DIR="$REPO_DIR/archive"
EXPORT_FILE="$EXPORT_DIR/drawers_export.json"
REMOTE_FILE="$EXPORT_DIR/.drawers_remote_tmp.json"
KG_EXPORT_FILE="$EXPORT_DIR/knowledge_graph.sql"
KG_REMOTE_FILE="$EXPORT_DIR/.kg_remote_tmp.sql"
LOCK_FILE="$REPO_DIR/.sync_lock"

SYNC_KG_NORMALIZED="$(printf '%s' "$SYNC_KG" | tr '[:upper:]' '[:lower:]')"
case "$SYNC_KG_NORMALIZED" in
    1|true|yes) SYNC_KG_ENABLED=1 ;;
    *) SYNC_KG_ENABLED=0 ;;
esac

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [$AGENT_ID] $*"; }

# ── Lock ──────────────────────────────────────────────────────────────────────

release_lock() { rm -f "$LOCK_FILE"; }

if [ -f "$LOCK_FILE" ]; then
    if [ "$(uname)" = "Darwin" ]; then
        LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCK_FILE") ))
    else
        LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE") ))
    fi
    if [ "$LOCK_AGE" -gt 600 ]; then
        log "Stale lock removed (age: ${LOCK_AGE}s)"
        rm -f "$LOCK_FILE"
    else
        log "Another sync is running (lock age: ${LOCK_AGE}s). Exiting."
        exit 0
    fi
fi

echo "$AGENT_ID $(date -Iseconds)" > "$LOCK_FILE"
trap release_lock EXIT INT TERM

# ── Guard ─────────────────────────────────────────────────────────────────────

if [ ! -d "$REPO_DIR/.git" ]; then
    log "ERROR: $REPO_DIR is not a git repo. Run 'git init' there first."
    exit 1
fi

cd "$REPO_DIR"
mkdir -p "$EXPORT_DIR"
if [ "$SYNC_KG_ENABLED" -ne 1 ]; then
    rm -f "$KG_EXPORT_FILE"
fi

# ── Detect branch ─────────────────────────────────────────────────────────────

if [ -n "${MNEMION_BRANCH:-}" ]; then
    BRANCH="$MNEMION_BRANCH"
else
    BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'main')"
    [ "$BRANCH" = "HEAD" ] && BRANCH="main"
fi

# ── Export ────────────────────────────────────────────────────────────────────

EXPORT_RESULT=$("$PYTHON" - <<PYEOF
import sys, json
if "$SRC_DIR":
    sys.path.insert(0, "$SRC_DIR")
from mnemion.chroma_compat import make_persistent_client
from mnemion.config import MnemionConfig

config = MnemionConfig()
BATCH = 2000  # stay under SQLite SQLITE_MAX_VARIABLE_NUMBER on any version
try:
    client  = make_persistent_client(config.anaktoron_path, vector_safe=True, collection_name=config.collection_name)
    col     = client.get_collection(config.collection_name)
    drawers = []
    offset  = 0
    while True:
        batch = col.get(include=['documents', 'metadatas'], limit=BATCH, offset=offset)
        ids = batch.get('ids') or []
        if not ids:
            break
        for id_, doc, meta in zip(ids, batch['documents'], batch['metadatas']):
            wing = (meta or {}).get('wing', '')
            if wing == 'sessions' and (meta or {}).get('added_by') != 'auto_hook':
                continue
            drawers.append({'id': id_, 'content': doc, 'meta': meta})
        offset += len(ids)
        if len(ids) < BATCH:
            break
    with open("$EXPORT_FILE", 'w', encoding='utf-8') as f:
        json.dump(sorted(drawers, key=lambda d: d['id']), f, ensure_ascii=False, indent=2)
    print(f'{len(drawers)} drawers exported')
    
    sync_kg = "$SYNC_KG_ENABLED" == "1"
    import sqlite3, os
    from pathlib import Path
    kg_path = Path(config.anaktoron_path).parent / 'knowledge_graph.sqlite3'
    if sync_kg and kg_path.exists():
        conn = sqlite3.connect(kg_path)
        with open("$KG_EXPORT_FILE", 'w', encoding='utf-8') as f:
            for line in conn.iterdump():
                f.write(f"{line}\\n")
        conn.close()
        print('Knowledge Graph / Trust data dumped')
except Exception as e:
    print(f'Export error: {e}', file=sys.stderr)
    sys.exit(1)
PYEOF
) 2>&1

EXPORT_EXIT=$?
log "Export: $EXPORT_RESULT"
if [ "$EXPORT_EXIT" -ne 0 ]; then
    log "Export failed. Aborting."
    exit 1
fi

# ── Sync loop ─────────────────────────────────────────────────────────────────

committed=0

for attempt in $(seq 1 "$MAX_RETRIES"); do
    if [ "$attempt" -gt 1 ]; then
        log "Retry $attempt/$MAX_RETRIES..."
    fi

    # Undo previous attempt's commit before re-merging
    if [ "$committed" -eq 1 ]; then
        COMMIT_COUNT="$(git rev-list --count HEAD 2>/dev/null || echo 0)"
        if [ "$COMMIT_COUNT" -gt 1 ]; then
            git reset HEAD~1 --soft >/dev/null 2>&1
        else
            git update-ref -d HEAD >/dev/null 2>&1 || true
        fi
        committed=0
        JITTER=$(( RANDOM % 8 + 2 ))
        log "Push rejected. Waiting ${JITTER}s before retry..."
        sleep "$JITTER"
    fi

    # ── Fetch ───────────────────────────────────────────────────────────────
    git fetch origin 2>/dev/null

    # ── Merge if remote is ahead ─────────────────────────────────────────────
    REMOTE_AHEAD="$(git rev-list "HEAD..origin/$BRANCH" --count 2>/dev/null || echo 0)"

    if [ "$REMOTE_AHEAD" -gt 0 ]; then
        log "Remote is $REMOTE_AHEAD commit(s) ahead. Merging exports..."
        if git show "origin/$BRANCH:archive/drawers_export.json" > "$REMOTE_FILE" 2>/dev/null; then
            MERGE_RESULT=$("$PYTHON" "$MERGE_SCRIPT" \
                --ours "$EXPORT_FILE" \
                --theirs "$REMOTE_FILE" \
                --out "$EXPORT_FILE" 2>&1)
            log "$MERGE_RESULT"
        else
            log "Remote has no export yet — skipping merge"
        fi
        rm -f "$REMOTE_FILE"

        # Optional: sync the Trust & Knowledge Graph SQLite table.
        if [ "$SYNC_KG_ENABLED" -eq 1 ] && git show "origin/$BRANCH:archive/knowledge_graph.sql" > "$KG_REMOTE_FILE" 2>/dev/null; then
            log "Trust Graph Remote File Found. Merging SQL dumps natively..."
            "$PYTHON" - <<PYEOF2
import sqlite3, sys
from pathlib import Path
from mnemion.config import MnemionConfig
try:
    config = MnemionConfig()
    kg_path = Path(config.anaktoron_path).parent / 'knowledge_graph.sqlite3'
    if kg_path.exists():
        conn = sqlite3.connect(kg_path)
        with open("$KG_REMOTE_FILE", 'r', encoding='utf-8') as f:
            sql_script = f.read()
        sql_script = sql_script.replace('INSERT INTO', 'INSERT OR REPLACE INTO')
        conn.executescript(sql_script)
        conn.commit()
        conn.close()
except Exception as e:
    print(f'KG Merge exception: {e}')
PYEOF2
            rm -f "$KG_REMOTE_FILE"
            
            # Re-dump the now successfully unified graph so it is staged 
            "$PYTHON" -c "import sqlite3; from mnemion.config import MnemionConfig; from pathlib import Path; p=Path(MnemionConfig().anaktoron_path).parent/'knowledge_graph.sqlite3'; c=sqlite3.connect(p); f=open('$KG_EXPORT_FILE', 'w', encoding='utf-8'); [f.write(l+'\n') for l in c.iterdump()]; c.close()"
        fi
    fi

    # ── Stage only portable sync artifacts ──────────────────────────────────
    sync_artifacts=(
        "archive/drawers_export.json"
        ".gitignore"
        "SyncMemories.ps1"
        "SyncMemories.sh"
        "merge_exports.py"
        "backfill_trust.py"
    )
    if [ "$SYNC_KG_ENABLED" -eq 1 ]; then
        sync_artifacts+=("archive/knowledge_graph.sql")
    fi
    for artifact in "${sync_artifacts[@]}"; do
        if [ -e "$artifact" ]; then
            git add -- "$artifact"
        fi
    done

    if git diff --staged --quiet; then
        log "No changes to sync."
        exit 0
    fi

    # ── Commit ───────────────────────────────────────────────────────────────
    NOW="$(date '+%Y-%m-%d %H:%M:%S')"
    DRAWER_COUNT="$(echo "$EXPORT_RESULT" | grep -oP '\d+ drawers' || echo 'drawers')"
    git commit -m "sync: $NOW [$AGENT_ID] $DRAWER_COUNT" >/dev/null 2>&1
    committed=1

    # ── Push ─────────────────────────────────────────────────────────────────
    PUSH_OUT="$(git push origin "$BRANCH" --force-with-lease 2>&1)"
    PUSH_EXIT=$?

    if [ "$PUSH_EXIT" -eq 0 ]; then
        log "Pushed OK (attempt $attempt). Branch: $BRANCH"
        committed=0
        exit 0
    fi

    log "Push failed: $PUSH_OUT"

    if [ "$attempt" -ge "$MAX_RETRIES" ]; then
        log "ERROR: Push failed after $MAX_RETRIES attempts. Manual intervention needed."
        exit 1
    fi
done

log "WARNING: Exited loop unexpectedly. Check manually."
exit 1
