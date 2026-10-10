"""Contracts for Phase 1 active Auto DX runtime wiring.

These tests deliberately inspect the staged native source.  Packaging has a
separate clean-replay/build attestation gate; this suite catches decorative UI
or backend-only settings before an expensive Windows/Qt build.
"""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(
    os.environ.get("OM0RX_MSHV_TEST_SOURCE_ROOT", ROOT / "data/build/mshv-auto-dx/src")
).resolve()
SOURCE = SOURCE_ROOT / "MSHV_2762" / "src"


def _text(relative: str) -> str:
    return (SOURCE / relative).read_text(encoding="utf-8")


def test_active_core_loads_runtime_configuration_without_opening_dialog():
    core = _text("HvAutoDxer/autodxercore.cpp")
    config = _text("HvAutoDxer/autodxruntimeconfig.h")
    assert "loadRuntimeConfig(settingsPath);" in core
    runtime_load = core.split("void AutoDxerCore::loadRuntimeConfig", 1)[1].split(
        "QJsonObject AutoDxerCore::runtimeConfigStatus", 1
    )[0]
    assert "m_bandManager->loadSettings(settingsPath);" in runtime_load
    assert runtime_load.index("m_bandManager->loadSettings(settingsPath);") < runtime_load.index(
        'AUTODX-RUNTIME-CONFIG: modes=%1 bands=%2'
    )
    panel_hydration = _text("main_ms.cpp")
    assert panel_hydration.index("m_autoDxerPanel->setAppPath(App_Path);") < panel_hydration.index(
        'm_autoDxerCore->bandManager()->loadSettings(App_Path + "/settings");'
    )
    assert 'settings.value("AutoDx/Modes", "FT8,FT4")' in config
    assert "modesValue.type() == QVariant::StringList" in config
    assert "modesValue.toStringList()" in config
    assert 'settings.value("BandSwitching/Enabled", false)' in config
    assert '"AutomationTiming/QuietBandEmptyPeriods", 5' in config
    assert "emptyDecodePeriodsExpired" in config
    assert 'settings.value("BandSelection/EnabledBands"' in _text("HvAutoDxer/bandmanager.cpp")
    for key in (
        "AutoDx/ATNOChaseType",
        "AutoDx/ScarceThreshold",
        "SpotSources/RbnEnabled",
        "SpotSources/PskEnabled",
        "SpotSources/DxcEnabled",
        "SpotSources/UsOnlyFilter",
        "TargetPriority/NewDxcc",
        "TargetPriority/NewBandSlot",
        "TargetPriority/NewGrid",
    ):
        assert key in config


def test_cross_band_qsy_has_an_explicit_false_by_default_gate():
    core = _text("HvAutoDxer/autodxercore.cpp")
    body = core.split("void AutoDxerCore::checkCrossBandAlerts()", 1)[1].split(
        "void AutoDxerCore::", 1
    )[0]
    assert "if (!m_bandSwitchingEnabled && !m_fullHuntingEnabled)" in body
    assert body.index("if (!m_bandSwitchingEnabled && !m_fullHuntingEnabled)") < body.index("beginBandChange")


