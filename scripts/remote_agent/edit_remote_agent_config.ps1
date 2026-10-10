param(
    [string]$Python = "python",
    [string]$Config = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Config) {
    Push-Location $projectRoot
    try {
        $Config = (& $Python -m remote_station config-path).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Could not resolve the remote-agent configuration path" }
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path -LiteralPath $Config)) {
    throw "Configuration does not exist: $Config. Run init_remote_agent.ps1 first."
}
Start-Process -FilePath "notepad.exe" -ArgumentList @($Config)
