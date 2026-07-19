"""Checks for the OM0RX WSJT-X Improved engine patch artifact."""

import subprocess
import tarfile
from pathlib import Path

import _bootstrap  # noqa: F401

from services.wsjtx import PROJECT_ROOT as WSJTX_PROJECT_ROOT
from services.wsjtx import WSJTXService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PATCH_PATH = PROJECT_ROOT / "docs" / "wsjtx" / "om0rx-start-target-qso.patch"
WSJTZ_PATCH_PATH = PROJECT_ROOT / "docs" / "wsjtx" / "om0rx-wsjtz-enrichment.patch"
SOURCE_ARCHIVE = PROJECT_ROOT / "data" / "research" / "wsjtx-improved-3.1.0" / "src" / "wsjtx.tgz"
WSJTZ_SOURCE_ROOT = PROJECT_ROOT / "data" / "build" / "wsjt-z-om0rx" / "src"


def test_wsjtx_engine_patch_contains_target_qso_extension():
    text = PATCH_PATH.read_text(encoding="utf-8")

    assert "OM0RXStartTargetQSO" in text
    assert "start_target_qso" in text
    assert "remote_start_target_qso" in text
    assert "QJsonDocument" in text
    assert "ui->autoButton->click" in text
    assert "OM0RX_BUILD_WITH_OMNIRIG" in text
    assert "TransceiverFactory.cpp" in text


def test_current_wsjtz_source_accepts_om0rx_target_qso_command():
    if not WSJTZ_SOURCE_ROOT.exists():
        return

    network_message = (WSJTZ_SOURCE_ROOT / "Network" / "NetworkMessage.hpp").read_text(encoding="utf-8")
    message_client_h = (WSJTZ_SOURCE_ROOT / "Network" / "MessageClient.hpp").read_text(encoding="utf-8")
    message_client_cpp = (WSJTZ_SOURCE_ROOT / "Network" / "MessageClient.cpp").read_text(encoding="utf-8")
    mainwindow_h = (WSJTZ_SOURCE_ROOT / "widgets" / "mainwindow.h").read_text(encoding="utf-8")
    mainwindow_cpp = (WSJTZ_SOURCE_ROOT / "widgets" / "mainwindow.cpp").read_text(encoding="utf-8")
    mainwindow_ui = (WSJTZ_SOURCE_ROOT / "widgets" / "mainwindow.ui").read_text(encoding="utf-8")
    displaytext_cpp = (WSJTZ_SOURCE_ROOT / "widgets" / "displaytext.cpp").read_text(encoding="utf-8")

    assert "OM0RXStartTargetQSO" in network_message
    assert "start_target_qso" in message_client_h
    assert "NetworkMessage::OM0RXStartTargetQSO" in message_client_cpp
    assert "remote_start_target_qso" in mainwindow_h
    assert "MessageClient::start_target_qso" in mainwindow_cpp
    assert "remote_configure (mode, frequency_tolerance" in mainwindow_cpp
    assert "ui->autoButton->click" in mainwindow_cpp
    assert 'bool_value ("priorityHunt", false)' in mainwindow_cpp
    assert "OM0RX backend priority hunt armed" in mainwindow_cpp
    assert "om0rx_auto_reply_direct_call" in mainwindow_h
    assert "OM0RX direct reply auto-start" in mainwindow_cpp
    assert "can_interrupt_unanswered_call" in mainwindow_cpp
    assert "OM0RX direct reply interrupts unanswered Auto Call" in mainwindow_cpp
    assert "m_om0rxPendingDirectReplyLine" in mainwindow_h
    assert "m_om0rxPendingDirectReplyValid" in mainwindow_h
    assert "ZProcess: starting held direct reply" in mainwindow_cpp
    assert "processMessage (DecodedText {held_reply})" in mainwindow_cpp
    assert "om0rx_clear_stale_logged_qso" in mainwindow_h
    assert "OM0RX stale logged QSO cleared" in mainwindow_cpp
    assert "direct reply precheck" in mainwindow_cpp
    assert "ZProcess entry" in mainwindow_cpp
    assert "preserved_appendage" in displaytext_cpp
    assert "QChar::Nbsp} + preserved_appendage" in displaytext_cpp
    assert "grid.trimmed ().toUpper ().left (4)" in displaytext_cpp
    assert "constexpr int status_column = 45" in displaytext_cpp
    assert 'leftJustified (45)' in mainwindow_cpp
    assert "qso_state" in message_client_h
    assert "QSO state:" in message_client_cpp
    assert "om0rx_qso_state" in mainwindow_h
    assert "waiting_rrr" in mainwindow_cpp
    assert "waiting_73" in mainwindow_cpp
    assert 'setValue ("AutoCall", ui->cbAutoCall->isChecked ())' in mainwindow_cpp
    assert 'value ("AutoCall", false)' in mainwindow_cpp
    assert "cbWatchUnconfirmedDXCC" in mainwindow_ui
    assert "Watch for new/unconfirmed DXCC's" in mainwindow_ui
    assert 'setValue ("WatchUnconfirmedDXCC"' in mainwindow_cpp
    assert 'value("WatchUnconfirmedDXCC", true)' in mainwindow_cpp
    assert "om0rx_dxcc_watch_status" in mainwindow_cpp
    assert 'normalized == "worked"' in mainwindow_cpp
    assert "normalized.contains (\"new mode\")" in mainwindow_cpp
    assert "om0rx_plain_worked_call_status" in mainwindow_cpp
    assert "dxcc_watch_candidate" in mainwindow_cpp
    assert "Third-party 73 and DXCC priority never make traffic callable" in mainwindow_cpp
    assert "accepted without CQ/73" not in mainwindow_cpp
    assert "om0rx_decode_line_for_selection" in mainwindow_cpp
    assert "line.remove (status_columns)" in mainwindow_cpp
    assert 'om0rx_clear_priority_hunt ("operator double-click")' in mainwindow_cpp