def test_full_hunting_coordinates_ft8_ft4_confirmation_patrol():
    config = _text("HvAutoDxer/autodxruntimeconfig.h")
    core_h = _text("HvAutoDxer/autodxercore.h")
    core = _text("HvAutoDxer/autodxercore.cpp")
    scorer = _text("HvAutoDxer/targetscorer.cpp")
    settings = _text("HvAutoDxSettings/hvautodxsettings.cpp")
    main = _text("main_ms.cpp")
    assert '"FullHunting/Enabled", false' in config
    assert '"FullHunting/VisitSeconds", 150' in config
    assert "qBound(120" in config and ", 180)" in config
    assert "requestModeChange(QString mode)" in core_h
    assert "advanceFullHuntingVisit()" in core
    assert 'normalized == "FT8" || normalized == "FT4"' in core
    assert "m_fullHuntingVisitedModes" in core
    check_timeout = core.split("void AutoDxerCore::checkTimeout()", 1)[1].split(
        "void AutoDxerCore::switchBand", 1
    )[0]
    full_hunt_timeout = check_timeout.split("if (m_fullHuntingEnabled) {", 1)[1].split(
        "const bool emptyPeriodExpired", 1
    )[0]
    assert "advanceFullHuntingVisit()" in full_hunt_timeout
    assert full_hunt_timeout.rstrip().endswith("}")
    assert "return;" in full_hunt_timeout
    assert "isDxccConfirmedBandModeByCall" in scorer
    assert "Full hunting: no DXCC confirmation need" not in scorer
    assert "NB/NM call rows" in scorer
    assert "m_dxpeditionMaxSpotAgeSeconds" in core
    assert "Enable full FT8/FT4 confirmation hunting" in settings
    assert 'new QGroupBox("Full Hunting Mode")' in settings
    assert "mainLayout->addWidget(m_fullHuntingGroup)" in settings
    assert settings.index("mainLayout->addWidget(m_fullHuntingGroup)") < settings.index(
        "mainLayout->addWidget(scrollArea, 1)"
    )
    assert "SetModeFromAutoDxer" in main
    assert "if (f_decoder_busy)" in main
    assert "m_pendingAutoDxerMode = normalized" in main
    assert "deferred until decoder idle" in main
    assert "if (f_decoder_busy) return;" in main


def test_fftw_planning_and_destruction_are_serialized():
    decoder_pom = (SOURCE / "HvDecoderMs" / "decoderpom.cpp").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "static QMutex _fftw_planner_mutex" in decoder_pom
    assert decoder_pom.count("QMutexLocker plannerLock(&_fftw_planner_mutex)") >= 2
    assert "static bool _block_th_all_" not in decoder_pom


def test_full_hunting_protects_final_exchange_and_fair_band_sweep():
    core_h = _text("HvAutoDxer/autodxercore.h")
    core = _text("HvAutoDxer/autodxercore.cpp")
    logged = core.split("void AutoDxerCore::onMSHVQsoLogged", 1)[1].split(
        "void AutoDxerCore::finishPostQsoGuard", 1
    )[0]
    evaluate = core.split("void AutoDxerCore::evaluateTargets", 1)[1].split(
        "qint64 AutoDxerCore::currentTargetAttemptElapsedMs", 1
    )[0]
    next_band = core.split("int AutoDxerCore::nextPatrolBand", 1)[1].split(
        "QSet<int> AutoDxerCore::openPatrolBands", 1
    )[0]
    assert "finishPostQsoGuard" in core_h
    assert 'const int guardMs = mode == "FT4" ? 30000 : 60000;' in logged
    assert 'auditEvent("post-qso-guard-started"' in logged
    assert 'if (postQsoGuardActive()) return;' in evaluate
    timeout = core.split("void AutoDxerCore::checkTimeout", 1)[1].split(
        "void AutoDxerCore::switchBand", 1
    )[0]
    switch_band = core.split("void AutoDxerCore::switchBand", 1)[1].split(
        "bool AutoDxerCore::advanceFullHuntingVisit", 1
    )[0]
    assert "postQsoGuardActive()" in timeout
    assert 'fields["reason"] = "post-qso-receive-guard";' in switch_band
    assert "fullHuntingVisitElapsedMs()" in evaluate
    assert "advanceFullHuntingVisit()" in evaluate
    assert evaluate.index("advanceFullHuntingVisit()") < evaluate.index("getActiveDecodes")
    assert "index = (index - 1 + enabled.size()) % enabled.size();" in next_band
    assert "suspendFullHuntingForDetour();" in core
    assert "resumeFullHuntingAfterDetour()" in core


