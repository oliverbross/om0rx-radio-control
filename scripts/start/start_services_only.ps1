param(
    [ValidateSet("local", "development")]
    [string]$AppEnv = "local",
    [string]$BackendHost = "127.0.0.1",
    [int]$BackendPort = 8080,
    [switch]$Reload
)

# Quick Start: WSJT-X Bridge + Backend Only (No Launcher)
# This script is lifecycle-aware and can restart services when the backend API
# writes a restart request.

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

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$BridgeScript = Join-Path $ProjectRoot "bridge\sdc-bridge-server.js"
$LifecycleRequestPath = Join-Path $ProjectRoot "logs\app_lifecycle_request.json"

$EnableReload = $Reload.IsPresent -or $AppEnv -eq "development" -or $env:UVICORN_RELOAD -in @("1", "true", "yes", "on")
$BackendProbeHost = if ($BackendHost -eq "0.0.0.0") { "127.0.0.1" } else { $BackendHost }
$BackendUrl = "http://${BackendProbeHost}:$BackendPort"

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

function Test-ProtectedProcessId {
    param([int]$ProcessId)

    return (Get-ProtectedProcessIds) -contains $ProcessId
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    if ($ProcessId -le 0 -or (Test-ProtectedProcessId -ProcessId $ProcessId)) {
        return
    }

    $children = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ParentProcessId -eq $ProcessId })

    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-ProcessId {
    param(
        [int]$ProcessId,
        [string]$Reason
    )

    if ($ProcessId -le 0 -or (Test-ProtectedProcessId -ProcessId $ProcessId)) {
        return
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }

    Write-Host "🧹 Stopping stale process $ProcessId ($($process.ProcessName)): $Reason" -ForegroundColor Yellow
    Stop-ProcessTree -ProcessId $ProcessId
}

function Stop-ProcessesOnPort {
    param([int]$Port)

    $owners = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)

    foreach ($owner in $owners) {
        Stop-ProcessId -ProcessId $owner -Reason "port $Port is already in use"
    }
}

function Stop-KnownRuntimePorts {
    $ports = @($BackendPort, 8080, 8081, 8091, 12166, 2237) | Select-Object -Unique
    foreach ($port in $ports) {
        Stop-ProcessesOnPort -Port $port
    }
}

function Stop-ProjectProcesses {
    $patterns = @("start_services_only.ps1", "backend.main:app", "sdc-bridge-server.js")
    $protectedProcessIds = @(Get-ProtectedProcessIds)

    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $commandLine = $_.CommandLine
            $protectedProcessIds -notcontains [int]$_.ProcessId -and
            $commandLine -and
            (
                ($commandLine -match [regex]::Escape($ProjectRoot) -and ($patterns | Where-Object { $commandLine -like "*$_*" })) -or
                $commandLine -like "*backend.main:app*"
            )
        }

    foreach ($process in $processes) {
        Stop-ProcessId -ProcessId $process.ProcessId -Reason "previous project process"
    }
}

function Stop-StaleRuntime {
    Write-Host "🧹 Cleaning stale local runtime processes..." -ForegroundColor Yellow
    Stop-KnownRuntimePorts
    Stop-ProjectProcesses
    Start-Sleep -Seconds 2
}

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

    Stop-ProcessTree -ProcessId $Process.Id
    Write-Host "✅ $Name stopped" -ForegroundColor Green
}

function Clear-LifecycleRequest {
    Remove-Item -LiteralPath $LifecycleRequestPath -Force -ErrorAction SilentlyContinue
}

function Get-LifecycleAction {
    if (-not (Test-Path -LiteralPath $LifecycleRequestPath)) {
        return $null
    }

    try {
        $request = Get-Content -LiteralPath $LifecycleRequestPath -Raw | ConvertFrom-Json
        return $request.action
    }
    catch {
        Write-Host "⚠️ Could not read lifecycle request: $($_.Exception.Message)" -ForegroundColor Yellow
        return $null
    }
}

function Start-BridgeProcess {
    Write-Host "📡 Starting WSJT-X bridge server..." -ForegroundColor Yellow
    $bridgeCommand = "Set-Location '$ProjectRoot'; `$env:TCP_HOST='127.0.0.1'; `$env:TCP_PORT='12166'; `$env:WSJTX_UDP_PORT='2237'; `$env:WSJTX_UDP_MULTICAST='224.0.0.1'; `$env:WS_PORT='8091'; `$env:WSJTX_ENABLED='true'; & node '$BridgeScript'"
    $process = Start-Process powershell -ArgumentList "-NoProfile", "-Command", $bridgeCommand -WindowStyle Hidden -PassThru
    Write-Host "✅ Bridge process started (PID: $($process.Id))" -ForegroundColor Green
    Start-Sleep -Seconds 2
    return $process
}

