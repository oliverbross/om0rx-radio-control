param(
    [int]$Port = 8080,
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$NoAutostart
)

$ErrorActionPreference = "Stop"
$AgentProject = Join-Path $ProjectRoot "tools\Om0rxAgent\Om0rxAgent.csproj"
$AgentExe = Join-Path $ProjectRoot "tools\Om0rxAgent\bin\$Configuration\net8.0-windows\Om0rxAgent.exe"

if (-not (Test-Path -LiteralPath $AgentExe)) {
    & (Join-Path $PSScriptRoot "generate_agent_icon.ps1") -ProjectRoot $ProjectRoot
    dotnet build $AgentProject -c $Configuration | Out-Host
}

if (-not (Test-Path -LiteralPath $AgentExe)) {
    throw "Agent executable not found after build: $AgentExe"
}

$arguments = @("--project-root", "`"$ProjectRoot`"", "--port", "$Port", "--launch-source", "powershell-launcher")
if ($NoAutostart) {
    $arguments += "--no-autostart"
}

Start-Process -FilePath $AgentExe -ArgumentList ($arguments -join " ") -WorkingDirectory $ProjectRoot -WindowStyle Hidden
Write-Host "OM0RX Agent started in the tray. You can close this PowerShell window." -ForegroundColor Green
