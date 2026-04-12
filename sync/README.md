# Mnemion Sync — Multi-Agent Palace Backup & Sync

The palace (ChromaDB vector store) is too large for git (~860 MB). The sync
system exports a portable JSON snapshot and commits that instead.  Multiple
agents on different machines can each run the sync script and share the same
memory automatically — no human coordination needed.

---

## How It Works

Every hour (or on your schedule):

1. **Export** — all non-session drawers are exported from the local ChromaDB
   palace → `archive/drawers_export.json` (stable-sorted, human-readable JSON)
2. **Fetch** — `git fetch` peeks at the remote without touching your working tree
3. **Merge** — if the remote is ahead (another agent pushed), `merge_exports.py`
   produces a clean union of both export files:
   - All drawers from both sides are kept
   - When the same drawer ID exists in both: the one with the newer `filed_at`
     timestamp wins; remote wins on tie
4. **Commit** — the merged (or unchanged) export is committed with the agent ID
   and drawer count in the message
5. **Push** — `git push --force-with-lease`; if rejected (another agent pushed
   between step 2 and step 5), the commit is rolled back, the script waits a
   random 2–9 seconds, then retries from step 2 — up to 5 times

The lock file (`~/.mnemion/.sync_lock`) prevents two concurrent runs on the
same machine.  Stale locks (> 10 minutes old) are cleaned up automatically.

### Commit messages are traceable

```
sync: 2026-04-13 14:32:10 [openclaw-prod] 1582 drawers
sync: 2026-04-13 14:35:01 [jorqu-windows] 1596 drawers
```

Set `MNEMION_AGENT_ID` to a meaningful name for each machine/agent.

### Known limitation — v1

Drawer **deletions** do not propagate.  A drawer deleted from one agent's palace
will be re-added after the next merge from another agent that still has it.
Deletion sync requires tombstone records and is planned for a future version.

---

## Quick Start

### One-Shot Windows Install

```powershell
powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1
```

Installs everything: hooks, hourly sync task, vLLM auto-start, trust backfill.
Skip optional parts: `install_windows.ps1 -SkipVllm` / `-SkipHook`

---

## Manual Setup

### 1. Initialize the memory git repo (once per machine)

```powershell
# Windows
cd $env:USERPROFILE\.mnemion
git init
git remote add origin https://github.com/YOUR_USERNAME/personal-ai-memories.git
```

```bash
# Linux / macOS
cd ~/.mnemion
git init
git remote add origin https://github.com/YOUR_USERNAME/personal-ai-memories.git
```

### 2. Copy the sync script and set your agent ID

**Windows:**
```powershell
Copy-Item sync\SyncMemories.ps1 $env:USERPROFILE\.mnemion\SyncMemories.ps1
$env:MNEMION_AGENT_ID = "my-machine-name"   # put this in your profile
```

**Linux / macOS:**
```bash
cp sync/SyncMemories.sh ~/.mnemion/SyncMemories.sh
chmod +x ~/.mnemion/SyncMemories.sh
export MNEMION_AGENT_ID="openclaw-prod"   # put this in ~/.bashrc or ~/.zshrc
```

### 3. Schedule the sync

**Windows — Task Scheduler (run as Administrator):**
```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -File $env:USERPROFILE\.mnemion\SyncMemories.ps1"
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At (Get-Date)
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName "MnemionMemorySync" `
    -Action $action -Trigger $trigger -Settings $settings `
    -RunLevel Highest -Force
```

**Linux / macOS — cron:**
```bash
# Every hour at :00
(crontab -l 2>/dev/null; echo "0 * * * * MNEMION_AGENT_ID=openclaw-prod ~/.mnemion/SyncMemories.sh >> ~/.mnemion/sync.log 2>&1") | crontab -
```

### 4. Verify

**Windows:**
```powershell
# Run once manually to confirm
powershell -File $env:USERPROFILE\.mnemion\SyncMemories.ps1
```

**Linux / macOS:**
```bash
~/.mnemion/SyncMemories.sh
```

You should see output like:
```
2026-04-13 14:32:10 [my-agent] Export: 1582 drawers exported
2026-04-13 14:32:14 [my-agent] Pushed OK (attempt 1). Branch: main
```

---

## Environment Variables

| Variable               | Default              | Description                                  |
|------------------------|----------------------|----------------------------------------------|
| `MNEMION_AGENT_ID`     | hostname             | Name shown in commit messages                |
| `MNEMION_BRANCH`       | auto-detected        | Git branch to push to                        |
| `MNEMION_REPO_DIR`     | `~/.mnemion`         | Path to the memory git repo                  |
| `MNEMION_SOURCE_DIR`   | auto-detected        | Path to the mnemion package (for imports)    |
| `MNEMION_PYTHON`       | `python3`            | Python binary (Linux/Mac only)               |

---

## Restoring on a New Machine

```bash
# 1. Clone your memory repo
git clone https://github.com/YOUR_USERNAME/personal-ai-memories.git ~/.mnemion

# 2. Rebuild the palace from the JSON export
cd ~/.mnemion
python3 -m mnemion mine archive/drawers_export.json

# 3. Backfill trust records for all restored drawers
python3 ~/.mnemion/backfill_trust.py
```

---

## .gitignore

`~/.mnemion/.gitignore` should contain:

```gitignore
palace/
cursor_scraped/
hook_state/
*.sqlite3
*.sqlite3-wal
*.sqlite3-shm
*.log
.sync_lock
.drawers_remote_tmp.json
!SyncMemories.ps1
!SyncMemories.sh
```

The ChromaDB binary files and SQLite databases never go to git.
Only the portable JSON export and the sync scripts travel.

---

## Merge Logic (`sync/merge_exports.py`)

The merge script produces a clean union without git merge markers:

```
local export  ──┐
                ├─► merge_exports.py ──► merged export
remote export ──┘
```

- **ID only in local** → kept
- **ID only in remote** → kept
- **ID in both** → newer `filed_at` timestamp wins; remote wins on tie
- Output is sorted by drawer ID (stable, diffable)

You can run it manually:
```bash
python3 sync/merge_exports.py \
    --ours   ~/.mnemion/archive/drawers_export.json \
    --theirs /tmp/remote_export.json \
    --out    ~/.mnemion/archive/drawers_export.json
```
