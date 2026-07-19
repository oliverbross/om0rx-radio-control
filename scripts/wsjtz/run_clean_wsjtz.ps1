param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$MsysRoot = "C:\JTSDK64-Tools\tools\msys64",
    [string]$RigName = "OM0RX-WSJT-Z",
    [string]$ConfigName = "OM0RX-WSJT-Z",
    [switch]$TestMode,
    [switch]$SkipClassificationServer
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

if (-not $SkipClassificationServer) {
    $classificationServer = Join-Path $ProjectRoot "scripts\wsjtz\om0rx_decode_status_server.py"
    $pythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python is required for the local CS/DS classification server."
        }
        $pythonExe = $pythonCommand.Source
    }
    if (-not (Test-Path -LiteralPath $classificationServer)) {
        throw "CS/DS classification server is missing: $classificationServer"
    }

    $classificationHealthy = $false
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 2
        $classificationHealthy = $health.StatusCode -eq 200
    } catch {
        $classificationHealthy = $false
    }
    if (-not $classificationHealthy) {
        $logRoot = Join-Path $ProjectRoot "logs"
        New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
        Start-Process `
            -FilePath $pythonExe `
            -ArgumentList @($classificationServer) `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logRoot "wsjt-z-classification.out.log") `
            -RedirectStandardError (Join-Path $logRoot "wsjt-z-classification.err.log")
        for ($attempt = 0; $attempt -lt 15; $attempt++) {
            Start-Sleep -Seconds 1
            try {
                $health = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 2
                if ($health.StatusCode -eq 200) {
                    $classificationHealthy = $true
                    break
                }
            } catch {
                $classificationHealthy = $false
            }
        }
    }
    if (-not $classificationHealthy) {
        throw "CS/DS classification server did not become healthy on 127.0.0.1:8765."
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
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

Write-Host "Started clean OM0RX WSJT-Z with local CS/DS classification and guarded DXCC priority:"
Write-Host "  $exe"
Write-Host "Arguments: $($args -join ' ')"
Write-Host "Profile: WSJT-X - $RigName"
