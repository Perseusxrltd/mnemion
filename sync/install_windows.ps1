#Requires -Version 5.1
<#
.SYNOPSIS
    Mnemion one-shot setup for Windows.

.DESCRIPTION
    Sets up the full Mnemion stack:
      1. Creates ~/.mnemion directory structure
      2. Installs the Python auto-save hook into Claude Code
      3. Schedules hourly palace sync (SyncMemories.ps1)
      4. Optionally registers vLLM auto-start on login
      5. Runs trust backfill if a palace already exists

    Safe to re-run -- all steps are idempotent.

.PARAMETER MempalaceSrc
    Path to this repo. Auto-detected from script location.

.PARAMETER SkipVllm
    Skip the vLLM Task Scheduler setup.

.PARAMETER SkipHook
    Skip Claude Code hook installation.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1
    powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1 -SkipVllm
#>

param(
    [string]$MempalaceSrc = "",
    [switch]$SkipVllm,
    [switch]$SkipHook
)

$ErrorActionPreference = "Stop"

# Locate repo root from this script's path
$SyncDir = Split-Path $PSScriptRoot -Parent
if ([string]::IsNullOrEmpty($SyncDir)) { $SyncDir = $PSScriptRoot }
$RepoRoot = $SyncDir

# Override if param passed
if ($MempalaceSrc -ne "") { $RepoRoot = $MempalaceSrc }

# Fallback: walk up from script looking for mcp_server.py
if (-not (Test-Path "$RepoRoot\mnemion\mcp_server.py")) {
    $check = Split-Path $PSScriptRoot -Parent
    if (Test-Path "$check\mnemion\mcp_server.py") { $RepoRoot = $check }
}

$MempalDir     = "$env:USERPROFILE\.mnemion"
$ClaudeSettings = "$env:USERPROFILE\.claude\settings.local.json"
$WslUser       = $env:USERNAME

function Write-Step([string]$msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "   OK   $msg" -ForegroundColor Green }
function Write-Skip([string]$msg) { Write-Host "   --   $msg" -ForegroundColor DarkGray }
function Write-Warn([string]$msg) { Write-Host "   WARN $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "Mnemion Windows Setup" -ForegroundColor White
Write-Host "-----------------------" -ForegroundColor White
Write-Host "Repo:   $RepoRoot"
Write-Host "Palace: $MempalDir"
Write-Host ""

# ---------------------------------------------------------------------------
# Step 1: Directory structure
# ---------------------------------------------------------------------------
Write-Step "Creating ~/.mnemion directory structure"

foreach ($dir in @($MempalDir, "$MempalDir\hooks", "$MempalDir\archive", "$MempalDir\hook_state")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Ok "Created $dir"
    } else {
        Write-Ok "Exists  $dir"
    }
}

# Copy SyncMemories.ps1
$syncSrc = "$RepoRoot\sync\SyncMemories.ps1"
$syncDst = "$MempalDir\SyncMemories.ps1"
if (Test-Path $syncSrc) {
    Copy-Item $syncSrc $syncDst -Force
    Write-Ok "Copied SyncMemories.ps1"
} else {
    Write-Warn "SyncMemories.ps1 not found at $syncSrc"
}

# Copy Python save hook
$hookSrc = "$RepoRoot\hooks\mnemion_save_hook.py"
$hookDst = "$MempalDir\hooks\mnemion_save_hook.py"
if (Test-Path $hookSrc) {
    Copy-Item $hookSrc $hookDst -Force
    Write-Ok "Copied mnemion_save_hook.py"
} else {
    Write-Warn "mnemion_save_hook.py not found at $hookSrc"
}

# Copy backfill script
$backfillSrc = "$RepoRoot\sync\backfill_trust.py"
$backfillDst = "$MempalDir\backfill_trust.py"
if (Test-Path $backfillSrc) {
    Copy-Item $backfillSrc $backfillDst -Force
    Write-Ok "Copied backfill_trust.py"
}

