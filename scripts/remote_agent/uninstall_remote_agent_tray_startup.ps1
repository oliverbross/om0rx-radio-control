$ErrorActionPreference = "Stop"
$taskName = "OM0RX Remote Station Tray"
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Removed tray task: $taskName"
