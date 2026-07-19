import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLEAN_DOC_ROOT = PROJECT_ROOT / "docs" / "wsjtx" / "clean-rebuild"
PREPARE_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtz" / "prepare_clean_wsjtz.ps1"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtz" / "build_clean_wsjtz.ps1"
RUN_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtz" / "run_clean_wsjtz.ps1"
SERVICE = PROJECT_ROOT / "services" / "wsjtx.py"


def test_clean_baseline_identity_is_pinned() -> None:
    lock = json.loads((CLEAN_DOC_ROOT / "baseline-lock.json").read_text(encoding="utf-8"))
    upstream = lock["upstream"]

    assert upstream["ref"] == "v2.0.14"
    assert upstream["commit"] == "fa53f635462def9f37b54f63f18e407ecda2ba12"
    assert upstream["tree"] == "2d23c72ddb826f18d21876ac7b6a89642ee0ef34"
    assert upstream["reported_wsjtx_core_version"] == "3.0.0"

    build = json.loads((CLEAN_DOC_ROOT / "build-lock.json").read_text(encoding="utf-8"))
    assert build["source_commit"] == upstream["commit"]
    assert build["source_tree"] == upstream["tree"]
    assert build["build_result"] == "success"


def test_prepare_script_uses_separate_clean_workspace_without_feature_patch() -> None:
    script = PREPARE_SCRIPT.read_text(encoding="utf-8")

    assert '"data\\build"' in script
    assert '"wsjt-z-clean"' in script
    assert '"v2.0.14"' in script
    assert "checkout --detach" in script
    assert "om0rx-wsjtz-enrichment.patch" not in script
    assert "git apply" not in script
    assert "wsjt-z-om0rx" not in script


def test_basic_scope_defers_award_reference_exceptions() -> None:
    decisions = json.loads((CLEAN_DOC_ROOT / "feature-decisions.json").read_text(encoding="utf-8"))

    assert decisions["items"]["20"] == "KEEP_BASIC_NO_AWARD_REFERENCE_EXCEPTIONS"
    assert "deferred" in decisions["scope_note"].lower()


def test_clean_build_separates_build_compatibility_and_band_control_patches() -> None:
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "0001-build-allow-omnirig-off.patch" in script
    assert "0002-build-link-fftw-threads-on-windows.patch" in script
    assert "0100-band-qsy-transaction-tracing.patch" in script
    assert "0200-display-status-columns.patch" in script
    assert "0300-dxcc-priority-hunt.patch" in script
    assert "0400-backend-target-command.patch" in script
    assert "0500-visible-automation-startup.patch" in script
    assert "0600-direct-reply-lock.patch" in script
    assert "0700-log-race-and-decode-dedup.patch" in script
    assert "om0rx-wsjtz-enrichment.patch" not in script
    assert "OM0RX_BUILD_WITH_OMNIRIG=OFF" in script
    assert "data\\build\\wsjt-z-clean" in script


def test_band_qsy_patch_has_correlated_request_outcomes() -> None:
    patch = (CLEAN_DOC_ROOT / "patches" / "0100-band-qsy-transaction-tracing.patch").read_text(encoding="utf-8")

    assert "OM0RX_QSY result=request sequence=" in patch
    assert "OM0RX_QSY result=ack sequence=" in patch
    assert "OM0RX_QSY result=timeout sequence=" in patch
    assert "OM0RX_QSY result=superseded sequence=" in patch
    assert "OM0RX_QSY result=failed sequence=" in patch
    assert "operator-band-selector" in patch
    assert "native-band-hopper" in patch
    assert "wspr-band-hopper" in patch
    assert "decoded-spot" in patch

    lock = json.loads((CLEAN_DOC_ROOT / "milestone-1-lock.json").read_text(encoding="utf-8"))
    assert lock["dial_frequency_owner"]["default"] == "wsjtz"
    assert lock["live_flex_qualification"]["result"] == "pending_operator_test"
    assert lock["artifacts"]["executable_sha256"] == "5AE228AB4C1B466B0F462F10CA32107BBA8A4C67B668B13C8AE55D5DC5FF2B7B"


def test_clean_launcher_starts_local_classifier_without_rewriting_ini() -> None:
    script = RUN_SCRIPT.read_text(encoding="utf-8")

    assert "om0rx_decode_status_server.py" in script
    assert "/api/wsjtx/decode-status" not in script
    assert "127.0.0.1:8765/health" in script
    assert "Set-IniValue" not in script
    assert "Set-IniSectionValue" not in script
    assert "AcceptUDPRequests" not in script
    assert "AutoCall" not in script
    assert "wsjt-z-clean.exe" in script
    assert '[string]$RigName = "OM0RX-WSJT-Z"' in script
    assert '[string]$ConfigName = "OM0RX-WSJT-Z"' in script
    gui_launch = script.rsplit("Start-Process `", 1)[-1]
    assert "-WindowStyle Hidden" not in gui_launch


def test_station_ui_wsjtz_launcher_points_only_to_clean_rebuild() -> None:
    service = SERVICE.read_text(encoding="utf-8")

    assert 'WSJTZ_ENGINE_BUILD_ROOT = PROJECT_ROOT / "data" / "build" / "wsjt-z-clean" / "build-msys"' in service
    assert 'WSJTZ_ENGINE_RUN_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtz" / "run_clean_wsjtz.ps1"' in service
    assert 'exe = WSJTZ_ENGINE_BUILD_ROOT / "wsjt-z-clean.exe"' in service
    assert '_wsjt_engine_process_ids(exe_name, rig_name' in service


