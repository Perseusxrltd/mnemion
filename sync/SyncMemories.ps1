#Requires -Version 5.1
# Refresh the local Obsidian vault from the authenticated Mnemion service.
param(
    [string]$Config = $env:MNEMION_VAULT_CONFIG,
    [string]$PythonExe = "python",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Config)) {
    [Console]::Error.WriteLine("Set -Config or MNEMION_VAULT_CONFIG. Legacy Git memory sync is retired; see sync/README.md.")
    exit 2
}
$refreshArgs = @("-m", "mnemion.vault_sync", "--config", $Config)
if ($DryRun) { $refreshArgs += "--dry-run" }
& $PythonExe @refreshArgs
exit $LASTEXITCODE
