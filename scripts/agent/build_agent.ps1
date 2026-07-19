param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$Publish
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$AgentProject = Join-Path $ProjectRoot "tools\Om0rxAgent\Om0rxAgent.csproj"

& (Join-Path $PSScriptRoot "generate_agent_icon.ps1") -ProjectRoot $ProjectRoot

if ($Publish) {
    dotnet publish $AgentProject -c $Configuration -r win-x64 --self-contained false
}
else {
    dotnet build $AgentProject -c $Configuration
}
