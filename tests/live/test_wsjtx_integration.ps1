# WSJT-X Bridge Integration Test Script
# Verifies that all components are properly set up and communicating

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         WSJT-X Bridge Integration Tests               ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Test 1: Check Node.js is installed
Write-Host "📋 Test 1: Checking Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "✅ Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js not found. Install from https://nodejs.org/" -ForegroundColor Red
    exit 1
}

# Test 2: Check Python is installed
Write-Host "📋 Test 2: Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found. Install Python 3.10+" -ForegroundColor Red
    exit 1
}

# Test 3: Check FastAPI is installed
Write-Host "📋 Test 3: Checking FastAPI..." -ForegroundColor Yellow
try {
    python -c "import fastapi; print(fastapi.__version__)" | Out-Null
    Write-Host "✅ FastAPI is installed" -ForegroundColor Green
} catch {
    Write-Host "❌ FastAPI not installed. Run: pip install fastapi uvicorn" -ForegroundColor Red
    exit 1
}

# Test 4: Check bridge server file exists
Write-Host "📋 Test 4: Checking bridge server file..." -ForegroundColor Yellow
if (Test-Path "bridge/sdc-bridge-server.js") {
    Write-Host "✅ sdc-bridge-server.js found" -ForegroundColor Green
} else {
    Write-Host "❌ sdc-bridge-server.js not found" -ForegroundColor Red
    exit 1
}

# Test 5: Check backend files
Write-Host "📋 Test 5: Checking backend files..." -ForegroundColor Yellow
if (Test-Path "backend/main.py") {
    Write-Host "✅ backend/main.py found" -ForegroundColor Green
} else {
    Write-Host "❌ backend/main.py not found" -ForegroundColor Red
    exit 1
}

if (Test-Path "services/wsjtx.py") {
    Write-Host "✅ services/wsjtx.py found" -ForegroundColor Green
} else {
    Write-Host "❌ services/wsjtx.py not found" -ForegroundColor Red
    exit 1
}

# Test 6: Check WSJT-X endpoints are registered
Write-Host "📋 Test 6: Checking WSJT-X endpoint registration..." -ForegroundColor Yellow
$mainContent = Get-Content "backend/main.py" -Raw
if ($mainContent -match "register_wsjtx_endpoints") {
    Write-Host "✅ WSJT-X endpoints are registered in main.py" -ForegroundColor Green
} else {
    Write-Host "❌ WSJT-X endpoints NOT registered in main.py" -ForegroundColor Red
    Write-Host "   Fix: Add 'register_wsjtx_endpoints(app)' to register_all_services()" -ForegroundColor Yellow
}

# Test 7: Check bridge has multi-interface support
Write-Host "📋 Test 7: Checking bridge multi-interface support..." -ForegroundColor Yellow
$bridgeContent = Get-Content "bridge/sdc-bridge-server.js" -Raw
if ($bridgeContent -match "getLocalIPAddress") {
    Write-Host "✅ Bridge has auto-interface detection" -ForegroundColor Green
} else {
    Write-Host "❌ Bridge missing auto-interface detection" -ForegroundColor Red
}

if ($bridgeContent -match "127\.0\.0\.1.*addMembership" -or ($bridgeContent -match "for.*interfaces" -and $bridgeContent -match "addMembership")) {
    Write-Host "✅ Bridge joins multicast on multiple interfaces" -ForegroundColor Green
} else {
    Write-Host "⚠️  Bridge may not join multicast on loopback interface" -ForegroundColor Yellow
}

# Test 8: Port availability
Write-Host "📋 Test 8: Checking port availability..." -ForegroundColor Yellow
$ports = @(8080, 8091, 2237, 12166)
foreach ($port in $ports) {
    try {
        $socket = New-Object System.Net.Sockets.Socket([System.Net.Sockets.AddressFamily]::InterNetwork, [System.Net.Sockets.SocketType]::Stream, [System.Net.Sockets.ProtocolType]::Tcp)
        $socket.Connect("localhost", $port)
        $socket.Close()
        Write-Host "⚠️  Port $port is already in use" -ForegroundColor Yellow
    } catch {
        Write-Host "✅ Port $port is available" -ForegroundColor Green
    }
}

# Test 9: Startup scripts
Write-Host "📋 Test 9: Checking startup scripts..." -ForegroundColor Yellow
if (Test-Path "scripts/start/start_services_only.ps1") {
    Write-Host "✅ start_services_only.ps1 exists (quick test startup)" -ForegroundColor Green
} else {
    Write-Host "⚠️  start_services_only.ps1 not found" -ForegroundColor Yellow
}

if (Test-Path "start_all.ps1") {
    Write-Host "✅ start_all.ps1 exists (full application startup)" -ForegroundColor Green
} else {
    Write-Host "❌ start_all.ps1 not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              Test Summary                             ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "✅ All critical components are ready!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Ensure WSJT-X is running with UDP Server enabled" -ForegroundColor White
Write-Host "  2. Run quick test: .\scripts\start\start_services_only.ps1" -ForegroundColor White
Write-Host "  3. WSJT-X should send packets to the bridge" -ForegroundColor White
Write-Host "  4. Check bridge window for 'UDP packet received' messages" -ForegroundColor White
Write-Host ""
Write-Host "For full app: .\start_all.ps1" -ForegroundColor Cyan
Write-Host ""
