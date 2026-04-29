# Mnemion Multi-Agent Sync  -  Windows (PowerShell)
# ===================================================
# Exports the local Anaktoron to JSON, merges with remote if needed, commits,
# and pushes.  Safe for concurrent use by multiple agents on different machines.
#
# How it works:
#   1. Acquire a local lock file (prevents concurrent runs on the same machine)
#   2. Export local ChromaDB drawers -> archive/drawers_export.json
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
#   MNEMION_AGENT_ID    -  display name in commit messages (default: $env:COMPUTERNAME)
#   MNEMION_BRANCH      -  git branch to sync (default: auto-detected, fallback: main)
#   MNEMION_REPO_DIR    -  override repo dir (default: ~/.mnemion)
#   MNEMION_SOURCE_DIR  -  path to mnemion package (default: next to this script's parent)
#   MNEMION_SYNC_KG     -  set to 1/true/yes to also sync knowledge_graph.sql (can be very large)

param(
    [string]$MnemionDir    = "",
    [string]$MnemionSrc = "",
    [string]$AgentId = "",
    [string]$Branch = ""
)

# -- Configuration ------------------------------------------------------------

$AgentId   = if ($AgentId) { $AgentId } elseif ($env:MNEMION_AGENT_ID) { $env:MNEMION_AGENT_ID } else { $env:COMPUTERNAME }
$BranchOverride = if ($Branch) { $Branch } elseif ($env:MNEMION_BRANCH) { $env:MNEMION_BRANCH } else { "" }
$RepoDir   = if ($env:MNEMION_REPO_DIR)  { $env:MNEMION_REPO_DIR }  elseif ($MnemionDir) { $MnemionDir } else { "$env:USERPROFILE\.mnemion" }
$SrcDir    = if ($env:MNEMION_SOURCE_DIR){ $env:MNEMION_SOURCE_DIR } elseif ($MnemionSrc) { $MnemionSrc } else {
    # Auto-detect: this script lives in ~/.mnemion; the package is in the repo next to projects
    $candidate = Join-Path (Split-Path $PSScriptRoot -Parent) "mnemion"
    if (Test-Path $candidate) { Split-Path $PSScriptRoot -Parent } else { "" }
}

$MaxRetries  = 5
$ExportDir   = Join-Path $RepoDir "archive"
$ExportFile  = Join-Path $ExportDir "drawers_export.json"
$RemoteFile  = Join-Path $ExportDir ".drawers_remote_tmp.json"
$KgExportFile = Join-Path $ExportDir "knowledge_graph.sql"
$LockFile    = Join-Path $RepoDir ".sync_lock"
$SyncKnowledgeGraph = $env:MNEMION_SYNC_KG -in @("1", "true", "yes")

# Locate merge_exports.py: prefer source repo, fall back to same dir as this script
$MergeScript = ""
if ($SrcDir) {
    $candidate = Join-Path $SrcDir "sync\merge_exports.py"
    if (Test-Path $candidate) { $MergeScript = $candidate }
}
if (-not $MergeScript) {
    # Script dir: $PSScriptRoot when run by Task Scheduler, otherwise derive from MyInvocation
    $scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else {
        Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $candidate = Join-Path $scriptDir "merge_exports.py"
    if (Test-Path $candidate) { $MergeScript = $candidate }
}
if (-not $MergeScript) {
    # Final fallback: look in the repo dir itself
    $candidate = Join-Path $RepoDir "merge_exports.py"
    if (Test-Path $candidate) { $MergeScript = $candidate }
}

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Output "$ts [$AgentId] $msg"
}

# -- Lock ---------------------------------------------------------------------

# Stale lock: older than 10 minutes -> treat as abandoned
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

# -- Guard: ensure we are inside the git repo ---------------------------------

if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
    Write-Log "ERROR: $RepoDir is not a git repo. Run 'git init' there first."
    Release-Lock; exit 1
}

Set-Location $RepoDir
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
if (-not $SyncKnowledgeGraph -and (Test-Path $KgExportFile)) {
    Remove-Item $KgExportFile -Force
}

# -- Detect branch ------------------------------------------------------------

$Branch = if ($BranchOverride) { $BranchOverride } else {
    $b = git rev-parse --abbrev-ref HEAD 2>$null
    if ([string]::IsNullOrEmpty($b) -or $b -eq "HEAD") { "main" } else { $b }
}

# -- Export -------------------------------------------------------------------

$exportScript = @"
import sys, json
if r'$SrcDir':
    sys.path.insert(0, r'$SrcDir')
