Set-StrictMode -Version Latest

function Get-RuntimeCleanupPorts {
    param([Parameter(Mandatory = $true)][int]$BackendPort)

    # 12166 belongs to the external SDC TCP service and 2237 belongs to the
    # external WSJT-compatible UDP client.  A launcher must never treat either
    # endpoint as a process it owns.  8081 is likewise not part of this runtime.
    return @($BackendPort, 8080, 8091, 8092) | Select-Object -Unique
}

function Invoke-RuntimePortCleanup {
    param(
        [Parameter(Mandatory = $true)][int]$BackendPort,
        [Parameter(Mandatory = $true)][scriptblock]$StopPort
    )

    foreach ($port in @(Get-RuntimeCleanupPorts -BackendPort $BackendPort)) {
        & $StopPort $port
    }
}

function Invoke-DirectBridgeHalt {
    param(
        [string]$CommandUri = 'http://127.0.0.1:8092/wsjtx/command',
        [string]$StatusUri = '',
        [string]$BackendHaltUri = '',
        [string]$ControlToken = '',
        [ValidateRange(1, 10)][int]$TimeoutSec = 3,
        [ValidateRange(1000, 60000)][int]$MaxStatusAgeMs = 6000
    )

    $headers = @{}
    if ($ControlToken) {
        $headers['X-OM0RX-Control-Token'] = $ControlToken
    }

    $result = [ordered]@{
        direct_halt_accepted = $false
        direct_idle_confirmed = $false
        fallback_halt_accepted = $false
        backend_idle_confirmed = $false
        idle_confirmed = $false
        idle_confirmation_source = 'none'
        direct_error = $null
        status_error = $null
        fallback_error = $null
    }

    # The bridge exposes a single command endpoint.  Calling it first preserves
    # a transmit-off path even when the backend has already disappeared.
    try {
        $body = @{ command = 'halt_tx'; payload = @{ autoOnly = $false; reason = 'runtime-owner-revoked' } } | ConvertTo-Json -Compress -Depth 4
        $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $CommandUri -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec $TimeoutSec
        $payload = $response.Content | ConvertFrom-Json
        $result.direct_halt_accepted = ($payload.success -eq $true)
        if ($payload.PSObject.Properties.Name -contains 'idle_confirmed') {
            $result.idle_confirmed = ($payload.idle_confirmed -eq $true)
        }

        if (-not $StatusUri) {
            $StatusUri = $CommandUri -replace '/wsjtx/command$', '/wsjtx/status'
        }
        $statusDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSec)
        do {
            try {
                $statusResponse = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $StatusUri -Headers $headers -TimeoutSec 1
                $statusPayload = $statusResponse.Content | ConvertFrom-Json
                $stats = $statusPayload.stats
                $lastStatus = if ($stats) { $stats.lastStatus } else { $null }
                $statusAge = if ($stats -and $stats.lastStatusAgeMs -ne $null) { [double]$stats.lastStatusAgeMs } else { [double]::PositiveInfinity }
                $hasTransmitting = $lastStatus -and ($lastStatus.PSObject.Properties.Name -contains 'transmitting')
                $hasTxEnabled = $lastStatus -and ($lastStatus.PSObject.Properties.Name -contains 'txEnabled')
                $transmitIdle = $hasTransmitting -and ($lastStatus.transmitting -eq $false)
                $enableIdle = (-not $hasTxEnabled) -or ($lastStatus.txEnabled -eq $false)
                if ($statusAge -ge 0 -and $statusAge -le $MaxStatusAgeMs -and $transmitIdle -and $enableIdle) {
                    $result.direct_idle_confirmed = $true
                    $result.idle_confirmed = $true
                    $result.idle_confirmation_source = 'bridge-status'
                }
            }
            catch {
                $result.status_error = $_.Exception.Message
            }
            if (-not $result.direct_idle_confirmed -and [DateTime]::UtcNow -lt $statusDeadline) {
                Start-Sleep -Milliseconds 200
            }
        }
        while (-not $result.direct_idle_confirmed -and [DateTime]::UtcNow -lt $statusDeadline)
    }
    catch {
        $result.direct_error = $_.Exception.Message
    }

    # The backend path can provide a fresh RF-idle confirmation while it is
    # still alive.  It is only a fallback/confirmation path: direct bridge halt
    # above is always attempted first.
    if ($BackendHaltUri) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $BackendHaltUri -Headers $headers -TimeoutSec $TimeoutSec
            $payload = $response.Content | ConvertFrom-Json
            $result.fallback_halt_accepted = ($payload.success -eq $true -or $payload.command_accepted -eq $true)
            if ($payload.PSObject.Properties.Name -contains 'idle_confirmed') {
                $result.backend_idle_confirmed = ($payload.idle_confirmed -eq $true)
                if ($result.backend_idle_confirmed) {
                    # A fresh backend/Flex readback is authoritative when it is
                    # available.  A negative/unavailable fallback must not erase
                    # an already-fresh direct bridge idle proof.
                    $result.idle_confirmed = $true
                    $result.idle_confirmation_source = 'backend-flex'
                }
            }
        }
        catch {
            $result.fallback_error = $_.Exception.Message
        }
    }

    return [pscustomobject]$result
}

