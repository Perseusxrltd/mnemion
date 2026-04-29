#Requires -Version 5.1
<#
.SYNOPSIS
    Mnemion one-shot setup for Windows.

.DESCRIPTION
    Sets up the full Mnemion stack:
      1. Creates ~/.mnemion directory structure
      2. Installs the Python auto-save hook into Claude Code
      3. Schedules hourly Anaktoron sync (SyncMemories.ps1)
      4. Optionally registers vLLM auto-start on login
      5. Runs trust backfill if a Anaktoron already exists

    Safe to re-run -- all steps are idempotent.

.PARAMETER MnemionSrc
    Path to this repo. Auto-detected from script location.

.PARAMETER MnemionDir
    Path to the private memory git repo. Defaults to ~/.mnemion.

.PARAMETER MemoryRepoUrl
    Optional git remote URL for the private memory repo.

.PARAMETER MemoryBranch
    Optional git branch to use for memory sync.

.PARAMETER AgentId
    Optional display name stamped into sync commit messages.

.PARAMETER SyncTaskName
    Windows Task Scheduler task name for hourly sync.

.PARAMETER SyncIntervalHours
    Number of hours between scheduled sync runs.

.PARAMETER SkipSync
    Skip git repo setup and Task Scheduler sync registration.

.PARAMETER SkipVllm
    Skip the vLLM Task Scheduler setup.

.PARAMETER SkipHook
    Skip Claude Code hook installation.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1
    powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1 -MemoryRepoUrl https://github.com/OWNER/PRIVATE-MEMORY-REPO.git -AgentId laptop
    powershell -ExecutionPolicy Bypass -File sync\install_windows.ps1 -SkipVllm -SkipSync
#>

param(
    [string]$MnemionSrc = "",
    [string]$MnemionDir = "",
    [string]$MemoryRepoUrl = "",
    [string]$MemoryBranch = "",
    [string]$AgentId = "",
    [string]$SyncTaskName = "MnemionSync",
    [int]$SyncIntervalHours = 1,
    [switch]$SkipSync,
    [switch]$SkipVllm,
    [switch]$SkipHook
)

$ErrorActionPreference = "Stop"

# Locate repo root from this script's path
$SyncDir = Split-Path $PSScriptRoot -Parent
if ([string]::IsNullOrEmpty($SyncDir)) { $SyncDir = $PSScriptRoot }
$RepoRoot = $SyncDir

# Override if param passed
if ($MnemionSrc -ne "") { $RepoRoot = $MnemionSrc }

# Fallback: walk up from script looking for mcp_server.py
if (-not (Test-Path "$RepoRoot\mnemion\mcp_server.py")) {
    $check = Split-Path $PSScriptRoot -Parent
    if (Test-Path "$check\mnemion\mcp_server.py") { $RepoRoot = $check }
}

if ([string]::IsNullOrWhiteSpace($MnemionDir)) {
    $MnemionDir = "$env:USERPROFILE\.mnemion"
}
$ClaudeSettings = "$env:USERPROFILE\.claude\settings.local.json"
$WslUser       = $env:USERNAME

function Write-Step([string]$msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "   OK   $msg" -ForegroundColor Green }
function Write-Skip([string]$msg) { Write-Host "   --   $msg" -ForegroundColor DarkGray }
function Write-Warn([string]$msg) { Write-Host "   WARN $msg" -ForegroundColor Yellow }

function Remove-LegacySyncTasks {
    try {
        $legacyTasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
            ($_.Actions | Where-Object {
                $_.Execute -like "*powershell*" -and $_.Arguments -like "*.mempalace*SyncMemories.ps1*"
            })
        }
        foreach ($task in $legacyTasks) {
            Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Confirm:$false
            Write-Ok "Removed legacy sync task '$($task.TaskName)'"
        }
    } catch {
        Write-Warn "Could not remove legacy sync task(s): $_"
    }
}

function ConvertTo-PlainHashtable($InputObject) {
    if ($null -eq $InputObject) { return $null }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $hash = @{}
        foreach ($key in $InputObject.Keys) {
            $hash[$key] = ConvertTo-PlainHashtable $InputObject[$key]
        }
        return $hash
    }
    if ($InputObject -is [System.Collections.IEnumerable] -and $InputObject -isnot [string]) {
        $items = @()
        foreach ($item in $InputObject) {
            $items += ConvertTo-PlainHashtable $item
        }
        return $items
    }
    if ($InputObject -is [pscustomobject]) {
        $hash = @{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $hash[$property.Name] = ConvertTo-PlainHashtable $property.Value
        }
        return $hash
    }
    return $InputObject
}

