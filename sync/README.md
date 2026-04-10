# Mnemion Sync & Setup

## One-Shot Windows Install

```powershell
powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1
```

This installs everything: hooks, hourly sync task, vLLM auto-start, trust backfill. Safe to re-run.

Skip vLLM setup: `install_windows.ps1 -SkipVllm`
Skip hook setup: `install_windows.ps1 -SkipHook`

---

# Auto-Sync — Palace Backup & Portability

The palace (ChromaDB vector store) is too large for git (~860MB). The sync system exports a portable JSON snapshot and commits that instead. On a new machine, one command rebuilds the full palace from the snapshot.

---

## What It Does

Every hour (or on your schedule):

1. **Exports** all non-session drawers from ChromaDB → `archive/drawers_export.json`
2. **Commits** the JSON export to your memory git repo
3. **Pushes** to GitHub (or any remote)

The SQLite-heavy files (`*.sqlite3`, `palace/`) are in `.gitignore`. Only the portable JSON travels.

---

## Setup (Windows — Task Scheduler)

### 1. Copy the sync script

```powershell
Copy-Item sync/SyncMemories.ps1 $env:USERPROFILE\.mnemion\SyncMemories.ps1
```

### 2. Initialize your memory git repo

```powershell
cd $env:USERPROFILE\.mnemion
git init
git remote add origin https://github.com/YOUR_USERNAME/personal-ai-memories.git
```

### 3. Create the Task Scheduler task

Open PowerShell as Administrator:

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -File $env:USERPROFILE\.mnemion\SyncMemories.ps1"
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At (Get-Date)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName "MnemionMemorySync" -Action $action `
    -Trigger $trigger -Settings $settings -RunLevel Highest -Force
```

### 4. Verify

```powershell
Start-ScheduledTask -TaskName "MnemionMemorySync"
cat $env:USERPROFILE\.mnemion\archive\drawers_export.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} drawers exported')"
```

---

## Setup (macOS / Linux — cron)

```bash
# Copy script
cp sync/SyncMemories.sh ~/.mnemion/SyncMemories.sh
chmod +x ~/.mnemion/SyncMemories.sh

# Add to crontab (every hour)
(crontab -l 2>/dev/null; echo "0 * * * * ~/.mnemion/SyncMemories.sh >> ~/.mnemion/sync.log 2>&1") | crontab -
```

---

## Restoring on a New Machine

```bash
# 1. Clone your memory repo
git clone https://github.com/YOUR_USERNAME/personal-ai-memories.git ~/.mnemion

# 2. Rebuild the palace from the JSON export
cd ~/.mnemion
py -m mnemion mine archive/drawers_export.json

# 3. Backfill trust records for all restored drawers
py ~/.mnemion/backfill_trust.py
```

That's it. The full palace is rebuilt from the exported JSON.

---

## .gitignore

The `~/.mnemion/.gitignore` should contain:

```gitignore
palace/
cursor_scraped/
hook_state/
*.sqlite3
*.sqlite3-wal
*.sqlite3-shm
*.log
!SyncMemories.ps1
```

This ensures the ChromaDB binary files never go to git, but the sync script and archive JSON do.
