#Requires -Version 5.1
<#
.SYNOPSIS
Configure an optional Obsidian refresh task for a Mnemion service client.
.DESCRIPTION
Install Mnemion's Python package first. This command prepares a reviewable
configuration and optionally registers one task for the current user. It does
not alter assistant hooks, start a model server, or configure a memory Git repo.
#>
param(
    [string]$MnemionDir = "",
    [Parameter(Mandatory=$true)][string]$CredentialsFile,
    [Parameter(Mandatory=$true)][string]$VaultPath,
    [Parameter(Mandatory=$true)][string[]]$SpaceIds,
    [string]$PythonExe = "python",
    [string]$SyncTaskName = "MnemionObsidianRefresh",
    [ValidateRange(1,168)][int]$SyncIntervalHours = 1,
    [switch]$SkipSync,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($MnemionDir)) {
    $MnemionDir = Join-Path $env:LOCALAPPDATA "Mnemion"
}
if (-not [IO.Path]::IsPathRooted($VaultPath) -or -not [IO.Path]::IsPathRooted($CredentialsFile)) {
    throw "Vault and credentials paths must be absolute."
}
if (-not (Test-Path -LiteralPath $CredentialsFile -PathType Leaf)) {
    throw "The private service credentials file does not exist."
}
$validatedSpaces = @($SpaceIds | ForEach-Object { ([Guid]::Parse($_)).ToString() })
if ($validatedSpaces.Count -lt 1 -or $validatedSpaces.Count -gt 20) {
    throw "Choose between 1 and 20 memory spaces."
}
$config = [ordered]@{
    credentials_file = $CredentialsFile
    vault_path = $VaultPath
    space_ids = $validatedSpaces
    review = $false
}
$configPath = Join-Path $MnemionDir "obsidian-refresh.json"
$scriptPath = Join-Path $MnemionDir "SyncMemories.ps1"
if ($DryRun) {
    [ordered]@{ configuration_file = $configPath; configuration = $config; scheduled_task = $(if ($SkipSync) { $null } else { $SyncTaskName }) } | ConvertTo-Json -Depth 5
    exit 0
}
& $PythonExe -c "import mnemion.vault_sync"
if ($LASTEXITCODE -ne 0) { throw "Install Mnemion into the selected Python environment first." }
New-Item -ItemType Directory -Path $MnemionDir -Force | Out-Null
if (Test-Path -LiteralPath $configPath) {
    throw "The refresh configuration already exists. Review and edit it directly; installation will not overwrite it."
}
[IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "SyncMemories.ps1") -Destination $scriptPath -Force
if (-not $SkipSync) {
    foreach ($value in @($scriptPath, $configPath, $PythonExe)) {
        if ($value -match '["\r\n]') { throw "Task paths cannot contain quotes or line breaks." }
    }
    $taskArguments = "-NoProfile -NonInteractive -File `"$scriptPath`" -Config `"$configPath`" -PythonExe `"$PythonExe`""
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArguments
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours $SyncIntervalHours)
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable
    Register-ScheduledTask -TaskName $SyncTaskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
}
[ordered]@{ configuration_file = $configPath; scheduled = (-not $SkipSync) } | ConvertTo-Json
