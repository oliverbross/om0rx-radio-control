param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64',
    [string]$Destination,
    [switch]$StageOnly
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'assert_source.ps1') -ProjectRoot $ProjectRoot
$work = Join-Path $ProjectRoot 'data\build\mshv-auto-dx'
$source = Join-Path $work 'src'
$destination = if ($Destination) { [IO.Path]::GetFullPath($Destination) } else { Join-Path $work 'runtime' }
$runtime = Join-Path $work ('runtime-stage-' + [Guid]::NewGuid().ToString('N'))
$runtimeExecutable = [IO.Path]::GetFullPath((Join-Path $destination 'MSHV_OM0RX.exe'))
$runningRuntime = Get-Process -Name 'MSHV_OM0RX' -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and [IO.Path]::GetFullPath($_.Path).Equals($runtimeExecutable, [StringComparison]::OrdinalIgnoreCase) }
    catch { $false }
}
if ($runningRuntime -and -not $StageOnly) { throw "Stop the packaged MSHV runtime before packaging: $runtimeExecutable" }
if (Test-Path (Join-Path $destination '.history-import.lock')) { throw 'History migration is in progress; refusing runtime packaging' }
$lock = Get-Content (Join-Path $PSScriptRoot 'upstream-lock.json') -Raw | ConvertFrom-Json
if ((git -C $source rev-parse HEAD).Trim() -ne $lock.commit) { throw 'MSHV source identity mismatch' }
$exe = Join-Path $source 'MSHV_2762\bin\MSHV_OM0RX.exe'
if (-not (Test-Path $exe)) { throw "Build executable missing: $exe" }
$identityPath = Join-Path $work 'compiled-source.json'
if (-not (Test-Path $identityPath)) { throw 'Build identity missing; use build_mshv.ps1' }
$identity = Get-Content $identityPath -Raw | ConvertFrom-Json
$basePatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-integration.patch'
$phasePatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-phase1.patch'
$phase2Patch = Join-Path $ProjectRoot 'docs\mshv\om0rx-wavelog-history-phase2.patch'
$quietQsyPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-quiet-qsy-fix.patch'
$nativePolicyPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-native-policy.patch'
$uiPersistencePatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-persistence.patch'
$uiLayoutPersistencePatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-layout-persistence.patch'
$performanceDecodeDxpeditionPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-performance-decode-dxpedition.patch'
$recentQsoCooldownPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-recent-qso-cooldown.patch'
$permanentSlotDedupePatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-permanent-slot-dedupe.patch'
$compactStatusCombinationsPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-compact-status-combinations.patch'
$usStatesChasePatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-us-states-chase.patch'
$clusterChaseSchedulerPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-cluster-chase-scheduler.patch'
$usStateDxccGuardPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-us-state-dxcc-guard.patch'
$composableAwardHuntingPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-composable-award-hunting.patch'
$priorityPatrolFt4Patch = Join-Path $ProjectRoot 'docs\mshv\om0rx-priority-patrol-ft4.patch'
$repeatFinalExchangePatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-repeat-final-exchange.patch'
$bandMarkersCountryExclusionsPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-band-markers-country-exclusions.patch'
$exchangeOnlyReplyGuardPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-exchange-only-reply-guard.patch'
$manualQsoLifecycleUiPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-qso-lifecycle-ui.patch'
$stationRfPanelPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-station-rf-panel.patch'
$manualTargetLockPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-target-lock.patch'
$lateReplyQsyGuardPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-late-reply-qsy-guard.patch'
$adaptiveRetryIgnorePatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-adaptive-retry-ignore.patch'
$sourceAttestation = Join-Path $work 'source-attestation.patch'
$mutablePaths = @(
    '.history-import.lock','history-import.json','history-backups/**','log/**','logs/**',
    'settings/autodx.ini','settings/ms_*','settings/*.txt','settings/azel.dat',
    'settings/database/worked.db','settings/database/worked.db-*',
    'settings/database/wavelog_delta_state.json','settings/database/award_hunting.json',
    'settings/database/dxpedition_watch.json','settings/database/autodx_ignore.json',
    'settings/database/autodx_status_owner.json',
    'settings/database/lotw-users.txt','settings/database/confirmed-dxcc.txt','settings/database/us-states.txt',
    'settings/database/status-colors.ini',
    'settings/database/msloc_db*','settings/database/msbcn_db*',
    'settings/database/mstn_db*','settings/database/sat.dat'
)
if ($identity.base_patch_sha256 -ne (Get-FileHash $basePatch -Algorithm SHA256).Hash -or
    $identity.autodx_phase1_patch_sha256 -ne (Get-FileHash $phasePatch -Algorithm SHA256).Hash -or
    $identity.wavelog_history_phase2_patch_sha256 -ne (Get-FileHash $phase2Patch -Algorithm SHA256).Hash -or
    $identity.autodx_quiet_qsy_fix_patch_sha256 -ne (Get-FileHash $quietQsyPatch -Algorithm SHA256).Hash -or
    $identity.autodx_native_policy_patch_sha256 -ne (Get-FileHash $nativePolicyPatch -Algorithm SHA256).Hash -or
    $identity.ui_persistence_patch_sha256 -ne (Get-FileHash $uiPersistencePatch -Algorithm SHA256).Hash -or
    $identity.ui_layout_persistence_patch_sha256 -ne (Get-FileHash $uiLayoutPersistencePatch -Algorithm SHA256).Hash -or
    $identity.performance_decode_dxpedition_patch_sha256 -ne (Get-FileHash $performanceDecodeDxpeditionPatch -Algorithm SHA256).Hash -or
    $identity.recent_qso_cooldown_patch_sha256 -ne (Get-FileHash $recentQsoCooldownPatch -Algorithm SHA256).Hash -or
    $identity.permanent_slot_dedupe_patch_sha256 -ne (Get-FileHash $permanentSlotDedupePatch -Algorithm SHA256).Hash -or
    $identity.compact_status_combinations_patch_sha256 -ne (Get-FileHash $compactStatusCombinationsPatch -Algorithm SHA256).Hash -or
    $identity.us_states_chase_patch_sha256 -ne (Get-FileHash $usStatesChasePatch -Algorithm SHA256).Hash -or
    $identity.cluster_chase_scheduler_patch_sha256 -ne (Get-FileHash $clusterChaseSchedulerPatch -Algorithm SHA256).Hash -or
    $identity.us_state_dxcc_guard_patch_sha256 -ne (Get-FileHash $usStateDxccGuardPatch -Algorithm SHA256).Hash -or
    $identity.composable_award_hunting_patch_sha256 -ne (Get-FileHash $composableAwardHuntingPatch -Algorithm SHA256).Hash -or
    $identity.priority_patrol_ft4_patch_sha256 -ne (Get-FileHash $priorityPatrolFt4Patch -Algorithm SHA256).Hash -or
    $identity.repeat_final_exchange_patch_sha256 -ne (Get-FileHash $repeatFinalExchangePatch -Algorithm SHA256).Hash -or
    $identity.band_markers_country_exclusions_patch_sha256 -ne (Get-FileHash $bandMarkersCountryExclusionsPatch -Algorithm SHA256).Hash -or
    $identity.exchange_only_reply_guard_patch_sha256 -ne (Get-FileHash $exchangeOnlyReplyGuardPatch -Algorithm SHA256).Hash -or
    $identity.manual_qso_lifecycle_ui_patch_sha256 -ne (Get-FileHash $manualQsoLifecycleUiPatch -Algorithm SHA256).Hash -or
    $identity.station_rf_panel_patch_sha256 -ne (Get-FileHash $stationRfPanelPatch -Algorithm SHA256).Hash -or
    $identity.manual_target_lock_patch_sha256 -ne (Get-FileHash $manualTargetLockPatch -Algorithm SHA256).Hash -or
    $identity.late_reply_qsy_guard_patch_sha256 -ne (Get-FileHash $lateReplyQsyGuardPatch -Algorithm SHA256).Hash -or
    $identity.adaptive_retry_ignore_patch_sha256 -ne (Get-FileHash $adaptiveRetryIgnorePatch -Algorithm SHA256).Hash -or
    $identity.source_diff_sha256 -ne (Get-FileHash $sourceAttestation -Algorithm SHA256).Hash -or
    $identity.executable_sha256 -ne (Get-FileHash $exe -Algorithm SHA256).Hash) {
    throw 'Compiled executable does not attest to maintained base + AutoDX Phase 1 source'
}
New-Item -ItemType Directory -Force -Path $runtime,(Join-Path $runtime 'settings\database'),(Join-Path $runtime 'log') | Out-Null
if (Test-Path -LiteralPath $destination) {
    Get-ChildItem -LiteralPath $destination -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($destination.Length + 1).Replace('\','/')
        if ($relative -ne '.history-import.lock' -and @($mutablePaths | Where-Object { $relative -like $_ }).Count) {
            $target = Join-Path $runtime ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}
Copy-Item -LiteralPath $exe -Destination $runtime
# MSYS2's windeployqt cannot resolve its split plugin prefix reliably. Deploy
# the exact imported Qt and compiler DLL closure below instead.
$pluginRoot = Join-Path $Toolchain 'share\qt5\plugins'
foreach ($directory in @('platforms','imageformats','styles')) {
    if (Test-Path (Join-Path $pluginRoot $directory)) { Copy-Item -LiteralPath (Join-Path $pluginRoot $directory) -Destination $runtime -Recurse -Force }
}
$sqlite = Join-Path $Toolchain 'share\qt5\plugins\sqldrivers\qsqlite.dll'
if (-not (Test-Path $sqlite)) { $sqlite = Join-Path $Toolchain 'plugins\sqldrivers\qsqlite.dll' }
if (-not (Test-Path $sqlite)) { throw 'QSQLITE runtime plugin is unavailable' }
New-Item -ItemType Directory -Force -Path (Join-Path $runtime 'sqldrivers') | Out-Null
Copy-Item -LiteralPath $sqlite -Destination (Join-Path $runtime 'sqldrivers')
foreach ($library in @('libssl-3-x64.dll','libcrypto-3-x64.dll')) {
    $libraryPath = Join-Path $Toolchain ('bin\' + $library)
    if (-not (Test-Path $libraryPath)) { throw "TLS runtime unavailable: $library" }
    Copy-Item -LiteralPath $libraryPath -Destination $runtime
}
# MSYS2 Qt depends on additional MinGW DLLs beyond Qt modules. Follow import
# tables recursively, copying only files resolved inside this toolchain's bin.
$queue = [Collections.Generic.Queue[string]]::new()
Get-ChildItem $runtime -Recurse -File | Where-Object { $_.Extension -in @('.exe','.dll') } | ForEach-Object { $queue.Enqueue($_.FullName) }
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
while ($queue.Count) {
    $binary = $queue.Dequeue()
    if (-not $seen.Add($binary)) { continue }
    $imports = & (Join-Path $Toolchain 'bin\objdump.exe') -p $binary
    if ($LASTEXITCODE -ne 0) { throw "Unable to inspect dependency imports: $binary" }
    foreach ($line in $imports) {
        if ($line -match 'DLL Name:\s*(\S+)') {
            $dependency = Join-Path $Toolchain ('bin\' + $Matches[1])
            if (Test-Path -LiteralPath $dependency) {
                $target = Join-Path $runtime $Matches[1]
                if (-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $dependency -Destination $target }
                $queue.Enqueue($target)
            }
        }
    }
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'data\cty.dat') -Destination (Join-Path $runtime 'settings\database\cty.dat')
$mapping = @(Get-Content (Join-Path $ProjectRoot 'data\cty.csv') | ConvertFrom-Csv -Header Prefix,Name,Dxcc,Continent,Cq,Itu,Lat,Lon,Offset,Aliases | ForEach-Object {
    $prefix = $_.Prefix.Trim().ToUpper().TrimStart('*','=')
    $number = 0
    if ($prefix -and [int]::TryParse($_.Dxcc,[ref]$number) -and $number -gt 0) { "$($prefix):$number" }
})
if ($mapping.Count -lt 300) { throw 'DXCC mapping is incomplete' }
$mapping | Set-Content -LiteralPath (Join-Path $runtime 'settings\database\dxcc_numbers.dat') -Encoding ASCII
foreach ($notice in @('LICENSE','THIRD_PARTY_LICENSES.md')) { Copy-Item -LiteralPath (Join-Path $source $notice) -Destination $runtime }
Copy-Item -LiteralPath (Join-Path $source 'MSHV_2762\COPYING.txt') -Destination $runtime
foreach ($notice in @('qt5-base','qt5-websockets','qt5-tools','openssl')) {
    $licenses = Join-Path $Toolchain ('share\licenses\' + $notice)
    if (Test-Path $licenses) {
        New-Item -ItemType Directory -Force -Path (Join-Path $runtime 'licenses') | Out-Null
        Copy-Item -LiteralPath $licenses -Destination (Join-Path $runtime 'licenses') -Recurse -Force
    }
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-integration.patch') -Destination $runtime
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-phase1.patch') -Destination $runtime
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-wavelog-history-phase2.patch') -Destination $runtime
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-quiet-qsy-fix.patch') -Destination $runtime
Copy-Item -LiteralPath $nativePolicyPatch -Destination $runtime
Copy-Item -LiteralPath $uiPersistencePatch -Destination $runtime
Copy-Item -LiteralPath $uiLayoutPersistencePatch -Destination $runtime
Copy-Item -LiteralPath $performanceDecodeDxpeditionPatch -Destination $runtime
Copy-Item -LiteralPath $recentQsoCooldownPatch -Destination $runtime
Copy-Item -LiteralPath $permanentSlotDedupePatch -Destination $runtime
Copy-Item -LiteralPath $compactStatusCombinationsPatch -Destination $runtime
Copy-Item -LiteralPath $usStatesChasePatch -Destination $runtime
Copy-Item -LiteralPath $clusterChaseSchedulerPatch -Destination $runtime
Copy-Item -LiteralPath $usStateDxccGuardPatch -Destination $runtime
Copy-Item -LiteralPath $composableAwardHuntingPatch -Destination $runtime
Copy-Item -LiteralPath $priorityPatrolFt4Patch -Destination $runtime
Copy-Item -LiteralPath $repeatFinalExchangePatch -Destination $runtime
Copy-Item -LiteralPath $bandMarkersCountryExclusionsPatch -Destination $runtime
Copy-Item -LiteralPath $exchangeOnlyReplyGuardPatch -Destination $runtime
Copy-Item -LiteralPath $manualQsoLifecycleUiPatch -Destination $runtime
Copy-Item -LiteralPath $stationRfPanelPatch -Destination $runtime
Copy-Item -LiteralPath $manualTargetLockPatch -Destination $runtime
Copy-Item -LiteralPath $lateReplyQsyGuardPatch -Destination $runtime
Copy-Item -LiteralPath $adaptiveRetryIgnorePatch -Destination $runtime
Copy-Item -LiteralPath $sourceAttestation -Destination $runtime
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'upstream-lock.json') -Destination $runtime
$manifest = @{ schema=1; provider='mshv_auto_dx'; version='2.76.2-om0rx.1'; station_interlock=$true; capabilities=@('station_ready_v2','station_permit_v1','engine_state_v1','offline_history_v1','ft8_ft4_import','target_priority_v1','autodx_runtime_config_v1','wavelog_history_authority_v1','wavelog_history_delta_v2','autodx_quiet_qsy_v1','autodx_native_policy_v1','ui_state_persistence_v1','autodx_performance_v1','dxpedition_chase_v1','decode_status_columns_v1','recent_qso_cooldown_v1','permanent_slot_dedupe_v1','band_dxcc_continent_override_v1','compact_status_combinations_v1','us_states_chase_v1','cluster_chase_scheduler_v1','us_state_dxcc_guard_v1','composable_award_hunting_v1','autodx_hot_reload_v1','decode_qso_panel_status_v1','priority_patrol_fallback_v1','ft4_dual_decode_layout_v1','ft4_autodx_v1','repeat_final_exchange_v1','band_markers_v1','country_exclusions_by_band_v1','exchange_only_reply_guard_v1','manual_qso_lifecycle_ui_v1','station_rf_panel_v1'); udp_client_id='MSHV-OM0RX-AUTO-DX'; commit=$lock.commit; executable_sha256=(Get-FileHash (Join-Path $runtime 'MSHV_OM0RX.exe') -Algorithm SHA256).Hash; cty_sha256=(Get-FileHash (Join-Path $runtime 'settings\database\cty.dat') -Algorithm SHA256).Hash; dxcc_sha256=(Get-FileHash (Join-Path $runtime 'settings\database\dxcc_numbers.dat') -Algorithm SHA256).Hash; patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-integration.patch') -Algorithm SHA256).Hash; autodx_phase1_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-autodx-phase1.patch') -Algorithm SHA256).Hash; wavelog_history_phase2_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-wavelog-history-phase2.patch') -Algorithm SHA256).Hash; autodx_quiet_qsy_fix_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-autodx-quiet-qsy-fix.patch') -Algorithm SHA256).Hash; autodx_native_policy_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-autodx-native-policy.patch') -Algorithm SHA256).Hash; ui_persistence_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-ui-persistence.patch') -Algorithm SHA256).Hash; ui_layout_persistence_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-ui-layout-persistence.patch') -Algorithm SHA256).Hash; performance_decode_dxpedition_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-performance-decode-dxpedition.patch') -Algorithm SHA256).Hash; recent_qso_cooldown_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-recent-qso-cooldown.patch') -Algorithm SHA256).Hash; permanent_slot_dedupe_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-permanent-slot-dedupe.patch') -Algorithm SHA256).Hash; compact_status_combinations_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-compact-status-combinations.patch') -Algorithm SHA256).Hash; us_states_chase_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-us-states-chase.patch') -Algorithm SHA256).Hash; cluster_chase_scheduler_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-cluster-chase-scheduler.patch') -Algorithm SHA256).Hash; us_state_dxcc_guard_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-us-state-dxcc-guard.patch') -Algorithm SHA256).Hash; composable_award_hunting_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-composable-award-hunting.patch') -Algorithm SHA256).Hash; priority_patrol_ft4_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-priority-patrol-ft4.patch') -Algorithm SHA256).Hash; repeat_final_exchange_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-repeat-final-exchange.patch') -Algorithm SHA256).Hash; band_markers_country_exclusions_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-band-markers-country-exclusions.patch') -Algorithm SHA256).Hash; exchange_only_reply_guard_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-exchange-only-reply-guard.patch') -Algorithm SHA256).Hash; manual_qso_lifecycle_ui_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-manual-qso-lifecycle-ui.patch') -Algorithm SHA256).Hash; station_rf_panel_patch_sha256=(Get-FileHash (Join-Path $runtime 'om0rx-station-rf-panel.patch') -Algorithm SHA256).Hash; built_utc=[DateTime]::UtcNow.ToString('o'); source=$lock.repository; inventory_excludes=@('om0rx-build.json'); mutable_paths=$mutablePaths }
$manifest.source_diff_sha256 = $identity.source_diff_sha256
$manifest.capabilities += 'manual_target_lock_v1'
$manifest.manual_target_lock_patch_sha256 = (Get-FileHash (Join-Path $runtime 'om0rx-manual-target-lock.patch') -Algorithm SHA256).Hash
$manifest.capabilities += 'late_reply_qsy_guard_v1'
$manifest.late_reply_qsy_guard_patch_sha256 = (Get-FileHash (Join-Path $runtime 'om0rx-late-reply-qsy-guard.patch') -Algorithm SHA256).Hash
$manifest.capabilities += 'adaptive_retry_ignore_v1'
$manifest.adaptive_retry_ignore_patch_sha256 = (Get-FileHash (Join-Path $runtime 'om0rx-adaptive-retry-ignore.patch') -Algorithm SHA256).Hash
$inventory = [ordered]@{}
$mutableFileCount = 0
Get-ChildItem $runtime -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($runtime.Length + 1).Replace('\','/')
    if (@($mutablePaths | Where-Object { $relative -like $_ }).Count) { $mutableFileCount++ }
    else { $inventory[$relative] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
}
$manifest.files = $inventory
$manifest.file_count = $inventory.Count
$manifest.mutable_file_count = $mutableFileCount
$manifest.staged_file_count = $inventory.Count + $mutableFileCount
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'om0rx-build.json') -Encoding UTF8
$actualInventory = @(Get-ChildItem $runtime -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($runtime.Length + 1).Replace('\','/')
    if ($relative -ne 'om0rx-build.json' -and -not @($mutablePaths | Where-Object { $relative -like $_ }).Count) { $relative }
})
if ($actualInventory.Count -ne $inventory.Count -or @($actualInventory | Where-Object { -not $inventory.Contains($_) }).Count) { throw 'Runtime SHA256 inventory is incomplete' }
if ($StageOnly) {
    # The immutable Qt/application bundle is now fully materialized and
    # attested while the old runtime can continue running.  The installer
    # refreshes mutable operator state from the stopped destination immediately
    # before the atomic directory swap.
    Write-Output "PRESTAGED_RUNTIME=$runtime"
} else {
    & (Join-Path $PSScriptRoot 'install_staged_runtime.ps1') -StagedRuntime $runtime -Destination $destination -WorkRoot $work
}
