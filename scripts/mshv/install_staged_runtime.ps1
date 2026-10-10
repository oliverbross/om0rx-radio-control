param(
    [Parameter(Mandatory = $true)][string]$StagedRuntime,
    [Parameter(Mandatory = $true)][string]$Destination,
    [Parameter(Mandatory = $true)][string]$WorkRoot
)

$ErrorActionPreference = 'Stop'
$allowedDestinationNames = @('runtime', 'phase1-runtime', 'phase2-runtime')
$allowedMutablePaths = @(
    '.history-import.lock','history-import.json','history-backups/**','log/**','logs/**',
    'settings/autodx.ini','settings/ms_*','settings/*.txt','settings/azel.dat',
    'settings/database/worked.db','settings/database/worked.db-*',
    'settings/database/wavelog_delta_state.json',
    'settings/database/award_hunting.json',
    'settings/database/dxpedition_watch.json',
    'settings/database/autodx_ignore.json',
    'settings/database/autodx_status_owner.json',
    'settings/database/lotw-users.txt','settings/database/confirmed-dxcc.txt','settings/database/us-states.txt',
    'settings/database/status-colors.ini',
    'settings/database/msloc_db*','settings/database/msbcn_db*',
    'settings/database/mstn_db*','settings/database/sat.dat'
)

function Assert-NoReparseAncestors([string]$Path) {
    $cursor = if (Test-Path -LiteralPath $Path) { Get-Item -LiteralPath $Path -Force } else { Get-Item -LiteralPath (Split-Path -Parent $Path) -Force }
    while ($null -ne $cursor) {
        if (($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Runtime path uses a reparse point: $($cursor.FullName)"
        }
        $cursor = $cursor.Parent
    }
}

function Assert-NoReparseTree([string]$Root) {
    $pending = [Collections.Generic.Queue[string]]::new()
    $pending.Enqueue($Root)
    while ($pending.Count) {
        $directory = $pending.Dequeue()
        foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Runtime tree contains a reparse point: $($item.FullName)"
            }
            if ($item.PSIsContainer) { $pending.Enqueue($item.FullName) }
        }
    }
}

function Assert-RuntimeInventory(
    [string]$RuntimePath,
    [switch]$AllowLegacyMutableSubset
) {
    Assert-NoReparseTree $RuntimePath
    $manifestPath = Join-Path $RuntimePath 'om0rx-build.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Runtime manifest missing: $manifestPath"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.provider -ne 'mshv_auto_dx') {
        throw 'Runtime manifest schema/provider mismatch'
    }
    $mutablePaths = @($manifest.mutable_paths)
    $unknownMutablePaths = @($mutablePaths | Where-Object { $_ -notin $allowedMutablePaths })
    $distinctMutablePaths = @($mutablePaths | Sort-Object -Unique)
    if ($AllowLegacyMutableSubset) {
        if ($mutablePaths.Count -eq 0 -or
            $distinctMutablePaths.Count -ne $mutablePaths.Count -or
            $unknownMutablePaths.Count) {
            throw 'Prior runtime manifest mutable paths are not a known whitelist subset'
        }
    }
    elseif ($mutablePaths.Count -ne $allowedMutablePaths.Count -or
        $distinctMutablePaths.Count -ne $mutablePaths.Count -or
        $unknownMutablePaths.Count) {
        throw 'Runtime manifest mutable paths differ from the package whitelist'
    }
    if ($null -eq $manifest.files) {
        throw 'Runtime manifest immutable file inventory is missing'
    }
    $inventoryProperties = @($manifest.files.PSObject.Properties)
    if ($inventoryProperties.Count -eq 0) {
        throw 'Runtime manifest immutable file inventory is empty'
    }
    $manifestExecutableHash = [string]$manifest.executable_sha256
    if ([string]::IsNullOrWhiteSpace($manifestExecutableHash) -or
        $manifestExecutableHash -notmatch '^[0-9A-Fa-f]{64}$') {
        throw 'Runtime manifest executable_sha256 must be a non-null 64-hex SHA256'
    }
    $expected = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
    $runtimePrefix = $RuntimePath.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    foreach ($property in $inventoryProperties) {
        $relative = [string]$property.Name
        if ([IO.Path]::IsPathRooted($relative) -or $relative.Contains('\\') -or $relative.Split('/') -contains '..' -or
            $expected.ContainsKey($relative)) {
            throw "Unsafe or duplicate runtime inventory path: $relative"
        }
        $expected.Add($relative, [string]$property.Value)
        if ([string]$property.Value -notmatch '^[0-9A-Fa-f]{64}$') {
            throw "Invalid runtime inventory hash: $relative"
        }
        $filePath = Join-Path $RuntimePath ($property.Name.Replace('/', [IO.Path]::DirectorySeparatorChar))
        $filePath = [IO.Path]::GetFullPath($filePath)
        if (-not $filePath.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Runtime inventory path escapes package: $relative"
        }
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            throw "Runtime inventory file missing: $($property.Name)"
        }
        $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash
        if ($actualHash -ne $property.Value) {
            throw "Runtime inventory hash mismatch for $($property.Name): actual=$actualHash expected=$($property.Value)"
        }
    }
    $actual = @(Get-ChildItem -LiteralPath $RuntimePath -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($RuntimePath.Length + 1).Replace('\','/')
        if ($relative -ne 'om0rx-build.json' -and -not @($mutablePaths | Where-Object { $relative -like $_ }).Count) {
            $relative
        }
    })
    if ($actual.Count -ne $expected.Count -or @($actual | Where-Object { -not $expected.ContainsKey($_) }).Count) {
        throw 'Runtime SHA256 inventory is incomplete or contains undeclared immutable files'
    }
    if (-not $expected.ContainsKey('MSHV_OM0RX.exe')) {
        throw 'Runtime inventory does not explicitly declare MSHV_OM0RX.exe'
    }
    if ($manifestExecutableHash -ne $expected['MSHV_OM0RX.exe']) {
        throw 'Runtime executable identity does not match inventory'
    }
}

