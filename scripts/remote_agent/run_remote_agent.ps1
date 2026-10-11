param(
    [string]$Python = "python",
    [string]$Config = "",
    [ValidateSet("debug", "info", "warning", "error")]
    [string]$LogLevel = "info",
    [ValidateSet("scheduled-task", "powershell-launcher", "direct-python")]
    [string]$LaunchSource = "powershell-launcher"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$arguments = @("-m", "remote_station", "run", "--log-level", $LogLevel, "--launch-source", $LaunchSource)
if ($Config) { $arguments += @("--config", $Config) }
Push-Location $projectRoot
try {
    & $Python @arguments
    $agentExitCode = $LASTEXITCODE
    if ($agentExitCode -ne 0) {
        if ($agentExitCode -eq 73 -and $LaunchSource -eq "scheduled-task") {
            Write-Warning "A different OM0RX station controller owns the shared mutex. Suppressing Task Scheduler retries; inspect the sanitized agent log and controller startup entries."
            exit 0
        }
        Write-Error "Remote agent stopped with exit code $agentExitCode" -ErrorAction Continue
        exit $agentExitCode
    }
} finally {
    Pop-Location
}

