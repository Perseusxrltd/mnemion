param(
    [Parameter(Mandatory = $true)][string]$Architecture,
    [Parameter(Mandatory = $true)][string]$HostArchitecture,
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

if ($Architecture -notin @('x64', 'arm64')) {
    throw "Unsupported target architecture '$Architecture'. This oracle accepts only x64 and arm64."
}
if ($HostArchitecture -notin @('x64', 'arm64')) {
    throw "Unsupported host architecture '$HostArchitecture'. This oracle accepts only x64 and arm64."
}
if ($env:PROCESSOR_ARCHITEW6432) {
    throw "This process is WOW64 ($env:PROCESSOR_ARCHITECTURE / $env:PROCESSOR_ARCHITEW6432). Refusing an emulated host."
}
$expectedProcessor = @{ x64 = 'AMD64'; arm64 = 'ARM64' }[$HostArchitecture]
if ($env:PROCESSOR_ARCHITECTURE -ne $expectedProcessor) {
    throw "Host PROCESSOR_ARCHITECTURE is '$($env:PROCESSOR_ARCHITECTURE)'. Requested host '$HostArchitecture' requires '$expectedProcessor'. Refusing to assume a different architecture."
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root 'out'
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$source = Join-Path $root 'sdk_abi.c'
$exe = Join-Path $OutputDirectory 'sdk_abi.exe'
$objectDir = Join-Path $OutputDirectory 'obj'
$abiPath = Join-Path $OutputDirectory 'abi.json'
$metadataPath = Join-Path $OutputDirectory 'metadata.json'

function Limit-Text([object]$Value, [int]$Max) {
    if ($null -eq $Value) { return '' }
    $text = ([string]$Value) -replace '[\u0000-\u001F]', ' '
    $text = $text.Trim()
    if ($text.Length -gt $Max) { return $text.Substring(0, $Max) }
    return $text
}

function Get-CapturedLines([object]$Entry) {
    if ($null -eq $Entry) { return @() }
    $text = ''
    if ($Entry -is [System.Management.Automation.ErrorRecord]) {
        $text = [string]$Entry.Exception.Message
        if (-not $text) { $text = [string]$Entry }
    } else {
        $text = [string]$Entry
    }
    $lines = @()
    foreach ($line in @($text -split '\r?\n')) {
        $clean = $line -replace '^.*?:\s+(?=Microsoft)', ''
        $clean = Limit-Text $clean 160
        if ($clean) { $lines += $clean }
        if ($lines.Count -ge 8) { break }
    }
    return $lines
}

function Get-AbiField($Node, [string]$Name) {
    if ($Node -isnot [System.Collections.IDictionary]) { return $null }
    foreach ($key in @($Node.Keys)) {
        if ([string]$key -ceq $Name) { return $Node[$key] }
    }
    return $null
}

function Assert-NumericTree($Node, [string]$PathName) {
    if ($Node -is [System.Collections.IDictionary]) {
        foreach ($key in @($Node.Keys)) {
            Assert-NumericTree $Node[$key] ($PathName + '.' + [string]$key)
        }
        return
    }
    $ok = $Node -is [long] -or $Node -is [int] -or $Node -is [uint32] -or $Node -is [uint64]
    if (-not $ok) {
        throw "ABI JSON has a non-numeric value at $PathName."
    }
    if ([int64]$Node -lt 0) {
        throw "ABI JSON has a negative value at $PathName."
    }
}

$hostDir = @{ x64 = 'Hostx64'; arm64 = 'Hostarm64' }[$HostArchitecture]
$targetDir = @{ x64 = 'x64'; arm64 = 'arm64' }[$Architecture]
$component = @{
    x64 = 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64'
    arm64 = 'Microsoft.VisualStudio.Component.VC.Tools.ARM64'
}[$Architecture]
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) {
    throw 'vswhere.exe is not installed. This oracle does not download a compiler.'
}
$installation = (& $vswhere -latest -products '*' -requires $component -property installationPath | Select-Object -First 1)
if ($installation) { $installation = $installation.Trim() }
if (-not $installation) {
    $installation = (& $vswhere -latest -products '*' -property installationPath | Select-Object -First 1)
    if ($installation) { $installation = $installation.Trim() }
}
if (-not $installation) {
    throw 'Visual Studio is not installed. This oracle does not download a compiler.'
}
$tools = Join-Path $installation 'VC\Tools\MSVC'
$nativeCl = $null
if (Test-Path -LiteralPath $tools) {
    $nativeCl = @(Get-ChildItem -LiteralPath $tools -Directory | ForEach-Object {
        $candidate = Join-Path $_.FullName "bin\$hostDir\$targetDir\cl.exe"
        if (Test-Path -LiteralPath $candidate) { $candidate }
    } | Select-Object -Last 1)
    if ($nativeCl -is [array]) { $nativeCl = $nativeCl[-1] }
}
if (-not $nativeCl) {
    throw "No installed MSVC compiler matches host $HostArchitecture and target $Architecture (VC\Tools\MSVC\*\bin\$hostDir\$targetDir\cl.exe). Refusing to substitute another architecture."
}

$exeReady = $false
try {
    Import-Module "$installation/Common7/Tools/Microsoft.VisualStudio.DevShell.dll"
    Enter-VsDevShell -VsInstallPath $installation -SkipAutomaticLocation -DevCmdArguments "-arch=$Architecture -host_arch=$HostArchitecture"
    $captured = @(& cl.exe 2>&1)
    $normalized = @()
    foreach ($entry in $captured) {
        $normalized += @(Get-CapturedLines $entry)
        if ($normalized.Count -ge 32) { break }
    }
    if ($normalized.Count -gt 32) { $normalized = @($normalized | Select-Object -First 32) }
    $bannerPattern = 'Microsoft \(R\) C/C\+\+ Optimizing Compiler Version \d+(?:\.\d+)+ for [A-Za-z0-9]+'
    $foundBanners = @()
    foreach ($line in $normalized) {
        foreach ($hit in @([regex]::Matches($line, $bannerPattern))) {
            $foundBanners += $hit.Value
        }
    }
    $distinctBanners = @($foundBanners | Select-Object -Unique)
    if ($distinctBanners.Count -eq 0) {
        throw 'No MSVC compiler version banner was found in the cl output. Refusing to treat usage text as the compiler target.'
    }
    if ($distinctBanners.Count -gt 1) {
        throw "MSVC compiler banners conflict: $($distinctBanners -join ' | ')."
    }
    $banner = [string]$distinctBanners[0]
    if ($banner -match 'ARM64EC') {
        throw "The selected compiler is ARM64EC ($banner). This oracle accepts only x64 and ARM64."
    }
    if ($Architecture -eq 'x64' -and $banner -notmatch 'for x64') {
        throw "Compiler banner does not target x64: $banner"
    }
    if ($Architecture -eq 'arm64' -and $banner -notmatch 'for ARM64') {
        throw "Compiler banner does not target ARM64: $banner"
    }
    $sdk = Limit-Text ([Environment]::GetEnvironmentVariable('WindowsSDKVersion')) 64
    $sdk = $sdk.TrimEnd('\', '/')
    if (-not $sdk) {
        throw 'The MSVC environment did not publish WindowsSDKVersion.'
    }

    New-Item -ItemType Directory -Force -Path $objectDir | Out-Null
    $objectDirArg = '/Fo' + $objectDir.TrimEnd('\', '/') + '\'
    & cl.exe /nologo /O1 /W4 /WX /MT /guard:cf /std:c17 /TC $objectDirArg "/Fe$exe" $source /link /DYNAMICBASE /NXCOMPAT /SUBSYSTEM:CONSOLE
    if ($LASTEXITCODE -ne 0) {
        throw 'The SDK ABI oracle did not compile.'
    }
    $bytes = [System.IO.File]::ReadAllBytes($exe)
    if ($bytes.Length -lt 0x40 -or $bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) {
        throw 'The compiler output is not a PE file.'
    }
    $lfanew = [BitConverter]::ToInt32($bytes, 0x3C)
    if ($lfanew -lt 0 -or ($lfanew + 6) -gt $bytes.Length -or $bytes[$lfanew] -ne 0x50 -or $bytes[$lfanew + 1] -ne 0x45) {
        throw 'The compiler output has no PE header.'
    }
    $machine = [int][BitConverter]::ToUInt16($bytes, $lfanew + 4)
    $expectedMachine = @{ x64 = 0x8664; arm64 = 0xAA64 }[$Architecture]
    if ($machine -ne $expectedMachine) {
        throw "PE machine $machine does not match target $Architecture ($expectedMachine). Refusing to execute it."
    }

    $raw = @(& $exe)
    if ($LASTEXITCODE -ne 0) {
        throw "The SDK ABI oracle exited $LASTEXITCODE."
    }
    $text = if ($raw.Count -eq 0) { '' } else { ($raw -join "`n").Trim() }
    if ($text.Length -gt 16384) {
        throw 'ABI JSON exceeded 16384 characters.'
    }
    $parsed = $text | ConvertFrom-Json -AsHashtable
    Assert-NumericTree $parsed 'abi'
    $required = @{
        WNODE_HEADER = @('sizeof', 'HistoricalContext', 'Version', 'Linkage', 'CountLost', 'KernelHandle', 'TimeStamp', 'Guid', 'ClientContext', 'Flags')
        EVENT_TRACE_PROPERTIES = @('sizeof', 'Wnode', 'LoggerThreadId', 'LogFileNameOffset', 'LoggerNameOffset')
        EVENT_DESCRIPTOR = @('sizeof', 'Id', 'Version', 'Channel', 'Level', 'Opcode', 'Task', 'Keyword')
        EVENT_HEADER = @('sizeof', 'Size', 'EventDescriptor', 'ProcessorTime', 'ActivityId')
        EVENT_RECORD = @('sizeof', 'ExtendedData', 'UserData', 'UserContext')
        EVENT_TRACE_HEADER = @('sizeof', 'Guid', 'GuidPtr', 'ClientContext', 'Flags')
        EVENT_TRACE = @('sizeof', 'Header', 'MofData', 'ClientContext', 'BufferContext')
        TRACE_LOGFILE_HEADER = @('sizeof', 'TimeZone', 'BootTime', 'PerfFreq', 'StartTime')
        EVENT_TRACE_LOGFILEW = @('sizeof', 'LogFileMode', 'ProcessTraceMode', 'LogfileHeader', 'BufferCallback', 'EventCallback', 'EventRecordCallback', 'Context')
    }
    foreach ($typeName in $required.Keys) {
        $block = Get-AbiField $parsed $typeName
        if ($null -eq $block) { throw "ABI JSON is missing $typeName." }
        foreach ($field in $required[$typeName]) {
            if ($null -eq (Get-AbiField $block $field)) { throw "ABI JSON is missing $typeName.$field." }
        }
    }
    $archCode = @{ x64 = 1; arm64 = 2 }[$Architecture]
    $schema = Get-AbiField $parsed 'schema'
    $archValue = Get-AbiField $parsed 'arch'
    if ($null -eq $schema -or $null -eq $archValue -or [int]$schema -ne 1 -or [int]$archValue -ne $archCode) {
        throw "ABI schema/arch does not match target $Architecture."
    }
    $primitives = Get-AbiField $parsed 'primitives'
    $pointerWidth = Get-AbiField $primitives 'pointer'
    $longWidth = Get-AbiField $primitives 'long'
    $intWidth = Get-AbiField $primitives 'int'
    if ($null -eq $pointerWidth -or $null -eq $longWidth -or $null -eq $intWidth -or [int]$pointerWidth -ne 8 -or [int]$longWidth -ne 4 -or [int]$intWidth -ne 4) {
        throw 'ABI primitives are not LLP64.'
    }
    if ($null -eq (Get-AbiField $primitives 'size_t') -or $null -eq (Get-AbiField $primitives 'SIZE_T')) {
        throw 'ABI JSON merged or dropped case-distinct size_t and SIZE_T keys.'
    }
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($abiPath, $text + "`n", $utf8)

    $current = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $metadata = [ordered]@{
        schema = 1
        host_arch = $HostArchitecture
        target_arch = $Architecture
        processor_architecture = Limit-Text $env:PROCESSOR_ARCHITECTURE 16
        pe_machine = $machine
        os_product = Limit-Text $current.ProductName 80
        os_display_version = Limit-Text $current.DisplayVersion 32
        os_build = Limit-Text $current.CurrentBuild 16
        os_ubr = Limit-Text $current.UBR 16
        windows_sdk_version = $sdk
        compiler_banner = $banner
        abi_bytes = ([System.IO.File]::ReadAllBytes($abiPath)).Length
    }
    $metadataJson = ($metadata | ConvertTo-Json -Compress) + "`n"
    if ($metadataJson.Length -gt 4096) {
        throw 'Metadata JSON exceeded 4096 characters.'
    }
    [System.IO.File]::WriteAllText($metadataPath, $metadataJson, $utf8)
    $exeReady = $true
}
finally {
    if (Test-Path -LiteralPath $exe) { Remove-Item -LiteralPath $exe -Force }
    if (Test-Path -LiteralPath $objectDir) { Remove-Item -LiteralPath $objectDir -Recurse -Force }
    if (-not $exeReady) {
        if (Test-Path -LiteralPath $abiPath) { Remove-Item -LiteralPath $abiPath -Force }
        if (Test-Path -LiteralPath $metadataPath) { Remove-Item -LiteralPath $metadataPath -Force }
    }
}

Write-Output "SDK ABI oracle wrote abi.json ($($metadata.abi_bytes) bytes) for host $HostArchitecture target $Architecture."
