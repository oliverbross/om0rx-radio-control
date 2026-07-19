param(
    [ValidateSet("local", "development")]
    [string]$AppEnv = "local",
    [string]$BackendHost = "127.0.0.1",
    [Alias("Port")]
    [int]$BackendPort = 8080,
    [switch]$Reload,
    [switch]$NoLauncher
)

# FlexRadio Complete Startup - Backend + Bridge + Multi-Window Launcher
# This script owns local process lifecycle. Backend restart/shutdown endpoints
# write a lifecycle request and exit; this supervisor decides what restarts.

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

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalSecretsPath = Join-Path $ProjectRoot "settings\local_secrets.json"
if (-not $env:WSJTX_BRIDGE_TOKEN -and (Test-Path -LiteralPath $LocalSecretsPath)) {
    try {
        $LocalSecrets = Get-Content -LiteralPath $LocalSecretsPath -Raw | ConvertFrom-Json
        if ($LocalSecrets.WSJTX_BRIDGE_TOKEN) { $env:WSJTX_BRIDGE_TOKEN = [string]$LocalSecrets.WSJTX_BRIDGE_TOKEN }
    } catch { Write-Warning "Could not read the local bridge token; bridge commands will remain loopback-only." }
}
$LogDir = Join-Path $ProjectRoot "logs"
$BridgeScript = Join-Path $ProjectRoot "bridge\sdc-bridge-server.js"
$LauncherScript = Join-Path $ProjectRoot "scripts\launch\launch_windows.py"
$LifecycleRequestPath = Join-Path $ProjectRoot "logs\app_lifecycle_request.json"
$BackendStdoutLog = Join-Path $LogDir "start_all-backend.out.log"
$BackendStderrLog = Join-Path $LogDir "start_all-backend.err.log"
$BridgeStdoutLog = Join-Path $LogDir "start_all-bridge.out.log"
$BridgeStderrLog = Join-Path $LogDir "start_all-bridge.err.log"
$LauncherStdoutLog = Join-Path $LogDir "start_all-launcher.out.log"
$LauncherStderrLog = Join-Path $LogDir "start_all-launcher.err.log"

$EnableReload = $Reload.IsPresent -or $AppEnv -eq "development" -or $env:UVICORN_RELOAD -in @("1", "true", "yes", "on")
$BackendProbeHost = if ($BackendHost -eq "0.0.0.0") { "127.0.0.1" } else { $BackendHost }
$BackendUrl = "http://${BackendProbeHost}:$BackendPort"
$BackendReadyMaxAttempts = 90

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Clear-StartupLogs {
    $logs = @(
        $BackendStdoutLog,
        $BackendStderrLog,
        $BridgeStdoutLog,
        $BridgeStderrLog,
        $LauncherStdoutLog,
        $LauncherStderrLog
    )

    foreach ($log in $logs) {
        Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
    }
}

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

function Test-ProjectOwnedProcessId {
    param([int]$ProcessId)

    $seen = @()
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    while ($current -and $seen -notcontains [int]$current.ProcessId) {
        $seen += [int]$current.ProcessId
        if ($current.CommandLine -and $current.CommandLine -match [regex]::Escape($ProjectRoot)) {
            return $true
        }

        $parentId = [int]$current.ParentProcessId
        if ($parentId -le 0) {
            break
        }
        $current = Get-CimInstance Win32_Process -Filter "ProcessId = $parentId" -ErrorAction SilentlyContinue
    }

    return $false
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

    $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)

    foreach ($owner in $owners) {
        $ownerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $owner" -ErrorAction SilentlyContinue
        if (-not (Test-ProjectOwnedProcessId -ProcessId $owner)) {
            throw "Port $Port is owned by unrelated PID $owner ($($ownerProcess.Name)). Stop it manually or choose another port."
        }
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
    $patterns = @("start_all.ps1", "backend.main:app", "sdc-bridge-server.js", "launch_windows.py")
    $protectedProcessIds = @(Get-ProtectedProcessIds)

    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $commandLine = $_.CommandLine
            $protectedProcessIds -notcontains [int]$_.ProcessId -and
            $commandLine -and
            (
                $commandLine -match [regex]::Escape($ProjectRoot) -and
                ($patterns | Where-Object { $commandLine -like "*$_*" })
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
    $process = Start-Process powershell -ArgumentList "-NoProfile", "-Command", $bridgeCommand -WindowStyle Hidden -PassThru -RedirectStandardOutput $BridgeStdoutLog -RedirectStandardError $BridgeStderrLog
    Write-Host "✅ Bridge process started (PID: $($process.Id))" -ForegroundColor Green
    Start-Sleep -Seconds 2
    return $process
}

function Start-BackendProcess {
    Write-Host "📡 Starting backend server..." -ForegroundColor Yellow
    $reloadArgs = if ($EnableReload) { " --reload" } else { "" }
    $reloadFlag = if ($EnableReload) { "1" } else { "0" }
    $backendCommand = "Set-Location '$ProjectRoot'; `$env:APP_ENV='$AppEnv'; `$env:APP_LIFECYCLE_SUPERVISOR='1'; `$env:APP_UVICORN_RELOAD='$reloadFlag'; `$env:BACKEND_HOST='$BackendHost'; `$env:BACKEND_PORT='$BackendPort'; & python -m uvicorn backend.main:app --host $BackendHost --port $BackendPort$reloadArgs"
    $process = Start-Process powershell -ArgumentList "-NoProfile", "-Command", $backendCommand -WindowStyle Hidden -PassThru -RedirectStandardOutput $BackendStdoutLog -RedirectStandardError $BackendStderrLog
    Write-Host "✅ Backend process started (PID: $($process.Id))" -ForegroundColor Green
    return $process
}

function Wait-BackendReady {
    Write-Host "⏳ Waiting for backend to be ready..." -ForegroundColor Yellow
    $attempt = 0

    while ($attempt -lt $BackendReadyMaxAttempts) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "$BackendUrl/api/health" -TimeoutSec 3 | Out-Null
            Write-Host "✅ Backend is ready!" -ForegroundColor Green
            return $true
        }
        catch {
            Start-Sleep -Seconds 1
            $attempt++
            if ($attempt % 5 -eq 0) {
                Write-Host "   Still waiting... ($attempt/$BackendReadyMaxAttempts)" -ForegroundColor Gray
            }
        }
    }

    return $false
}

