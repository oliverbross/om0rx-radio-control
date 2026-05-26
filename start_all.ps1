param(
    [ValidateSet("local", "development")]
    [string]$AppEnv = "local",
    [string]$BackendHost = "127.0.0.1",
    [int]$BackendPort = 8000,
    [switch]$Reload
)

# FlexRadio Complete Startup - Backend + Bridge + Multi-Window Launcher
# This script starts backend, WSJT-X bridge, and launches the native windows.

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
Write-Host "║    FlexRadio Multi-Window Launcher + WSJT-X Bridge   ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mode: $AppEnv | Backend: $BackendUrl | Reload: $EnableReload" -ForegroundColor Cyan
Write-Host ""

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Step 1: Start WSJT-X Bridge Server
Write-Host "📡 Step 1: Starting WSJT-X bridge server..." -ForegroundColor Yellow
$bridgeScript = Join-Path $ProjectRoot "bridge\sdc-bridge-server.js"
$bridgeProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ProjectRoot'; `$env:TCP_HOST='127.0.0.1'; `$env:TCP_PORT='12166'; `$env:WSJTX_UDP_PORT='2237'; `$env:WSJTX_UDP_MULTICAST='224.0.0.1'; `$env:WS_PORT='8091'; `$env:WSJTX_ENABLED='true'; node '$bridgeScript'" -PassThru
Write-Host "✅ Bridge process started (PID: $($bridgeProcess.Id))" -ForegroundColor Green
Start-Sleep -Seconds 2

# Step 2: Start backend in background
Write-Host "📡 Step 2: Starting backend server..." -ForegroundColor Yellow
$reloadArgs = if ($EnableReload) { " --reload" } else { "" }
$backendCommand = "Set-Location '$ProjectRoot'; `$env:APP_ENV='$AppEnv'; `$env:BACKEND_HOST='$BackendHost'; `$env:BACKEND_PORT='$BackendPort'; & python -m uvicorn backend.main:app --host $BackendHost --port $BackendPort$reloadArgs"
$backendProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand -PassThru
Write-Host "✅ Backend process started (PID: $($backendProcess.Id))" -ForegroundColor Green

# Wait for backend to be ready (socket-based check - more reliable)
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

if (-not $backendReady) {
    Write-Host "❌ Backend failed to start after $maxAttempts seconds" -ForegroundColor Red
    Write-Host "Check the backend window for errors" -ForegroundColor Red
    Write-Host ""
    Write-Host "Backend window shows these errors:" -ForegroundColor Yellow
    Write-Host "   • pythonnet compatibility issues" -ForegroundColor White
    Write-Host "   • Missing dependencies" -ForegroundColor White
    Write-Host "   • Configuration errors" -ForegroundColor White
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "✅ WSJT-X Bridge connected on WebSocket :8091" -ForegroundColor Green
Write-Host "✅ Backend available at $BackendUrl" -ForegroundColor Green
Write-Host ""
Write-Host "🚀 Step 3: Launching native windows..." -ForegroundColor Yellow
Write-Host ""

# Step 3: Launch windows
$env:APP_ENV = $AppEnv
$env:BACKEND_HOST = $BackendHost
$env:BACKEND_PORT = [string]$BackendPort
& python (Join-Path $ProjectRoot "scripts\launch\launch_windows.py")

# Cleanup
Write-Host ""
Write-Host "🛑 Stopping services..." -ForegroundColor Yellow
Stop-StartedProcess -Process $bridgeProcess -Name "Bridge"
Stop-StartedProcess -Process $backendProcess -Name "Backend"
Write-Host "✅ All services stopped" -ForegroundColor Green