function Start-BackendProcess {
    Write-Host "📡 Starting backend server..." -ForegroundColor Yellow
    $reloadArgs = if ($EnableReload) { " --reload" } else { "" }
    $reloadFlag = if ($EnableReload) { "1" } else { "0" }
    $backendCommand = "Set-Location '$ProjectRoot'; `$env:APP_ENV='$AppEnv'; `$env:APP_LIFECYCLE_SUPERVISOR='1'; `$env:APP_UVICORN_RELOAD='$reloadFlag'; `$env:BACKEND_HOST='$BackendHost'; `$env:BACKEND_PORT='$BackendPort'; & python -m uvicorn backend.main:app --host $BackendHost --port $BackendPort$reloadArgs"
    $process = Start-Process powershell -ArgumentList "-NoProfile", "-Command", $backendCommand -WindowStyle Hidden -PassThru
    Write-Host "✅ Backend process started (PID: $($process.Id))" -ForegroundColor Green
    return $process
}

function Wait-BackendReady {
    Write-Host "⏳ Waiting for backend to be ready..." -ForegroundColor Yellow
    $maxAttempts = 30
    $attempt = 0

    while ($attempt -lt $maxAttempts) {
        try {
            $socket = New-Object System.Net.Sockets.Socket([System.Net.Sockets.AddressFamily]::InterNetwork, [System.Net.Sockets.SocketType]::Stream, [System.Net.Sockets.ProtocolType]::Tcp)
            $socket.Connect($BackendProbeHost, $BackendPort)
            $socket.Close()
            Write-Host "✅ Backend is ready!" -ForegroundColor Green
            return $true
        }
        catch {
            Start-Sleep -Seconds 1
            $attempt++
            if ($attempt % 5 -eq 0) {
                Write-Host "   Still waiting... ($attempt/$maxAttempts)" -ForegroundColor Gray
            }
        }
    }

    return $false
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         WSJT-X Bridge + Backend Server               ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mode: $AppEnv | Backend: $BackendUrl | Reload: $EnableReload" -ForegroundColor Cyan
Write-Host ""

$bridgeProcess = $null
$backendProcess = $null

try {
    Clear-LifecycleRequest
    Stop-StaleRuntime

    $bridgeProcess = Start-BridgeProcess
    $backendProcess = Start-BackendProcess

    if (-not (Wait-BackendReady)) {
        Write-Host "❌ Backend failed to start after 30 seconds" -ForegroundColor Red
        exit 1
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
    Write-Host "Press Ctrl+C to stop all services..." -ForegroundColor Yellow
    Write-Host ""

    while ($true) {
        if ($backendProcess.HasExited) {
            $action = Get-LifecycleAction

            if ($action -eq "restart") {
                Write-Host "🔄 Restart request received from backend" -ForegroundColor Yellow
                Stop-StartedProcess -Process $bridgeProcess -Name "Bridge"
                Clear-LifecycleRequest

                $bridgeProcess = Start-BridgeProcess
                $backendProcess = Start-BackendProcess

                if (-not (Wait-BackendReady)) {
                    Write-Host "❌ Backend failed to restart after 30 seconds" -ForegroundColor Red
                    break
                }

                Write-Host "✅ Services restarted" -ForegroundColor Green
                continue
            }

            if ($action -eq "shutdown") {
                Write-Host "🛑 Shutdown request received from backend" -ForegroundColor Yellow
                break
            }

            Write-Host "⚠️ Backend process exited without a lifecycle request" -ForegroundColor Yellow
            break
        }

        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host ""
    Write-Host "🛑 Stopping managed processes..." -ForegroundColor Yellow
    Stop-StartedProcess -Process $backendProcess -Name "Backend"
    Stop-StartedProcess -Process $bridgeProcess -Name "Bridge"
    Stop-KnownRuntimePorts
    Stop-ProjectProcesses
    Clear-LifecycleRequest
    Write-Host "✅ All managed processes stopped" -ForegroundColor Green
}
