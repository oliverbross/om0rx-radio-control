param(
    [string]$Python = "python",
    [string]$Config = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$arguments = @("-m", "remote_station", "init")
if ($Config) { $arguments += @("--config", $Config) }
Push-Location $projectRoot
try {
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Remote agent initialization failed with exit code $LASTEXITCODE" }
    $configPath = if ($Config) { (Resolve-Path -LiteralPath $Config).Path } else {
        (& $Python -m remote_station config-path).Trim()
    }
    if ($LASTEXITCODE -ne 0 -or -not $configPath) {
        throw "Could not resolve the remote-agent configuration path"
    }
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        $account = "$env:USERDOMAIN\$env:USERNAME"
        & icacls.exe $configPath /inheritance:r /grant:r "${account}:(F)" "*S-1-5-18:(F)" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not restrict configuration permissions" }
        Write-Host "Restricted configuration access to $account and SYSTEM"
    }
} finally {
    Pop-Location
}

