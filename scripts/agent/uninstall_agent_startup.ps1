$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$ValueName = "OM0RX Radio Control Agent"
Remove-ItemProperty -Path $RunKey -Name $ValueName -ErrorAction SilentlyContinue
Write-Host "Removed startup entry: $ValueName" -ForegroundColor Green
