$ErrorActionPreference = "Stop"
$taskName = "OM0RX Remote Station Tray"
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$menuDirectory = Join-Path ([Environment]::GetFolderPath("Programs")) "OM0RX Remote Station"
$shortcutPath = Join-Path $menuDirectory "OM0RX Remote Station Agent.lnk"
Remove-Item -LiteralPath $shortcutPath -Force -ErrorAction SilentlyContinue
if ((Test-Path -LiteralPath $menuDirectory) -and -not (Get-ChildItem -LiteralPath $menuDirectory -Force)) {
    Remove-Item -LiteralPath $menuDirectory -Force
}
Write-Host "Removed tray task: $taskName"
Write-Host "Removed Start menu shortcut: $shortcutPath"
