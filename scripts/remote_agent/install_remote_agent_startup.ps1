param(
    [string]$Python = "python.exe",
    [string]$Config = "",
    [switch]$DisableLegacyStartup
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runScript = (Resolve-Path (Join-Path $PSScriptRoot "run_remote_agent.ps1")).Path
$taskName = "OM0RX Remote Station Agent"
$legacyRunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$legacyValueName = "OM0RX Radio Control Agent"
$migrationKey = "HKCU:\Software\OM0RX\StationControllerMigration"
$legacyCommand = (Get-ItemProperty -LiteralPath $legacyRunKey -Name $legacyValueName -ErrorAction SilentlyContinue).$legacyValueName
if ($legacyCommand -and -not $DisableLegacyStartup) {
    throw "The legacy HKCU Run entry '$legacyValueName' is enabled. Re-run with -DisableLegacyStartup to back it up and select the Python Remote Station Agent, or remove the conflicting startup entry explicitly."
}
if ($legacyCommand -and $DisableLegacyStartup) {
    New-Item -Path $migrationKey -Force | Out-Null
    Set-ItemProperty -LiteralPath $migrationKey -Name "LegacyRunCommand" -Value ([string]$legacyCommand)
    Remove-ItemProperty -LiteralPath $legacyRunKey -Name $legacyValueName
    Write-Host "Backed up and disabled legacy startup: $legacyValueName"
    Write-Host "Restore with scripts\remote_agent\restore_legacy_agent_startup.ps1 after disabling the remote controller task."
}
$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runScript`" -Python `"$Python`" -LaunchSource scheduled-task"
if ($Config) { $arguments += " -Config `"$Config`"" }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Independent FLEX-8400/KPA500/KAT500 remote station agent" -Force | Out-Null
Write-Host "Installed scheduled task: $taskName"

