param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$MsysRoot = "C:\JTSDK64-Tools\tools\msys64",
    [string]$RigName = "OM0RX-AUTO",
    [string]$ConfigName = "OM0RX-AUTO",
    [switch]$TestMode
)

$ErrorActionPreference = "Stop"

$buildRoot = Join-Path $ProjectRoot "data\build\wsjtx-improved-om0rx\build-msys"
$exe = Join-Path $buildRoot "wsjtx.exe"
$decoder = Join-Path $buildRoot "jt9.exe"
$mingwBin = Join-Path $MsysRoot "mingw64\bin"
$usrBin = Join-Path $MsysRoot "usr\bin"

if (-not (Test-Path -LiteralPath $exe)) {
    throw "Patched wsjtx.exe not found. Run scripts\wsjtx\build_om0rx_wsjtx.ps1 first."
}
if (-not (Test-Path -LiteralPath $decoder)) {
    throw "WSJT-X decoder helper jt9.exe not found. Run scripts\wsjtx\build_om0rx_wsjtx.ps1 first."
}
if (-not (Test-Path -LiteralPath $mingwBin)) {
    throw "MSYS2 MinGW bin not found: $mingwBin"
}

$env:PATH = "$mingwBin;$usrBin;$env:PATH"

$args = @("--rig-name", $RigName, "--config", $ConfigName)
if ($TestMode) {
    $args += "--test-mode"
}

$appName = "WSJT-X - $RigName"
if ($TestMode) {
    $appName = "$appName - test"
}

$matchingProcess = Get-CimInstance Win32_Process -Filter "Name='wsjtx.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -like "*--rig-name $RigName*" -and
        (-not $TestMode -or $_.CommandLine -like "*--test-mode*")
    } |
    Select-Object -First 1

if ($matchingProcess) {
    Write-Host "Patched WSJT-X Improved is already running for $appName (PID $($matchingProcess.ProcessId))."
    return
}

$lockFile = Join-Path $env:TEMP "$appName.lock"
Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue

$logRoot = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
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
Write-Host "Started patched WSJT-X Improved:"
Write-Host "  $exe"
Write-Host "Decoder:"
Write-Host "  $decoder"
Write-Host "Arguments: $($args -join ' ')"
Write-Host "Logs:"
Write-Host "  $outLog"
Write-Host "  $errLog"
