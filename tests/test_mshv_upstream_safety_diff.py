"""Differential contracts: OM0RX safety remains additive to pinned MSHV UX."""
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(
    os.environ.get("OM0RX_MSHV_TEST_SOURCE_ROOT", ROOT / "data/build/mshv-auto-dx/src")
).resolve()


def _text(relative: str) -> str:
    return (SOURCE / relative).read_text(encoding="utf-8", errors="replace")


def _upstream(relative: str) -> str:
    return subprocess.run(
        ["git", "-C", str(SOURCE), "show", f"HEAD:{relative}"],
        capture_output=True, text=True, check=True, encoding="utf-8", errors="replace",
    ).stdout


def _function(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def _assert_ordered(haystack: str, fragments: list[str]) -> None:
    cursor = 0
    for fragment in fragments:
        cursor = haystack.index(fragment, cursor) + len(fragment)


def test_a_auto_button_keeps_upstream_synchronous_observable_transition():
    relative = "MSHV_2762/src/HvTxW/hvtxw.cpp"
    pristine = _function(_upstream(relative), "void HvTxW::auto_on()")
    patched = _function(_text(relative), "void HvTxW::auto_on()")
    fragments = [
        "if (f_auto_on)", "f_auto_on = false", 'b_auto_on->setText(tr("AUTO IS OFF"))',
        "else", "f_auto_on = true", 'b_auto_on->setText(tr("AUTO IS ON"))',
        "TRadioAndNetW->SetAuto(true)", "MultiAnswerMod->SetAuto(true)", "emit EmitAuto()",
    ]
    _assert_ordered(pristine, fragments)
    _assert_ordered(patched, fragments)
    assert "Om0rxStationGate::prefetch" not in patched
    assert "gate->confirm" not in patched and "StopAuto();" not in patched


def test_b_autodx_start_auto_keeps_upstream_immediate_state_change():
    relative = "MSHV_2762/src/HvTxW/hvtxw.cpp"
    patched = _function(_text(relative), "void HvTxW::StartAuto()")
    _assert_ordered(patched, [
        "if (!f_auto_on)", "f_auto_on = true", 'b_auto_on->setText(tr("AUTO IS ON"))',
        "TRadioAndNetW->SetAuto(true)", "MultiAnswerMod->SetAuto(true)",
        "emit EmitAuto()", "Om0rxStationGate::autoDesired() = true",
    ])
    assert "Om0rxStationGate::prefetch" not in patched
    assert "gate->confirm" not in patched and "StopAuto();" not in patched


def test_c_internal_stop_preserves_upstream_stop_without_invalidating_authorization():
    relative = "MSHV_2762/src/HvTxW/hvtxw.cpp"
    pristine = _function(_upstream(relative), "void HvTxW::StopAuto()")
    patched = _function(_text(relative), "void HvTxW::StopAuto()")
    for statement in (
        "f_auto_on = false", 'b_auto_on->setText(tr("AUTO IS OFF"))',
        "TRadioAndNetW->SetAuto(false)", "MultiAnswerMod->SetAuto(false)", "emit EmitAuto()",
    ):
        assert statement in pristine and statement in patched
    assert "Om0rxStationGate::noteInternalAutoStopped()" in patched
    assert "invalidate" not in patched
    assert "prepare(" not in patched and "confirm(" not in patched


def test_c2_explicit_global_escape_udp_and_teardown_stops_invalidate():
    main = _text("MSHV_2762/src/main_ms.cpp")
    core = _text("MSHV_2762/src/HvAutoDxer/autodxercore.cpp")
    helper = _function(main, "void Main_Ms::StopTxGlobalWithReason")
    assert "Om0rxStationGate::invalidateAndNotify(this, reason)" in helper
    assert helper.index("invalidateAndNotify") < helper.index("THvTxW->StopAuto()")
    assert 'StopTxGlobalWithReason("stop-tx-global")' in _function(
        main, "void Main_Ms::StopTxGlobal()"
    )
    assert 'StopTxGlobalWithReason("udp-stop")' in _function(
        main, "void Main_Ms::SetUdpCmdStop(bool)"
    )
    assert 'StopTxGlobalWithReason("escape-stop")' in _function(
        main, "void Main_Ms::keyPressEvent(QKeyEvent* event)"
    )
    assert 'StopTxGlobalWithReason("process-teardown")' in _function(
        main, "Main_Ms::~Main_Ms()"
    )
    assert "requestAuthorizationInvalidation" in main
    assert 'enabled ? "autodx-mode-exit" : "autodx-disabled"' in core
    assert 'StopTxGlobalWithReason("tx-watchdog-stop")' in main


def test_c3_tx_watchdog_only_trips_while_the_same_true_edge_remains_asserted():
    tx = _function(
        _text("MSHV_2762/src/HvTxW/hvtxw.cpp"),
        "void HvTxW::SetTxRxCountAutoSeq(bool f)",
    )
    _assert_ordered(tx, [
        "const quint64 txEdgeGeneration = ++m_om0rxTxEdgeGeneration",
        "f_tx_rx = f",
        "if (f && f_no_time_count_txwatchdog != 0",
        "QTimer::singleShot",
        "Om0rxTxWatchdogEdge::shouldTrip",
        "emit EmitTxWatchdogStop()",
        "if (!f)",
        "CountTx73_p(false)",
    ])
    assert 'invalidateAndNotify(this, "tx-watchdog-stop")' not in tx
    assert "StopAuto()" not in tx


def test_d_periodic_telemetry_never_mutates_upstream_automation():
    main = _text("MSHV_2762/src/main_ms.cpp")
    timer = main[main.index("connect(om0rxStateTimer"):main.index("om0rxStateTimer->start")]
    assert "Om0rxStationGate::prefetch" not in timer
    assert "StopAuto" not in timer
    assert "setEnabled(false)" not in timer
    assert "StartAuto" not in timer


def test_e_native_ptt_path_has_no_station_permit_gate():
    body = _function(_text("MSHV_2762/src/main_ms.cpp"), "void Main_Ms::SetRigTxRx(bool f)")
    assert "THvRigControl->SetPtt(f,0)" in body
    for station_gate in ("hasPermit", "consumePermitBlocking", "prefetch", "auditRejected"):
        assert station_gate not in body

    tx = _text("MSHV_2762/src/HvTxW/hvtxw.cpp")
    for signature in ("void HvTxW::StartAuto()", "void HvTxW::auto_on()"):
        auto_body = _function(tx, signature)
        assert "Om0rxStationGate::prefetch" not in auto_body


def test_f_decode_list_enrichment_does_not_control_tx_or_station_routing():
    decode_cpp = _text("MSHV_2762/src/HvDecodeList/decodelist.cpp")
    decode_h = _text("MSHV_2762/src/HvDecodeList/decodelist.h")
    combined = decode_cpp + decode_h
    for forbidden in (
        "Om0rxStationGate",
        "SetPtt(",
        "StopAuto(",
        "StartAuto(",
        "SetBandFromAutoDxer",
        "SetDialFreqFromAutoDxer",
        "/api/digital/station-ready",
    ):
        assert forbidden not in combined


def test_g_native_band_qsy_is_not_vetoed_by_synchronous_station_gate():
    main = _text("MSHV_2762/src/main_ms.cpp")
    band = _function(main, "void Main_Ms::SetBandFromAutoDxer(int bandIndex)")
    dial = _function(main, "void Main_Ms::SetDialFreqFromAutoDxer(int dialFreqHz)")
    assert "ListBands.at(bandIndex)->setChecked(true);" in band
    assert "onBandChangeCompleteForRequest" in band
    assert "Om0rxStationGate *gate" not in band
    assert "gate->prepare" not in band
    assert "finalGate->confirm" not in band
    assert "/api/digital/station-ready" not in band
    assert "Om0rxStationGate *gate" not in dial
    assert "gate->prepare" not in dial
    assert "finalGate->confirm" not in dial
    for body in (band, dial):
        assert "m_autoDxerCore->setEnabled(false)" not in body
        assert "THvTxW->StopAuto()" not in body


def test_g2_explicit_stop_and_emergency_invalidation_remain():
    main = _text("MSHV_2762/src/main_ms.cpp")
    stop = _function(main, "void Main_Ms::StopTxGlobal()")
    stop_with_reason = _function(
        main, "void Main_Ms::StopTxGlobalWithReason(const QString &reason)"
    )
    udp_stop = _function(main, "void Main_Ms::SetUdpCmdStop(bool)")
    assert 'StopTxGlobalWithReason("stop-tx-global")' in stop
    assert 'StopTxGlobalWithReason("udp-stop")' in udp_stop
    assert "invalidateAndNotify(this, reason)" in stop_with_reason
    assert "THvTxW->StopAuto();" in stop_with_reason


def test_h_lowest_ptt_edge_is_direct_native_hardware_control():
    rig = _text("MSHV_2762/src/HvRigControl/hvrigcontrol.cpp")
    low = _function(rig, "void HvRigControl::SetPtt_p(bool flag,int id)")
    assert "THvRigCat->set_ptt(flag,false)" in low
    assert "flag && pttOutputAttempted" in low
    assert "ptt-output-path-unavailable" in low
    for station_gate in ("consumePermitBlocking", "hasPermit", "prefetch", "notePttRequest"):
        assert station_gate not in low
    assert "StopAuto" not in low and "setEnabled(false)" not in low


def test_no_old_reusable_approval_contract_remains():
    combined = "\n".join([
        _text("MSHV_2762/src/om0rxstationgate.h"),
        _text("MSHV_2762/src/main_ms.cpp"),
        _text("MSHV_2762/src/HvTxW/hvtxw.cpp"),
    ])
    assert not re.search(r"approved(?:At|Hz)|canEnable", combined)
    assert "permitNonce().clear()" in combined
    assert "station-permit/consume" in combined