from mnemion.chroma_compat import make_persistent_client
from mnemion.config import MnemionConfig

BATCH = 2000  # stay under SQLite SQLITE_MAX_VARIABLE_NUMBER on any version

config = MnemionConfig()
try:
    client = make_persistent_client(config.anaktoron_path, vector_safe=True, collection_name=config.collection_name)
    col    = client.get_collection(config.collection_name)
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
    out = r'$ExportFile'.replace('\\\\', '/').replace('\\', '/')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(sorted(drawers, key=lambda d: d['id']), f, ensure_ascii=False, indent=2)
    print(f'{len(drawers)} drawers exported')
    
    sync_kg = r'$SyncKnowledgeGraph'.lower() == 'true'
    import sqlite3, os
    from pathlib import Path
    kg_path = Path(config.anaktoron_path).parent / 'knowledge_graph.sqlite3'
    if sync_kg and kg_path.exists():
        kg_out = r'$KgExportFile'.replace('\\\\', '/').replace('\\', '/')
        conn = sqlite3.connect(kg_path)
        with open(kg_out, 'w', encoding='utf-8') as f:
            for line in conn.iterdump():
                f.write(line + '\n')
        conn.close()
        print('Knowledge Graph / Trust data dumped')
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

# -- Sync loop -----------------------------------------------------------------

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

    # -- Fetch remote ----------------------------------------------------------
    git fetch origin 2>&1 | Out-Null

    # -- Merge if remote is ahead ----------------------------------------------
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
            Write-Log "Remote has no export yet  -  skipping merge"
            Remove-Item $RemoteFile -Force -ErrorAction SilentlyContinue
        }

        # Optional: sync the Trust & Knowledge Graph SQLite table.
        $KgRemoteFile = Join-Path $ExportDir ".kg_remote_tmp.sql"
        if ($SyncKnowledgeGraph) {
            git show "${remoteRef}:archive/knowledge_graph.sql" > $KgRemoteFile 2>&1
        }
        if ($SyncKnowledgeGraph -and $LASTEXITCODE -eq 0 -and (Test-Path $KgRemoteFile)) {
            Write-Log "Trust Graph Remote File Found. Merging SQL dumps natively..."
            $mergeKGSql = @"
import sqlite3, sys
from pathlib import Path
from mnemion.config import MnemionConfig

try:
    config = MnemionConfig()
    kg_path = Path(config.anaktoron_path).parent / 'knowledge_graph.sqlite3'
    if kg_path.exists():
        conn = sqlite3.connect(kg_path)
        with open(r'$KgRemoteFile'.replace('\\\\', '/').replace('\\', '/'), 'r', encoding='utf-8') as f:
            sql_script = f.read()
        sql_script = sql_script.replace('INSERT INTO', 'INSERT OR REPLACE INTO')
        conn.executescript(sql_script)
        conn.commit()
        conn.close()
except Exception as e:
    print(f'KG Merge exception: {e}')
"@
            py -c $mergeKGSql 2>&1 | Out-Null
            Remove-Item $KgRemoteFile -Force -ErrorAction SilentlyContinue
            
            # Re-dump the now successfully unified graph so it is staged 
            py -c "import sqlite3; from mnemion.config import MnemionConfig; from pathlib import Path; p=Path(MnemionConfig().anaktoron_path).parent/'knowledge_graph.sqlite3'; c=sqlite3.connect(p); f=open(r'$KgExportFile'.replace('\\\\','/'), 'w', encoding='utf-8'); [f.write(l+'\n') for l in c.iterdump()]; c.close()" 2>&1 | Out-Null
        }
    }

    # -- Stage only portable sync artifacts ------------------------------------
    $syncArtifacts = @(
        "archive/drawers_export.json",
        ".gitignore",
        "SyncMemories.ps1",
        "SyncMemories.sh",
        "merge_exports.py",
        "backfill_trust.py"
    )
    if ($SyncKnowledgeGraph) { $syncArtifacts += "archive/knowledge_graph.sql" }
    foreach ($artifact in $syncArtifacts) {
        if (Test-Path $artifact) {
            git add -- $artifact
        }
    }

    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Log "No changes to sync."
        Release-Lock; exit 0
    }

    # -- Commit ----------------------------------------------------------------
    $now     = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $drawerLine = ($exportResult | Select-String "\d+ drawers").Matches[0].Value
    git commit -m "sync: $now [$AgentId] $drawerLine" 2>&1 | Out-Null
    $committed = $true

    # -- Push ------------------------------------------------------------------
    # --force-with-lease: safe push  -  only succeeds if nobody pushed since our fetch
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
