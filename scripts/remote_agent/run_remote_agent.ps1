param(
    [string]$Python = "python",
    [string]$Config = "",
    [ValidateSet("debug", "info", "warning", "error")]
    [string]$LogLevel = "info"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$arguments = @("-m", "remote_station", "run", "--log-level", $LogLevel)
if ($Config) { $arguments += @("--config", $Config) }
Push-Location $projectRoot
try {
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Remote agent stopped with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