def test_only_all_time_new_dxcc_gets_uninterrupted_thirty_minute_lease():
    core = _text("HvAutoDxer/autodxercore.cpp")
    core_h = _text("HvAutoDxer/autodxercore.h")
    assert "m_currentTargetIsDxpedition" in core_h
    assert "const bool newDxccLease = m_currentTargetIsATNO;" in core
    assert "baseBudgetSeconds = qMax(baseBudgetSeconds, m_atnoMinimumCallSeconds);" in core
    assert "if (m_currentTargetIsATNO)" in core
    assert "ownedAttemptSeconds = m_currentTargetIsATNO" in core
    assert 'budget["new_dxcc_30_minute_lease_active"] = newDxccLease;' in core
    assert 'budget["dxpedition_30_minute_lease_active"] = false;' in core


def test_ft8_ft4_mode_policy_controls_effective_state_and_is_reported():
    core = _text("HvAutoDxer/autodxercore.cpp")
    main = _text("main_ms.cpp")
    config = _text("HvAutoDxer/autodxruntimeconfig.h")
    assert 'QStringList() << "FT8" << "FT4"' in config
    set_enabled = core.split("void AutoDxerCore::setEnabled(bool enabled)", 1)[1].split(
        "void AutoDxerCore::", 1
    )[0]
    assert "m_desiredEnabled = enabled;" in set_enabled
    assert "isConfiguredMode(m_currentMode)" in set_enabled
    assert "m_historicalNoveltyAllowed" in set_enabled
    assert "m_enabled = effective;" in set_enabled
    assert "m_autoDxerCore->setCurrentMode(ModeStr(s_mod_ident));" in main
    assert 'state["desired_enabled"] = m_autoDxerCore->desiredEnabled();' in main
    assert 'state["autodx_config"] = m_autoDxerCore->runtimeConfigStatus();' in main
    assert 'result["historical_novelty_allowed"] = m_historicalNoveltyAllowed;' in core


def test_clean_patch_harness_replays_all_maintained_patches_before_attestation():
    script = (ROOT / "scripts" / "mshv" / "test_clean_patch.ps1").read_text(
        encoding="utf-8"
    )
    base = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-integration.patch')")
    phase1 = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-autodx-phase1.patch')")
    phase2 = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-wavelog-history-phase2.patch')")
    quiet_qsy = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-autodx-quiet-qsy-fix.patch')")
    native_policy = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-autodx-native-policy.patch')")
    ui_persistence = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-ui-persistence.patch')")
    ui_layout = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-ui-layout-persistence.patch')")
    performance = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-performance-decode-dxpedition.patch')")
    permanent_dedupe = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-permanent-slot-dedupe.patch')")
    compact_status = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-compact-status-combinations.patch')")
    us_states = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-us-states-chase.patch')")
    cluster_chase = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-cluster-chase-scheduler.patch')")
    us_state_guard = script.index("git -C $source apply (Join-Path $ProjectRoot 'docs\\mshv\\om0rx-us-state-dxcc-guard.patch')")
    attest = script.index("'assert_source.ps1'")
    assert base < phase1 < phase2 < quiet_qsy < native_policy < ui_persistence < ui_layout < performance < permanent_dedupe < compact_status < us_states < cluster_chase < us_state_guard < attest