def test_current_wsjtz_source_sanitizes_grid_and_clears_stuck_auto_log():
    if not WSJTZ_SOURCE_ROOT.exists():
        return

    mainwindow_cpp = (WSJTZ_SOURCE_ROOT / "widgets" / "mainwindow.cpp").read_text(encoding="utf-8")
    mainwindow_h = (WSJTZ_SOURCE_ROOT / "widgets" / "mainwindow.h").read_text(encoding="utf-8")

    assert "QString om0rx_sanitized_grid" in mainwindow_cpp
    assert "grid = grid.trimmed ().toUpper ()" in mainwindow_cpp
    assert "return grid.contains (grid_regexp) ? grid : QString {}" in mainwindow_cpp
    assert 'setValue("DXgrid",om0rx_sanitized_grid' in mainwindow_cpp
    assert 'setText (om0rx_sanitized_grid (m_settings->value ("DXgrid"' in mainwindow_cpp
    assert "m_hisGrid = om0rx_sanitized_grid (ui->dxGridEntry->text())" in mainwindow_cpp
    assert "QString grid=om0rx_sanitized_grid (m_hisGrid)" in mainwindow_cpp
    assert "auto const reply_grid = om0rx_sanitized_grid (hisgrid)" in mainwindow_cpp
    assert "Auto-log completion left DX active; clearing completed QSO state" in mainwindow_cpp
    assert "om0rx_stop_forbidden_autocall_cq" in mainwindow_h
    assert "OM0RX blocked Auto Call CQ" in mainwindow_cpp
    assert "ui->cbAutoCall->isChecked() || ui->cbAutoCQ->isChecked()" in mainwindow_cpp
    assert "ui->cbAutoCall->isChecked()" in mainwindow_cpp
    assert "!ui->cbAutoCQ->isChecked()" in mainwindow_cpp
    assert 'om0rx_stop_forbidden_autocall_cq("transmit gate")' in mainwindow_cpp
    assert 'om0rx_stop_forbidden_autocall_cq("ZProcess entry")' in mainwindow_cpp
    assert "om0rx_tx_starting" in mainwindow_cpp
    assert "m_restart && m_transmitting && !om0rx_tx_starting" in mainwindow_cpp
    assert "OM0RX stale TX state cleared after PTT release" in mainwindow_cpp
    assert "if (m_transmitting) stopTx();" in mainwindow_cpp
    assert "m_pendingTxIs73 = is_73" in mainwindow_cpp
    assert "record_tx_start ();" in mainwindow_cpp
    assert "void MainWindow::record_tx_start ()" in mainwindow_cpp
    assert "Do not treat a PTT request as a transmitted message" in mainwindow_cpp
    assert mainwindow_cpp.index("transmit (snr);") < mainwindow_cpp.index("record_tx_start ();")
    assert "m_final73TxGuard = true" in mainwindow_cpp
    assert "OM0RX final-73 TX completed; RX/PTT released" in mainwindow_cpp
    assert "OM0RX final-73 safety guard forced RX/PTT release" in mainwindow_cpp
    assert "if (m_final73TxGuard && !m_transmitting)" in mainwindow_cpp
    assert "m_config.transceiver_ptt (false);" in mainwindow_cpp
    assert "bool    m_final73TxGuard = false;" in mainwindow_h
    assert "bool    m_final73LogPending = false;" in mainwindow_h
    assert "void complete_final73_tx ();" in mainwindow_h

    record_tx_body = mainwindow_cpp.split(
        "void MainWindow::record_tx_start ()", 1
    )[1].split("void MainWindow::complete_final73_tx ()", 1)[0]
    assert "m_final73LogPending =" in record_tx_body
    assert "logQSOTimer.start (0)" not in record_tx_body
    assert "cease_auto_Tx_after_QSO" not in record_tx_body

    complete_tx_body = mainwindow_cpp.split(
        "void MainWindow::complete_final73_tx ()", 1
    )[1].split("void MainWindow::stopTx()", 1)[0]
    assert "auto_tx_mode (false)" in complete_tx_body
    assert "logQSOTimer.start (0)" in complete_tx_body
    assert "cease_auto_Tx_after_QSO" in complete_tx_body
    assert mainwindow_cpp.index("m_config.transceiver_ptt (false); //Lower PTT") < mainwindow_cpp.index(
        "complete_final73_tx ();", mainwindow_cpp.index("void MainWindow::stopTx2()")
    )


