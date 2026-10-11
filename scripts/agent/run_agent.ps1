param(
    [int]$Port = 8080,
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [switch]$NoAutostart
)

$ErrorActionPreference = "Stop"
$AgentProject = Join-Path $ProjectRoot "tools\Om0rxAgent\Om0rxAgent.csproj"
$argsList = @("--project-root", $ProjectRoot, "--port", "$Port", "--launch-source", "powershell-launcher")
if ($NoAutostart) {
    $argsList += "--no-autostart"
}

& dotnet run --project $AgentProject -c Release -- $argsList
