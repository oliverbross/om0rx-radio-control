#!/usr/bin/env pwsh
# Force DuckDB recreation with correct schema

Write-Host "`n🔧 Forcing DuckDB recreation with fixed schema..." -ForegroundColor Cyan

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$dbPath = Join-Path $ProjectRoot "data\qso_log.duckdb"
$walPath = "${dbPath}.wal"

# Check for running processes
$processesUsingDb = Get-Process | Where-Object {
    try {
        $_.Modules | Where-Object { $_.FileName -like "*$dbPath*" }
    } catch { $null }
}

if ($processesUsingDb) {
    Write-Host "❌ Database is in use by:" -ForegroundColor Red
    $processesUsingDb | ForEach-Object {
        Write-Host "   - $($_.ProcessName) (PID: $($_.Id))" -ForegroundColor Yellow
    }
    Write-Host "`n💡 Stop the backend first (Ctrl+C in the terminal running it)" -ForegroundColor Yellow
    exit 1
}

# Delete database files
if (Test-Path $dbPath) {
    Remove-Item $dbPath -Force
    Write-Host "✅ Deleted: $dbPath" -ForegroundColor Green
}

if (Test-Path $walPath) {
    Remove-Item $walPath -Force
    Write-Host "✅ Deleted: $walPath" -ForegroundColor Green
}

Write-Host "`n✨ Database cleared! Now restart the backend:" -ForegroundColor Cyan
Write-Host "   .\start_webapp.ps1" -ForegroundColor White
Write-Host "`n📊 The database will be recreated with the correct schema" -ForegroundColor Green
Write-Host "    and sync all ~41,826 QSOs in batches of 1000." -ForegroundColor Green
Write-Host "`n⏱️  This should take 3-5 minutes total.`n" -ForegroundColor Yellow
