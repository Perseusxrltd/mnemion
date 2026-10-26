param([Parameter(Mandatory=$true)][string]$Architecture, [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
if ($Architecture -notin @('x64', 'arm64')) { throw 'Unsupported native network-policy target.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw 'The native network-policy probe requires the MSVC system SDK.' }
Import-Module "$installation/Common7/Tools/Microsoft.VisualStudio.DevShell.dll"
Enter-VsDevShell -VsInstallPath $installation -SkipAutomaticLocation -DevCmdArguments "-arch=$Architecture -host_arch=x64"
$source = Join-Path $PSScriptRoot '../mnemion/product_telemetry/native'
$work = Join-Path ([IO.Path]::GetTempPath()) ('mnemion-network-build-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($work) | Out-Null
try {
    & cl.exe /nologo /O1 /W4 /WX /MT /guard:cf /std:c17 /LD "/Fo$work/" "/Fe$Destination" `
        (Join-Path $source 'network-state.c') (Join-Path $source 'network-node.c') `
        /link /DYNAMICBASE /NXCOMPAT bcrypt.lib advapi32.lib OneCore.lib "/IMPLIB:$work/network-state.lib"
    if ($LASTEXITCODE -ne 0) { throw 'The native network-policy probe did not compile.' }
} finally { Remove-Item -LiteralPath $work -Recurse -Force }
