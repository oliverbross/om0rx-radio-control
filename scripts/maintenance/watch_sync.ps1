#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Watch Wavelog sync progress in real-time
#>

Write-Host "🔍 Watching Wavelog Sync Progress..." -ForegroundColor Cyan
Write-Host "   Log file: logs\flex_debug.log"
Write-Host "   Press Ctrl+C to stop watching"
Write-Host ""

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logPath = Join-Path $ProjectRoot "logs\flex_debug.log"

Get-Content $logPath -Tail 20 -Wait | ForEach-Object {
    if ($_ -match "sync|Batch|Wavelog|📥|✅|🔄|❌") {
        # Color code different message types
        if ($_ -match "✅") {
            Write-Host $_ -ForegroundColor Green
        }
        elseif ($_ -match "❌|Error|ERROR|Failed") {
            Write-Host $_ -ForegroundColor Red
        }
        elseif ($_ -match "⚠️|WARNING|WARN") {
            Write-Host $_ -ForegroundColor Yellow
        }
        elseif ($_ -match "🔄|Starting|Fetched") {
            Write-Host $_ -ForegroundColor Cyan
        }
        else {
            Write-Host $_
        }
    }
}