Write-Host ""
Write-Host "Mnemion Windows Setup" -ForegroundColor White
Write-Host "-----------------------" -ForegroundColor White
Write-Host "Repo:   $RepoRoot"
Write-Host "Anaktoron: $MnemionDir"
Write-Host ""

# ---------------------------------------------------------------------------
# Step 1: Directory structure
# ---------------------------------------------------------------------------
Write-Step "Creating ~/.mnemion directory structure"

foreach ($dir in @($MnemionDir, "$MnemionDir\hooks", "$MnemionDir\archive", "$MnemionDir\hook_state")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Ok "Created $dir"
    } else {
        Write-Ok "Exists  $dir"
    }
}

# Copy SyncMemories.ps1
$syncSrc = "$RepoRoot\sync\SyncMemories.ps1"
$syncDst = "$MnemionDir\SyncMemories.ps1"
if (Test-Path $syncSrc) {
    Copy-Item $syncSrc $syncDst -Force
    Write-Ok "Copied SyncMemories.ps1"
} else {
    Write-Warn "SyncMemories.ps1 not found at $syncSrc"
}

# Copy Python save hook
$hookSrc = "$RepoRoot\hooks\mnemion_save_hook.py"
$hookDst = "$MnemionDir\hooks\mnemion_save_hook.py"
if (Test-Path $hookSrc) {
    Copy-Item $hookSrc $hookDst -Force
    Write-Ok "Copied mnemion_save_hook.py"
} else {
    Write-Warn "mnemion_save_hook.py not found at $hookSrc"
}

# Copy backfill script
$backfillSrc = "$RepoRoot\sync\backfill_trust.py"
$backfillDst = "$MnemionDir\backfill_trust.py"
if (Test-Path $backfillSrc) {
    Copy-Item $backfillSrc $backfillDst -Force
    Write-Ok "Copied backfill_trust.py"
}

# ---------------------------------------------------------------------------
# Step 2: Memory git repo
# ---------------------------------------------------------------------------
Write-Step "Configuring private memory git repo"