# Copy run_vllm.sh to WSL via Python (avoids bash PATH issues)
$vllmSrc = "$RepoRoot\sync\run_vllm.sh"
if ((Test-Path $vllmSrc) -and (-not $SkipVllm)) {
    $wslMntPath = "/mnt/c/Users/$WslUser/projects/mnemion/sync/run_vllm.sh"
    # Try to find the actual Windows mount path
    $winRelPath = $vllmSrc -replace [regex]::Escape("C:\"), "/mnt/c/" -replace "\\", "/"
    $pyCmd = "import shutil,os; shutil.copy('$winRelPath','/home/$WslUser/run_vllm.sh'); os.chmod('/home/$WslUser/run_vllm.sh',0o755); print('ok')"
    try {
        $res = wsl -d Ubuntu python3 -c $pyCmd 2>&1
        if ($res -match "ok") {
            Write-Ok "Copied run_vllm.sh to WSL /home/$WslUser/"
        } else {
            Write-Warn "WSL copy result: $res"
        }
    } catch {
        Write-Warn "Could not copy run_vllm.sh to WSL: $_"
    }
}

# ---------------------------------------------------------------------------
# Step 2: Claude Code auto-save hook
# ---------------------------------------------------------------------------
Write-Step "Installing Claude Code auto-save hook"

if ($SkipHook) {
    Write-Skip "Claude Code hook (-SkipHook passed)"
} else {
    $hookCmd = "python3 `"$MempalDir\hooks\mnemion_save_hook.py`""

    $claudeDir = Split-Path $ClaudeSettings -Parent
    if (-not (Test-Path $claudeDir)) {
        New-Item -ItemType Directory $claudeDir -Force | Out-Null
    }

    $settings = @{}
    if (Test-Path $ClaudeSettings) {
        try {
            $raw = Get-Content $ClaudeSettings -Raw -Encoding UTF8
            $settings = $raw | ConvertFrom-Json -AsHashtable
        } catch {
            $settings = @{}
        }
    }

    if (-not $settings.ContainsKey("hooks")) { $settings["hooks"] = @{} }
    if (-not $settings["hooks"].ContainsKey("Stop")) { $settings["hooks"]["Stop"] = @() }

    $alreadyIn = $settings["hooks"]["Stop"] | Where-Object {
        $_.hooks | Where-Object { $_.command -like "*mnemion_save_hook*" }
    }

    if ($alreadyIn) {
        Write-Ok "Hook already present in $ClaudeSettings"
    } else {
        $newEntry = @{
            matcher = "*"
            hooks   = @(@{ type = "command"; command = $hookCmd; timeout = 15 })
        }
        $settings["hooks"]["Stop"] += $newEntry
        $settings | ConvertTo-Json -Depth 10 | Set-Content $ClaudeSettings -Encoding UTF8
        Write-Ok "Hook installed in $ClaudeSettings"
        Write-Warn "Restart Claude Code for the hook to take effect"
    }
}

# ---------------------------------------------------------------------------
# Step 3: Task Scheduler -- hourly sync
# ---------------------------------------------------------------------------
Write-Step "Registering hourly palace sync task"

try {
    if (Get-ScheduledTask -TaskName "MnemionSync" -ErrorAction SilentlyContinue) {
        Write-Ok "Task 'MnemionSync' already registered"
    } else {
        $action = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$MempalDir\SyncMemories.ps1`""
        $trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At (Get-Date)
        $ts = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
            -StartWhenAvailable -RunOnlyIfNetworkAvailable
        Register-ScheduledTask -TaskName "MnemionSync" `
            -Action $action -Trigger $trigger -Settings $ts -RunLevel Highest -Force | Out-Null
        Write-Ok "Task 'MnemionSync' registered (runs every hour)"
    }
} catch {
    Write-Warn "Task Scheduler requires Administrator -- re-run: Start-Process powershell -Verb RunAs"
    Write-Warn "Or manually: Task Scheduler > Create Task > Action: powershell.exe -File `"$MempalDir\SyncMemories.ps1`""
}

# ---------------------------------------------------------------------------
# Step 4: Task Scheduler -- vLLM at login
# ---------------------------------------------------------------------------
Write-Step "Registering vLLM startup task"

if ($SkipVllm) {
    Write-Skip "vLLM task (-SkipVllm passed)"
} else {
    try {
        if (Get-ScheduledTask -TaskName "MnemionVLLM" -ErrorAction SilentlyContinue) {
            Write-Ok "Task 'MnemionVLLM' already registered"
        } else {
            # Use Python in WSL to spawn bash -- avoids the broken PATH problem entirely
            $pyLaunch = "import subprocess; subprocess.Popen(['/bin/bash','/home/$WslUser/run_vllm.sh'],stdout=open('/home/$WslUser/vllm.log','w'),stderr=subprocess.STDOUT,start_new_session=True)"
            $action = New-ScheduledTaskAction -Execute "wsl.exe" `
                -Argument "-d Ubuntu python3 -c `"$pyLaunch`""
            $trigger = New-ScheduledTaskTrigger -AtLogOn
            $ts = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -StartWhenAvailable
            Register-ScheduledTask -TaskName "MnemionVLLM" `
                -Action $action -Trigger $trigger -Settings $ts -RunLevel Highest -Force | Out-Null
            Write-Ok "Task 'MnemionVLLM' registered (starts vLLM at each login)"
        }
    } catch {
        Write-Warn "Could not register vLLM task (run as Administrator to fix): $_"
    }
}

# ---------------------------------------------------------------------------
# Step 5: Trust backfill (if palace exists)
# ---------------------------------------------------------------------------
Write-Step "Checking for existing palace"

$palaceDb = "$MempalDir\palace\chroma.sqlite3"
if (-not (Test-Path $palaceDb)) {
    Write-Skip "No palace at $palaceDb -- backfill skipped (run after mnemion mine)"
} elseif (Test-Path $backfillDst) {
    Write-Host "   Running trust backfill..." -ForegroundColor DarkCyan
    $out = py $backfillDst 2>&1
    $summary = $out | Select-String "Done\.|trust stats" | ForEach-Object { $_.Line }
    if ($summary) { $summary | ForEach-Object { Write-Ok $_ } }
    else { Write-Ok "Backfill complete" }
} else {
    Write-Warn "backfill_trust.py not found -- run manually: py $backfillDst"
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "-------------------------------------------" -ForegroundColor White
Write-Host "  Mnemion setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:"
Write-Host "    1. Restart Claude Code  (hook takes effect)"
Write-Host "    2. claude mcp add mnemion -- python -m mnemion.mcp_server"
Write-Host "    3. Call mnemion_status in your first conversation"
if (-not $SkipVllm) {
    Write-Host "    4. Log out/in to trigger vLLM auto-start (or run the task manually)"
    Write-Host "       Then check: wsl -d Ubuntu tail /home/$WslUser/vllm.log"
}
Write-Host "-------------------------------------------" -ForegroundColor White
