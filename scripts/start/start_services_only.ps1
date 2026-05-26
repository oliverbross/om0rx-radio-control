param(
    [ValidateSet("local", "development")]
    [string]$AppEnv = "local",
    [string]$BackendHost = "127.0.0.1",
    [int]$BackendPort = 8000,
    [switch]$Reload
)

# Quick Start: WSJT-X Bridge + Backend Only (No Launcher)
# Use this for testing without the native windows launcher.

if ($env:APP_ENV) {
    if ($env:APP_ENV -notin @("local", "development")) {
        throw "APP_ENV must be 'local' or 'development'. Current value: $env:APP_ENV"
    }
    $AppEnv = $env:APP_ENV
}

if ($env:BACKEND_HOST) {
    $BackendHost = $env:BACKEND_HOST
}

if ($env:BACKEND_PORT) {
    $BackendPort = [int]$env:BACKEND_PORT
}

$EnableReload = $Reload.IsPresent -or $AppEnv -eq "development" -or $env:UVICORN_RELOAD -in @("1", "true", "yes", "on")
$BackendProbeHost = if ($BackendHost -eq "0.0.0.0") { "127.0.0.1" } else { $BackendHost }
$BackendUrl = "http://${BackendProbeHost}:$BackendPort"

function Stop-StartedProcess {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Name
    )

    if (-not $Process -or $Process.HasExited) {
        return
    }

    try {
        $closed = $Process.CloseMainWindow()
        if ($closed -and $Process.WaitForExit(5000)) {
            Write-Host "✅ $Name stopped" -ForegroundColor Green
            return
        }
    }
    catch {
        # Fall back to forced termination below.
    }

    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    Write-Host "✅ $Name stopped" -ForegroundColor Green
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         WSJT-X Bridge + Backend Server               ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mode: $AppEnv | Backend: $BackendUrl | Reload: $EnableReload" -ForegroundColor Cyan
Write-Host ""

# Clean up any existing processes
Write-Host "🧹 Cleaning up old processes..." -ForegroundColor Yellow
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$bridgeScript = Join-Path $ProjectRoot "bridge\sdc-bridge-server.js"

# Step 1: Start WSJT-X Bridge Server
Write-Host "📡 Step 1: Starting WSJT-X bridge server..." -ForegroundColor Yellow
$bridgeProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ProjectRoot'; `$env:TCP_HOST='127.0.0.1'; `$env:TCP_PORT='12166'; `$env:WSJTX_UDP_PORT='2237'; `$env:WSJTX_UDP_MULTICAST='224.0.0.1'; `$env:WS_PORT='8091'; `$env:WSJTX_ENABLED='true'; node '$bridgeScript'" -PassThru
Write-Host "✅ Bridge process started (PID: $($bridgeProcess.Id))" -ForegroundColor Green
Start-Sleep -Seconds 2

# Step 2: Start backend in background
Write-Host "📡 Step 2: Starting backend server..." -ForegroundColor Yellow
$reloadArgs = if ($EnableReload) { " --reload" } else { "" }
$backendCommand = "Set-Location '$ProjectRoot'; `$env:APP_ENV='$AppEnv'; `$env:BACKEND_HOST='$BackendHost'; `$env:BACKEND_PORT='$BackendPort'; & python -m uvicorn backend.main:app --host $BackendHost --port $BackendPort$reloadArgs"
$backendProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand -PassThru
Write-Host "✅ Backend process started (PID: $($backendProcess.Id))" -ForegroundColor Green

# Wait for backend to be ready
Write-Host "⏳ Waiting for backend to be ready..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$backendReady = $false

while ($attempt -lt $maxAttempts -and -not $backendReady) {
    try {
        $socket = New-Object System.Net.Sockets.Socket([System.Net.Sockets.AddressFamily]::InterNetwork, [System.Net.Sockets.SocketType]::Stream, [System.Net.Sockets.ProtocolType]::Tcp)
        $socket.Connect($BackendProbeHost, $BackendPort)
        $socket.Close()
        $backendReady = $true
        Write-Host "✅ Backend is ready!" -ForegroundColor Green
    }
    catch {
        # Backend not ready yet
    }
    
    if (-not $backendReady) {
        Start-Sleep -Seconds 1
        $attempt++
        if ($attempt % 5 -eq 0) {
            Write-Host "   Still waiting... ($attempt/$maxAttempts)" -ForegroundColor Gray
        }
    }
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              Services Ready! ✅                        ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 Web Interface: $BackendUrl" -ForegroundColor Cyan
Write-Host "🔌 WebSocket Bridge: ws://localhost:8091" -ForegroundColor Cyan
Write-Host "📡 WSJT-X UDP Port: 2237 (multicast: 224.0.0.1)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Bridge PID: $($bridgeProcess.Id)" -ForegroundColor Gray
Write-Host "Backend PID: $($backendProcess.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop all services..." -ForegroundColor Yellow
Write-Host ""

# Wait for user to stop
$backendProcess.WaitForExit()

# Cleanup
Write-Host ""
Write-Host "🛑 Stopping services..." -ForegroundColor Yellow
Stop-StartedProcess -Process $bridgeProcess -Name "Bridge"
Stop-StartedProcess -Process $backendProcess -Name "Backend"
Write-Host "✅ All services stopped" -ForegroundColor Green
