param(
    [int]$Port = 8080,
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$DesktopOnly,
    [switch]$StartMenuOnly
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

function New-AgentShortcut {
    param(
        [string]$ShortcutPath
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $AgentExe
    $shortcut.Arguments = "--project-root `"$ProjectRoot`" --port $Port"
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.IconLocation = "$AgentExe,0"
    $shortcut.Description = "Start OM0RX Radio Control Agent"
    $shortcut.Save()
}

$created = @()

if (-not $StartMenuOnly) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $desktopShortcut = Join-Path $desktop "OM0RX Radio Control Agent.lnk"
    New-AgentShortcut -ShortcutPath $desktopShortcut
    $created += $desktopShortcut
}

if (-not $DesktopOnly) {
    $programs = [Environment]::GetFolderPath("Programs")
    $menuDir = Join-Path $programs "OM0RX Radio Control"
    New-Item -ItemType Directory -Force -Path $menuDir | Out-Null
    $menuShortcut = Join-Path $menuDir "OM0RX Radio Control Agent.lnk"
    New-AgentShortcut -ShortcutPath $menuShortcut
    $created += $menuShortcut
}

Write-Host "Created shortcut(s):" -ForegroundColor Green
$created | ForEach-Object { Write-Host "  $_" }
