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

    assert "OM0RXStartTargetQSO" in network_message
    assert "start_target_qso" in message_client_h
    assert "NetworkMessage::OM0RXStartTargetQSO" in message_client_cpp
    assert "remote_start_target_qso" in mainwindow_h
    assert "MessageClient::start_target_qso" in mainwindow_cpp
    assert "remote_configure (mode, frequency_tolerance" in mainwindow_cpp
    assert "ui->autoButton->click" in mainwindow_cpp


def test_wsjtz_enrichment_patch_accepts_om0rx_target_qso_command():
    text = WSJTZ_PATCH_PATH.read_text(encoding="utf-8")

    assert "OM0RXStartTargetQSO" in text
    assert "start_target_qso" in text
    assert "remote_start_target_qso" in text
    assert "NetworkMessage::OM0RXStartTargetQSO" in text
    assert "MessageClient::start_target_qso" in text
    assert "remote_configure (mode, frequency_tolerance" in text
    assert "ui->autoButton->click" in text


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
