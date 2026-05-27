param(
    [string]$BackendHost = "127.0.0.1",
    [int]$BackendPort = 8080
)

# FlexRadio Chrome App Mode Launcher
# Launches three windows in Chrome app mode (no URL bar, native-like appearance)

Write-Host ""
Write-Host "╔════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     OM0RX Radio Control Launcher      ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

if ($env:BACKEND_HOST) {
    $BackendHost = $env:BACKEND_HOST
}

if ($env:BACKEND_PORT) {
    $BackendPort = [int]$env:BACKEND_PORT
}

$BackendProbeHost = if ($BackendHost -eq "0.0.0.0") { "127.0.0.1" } else { $BackendHost }
$BackendUrl = "http://${BackendProbeHost}:$BackendPort"

# Check if backend is running
Write-Host "🔍 Checking backend..." -ForegroundColor Yellow
$backendReady = $false
for ($i = 0; $i -lt 5; $i++) {
    try {
        $socket = New-Object System.Net.Sockets.TcpClient
        $socket.Connect($BackendProbeHost, $BackendPort)
        if ($socket.Connected) {
            $backendReady = $true
            $socket.Close()
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $backendReady) {
    Write-Host "❌ Backend is not running!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please start the backend first:" -ForegroundColor Yellow
    Write-Host "   .\start_all.ps1" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "✅ Backend is ready!" -ForegroundColor Green
Write-Host ""

# Find Chrome
$chromeExe = $null
$chromePaths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

foreach ($path in $chromePaths) {
    if (Test-Path $path) {
        $chromeExe = $path
        break
    }
}

if (-not $chromeExe) {
    Write-Host "❌ Google Chrome not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Google Chrome from: https://www.google.com/chrome/" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "🚀 Launching 3 windows in Chrome App Mode (no URL bar)" -ForegroundColor Green
Write-Host ""

# Define windows configuration
$windows = @(
    @{
        title = "OM0RX Radio Control"
        url = "$BackendUrl/radio-control.html"
        x = 100
        y = 100
        width = 1000
        height = 600
    },
    @{
        title = "OM0RX Radio Control - Logging & QRZ"
        url = "$BackendUrl/logging.html"
        x = 1150
        y = 100
        width = 1200
        height = 700
    },
    @{
        title = "OM0RX Radio Control - DX Spots"
        url = "$BackendUrl/spots.html"
        x = 150
        y = 750
        width = 1400
        height = 800
    }
)

# Launch each window
$processes = @()
foreach ($window in $windows) {
    $args = @(
        "--app=$($window.url)",
        "--window-position=$($window.x),$($window.y)",
        "--window-size=$($window.width),$($window.height)",
        "--no-first-run",
        "--no-default-browser-check"
    )
    
    Write-Host "📍 Launching: $($window.title)" -ForegroundColor Cyan
    $proc = Start-Process -FilePath $chromeExe -ArgumentList $args -PassThru
    $processes += $proc
    Start-Sleep -Milliseconds 300
}

Write-Host ""
Write-Host "✅ All windows launched!" -ForegroundColor Green
Write-Host ""
Write-Host "💡 Features:" -ForegroundColor Yellow
Write-Host "   • No URL bar in App Mode" -ForegroundColor White
Write-Host "   • All windows sync in real-time" -ForegroundColor White
Write-Host "   • Resize and arrange windows as needed" -ForegroundColor White
Write-Host ""
Write-Host "⏳ Waiting for windows to close..." -ForegroundColor Gray
Write-Host ""

# Wait for all windows to close
foreach ($proc in $processes) {
    try {
        $proc.WaitForExit()
    }
    catch {
        # Window already closed
    }
}

Write-Host "👋 All windows closed" -ForegroundColor Green
