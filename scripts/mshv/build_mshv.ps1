param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64',
    [int]$Jobs = 4,
    [switch]$SkipPackage,
    [switch]$StageOnlyPackage,
    [string]$PackageDestination
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'prepare_mshv.ps1') -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'Source preparation failed' }
$source = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762'
$originalPath = $env:PATH
try {
    $env:PATH = (Join-Path $Toolchain 'bin') + ';' + $originalPath
    Push-Location $source
    if (Test-Path 'Makefile') {
        & (Join-Path $Toolchain 'bin\mingw32-make.exe') clean
        if ($LASTEXITCODE -ne 0) { throw 'MSHV clean build preparation failed' }
    }
    & (Join-Path $Toolchain 'bin\qmake.exe') MSHV_WIN64.pro TARGET=MSHV_OM0RX
    if ($LASTEXITCODE -ne 0) { throw 'MSHV qmake failed' }
    & (Join-Path $Toolchain 'bin\mingw32-make.exe') "-j$Jobs"
    if ($LASTEXITCODE -ne 0) { throw 'MSHV compilation failed' }
    $identity = @{
        base_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-integration.patch') -Algorithm SHA256).Hash
        autodx_phase1_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-phase1.patch') -Algorithm SHA256).Hash
        wavelog_history_phase2_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-wavelog-history-phase2.patch') -Algorithm SHA256).Hash
        autodx_quiet_qsy_fix_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-quiet-qsy-fix.patch') -Algorithm SHA256).Hash
        autodx_native_policy_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-native-policy.patch') -Algorithm SHA256).Hash
        ui_persistence_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-persistence.patch') -Algorithm SHA256).Hash
        ui_layout_persistence_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-layout-persistence.patch') -Algorithm SHA256).Hash
        performance_decode_dxpedition_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-performance-decode-dxpedition.patch') -Algorithm SHA256).Hash
        recent_qso_cooldown_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-recent-qso-cooldown.patch') -Algorithm SHA256).Hash
        permanent_slot_dedupe_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-permanent-slot-dedupe.patch') -Algorithm SHA256).Hash
        compact_status_combinations_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-compact-status-combinations.patch') -Algorithm SHA256).Hash
        us_states_chase_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-us-states-chase.patch') -Algorithm SHA256).Hash
        cluster_chase_scheduler_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-cluster-chase-scheduler.patch') -Algorithm SHA256).Hash
        us_state_dxcc_guard_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-us-state-dxcc-guard.patch') -Algorithm SHA256).Hash
        composable_award_hunting_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-composable-award-hunting.patch') -Algorithm SHA256).Hash
        priority_patrol_ft4_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-priority-patrol-ft4.patch') -Algorithm SHA256).Hash
        repeat_final_exchange_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-repeat-final-exchange.patch') -Algorithm SHA256).Hash
        band_markers_country_exclusions_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-band-markers-country-exclusions.patch') -Algorithm SHA256).Hash
        exchange_only_reply_guard_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-exchange-only-reply-guard.patch') -Algorithm SHA256).Hash
        manual_qso_lifecycle_ui_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-qso-lifecycle-ui.patch') -Algorithm SHA256).Hash
        station_rf_panel_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-station-rf-panel.patch') -Algorithm SHA256).Hash
        manual_target_lock_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-target-lock.patch') -Algorithm SHA256).Hash
        late_reply_qsy_guard_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-late-reply-qsy-guard.patch') -Algorithm SHA256).Hash
        adaptive_retry_ignore_patch_sha256=(Get-FileHash (Join-Path $ProjectRoot 'docs\mshv\om0rx-adaptive-retry-ignore.patch') -Algorithm SHA256).Hash
        source_diff_sha256=(Get-FileHash (Join-Path $ProjectRoot 'data\build\mshv-auto-dx\source-attestation.patch') -Algorithm SHA256).Hash
        executable_sha256=(Get-FileHash (Join-Path $source 'bin\MSHV_OM0RX.exe') -Algorithm SHA256).Hash
    }
    $identity | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ProjectRoot 'data\build\mshv-auto-dx\compiled-source.json') -Encoding UTF8
} finally { Pop-Location; $env:PATH = $originalPath }
if (-not $SkipPackage) {
    $packageArgs = @{ ProjectRoot=$ProjectRoot; Toolchain=$Toolchain }
    if ($PackageDestination) { $packageArgs.Destination = $PackageDestination }
    if ($StageOnlyPackage) { $packageArgs.StageOnly = $true }
    & (Join-Path $PSScriptRoot 'package_mshv.ps1') @packageArgs
}
