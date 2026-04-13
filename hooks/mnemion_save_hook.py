#!/usr/bin/env python3
"""
Mnemion Auto-Save Hook — fires every N exchanges.
Extracts memories from the transcript WITHOUT AI cooperation,
saves them directly to ChromaDB, then triggers a git sync.

No blocking. No AI interruption. Fully automatic.
"""

import sys
import json
import os
import datetime
import subprocess
import hashlib

# ── Config ────────────────────────────────────────────────────────────────────
SAVE_INTERVAL = 3  # exchanges between auto-saves (was 15)
MNEMION_SRC = os.path.expanduser("~/projects/mnemion")
SYNC_SCRIPT = os.path.expanduser("~/.mnemion/SyncMemories.ps1")
STATE_DIR = os.path.expanduser("~/.mnemion/hook_state")
LOG_FILE = os.path.join(STATE_DIR, "hook.log")

os.makedirs(STATE_DIR, exist_ok=True)


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


# ── Transcript parsing ────────────────────────────────────────────────────────


def read_transcript(transcript_path):
    """Extract human-readable text from a Claude Code JSONL transcript."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    messages = []
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    msg = entry.get("message", {})
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "")
                    if role not in ("user", "assistant"):
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        text = " ".join(
                            b.get("text", "")
                            for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    elif isinstance(content, str):
                        text = content
                    else:
                        continue
                    # Skip command scaffolding noise
                    if not text.strip() or "<command-message>" in text:
                        continue
                    messages.append(f"{role.upper()}: {text.strip()}")
                except Exception:
                    pass
    except Exception as e:
        log(f"Transcript read error: {e}")
    return "\n\n".join(messages)


def count_user_exchanges(transcript_path):
    """Count user messages in transcript (for interval throttle)."""
    count = 0
    if not transcript_path or not os.path.exists(transcript_path):
        return 0
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    msg = entry.get("message", {})
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str) and "<command-message>" not in content:
                            count += 1
                        elif isinstance(content, list):
                            count += 1
                except Exception:
                    pass
    except Exception:
        pass
    return count


# ── Anaktoron save ───────────────────────────────────────────────────────────────


def save_to_anaktoron(memories, session_id):
    """Save extracted memories directly to ChromaDB. Returns count saved."""
    try:
        if MNEMION_SRC not in sys.path:
            sys.path.insert(0, MNEMION_SRC)
        import chromadb
        from mnemion.config import MempalaceConfig

        config = MempalaceConfig()
        client = chromadb.PersistentClient(path=config.anaktoron_path)
        collection = client.get_or_create_collection(config.collection_name)

        saved = 0
        for mem in memories:
            content = mem["content"]
            mem_type = mem["memory_type"]

            # Stable ID = content hash (dedup across runs)
            doc_id = "auto_" + hashlib.sha1(content.encode()).hexdigest()[:16]

            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                continue  # already stored

            collection.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[
                    {
                        "wing": "sessions",
                        "room": mem_type,  # decision / preference / milestone / problem / emotional
                        "source": f"hook:{session_id[:12]}",
                        "added_by": "auto_hook",
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
                ],
            )
            saved += 1

        return saved
    except Exception as e:
        log(f"Anaktoron save error: {e}")
        return 0


# ── Git sync ──────────────────────────────────────────────────────────────────


def trigger_git_sync():
    """Fire the sync script in the background — non-blocking."""
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            ["powershell", "-NonInteractive", "-WindowStyle", "Hidden", "-File", SYNC_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as e:
        log(f"Git sync trigger error: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

data = json.load(sys.stdin)
session_id = data.get("session_id", "unknown")
transcript_path = data.get("transcript_path", "")
stop_hook_active = data.get("stop_hook_active", False)

if stop_hook_active:
    print("{}")
    sys.exit(0)

# ── Throttle: only run every SAVE_INTERVAL exchanges ─────────────────────────
exchange_count = count_user_exchanges(transcript_path)

last_save_file = os.path.join(STATE_DIR, f"{session_id}_last_save")
last_save = 0
if os.path.exists(last_save_file):
    try:
        with open(last_save_file) as f:
            last_save = int(f.read().strip() or 0)
    except Exception:
        pass

since_last = exchange_count - last_save

if since_last < SAVE_INTERVAL or exchange_count == 0:
    print("{}")
    sys.exit(0)

# ── Extract + save ────────────────────────────────────────────────────────────
with open(last_save_file, "w") as f:
    f.write(str(exchange_count))

try:
    if MNEMION_SRC not in sys.path:
        sys.path.insert(0, MNEMION_SRC)
    from mnemion.general_extractor import extract_memories

    text = read_transcript(transcript_path)
    if text:
        memories = extract_memories(text, min_confidence=0.4)
        if memories:
            saved = save_to_anaktoron(memories, session_id)
            log(
                f"Session {session_id[:8]}: {exchange_count} exchanges | "
                f"extracted {len(memories)} memories | saved {saved} new | "
                f"types: {set(m['memory_type'] for m in memories)}"
            )
            trigger_git_sync()
        else:
            log(
                f"Session {session_id[:8]}: {exchange_count} exchanges | no memories matched patterns"
            )
    else:
        log(f"Session {session_id[:8]}: no transcript content")
except Exception as e:
    log(f"Hook error: {e}")
    import traceback

    log(traceback.format_exc())

# Never block — always let the conversation continue
print("{}")
