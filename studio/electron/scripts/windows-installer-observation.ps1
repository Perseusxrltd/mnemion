# Read only: report installer processes/windows in one disposable probe directory.
# No arbitrary desktop windows or command-line arguments enter the report.
$ErrorActionPreference = 'Stop'
$root = $env:MNEMION_PROBE_OUTPUT_DIRECTORY
if (-not $root -or -not [IO.Path]::IsPathRooted($root)) { throw 'Use a disposable probe directory' }
$all = @(Get-CimInstance Win32_Process)
$owned = @{}
foreach ($item in $all) {
  if ($item.ExecutablePath -and $item.ExecutablePath.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
    $owned[[int]$item.ProcessId] = $true
  }
}
for ($depth = 0; $depth -lt 5; $depth++) {
  foreach ($item in $all) {
    if ($owned.ContainsKey([int]$item.ParentProcessId)) { $owned[[int]$item.ProcessId] = $true }
  }
}
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class MnemionInstallerObservation {
  public delegate bool Callback(IntPtr window, IntPtr parameter);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Callback cb, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, Callback cb, IntPtr p);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr window, StringBuilder text, int capacity);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr window, StringBuilder text, int capacity);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
}
'@
$windows = [Collections.Generic.List[object]]::new()
$callback = [MnemionInstallerObservation+Callback] {
  param($handle, $unused)
  [uint32]$owner = 0
  [void][MnemionInstallerObservation]::GetWindowThreadProcessId($handle, [ref]$owner)
  if (-not $owned.ContainsKey([int]$owner) -or $windows.Count -ge 40) { return $true }
  $title = [Text.StringBuilder]::new(512)
  $class = [Text.StringBuilder]::new(128)
  [void][MnemionInstallerObservation]::GetWindowText($handle, $title, $title.Capacity)
  [void][MnemionInstallerObservation]::GetClassName($handle, $class, $class.Capacity)
  $controls = [Collections.Generic.List[string]]::new()
  $child = [MnemionInstallerObservation+Callback] {
    param($control, $unusedChild)
    if ($controls.Count -ge 20) { return $false }
    $text = [Text.StringBuilder]::new(512)
    [void][MnemionInstallerObservation]::GetWindowText($control, $text, $text.Capacity)
    if ($text.Length -gt 0) { $controls.Add($text.ToString()) }
    return $true
  }
  [void][MnemionInstallerObservation]::EnumChildWindows($handle, $child, [IntPtr]::Zero)
  $windows.Add(@{ pid = $owner; class = $class.ToString(); title = $title.ToString();
    visible = [MnemionInstallerObservation]::IsWindowVisible($handle); controls = @($controls.ToArray()) })
  return $true
}
[void][MnemionInstallerObservation]::EnumWindows($callback, [IntPtr]::Zero)
@{
  processes = @($all | Where-Object { $owned.ContainsKey([int]$_.ProcessId) } | Select-Object -First 40 ProcessId,ParentProcessId,Name,ExecutablePath,KernelModeTime,UserModeTime,WorkingSetSize)
  windows = @($windows.ToArray())
  disk = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,Size,FreeSpace)
} | ConvertTo-Json -Depth 6 -Compress