def test_current_wsjtz_source_has_lean_startup_and_tci_fixes():
    if not WSJTZ_SOURCE_ROOT.exists():
        return

    cmake = (WSJTZ_SOURCE_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    configuration_cpp = (WSJTZ_SOURCE_ROOT / "Configuration.cpp").read_text(encoding="utf-8")
    configuration_hpp = (WSJTZ_SOURCE_ROOT / "Configuration.hpp").read_text(encoding="utf-8")
    modulator_cpp = (WSJTZ_SOURCE_ROOT / "Modulator" / "Modulator.cpp").read_text(encoding="utf-8")
    soundin_cpp = (WSJTZ_SOURCE_ROOT / "Audio" / "soundin.cpp").read_text(encoding="utf-8")
    worked_before = (WSJTZ_SOURCE_ROOT / "logbook" / "WorkedBefore.cpp").read_text(encoding="utf-8")
    mainwindow_cpp = (WSJTZ_SOURCE_ROOT / "widgets" / "mainwindow.cpp").read_text(encoding="utf-8")

    assert "configure_file (${CMAKE_SOURCE_DIR}/USState.db ${CMAKE_BINARY_DIR}/USState.db COPYONLY)" in cmake
    assert 'QSqlDatabase::database(kConnName, false)' in mainwindow_cpp
    assert 'QCoreApplication::applicationDirPath ()' in mainwindow_cpp
    assert "m_->load_worked_before ();" in worked_before
    assert "Q_SLOT void transceiver_period (double = 15.0, bool force = false);" in configuration_hpp
    assert "if (force || cached_rig_state_.period() != period)" in configuration_cpp
    assert "m_config.transceiver_period(m_TRperiod, true)" in mainwindow_cpp
    assert "bool Modulator::reset ()" in modulator_cpp
    assert "5 * 1000000ll" in soundin_cpp


def test_current_wsjtz_source_blocks_exact_worked_band_mode_hunts():
    if not WSJTZ_SOURCE_ROOT.exists():
        return

    mainwindow_cpp = (WSJTZ_SOURCE_ROOT / "widgets" / "mainwindow.cpp").read_text(encoding="utf-8")

    assert "om0rx_status_cache_call_done_on_band_mode" in mainwindow_cpp
    assert "om0rx_status_cache_dxcc_hunt_needed" in mainwindow_cpp
    assert "cacheCallDoneOnBandMode" in mainwindow_cpp
    assert "exact call/band/mode already worked, not selecting" in mainwindow_cpp
    assert "watchdog target no longer needed" in mainwindow_cpp
    assert "watchdog inactive target" in mainwindow_cpp
    assert "needed_on_band.insert" in mainwindow_cpp
    assert 'QString {"%1|%2|%3|%4|%5|%6|%7|%8|%9|%10|%11|%12"}' in mainwindow_cpp


def test_wsjtz_enrichment_patch_accepts_om0rx_target_qso_command():
    text = WSJTZ_PATCH_PATH.read_text(encoding="utf-8")

    assert "OM0RXStartTargetQSO" in text
    assert "start_target_qso" in text
    assert "remote_start_target_qso" in text
    assert "NetworkMessage::OM0RXStartTargetQSO" in text
    assert "MessageClient::start_target_qso" in text
    assert "remote_configure (mode, frequency_tolerance" in text
    assert "ui->autoButton->click" in text
    assert 'bool_value ("priorityHunt", false)' in text
    assert "OM0RX backend priority hunt armed" in text
    assert "om0rx_auto_reply_direct_call" in text
    assert "OM0RX direct reply auto-start" in text
    assert "can_interrupt_unanswered_call" in text
    assert "OM0RX direct reply interrupts unanswered Auto Call" in text
    assert "m_om0rxPendingDirectReplyLine" in text
    assert "m_om0rxPendingDirectReplyValid" in text
    assert "ZProcess: starting held direct reply" in text
    assert "processMessage (DecodedText {held_reply})" in text
    assert "qso_state" in text
    assert "QSO state:" in text
    assert "om0rx_qso_state" in text
    assert "waiting_rrr" in text
    assert "waiting_73" in text
    assert 'setValue ("AutoCall", ui->cbAutoCall->isChecked ())' in text
    assert 'value ("AutoCall", false)' in text
    assert "cbWatchUnconfirmedDXCC" in text
    assert "Watch for new/unconfirmed DXCC's" in text
    assert 'setValue ("WatchUnconfirmedDXCC"' in text
    assert 'value("WatchUnconfirmedDXCC", true)' in text
    assert "om0rx_dxcc_watch_status" in text
    assert 'normalized == "worked"' in text
    assert "normalized.contains (\"new mode\")" in text
    assert "om0rx_plain_worked_call_status" in text
    assert "dxcc_watch_candidate" in text
    assert "Third-party 73 and DXCC priority never make traffic callable" in text
    assert "accepted without CQ/73" not in text
    assert "om0rx_decode_line_for_selection" in text
    assert "line.remove (status_columns)" in text
    assert 'om0rx_clear_priority_hunt ("operator double-click")' in text
    assert "preserved_appendage" in text
    assert "QChar::Nbsp} + preserved_appendage" in text
    assert "grid.trimmed ().toUpper ().left (4)" in text
    assert "constexpr int status_column = 45" in text
    assert 'leftJustified (45)' in text
    assert "om0rx_tx_starting" in text
    assert "record_tx_start" in text
    assert "m_final73TxGuard" in text
    assert "OM0RX final-73 TX completed; RX/PTT released" in text
    assert "OM0RX final-73 safety guard forced RX/PTT release" in text
    assert "m_config.transceiver_ptt (false)" in text
    assert "m_restart && m_transmitting && !om0rx_tx_starting" in text
    assert "m_pendingTxIs73 = is_73" in text
    assert "m_pendingTxFirst73 = is_73" in text


def test_wsjtx_engine_patch_contains_om0rx_hunting_controls():
    text = PATCH_PATH.read_text(encoding="utf-8")

    assert "tabOm0rxAutomation" in text
    assert "cbOm0rxBandHopping" in text
    assert "cbOm0rxModeSwitching" in text
    assert "cbOm0rxTreat73AsCQ" in text
    assert "cbOm0rxQsoPopup" in text
    assert "teOm0rxBandPlan" in text
    assert "teOm0rxIgnoreList" in text
    assert "annotate_callsign" in text
    assert "labOm0rxCallStatus" in text
    assert "labOm0rxDxccStatus" in text
    assert "labOm0rxEntityStatus" in text
    assert "set_om0rx_active_status_pending" in text
    assert "CALL Checking" in text
    assert "DXCC Checking" in text
    assert "entity checking" in text
    assert "previous_call != dx_call" in text
    assert "backend_has_active_target" in text
    assert "ui->dxCallEntry->clear" in text
    assert "ui->dxGridEntry->clear" in text
    assert "startup cleared stale target" in text
    assert "/api/ft8/tx/clear-qso" in text
    assert "Call Status" in text
    assert "DXCC Status" in text
    assert "om0rx_status_format" in text
    assert "om0rx_status_label" in text
    assert "normalize_om0rx_decode_colours" in text
    assert "Checking | Checking" in text
    assert "status_column = 40" in text
    assert "leftJustified (40)" in text
    assert "left (12).leftJustified (12)" in text
    assert "QTimer::singleShot (0, this, [this, call, cached]" in text
    assert "NewB+Mode" in text
    assert "New Band" in text
    assert "New Mode" in text
    assert 'cache_key = QString {"%1|%2|%3"}.arg (call, band, mode)' in text
    assert 'annotate_callsign (display_call, QString {"%1 | %2"}.arg (call_status, dxcc_status)' in text
    assert "cbOm0rxNeedCall" in text
    assert "cbOm0rxNeedDxcc" in text
    assert "cbOm0rxNeedBand" in text
    assert "cbOm0rxNeedMode" in text
    assert "cbOm0rxNeedGrid" in text
    assert "gbOm0rxFiltering" in text
    assert "cbOm0rxFilterNewCall" in text
    assert "cbOm0rxFilterNewDxcc" in text
    assert "cbOm0rxFilterBandCall" in text
    assert "cbOm0rxFilterBandGrid" in text
    assert "cbOm0rxContinentNorthAmerica" in text
    assert "cbOm0rxContinentSouthAmerica" in text
    assert "cbOm0rxLotwOnly" in text
    assert "sbOm0rxHopInterval" in text
    assert "om0rx_watchdog_minutes" in text
    assert "om0rx_current_band_plan" in text
    assert "om0rx_band_hopping_tick" in text
    assert "om0rx_qsy_to_band_mode" in text
    assert "struct Om0rxHuntSlot" in text
    assert "om0rx_hunting_sequence" in text
    assert 'sequence.append ({band, "FT8"})' in text
    assert 'sequence.append ({band, "FT4"})' in text
    assert "current_slot_index" in text
    assert "target_slot = sequence.value" in text
    assert "om0rx_hunting_frequency_hz" in text
    assert "OM0RX hunt hop: %1 %2" in text
    assert "24919000" in text
    assert "28180000" in text
    assert "background: #111820" in text
    assert 'payload.insert ("grid"' in text
    assert 'payload.insert ("message"' in text
    assert 'payload.insert ("snr"' in text
    assert 'automation.insert ("bandPlan"' in text
    assert 'automation.insert ("ignoreList"' in text
    assert 'automation.insert ("currentBand", m_currentBand)' in text
    assert 'automation.insert ("autoLogToWavelog"' in text
    assert 'automation.insert ("hopIntervalSeconds"' in text
    assert 'automation.insert ("currentMode", m_mode)' in text
    assert 'automation.insert ("needCall"' in text
    assert 'automation.insert ("needDxcc"' in text
    assert 'automation.insert ("filterMatrixEnabled", true)' in text
    assert 'automation.insert ("filterNew", filter_new)' in text
    assert 'automation.insert ("filterNewOnBand", filter_band)' in text
    assert 'automation.insert ("filterContinents", filter_continents)' in text
    assert 'automation.insert ("lotwOnly"' in text
    assert "ui->cbOm0rxAutoLog->isChecked ())" in text
    assert "ui->cbOm0rxAutoLog->isChecked () && m_logDlg->isVisible ()" not in text
    assert "decodedCallsignClicked" in text
    assert "request_om0rx_qso_history_popup" in text
    assert "show_om0rx_qso_history_popup" in text
    assert "/api/wavelog-log/search/%1" in text
    assert "Previous QSOs - %1" in text
    assert "single_click_timer_.stop" in text
    assert "call.remove ('<')" in text
    assert "display_call.remove ('<')" in text
    assert "Band hopping is off" in text
    assert "Mode switching is off" in text
    assert 'auto listen_only = bool_value ("listenOnly", false);' in text
    assert "OM0RX listening for %1 before calling" in text
    assert "active QSO with %2 is still in progress" in text
    assert "m_om0rx_backend_has_active_target" in text
    assert "m_om0rx_no_eligible_since" in text
    assert "backend_eligible_count == 0" in text
    assert "clear_om0rx_target_state ();" in text
    assert "no_eligible_seconds" in text
    assert "no eligible target" in text
    assert "om0rx_final_73_for_us" in text
    assert "logQSOTimer.start (0)" in text
    assert "OM0RX automation stopped" in text
    assert "Auto CQ and Auto Call are off; TX was halted" in text
    assert 'SLOT (accept ())' in text


def test_wsjtx_engine_patch_treats_73_as_cq_in_native_cq_only_filter():
    text = PATCH_PATH.read_text(encoding="utf-8")

    assert "bool include73AsCQ" in text
    assert "include73AsCQ && is_73" in text
    assert "ui->cbOm0rxTreat73AsCQ->isChecked ())" in text
    assert "if (checked) ui->cbHoldTxFreq->setChecked (true);" in text


def test_wsjtx_engine_patch_clears_finished_target_and_mirrors_tx_rows():
    text = PATCH_PATH.read_text(encoding="utf-8")

    assert "void MainWindow::clear_om0rx_target_state ()" in text
    assert "genStdMsgs (QString {}, true);" in text
    assert "clear_om0rx_target_state ();" in text
    assert "void MainWindow::display_om0rx_transmitted_text" in text
    assert "ui->decodedTextBrowser2->displayTransmittedText" in text
    assert "ui->decodedTextBrowser->displayTransmittedText" in text
    assert "display_om0rx_transmitted_text (current_message);" in text


def test_wsjtx_engine_patch_contains_runtime_reason_panel_contract():
    text = PATCH_PATH.read_text(encoding="utf-8")

    assert "m_om0rx_automation_timer.setInterval (750)" in text
    assert "QJsonArray" in text
    assert 'automation.value ("reason_panel").toObject ()' in text
    assert "Why selected: %1" in text
    assert "Why not TX: %1" in text
    assert "Rejected: %1" in text
    assert "setToolTip (tooltip_text)" in text


def test_wsjtx_engine_patch_refreshes_backend_even_when_status_label_is_cached():
    text = PATCH_PATH.read_text(encoding="utf-8")
    cached_block_start = text.index("+  if (m_om0rx_status_cache.contains (cache_key))")
    inflight_block_start = text.index("+  if (m_om0rx_status_inflight.contains (cache_key))")
    cached_block = text[cached_block_start:inflight_block_start]

    assert "apply_om0rx_decode_status (call, cached)" in cached_block
    assert "+      return;" not in cached_block


def test_wsjtx_engine_patch_does_not_repaint_active_cached_status_as_checking():
    text = PATCH_PATH.read_text(encoding="utf-8")
    cache_pos = text.index("+  if (m_om0rx_status_cache.contains (cache_key))")
    inflight_pos = text.index("+  if (m_om0rx_status_inflight.contains (cache_key))")
    pending_pos = text.index("+      set_om0rx_active_status_pending (call);", inflight_pos)

    assert cache_pos < inflight_pos < pending_pos


def test_wsjtx_engine_patch_applies_to_downloaded_source(tmp_path):
    if not SOURCE_ARCHIVE.exists():
        return

    source_root = tmp_path / "wsjtx-src"
    source_root.mkdir()
    with tarfile.open(SOURCE_ARCHIVE, "r:gz") as archive:
      members = archive.getmembers()
      root_prefix = members[0].name.split("/")[0] + "/"
      for member in members:
          if not member.name.startswith(root_prefix):
              continue
          member.name = member.name[len(root_prefix):]
          if member.name:
              archive.extract(member, source_root)

    subprocess.run(
        ["git", "-C", str(source_root), "apply", "--unidiff-zero", "--check", str(PATCH_PATH)],
        check=True,
        text=True,
        capture_output=True,
    )


def test_wsjtx_engine_build_scripts_are_present():
    script_root = PROJECT_ROOT / "scripts" / "wsjtx"

    prepare = (script_root / "prepare_om0rx_wsjtx.ps1").read_text(encoding="utf-8")
    build = (script_root / "build_om0rx_wsjtx.ps1").read_text(encoding="utf-8")
    run = (script_root / "run_om0rx_wsjtx.ps1").read_text(encoding="utf-8")

    assert "om0rx-start-target-qso.patch" in prepare
    assert "OM0RX_BUILD_WITH_OMNIRIG=OFF" in build
    assert "--target wsjtx jt9" in build
    assert "jt9.exe" in build
    assert "--rig-name" in run
    assert "--config" in run
    assert "jt9.exe" in run
    assert "$appName.lock" in run
    assert "already running" in run
    assert "RedirectStandardOutput" in run

    wsjtz_run = (PROJECT_ROOT / "scripts" / "wsjtz" / "run_om0rx_wsjtz.ps1").read_text(encoding="utf-8")
    assert "function Set-IniSectionValue" in wsjtz_run
    assert '-Section "Configuration" -Key "AcceptUDPRequests" -Value "true"' in wsjtz_run
    assert '-Section "Configuration" -Key "AutoLog" -Value "true"' in wsjtz_run
    assert '-Section "MainWindow" -Key "AutoCall" -Value "true"' in wsjtz_run
    assert '-Section "MainWindow" -Key "AutoSeq" -Value "true"' in wsjtz_run
    assert '-Section "MainWindow" -Key "AutoCQ" -Value "false"' in wsjtz_run
    assert '-Section "MainWindow" -Key "autoModeSwitchEnabled" -Value "false"' in wsjtz_run
    assert '-Section "MainWindow" -Key "WatchUnconfirmedDXCC" -Value "true"' in wsjtz_run
    assert '-Section "Common" -Key "AutoCall" -Value "true"' in wsjtz_run
    assert '-Section "Common" -Key "AutoSeq" -Value "true"' in wsjtz_run
    assert '-Section "Common" -Key "autoModeSwitchEnabled" -Value "false"' in wsjtz_run
    assert '-Section "Common" -Key "WatchUnconfirmedDXCC" -Value "true"' in wsjtz_run


def test_websocket_initial_status_uses_typed_shared_snapshot_without_fake_defaults():
    websocket_py = (PROJECT_ROOT / "services" / "websocket.py").read_text(encoding="utf-8")

    assert 'getattr(runtime_context, "radio_snapshot"' in websocket_py
    assert "initial_status = dict(" in websocket_py
    assert "14.074" not in websocket_py


def test_wsjtx_launch_logs_tail_stdout_and_missing_stderr():
    service = WSJTXService()
    rig_name = "PYTEST-LOG"
    log_root = WSJTX_PROJECT_ROOT / "logs"
    stdout_log = log_root / "wsjt-x-pytest-log.out.log"
    stderr_log = log_root / "wsjt-x-pytest-log.err.log"
    log_root.mkdir(parents=True, exist_ok=True)

    try:
        stdout_log.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
        if stderr_log.exists():
            stderr_log.unlink()

        result = service.get_launch_logs(rig_name=rig_name, lines=2)

        assert result["success"] is True
        assert result["rig_name"] == rig_name
        assert result["lines"] == 2
        assert result["logs"]["stdout"]["exists"] is True
        assert result["logs"]["stdout"]["lines"] == ["line 2", "line 3"]
        assert result["logs"]["stderr"]["exists"] is False
        assert result["logs"]["stderr"]["lines"] == []
    finally:
        if stdout_log.exists():
            stdout_log.unlink()
        if stderr_log.exists():
            stderr_log.unlink()