def test_native_timing_schedules_and_engaged_qso_guards_are_wired():
    core = _text("HvAutoDxer/autodxercore.cpp")
    main = _text("main_ms.cpp")
    config = _text("HvAutoDxer/autodxruntimeconfig.h")
    bands = _text("HvAutoDxer/bandmanager.cpp")
    for key in (
        "NormalCallSeconds", "QuietBandSeconds", "QuietBandEmptyPeriods", "TargetHeardFreshSeconds",
        "CrossBandVerifySeconds", "BandSwitchCooldownSeconds",
        "PersistNewDxccWhileHeard", "PersistNewBandSlotWhileHeard",
    ):
        assert f'AutomationTiming/{key}' in config
    assert "AutoDxTimingPolicy::normalAttemptExpired" in core
    assert "AutoDxTimingPolicy::quietBandExpired" in core
    assert "AutoDxTimingPolicy::emptyDecodePeriodsExpired" in core
    assert "!m_bandManager->isBandOpenNow(m_currentBandIndex)" in core
    assert "AutoDxTimingPolicy::noveltyPersists" in core
    assert "chaseType == 1 || chaseType == 3" in config
    assert "chaseType == 2 || chaseType == 3" in config
    assert "m_waitingForSlotAnalysis" in core.split(
        "void AutoDxerCore::checkSameBandNonStdFreqAlerts()", 1
    )[1].split("void AutoDxerCore::", 1)[0]
    same_band_alert = core.split(
        "void AutoDxerCore::checkSameBandNonStdFreqAlerts()", 1
    )[1].split("void AutoDxerCore::", 1)[0]
    assert "!m_bandManager->isBandOpenNow(m_currentBandIndex)" in same_band_alert
    slot_callback = core.split(
        "void AutoDxerCore::onSlotAnalysisReady", 1
    )[1].split("void AutoDxerCore::", 1)[0]
    assert "SLOT-ANALYSIS: Band schedule closed; deferred target cancelled" in slot_callback
    band_complete = core.split(
        "void AutoDxerCore::onBandChangeComplete", 1
    )[1].split("void AutoDxerCore::onBandChangeCompleteForRequest", 1)[1].split(
        "void AutoDxerCore::", 1
    )[0]
    assert "destination schedule closed during QSY" in band_complete
    assert "engagedActiveCall" in core
    assert "!m_targetRespondedToUs" in core.split(
        "bool AutoDxerCore::cancelPendingWavelogPaths()", 1
    )[1].split("void AutoDxerCore::clearPendingCrossBandVerification", 1)[0]
    assert 'QString("BandSchedules/Band%1")' in bands
    assert "i >= 3 && i <= 14" in main


def test_quiet_expiry_uses_actual_target_ownership_and_failed_qsy_cleans_up():
    core = _text("HvAutoDxer/autodxercore.cpp")
    main = _text("main_ms.cpp")
    timeout = core.split("void AutoDxerCore::checkTimeout()", 1)[1].split(
        "void AutoDxerCore::switchBand(bool emptyPeriodOverride)", 1
    )[0]
    evaluate = core.split("void AutoDxerCore::evaluateTargets()", 1)[1].split(
        "void AutoDxerCore::feedToQueue", 1
    )[0]
    assert "evaluateTargets();" in timeout
    assert timeout.index("quietBandExpired") < timeout.index("evaluateTargets();")
    assert "m_waitingForSlotAnalysis" in timeout
    assert "m_emptyDecodePeriods" in timeout
    assert "scheduleOverride || emptyPeriodOverride" in core
    assert "getBestTarget(local)" not in timeout
    assert "if (best.priority > 0) {\n        resetQuietBandTimer();" not in evaluate
    assert "void AutoDxerCore::onBandChangeFailedForRequest" in core
    assert "if (!m_quietBandTimer.isValid()) m_quietBandTimer.start();" in core
    assert "m_autoDxerBandChangePending" in main
    band_qsy = main.split("void Main_Ms::SetBandFromAutoDxer", 1)[1].split(
        "void Main_Ms::SetDialFreqFromAutoDxer", 1
    )[0]
    assert band_qsy.count("onBandChangeFailedForRequest(") == 1
    assert "gate->prepare" not in band_qsy
    assert "finalGate->confirm" not in band_qsy
    assert "onBandChangeCompleteForRequest" in band_qsy
    assert "activeBandChangeRequestId" in main
    assert "requestId != m_bandChangeRequestId" in core
    assert "observedAtDestination" in core
    assert main.count('invalidateAndNotify(this, "autodx-band-qsy")') == 1
    tx = _text("HvTxW/hvtxw.cpp")
    stop_auto = tx.split("void HvTxW::StopAuto()", 1)[1].split(
        "void HvTxW::auto_on()", 1
    )[0]
    assert "noteInternalAutoStopped" in stop_auto
    assert "invalidate" not in stop_auto