function Test-MutableRuntimePath([string]$RelativePath) {
    return @($allowedMutablePaths | Where-Object { $RelativePath -like $_ }).Count -gt 0
}

function Sync-MutableRuntimeState([string]$SourceRuntime, [string]$TargetRuntime) {
    # Stage-only packaging is allowed while the current engine is running.  Its
    # mutable snapshot can therefore age before the eventual stop.  Refresh the
    # candidate from the now-stopped destination immediately before the swap,
    # without recopying the large immutable Qt/application bundle.
    if (Test-Path -LiteralPath (Join-Path $SourceRuntime '.history-import.lock')) {
        throw 'History migration is in progress; refusing runtime installation'
    }
    Get-ChildItem -LiteralPath $TargetRuntime -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($TargetRuntime.Length + 1).Replace('\','/')
        if (Test-MutableRuntimePath $relative) {
            Remove-Item -LiteralPath $_.FullName -Force
        }
    }
    Get-ChildItem -LiteralPath $SourceRuntime -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($SourceRuntime.Length + 1).Replace('\','/')
        if ($relative -ne '.history-import.lock' -and (Test-MutableRuntimePath $relative)) {
            $target = Join-Path $TargetRuntime ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

function Assert-DestinationRuntimeStopped([string]$DestinationRuntime) {
    $destinationExecutable = [IO.Path]::GetFullPath((Join-Path $DestinationRuntime 'MSHV_OM0RX.exe'))
    $runningAtDestination = @(Get-Process -Name 'MSHV_OM0RX' -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -and [IO.Path]::GetFullPath($_.Path).Equals(
                $destinationExecutable, [StringComparison]::OrdinalIgnoreCase
            )
        }
        catch {
            # An inaccessible process path is not proof that the destination is
            # safe to replace.  CIM provides an independent executable-path
            # source below; this branch simply avoids treating access failure as
            # a non-match.
            $false
        }
    })
    if (-not $runningAtDestination.Count) {
        $runningAtDestination = @(Get-CimInstance Win32_Process -Filter "Name='MSHV_OM0RX.exe'" -ErrorAction SilentlyContinue | Where-Object {
            try {
                $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath).Equals(
                    $destinationExecutable, [StringComparison]::OrdinalIgnoreCase
                )
            }
            catch { $false }
        })
    }
    if ($runningAtDestination.Count) {
        $pids = ($runningAtDestination | ForEach-Object {
            if ($_.PSObject.Properties['Id']) { $_.Id } else { $_.ProcessId }
        }) -join ','
        throw "Stop the destination MSHV runtime before installation: $destinationExecutable (PID $pids)"
    }
}

$work = [IO.Path]::GetFullPath($WorkRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
if (-not (Test-Path -LiteralPath $work -PathType Container)) { throw "Runtime work root missing: $work" }
$workPrefix = $work.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$staged = [IO.Path]::GetFullPath($StagedRuntime)
$destinationPath = [IO.Path]::GetFullPath($Destination)
Assert-NoReparseAncestors $work
foreach ($target in @($staged, $destinationPath)) { Assert-NoReparseAncestors $target }
if (-not (Split-Path -Parent $staged).Equals($work, [StringComparison]::OrdinalIgnoreCase) -or
    (Split-Path -Leaf $staged) -notmatch '^runtime-stage-[0-9a-f]{32}$') {
    throw "Staged runtime path is not an approved deterministic stage: $staged"
}
if (-not (Split-Path -Parent $destinationPath).Equals($work, [StringComparison]::OrdinalIgnoreCase) -or
    (Split-Path -Leaf $destinationPath) -notin $allowedDestinationNames) {
    throw "Runtime destination is not approved: $destinationPath"
}
if ($staged.Equals($destinationPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Staged runtime and destination must differ'
}

Assert-RuntimeInventory $staged
$previous = Join-Path $work ('runtime-previous-' + [Guid]::NewGuid().ToString('N'))
$failed = Join-Path $work ('runtime-failed-' + [Guid]::NewGuid().ToString('N'))
$hadPrevious = Test-Path -LiteralPath $destinationPath
if ($hadPrevious) { Assert-RuntimeInventory $destinationPath -AllowLegacyMutableSubset }
# This check must precede Sync-MutableRuntimeState and every directory move.
# Stage-only packaging is intentionally live-safe; final installation is not.
Assert-DestinationRuntimeStopped $destinationPath
if ($hadPrevious) { Sync-MutableRuntimeState $destinationPath $staged }
Assert-RuntimeInventory $staged
if ($hadPrevious) { Move-Item -LiteralPath $destinationPath -Destination $previous }
try {
    Move-Item -LiteralPath $staged -Destination $destinationPath
    if ($env:OM0RX_PACKAGE_TRANSACTION_TEST -eq 'fail-after-swap') {
        throw 'Injected post-swap validation failure'
    }
    Assert-RuntimeInventory $destinationPath
}
catch {
    $failure = $_
    if (Test-Path -LiteralPath $destinationPath) { Move-Item -LiteralPath $destinationPath -Destination $failed }
    if ($hadPrevious) { Move-Item -LiteralPath $previous -Destination $destinationPath }
    throw $failure
}

Write-Host "Packaged runtime: $destinationPath"
if ($hadPrevious) { Write-Host "Previous runtime preserved: $previous" }
