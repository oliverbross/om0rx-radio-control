#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Fix DuckDB schema issue - drops and recreates database with correct schema
    
.DESCRIPTION
    The qso_records table was created without a DEFAULT value for the id column.
    This script deletes the database file so it can be recreated with the fixed schema.
    
.NOTES
    IMPORTANT: Stop the backend before running this script!
#>

Write-Host "🔧 DuckDB Schema Fix Script" -ForegroundColor Cyan
Write-Host "=" * 50

# Check if backend is running
$backendProcess = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*backend*main.py*" -or $_.CommandLine -like "*uvicorn*"
}

if ($backendProcess) {
    Write-Host "⚠️  WARNING: Backend appears to be running!" -ForegroundColor Yellow
    Write-Host "   Please stop the backend (Ctrl+C) before continuing." -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne "y" -and $continue -ne "Y") {
        Write-Host "❌ Aborted." -ForegroundColor Red
        exit 1
    }
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$dbPath = Join-Path $ProjectRoot "data\qso_log.duckdb"

Write-Host ""
Write-Host "🗂️  Database location: $dbPath"

if (Test-Path $dbPath) {
    Write-Host "✅ Found existing database"
    Write-Host ""
    Write-Host "This will DELETE the database and let it be recreated with the correct schema."
    Write-Host "All synced QSOs will be re-fetched from Wavelog (may take a few minutes)."
    Write-Host ""
    $confirm = Read-Host "Are you sure you want to delete the database? (yes/no)"
    
    if ($confirm -eq "yes") {
        try {
            Remove-Item $dbPath -Force
            Write-Host "✅ Database deleted successfully!" -ForegroundColor Green
            Write-Host ""
            Write-Host "📝 Next steps:" -ForegroundColor Cyan
            Write-Host "   1. Start the backend: .\start_all.ps1"
            Write-Host "   2. Watch logs for sync progress"
            Write-Host "   3. Sync will complete in a few minutes"
        }
        catch {
            Write-Host "❌ Error deleting database: $_" -ForegroundColor Red
            Write-Host ""
            Write-Host "💡 Try:" -ForegroundColor Yellow
            Write-Host "   1. Make sure backend is stopped"
            Write-Host "   2. Close any database tools viewing the file"
            Write-Host "   3. Run this script again"
            exit 1
        }
    }
    else {
        Write-Host "❌ Cancelled." -ForegroundColor Yellow
    }
}
else {
    Write-Host "ℹ️  Database doesn't exist - it will be created automatically" -ForegroundColor Cyan
    Write-Host "   when you start the backend."
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