function Get-RuntimeProcessIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)]
        [string]$Role
    )

    try {
        $path = [System.IO.Path]::GetFullPath($Process.Path)
        $created = $Process.StartTime.ToUniversalTime().ToFileTimeUtc()
    }
    catch {
        throw "Could not establish $Role process identity for PID $($Process.Id): $($_.Exception.Message)"
    }

    return [ordered]@{
        role = $Role
        pid = [int]$Process.Id
        executable_path = $path
        creation_time_filetime = [long]$created
    }
}

function Test-RuntimeProcessIdentity {
    param([Parameter(Mandatory = $true)]$Identity)

    try {
        $process = Get-Process -Id ([int]$Identity.pid) -ErrorAction Stop
        $actual = Get-RuntimeProcessIdentity -Process $process -Role ([string]$Identity.role)
        return (
            [int]$actual.pid -eq [int]$Identity.pid -and
            [long]$actual.creation_time_filetime -eq [long]$Identity.creation_time_filetime -and
            [string]::Equals(
                [System.IO.Path]::GetFullPath([string]$actual.executable_path),
                [System.IO.Path]::GetFullPath([string]$Identity.executable_path),
                [System.StringComparison]::OrdinalIgnoreCase
            )
        )
    }
    catch {
        return $false
    }
}

function Get-RuntimePortOwnerIds {
    param([Parameter(Mandatory = $true)][int]$Port)

    return @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Test-RuntimePortOwner {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][int]$ProcessId
    )

    return (Get-RuntimePortOwnerIds -Port $Port) -contains $ProcessId
}

function Write-RuntimeOwnerManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$OwnerId,
        [Parameter(Mandatory = $true)][string]$State,
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Supervisor,
        [System.Diagnostics.Process]$Backend,
        [System.Diagnostics.Process]$Bridge,
        [Parameter(Mandatory = $true)][hashtable]$Ports,
        [string]$Reason = ""
    )

    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $manifest = [ordered]@{
        schema = 1
        owner_id = $OwnerId
        state = $State
        created_at = [DateTime]::UtcNow.ToString('o')
        updated_at = [DateTime]::UtcNow.ToString('o')
        supervisor = Get-RuntimeProcessIdentity -Process $Supervisor -Role 'supervisor'
        backend = if ($Backend) { Get-RuntimeProcessIdentity -Process $Backend -Role 'backend' } else { $null }
        bridge = if ($Bridge) { Get-RuntimeProcessIdentity -Process $Bridge -Role 'bridge' } else { $null }
        ports = [ordered]@{
            backend = [int]$Ports.backend
            bridge_ws = [int]$Ports.bridge_ws
            bridge_command = [int]$Ports.bridge_command
            bridge_tcp = [int]$Ports.bridge_tcp
            bridge_udp = [int]$Ports.bridge_udp
        }
        reason = $Reason
    }
    $temporary = Join-Path $directory ('.' + [System.IO.Path]::GetFileName($Path) + '.' + $OwnerId + '.tmp')
    $json = $manifest | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $Path) {
        $backup = $Path + '.replace.bak'
        [System.IO.File]::Replace($temporary, $Path, $backup, $true)
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    }
    else {
        [System.IO.File]::Move($temporary, $Path)
    }
    return $manifest
}

function Read-RuntimeOwnerManifest {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Test-RuntimeOwnerManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$OwnerId,
        [switch]$RequirePorts
    )

    $manifest = Read-RuntimeOwnerManifest -Path $Path
    if (-not $manifest -or [int]$manifest.schema -ne 1 -or [string]$manifest.owner_id -ne $OwnerId -or [string]$manifest.state -ne 'active') {
        return $false
    }
    if (-not $manifest.supervisor -or -not $manifest.backend -or -not $manifest.bridge) { return $false }
    if (-not (Test-RuntimeProcessIdentity -Identity $manifest.supervisor)) { return $false }
    if (-not (Test-RuntimeProcessIdentity -Identity $manifest.backend)) { return $false }
    if (-not (Test-RuntimeProcessIdentity -Identity $manifest.bridge)) { return $false }
    if ($RequirePorts) {
        if (-not (Test-RuntimePortOwner -Port ([int]$manifest.ports.backend) -ProcessId ([int]$manifest.backend.pid))) { return $false }
        if (-not (Test-RuntimePortOwner -Port ([int]$manifest.ports.bridge_ws) -ProcessId ([int]$manifest.bridge.pid))) { return $false }
        if (-not (Test-RuntimePortOwner -Port ([int]$manifest.ports.bridge_command) -ProcessId ([int]$manifest.bridge.pid))) { return $false }
    }
    return $true
}

function Enter-RuntimeOwnerLock {
    param([Parameter(Mandatory = $true)][string]$Path)

    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    try {
        return [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    }
    catch {
        throw "Another OM0RX runtime owner is active; parallel supervisors are forbidden."
    }
}

function Remove-RuntimeOwnerManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$OwnerId
    )

    $manifest = Read-RuntimeOwnerManifest -Path $Path
    if ($manifest -and [string]$manifest.owner_id -eq $OwnerId) {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    }
}