def test_full_attempt_ownership_and_directed_caller_preemption_are_native():
    core = _text("HvAutoDxer/autodxercore.cpp")
    scorer = _text("HvAutoDxer/targetscorer.cpp")
    decode_complete = core.split(
        "void AutoDxerCore::onDecodeComplete", 1
    )[1].split("void AutoDxerCore::processListeningState", 1)[0]
    preempt = core.split(
        "void AutoDxerCore::considerCallingMePreemption", 1
    )[1].split("bool AutoDxerCore::resumeSuspendedTarget", 1)[0]
    resume = core.split(
        "bool AutoDxerCore::resumeSuspendedTarget", 1
    )[1].split("void AutoDxerCore::feedToQueue", 1)[0]
    assert "currentTargetAttemptElapsedMs()" in decode_complete
    assert "engagedProgressExpired" in decode_complete
    assert "m_lastTargetProgressUtc.msecsTo(now)" in decode_complete
    assert "const bool attemptExpired" in decode_complete
    assert "terminalClearCurrentTarget(reason, true);" in decode_complete
    assert "not heard locally for" not in decode_complete
    assert "considerCallingMePreemption(localDecode);" in core
    assert "m_targetRespondedToUs || m_currentTarget.isCallingMe" in preempt
    assert "m_suspendedTargetElapsedMs = currentTargetAttemptElapsedMs();" in preempt
    assert "CALLING-ME-PREEMPT" in preempt
    assert "CALLING-ME-RECENTLY-WORKED" in preempt
    assert "m_targetAttemptElapsedOffsetMs = elapsedMs;" in resume
    assert "CALLING-ME-RESUME" in resume
    # Directed callers receive priority, but never bypass permanent exact-slot
    # dedupe or a pending Wavelog write.
    assert "Q_UNUSED(isCallingMe);" in core
    assert "if (isPendingWavelogCall(callsign)) return false;" in core
    assert "if (isPendingWavelogCall(decode.callsign))" in scorer
    assert "!target.isCallingMe && decode.snr < m_selectionConfig.minSignal" in scorer


def test_initial_enable_happens_only_after_upstream_control_signals_are_connected():
    main = _text("main_ms.cpp")
    panel = _text("HvAutoDxer/autodxerpanel.cpp")
    configure = main.index("m_autoDxerPanel->setAppPath(App_Path);")
    cq_guard = main.index("SIGNAL(requestDisableCQOnFreeSlot())")
    auto_enable = main.index("SIGNAL(requestEnableAuto())")
    auto_disable = main.index("SIGNAL(requestDisableAuto())")
    assert cq_guard < configure
    assert auto_enable < configure
    assert auto_disable < configure
    assert main.index("setCurrentMode(ModeStr(s_mod_ident));") < configure
    assert "m_enableCheck->setChecked(m_core->desiredEnabled());" in panel
    assert "m_usGridOnlyCheck->setChecked(m_core->targetScorer()->isUSGridOnly());" in panel
    assert 'settings.value("AutoDx/Enabled", true)' not in panel
    assert 'settings.value("GridChase/USOnly", true)' not in panel
    assert "m_scarceThresholdSpin->setValue(m_core->scarceTargetThreshold());" in panel
    assert "const int atnoChaseType = static_cast<int>(m_core->atnoChaseType());" in panel
    assert 'settings.value("AutoDx/ScarceThreshold"' not in panel
    assert 'settings.value("AutoDx/ATNOChaseType"' not in panel


def test_panel_startup_only_renders_authoritative_core_without_policy_writes():
    panel = _text("HvAutoDxer/autodxerpanel.cpp")
    load = panel.split("void AutoDxerPanel::loadEnableFromSettings()", 1)[1].split(
        "void AutoDxerPanel::loadBandSelectionFromSettings()", 1
    )[0]
    bands = panel.split("void AutoDxerPanel::loadBandSelectionFromSettings()", 1)[1].split(
        "void AutoDxerPanel::saveBandSelectionToSettings()", 1
    )[0]
    display = panel.split("void AutoDxerPanel::updateStatusDisplay()", 1)[1].split(
        "void AutoDxerPanel::onImportAdif()", 1
    )[0]

    assert "QSettings" not in load
    assert "setTargetWeights" not in load
    assert "setMinSNR" not in load
    assert "m_core->setEnabled" not in load
    assert load.count("QSignalBlocker") >= 8
    assert "targetScorer()->minSNR()" in load
    assert "spotAggregator()->rbnEnabled()" in load
    assert "spotAggregator()->pskrEnabled()" in load
    assert "QSettings" not in bands
    assert "bandManager()->getEnabledBands()" in bands
    assert bands.count("QSignalBlocker") >= 3
    assert "QSignalBlocker" in display
    assert "desiredEnabled()" in display
    assert "isEnabled()" not in display


