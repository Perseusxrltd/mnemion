param([Parameter(Mandatory=$true)][string]$Architecture, [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
if ($Architecture -notin @('x64', 'arm64')) { throw 'Unsupported native privacy target.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw 'A native MSVC compiler is required for the Windows privacy check.' }
Import-Module "$installation/Common7/Tools/Microsoft.VisualStudio.DevShell.dll"
Enter-VsDevShell -VsInstallPath $installation -SkipAutomaticLocation -DevCmdArguments "-arch=$Architecture -host_arch=x64"
$source = Join-Path $PSScriptRoot '../native/telemetry-private-store.c'
$work = Join-Path ([IO.Path]::GetTempPath()) ('mnemion-privacy-build-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($work) | Out-Null
try {
    & cl.exe /nologo /O1 /W4 /WX /MT /guard:cf /std:c17 "/Fo$work/privacy.obj" "/Fe$Destination" $source advapi32.lib /link /DYNAMICBASE /NXCOMPAT
    if ($LASTEXITCODE -ne 0) { throw 'The native Windows privacy check did not compile.' }
} finally { Remove-Item -LiteralPath $work -Recurse -Force }
