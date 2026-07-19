param(
    [int]$Port = 8080,
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$AgentProject = Join-Path $ProjectRoot "tools\Om0rxAgent\Om0rxAgent.csproj"
& (Join-Path $PSScriptRoot "generate_agent_icon.ps1") -ProjectRoot $ProjectRoot
dotnet publish $AgentProject -c $Configuration -r win-x64 --self-contained false | Out-Host

$Exe = Join-Path $ProjectRoot "tools\Om0rxAgent\bin\$Configuration\net8.0-windows\win-x64\publish\Om0rxAgent.exe"
if (-not (Test-Path -LiteralPath $Exe)) {
    throw "Published agent executable not found: $Exe"
}

$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$ValueName = "OM0RX Radio Control Agent"
$Command = "`"$Exe`" --project-root `"$ProjectRoot`" --port $Port"
Set-ItemProperty -Path $RunKey -Name $ValueName -Value $Command
Write-Host "Installed startup entry: $ValueName" -ForegroundColor Green
Write-Host $Command
