# FlexRadio Web Control v2.0 - Startup Script
# This script starts both the FastAPI backend and SDC bridge server

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   FlexRadio Web Control v2.0" -ForegroundColor Cyan
Write-Host "   Complete Professional Interface" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory (project root)
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# ============= KILL PORT PROCESSES =============
Write-Host "🧹 Cleaning up ports..." -ForegroundColor Yellow
$portsToClean = @(2237, 8091, 8000, 12166)
foreach ($port in $portsToClean) {
    $processes = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if ($processes) {
        foreach ($proc in $processes) {
            try {
                Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue
                Write-Host "   ✓ Killed process on port $port (PID: $proc)" -ForegroundColor Green
            } catch {
                # Silent fail
            }
        }
    }
}

# Also kill any stray Node.js processes
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "✅ Ports cleaned" -ForegroundColor Green
Write-Host ""

# Check for Node.js
Write-Host "🔍 Checking Node.js installation..." -ForegroundColor Yellow
$nodeCheck = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ ERROR: Node.js is not installed" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Node.js from: https://nodejs.org/" -ForegroundColor Yellow
    Write-Host "Node.js is required for SDC Skimmer integration" -ForegroundColor White
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "✅ Node.js found: $nodeCheck" -ForegroundColor Green

# Install npm dependencies if needed
Write-Host "🔍 Checking npm dependencies..." -ForegroundColor Yellow
$packageJsonPath = Join-Path $ProjectRoot "package.json"
$nodeModulesPath = Join-Path $ProjectRoot "node_modules"

if (-not (Test-Path $nodeModulesPath)) {
    Write-Host "📦 Installing npm dependencies..." -ForegroundColor Yellow
    Push-Location $ProjectRoot
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "❌ ERROR: Failed to install npm dependencies" -ForegroundColor Red
        Write-Host ""
        Pop-Location
        Read-Host "Press Enter to exit"
        exit 1
    }
    Pop-Location
}
Write-Host "✅ npm dependencies ready" -ForegroundColor Green

# Detect local IP address
Write-Host "🔍 Detecting network configuration..." -ForegroundColor Yellow
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -eq 'Dhcp' } | Select-Object -First 1).IPAddress

if (-not $localIP) {
    $localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1).IPAddress
}

Write-Host ""
Write-Host "✅ READY TO START" -ForegroundColor Green
Write-Host ""
Write-Host "📡 Access URLs:" -ForegroundColor Cyan
Write-Host "   Desktop:    " -NoNewline -ForegroundColor White
Write-Host "http://localhost:8000" -ForegroundColor Green
if ($localIP) {
    Write-Host "   Mobile:     " -NoNewline -ForegroundColor White
    Write-Host "http://${localIP}:8000" -ForegroundColor Green
}
Write-Host ""

Write-Host "🎯 Features Available:" -ForegroundColor Cyan
Write-Host "   ✅ All radio controls (bands, modes, filters)" -ForegroundColor White
Write-Host "   ✅ S-Meter visualization" -ForegroundColor White
Write-Host "   ✅ AGC + DSP controls (NB, NR, ANF, APF)" -ForegroundColor White
Write-Host "   ✅ RX2 / SPLIT operation" -ForegroundColor White
Write-Host "   ✅ DX Spots with click-to-tune" -ForegroundColor White
Write-Host "   ✅ Real-time WebSocket sync" -ForegroundColor White
Write-Host "   ✅ SDC Decoded CW ticker (in CW mode)" -ForegroundColor Green
Write-Host "   ✅ WSJT-X Integration (FT8/FT4 auto-logging + auto-rotate)" -ForegroundColor Green
Write-Host ""

# Start Multi-Protocol Bridge Server (SDC + WSJT-X) in background
Write-Host "🚀 Starting Multi-Protocol Bridge Server (SDC + WSJT-X)..." -ForegroundColor Yellow
$bridgeScript = Join-Path $ProjectRoot "sdc-bridge-server.js"

# Set environment variables for WSJT-X integration
$env:TCP_HOST = "127.0.0.1"
$env:TCP_PORT = "12166"
$env:WSJTX_UDP_PORT = "2237"
$env:WSJTX_UDP_MULTICAST = "224.0.0.1"
$env:WS_PORT = "8091"
$env:WSJTX_ENABLED = "true"

$job = Start-Job -ScriptBlock {
    param($script, $root, $tcp_host, $tcp_port, $wsjtx_udp_port, $wsjtx_multicast, $ws_port, $wsjtx_enabled)
    
    # Set environment variables in the job context
    $env:TCP_HOST = $tcp_host
    $env:TCP_PORT = $tcp_port
    $env:WSJTX_UDP_PORT = $wsjtx_udp_port
    $env:WSJTX_UDP_MULTICAST = $wsjtx_multicast
    $env:WS_PORT = $ws_port
    $env:WSJTX_ENABLED = $wsjtx_enabled
    
    Set-Location $root
    & node $script
} -ArgumentList $bridgeScript, $ProjectRoot, $env:TCP_HOST, $env:TCP_PORT, $env:WSJTX_UDP_PORT, $env:WSJTX_UDP_MULTICAST, $env:WS_PORT, $env:WSJTX_ENABLED -Name "Bridge-Server"

# Give it a moment to start
Start-Sleep -Seconds 2

# Check if job started successfully
$jobStatus = Get-Job -Name "Bridge-Server" -ErrorAction SilentlyContinue
if ($jobStatus -and $jobStatus.State -eq "Running") {
    Write-Host "✅ Multi-Protocol Bridge Server started (Job ID: $($jobStatus.Id))" -ForegroundColor Green
    Write-Host "   SDC WebSocket: ws://localhost:8091" -ForegroundColor Cyan
    Write-Host "   WSJT-X UDP: listening on port 2237" -ForegroundColor Cyan
} elseif ($jobStatus -and $jobStatus.State -eq "Failed") {
    Write-Host "⚠️  Bridge Server failed to start - check configuration" -ForegroundColor Yellow
    Write-Host "   (This is optional - the app will still work without it)" -ForegroundColor Yellow
} else {
    Write-Host "✅ Multi-Protocol Bridge Server started in background" -ForegroundColor Green
}

Write-Host ""
Write-Host "🚀 Starting FastAPI backend server..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Start the server
# Note: --reload-exclude="config.py" prevents file watcher from restarting when config is modified
try {
    python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude="config.py"
}
catch {
    Write-Host ""
    Write-Host "❌ ERROR: Failed to start server" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Make sure Python is installed: python --version" -ForegroundColor White
    Write-Host "2. Install dependencies: pip install -r documentation/requirements.txt" -ForegroundColor White
    Write-Host "3. Check config.py for correct FlexRadio IP" -ForegroundColor White
    Write-Host ""
    Write-Host "Stopping Bridge Server..." -ForegroundColor Yellow
    Get-Job -Name "Bridge-Server" -ErrorAction SilentlyContinue | Stop-Job
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
finally {
    # Cleanup: Stop the Bridge job when Python server exits
    Write-Host ""
    Write-Host "Stopping Multi-Protocol Bridge Server..." -ForegroundColor Yellow
    Get-Job -Name "Bridge-Server" -ErrorAction SilentlyContinue | Stop-Job
    Get-Job -Name "Bridge-Server" -ErrorAction SilentlyContinue | Remove-Job
    Write-Host "✅ Cleanup complete" -ForegroundColor Green
}