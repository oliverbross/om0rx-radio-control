"""Native decoded-list status, manual-target, and hot-path contracts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/build/mshv-auto-dx/src/MSHV_2762/src"


def text(path: str) -> str:
    return (SOURCE / path).read_text(encoding="utf-8")


def test_decode_list_uses_authoritative_country_and_compact_statuses():
    cpp = text("HvDecodeList/decodelist.cpp")
    assert '<<tr("Country")<<"CS"<<"DS"<<"MW"' in cpp
    assert "m_dxccTracker->lookupDxcc(cacheKey, entity)" in cpp
    for compact in (
        'cs = "NC"', 'cs = "NB+NM/" + callSuffix', 'cs = "NB/" + callSuffix',
        'cs = "NM/" + callSuffix', 'ds = "ATNO"', 'ds = "NB+NM/" + QString',
        'ds = "NB/" + QString', 'ds = "NM/" + QString',
    ):
        assert compact in cpp
    assert "m_countryCache.contains(cacheKey)" in cpp
    assert "m_statusCache.contains(key)" in cpp
    assert "m_countryCache.size() >= 4096" in cpp
    assert "m_statusCache.size() >= 4096" in cpp
    assert "isCallConfirmedBandMode(call, band, mode)" in cpp
    assert "isDxccConfirmedBandMode(entity, band, mode)" in cpp
    assert "isCallWorkedOnMode(call, mode)" in cpp
    assert "isDxccWorkedOnMode(entity, mode)" in cpp
    assert 'status.endsWith("/C")' in cpp
    assert 'status.endsWith("/W")' in cpp
    assert "AutoDxMessageParser::parse(c).transmitter" in cpp
    assert 's_list_ident == 2 && list.at(1).startsWith("TX")' in cpp
    assert "call = parsed.destination.trimmed().toUpper();" in cpp
    country_body = cpp.split("QString DecodeList::FindCountry", 1)[1].split(
        "QStringList DecodeList::CompactStatuses", 1
    )[0]
    assert 'if (sid.startsWith("TX") && call.trimmed().isEmpty()) return res;' in country_body
    assert 'if (sid.startsWith("TX") || sid=="QSY") return res;' not in country_body


def test_operational_decode_columns_are_resizable_colored_and_persisted():
    cpp = text("HvDecodeList/decodelist.cpp")
    header = text("HvDecodeList/decodelist.h")
    assert "QHeaderView::Interactive" in cpp
    assert "ScrollBarAsNeeded" in cpp
    for hidden in ("FT_MW_COLUMN", "FT_DISTANCE_COLUMN", "FT_TYPE_COLUMN", "FT_QUALITY_COLUMN"):
        assert f"THvHeader->hideSection({hidden})" in cpp
    assert "StatusColor(txtin, false)" in cpp
    assert "StatusColor(txtin, true)" in cpp
    assert "DecodeHeader%1" in cpp
    assert "SaveFtHeaderState" in header


def test_ft_audio_frequency_is_positioned_not_guessed_from_numeric_columns():
    core = text("HvAutoDxer/autodxercore.cpp")
    decode = text("HvDecodeList/decodelist.cpp")
    tx = text("HvTxW/hvtxw.cpp")
    assert "data.value(data.size() >= 13 ? 12 : 7)" in core
    assert "for (int i = 5; i < data.size(); i++)" not in core
    assert "FT_FREQUENCY_COLUMN = 12" in decode
    assert "freq_offset = list_in.at(12).toInt()" in tx


def test_double_click_manual_target_is_absolute_operator_priority():
    decode = text("HvDecodeList/decodelist.cpp")
    core = text("HvAutoDxer/autodxercore.cpp")
    main = text("main_ms.cpp")
    assert "emit RequestAutoDxTarget(rawDecode)" in decode
    assert "QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows" in decode
    assert "ItemSelectedText(displayedMessage, FT_MESSAGE_COLUMN, index.row())" in decode
    assert "setSelectionMode(QAbstractItemView::SingleSelection)" in decode
    assert "QColor(180,215,250)" in decode
    assert "m_state == WaitingForQSO ? \"Queued after engaged QSO\"" in core
    assert '"Queued by operator override"' in core
    assert 'abandonCurrentTarget("operator manual override")' in core
    assert "if (best.priority > 0) break;" in core
    assert "!operatorSelected && m_targetRetryAfter.value(retryKey)" in core
    assert 'target.priorityReason = "Operator double-click override"' in core
    assert 'target.eligibilityClass = "manual-operator"' in core
    assert "m_fullHuntingEnabled && m_manualTarget.callsign.isEmpty()" in core
    assert "|| !m_manualTarget.callsign.isEmpty()" in core
    assert "best = m_manualTarget;" in core
    assert "!selectedByManualRequest\n                && !historicalActionAllowed" in core
    assert "!operatorSelected\n            && !historicalActionAllowed" in core
    assert 'const bool operatorSelected = target.eligibilityClass == "manual-operator"' in core
    assert "m_decodeCache->addDecode(callsign, grid, decode.dxccEntity" in core
    assert main.count("RequestAutoDxTarget(QStringList)") == 2
    assert "connect(TDecodeList1, SIGNAL(RequestAutoDxTarget(QStringList))" in main
    assert "connect(TDecodeList2, SIGNAL(RequestAutoDxTarget(QStringList))" in main
    assert 'queued && reason.startsWith("Queued ")' in main
    assert 'reason == "Active target"' in main
    assert 'reason == "Auto DX disabled; manual target cancelled"' in main
    assert "m_autoDxerQueuedCall.clear()" in main
    assert "SetAutoDxQueuedTarget(m_autoDxerQueuedCall)" in main
    assert 'status->setText("Q")' in decode


def test_directed_callers_resume_at_the_received_stage_and_operator_stage_wins():
    core = text("HvAutoDxer/autodxercore.cpp")
    mam = text("HvTxW/hvmultianswermodw.cpp")
    mam_header = text("HvTxW/hvmultianswermodw.h")
    tx = text("HvTxW/hvtxw.cpp")

    assert "static int initialQueueStage" in core
    assert 'QRegExp plainReport("^[+-][0-9]{2}$")' in core
    assert 'QRegExp acknowledgedReport("^R[+-][0-9]{2}$")' in core
    assert "QString::number(initialStage)" in core
    assert "m_targetRespondedToUs = target.isCallingMe;" in core
    assert "m_lastTargetProgressUtc = target.isCallingMe ? attemptUtc : QDateTime();" in core
    assert "bool setOperatorTxStage(const QString &callsign, int stage);" in mam_header
    assert "bool MultiAnswerModW::setOperatorTxStage" in mam
    assert "LsNow->SetItem(row, 7, QString::number(stage));" in mam
    assert tx.count("MultiAnswerMod->setOperatorTxStage(le_his_call->getText(), identif);") == 2


def test_operator_stop_clear_call_is_a_hard_manual_interlock():
    core = text("HvAutoDxer/autodxercore.cpp")
    header = text("HvAutoDxer/autodxercore.h")
    main = text("main_ms.cpp")
    main_header = text("main_ms.h")

    assert "void cancelCurrentCallByOperator();" in header
    assert "bool m_operatorTargetHold;" in header
    assert "if (m_operatorTargetHold) return;" in core
    cancel = core.split("void AutoDxerCore::cancelCurrentCallByOperator", 1)[1].split(
        "void AutoDxerCore::onLocalDecode", 1
    )[0]
    for required in (
        'emit requestAuthorizationInvalidation("operator-stop-clear-call")',
        "emit requestDisableAuto();",
        "m_operatorTargetHold = true;",
        "clearPendingCrossBandVerification();",
        "m_waitingForSlotAnalysis = false;",
        "m_waitingForStandardDialReturn = false;",
        "m_queueWidget->clearBothLists();",
        "m_currentTarget.clear();",
        "emit targetChanged(m_currentTarget);",
    ):
        assert required in cancel
    assert "requestDialFreqChange" not in cancel
    assert "m_operatorTargetHold = false;\n    m_manualTarget = target;" in core
    assert 'tr("STOP / CLEAR CALL")' in main
    assert 'QKeySequence("Ctrl+Esc")' in main
    assert "void StopAndClearAutoDxCall();" in main_header
    handler = main.split("void Main_Ms::StopAndClearAutoDxCall", 1)[1].split(
        "void Main_Ms::StopTxGlobalWithReason", 1
    )[0]
    assert 'StopTxGlobalWithReason("operator-stop-clear-call")' in handler
    assert "cancelCurrentCallByOperator()" in handler
    assert "THvTxW->ResetQSO();" in handler


def test_unanswered_attempt_waits_60_seconds_after_actual_last_tx_before_qsy():
    core = text("HvAutoDxer/autodxercore.cpp")
    header = text("HvAutoDxer/autodxercore.h")
    main = text("main_ms.cpp")

    assert "static const int LATE_REPLY_GUARD_MS = 60000;" in header
    assert "void onLocalTransmission(const QString &message);" in header
    assert "m_autoDxerCore->onLocalTransmission(str);" in main
    assert "if (!m_targetRespondedToUs && startLateReplyGuard(reason)) return;" in core
    assert "m_lastLocalTransmissionUtc.msecsTo(QDateTime::currentDateTimeUtc())" in core
    assert "emit requestDisableAuto();" in core
    assert 'auditEvent("late-reply-guard-started", fields);' in core
    assert 'auditEvent("late-reply-received", lateFields);' in core
    assert 'fields["reason"] = "late-reply-receive-guard";' in core
    assert "postQsoGuardActive() || lateReplyGuardActive()" in core
    assert 'fullHunting["late_reply_guard"] = lateReplyGuard;' in core
    assert "clearLateReplyGuard();" in core.split(
        "void AutoDxerCore::cancelCurrentCallByOperator", 1
    )[1].split("void AutoDxerCore::onLocalDecode", 1)[0]


def test_normal_autodx_does_not_wait_for_an_all_band_patrol_before_calling():
    core = text("HvAutoDxer/autodxercore.cpp")
    fallback = core.split(
        "bool AutoDxerCore::ordinaryNewCallFallbackAllowed", 1
    )[1].split("void AutoDxerCore::resetPriorityPatrolCycle", 1)[0]
    assert "if (hasEligiblePriorityOpportunity()) return false;" in fallback
    assert "return !m_fullHuntingEnabled || priorityPatrolComplete();" in fallback
    set_enabled = core.split("void AutoDxerCore::setEnabled", 1)[1].split(
        "bool AutoDxerCore::isConfiguredMode", 1
    )[0]
    assert "m_operatorTargetHold = false;" in set_enabled


def test_qso_lifecycle_controls_are_visible_and_actionable():
    tx = text("HvTxW/hvtxw.cpp")
    header = text("HvTxW/hvtxw.h")
    assert 'tr("GENERATED QSO MESSAGES")' in tx
    assert 'tr("STAGE")' in tx
    assert 'tr("MESSAGE")' in tx
    assert 'tr("NEXT")' in tx
    assert 'tr("NOW")' in tx
    assert 'tr("CALL/GRID")' in tx
    assert 'tr("REPORT")' in tx
    assert 'tr("R+REPORT")' in tx
    assert 'tr("RR73/RRR")' in tx
    assert 'void SetStageName(const QString &name);' in header
    assert 'tr("Select this QSO message stage")' in tx
    assert 'tr("Transmit or repeat this QSO message now")' in tx
    assert "H_tx->addWidget(Box_qso_lifecycle,2)" in tx
    assert "H_tx->addWidget(MultiAnswerMod,1)" in tx
    assert "V_qso_lifecycle->addLayout(V_l)" in tx
    assert "Box_qso_lifecycle->setMinimumHeight(205)" in tx
    assert "SetTxTextsHiden(false);\n        MultiAnswerMod->setHidden(false);" in tx
    assert "Box_dt->setMaximumWidth(480)" in tx
    assert "Box_in_tx->setMaximumWidth(QWIDGETSIZE_MAX)" in tx
    assert "Box_in_tx->setMinimumWidth(680)" in tx
    assert 'TempHvTxIn->b_tx->setText("Tx"+QString("%1").arg(i+1))' in tx


def test_autodx_target_refreshes_and_clears_generated_qso_messages_before_tx():
    tx = text("HvTxW/hvtxw.cpp")
    main = text("main_ms.cpp")
    core = text("HvAutoDxer/autodxercore.cpp")
    header = text("HvAutoDxer/autodxercore.h")

    sync = tx.split("void HvTxW::SyncAutoDxerStatusTarget", 1)[1].split(
        "void HvTxW::RfreshDxParm", 1
    )[0]
    assert "le_rst_tx->SetText(receivedReport, false)" in sync
    assert "gen_msg();" in sync
    assert "i < count_tx_widget && i < 5" in sync
    assert "txRow->line_txt->setText(QString())" in sync
    assert "QString::number(target.snr)" in main
    assert "int snr;" in header

    feed = core.split("void AutoDxerCore::feedToQueue", 1)[1].split(
        "void AutoDxerCore::checkQueueStatus", 1
    )[0]
    assert "m_currentTarget.snr = target.snr" in feed
    assert feed.index("emit targetChanged(m_currentTarget);") < feed.index(
        "emit requestEnableAuto();"
    )


def test_multi_answer_progress_synchronizes_visible_qso_stage_without_retransmit():
    tx = text("HvTxW/hvtxw.cpp")
    progress = tx.split("void HvTxW::SetQSOProgressAll", 1)[1].split(
        "void HvTxW::RbPress", 1
    )[0]
    assert "from_mam && f_multi_answer_mod" in progress
    assert "idd_out>=0 && idd_out<count_tx_widget" in progress
    assert "TempHvTxIn->rb_tx->setChecked(i==idd_out)" in progress
    assert "\n    RbPress(" not in progress
    assert "\n    SetTxRaportToRB(" not in progress
    assert "\n    SetEmitMessage(" not in progress


def test_decode_ui_hot_paths_avoid_repaint_and_full_sort_storms():
    decode = text("HvDecodeList/decodelist.cpp")
    scorer = text("HvAutoDxer/targetscorer.cpp")
    clear_body = decode.split("void DecodeList::Clear_List()", 1)[1].split(
        "void DecodeList::SetAutoDxQueuedTarget", 1
    )[0]
    assert "model.removeRows(0, model.rowCount())" in clear_body
    best_body = scorer.split("ScoredTarget TargetScorer::getBestTarget", 1)[1]
    assert "scoreAllTargets(decodes)" not in best_body
    assert "for (const CachedDecode &decode : decodes)" in best_body


def test_disabling_autodx_cancels_a_queued_manual_target():
    core = text("HvAutoDxer/autodxercore.cpp")
    disabled = core.split("if (effective) {", 1)[1].split(
        "bool AutoDxerCore::isConfiguredMode", 1
    )[0]
    assert '"Auto DX disabled; manual target cancelled"' in disabled
    assert "m_manualTarget = ScoredTarget();" in disabled


def test_atno_minimum_call_setting_and_manual_override_are_wired():
    core = text("HvAutoDxer/autodxercore.cpp")
    runtime = text("HvAutoDxer/autodxruntimeconfig.h")
    settings = text("HvAutoDxSettings/hvautodxsettings.cpp")
    assert '"Attempt/ATNOMinimumCallMinutes", 30' in runtime
    assert "attemptLimitSeconds(" in runtime
    assert 'new QLabel("ATNO minimum call:")' in settings
    assert 'm_atnoMinimumCallMinutes->setRange(1, 180)' in settings
    assert 'settings.setValue("Attempt/ATNOMinimumCallMinutes"' in settings
    assert '"Queued by operator override"' in core
    assert 'abandonCurrentTarget("operator manual override")' in core
    assert "const bool operatorSelected" in core


def test_confirmed_dxcc_uses_adaptive_scoped_retry_and_ignore_ui():
    core = text("HvAutoDxer/autodxercore.cpp")
    header = text("HvAutoDxer/autodxercore.h")
    panel = text("HvAutoDxer/autodxerpanel.cpp")
    decode = text("HvDecodeList/decodelist.cpp")
    main = text("main_ms.cpp")

    assert "static const int delays[] = { 180, 600, 1800, 3600 };" in core
    assert "targetScopeKey(callsign, bandIndex, mode)" in core
    assert "m_unansweredBurstCounts" in header
    assert "isStationIgnored" in core
    assert "autodx_ignore.json" in core
    assert 'm_tabWidget->addTab(ignoreTab, "Ignore")' in panel
    assert 'm_tabWidget->addTab(smsTab, "SMS")' not in panel
    assert 'Ignore for Auto DX on this band/mode' in decode
    assert "RequestAutoDxIgnore(QStringList)" in main
    assert "RequestAutoDxIgnoreCall(QString)" in main
    assert "message->data(CALLSIGN_ROLE)" in decode
    assert "requestImmediateStopAndReset" in core
    assert 'StopTxGlobalWithReason("operator-ignore-active-station")' in main


def test_right_click_call_next_uses_a_visible_fifo_operator_queue():
    core = text("HvAutoDxer/autodxercore.cpp")
    header = text("HvAutoDxer/autodxercore.h")
    panel = text("HvAutoDxer/autodxerpanel.cpp")
    decode = text("HvDecodeList/decodelist.cpp")
    main = text("main_ms.cpp")

    assert 'Add to Auto DX callers list (call next)' in decode
    assert "RequestAutoDxCallNext(QStringList)" in main
    assert "queueOperatorTarget(QStringList)" in main
    assert "QList<OperatorCallRequest> m_operatorCallQueue" in header
    assert 'm_tabWidget->addTab(callersTab, "Callers")' in panel
    assert "removeSelectedCaller" in panel
    assert "clearCallerList" in panel
    assert '"CALLERS: band change deferred until operator queue is empty"' in core
    assert "m_operatorCallQueue.removeFirst()" in core


def test_standard_ft8_ft4_calls_choose_a_recently_clear_protected_tx_slot():
    core = text("HvAutoDxer/autodxercore.cpp")
    finder = text("HvAutoBand/hvslotfinder.cpp")

    feed = core.split("void AutoDxerCore::feedToQueue", 1)[1].split(
        "void AutoDxerCore::checkQueueStatus", 1
    )[0]
    assert "replyRange.minFreq = 1400" in feed
    assert "replyRange.maxFreq = 1800" in feed
    assert "m_slotFinder->findBestSlot(replyRange)" in feed
    assert "emit requestTxFreqChange(txSlot.suggestedFreq)" in feed
    assert 'auditEvent("tx-slot-selected"' in feed
    assert "!splitTarget" in feed
    assert "newAttempt" in feed

    assert "normalized == \"FT4\" ? 100 : 60" in core
    assert "SLOT_OCCUPANCY_MAX_AGE_SECONDS = 45" in finder
    assert "isRecentlyOccupied" in finder
    assert "firstAlignedSlot" in finder
    assert "lastAlignedSlot" in finder
