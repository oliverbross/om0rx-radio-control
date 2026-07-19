param(
    [ValidateSet("local", "development")]
    [string]$AppEnv = "local",
    [string]$BackendHost = "127.0.0.1",
    [int]$BackendPort = 8080,
    [switch]$Reload
)

# FlexRadio Web Control v2.0 - Startup Script
# This script starts both the FastAPI backend and SDC bridge server.

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

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   FlexRadio Web Control v2.0" -ForegroundColor Cyan
Write-Host "   Complete Professional Interface" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mode: $AppEnv | Backend: $BackendUrl | Reload: $EnableReload" -ForegroundColor Cyan
Write-Host ""

# Get project root from scripts/start/
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

function Get-ProtectedProcessIds {
    $protectedIds = @([int]$PID)
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $PID" -ErrorAction SilentlyContinue

    while ($current -and $current.ParentProcessId) {
        $parentId = [int]$current.ParentProcessId
        if ($parentId -le 0 -or $protectedIds -contains $parentId) {
            break
        }

        $protectedIds += $parentId
        $current = Get-CimInstance Win32_Process -Filter "ProcessId = $parentId" -ErrorAction SilentlyContinue
    }

    return $protectedIds
}

# ============= KILL STALE RUNTIME PROCESSES =============
Write-Host "🧹 Cleaning up ports..." -ForegroundColor Yellow
$protectedProcessIds = @(Get-ProtectedProcessIds)
$portsToClean = @(2237, 8091, 8092, 12166, $BackendPort, 8080, 8081) | Select-Object -Unique
foreach ($port in $portsToClean) {
    $processes = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if ($processes) {
        foreach ($proc in $processes) {
            if ($protectedProcessIds -contains [int]$proc) {
                continue
            }

            $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $proc" -ErrorAction SilentlyContinue
            if (-not $owner.CommandLine -or $owner.CommandLine -notmatch [regex]::Escape($ProjectRoot)) {
                throw "Port $port is owned by unrelated PID $proc ($($owner.Name)). Stop it manually or choose another port."
            }
            Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue
            Write-Host "   ✓ Stopped owned process on port $port (PID: $proc)" -ForegroundColor Green
        }
    }
}

# Also kill duplicate OM0RX backend processes that may hold DuckDB locks even
# when they are not bound to the selected backend port.
$backendProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $protectedProcessIds -notcontains [int]$_.ProcessId -and
        $_.CommandLine -and
        $_.CommandLine -match [regex]::Escape($ProjectRoot) -and
        $_.CommandLine -like "*backend.main:app*"
    }

foreach ($process in $backendProcesses) {
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "   ✓ Killed stale backend process (PID: $($process.ProcessId))" -ForegroundColor Green
    } catch {
        # Silent fail
    }
}

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
Write-Host $BackendUrl -ForegroundColor Green
if ($localIP -and $BackendHost -eq "0.0.0.0") {
    Write-Host "   Mobile:     " -NoNewline -ForegroundColor White
    Write-Host "http://${localIP}:$BackendPort" -ForegroundColor Green
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
$bridgeScript = Join-Path $ProjectRoot "bridge\sdc-bridge-server.js"

# Set environment variables for WSJT-X integration
$env:TCP_HOST = "127.0.0.1"
$env:TCP_PORT = "12166"
$env:WSJTX_UDP_PORT = "2237"
$env:WSJTX_UDP_MULTICAST = "224.0.0.1"
$env:WS_PORT = "8091"
$env:WSJTX_COMMAND_PORT = "8092"
$env:WSJTX_ENABLED = "true"
$localSecretsPath = Join-Path $ProjectRoot "settings\local_secrets.json"
if (-not $env:WSJTX_BRIDGE_TOKEN -and (Test-Path -LiteralPath $localSecretsPath)) {
    try {
        $localSecrets = Get-Content -LiteralPath $localSecretsPath -Raw | ConvertFrom-Json
        if ($localSecrets.WSJTX_BRIDGE_TOKEN) { $env:WSJTX_BRIDGE_TOKEN = [string]$localSecrets.WSJTX_BRIDGE_TOKEN }
    } catch { Write-Warning "Could not read the local bridge token; bridge commands will remain loopback-only." }
}

$job = Start-Job -ScriptBlock {
    param($script, $root, $tcp_host, $tcp_port, $wsjtx_udp_port, $wsjtx_multicast, $ws_port, $wsjtx_command_port, $wsjtx_enabled, $bridge_token)
    
    # Set environment variables in the job context
    $env:TCP_HOST = $tcp_host
    $env:TCP_PORT = $tcp_port
    $env:WSJTX_UDP_PORT = $wsjtx_udp_port
    $env:WSJTX_UDP_MULTICAST = $wsjtx_multicast
    $env:WS_PORT = $ws_port
    $env:WSJTX_COMMAND_PORT = $wsjtx_command_port
    $env:WSJTX_ENABLED = $wsjtx_enabled
    $env:WSJTX_BRIDGE_TOKEN = $bridge_token
    
    Set-Location $root
    & node $script
} -ArgumentList $bridgeScript, $ProjectRoot, $env:TCP_HOST, $env:TCP_PORT, $env:WSJTX_UDP_PORT, $env:WSJTX_UDP_MULTICAST, $env:WS_PORT, $env:WSJTX_COMMAND_PORT, $env:WSJTX_ENABLED, $env:WSJTX_BRIDGE_TOKEN -Name "Bridge-Server"

# Give it a moment to start
Start-Sleep -Seconds 2

# Check if job started successfully
$jobStatus = Get-Job -Name "Bridge-Server" -ErrorAction SilentlyContinue
if ($jobStatus -and $jobStatus.State -eq "Running") {
    Write-Host "✅ Multi-Protocol Bridge Server started (Job ID: $($jobStatus.Id))" -ForegroundColor Green
    Write-Host "   SDC WebSocket: ws://localhost:8091" -ForegroundColor Cyan
    Write-Host "   WSJT-X UDP: listening on port 2237" -ForegroundColor Cyan
    Write-Host "   WSJT-X Command API: http://127.0.0.1:8092/wsjtx/command" -ForegroundColor Cyan
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
try {
    $env:APP_ENV = $AppEnv
    $env:BACKEND_HOST = $BackendHost
    $env:BACKEND_PORT = [string]$BackendPort

    $uvicornArgs = @("-m", "uvicorn", "backend.main:app", "--host", $BackendHost, "--port", $BackendPort)
    if ($EnableReload) {
        $uvicornArgs += "--reload"
    }

    python @uvicornArgs
}
catch {
    Write-Host ""
    Write-Host "❌ ERROR: Failed to start server" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Make sure Python is installed: python --version" -ForegroundColor White
    Write-Host "2. Install dependencies: pip install -r requirements.txt" -ForegroundColor White
    Write-Host "3. Check local settings or config_local.py for correct FlexRadio IP" -ForegroundColor White
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
