param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$MsysRoot = "C:\JTSDK64-Tools\tools\msys64",
    [string]$RigName = "OM0RX-WSJTZ-CLEAN",
    [string]$ConfigName = "OM0RX-WSJTZ-CLEAN",
    [switch]$TestMode
)

$ErrorActionPreference = "Stop"

$buildRoot = Join-Path $ProjectRoot "data\build\wsjt-z-clean\build-msys"
$exe = Join-Path $buildRoot "wsjt-z-clean.exe"
$decoder = Join-Path $buildRoot "jt9.exe"
$mingwBin = Join-Path $MsysRoot "mingw64\bin"
$usrBin = Join-Path $MsysRoot "usr\bin"

foreach ($required in @($exe, $decoder, $mingwBin)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Clean WSJT-Z runtime dependency is missing: $required"
    }
}

$env:PATH = "$mingwBin;$usrBin;$env:PATH"
$args = @("--rig-name", $RigName, "--config", $ConfigName)
if ($TestMode) {
    $args += "--test-mode"
}

$matchingProcess = Get-CimInstance Win32_Process -Filter "Name='wsjt-z-clean.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*--rig-name $RigName*" } |
    Select-Object -First 1
if ($matchingProcess) {
    Write-Host "Clean WSJT-Z is already running for $RigName (PID $($matchingProcess.ProcessId))."
    return
}

$logRoot = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$outLog = Join-Path $logRoot "wsjt-z-clean.out.log"
$errLog = Join-Path $logRoot "wsjt-z-clean.err.log"

Start-Process `
    -FilePath $exe `
    -ArgumentList $args `
    -WorkingDirectory $buildRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

Write-Host "Started clean WSJT-Z baseline without enrichment or INI mutation:"
Write-Host "  $exe"
Write-Host "Arguments: $($args -join ' ')"
Write-Host "Profile: WSJT-X - $RigName"

