param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Runtime
)
$ErrorActionPreference = 'Stop'
$buildRoot = Join-Path $ProjectRoot 'data\build\mshv-auto-dx'
$runtime = if ($Runtime) { [IO.Path]::GetFullPath($Runtime) } else { Join-Path $buildRoot 'runtime' }
$maintainedPatch = Join-Path $ProjectRoot 'docs\mshv\om0rx-integration.patch'
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
$sourceAttestation = Join-Path $buildRoot 'source-attestation.patch'
$compiled = Get-Content (Join-Path $buildRoot 'compiled-source.json') -Raw | ConvertFrom-Json
$manifest = Get-Content (Join-Path $runtime 'om0rx-build.json') -Raw | ConvertFrom-Json
$sourceExe = Join-Path $buildRoot 'src\MSHV_2762\bin\MSHV_OM0RX.exe'
$runtimeExe = Join-Path $runtime $(if ($manifest.executable) { $manifest.executable } else { 'MSHV_OM0RX.exe' })
$baseHash = (Get-FileHash $maintainedPatch -Algorithm SHA256).Hash
$phaseHash = (Get-FileHash $phasePatch -Algorithm SHA256).Hash
$phase2Hash = (Get-FileHash $phase2Patch -Algorithm SHA256).Hash
$quietQsyHash = (Get-FileHash $quietQsyPatch -Algorithm SHA256).Hash
$nativePolicyHash = (Get-FileHash $nativePolicyPatch -Algorithm SHA256).Hash
$uiPersistenceHash = (Get-FileHash $uiPersistencePatch -Algorithm SHA256).Hash
$uiLayoutPersistenceHash = (Get-FileHash $uiLayoutPersistencePatch -Algorithm SHA256).Hash
$performanceDecodeDxpeditionHash = (Get-FileHash $performanceDecodeDxpeditionPatch -Algorithm SHA256).Hash
$recentQsoCooldownHash = (Get-FileHash $recentQsoCooldownPatch -Algorithm SHA256).Hash
$permanentSlotDedupeHash = (Get-FileHash $permanentSlotDedupePatch -Algorithm SHA256).Hash
$compactStatusCombinationsHash = (Get-FileHash $compactStatusCombinationsPatch -Algorithm SHA256).Hash
$usStatesChaseHash = (Get-FileHash $usStatesChasePatch -Algorithm SHA256).Hash
$clusterChaseSchedulerHash = (Get-FileHash $clusterChaseSchedulerPatch -Algorithm SHA256).Hash
$usStateDxccGuardHash = (Get-FileHash $usStateDxccGuardPatch -Algorithm SHA256).Hash
$composableAwardHuntingHash = (Get-FileHash $composableAwardHuntingPatch -Algorithm SHA256).Hash
$priorityPatrolFt4Hash = (Get-FileHash $priorityPatrolFt4Patch -Algorithm SHA256).Hash
$repeatFinalExchangeHash = (Get-FileHash $repeatFinalExchangePatch -Algorithm SHA256).Hash
$bandMarkersCountryExclusionsHash = (Get-FileHash $bandMarkersCountryExclusionsPatch -Algorithm SHA256).Hash
$exchangeOnlyReplyGuardHash = (Get-FileHash $exchangeOnlyReplyGuardPatch -Algorithm SHA256).Hash
$manualQsoLifecycleUiHash = (Get-FileHash $manualQsoLifecycleUiPatch -Algorithm SHA256).Hash
$stationRfPanelHash = (Get-FileHash $stationRfPanelPatch -Algorithm SHA256).Hash
$manualTargetLockHash = (Get-FileHash $manualTargetLockPatch -Algorithm SHA256).Hash
$lateReplyQsyGuardHash = (Get-FileHash $lateReplyQsyGuardPatch -Algorithm SHA256).Hash
$adaptiveRetryIgnoreHash = (Get-FileHash $adaptiveRetryIgnorePatch -Algorithm SHA256).Hash
$sourceDiffHash = (Get-FileHash $sourceAttestation -Algorithm SHA256).Hash
$sourceExeHash = (Get-FileHash $sourceExe -Algorithm SHA256).Hash
$runtimeExeHash = (Get-FileHash $runtimeExe -Algorithm SHA256).Hash
foreach ($check in @(
    @{ Name='compiled base patch'; Actual=$compiled.base_patch_sha256; Expected=$baseHash },
    @{ Name='compiled AutoDX Phase 1 patch'; Actual=$compiled.autodx_phase1_patch_sha256; Expected=$phaseHash },
    @{ Name='compiled Wavelog history Phase 2 patch'; Actual=$compiled.wavelog_history_phase2_patch_sha256; Expected=$phase2Hash },
    @{ Name='compiled AutoDX quiet QSY patch'; Actual=$compiled.autodx_quiet_qsy_fix_patch_sha256; Expected=$quietQsyHash },
    @{ Name='compiled native AutoDX policy patch'; Actual=$compiled.autodx_native_policy_patch_sha256; Expected=$nativePolicyHash },
    @{ Name='compiled UI persistence patch'; Actual=$compiled.ui_persistence_patch_sha256; Expected=$uiPersistenceHash },
    @{ Name='compiled UI layout persistence patch'; Actual=$compiled.ui_layout_persistence_patch_sha256; Expected=$uiLayoutPersistenceHash },
    @{ Name='compiled performance/decode/DXpedition patch'; Actual=$compiled.performance_decode_dxpedition_patch_sha256; Expected=$performanceDecodeDxpeditionHash },
    @{ Name='compiled recent-QSO cooldown patch'; Actual=$compiled.recent_qso_cooldown_patch_sha256; Expected=$recentQsoCooldownHash },
    @{ Name='compiled permanent slot-dedupe patch'; Actual=$compiled.permanent_slot_dedupe_patch_sha256; Expected=$permanentSlotDedupeHash },
    @{ Name='compiled compact status-combinations patch'; Actual=$compiled.compact_status_combinations_patch_sha256; Expected=$compactStatusCombinationsHash },
    @{ Name='compiled US states chase patch'; Actual=$compiled.us_states_chase_patch_sha256; Expected=$usStatesChaseHash },
    @{ Name='compiled cluster chase scheduler patch'; Actual=$compiled.cluster_chase_scheduler_patch_sha256; Expected=$clusterChaseSchedulerHash },
    @{ Name='compiled US-state DXCC guard patch'; Actual=$compiled.us_state_dxcc_guard_patch_sha256; Expected=$usStateDxccGuardHash },
    @{ Name='compiled composable award-hunting patch'; Actual=$compiled.composable_award_hunting_patch_sha256; Expected=$composableAwardHuntingHash },
    @{ Name='compiled priority-patrol/FT4 patch'; Actual=$compiled.priority_patrol_ft4_patch_sha256; Expected=$priorityPatrolFt4Hash },
    @{ Name='compiled final-exchange repeat patch'; Actual=$compiled.repeat_final_exchange_patch_sha256; Expected=$repeatFinalExchangeHash },
    @{ Name='compiled band-marker/country-exclusion patch'; Actual=$compiled.band_markers_country_exclusions_patch_sha256; Expected=$bandMarkersCountryExclusionsHash },
    @{ Name='compiled exchange-only reply guard patch'; Actual=$compiled.exchange_only_reply_guard_patch_sha256; Expected=$exchangeOnlyReplyGuardHash },
    @{ Name='compiled manual-QSO lifecycle UI patch'; Actual=$compiled.manual_qso_lifecycle_ui_patch_sha256; Expected=$manualQsoLifecycleUiHash },
    @{ Name='compiled station RF panel patch'; Actual=$compiled.station_rf_panel_patch_sha256; Expected=$stationRfPanelHash },
    @{ Name='compiled manual target lock patch'; Actual=$compiled.manual_target_lock_patch_sha256; Expected=$manualTargetLockHash },
    @{ Name='compiled late-reply QSY guard patch'; Actual=$compiled.late_reply_qsy_guard_patch_sha256; Expected=$lateReplyQsyGuardHash },
    @{ Name='compiled adaptive-retry/ignore patch'; Actual=$compiled.adaptive_retry_ignore_patch_sha256; Expected=$adaptiveRetryIgnoreHash },
    @{ Name='compiled aggregate source'; Actual=$compiled.source_diff_sha256; Expected=$sourceDiffHash },
    @{ Name='runtime base patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-integration.patch') -Algorithm SHA256).Hash; Expected=$baseHash },
    @{ Name='runtime AutoDX Phase 1 patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-autodx-phase1.patch') -Algorithm SHA256).Hash; Expected=$phaseHash },
    @{ Name='runtime Wavelog history Phase 2 patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-wavelog-history-phase2.patch') -Algorithm SHA256).Hash; Expected=$phase2Hash },
    @{ Name='runtime AutoDX quiet QSY patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-autodx-quiet-qsy-fix.patch') -Algorithm SHA256).Hash; Expected=$quietQsyHash },
    @{ Name='runtime native AutoDX policy patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-autodx-native-policy.patch') -Algorithm SHA256).Hash; Expected=$nativePolicyHash },
    @{ Name='runtime UI persistence patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-ui-persistence.patch') -Algorithm SHA256).Hash; Expected=$uiPersistenceHash },
    @{ Name='runtime UI layout persistence patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-ui-layout-persistence.patch') -Algorithm SHA256).Hash; Expected=$uiLayoutPersistenceHash },
    @{ Name='runtime performance/decode/DXpedition patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-performance-decode-dxpedition.patch') -Algorithm SHA256).Hash; Expected=$performanceDecodeDxpeditionHash },
    @{ Name='runtime recent-QSO cooldown patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-recent-qso-cooldown.patch') -Algorithm SHA256).Hash; Expected=$recentQsoCooldownHash },
    @{ Name='runtime permanent slot-dedupe patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-permanent-slot-dedupe.patch') -Algorithm SHA256).Hash; Expected=$permanentSlotDedupeHash },
    @{ Name='runtime compact status-combinations patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-compact-status-combinations.patch') -Algorithm SHA256).Hash; Expected=$compactStatusCombinationsHash },
    @{ Name='runtime US states chase patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-us-states-chase.patch') -Algorithm SHA256).Hash; Expected=$usStatesChaseHash },
    @{ Name='runtime cluster chase scheduler patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-cluster-chase-scheduler.patch') -Algorithm SHA256).Hash; Expected=$clusterChaseSchedulerHash },
    @{ Name='runtime US-state DXCC guard patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-us-state-dxcc-guard.patch') -Algorithm SHA256).Hash; Expected=$usStateDxccGuardHash },
    @{ Name='runtime composable award-hunting patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-composable-award-hunting.patch') -Algorithm SHA256).Hash; Expected=$composableAwardHuntingHash },
    @{ Name='runtime priority-patrol/FT4 patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-priority-patrol-ft4.patch') -Algorithm SHA256).Hash; Expected=$priorityPatrolFt4Hash },
    @{ Name='runtime final-exchange repeat patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-repeat-final-exchange.patch') -Algorithm SHA256).Hash; Expected=$repeatFinalExchangeHash },
    @{ Name='runtime band-marker/country-exclusion patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-band-markers-country-exclusions.patch') -Algorithm SHA256).Hash; Expected=$bandMarkersCountryExclusionsHash },
    @{ Name='runtime exchange-only reply guard patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-exchange-only-reply-guard.patch') -Algorithm SHA256).Hash; Expected=$exchangeOnlyReplyGuardHash },
    @{ Name='runtime manual-QSO lifecycle UI patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-manual-qso-lifecycle-ui.patch') -Algorithm SHA256).Hash; Expected=$manualQsoLifecycleUiHash },
    @{ Name='runtime station RF panel patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-station-rf-panel.patch') -Algorithm SHA256).Hash; Expected=$stationRfPanelHash },
    @{ Name='runtime manual target lock patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-manual-target-lock.patch') -Algorithm SHA256).Hash; Expected=$manualTargetLockHash },
    @{ Name='runtime late-reply QSY guard patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-late-reply-qsy-guard.patch') -Algorithm SHA256).Hash; Expected=$lateReplyQsyGuardHash },
    @{ Name='runtime adaptive-retry/ignore patch'; Actual=(Get-FileHash (Join-Path $runtime 'om0rx-adaptive-retry-ignore.patch') -Algorithm SHA256).Hash; Expected=$adaptiveRetryIgnoreHash },
    @{ Name='runtime aggregate source'; Actual=(Get-FileHash (Join-Path $runtime 'source-attestation.patch') -Algorithm SHA256).Hash; Expected=$sourceDiffHash },
    @{ Name='manifest base patch'; Actual=$manifest.patch_sha256; Expected=$baseHash },
    @{ Name='manifest AutoDX Phase 1 patch'; Actual=$manifest.autodx_phase1_patch_sha256; Expected=$phaseHash },
    @{ Name='manifest Wavelog history Phase 2 patch'; Actual=$manifest.wavelog_history_phase2_patch_sha256; Expected=$phase2Hash },
    @{ Name='manifest AutoDX quiet QSY patch'; Actual=$manifest.autodx_quiet_qsy_fix_patch_sha256; Expected=$quietQsyHash },
    @{ Name='manifest native AutoDX policy patch'; Actual=$manifest.autodx_native_policy_patch_sha256; Expected=$nativePolicyHash },
    @{ Name='manifest UI persistence patch'; Actual=$manifest.ui_persistence_patch_sha256; Expected=$uiPersistenceHash },
    @{ Name='manifest UI layout persistence patch'; Actual=$manifest.ui_layout_persistence_patch_sha256; Expected=$uiLayoutPersistenceHash },
    @{ Name='manifest performance/decode/DXpedition patch'; Actual=$manifest.performance_decode_dxpedition_patch_sha256; Expected=$performanceDecodeDxpeditionHash },
    @{ Name='manifest recent-QSO cooldown patch'; Actual=$manifest.recent_qso_cooldown_patch_sha256; Expected=$recentQsoCooldownHash },
    @{ Name='manifest permanent slot-dedupe patch'; Actual=$manifest.permanent_slot_dedupe_patch_sha256; Expected=$permanentSlotDedupeHash },
    @{ Name='manifest compact status-combinations patch'; Actual=$manifest.compact_status_combinations_patch_sha256; Expected=$compactStatusCombinationsHash },
    @{ Name='manifest US states chase patch'; Actual=$manifest.us_states_chase_patch_sha256; Expected=$usStatesChaseHash },
    @{ Name='manifest cluster chase scheduler patch'; Actual=$manifest.cluster_chase_scheduler_patch_sha256; Expected=$clusterChaseSchedulerHash },
    @{ Name='manifest US-state DXCC guard patch'; Actual=$manifest.us_state_dxcc_guard_patch_sha256; Expected=$usStateDxccGuardHash },
    @{ Name='manifest composable award-hunting patch'; Actual=$manifest.composable_award_hunting_patch_sha256; Expected=$composableAwardHuntingHash },
    @{ Name='manifest priority-patrol/FT4 patch'; Actual=$manifest.priority_patrol_ft4_patch_sha256; Expected=$priorityPatrolFt4Hash },
    @{ Name='manifest final-exchange repeat patch'; Actual=$manifest.repeat_final_exchange_patch_sha256; Expected=$repeatFinalExchangeHash },
    @{ Name='manifest band-marker/country-exclusion patch'; Actual=$manifest.band_markers_country_exclusions_patch_sha256; Expected=$bandMarkersCountryExclusionsHash },
    @{ Name='manifest exchange-only reply guard patch'; Actual=$manifest.exchange_only_reply_guard_patch_sha256; Expected=$exchangeOnlyReplyGuardHash },
    @{ Name='manifest manual-QSO lifecycle UI patch'; Actual=$manifest.manual_qso_lifecycle_ui_patch_sha256; Expected=$manualQsoLifecycleUiHash },
    @{ Name='manifest station RF panel patch'; Actual=$manifest.station_rf_panel_patch_sha256; Expected=$stationRfPanelHash },
    @{ Name='manifest manual target lock patch'; Actual=$manifest.manual_target_lock_patch_sha256; Expected=$manualTargetLockHash },
    @{ Name='manifest late-reply QSY guard patch'; Actual=$manifest.late_reply_qsy_guard_patch_sha256; Expected=$lateReplyQsyGuardHash },
    @{ Name='manifest adaptive-retry/ignore patch'; Actual=$manifest.adaptive_retry_ignore_patch_sha256; Expected=$adaptiveRetryIgnoreHash },
    @{ Name='manifest source diff'; Actual=$manifest.source_diff_sha256; Expected=$sourceDiffHash },
    @{ Name='compiled executable'; Actual=$compiled.executable_sha256; Expected=$sourceExeHash },
    @{ Name='runtime executable vs compiled'; Actual=$runtimeExeHash; Expected=$sourceExeHash },
    @{ Name='manifest executable'; Actual=$manifest.executable_sha256; Expected=$runtimeExeHash }
)) {
    if ([string]$check.Actual -ne [string]$check.Expected) {
        throw "$($check.Name) hash mismatch: actual=$($check.Actual) expected=$($check.Expected)"
    }
}
if ('autodx_runtime_config_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks autodx_runtime_config_v1' }
if ('wavelog_history_authority_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks wavelog_history_authority_v1' }
if ('wavelog_history_delta_v2' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks wavelog_history_delta_v2' }
if ('autodx_quiet_qsy_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks autodx_quiet_qsy_v1' }
if ('autodx_native_policy_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks autodx_native_policy_v1' }
if ('ui_state_persistence_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks ui_state_persistence_v1' }
if ('autodx_performance_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks autodx_performance_v1' }
if ('dxpedition_chase_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks dxpedition_chase_v1' }
if ('recent_qso_cooldown_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks recent_qso_cooldown_v1' }
if ('permanent_slot_dedupe_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks permanent_slot_dedupe_v1' }
if ('band_dxcc_continent_override_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks band_dxcc_continent_override_v1' }
if ('decode_status_columns_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks decode_status_columns_v1' }
if ('compact_status_combinations_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks compact_status_combinations_v1' }
if ('cluster_chase_scheduler_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks cluster_chase_scheduler_v1' }
if ('us_state_dxcc_guard_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks us_state_dxcc_guard_v1' }
if ('us_states_chase_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks us_states_chase_v1' }
if ('decode_qso_panel_status_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks decode_qso_panel_status_v1' }
if ('priority_patrol_fallback_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks priority_patrol_fallback_v1' }
if ('ft4_dual_decode_layout_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks ft4_dual_decode_layout_v1' }
if ('ft4_autodx_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks ft4_autodx_v1' }
if ('repeat_final_exchange_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks repeat_final_exchange_v1' }
if ('band_markers_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks band_markers_v1' }
if ('country_exclusions_by_band_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks country_exclusions_by_band_v1' }
if ('exchange_only_reply_guard_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks exchange_only_reply_guard_v1' }
if ('manual_qso_lifecycle_ui_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks manual_qso_lifecycle_ui_v1' }
if ('station_rf_panel_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks station_rf_panel_v1' }
if ('manual_target_lock_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks manual_target_lock_v1' }
if ('late_reply_qsy_guard_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks late_reply_qsy_guard_v1' }
if ('adaptive_retry_ignore_v1' -notin @($manifest.capabilities)) { throw 'Runtime manifest lacks adaptive_retry_ignore_v1' }
Write-Host "MSHV release attestation passed: base=$baseHash phase1=$phaseHash phase2=$phase2Hash quietQsy=$quietQsyHash nativePolicy=$nativePolicyHash uiPersistence=$uiPersistenceHash uiLayoutPersistence=$uiLayoutPersistenceHash performanceDecodeDxpedition=$performanceDecodeDxpeditionHash source=$sourceDiffHash exe=$runtimeExeHash"
