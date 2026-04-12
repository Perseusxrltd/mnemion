# Mnemion Multi-Agent Sync — Windows (PowerShell)
# ===================================================
# Exports the local palace to JSON, merges with remote if needed, commits,
# and pushes.  Safe for concurrent use by multiple agents on different machines.
#
# How it works:
#   1. Acquire a local lock file (prevents concurrent runs on the same machine)
#   2. Export local ChromaDB drawers → archive/drawers_export.json
#   3. git fetch (non-destructive peek at remote state)
#   4. If remote is ahead: merge remote export into local using merge_exports.py
#   5. git add + commit (with agent identity in message)
#   6. git push --force-with-lease
#      On rejection (another agent pushed between step 3 and 6): undo commit,
#      sleep jitter, retry up to $MaxRetries times
#   7. Release lock
#
# Setup:
#   Copy to ~/.mnemion/SyncMemories.ps1 and schedule hourly (see sync/README.md).
#
# Environment variables:
#   MNEMION_AGENT_ID   — display name in commit messages (default: $env:COMPUTERNAME)
#   MNEMION_BRANCH     — git branch to sync (default: auto-detected, fallback: main)
#   MNEMION_REPO_DIR   — override repo dir (default: ~/.mnemion)
#   MNEMION_SOURCE_DIR — path to mnemion package (default: next to this script's parent)

param(
    [string]$MempalDir    = "",
    [string]$MempalaceSrc = ""
)

# ── Configuration ────────────────────────────────────────────────────────────

$AgentId   = if ($env:MNEMION_AGENT_ID)  { $env:MNEMION_AGENT_ID }  else { $env:COMPUTERNAME }
$RepoDir   = if ($env:MNEMION_REPO_DIR)  { $env:MNEMION_REPO_DIR }  elseif ($MempalDir) { $MempalDir } else { "$env:USERPROFILE\.mnemion" }
$SrcDir    = if ($env:MNEMION_SOURCE_DIR){ $env:MNEMION_SOURCE_DIR } elseif ($MempalaceSrc) { $MempalaceSrc } else {
    # Auto-detect: this script lives in ~/.mnemion; the package is in the repo next to projects
    $candidate = Join-Path (Split-Path $PSScriptRoot -Parent) "mnemion"
    if (Test-Path $candidate) { Split-Path $PSScriptRoot -Parent } else { "" }
}

$MaxRetries  = 5
$ExportDir   = Join-Path $RepoDir "archive"
$ExportFile  = Join-Path $ExportDir "drawers_export.json"
$RemoteFile  = Join-Path $ExportDir ".drawers_remote_tmp.json"
$LockFile    = Join-Path $RepoDir ".sync_lock"
$MergeScript = Join-Path $SrcDir "sync\merge_exports.py"

# Fallback: merge script next to this file
if (-not (Test-Path $MergeScript)) {
    $MergeScript = Join-Path $PSScriptRoot "merge_exports.py"
}

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Output "$ts [$AgentId] $msg"
}

# ── Lock ─────────────────────────────────────────────────────────────────────

# Stale lock: older than 10 minutes → treat as abandoned
if (Test-Path $LockFile) {
    $lockAge = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($lockAge.TotalMinutes -gt 10) {
        Write-Log "Stale lock removed (age: $([int]$lockAge.TotalMinutes)m)"
        Remove-Item $LockFile -Force
    } else {
        Write-Log "Another sync is running (lock age: $([int]$lockAge.TotalSeconds)s). Exiting."
        exit 0
    }
}
"$AgentId $(Get-Date -Format 'o')" | Out-File -FilePath $LockFile -Encoding utf8

function Release-Lock { if (Test-Path $LockFile) { Remove-Item $LockFile -Force } }

# ── Guard: ensure we are inside the git repo ─────────────────────────────────

if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
    Write-Log "ERROR: $RepoDir is not a git repo. Run 'git init' there first."
    Release-Lock; exit 1
}

Set-Location $RepoDir
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null

# ── Detect branch ────────────────────────────────────────────────────────────

$Branch = if ($env:MNEMION_BRANCH) { $env:MNEMION_BRANCH } else {
    $b = git rev-parse --abbrev-ref HEAD 2>$null
    if ([string]::IsNullOrEmpty($b) -or $b -eq "HEAD") { "main" } else { $b }
}

# ── Export ───────────────────────────────────────────────────────────────────

$exportScript = @"
import sys, json, os
if r'$SrcDir':
    sys.path.insert(0, r'$SrcDir')
