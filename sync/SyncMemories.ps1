# Mnemion Auto-Sync Script
# Exports drawer content as portable JSON, then git commits + pushes.
# Run on a schedule (Task Scheduler) — recommended: every 1 hour.
#
# Setup:
#   1. Copy this file to your ~/.mnemion/ directory
#   2. Edit $mempalDir and $repoDir below
#   3. Schedule via Task Scheduler (see sync/README.md)
#
# On a new machine: git clone <repo> → py -m mnemion mine ./archive/drawers_export.json

param(
    [string]$MempalDir = "$env:USERPROFILE\.mnemion",
    [string]$MempalaceSrc = "$env:USERPROFILE\projects\mnemion"
)

$exportDir  = Join-Path $MempalDir "archive"
$exportFile = Join-Path $exportDir "drawers_export.json"
$readmePath = Join-Path $MempalDir "README.md"

Set-Location $MempalDir
New-Item -ItemType Directory -Force -Path $exportDir | Out-Null

# ── Step 1: Export drawable content as plain JSON (portable, rebuildable) ────
# Exports only non-sessions wings (distilled knowledge, not raw logs).
# Skip raw session dumps — they're noise, not memory.
$exportScript = @"
import sys, json, os
sys.path.insert(0, r'$MempalaceSrc')
import chromadb
from mnemion.config import MempalaceConfig

config = MempalaceConfig()
try:
    client = chromadb.PersistentClient(path=config.palace_path)
    col = client.get_collection(config.collection_name)
    all_data = col.get(include=['documents', 'metadatas'], limit=100000)

    drawers = []
    for id_, doc, meta in zip(all_data['ids'], all_data['documents'], all_data['metadatas']):
        wing = (meta or {}).get('wing', '')
        # Skip raw session dumps
        if wing == 'sessions' and (meta or {}).get('added_by') != 'auto_hook':
            continue
        drawers.append({'id': id_, 'content': doc, 'meta': meta})

    export_path = r'$exportFile'.replace('\\\\', '/').replace('\\', '/')
    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(drawers, f, ensure_ascii=False, indent=2)
    print(f'Exported {len(drawers)} drawers')
except Exception as e:
    print(f'Export error: {e}')
    sys.exit(0)
"@

$exportResult = py -c $exportScript 2>&1
Write-Output "Export: $exportResult"

# ── Step 2: Git commit + push if anything changed ─────────────────────────────
$status = git status --porcelain
if ($status) {
    $now = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    # Append to README log
    "`n*   **$now**: Auto-sync. $exportResult" | Out-File -FilePath $readmePath -Append -Encoding utf8

    git add .
    git commit -m "Auto-sync memory palace: $now"

    $pushResult = git push origin master 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Output "$now - Pushed OK."
    } else {
        Write-Output "$now - Push failed: $pushResult"
    }
} else {
    Write-Output "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - No changes to sync."
}