function Start-LauncherProcess {
    Write-Host "🚀 Launching native windows..." -ForegroundColor Yellow
    $launcherCommand = "Set-Location '$ProjectRoot'; `$env:APP_ENV='$AppEnv'; `$env:BACKEND_HOST='$BackendHost'; `$env:BACKEND_PORT='$BackendPort'; & python '$LauncherScript'"
    $process = Start-Process powershell -ArgumentList "-NoProfile", "-Command", $launcherCommand -WindowStyle Hidden -PassThru -RedirectStandardOutput $LauncherStdoutLog -RedirectStandardError $LauncherStderrLog
    Write-Host "✅ Launcher process started (PID: $($process.Id))" -ForegroundColor Green
    return $process
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       OM0RX Radio Control + WSJT-X Bridge            ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mode: $AppEnv | Backend: $BackendUrl | Reload: $EnableReload" -ForegroundColor Cyan
Write-Host ""

$bridgeProcess = $null
$backendProcess = $null
$launcherProcess = $null

try {
    Clear-StartupLogs
    Clear-LifecycleRequest
    Stop-StaleRuntime

    $bridgeProcess = Start-BridgeProcess
    $backendProcess = Start-BackendProcess

    if (-not (Wait-BackendReady)) {
        Write-Host "❌ Backend failed to start after $BackendReadyMaxAttempts seconds" -ForegroundColor Red
        Write-Host "Check the application logs for configuration or dependency errors." -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    Write-Host "✅ WSJT-X Bridge connected on WebSocket :8091" -ForegroundColor Green
    Write-Host "✅ Backend available at $BackendUrl" -ForegroundColor Green
    Write-Host ""

    if (-not $NoLauncher.IsPresent) {
        $launcherProcess = Start-LauncherProcess
    }
    else {
        Write-Host "ℹ️ Launcher disabled. Open $BackendUrl in your browser." -ForegroundColor Cyan
    }

    $launcherStartedAt = Get-Date

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
                    Write-Host "❌ Backend failed to restart" -ForegroundColor Red
                    break
                }

                Write-Host "✅ Services restarted; existing windows can reconnect" -ForegroundColor Green
                continue
            }

            if ($action -eq "shutdown") {
                Write-Host "🛑 Shutdown request received from backend" -ForegroundColor Yellow
                break
            }

            Write-Host "⚠️ Backend process exited without a lifecycle request" -ForegroundColor Yellow
            break
        }

        if ($launcherProcess -and $launcherProcess.HasExited) {
            $launcherRuntime = ((Get-Date) - $launcherStartedAt).TotalSeconds
            if ($launcherProcess.ExitCode -ne 0) {
                Write-Host "⚠️ Launcher exited after $([math]::Round($launcherRuntime, 1))s; services will stay running." -ForegroundColor Yellow
                Write-Host "   Open $BackendUrl directly, or inspect:" -ForegroundColor Yellow
                Write-Host "   $LauncherStdoutLog" -ForegroundColor Gray
                Write-Host "   $LauncherStderrLog" -ForegroundColor Gray
            }
            else {
                Write-Host "👋 Launcher windows closed; background services remain available." -ForegroundColor Cyan
            }

            # The launcher owns desktop windows, not the service lifecycle. A
            # closed or failed window must never tear down a healthy backend.
            $launcherProcess = $null
            continue
        }

        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host ""
    Write-Host "🛑 Stopping managed processes..." -ForegroundColor Yellow
    Stop-StartedProcess -Process $backendProcess -Name "Backend"
    Stop-StartedProcess -Process $bridgeProcess -Name "Bridge"
    Stop-StartedProcess -Process $launcherProcess -Name "Launcher"
    Stop-KnownRuntimePorts
    Stop-ProjectProcesses
    Clear-LifecycleRequest
    Write-Host "✅ All managed processes stopped" -ForegroundColor Green
}