if ($SkipSync) {
    Write-Skip "Memory git repo setup (-SkipSync passed)"
} elseif (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Warn "git was not found on PATH; configure $MnemionDir manually before sync can push"
} else {
    if (-not (Test-Path "$MnemionDir\.git")) {
        Push-Location $MnemionDir
        git init | Out-Null
        Pop-Location
        Write-Ok "Initialized git repo at $MnemionDir"
    } else {
        Write-Ok "Git repo exists at $MnemionDir"
    }

    if ($MemoryBranch) {
        Push-Location $MnemionDir
        $currentBranch = git rev-parse --abbrev-ref HEAD 2>$null
        if ($currentBranch -ne $MemoryBranch) {
            git checkout $MemoryBranch *> $null
            if ($LASTEXITCODE -ne 0) {
                git checkout -B $MemoryBranch *> $null
            }
        }
        Pop-Location
        Write-Ok "Using memory branch '$MemoryBranch'"
    }

    Push-Location $MnemionDir
    $existingOrigin = git remote get-url origin 2>$null
    $hasOrigin = ($LASTEXITCODE -eq 0)
    if ($MemoryRepoUrl) {
        if ($hasOrigin) {
            if ($existingOrigin -ne $MemoryRepoUrl) {
                git remote set-url origin $MemoryRepoUrl
                Write-Ok "Updated origin remote"
            } else {
                Write-Ok "Origin remote already configured"
            }
        } else {
            git remote add origin $MemoryRepoUrl
            Write-Ok "Added origin remote"
        }
    } elseif (-not $hasOrigin) {
        Write-Warn "No origin remote configured; re-run with -MemoryRepoUrl <git-url> or add one manually"
    } else {
        Write-Ok "Origin remote already configured"
    }
    Pop-Location

    $memoryIgnoreRules = @(
        "anaktoron/",
        "cursor_scraped/",
        "hook_state/",
        "hooks/",
        "heartbeats/",
        "config.json",
        "session_history.json",
        "jepa_predictor.pt",
        "archive/knowledge_graph.sql",
        "*.sqlite3",
        "*.sqlite3-wal",
        "*.sqlite3-shm",
        "*.log",
        ".sync_lock",
        ".drawers_remote_tmp.json",
        "!SyncMemories.ps1",
        "!SyncMemories.sh"
    )
    $memoryGitignore = Join-Path $MnemionDir ".gitignore"
    $existingIgnore = if (Test-Path $memoryGitignore) { Get-Content $memoryGitignore } else { @() }
    foreach ($rule in $memoryIgnoreRules) {
        if ($existingIgnore -notcontains $rule) {
            Add-Content -Path $memoryGitignore -Value $rule
        }
    }
    Write-Ok "Memory repo .gitignore is configured"
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
# Step 3: Claude Code auto-save hook
# ---------------------------------------------------------------------------
Write-Step "Installing Claude Code auto-save hook"

if ($SkipHook) {
    Write-Skip "Claude Code hook (-SkipHook passed)"
} else {
    $hookCmd = "python3 `"$MnemionDir\hooks\mnemion_save_hook.py`""

    $claudeDir = Split-Path $ClaudeSettings -Parent
    if (-not (Test-Path $claudeDir)) {
        New-Item -ItemType Directory $claudeDir -Force | Out-Null
    }

    $settings = @{}
    if (Test-Path $ClaudeSettings) {
        try {
            $raw = Get-Content $ClaudeSettings -Raw -Encoding UTF8
            $settings = ConvertTo-PlainHashtable ($raw | ConvertFrom-Json)
        } catch {
            $settings = @{}
        }
    }

    if (-not $settings.ContainsKey("hooks")) { $settings["hooks"] = @{} }
    if (-not $settings["hooks"].ContainsKey("Stop")) { $settings["hooks"]["Stop"] = @() }

    $filteredStopHooks = @()
    $removedLegacyHook = $false
    foreach ($entry in @($settings["hooks"]["Stop"])) {
        $entryHooks = if ($entry.ContainsKey("hooks")) { @($entry["hooks"]) } else { @() }
        $hasLegacyHook = $false
        foreach ($hook in $entryHooks) {
            $command = if ($hook.ContainsKey("command")) { [string]$hook["command"] } else { "" }
            if ($command -like "*mempalace*" -or $command -like "*mempal_save_hook*") {
                $hasLegacyHook = $true
            }
        }
        if ($hasLegacyHook) {
            $removedLegacyHook = $true
        } else {
            $filteredStopHooks += $entry
        }
    }
    $settings["hooks"]["Stop"] = $filteredStopHooks
    if ($removedLegacyHook) {
        Write-Ok "Removed legacy mempalace auto-save hook from $ClaudeSettings"
    }

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
# Step 4: Task Scheduler -- hourly sync
# ---------------------------------------------------------------------------
Write-Step "Registering hourly Anaktoron sync task"

if ($SkipSync) {
    Write-Skip "Hourly sync task (-SkipSync passed)"
} else {
    $syncArgs = "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$MnemionDir\SyncMemories.ps1`" -MnemionDir `"$MnemionDir`" -MnemionSrc `"$RepoRoot`""
    if ($MemoryBranch) { $syncArgs += " -Branch `"$MemoryBranch`"" }
    if ($AgentId) { $syncArgs += " -AgentId `"$AgentId`"" }
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $syncArgs
    $trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours $SyncIntervalHours) -Once -At (Get-Date)
    $ts = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
        -StartWhenAvailable -RunOnlyIfNetworkAvailable
    $registeredSyncTask = $false
    try {
        Register-ScheduledTask -TaskName $SyncTaskName `
            -Action $action -Trigger $trigger -Settings $ts -RunLevel Highest -Force | Out-Null
        Write-Ok "Task '$SyncTaskName' registered/updated (runs every $SyncIntervalHours hour(s))"
        $registeredSyncTask = $true
    } catch {
        Write-Warn "Could not register elevated sync task; trying current-user task"
        try {
            Register-ScheduledTask -TaskName $SyncTaskName `
                -Action $action -Trigger $trigger -Settings $ts -Force | Out-Null
            Write-Ok "Task '$SyncTaskName' registered/updated for current user (runs every $SyncIntervalHours hour(s))"
            $registeredSyncTask = $true
        } catch {
            Write-Warn "Could not register sync task: $_"
            Write-Warn "Or manually: Task Scheduler > Create Task > Action: powershell.exe -File `"$MnemionDir\SyncMemories.ps1`""
        }
    }
    if ($registeredSyncTask) {
        Remove-LegacySyncTasks
    }
}

# ---------------------------------------------------------------------------
# Step 5: Task Scheduler -- vLLM at login
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
# Step 6: Trust backfill (if Anaktoron exists)
# ---------------------------------------------------------------------------
Write-Step "Checking for existing Anaktoron"

$anaktoronDb = "$MnemionDir\anaktoron\chroma.sqlite3"
if (-not (Test-Path $anaktoronDb)) {
    Write-Skip "No Anaktoron at $anaktoronDb -- backfill skipped (run after mnemion mine)"
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