def test_native_us_spotter_wording_reports_rare_dx_exception_semantics():
    panel = _text("HvAutoDxer/autodxerpanel.cpp")
    assert 'QCheckBox("US Spotters Preferred")' in panel
    assert "rare-DX exceptions remain eligible" in panel
    assert "international spots will be ignored" not in panel


def test_runtime_configuration_does_not_open_network_during_load():
    aggregator = _text("HvAutoDxer/spotaggregator.cpp")
    assert aggregator.count("if (!m_cleanupTimer->isActive()) return;") >= 3
    assert "m_pskrEnabled &&\n        m_cleanupTimer->isActive()" in aggregator
    assert "void SpotAggregator::setPSKRPollInterval(int seconds)" in aggregator


def test_every_external_source_requires_explicit_active_mode_before_ingest_or_qsy():
    config = _text("HvAutoDxer/autodxruntimeconfig.h")
    aggregator = _text("HvAutoDxer/spotaggregator.cpp")
    cluster = _text("HvAutoDxer/dxclusterclient.cpp")
    core = _text("HvAutoDxer/autodxercore.cpp")
    assert 'normalized == "FT8" || normalized == "FT4"' in config
    assert '(FT8|FT4)' in aggregator
    assert 'const QString mode = obj["mode"].toString()' in aggregator
    assert 'attrs.value("mode")' in aggregator
    assert aggregator.count("AutoDxRuntimeConfig::acceptsExternalMode") >= 4
    assert 'm_dxClusterClient->setMode(m_mode);' in aggregator
    assert 'socket->write(QByteArray("set/") + mode' in cluster
    assert "dial-frequency guess is not mode" in cluster.lower()
    assert 'mode.compare(m_mode, Qt::CaseInsensitive) != 0' in cluster
    cross = core.split("void AutoDxerCore::checkCrossBandAlerts()", 1)[1].split(
        "void AutoDxerCore::checkSameBandNonStdFreqAlerts()", 1
    )[0]
    same = core.split("void AutoDxerCore::checkSameBandNonStdFreqAlerts()", 1)[1].split(
        "QString AutoDxerCore::bandName", 1
    )[0]
    assert "acceptsExternalMode(spot.mode)" in cross
    assert "acceptsExternalMode(spot.mode)" in same


def test_zero_priority_dimensions_cannot_trigger_alert_qsy():
    core = _text("HvAutoDxer/autodxercore.cpp")
    scorer = _text("HvAutoDxer/targetscorer.h")
    assert "priorityDXCCEnabled() const" in scorer
    assert "priorityBandSlotEnabled() const" in scorer
    assert core.count("m_targetScorer->priorityDXCCEnabled()") >= 2
    assert core.count("m_targetScorer->priorityBandSlotEnabled()") >= 2


def test_runtime_status_reports_every_phase1_operator_knob():
    core = _text("HvAutoDxer/autodxercore.cpp")
    status = core.split("QJsonObject AutoDxerCore::runtimeConfigStatus() const", 1)[1].split(
        "void AutoDxerCore::setCallsign", 1
    )[0]
    for field in (
        '"callsign"', '"grid"', '"min_snr"', '"grid_chase_enabled"',
        '"grid_chase_us_only"', '"target_priority"', '"eligibility"',
        '"enabled_bands"', '"auto_dx_modes"', '"band_switching_enabled"',
        '"atno_chase_type"', '"scarce_threshold"', '"spot_sources"',
    ):
        assert field in status
    for source in ('"rbn"', '"psk_reporter"', '"dx_cluster"', '"us_only"'):
        assert source in status


