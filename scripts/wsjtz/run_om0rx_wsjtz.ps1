param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$MsysRoot = "C:\JTSDK64-Tools\tools\msys64",
    [string]$RigName = "OM0RX-WSJT-Z",
    [string]$ConfigName = "OM0RX-WSJT-Z",
    [switch]$NoAutoLog,
    [switch]$TestMode
)

$ErrorActionPreference = "Stop"

$buildRoot = Join-Path $ProjectRoot "data\build\wsjt-z-om0rx\build-msys"
$sourceRoot = Join-Path $ProjectRoot "data\build\wsjt-z-om0rx\src"
$exe = Join-Path $buildRoot "wsjt-z.exe"
$fallbackExe = Join-Path $buildRoot "wsjtx.exe"
$decoder = Join-Path $buildRoot "jt9.exe"
$enrichmentServer = Join-Path $ProjectRoot "scripts\wsjtz\om0rx_decode_status_server.py"
$allcallSource = Join-Path $sourceRoot "ALLCALL7.TXT"
$allcallRuntime = Join-Path $buildRoot "ALLCALL7.TXT"
$mingwBin = Join-Path $MsysRoot "mingw64\bin"
$usrBin = Join-Path $MsysRoot "usr\bin"

if ((Test-Path -LiteralPath $fallbackExe) -and (
        -not (Test-Path -LiteralPath $exe) -or
        (Get-Item -LiteralPath $fallbackExe).LastWriteTimeUtc -gt (Get-Item -LiteralPath $exe).LastWriteTimeUtc
    )) {
    Copy-Item -LiteralPath $fallbackExe -Destination $exe -Force
}
if (-not (Test-Path -LiteralPath $exe)) {
    throw "OM0RX WSJT-Z executable not found. Run scripts\wsjtz\build_om0rx_wsjtz.ps1 first."
}
if (-not (Test-Path -LiteralPath $decoder)) {
    throw "WSJT-Z decoder helper jt9.exe not found. Run scripts\wsjtz\build_om0rx_wsjtz.ps1 first."
}
if (-not (Test-Path -LiteralPath $enrichmentServer)) {
    throw "WSJT-Z enrichment server not found: $enrichmentServer"
}
if (-not (Test-Path -LiteralPath $allcallSource)) {
    throw "WSJT-Z ALLCALL7.TXT not found: $allcallSource"
}
if (-not (Test-Path -LiteralPath $allcallRuntime) -or ((Get-Item -LiteralPath $allcallRuntime).Length -ne (Get-Item -LiteralPath $allcallSource).Length)) {
    Copy-Item -LiteralPath $allcallSource -Destination $allcallRuntime -Force
}
if (-not (Test-Path -LiteralPath $mingwBin)) {
    throw "MSYS2 MinGW bin not found: $mingwBin"
}

$env:PATH = "$mingwBin;$usrBin;$env:PATH"

function Set-IniValue {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string[]]$Lines,
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $pattern = "^$([regex]::Escape($Key))="
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match $pattern) {
            $Lines[$i] = "$Key=$Value"
            return $Lines
        }
    }

    return @($Lines + "$Key=$Value")
}

function Set-IniSectionValue {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string[]]$Lines,
        [Parameter(Mandatory = $true)]
        [string]$Section,
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $sectionPattern = "^\[$([regex]::Escape($Section))\]$"
    $keyPattern = "^$([regex]::Escape($Key))="
    $sectionIndex = -1
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match $sectionPattern) {
            $sectionIndex = $i
            break
        }
    }

    if ($sectionIndex -lt 0) {
        return @($Lines + "" + "[$Section]" + "$Key=$Value")
    }

    for ($i = $sectionIndex + 1; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match '^\[.+\]$') {
            $before = if ($i -gt 0) { $Lines[0..($i - 1)] } else { @() }
            $after = $Lines[$i..($Lines.Count - 1)]
            return @($before + "$Key=$Value" + $after)
        }
        if ($Lines[$i] -match $keyPattern) {
            $Lines[$i] = "$Key=$Value"
            return $Lines
        }
    }

    return @($Lines + "$Key=$Value")
}

