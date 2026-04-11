# setup_librarian_scheduler.ps1
# Registers a daily Windows Task Scheduler job to run 'mnemion librarian' at 3 AM.
# Run once from an elevated PowerShell prompt:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\setup_librarian_scheduler.ps1

$TaskName  = "MnemionLibrarian"
$TaskDesc  = "Daily Mnemion memory-palace tidy-up (contradiction scan, room re-classification, KG extraction)"
$PythonExe = (Get-Command py -ErrorAction SilentlyContinue)?.Source
if (-not $PythonExe) { $PythonExe = "py" }   # fallback — must be on PATH

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m mnemion librarian" `
    -WorkingDirectory $env:USERPROFILE

$Trigger = New-ScheduledTaskTrigger -Daily -At "03:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -WakeToRun:$false

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

# Remove old registration if it exists
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "  Removed existing task '$TaskName'"
}

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Description $TaskDesc `
    -Action    $Action `
    -Trigger   $Trigger `
    -Settings  $Settings `
    -Principal $Principal | Out-Null

Write-Host ""
Write-Host "  Mnemion Librarian scheduled successfully."
Write-Host "  Task name : $TaskName"
Write-Host "  Runs at   : 03:00 daily"
Write-Host "  Command   : $PythonExe -m mnemion librarian"
Write-Host ""
Write-Host "  To verify:"
Write-Host "    Get-ScheduledTask -TaskName '$TaskName' | Format-List"
Write-Host ""
Write-Host "  To run immediately (test):"
Write-Host "    Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