def test_native_target_owns_and_clears_wsjt_status_cache_without_control_side_effects():
    main = _text("main_ms.cpp")
    core = _text("HvAutoDxer/autodxercore.cpp")
    tx = _text("HvTxW/hvtxw.cpp")
    radio = _text("HvTxW/HvRadioNetW/radionetw.cpp")
    ownership = _text("HvAutoDxer/autodxstatusownership.h")
    provenance = _text("HvAutoDxer/autodxstatusprovenance.h")

    assert "&AutoDxerCore::targetChanged" in main
    assert "SyncAutoDxerStatusTarget" in main
    assert "const DxTarget startupTarget = m_autoDxerCore->currentTarget();" in main
    assert "m_autoDxerCore->targetRespondedToUs() || THvTxW->GetAutoIsOn()" in main
    assert "m_autoDxerCore->isEnabled());" in main
    assert main.index("m_autoDxerCore->setCurrentMode(ModeStr(s_mod_ident));") < main.index(
        "const DxTarget startupTarget = m_autoDxerCore->currentTarget();"
    )
    sync = tx.split("void HvTxW::SyncAutoDxerStatusTarget", 1)[1].split(
        "void HvTxW::RfreshDxParm", 1
    )[0]
    assert "m_autoDxStatusOwnership.targetChanged" in sync
    assert "reconcileIdleStartup" in sync
    assert 'SetDxParm("", le_rst_tx->getText(), "")' in sync
    assert "TRadioAndNetW->GetStatusDxGrid()" in sync
    assert "requestEnableAuto" not in sync
    assert "requestDisableAuto" not in sync
    assert "SetRigTxRx" not in sync
    assert "SetBand" not in sync
    assert "durableCall.isEmpty()" in ownership
    assert "currentLegacy == durableCall" in ownership
    assert "currentStatusGrid == durableGrid" in ownership
    assert "currentLegacy.isEmpty() || currentStatus.isEmpty()" in ownership
    assert "RetireProvenance" in ownership
    assert "if (qsoEngaged) return Decision();" in ownership
    assert "QSaveFile" in provenance
    assert 'object.value("owner").toString() != "mshv-native-autodx"' in provenance
    assert "maximumAgeSeconds()" in provenance
    assert "SendStatus(3);" in radio.split("void RadioAndNetW::SetDxParm", 1)[1].split(
        "void RadioAndNetW::SendStatus", 1
    )[0]
    set_dx = tx.split("void HvTxW::SetDxParm", 1)[1].split(
        "void HvTxW::SyncAutoDxerStatusTarget", 1
    )[0]
    assert "TRadioAndNetW->GetStatusDxCall()==dc" in set_dx
    assert "TRadioAndNetW->GetStatusDxGrid()==dxg" in set_dx
    assert "AutoDxStatusProvenance::store" in sync
    assert "AutoDxStatusProvenance::clear" in sync
    state_timer = main.split("connect(om0rxStateTimer", 1)[1].split(
        "om0rxStateTimer->start", 1
    )[0]
    assert "!statusTarget.isValid()" in state_timer
    assert "SyncAutoDxerStatusTarget" in state_timer

    # Authoritative clear paths publish an empty target. Successful log and
    # hard-budget completion are centralized in the terminal-clear helper.
    terminal_clear = core.split(
        "void AutoDxerCore::terminalClearCurrentTarget", 1
    )[1].split("void AutoDxerCore::onQSOComplete", 1)[0]
    logged = core.split("void AutoDxerCore::onMSHVQsoLogged", 1)[1].split(
        "void AutoDxerCore::onTargetQueued", 1
    )[0]
    assert core.count("emit targetChanged(m_currentTarget);") >= 5
    assert "emit targetChanged(m_currentTarget);" in terminal_clear
    assert 'auditEvent("post-qso-guard-started"' in logged
    post_guard = core.split("void AutoDxerCore::finishPostQsoGuard", 1)[1].split(
        "void AutoDxerCore::onTargetQueued", 1
    )[0]
    assert "terminalClearCurrentTarget" in post_guard


