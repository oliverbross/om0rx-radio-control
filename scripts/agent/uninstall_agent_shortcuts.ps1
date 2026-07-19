param(
    [switch]$DesktopOnly,
    [switch]$StartMenuOnly
)

$ErrorActionPreference = "Stop"
$removed = @()

if (-not $StartMenuOnly) {
    $desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "OM0RX Radio Control Agent.lnk"
    if (Test-Path -LiteralPath $desktopShortcut) {
        Remove-Item -LiteralPath $desktopShortcut -Force
        $removed += $desktopShortcut
    }
}

if (-not $DesktopOnly) {
    $menuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "OM0RX Radio Control"
    $menuShortcut = Join-Path $menuDir "OM0RX Radio Control Agent.lnk"
    if (Test-Path -LiteralPath $menuShortcut) {
        Remove-Item -LiteralPath $menuShortcut -Force
        $removed += $menuShortcut
    }

    if ((Test-Path -LiteralPath $menuDir) -and -not (Get-ChildItem -LiteralPath $menuDir -Force -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $menuDir -Force
    }
}

if ($removed.Count -eq 0) {
    Write-Host "No OM0RX Agent shortcuts were found." -ForegroundColor Yellow
}
else {
    Write-Host "Removed shortcut(s):" -ForegroundColor Green
    $removed | ForEach-Object { Write-Host "  $_" }
}
