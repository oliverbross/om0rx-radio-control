param(
    [string]$Python = "python.exe",
    [string]$Config = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runScript = (Resolve-Path (Join-Path $PSScriptRoot "run_remote_agent.ps1")).Path
$taskName = "OM0RX Remote Station Agent"
$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runScript`" -Python `"$Python`""
if ($Config) { $arguments += " -Config `"$Config`"" }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Independent FLEX-8400/KPA500/KAT500 remote station agent" -Force | Out-Null
Write-Host "Installed scheduled task: $taskName"

