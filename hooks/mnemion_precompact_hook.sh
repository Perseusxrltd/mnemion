#!/bin/bash
# MNEMION PRE-COMPACT HOOK — Emergency save before compaction
#
# Claude Code "PreCompact" hook. Fires RIGHT BEFORE the conversation
# gets compressed to free up context window space.
#
# This is the safety net. When compaction happens, the AI loses detailed
# context about what was discussed. This hook forces one final save of
# EVERYTHING before that happens.
#
# Unlike the save hook (which triggers every N exchanges), this ALWAYS
# blocks — because compaction is always worth saving before.
#
# === INSTALL ===
# Add to .claude/settings.local.json:
#
#   "hooks": {
#     "PreCompact": [{
#       "hooks": [{
#         "type": "command",
#         "command": "/absolute/path/to/mnemion_precompact_hook.sh",
#         "timeout": 30
#       }]
#     }]
#   }
#
# For Codex CLI, add to .codex/hooks.json:
#
#   "PreCompact": [{
#     "type": "command",
#     "command": "/absolute/path/to/mnemion_precompact_hook.sh",
#     "timeout": 30
#   }]
#
# === HOW IT WORKS ===
#
# Claude Code sends JSON on stdin with:
#   session_id — unique session identifier
#
# We always return decision: "block" with a reason telling the AI
# to save everything. After the AI saves, compaction proceeds normally.
#
# === MNEMION CLI ===
# This repo uses: mnemion mine <dir>
# or:            mnemion mine <dir> --mode convos
# Set MNEMION_DIR below if you want the hook to auto-ingest before compaction.
# Leave blank to rely on the AI's own save instructions.

STATE_DIR="$HOME/.mnemion/hook_state"
mkdir -p "$STATE_DIR"

# Optional: set to the directory you want auto-ingested before compaction.
# Example: MNEMION_DIR="$HOME/conversations"
# Leave empty to skip auto-ingest (AI handles saving via the block reason).
MNEMION_DIR=""

# Read JSON input from stdin
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null)

echo "[$(date '+%H:%M:%S')] PRE-COMPACT triggered for session $SESSION_ID" >> "$STATE_DIR/hook.log"

# Optional: run mnemion ingest synchronously so memories land before compaction
if [ -n "$MNEMION_DIR" ] && [ -d "$MNEMION_DIR" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    REPO_DIR="$(dirname "$SCRIPT_DIR")"
    python3 -m mnemion mine "$MNEMION_DIR" >> "$STATE_DIR/hook.log" 2>&1
fi

# Always block — compaction = save everything
cat << 'HOOKJSON'
{
  "decision": "block",
  "reason": "COMPACTION IMMINENT. Save ALL topics, decisions, quotes, code, and important context from this session to your memory system. Be thorough — after compaction, detailed context will be lost. Organize into appropriate categories. Use verbatim quotes where possible. Save everything, then allow compaction to proceed."
}
HOOKJSON
