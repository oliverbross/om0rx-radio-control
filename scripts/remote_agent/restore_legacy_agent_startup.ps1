$ErrorActionPreference = "Stop"
$remoteTaskName = "OM0RX Remote Station Agent"
$remoteTask = Get-ScheduledTask -TaskName $remoteTaskName -ErrorAction SilentlyContinue
if ($remoteTask -and $remoteTask.State -ne "Disabled") {
    throw "Disable or uninstall the '$remoteTaskName' scheduled task before restoring legacy startup. The remote tray task may remain enabled."
}

$migrationKey = "HKCU:\Software\OM0RX\StationControllerMigration"
$legacyRunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$legacyValueName = "OM0RX Radio Control Agent"
$legacyCommand = (Get-ItemProperty -LiteralPath $migrationKey -Name "LegacyRunCommand" -ErrorAction SilentlyContinue).LegacyRunCommand
if (-not $legacyCommand) {
    throw "No backed-up legacy startup command was found. Nothing was changed."
}

Set-ItemProperty -LiteralPath $legacyRunKey -Name $legacyValueName -Value ([string]$legacyCommand)
Write-Host "Restored legacy startup entry: $legacyValueName"
