param(
    [string]$Config = "",
    [string]$Python = "python.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$trayScript = (Resolve-Path (Join-Path $PSScriptRoot "run_remote_agent_tray.ps1")).Path
$taskName = "OM0RX Remote Station Tray"
$arguments = "-NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$trayScript`" -Python `"$Python`""
if ($Config) { $arguments += " -Config `"$Config`"" }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "OM0RX Remote Station Agent status and process-control tray" -Force | Out-Null

$programs = [Environment]::GetFolderPath("Programs")
$menuDirectory = Join-Path $programs "OM0RX Remote Station"
$shortcutPath = Join-Path $menuDirectory "OM0RX Remote Station Agent.lnk"
$iconPath = Join-Path $projectRoot "tools\Om0rxAgent\assets\om0rx-agent.ico"
New-Item -ItemType Directory -Force -Path $menuDirectory | Out-Null
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = (Join-Path $PSHOME "powershell.exe")
$shortcut.Arguments = "$arguments -ShowDetails"
$shortcut.WorkingDirectory = $projectRoot
if (Test-Path -LiteralPath $iconPath) {
    $shortcut.IconLocation = "$iconPath,0"
}
$shortcut.Description = "Open the OM0RX Remote Station Agent"
$shortcut.Save()

Start-ScheduledTask -TaskName $taskName
Write-Host "Installed and started tray task: $taskName"
Write-Host "Installed Start menu shortcut: $shortcutPath"