if (-not $NoAutoLog) {
    $profileDir = Join-Path $env:LOCALAPPDATA "WSJT-X - $RigName"
    $profileIni = Join-Path $profileDir "WSJT-X - $RigName.ini"
    if (Test-Path -LiteralPath $profileIni) {
        $profileLines = @(Get-Content -LiteralPath $profileIni)
        $profileLines = Set-IniValue -Lines $profileLines -Key "PromptToLog" -Value "false"
        $profileLines = Set-IniValue -Lines $profileLines -Key "AutoLog" -Value "true"
        $profileLines = Set-IniValue -Lines $profileLines -Key "AcceptUDPRequests" -Value "true"
        $profileLines = Set-IniValue -Lines $profileLines -Key "UDPServer" -Value "224.0.0.1"
        $profileLines = Set-IniValue -Lines $profileLines -Key "UDPServerPort" -Value "2237"
        $profileLines = Set-IniSectionValue -Lines $profileLines -Section "Configuration" -Key "PromptToLog" -Value "false"
        $profileLines = Set-IniSectionValue -Lines $profileLines -Section "Configuration" -Key "AutoLog" -Value "true"
        $profileLines = Set-IniSectionValue -Lines $profileLines -Section "Configuration" -Key "AcceptUDPRequests" -Value "true"
        $profileLines = Set-IniSectionValue -Lines $profileLines -Section "Configuration" -Key "UDPServer" -Value "224.0.0.1"
        $profileLines = Set-IniSectionValue -Lines $profileLines -Section "Configuration" -Key "UDPServerPort" -Value "2237"
        Set-Content -LiteralPath $profileIni -Value $profileLines -Encoding UTF8
        Write-Host "Automation logging enabled for $RigName profile."
    }
}

$args = @("--rig-name", $RigName, "--config", $ConfigName)
if ($TestMode) {
    $args += "--test-mode"
}

$appName = "WSJT-Z - $RigName"
if ($TestMode) {
    $appName = "$appName - test"
}

$matchingProcess = Get-CimInstance Win32_Process -Filter "Name='wsjt-z.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -like "*--rig-name $RigName*" -and
        (-not $TestMode -or $_.CommandLine -like "*--test-mode*")
    } |
    Select-Object -First 1

if ($matchingProcess) {
    Write-Host "OM0RX WSJT-Z is already running for $appName (PID $($matchingProcess.ProcessId))."
    return
}

$lockFile = Join-Path $env:TEMP "$appName.lock"
Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue

$logRoot = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$enrichmentOutLog = Join-Path $logRoot "wsjt-z-enrichment.out.log"
$enrichmentErrLog = Join-Path $logRoot "wsjt-z-enrichment.err.log"

$enrichmentOk = $false
try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 2
    $enrichmentOk = $health.StatusCode -eq 200
} catch {
    $enrichmentOk = $false
}
if (-not $enrichmentOk) {
    Start-Process `
        -FilePath "python" `
        -ArgumentList @($enrichmentServer) `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $enrichmentOutLog `
        -RedirectStandardError $enrichmentErrLog
    Start-Sleep -Seconds 2
}

$logSafeName = (($appName -replace '[^\w.]+', '-') -replace '-+', '-').Trim('-').ToLowerInvariant()
$outLog = Join-Path $logRoot "$logSafeName.out.log"
$errLog = Join-Path $logRoot "$logSafeName.err.log"
Remove-Item -LiteralPath $outLog, $errLog -Force -ErrorAction SilentlyContinue

Start-Process `
    -FilePath $exe `
    -ArgumentList $args `
    -WorkingDirectory $buildRoot `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog
Write-Host "Started OM0RX WSJT-Z:"
Write-Host "  $exe"
Write-Host "Decoder:"
Write-Host "  $decoder"
Write-Host "Arguments: $($args -join ' ')"
Write-Host "Logs:"
Write-Host "  $outLog"
Write-Host "  $errLog"
Write-Host "Enrichment:"
Write-Host "  http://127.0.0.1:8765/health"