def test_native_settings_menu_controls_live_autodx_policy_and_watchdog():
    main = _text("main_ms.cpp")
    dialog = _text("HvAutoDxSettings/hvautodxsettings.cpp")
    panel_h = _text("HvAutoDxer/autodxerpanel.h")
    panel_cpp = _text("HvAutoDxer/autodxerpanel.cpp")

    assert 'new QMenu(tr("Settings"))' in main
    assert 'Auto DX, Bands, Filters && Watchdogs...' in main
    assert 'SLOT(onOpenSettings())' in main
    assert "void onOpenSettings();" in panel_h
    assert "txWatchdogParametersChanged" in panel_cpp
    assert 'setWindowTitle("MSHV :: Settings")' in dialog
    for key in (
        "Eligibility/FilterMatrixEnabled",
        "Eligibility/FilterContinents",
        "TargetPriority/PreferNonEurope",
        "Attempt/CallWindowSeconds",
        "Attempt/MaxConsecutiveWindows",
        "Attempt/SameTargetRetrySeconds",
        "BandSwitching/MinimumDwellSeconds",
        "Attempt/EngagedCompletionGraceSeconds",
        "TargetPriority/DxpeditionBoost",
    ):
        assert key in dialog
    assert "m_autoDxerCore->reloadRuntimeConfig()" in dialog
    assert "emit txWatchdogParametersChanged" in dialog
    assert 'nativeSettings.beginGroup("ms_settings")' in dialog
    load_body = dialog.split("void HvAutoDxSettings::loadSettings", 1)[1].split(
        "void HvAutoDxSettings::saveSettings", 1
    )[0]
    assert "applyToComponents();" not in load_body
    open_body = panel_cpp.split("void AutoDxerPanel::onOpenSettings", 1)[1]
    assert "saveSettings(m_appPath)" not in open_body
    assert "nullptr,  // native core reloads the authoritative band settings" in open_body


def test_dx_cluster_server_mode_can_transition_back_to_defaults_cleanly():
    core = _text("HvAutoDxer/autodxercore.cpp")
    client = _text("HvAutoDxer/dxclusterclient.cpp")
    config = core.split("void AutoDxerCore::loadRuntimeConfig", 1)[1].split(
        'emit debugMessage(QString("AUTODX-RUNTIME-CONFIG', 1
    )[0]
    assert config.index("clearDxClusterServers();") < config.index(
        "setUseDefaultServers(m_runtimeUseDefaultServers);"
    )
    assert "m_spotAggregator->addDefaultDxClusterServers();" in config
    clear = client.split("void DxClusterClient::clearServers()", 1)[1].split(
        "void DxClusterClient::start()", 1
    )[0]
    assert "qDeleteAll(m_sockets);" in clear
    assert "m_socketToServer.clear();" in clear


def test_dxpedition_dial_is_exclusive_until_standard_frequency_is_confirmed():
    core = _text("HvAutoDxer/autodxercore.cpp")
    header = _text("HvAutoDxer/autodxercore.h")

    assert "m_waitingForStandardDialReturn" in header
    assert "if (m_waitingForStandardDialReturn) return;" in core
    helper = core.split(
        "bool AutoDxerCore::requestStandardDialReturnIfNeeded", 1
    )[1].split("void AutoDxerCore::abandonCurrentTarget", 1)[0]
    assert "m_waitingForStandardDialReturn = true;" in helper
    assert "emit requestDialFreqChange(standardDial);" in helper
    abandon = core.split("void AutoDxerCore::abandonCurrentTarget", 1)[1].split(
        "void AutoDxerCore::terminalClearCurrentTarget", 1
    )[0]
    assert "targetWasDxpedition" in abandon
    assert "requestStandardDialReturnIfNeeded(reason)" in abandon
    dial = core.split("void AutoDxerCore::onDialFrequencyChanged", 1)[1]
    assert "standard dial confirmed; target selection resumed" in dial
