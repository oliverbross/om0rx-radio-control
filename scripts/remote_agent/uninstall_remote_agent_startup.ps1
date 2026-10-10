$ErrorActionPreference = "Stop"
$taskName = "OM0RX Remote Station Agent"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Removed scheduled task: $taskName"