def test_status_columns_patch_uses_exact_row_identity_and_fixed_width_cells() -> None:
    patch = (CLEAN_DOC_ROOT / "patches" / "0200-display-status-columns.patch").read_text(encoding="utf-8")

    assert "DecodeStatusBlockData" in patch
    assert "decode_status_key" in patch
    assert "call, band, mode" in patch
    assert "leftJustified (45)" in patch
    assert 'QObject::tr ("CS     DS")' in patch
    assert "label.left (6).leftJustified (6)" in patch
    assert "http://127.0.0.1:8765/api/wsjtx/decode-status" in patch


def test_dxcc_priority_patch_is_current_band_fail_closed_and_watchdog_scoped() -> None:
    patch = (CLEAN_DOC_ROOT / "patches" / "0300-dxcc-priority-hunt.patch").read_text(encoding="utf-8")

    assert "cbWatchUnconfirmedDXCC" in patch
    assert "band != current_band" in patch
    assert 'dxcc_status == "Unknown"' in patch
    assert "!ui->cbAutoCall->isChecked ()" in patch
    assert "m_transmitting || m_tune || m_tx_watchdog" in patch
    assert "m_om0rxPriorityHuntWatchdogMinutes = 20" in patch
    assert 'clear_om0rx_priority_hunt ("band change")' in patch
    assert 'clear_om0rx_priority_hunt ("QSO logged")' in patch
    assert 'clear_om0rx_priority_hunt ("watchdog triggered")' in patch


def test_backend_target_patch_receives_commands_and_arms_priority_watchdog() -> None:
    patch = (CLEAN_DOC_ROOT / "patches" / "0400-backend-target-command.patch").read_text(encoding="utf-8")

    assert "OM0RXStartTargetQSO" in patch
    assert "Q_SIGNAL void start_target_qso" in patch
    assert "remote_start_target_qso" in patch
    assert 'bool_value ("priorityHunt", false)' in patch
    assert 'uint_value ("watchdogMinutes", 20u)' in patch
    assert "OM0RX backend priority hunt armed" in patch
    assert "active QSO=" in patch


def test_visible_automation_controls_are_startup_defaults_and_tx_authority() -> None:
    patch = (CLEAN_DOC_ROOT / "patches" / "0500-visible-automation-startup.patch").read_text(encoding="utf-8")

    assert "ui->cbCQonly->setChecked (true)" in patch
    assert "ui->cbAutoCall->setChecked (true)" in patch
    assert 'on_monitorButton_clicked (m_mode != "Echo")' in patch
    assert "QTimer::singleShot (1500" in patch
    assert "!m_monitoring" in patch
    assert "enable_tx && !ui->cbAutoCall->isChecked ()" in patch
    assert "visible Auto Call is off" in patch


def test_direct_reply_lock_prevents_same_batch_cq_replacement() -> None:
    patch = (CLEAN_DOC_ROOT / "patches" / "0600-direct-reply-lock.patch").read_text(encoding="utf-8")

    assert "addressed_to_me" in patch
    assert "progressed_with_other" in patch
    assert "Direct reply lock:" in patch
    assert "CQ candidate suppressed by direct reply lock:" in patch
    assert "om0rx_process_pending_direct_reply" in patch
    assert "m_om0rxPendingDirectReplyLine = dt.string()" in patch
    assert "processMessage(message)" in patch
    assert "m_om0rxDirectReplyCall.clear()" in patch


def test_logged_target_guard_and_semantic_decode_dedup_are_native() -> None:
    patch = (CLEAN_DOC_ROOT / "patches" / "0700-log-race-and-decode-dedup.patch").read_text(encoding="utf-8")

    assert "m_om0rxLastLoggedCall" in patch
    assert "m_om0rxLastLoggedBand" in patch
    assert "m_om0rxLastLoggedMode" in patch
    assert "QSO already logged" in patch
    assert "m_om0rxDecodeDedupSlot" in patch
    assert "m_om0rxSeenDecodeLines" in patch
    assert "decode_identity.remove(ap_suffix)" in patch
    assert "decode_fields.mid(5).join(' ')" in patch
    assert "m_om0rxSeenDecodeLines.contains(decode_identity)" in patch


def test_basic_antenna_policy_lock_defers_award_reference_exceptions() -> None:
    lock = json.loads((CLEAN_DOC_ROOT / "milestone-2-lock.json").read_text(encoding="utf-8"))

    assert lock["trigger"] == "radio-reported slice frequency"
    assert lock["default_mapping"] == {
        "160m": "ANT2",
        "80m": "ANT2",
        "60m": "ANT2",
        "40m": "ANT2",
        "30m": "ANT2",
        "20m": "ANT1",
        "17m": "ANT1",
        "15m": "ANT1",
        "12m": "ANT1",
        "10m": "ANT1",
    }
    assert lock["safety"]["unknown_tx_state"] == "defer"
    assert lock["award_reference_exceptions"] == "deferred"