import chromadb
from mnemion.chroma_compat import fix_blob_seq_ids
from mnemion.config import MempalaceConfig

config = MempalaceConfig()
fix_blob_seq_ids(config.palace_path)
try:
    client = chromadb.PersistentClient(path=config.palace_path)
    col    = client.get_collection(config.collection_name)
    all_data = col.get(include=['documents', 'metadatas'], limit=100000)
    drawers = []
    for id_, doc, meta in zip(all_data['ids'], all_data['documents'], all_data['metadatas']):
        wing = (meta or {}).get('wing', '')
        if wing == 'sessions' and (meta or {}).get('added_by') != 'auto_hook':
            continue
        drawers.append({'id': id_, 'content': doc, 'meta': meta})
    out = r'$ExportFile'.replace('\\\\', '/').replace('\\', '/')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(sorted(drawers, key=lambda d: d['id']), f, ensure_ascii=False, indent=2)
    print(f'{len(drawers)} drawers exported')
except Exception as e:
    print(f'Export error: {e}', file=sys.stderr)
    sys.exit(1)
"@

$exportResult = py -c $exportScript 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Log "Export failed: $exportResult"
    Release-Lock; exit 1
}
Write-Log "Export: $exportResult"

# ── Sync loop ─────────────────────────────────────────────────────────────────

$committed = $false

for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
    if ($attempt -gt 1) {
        Write-Log "Retry $attempt/$MaxRetries..."
    }

    # Undo previous attempt's commit before re-merging
    if ($committed) {
        $commitCount = [int](git rev-list --count HEAD 2>$null)
        if ($commitCount -gt 1) {
            git reset HEAD~1 --soft 2>&1 | Out-Null
        } else {
            # Undo the very first commit in the repo
            git update-ref -d HEAD 2>&1 | Out-Null
        }
        $committed = $false
        $jitter = Get-Random -Minimum 2 -Maximum 9
        Write-Log "Push rejected. Waiting ${jitter}s before retry..."
        Start-Sleep -Seconds $jitter
    }

    # ── Fetch remote ──────────────────────────────────────────────────────────
    git fetch origin 2>&1 | Out-Null

    # ── Merge if remote is ahead ──────────────────────────────────────────────
    $remoteRef = "origin/$Branch"
    $localRef  = "HEAD"
    $remoteAhead = 0
    try {
        $remoteAhead = [int](git rev-list "${localRef}..${remoteRef}" --count 2>$null)
    } catch { $remoteAhead = 0 }

    if ($remoteAhead -gt 0) {
        Write-Log "Remote is $remoteAhead commit(s) ahead. Merging exports..."
        # Extract remote export without touching the working tree
        git show "${remoteRef}:archive/drawers_export.json" > $RemoteFile 2>&1
        if ($LASTEXITCODE -eq 0 -and (Test-Path $RemoteFile)) {
            $mergeResult = py $MergeScript --ours $ExportFile --theirs $RemoteFile --out $ExportFile 2>&1
            Write-Log $mergeResult
            Remove-Item $RemoteFile -Force -ErrorAction SilentlyContinue
        } else {
            Write-Log "Remote has no export yet — skipping merge"
            Remove-Item $RemoteFile -Force -ErrorAction SilentlyContinue
        }
    }

    # ── Stage ─────────────────────────────────────────────────────────────────
    git add .

    $staged = (git status --porcelain).Trim()
    if ([string]::IsNullOrEmpty($staged)) {
        Write-Log "No changes to sync."
        Release-Lock; exit 0
    }

    # ── Commit ────────────────────────────────────────────────────────────────
    $now     = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $drawerLine = ($exportResult | Select-String "\d+ drawers").Matches[0].Value
    git commit -m "sync: $now [$AgentId] $drawerLine" 2>&1 | Out-Null
    $committed = $true

    # ── Push ──────────────────────────────────────────────────────────────────
    # --force-with-lease: safe push — only succeeds if nobody pushed since our fetch
    $pushOut = git push origin $Branch --force-with-lease 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Pushed OK (attempt $attempt). Branch: $Branch"
        $committed = $false
        break
    }

    Write-Log "Push failed: $pushOut"

    if ($attempt -ge $MaxRetries) {
        Write-Log "ERROR: Push failed after $MaxRetries attempts. Manual intervention needed."
        # Leave committed state so the user can inspect and push manually
        Release-Lock; exit 1
    }
}

if ($committed) {
    Write-Log "WARNING: Exited loop with uncommitted state. Check manually."
}

Release-Lock
