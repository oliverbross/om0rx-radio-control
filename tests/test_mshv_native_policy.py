"""Source contracts for the final native MSHV AutoDX policy patch."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(
    os.environ.get("OM0RX_MSHV_TEST_SOURCE_ROOT", ROOT / "data/build/mshv-auto-dx/src")
).resolve()
SOURCE = SOURCE_ROOT / "MSHV_2762" / "src"


def text(relative: str) -> str:
    return (SOURCE / relative).read_text(encoding="utf-8")


def test_native_config_exposes_wsjt_z_compatible_filter_matrix_and_defaults():
    config = text("HvAutoDxer/autodxruntimeconfig.h")
    for key in (
        "FilterMatrixEnabled", "FilterNewCall", "FilterNewDxcc",
        "FilterNewContinent", "FilterNewGrid", "FilterNewCqZone",
        "FilterNewItuZone", "FilterBandCall", "FilterBandDxcc",
        "FilterBandContinent", "FilterBandGrid", "FilterBandCqZone",
        "FilterBandItuZone", "FilterContinents", "FilterLotwOnly",
        "MinSignal", "Treat73AsCq", "WatchUnconfirmedDxcc",
    ):
        assert f'Eligibility/{key}' in config
    assert '"Selection/Order", "score"' in config
    assert '"Attempt/CallWindowSeconds", 120' in config
    assert 'requestedWindow >= 240 ? 240 : 120' in config
    assert '"Attempt/MaxConsecutiveWindows", 1' in config
    assert 'qBound(1, settings.value(' in config
    assert '"Attempt/MaxConsecutiveWindows", 1).toInt(), 20)' in config
    assert '"Attempt/SameTargetRetrySeconds", 1800' in config
    assert '"BandSwitching/MinimumDwellSeconds", 180' in config
    assert '"Eligibility/FilterNewCall", true' in config
    assert '"Eligibility/FilterNewDxcc", true' in config
    assert '"Eligibility/FilterNewGrid", true' in config
    assert '"TargetPriority/PreferNonEurope", true' in config
    assert '"TargetPriority/NonEuropeBoost", 7500' in config
    assert 'qBound(-30, settings.value(' in config
    assert '"Eligibility/MinSignal", c.minSnr).toInt(), 0)' in config


def test_policy_has_non_europe_lotw_ordering_retry_and_dwell_semantics():
    policy = text("HvAutoDxer/autodxselectionpolicy.h")
    scorer = text("HvAutoDxer/targetscorer.cpp")
    core = text("HvAutoDxer/autodxercore.cpp")
    assert 'r.scoreBoost = nonEuropeBoost' in policy
    assert 'lotwOnly && f.lotwKnown && !f.lotwMember' in policy
    assert 'selectionOrder == "last"' in scorer
    assert "a.decodedAt > b.decodedAt" in scorer
    assert 'm_targetRetryAfter.value(retryKey)' in core
    assert 'same-target-retry-delay' in core
    assert 'm_selectionConfig.canLeaveBand' in core
    assert 'minimum-band-dwell' in core
    assert 'highPriority || directedCaller || scheduleOverride' in policy
    assert 'if (!hasNewStatus || target.priority <= 0)' in scorer
    assert 'if (target.priority > 0 && watchedDxpedition' in scorer
    assert 'm_historicalNoveltyAllowed' in scorer and 'm_tracker' in scorer


def test_runtime_capabilities_come_from_actual_native_data_file_loads():
    core = text("HvAutoDxer/autodxercore.cpp")
    header = text("HvAutoDxer/autodxercore.h")
    assert "bool m_lotwMembershipCapability" in header
    assert "bool m_confirmedDxccDataAvailable" in header
    assert "m_lotwMembershipCapability = lotwDataAvailable" in core
    assert "m_confirmedDxccDataAvailable = confirmationDataAvailable" in core
    assert 'result["lotw_membership_capability"] = m_lotwMembershipCapability' in core
    assert 'result["confirmed_dxcc_data_available"] = m_confirmedDxccDataAvailable' in core
    assert 'Capabilities/LotwMembership' not in core


def test_history_tracker_supplies_all_time_and_band_category_facts():
    wrapper = text("HvAutoDxer/dxcctracker.cpp")
    tracker = text("HvDxccTracker/hvdxcctracker.cpp")
    for fact in (
        "newCall", "bandCall", "newDxcc", "bandDxcc", "newContinent",
        "bandContinent", "newGrid", "bandGrid", "newCqZone",
        "bandCqZone", "newItuZone", "bandItuZone",
    ):
        assert f"facts.{fact}" in wrapper
    for method in (
        "isCallWorkedAllTime", "isContinentWorkedAllTime", "isContinentWorked",
        "isCqZoneWorkedAllTime", "isCqZoneWorked", "isItuZoneWorkedAllTime",
        "isItuZoneWorked",
    ):
        assert f"HvDxccTracker::{method}" in tracker


def test_dxpedition_catalog_is_metadata_only_and_local_decode_gate_survives():
    core = text("HvAutoDxer/autodxercore.cpp")
    scorer = text("HvAutoDxer/targetscorer.cpp")
    assert 'settingsPath + "/database/dxpedition_watch.json"' in core
    assert 'watch.value("schema").toInt() == 1' in core
    assert 'watch.value("watch_max_age_seconds")' in core
    assert 'generated <= now && now <= expiresAt' in core
    assert 'm_dxpeditionWatchTimer->setInterval(5000)' in core
    assert 'm_dxpeditionWatchTimer->start()' in core
    assert 'fingerprintChanged' in core
    assert 'now < m_dxpeditionCatalogExpiresAt' in core
    assert 'm_targetScorer->setDxpeditionWatch' in core
    assert 'target.priority += m_dxpeditionBoost' in scorer
    feed = core.split("void AutoDxerCore::feedToQueue", 1)[1].split(
        "void AutoDxerCore::checkQueueStatus", 1
    )[0]
    assert "if (!foundCurrentBand)" in feed
    assert "if (!cacheCheck.isLocalDecode)" in feed


def test_dxpedition_settings_are_native_persistent_and_catalogue_driven():
    config = text("HvAutoDxer/autodxruntimeconfig.h")
    core_h = text("HvAutoDxer/autodxercore.h")
    core = text("HvAutoDxer/autodxercore.cpp")
    settings_h = text("HvAutoDxSettings/hvautodxsettings.h")
    settings = text("HvAutoDxSettings/hvautodxsettings.cpp")
    scorer = text("HvAutoDxer/targetscorer.cpp")
    for key in (
        "Enabled", "AllowSameBandOffStandardQsy", "AllowCrossBandQsy",
        "ChaseScope", "MinSpotters", "MaxSpotAgeSeconds", "TxOffsetHz",
        "ReturnToStandard",
    ):
        assert f'Dxpedition/{key}' in config
        assert f'Dxpedition/{key}' in settings
    assert "createDxpeditionGroup" in settings_h and "DXpedition Chase" in settings
    assert "Local verification timeout:" in settings
    assert "AutomationTiming/CrossBandVerifySeconds" in settings
    assert "isCataloguedDxpedition" in core_h
    assert "m_dxpeditionCallBands = valid ? callBandKeys" in core
    assert "isCataloguedDxpedition(callsign, bandIndex)" in core
    assert "hasLegacyRarePrefix" in core
    assert "isRareDXCallsign" not in core
    assert "m_dxpeditionMinSpotters" in core
    assert "m_dxpeditionMaxSpotAgeSeconds" in core
    assert "m_dxpeditionTxOffsetHz" in core
    assert "m_dxpeditionReturnToStandard" in core
    assert "facts.bandCall" in scorer
    assert "active-dxpedition-any-active" in scorer


def test_targets_tab_renders_active_owned_target_separately_from_candidates():
    panel = text("HvAutoDxer/autodxerpanel.cpp")
    refresh = panel.split("void AutoDxerPanel::refreshTargetList()", 1)[1].split(
        "void AutoDxerPanel::onUsOnlyToggled", 1
    )[0]
    assert "const DxTarget active = m_core->currentTarget()" in refresh
    assert 'QString("ACTIVE  %1  %2  %3 Hz")' in refresh
    assert "future candidates" in refresh
    assert "t.callsign.compare(active.callsign" in refresh
    assert "futureCount == 0" in refresh
    assert "No other eligible future candidates on this band" in refresh


def test_native_status_is_emitted_on_normal_engine_state_path_with_stable_identity():
    core_h = text("HvAutoDxer/autodxercore.h")
    core = text("HvAutoDxer/autodxercore.cpp")
    main = text("main_ms.cpp")
    assert "QJsonObject autoDxStatus() const" in core_h
    assert 'state["autodx_status"] = m_autoDxerCore->autoDxStatus()' in main
    for field in (
        'result["schema_version"]', 'result["selection_id"]',
        'result["target"]', 'result["selection_reason"]',
        'result["selection_class"]', 'result["selection_score"]',
        'result["attempt"]', 'result["budget"]', 'result["next_retry"]',
        'result["band_dwell"]', 'result["active_schedule"]',
        'result["skipped_reasons"]', 'result["last_directed_caller"]',
        'result["audit"]', 'result["dxpedition_catalog"]',
    ):
        assert field in core
    assert "QUuid::createUuid().toString(QUuid::WithoutBraces)" in core
    assert "m_selectionId = m_suspendedSelectionId" in core
    assert 'result["state"] = stateString()' in core


def test_native_window_and_waterfall_preferences_survive_restart_safely():
    main = text("main_ms.cpp")
    header = text("main_ms.h")
    entrypoint = text("main.cpp")

    for key in (
        "def_main_window_geometry",
        "def_main_window_maximized",
        "def_show_waterfall",
        "def_show_transmit_panel",
        "def_dxcc_chaser_geometry",
        "def_show_dxcc_chaser",
    ):
        assert main.count(f'"{key}') >= 2

    assert "CurrentNormalWindowGeometry()" in main
    assert "normalGeometry()" in main
    assert "w_sz==desktopw->width()" not in main
    assert "QGuiApplication::screens()" in main
    assert "availableGeometry()" in main
    assert "qBound(available.left()" in main
    assert "qBound(available.top()" in main
    assert "f_is_moved_to_prev_desk_pos = true" in main
    assert "restore_window_maximized = (st_res[109].toInt() != 0)" in main
    assert "sh_wf->setChecked(st_res[110].toInt() != 0)" in main
    assert "sh_wf->setChecked(true)" in main  # first-run compatibility
    assert "sh_tx->setChecked(st_res[111].toInt() != 0)" in main
    assert "sh_tx->setChecked(true)" in main  # first-run compatibility
    assert "dxcc_chaser_m->setChecked(true)" in main  # legacy default-visible
    assert "dxcc_chaser_m->setChecked(st_res[113].toInt() != 0)" in main
    assert "m_dxccChaserWindow->installEventFilter(this)" in main
    assert "event->type() == QEvent::Close && !closing_application" in main
    assert "window_state_save_timer->setSingleShot(true)" in main
    assert "QSaveFile file(path)" in main
    assert "if (!file.commit()) return" in main
    assert "SaveSettings();" in header.split("void closeEvent", 1)[1]
    assert "void ShowWithSavedWindowState()" in header
    assert "win.ShowWithSavedWindowState();" in entrypoint
    assert "if (restore_window_maximized) showMaximized();" in main

    save = main.split("void Main_Ms::Save_Settings", 1)[1].split(
        "void Main_Ms::SetBS1Text", 1
    )[0]
    assert save.index('out << "def_band_bt_sw="') < save.index(
        'out << "def_main_window_geometry="'
    )
    assert save.index('out << "def_flat_vdsp="') < save.index(
        'out << "def_band_bt_sw="'
    )
    assert save.index('out << "def_show_waterfall="') < save.index(
        'out << "def_show_transmit_panel="'
    ) < save.index('out << "def_dxcc_chaser_geometry="') < save.index(
        'out << "def_show_dxcc_chaser="'
    )

    restore = main.split("void Main_Ms::Read_Settings", 1)[1].split(
        "void Main_Ms::SaveSettings", 1
    )[0]
    assert 'if (geometryParts.count() == 4)' in restore
    assert "savedWidth > 0 && savedHeight > 0" in restore
    assert "ValidatedWindowGeometry(" in restore


def test_native_cross_band_fairness_and_pending_telemetry_contract():
    core = text("HvAutoDxer/autodxercore.cpp")
    header = text("HvAutoDxer/autodxercore.h")
    policy = text("HvAutoDxer/autodxselectionpolicy.h")
    assert "AutoDxCrossBandFairness::chooseBand" in core
    assert "a.score != b.score" in core
    assert "m_clusterChaseQueue.append(queued)" in core
    assert "m_crossBandAlertCursorBand = chosen.band" in core
    assert "crossBandRetryDeferred(spot.callsign, band, now)" in core
    assert "!m_bandManager->isBandOpenNow(band)" in core
    assert "struct AutoDxCrossBandFairness" in policy
    assert "m_crossBandAlertCursorBand" in header
    for field in (
        'pendingVerification["active"]',
        'pendingVerification["callsign"]',
        'pendingVerification["band_index"]',
        'pendingVerification["source"]',
        'pendingVerification["reason"]',
        'pendingVerification["terminal_reason"]',
    ):
        assert field in core
    clear = core.split("void AutoDxerCore::clearPendingCrossBandVerification()", 1)[1]
    clear = clear.split("bool AutoDxerCore::returnFromPendingCrossBandVerification", 1)[0]
    assert "m_pendingCrossBandSource.clear()" in clear
    assert "m_pendingCrossBandReason.clear()" in clear


def test_cluster_chase_queues_during_qso_and_overrides_continent_for_needed_awards():
    core = text("HvAutoDxer/autodxercore.cpp")
    runtime = text("HvAutoDxer/autodxruntimeconfig.h")
    tracker_h = text("HvDxccTracker/hvdxcctracker.h")
    assert "const bool qsoProtected" in core
    assert "if (qsoProtected || candidates.isEmpty()) return;" in core
    assert 'queued["continent_filter_overridden"] = true' in core
    for reason in (
        "new-dxcc", "new-band-slot", "us-state-needed",
        "continent-unconfirmed", "waz-zone-unconfirmed", "itu-zone-unconfirmed",
    ):
        assert reason in core
    assert "ClusterChase/ChaseUnconfirmedContinents" in runtime
    assert "ClusterChase/ChaseUnconfirmedCqZones" in runtime
    assert "ClusterChase/ChaseUnconfirmedItuZones" in runtime
    assert "isContinentConfirmed" in tracker_h
    assert "isCqZoneConfirmed" in tracker_h
    assert "isItuZoneConfirmed" in tracker_h


def test_native_cat_change_ownership_blocks_overlapping_alert_qsy():
    core = text("HvAutoDxer/autodxercore.cpp")
    cross = core.split("void AutoDxerCore::checkCrossBandAlerts()", 1)[1].split(
        "void AutoDxerCore::checkSameBandNonStdFreqAlerts()", 1
    )[0]
    same_band = core.split("void AutoDxerCore::checkSameBandNonStdFreqAlerts()", 1)[1].split(
        "CachedDecode AutoDxerCore::spotToCachedDecode", 1
    )[0]
    feed = core.split("void AutoDxerCore::feedToQueue", 1)[1].split(
        "void AutoDxerCore::checkQueueStatus", 1
    )[0]
    assert "catTransitionPending()" in cross
    assert "catTransitionPending()" in same_band
    assert 'noteSkipped("cat-band-change-in-flight:" + target.callsign)' in feed
    assert "if (catTransitionPending())" in feed
    evaluate = core.split("void AutoDxerCore::evaluateTargets()", 1)[1].split(
        "qint64 AutoDxerCore::currentTargetAttemptElapsedMs", 1
    )[0]
    preempt = core.split("void AutoDxerCore::considerCallingMePreemption", 1)[1].split(
        "bool AutoDxerCore::resumeSuspendedTarget", 1
    )[0]
    slot = core.split("void AutoDxerCore::onSlotAnalysisReady", 1)[1].split(
        "void AutoDxerCore::onDialFrequencyChanged", 1
    )[0]
    assert "if (catTransitionPending()) return;" in evaluate
    assert "if (catTransitionPending()) return;" in preempt
    assert "if (catTransitionPending()) return;" in slot
    helper = core.split("bool AutoDxerCore::catTransitionPending() const", 1)[1].split(
        "void AutoDxerCore::clearSuspendedTarget", 1
    )[0]
    assert "m_bandChangePending || !m_pendingCrossBandTerminalReason.isEmpty()" in helper


def test_logged_qso_and_hard_budget_are_terminal_selection_boundaries():
    core = text("HvAutoDxer/autodxercore.cpp")
    callback = core.split("void AutoDxerCore::onMSHVQsoLogged", 1)[1].split(
        "CachedDecode AutoDxerCore::spotToCachedDecode", 1
    )[0]
    terminal = core.split("void AutoDxerCore::terminalClearCurrentTarget", 1)[1].split(
        "void AutoDxerCore::resetQuietBandTimer", 1
    )[0]
    assert "m_state == WaitingForQSO" not in callback
    assert 'auditEvent("post-qso-guard-started"' in callback
    assert 'terminalClearCurrentTarget(QString("QSO completed with %1; receive guard complete")' in callback
    assert "resumeSuspendedTarget" not in callback
    assert "clearSuspendedTarget()" in terminal
    assert "m_targetRetryAfter.remove(retryKey)" in terminal
    assert "m_selectionId.clear()" in terminal
    assert 'auditEvent("target-terminal"' in terminal
    assert 'terminalClearCurrentTarget(reason, true)' in core


def test_external_spot_identity_is_frequency_aware_and_offstandard_qsy_is_cluster_gated():
    aggregator_h = text("HvAutoDxer/spotaggregator.h")
    aggregator = text("HvAutoDxer/spotaggregator.cpp")
    core = text("HvAutoDxer/autodxercore.cpp")
    assert "callsign@band@100-Hz frequency bucket" in aggregator_h
    assert 'QString::number(qMax(0, frequencyHz) / 100)' in aggregator
    assert 'spotKey(spot.callsign, spot.bandIndex, frequencyHz)' in aggregator
    assert 'spot.source == "RBN" || spot.source.startsWith("DxCluster:")' in core
    assert 'off-standard-qsy-needs-explicit-ft8-cluster' in core


def test_structured_audit_covers_selection_budget_stop_preempt_qsy_and_ptt_edges():
    core = text("HvAutoDxer/autodxercore.cpp")
    rig = text("HvRigControl/hvrigcontrol.cpp")
    assert '"om0rx.autodx.audit.v1"' in core
    for event in (
        '"target-selected"', '"target-stop"', '"retry-blocked"',
        '"directed-caller-preempt"', '"qsy-request"', '"qsy-complete"',
        '"qsy-failed"', '"qsy-deferred"',
    ):
        assert event in core
    for field in (
        'fields["selection_reason"]', 'fields["target_class"]',
        'fields["score"]', 'fields["attempt"]', 'fields["budget_seconds"]',
    ):
        assert field in core
    assert '"ptt-edge"' in rig and '\\"edge\\":\\"%1\\"' in rig
    lowest_ptt = rig.split("void HvRigControl::SetPtt_p", 1)[1].split(
        "void HvRigControl::SetQSOProgress", 1
    )[0]
    for forbidden in ("hasPermit", "consumePermitBlocking", "prefetch", "notePttRequest"):
        assert forbidden not in lowest_ptt


def test_native_policy_fixture_is_part_of_offline_test_runner():
    runner = (ROOT / "scripts/mshv/test_mshv.ps1").read_text(encoding="utf-8")
    assert "test_autodx_selection_policy.ps1" in runner
    fixture = (ROOT / "tests/mshv/autodx_selection_policy_test.cpp").read_text(encoding="utf-8")
    assert "sameTargetRetrySeconds == 1800" in fixture
    assert "minimumBandDwellSeconds == 180" in fixture
