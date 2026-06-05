"""Smoke tests for the built-in FT8 architecture boundary."""

import asyncio
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import _bootstrap  # noqa: F401


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_frontend_uses_engine_boundary_not_retired_decoder():
    modal = read_text("frontend/js/ft8-modal.js")

    assert "./ft8-engine.js" in modal
    assert "./ft8-decoder.js" not in modal
    assert "loadFT8Engine" in modal
    assert "loadFT8Decoder" not in modal


def test_digital_button_uses_native_window_not_main_modal_or_browser_tab():
    modal = read_text("frontend/js/ft8-modal.js")
    controls = read_text("frontend/templates/controls-row1.html")
    controls_section = read_text("frontend/controls-section.html")
    launcher = read_text("scripts/launch/launch_windows.py")

    assert '@click="openDigitalWindow"' in controls
    assert '@click="openDigitalWindow"' in controls_section
    assert "async openDigitalWindow()" in modal
    assert "window.pywebview.api.open_digital_window()" in modal
    assert "window.open(" not in modal
    assert "Digital window can only be opened from the native launcher." in modal
    assert "class DesktopApi" in launcher
    assert "def open_digital_window(self):" in launcher
    assert "url=DIGITAL_WINDOW_CONFIG[\"url\"]" in launcher
    assert "js_api=api" in launcher


def test_engine_uses_mit_ft8lib_without_mshv_dependency():
    engine = read_text("frontend/js/ft8-engine.js")

    assert "../ft8_ft8lib.js" in engine
    assert "mshv" not in engine.lower()
    assert "receive: 'unavailable'" in engine
    assert "messageEncode: true" in engine


def test_backend_does_not_import_retired_homegrown_protocol():
    service = read_text("services/ft8_service.py")

    assert "services.ft8_protocol" not in service
    assert "rx_decode_enabled = False" in service
    assert "FT8TxEngine" in service
    assert "raise NotImplementedError" not in service


def test_ft8_status_reports_honest_capabilities():
    from services.ft8_service import FT8Service
    from services.ft8_rx_decoder import VENDOR_DECODER_PATH

    status = FT8Service().get_stats()
    decoder_available = VENDOR_DECODER_PATH.exists()

    assert status["engine"] == "ft8_lib"
    assert status["engine_license"] == "MIT"
    assert status["decoder_status"] == ("available" if decoder_available else "unavailable")
    assert status["rx_decoder"]["available"] is decoder_available
    assert status["tx_engine"]["encoder"] == "vendor.ft8_lib.gen_ft8"
    assert status["capabilities"]["waterfall"] is True
    assert status["capabilities"]["rx_decode"] is decoder_available
    assert isinstance(status["capabilities"]["tx"], bool)
    assert status["automation_controller"]["settings"]["allowed_modes"] == ["FT4", "FT8"]
    assert "targets" in status["automation_controller"]


def test_hamlib_rigctl_adapter_parses_and_tracks_ptt_state():
    from radio_control.hamlib_rig import HamlibRig, HamlibRigConfig, parse_rigctl_ptt

    calls = []

    def fake_runner(args, input, capture_output, text, timeout):
        calls.append((args, input, capture_output, text, timeout))
        if "T 1" in input:
            stdout = "\nRig command: T 1\n\nRig command: t\nPTT: 1\n"
        else:
            stdout = "\nRig command: t\nPTT: 0\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    rig = HamlibRig(
        HamlibRigConfig(rigctl_path="rigctl", model=23005, rig_path="192.168.0.199"),
        runner=fake_runner,
    )

    assert parse_rigctl_ptt("Rig command: t\nPTT: 1\n") is True
    assert parse_rigctl_ptt("Rig command: t\nPTT: 0\n") is False
    assert rig.set_mox(True) is True
    assert rig.current_mox is True
    assert rig.current_interlock_state == "TRANSMITTING"
    assert calls[-1][0] == ["rigctl", "-m", "23005", "-r", "192.168.0.199"]


def test_ft8_hamlib_backend_config_is_persistable_and_status_reports_backend():
    api = read_text("backend/api/ft8.py")
    settings = read_text("radio_control/settings_store.py")
    service = read_text("services/ft8_service.py")
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")

    assert "FT8_RIG_BACKEND" in settings
    assert "FT8_HAMLIB_MODEL" in settings
    assert "hamlibModel" in api
    assert "_build_digital_ptt_device" in api
    assert '{"", "auto", "direct", "flex", "smartsdr"}' in api
    assert "ptt_device=ptt_device" in api
    assert "self.ptt_device = ptt_device" in service
    assert "'tx_ptt_backend': tx_ptt_backend" in service
    assert "rigBackend: 'auto'" in modal
    assert "Hamlib Model" in template


def test_ft8_operator_settings_are_persistable():
    api = read_text("backend/api/ft8.py")
    settings = read_text("radio_control/settings_store.py")
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")

    assert "operatorSettings" in api
    assert "FT8_OPERATOR_SETTINGS" in settings
    assert "ft8OperatorSettingsPayload" in modal
    assert "Band hopping" in template
    assert "Treat 73's as CQ" in template
    assert "Spot-driven hunt" in template
    assert "@router.get(\"/automation/status\")" in api
    assert "ft8SubmitAutomationTarget" in modal
    assert "Backend controller" in template


def test_decoded_rows_are_enriched_and_grouped_by_pass():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")
    css = read_text("frontend/ft8-modal.css")

    assert "ft8NormalizeDecodedMessage" in modal
    assert "ft8VisibleBandActivityRows" in modal
    assert "ft8VisibleRxFrequencyRows" in modal
    assert "ft8WithDecodePassSeparators" in modal
    assert "_statusPending" in modal
    assert "ft8StatusCellLabel" in modal
    assert "Checking..." not in modal
    assert "this.ft8EnrichDecodedMessage(message);" in modal
    assert "ft8SubmitAutomationTarget(message)" in modal
    assert "ft8-decode-pass-separator" in template
    assert "txInProgress" in modal
    assert ":class=\"{ tx: ft8.txInProgress" in template
    assert ".ft8-decode-pass-separator" in css
    assert "@router.post(\"/decoded/clear\")" in read_text("backend/api/ft8.py")
    assert "clear_decoded_messages" in read_text("services/ft8_service.py")


def test_digital_frequency_plan_supports_ft8_ft4_hf_to_6m():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")

    assert "FT8_DEFAULT_FREQUENCY_PLAN" in modal
    assert "{ band: '160m', ft8: 1.840" in modal
    assert "{ band: '6m', ft8: 50.313" in modal
    assert "band: '2m'" not in modal
    assert "ft2:" not in modal
    assert "Digital Frequencies" in template
    assert '<option value="FT2">FT2</option>' not in template
    assert "FT2 MHz" not in template
    assert "Call</span>" in template
    assert "DXCC</span>" in template


def test_builtin_tx_boundary_is_wired_for_real_ft8_ft4_controls():
    service = read_text("services/ft8_tx.py")
    api = read_text("backend/api/ft8.py")
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")

    assert "GEN_FT8_PATH" in service
    assert "def transmit(" in service
    assert "def tune_tone(" in service
    assert "confirmation_timeout=confirmation_timeout" in service
    assert "require_confirmation=True" in service
    assert "CAT PTT {state} was not confirmed" in service
    assert "current_interlock_state" in read_text("radio_control/flex_radio.py")
    assert "TRANSMITTING" in read_text("radio_control/flex_radio.py")
    assert "@router.post(\"/tx/enable\")" in api
    assert "@router.post(\"/tx/halt\")" in api
    assert "@router.post(\"/tx/tune\")" in api
    assert "ft8EnableTx" in modal
    assert "ft8HaltTx" in modal
    assert "ft8TuneTone" in modal
    assert "@click=\"ft8EnableTx\"" in template
    assert "FT8_LEGACY_TX_ROUTES_ENABLED" in api
    assert "_raise_legacy_tx_disabled(\"/api/ft8/transmit\")" in api
    assert "async def queue_manual_tx_button" in read_text("services/ft8_service.py")


def test_auto_call_and_qso_state_machine_are_wired():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    class Message:
        message = "K1ABC OM0RX -12"
        snr = -15
        freq = 1500

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    qso = QSOSession(
        their_call="K1ABC",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )

    asyncio.run(service._update_qso_state(qso, Message()))

    assert qso.state == QSOState.SENDING_REPORT
    assert service.tx_queue == ["K1ABC OM0RX R-15"]


def test_manual_first_call_seeds_qso_and_auto_sequence_advances_exchange():
    from services.ft8_service import FT8Service, QSOState

    class Reply:
        message = "OM0RX A61DI -08"
        snr = -10
        freq = 391

    class Rr73:
        message = "OM0RX A61DI RR73"
        snr = -11
        freq = 391

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.enable_tx()

    asyncio.run(service.queue_tx_message("A61DI OM0RX JN88"))
    assert service.auto_sequence is True
    assert service.active_qsos["A61DI"].state == QSOState.WAITING_RESPONSE

    service.tx_queue.clear()
    asyncio.run(service._auto_sequence_handler(Reply()))
    assert service.active_qsos["A61DI"].state == QSOState.SENDING_REPORT
    assert service.tx_queue == ["A61DI OM0RX R-10"]

    service.tx_queue.clear()
    asyncio.run(service._auto_sequence_handler(Rr73()))
    assert service.active_qsos["A61DI"].state == QSOState.SENDING_73
    assert service.tx_queue == ["A61DI OM0RX 73"]

    asyncio.run(service._complete_qso_after_final_tx("A61DI OM0RX 73"))
    assert "A61DI" not in service.active_qsos
    assert service.stats["qso_completed"] == 1
    assert service.tx_enabled is False
    assert service.auto_sequence is False


def test_auto_sequence_handles_ack_report_and_tailenders_intelligently():
    from services.ft8_service import FT8Service, QSOState

    class AckReport:
        message = "OM0RX A61DI R-08"
        snr = -9
        freq = 391

    class Tailender:
        message = "OM0RX A61DI RR73; GB4SPD <3Y0K> -16"
        snr = -10
        freq = 560

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.enable_tx()
    asyncio.run(service.queue_tx_message("A61DI OM0RX R-10"))

    service.tx_queue.clear()
    asyncio.run(service._auto_sequence_handler(AckReport()))
    assert service.active_qsos["A61DI"].state == QSOState.SENDING_73
    assert service.tx_queue == ["A61DI OM0RX RR73"]

    service.tx_queue.clear()
    asyncio.run(service._auto_sequence_handler(Tailender()))
    assert service.active_qsos["A61DI"].state == QSOState.SENDING_73
    assert service.tx_queue == ["A61DI OM0RX 73"]


def test_auto_sequence_ignores_unrelated_directed_messages_and_repeats_last_tx():
    from services.ft8_service import FT8Service

    class OtherStation:
        message = "OM0RX K1ABC -12"
        snr = -12
        freq = 1200

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.enable_tx()
    asyncio.run(service.queue_tx_message("A61DI OM0RX JN88"))
    service.tx_queue.clear()

    asyncio.run(service._auto_sequence_handler(OtherStation()))

    assert service.active_tx_message == "A61DI OM0RX JN88"
    assert service.tx_queue == []
    assert sorted(service.active_qsos) == ["A61DI"]


def test_immediate_tx_waits_for_next_slot_when_too_late():
    from services.ft8_service import FT8Service

    class Service(FT8Service):
        def _live_cycle_state(self):
            return 15.0, 10.0, 100, True

    service = Service(mycall="OM0RX", mygrid="JN88")
    service.tx_enabled = True
    service.tx_queue.append("A61DI OM0RX JN88")

    transmitted = asyncio.run(service.transmit_queued_now_if_possible())

    assert transmitted is False
    assert service.tx_queue == ["A61DI OM0RX JN88"]
    assert "after slot start is too late" in service.tx_status


def test_immediate_manual_tx_uses_current_over_with_usable_time():
    from services.ft8_service import FT8Service

    class Service(FT8Service):
        def _live_cycle_state(self):
            return 15.0, 0.2, 100, True

        async def transmit_message(self, message, max_duration_seconds=None, attempt_id=None, playback_delay_seconds=None):
            self.sent_message = message
            self.sent_duration = max_duration_seconds
            self.sent_delay = playback_delay_seconds

    service = Service(mycall="OM0RX", mygrid="JN88")
    service.tx_enabled = True
    service.tx_queue.append("WU5E OM0RX JN88")

    transmitted = asyncio.run(service.transmit_queued_now_if_possible(force_current_slot=True))

    assert transmitted is True
    assert service.sent_message == "WU5E OM0RX JN88"
    assert service.sent_duration == 13.9
    assert service.sent_delay == 0.0
    assert service.tx_queue == []


def test_queued_tx_prekeys_before_next_tx_slot():
    from services.ft8_service import FT8Service

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_enabled = True
    service.tx_queue.append("YU7GMN OM0RX JN88")

    should_prekey, delay, next_slot = service._should_prekey_next_tx_slot(
        cycle_number=100,
        cycle_position=14.2,
        slot_is_tx=False,
    )

    assert should_prekey is True
    assert round(delay, 1) == 0.8
    assert next_slot == 101


def test_active_repeat_tx_prekeys_even_before_queue_is_rebuilt():
    from services.ft8_service import FT8Service

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_enabled = True
    service.active_tx_message = "S55X OM0RX JN88"

    should_prekey, delay, next_slot = service._should_prekey_next_tx_slot(
        cycle_number=100,
        cycle_position=13.4,
        slot_is_tx=False,
    )

    assert should_prekey is True
    assert round(delay, 1) == 1.6
    assert next_slot == 101


def test_prekeyed_tx_passes_playback_delay_to_transmit():
    from services.ft8_service import FT8Service

    class Service(FT8Service):
        async def transmit_message(self, message, max_duration_seconds=None, attempt_id=None, playback_delay_seconds=None):
            self.sent_message = message
            self.sent_duration = max_duration_seconds
            self.sent_delay = playback_delay_seconds

    service = Service(mycall="OM0RX", mygrid="JN88")
    service.tx_enabled = True
    service.tx_queue.append("YU7GMN OM0RX JN88")

    asyncio.run(service._handle_tx_cycle(playback_delay_seconds=0.8))

    assert service.sent_message == "YU7GMN OM0RX JN88"
    assert service.sent_duration == 13.9
    assert service.sent_delay == 0.8
    assert service.tx_queue == []


def test_repeated_active_qso_tx_preserves_attempt_id():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    class Service(FT8Service):
        async def transmit_message(self, message, max_duration_seconds=None, attempt_id=None, playback_delay_seconds=None):
            self.sent_message = message
            self.sent_attempt_id = attempt_id

    service = Service(mycall="OM0RX", mygrid="JN88")
    service.tx_enabled = True
    service.auto_call_enabled = True
    qso = QSOSession(
        their_call="IN3IZQ",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )
    service.active_qsos[qso.their_call] = qso
    service.active_attempt_id = qso.attempt_id
    service.active_tx_message = "IN3IZQ OM0RX JN88"

    asyncio.run(service._handle_tx_cycle(playback_delay_seconds=0.0))

    assert service.sent_message == "IN3IZQ OM0RX JN88"
    assert service.sent_attempt_id == qso.attempt_id


def test_tx_engine_trims_trailing_silence_but_keeps_protocol_lead():
    import numpy as np
    from services.ft8_tx import FT8TxEngine

    engine = FT8TxEngine()
    samples = np.concatenate([
        np.zeros(1200, dtype=np.float32),
        np.ones(1200, dtype=np.float32) * 0.1,
        np.zeros(1200, dtype=np.float32),
    ])

    trimmed = engine._trim_trailing_silence(samples)

    assert len(trimmed) < len(samples)
    assert len(trimmed) > 2400
    assert np.all(trimmed[:1200] == 0)


def test_automation_can_keep_tx_armed_after_qso_completion():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.enable_tx()
    service.auto_call_enabled = True
    service.active_tx_message = "A61DI OM0RX 73"
    service.active_qsos["A61DI"] = QSOSession(
        their_call="A61DI",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.SENDING_73,
    )

    asyncio.run(service._complete_qso(service.active_qsos["A61DI"]))

    assert service.tx_enabled is True
    assert service.auto_sequence is True
    assert service.stats["qso_completed"] == 1


def test_directed_reply_keeps_active_qso_alive_past_watchdog():
    from datetime import datetime, timedelta, timezone
    from services.ft8_service import FT8Service, QSOSession, QSOState

    class Service(FT8Service):
        async def transmit_message(self, message, max_duration_seconds=None):
            self.sent_message = message

    class Reply:
        message = "OM0RX OH6FSO +06"
        snr = 14
        freq = 2766

    service = Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.enable_tx()
    service.watchdog_cycles["FT8"] = 1
    service.tx_watchdog_started_at = datetime.now(timezone.utc) - timedelta(minutes=3)
    service.active_qsos["OH6FSO"] = QSOSession(
        their_call="OH6FSO",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )

    asyncio.run(service._auto_sequence_handler(Reply()))

    assert service.tx_enabled is True
    assert service.auto_sequence is True
    assert service.active_qsos["OH6FSO"].state == QSOState.SENDING_REPORT
    assert service.tx_queue == ["OH6FSO OM0RX R+14"]


def test_stale_locator_does_not_replace_report_after_reply():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.active_qsos["EA1AA"] = QSOSession(
        their_call="EA1AA",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.SENDING_REPORT,
        rx_count=1,
    )

    asyncio.run(service.queue_tx_message("EA1AA OM0RX R+13"))
    asyncio.run(service.queue_tx_message("EA1AA OM0RX JN88"))

    assert service.active_tx_message == "EA1AA OM0RX R+13"
    assert service.tx_queue == ["EA1AA OM0RX R+13"]
    assert "ignored stale locator" in service.tx_status


def test_halt_is_hard_stop_for_active_qso_late_reply():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.enable_tx()
    service.active_qsos["EA1AA"] = QSOSession(
        their_call="EA1AA",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )

    service.halt_tx()

    assert service.tx_enabled is False
    assert service.auto_sequence is False
    assert service.tx_inhibit_reason == "user_abort"
    assert service.active_qsos == {}


def test_abort_current_attempt_hard_stops_and_backs_off_target():
    from services.ft8_service import FT8Service

    class FakeTxEngine:
        def __init__(self):
            self.aborted = False

        def abort(self):
            self.aborted = True

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    fake = FakeTxEngine()
    service.tx_engine = fake
    service.tx_capability_enabled = True
    service.tx_enabled = True
    service.auto_sequence = True
    service.auto_call_enabled = True
    target = service.automation_controller.ingest_target({
        "callsign": "EA1AA",
        "band": "30m",
        "mode": "FT8",
        "message": "CQ EA1AA IN83",
        "call_status": "ATNO",
        "dxcc_status": "ATNO",
        "heard": True,
    })
    service.automation_controller.active_target_key = target.key
    service.tx_queue.append("EA1AA OM0RX JN88")
    service.active_tx_message = "EA1AA OM0RX JN88"

    service.abort_current_attempt()

    assert fake.aborted is True
    assert service.tx_enabled is False
    assert service.auto_sequence is False
    assert service.tx_inhibit_reason == "user_abort"
    assert service.tx_queue == []
    assert service.active_tx_message is None
    assert target.state == "backoff"


def test_watchdog_does_not_halt_active_qso_reply_transmit():
    from datetime import datetime, timedelta, timezone
    from services.ft8_service import FT8Service, QSOSession, QSOState

    class Service(FT8Service):
        async def transmit_message(self, message, max_duration_seconds=None):
            await super().transmit_message(message, max_duration_seconds=max_duration_seconds)

    class FakeTxEngine:
        class Status:
            available = True
            reason = "ok"

            def to_dict(self):
                return {"available": True}

        status = Status()

        def transmit(self, message, **kwargs):
            class Result:
                def __init__(self, text):
                    self.duration_seconds = 13.9
                    self.message = text

                def to_dict(self):
                    return {"message": self.message}

            return Result(message)

    service = Service(mycall="OM0RX", mygrid="JN88")
    service.tx_engine = FakeTxEngine()
    service.tx_capability_enabled = True
    service.enable_tx()
    service.watchdog_cycles["FT8"] = 1
    service.tx_watchdog_started_at = datetime.now(timezone.utc) - timedelta(minutes=3)
    service.active_qsos["OH6FSO"] = QSOSession(
        their_call="OH6FSO",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.SENDING_REPORT,
    )

    asyncio.run(service.transmit_message("OH6FSO OM0RX R+14"))

    assert service.tx_enabled is True
    assert service.stats["transmitted_count"] == 1
    assert "watchdog halted" not in service.tx_status


def test_watchdog_moves_auto_call_to_next_target_instead_of_halting_automation():
    from datetime import datetime, timedelta, timezone
    from services.ft8_service import FT8Service

    class FakeTxEngine:
        class Status:
            available = True
            reason = "ok"

            def to_dict(self):
                return {"available": True}

        status = Status()

        def abort(self):
            self.aborted = True

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_engine = FakeTxEngine()
    service.tx_capability_enabled = True
    service.enable_tx()
    service.auto_call_enabled = True
    service.watchdog_cycles["FT8"] = 1
    service.tx_watchdog_started_at = datetime.now(timezone.utc) - timedelta(minutes=3)
    target = service.automation_controller.ingest_target({
        "callsign": "EA1AA",
        "band": "30m",
        "mode": "FT8",
        "message": "CQ EA1AA IN83",
        "call_status": "ATNO",
        "dxcc_status": "ATNO",
        "heard": True,
    })
    service.automation_controller.active_target_key = target.key
    service.active_tx_message = "EA1AA OM0RX JN88"

    asyncio.run(service.transmit_message("EA1AA OM0RX JN88"))

    assert service.tx_enabled is True
    assert service.auto_call_enabled is True
    assert service.active_tx_message is None
    assert target.state == "backoff"
    assert "target backed off" in service.tx_status


def test_auto_call_max_attempts_backoff_keeps_searching_next_target():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    class FakeTxEngine:
        class Status:
            available = True
            reason = "ok"

            def to_dict(self):
                return {"available": True}

        status = Status()

        def abort(self):
            self.aborted = True

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_engine = FakeTxEngine()
    service.tx_capability_enabled = True
    service.enable_tx()
    service.auto_call_enabled = True
    service.auto_call_limit = 5
    service.auto_call_remaining = 0
    target = service.automation_controller.ingest_target({
        "callsign": "YO3OBB",
        "band": "40m",
        "mode": "FT8",
        "message": "CQ YO3OBB KN34",
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
        "heard": True,
    })
    service.automation_controller.active_target_key = target.key
    qso = QSOSession(
        their_call="YO3OBB",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )
    qso.tx_count = service.automation_controller.settings.max_attempts_per_target
    qso.rx_count = 0
    service.active_qsos[qso.their_call] = qso
    service.active_attempt_id = qso.attempt_id
    service.active_tx_message = "YO3OBB OM0RX JN88"
    service.slot_is_tx = True
    service.is_tx_cycle = True

    asyncio.run(service._handle_tx_cycle())

    assert service.auto_call_enabled is True
    assert service.tx_enabled is True
    assert service.auto_call_remaining == 5
    assert service.active_qsos == {}
    assert service.active_tx_message is None
    assert target.state == "backoff"
    assert "searching next target" in service.tx_status


def test_ft4_service_uses_ft4_slot_duration():
    from services.ft8_service import FT8Service

    assert FT8Service(mode="FT8")._cycle_duration_seconds() == 15.0
    assert FT8Service(mode="FT4")._cycle_duration_seconds() == 7.5


def test_digital_tx_start_and_audio_duration_are_protocol_tight():
    from services.ft8_service import FT8Service

    ft8 = FT8Service(mode="FT8")
    ft4 = FT8Service(mode="FT4")

    assert ft8._max_safe_late_start_seconds() == 0.35
    assert ft8._protocol_tx_audio_seconds() == 13.9
    assert ft4._max_safe_late_start_seconds() == 0.2
    assert ft4._protocol_tx_audio_seconds() == 6.35


def test_prekeyed_cat_tx_requires_radio_mox_before_audio():
    tx = read_text("services/ft8_tx.py")

    assert "confirmation_timeout = max(0.25, min(1.2, playback_deadline - time.monotonic() - 0.05))" in tx
    assert "require_confirmation=True" in tx
    assert "playback_deadline - pre_key_seconds" in tx
    assert "pre_key_seconds = 1.7" in tx
    assert "self._sleep_until(playback_deadline)" in tx


def test_auto_call_backs_off_when_target_is_busy_elsewhere():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    class FakeTxEngine:
        class Status:
            available = True
            reason = "ok"

            def to_dict(self):
                return {"available": True}

        status = Status()

        def abort(self):
            pass

    class Message:
        message = "VA3THP DL4ME RR73"

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_engine = FakeTxEngine()
    service.tx_capability_enabled = True
    service.enable_tx()
    service.auto_call_enabled = True
    target = service.automation_controller.ingest_target({
        "callsign": "DL4ME",
        "band": "30m",
        "mode": "FT8",
        "message": "CQ DL4ME JO50",
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
        "heard": True,
    })
    service.automation_controller.active_target_key = target.key
    qso = QSOSession(
        their_call="DL4ME",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )
    service.active_qsos[qso.their_call] = qso
    service.active_attempt_id = qso.attempt_id
    service.active_tx_message = "DL4ME OM0RX JN88"
    service.tx_queue.append("DL4ME OM0RX JN88")

    service._backoff_active_target_if_busy_elsewhere(Message())

    assert service.active_qsos == {"DL4ME": qso}
    assert service.tx_queue == ["DL4ME OM0RX JN88"]
    assert target.state != "backoff"
    assert service.automation_decisions[-1]["event"] == "target-busy-observed"
    assert service.automation_decisions[-1]["reason"] == "active-qso-still-owned-by-backend"


def test_busy_elsewhere_decode_does_not_abort_active_tx():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    class FakeTxEngine:
        class Status:
            available = True
            reason = "ok"

            def to_dict(self):
                return {"available": True}

        status = Status()

        def __init__(self):
            self.abort_count = 0

        def abort(self):
            self.abort_count += 1

    class Message:
        message = "VA3THP DL4ME RR73"

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_engine = FakeTxEngine()
    service.tx_capability_enabled = True
    service.enable_tx()
    service.auto_call_enabled = True
    target = service.automation_controller.ingest_target({
        "callsign": "DL4ME",
        "band": "30m",
        "mode": "FT8",
        "message": "CQ DL4ME JO50",
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
        "heard": True,
    })
    service.automation_controller.active_target_key = target.key
    qso = QSOSession(
        their_call="DL4ME",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )
    service.active_qsos[qso.their_call] = qso
    service.active_attempt_id = qso.attempt_id
    service.active_tx_message = "DL4ME OM0RX JN88"
    service.tx_queue.append("DL4ME OM0RX JN88")
    service.tx_in_progress = True

    service._backoff_active_target_if_busy_elsewhere(Message())

    assert service.tx_engine.abort_count == 0
    assert service.active_qsos == {"DL4ME": qso}
    assert service.tx_queue == ["DL4ME OM0RX JN88"]
    assert target.state != "backoff"
    assert service.automation_decisions[-1]["event"] == "target-busy-observed"
    assert service.automation_decisions[-1]["reason"] == "active-qso-still-owned-by-backend"


def test_generated_ft8_tx_frame_decodes_at_requested_audio_frequency():
    import tempfile
    import numpy as np

    from services.ft8_rx_decoder import VendorFT8LibRxDecoder
    from services.ft8_tx import FT8TxEngine

    tx = FT8TxEngine(output_sample_rate=12000)
    decoder = VendorFT8LibRxDecoder()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        wav_path = Path(temp_file.name)

    try:
        tx._generate_wav("IK0EIA OM0RX JN88", wav_path, "FT8", 1500)
        samples, sample_rate = tx._read_wav(wav_path)
        prepared = tx._prepare_output_samples(samples, sample_rate)
        trimmed = tx._trim_trailing_silence(prepared)

        assert 13.8 <= len(trimmed) / tx.output_sample_rate <= 14.0

        window = np.zeros(tx.output_sample_rate * 15, dtype=np.float32)
        window[: len(trimmed)] = trimmed
        decoded = decoder.decode_window(
            window,
            sample_rate=tx.output_sample_rate,
            window_start=datetime(2026, 6, 3, tzinfo=timezone.utc),
            mode="FT8",
        )
    finally:
        wav_path.unlink(missing_ok=True)

    assert [(item.message, item.freq) for item in decoded] == [("IK0EIA OM0RX JN88", 1500.0)]


def test_running_service_mode_switch_updates_audio_processor():
    from services.ft8_service import FT8Service

    service = FT8Service(mode="FT8")
    service.set_mode("FT4")

    assert service.mode == "FT4"
    assert service.audio_processor.mode == "FT4"
    assert service._cycle_duration_seconds() == 7.5


def test_unsupported_ptt_method_disables_tx_capability():
    from services.ft8_tx import FT8TxEngine

    status = FT8TxEngine(ptt_method="DTR").status

    assert status.available is False
    assert "Unsupported" in status.reason
    assert FT8TxEngine._normalise_audio_frequency(4000) == 4000


def test_flexradio_dax_tx_avoids_known_bad_wdmks_path():
    tx = read_text("services/ft8_tx.py")

    assert "def _resolve_output_device_indexes" in tx
    assert "\"wasapi\" in host" in tx
    assert "\"directsound\" in host" in tx
    assert "\"wdm-ks\" in host" in tx
    assert 'name_l == "dax tx (flexradio dax)"' in tx
    assert "Digital TX audio failed on all candidate output devices" in tx


def test_selected_cq_station_primes_reply_message_for_enable_tx():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")
    css = read_text("frontend/ft8-modal.css")

    assert "this.ft8.selectedTxMessage = 1;" in modal
    assert "Select a decoded station or TX message first" in modal
    assert "Manual TX queued by backend" in modal
    assert "ft8CycleProgressStyle" in modal
    assert "ft8WatchdogLabel" in modal
    assert "ft8ExtendWatchdog" in modal
    assert "/api/ft8/tx/watchdog/extend" in modal
    assert "ft8ActiveTxCall" in modal
    assert "async ft8SelectMessage" in modal
    assert "async ft8EngageQso" in modal
    assert "async ft8AutoCallChanged" in modal
    assert "async ft8RunAutoCallSweep" in modal
    assert "async ft8ClearQsoTarget" in modal
    assert "ft8AddTxDisplayRow" in modal
    assert "ft8InferTransmitSlotFromDecode" in modal
    assert "ft8QueueSelectedTxMessage" in modal
    assert "ft8RestoreQsoTargetFromTxMessage" in modal
    assert "ft8PartnerCallFromTxText" in modal
    assert "this.ft8RestoreQsoTargetFromTxMessage(text)" in modal
    assert "this.ft8RestoreQsoTargetFromTxMessage(this.ft8.activeTxMessage)" in modal
    assert "ft8DirectedPartsForSelected" in modal
    assert "ft8SignalReportFromDecode" in modal
    assert "activeAttemptId" in modal
    assert "digitalState" in modal
    assert "pendingTxIntent" in modal
    assert "lastLogSyncKey" in modal
    assert "ft8SyncActiveQsoToMainLog" in modal
    assert "ft8SyncSelectedTxStage" in modal
    assert "status.pending_message" in modal
    assert "decodedRefreshInFlight" in modal
    assert "backendDecodedCount > Number(this.ft8.lastDecodedFetchCount || 0)" in modal
    assert "last_cancel_abort_reason" in modal
    assert "'active-target'" in modal
    assert "this.ft8BroadcastDigitalEvent('decoded-selected', logPayload)" in modal
    assert "this.applyDigitalSelectionToLog(logPayload, 'decoded-selected')" in modal
    assert "automationDecisions" in modal
    assert "ft8MaybeAdvanceActiveQso" not in modal
    assert "this.ft8.txEvenFirst = !stationWasEven;" in modal
    assert "await this.ft8EngageBackendTarget(message" in modal
    assert "Select or double-click a decoded station before TX" in modal
    assert "this.ft8FindSelectedDecodedMessage()" in modal
    assert "source: options.source || 'manual_tx_button'" in modal
    assert "'/api/ft8/automation/engage'" in modal
    assert "'/api/ft8/tx/manual'" in modal
    assert "Manual TX queued by backend" in modal
    assert "Queued next TX slot" in modal
    assert "this.ft8.txEnabled = true;" in modal
    assert "@dblclick.stop=\"ft8EngageQso(msg)\"" in template
    assert "@change=\"ft8AutoCallChanged\"" in template
    assert "@click=\"ft8QueueSelectedTxMessage(tx.id, { immediate: true })\"" in template
    assert "replace_active: Optional[bool] = True" in read_text("backend/api/ft8.py")
    assert "_raise_legacy_tx_disabled(\"/api/ft8/transmit\")" in read_text("backend/api/ft8.py")
    assert "@router.post(\"/automation/engage\")" in read_text("backend/api/ft8.py")
    assert "await service.engage_target(" in read_text("backend/api/ft8.py")
    assert "ft8StopTransmitOnly" in modal
    assert "ft8InstallKeyboardShortcuts" in modal
    assert "event.key !== 'Escape'" in modal
    assert "Abort QSO / Stop TX" in template
    assert "Abort the current QSO attempt" in template
    assert "Stop RX" in template
    assert "ft8-compact-toolbar" in template
    assert "ft8-station-strip" in template
    assert "ft8-modal-header" not in template
    assert "QSO / Rx Frequency" in template
    assert "Clear QSO" in template
    assert "return !isTx && message?._displayAccepted !== false && this.ft8PassesStableDecodeFilters(message);" in modal
    assert "this.ft8ClearQsoTarget({ haltTx: false, keepStatus: true });" in modal
    assert "/api/ft8/tx/abort-current" in modal
    assert "TX stopped; re-arm TX to transmit again" in modal
    assert "Auto Call stopped" in modal
    assert "Number(status.active_qsos || 0) === 0" in modal
    assert "if (this.ft8HasActiveQsoAttempt())" in modal
    assert "ft8NormaliseReportValue" in modal
    assert "ft8SyncBackendAutomationSettings" in modal
    assert "ft8ArmAutomationTx" in modal
    assert "handleTransmitting" in modal
    assert "direction: 'tx'" in modal
    assert "const source = options.pending ? 'tx_pending' : 'tx';" in modal
    assert "immediate: Optional[bool] = False" in read_text("backend/api/ft8.py")
    assert "transmit_queued_now_if_possible" in read_text("services/ft8_service.py")
    assert "self.tx_queue.clear()" in read_text("services/ft8_service.py")
    assert "max_duration_seconds" in read_text("services/ft8_tx.py")
    assert "_trim_trailing_silence" in read_text("services/ft8_tx.py")
    assert "ptt_limit_seconds=duration + 1.25" in read_text("services/ft8_tx.py")
    assert "Digital CAT PTT deadline reached" in read_text("services/ft8_tx.py")
    assert "def _max_safe_late_start_seconds" in read_text("services/ft8_service.py")
    assert "protocol-safe" in read_text("services/ft8_service.py")
    assert "force_current_slot=True" in read_text("backend/api/ft8.py")
    assert "0.35 if stats.get(\"mode\") == \"FT8\" else 0.2" in read_text("backend/api/ft8.py")
    assert "'tx_in_progress': self.tx_in_progress" in read_text("services/ft8_service.py")
    assert "'tx_ptt_command_active': tx_ptt_command_active" in read_text("services/ft8_service.py")
    assert "'tx_radio_mox': tx_radio_mox" in read_text("services/ft8_service.py")
    assert "'tx_rf_active': tx_rf_active" in read_text("services/ft8_service.py")
    assert '"last_audio_output_device": getattr(self.tx_engine, "last_audio_output_device", None)' in read_text("services/ft8_service.py")
    assert "status.tx_rf_active ?? status.tx_in_progress" in modal
    assert "status.tx_ptt_command_active ?? status.tx_in_progress" in modal
    assert "ft8.txPttCommandActive ? 'PTT' : 'RX'" in read_text("frontend/templates/modal-ft8.html")
    assert "def ptt_on(self) -> bool" in read_text("services/ft8_tx.py")
    assert '"rx_audio_frequency": rx_audio_frequency' in read_text("services/ft8_service.py")
    assert "activeAutomationTarget?.audio_offset" in modal
    assert "this.ft8SetRxOffset(backendRxOffset)" in modal
    assert "this.ft8SetTxOffset(backendTxOffset)" in modal
    assert "return true;" in modal
    assert "ft8SnrCell" in modal
    assert "this.ft8.autoSequence = true;" in modal
    assert "ft8-cycle-meter" in template
    assert "ft8-watchdog-meter" in template
    assert "ft8-watchdog-extend-btn" in template
    assert "'ft8-enable-tx-active': ft8.txEnabled" in template
    assert ".ft8-decode-row.working" in css
    assert ".ft8-decode-row.reply" in css
    assert ".ft8-decode-row.tx" in css
    assert ".ft8-decode-row.reply {\n    background: #facc15;" in css
    assert ".ft8-decode-row.tx {\n    background: #ef4444;" in css
    assert "filter: brightness(1.18);" in css
    assert "'cycle_position': live_cycle_position" in read_text("services/ft8_service.py")
    assert "extend_watchdog" in read_text("services/ft8_service.py")
    assert "@router.post(\"/tx/watchdog/extend\")" in read_text("backend/api/ft8.py")
    assert "@router.post(\"/tx/abort-current\")" in read_text("backend/api/ft8.py")
    assert "ft8AppendDecodedMessage" in modal
    assert "ft8MergeDecodedMessage" in modal
    assert "ft8PassesStableDecodeFilters" in modal
    assert "ft8IsCqOrClosingMessage" in modal
    assert "ft8ScrollDecodePanesToBottom" in modal
    assert "decodedMessages.push" in modal
    assert "decodedMessages.shift" in modal
    assert "this.ft8.decodedMessages = messages.map" not in modal
    assert "message?._displayAccepted !== false && this.ft8PassesStableDecodeFilters(message)" in modal
    assert "orderValue(a) - orderValue(b)" in modal
    assert 'ref="ft8BandActivityList"' in template
    assert 'ref="ft8RxFrequencyList"' in template


def test_local_qso_status_cache_provides_call_slot_flags():
    from radio_control.qso_status_store import DuckDBQSOStatusStore

    store = DuckDBQSOStatusStore()
    store._ensure_loaded = lambda: True
    store.call_worked = {"EA1AA"}
    store.call_confirmed = {"EA1AA"}
    store.call_band_worked = {("EA1AA", "20m")}
    store.call_mode_worked = {("EA1AA", "FT8")}
    store.call_bandmode_confirmed = {("EA1AA", "20m", "FT8")}

    assert store.call_flags("EA1AA", "20m", "FT8") == (True, True, False, False, True)
    assert store.call_flags("EA1AA", "15m", "FT8") == (True, True, True, False, False)
    assert store.call_flags("K3ZK", "20m", "FT8") == (False, False, True, True, False)


def test_decoded_ft8_enrichment_uses_local_cache_before_wavelog_api():
    api = read_text("backend/api/ft8.py")
    store = read_text("radio_control/qso_status_store.py")

    assert "local_call_flags = await asyncio.to_thread(qso_status_store.call_flags, callsign, band, mode)" in api
    assert "if source != \"decoded\":" in api
    assert "await classifier.call_status_flags(callsign, band, mode)" in api
    assert "lotw_qsl_rcvd, eqsl_qsl_rcvd, qsl_rcvd" in store
    assert "def call_flags(" in store


def test_ft8_grid_parser_does_not_treat_rr73_as_grid():
    modal = read_text("frontend/js/ft8-modal.js")

    assert "!/^(RR73|73)$/.test(part)" in modal


def test_ft8_slot_clock_uses_ntp_offset_for_cycle_timing():
    from services.ft8_service import FT8Service

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service._get_cached_time_sync = lambda: {"ok": True, "offset_ms": -1000.0}

    real_now = service._now()
    slot_now = service._slot_now()

    assert 0.8 <= (real_now - slot_now).total_seconds() <= 1.2


def test_ft8_timing_contracts_use_corrected_slot_clock():
    service = read_text("services/ft8_service.py")

    assert "def _clock_offset_seconds" in service
    assert "def _slot_now" in service
    assert "now = self._slot_now()" in service
    assert "current_time = self._slot_now()" in service
    assert "slot_now = self._slot_now()" in service
    assert "'time_correction_seconds': self._clock_offset_seconds()" in service


def test_waterfall_uses_fixed_scan_lines_without_history_compression():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")
    api = read_text("backend/api/ft8.py")
    service = read_text("services/ft8_service.py")

    assert "ft8VisibleWaterfallRows" in modal
    assert "ctx.createImageData(width, height)" in modal
    assert "data[data.length - 1 - y]" in modal
    assert "ft8ClampWaterfallIntensity" in modal
    assert "getWaterfallRgb" in modal
    assert "ft8WaterfallSettingChanged" in modal
    assert "ft8.display.waterfall" in modal
    assert "waterfallEnabled" in api
    assert "service.audio_stream_enabled = bool(config.waterfallEnabled)" in api
    assert "if service.audio_stream_enabled:" in api
    assert "if not self.audio_stream_enabled:" in service
    assert "Waterfall disabled" in template
    assert "rowHeight = height / data.length" not in modal


def test_watchdog_is_time_based_and_repeats_active_tx_message():
    service = read_text("services/ft8_service.py")
    tx = read_text("services/ft8_tx.py")

    assert "tx_watchdog_started_at" in service
    assert "limit * 60" in service
    assert "watchdog_remaining_seconds" in service
    assert "self.active_tx_message" in service
    assert "if self.tx_enabled and not self.tx_queue and self.active_tx_message" in service
    assert "self.tx_engine.abort()" in service
    assert "def abort(self) -> None:" in tx
    assert "sd.stop()" in tx
    assert "_set_cat_ptt(flex, False" in tx


def test_halt_tx_aborts_in_flight_audio_engine():
    from services.ft8_service import FT8Service

    class FakeTxEngine:
        def __init__(self):
            self.aborted = False

        def abort(self):
            self.aborted = True

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    fake = FakeTxEngine()
    service.tx_engine = fake
    service.tx_enabled = True
    service.tx_queue.append("A61DI OM0RX JN88")
    service.active_tx_message = "A61DI OM0RX JN88"

    service.halt_tx()

    assert fake.aborted is True
    assert service.tx_enabled is False
    assert service.tx_queue == []
    assert service.tx_status == "halted"


def test_foxhound_hound_frequency_rules_are_enforced():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    class Message:
        message = "OM0RX <DX0FOX> -12"
        freq = 420

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.set_special_activity({"enabled": True, "role": "hound", "submode": "foxhound"})
    service.set_tx_options(tx_audio_frequency=3900)

    assert service.tx_audio_frequency == 3900

    qso = QSOSession(
        their_call="DX0FOX",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )
    asyncio.run(service._update_qso_state(qso, Message()))

    assert service.tx_audio_frequency == 420
    assert qso.state == QSOState.SENDING_REPORT
    assert service.tx_queue == ["DX0FOX OM0RX R-15"]

    service.set_special_activity({"enabled": True, "role": "hound", "submode": "foxhound", "houndTxMax": 3500})
    service.set_tx_options(tx_audio_frequency=3900)
    assert service.tx_audio_frequency == 3500


def test_superfox_automation_is_blocked_until_verified_decode():
    from services.ft8_service import FT8Service

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.set_special_activity({"enabled": True, "role": "hound", "submode": "superfox"})

    try:
        asyncio.run(service.queue_tx_message("DX0FOX OM0RX JN88"))
    except RuntimeError as exc:
        assert "verified SuperFox decode" in str(exc)
    else:
        raise AssertionError("SuperFox queued before verification")

    service.set_special_activity({"enabled": True, "role": "hound", "submode": "superfox", "superfox_verified": True})
    asyncio.run(service.queue_tx_message("DX0FOX OM0RX JN88", automation="auto_call"))

    assert service.tx_queue == ["DX0FOX OM0RX JN88"]


def test_backend_engage_target_atomically_replaces_active_qso_and_queues_tx1():
    from services.ft8_service import FT8Service, QSOSession, QSOState

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.tx_capability_enabled = True
    service.tx_enabled = True
    service.active_qsos["OLD1"] = QSOSession(
        their_call="OLD1",
        my_call="OM0RX",
        my_grid="JN88",
        state=QSOState.WAITING_RESPONSE,
    )
    service.active_tx_message = "OLD1 OM0RX JN88"
    service.tx_queue.append("OLD1 OM0RX JN88")

    message = asyncio.run(service.engage_target({
        "callsign": "EA1AA",
        "grid": "IN83",
        "mode": "FT8",
        "band": "30m",
        "frequency_mhz": 10.136,
        "timestamp": "2026-05-27T00:00:00+00:00",
    }, source="manual_double_click", replace_active=True))

    assert message == "EA1AA OM0RX JN88"
    assert list(service.active_qsos) == ["EA1AA"]
    assert service.tx_queue == ["EA1AA OM0RX JN88"]
    assert service.pending_tx_intent["source"] == "manual_double_click"
    assert service.pending_tx_intent["call"] == "EA1AA"
    assert service.tx_enabled is True
    assert service.auto_sequence is True


def test_backend_engage_endpoint_exists_for_atomic_manual_selection():
    api = read_text("backend/api/ft8.py")
    modal = read_text("frontend/js/ft8-modal.js")

    assert "class AutomationEngageRequest" in api
    assert "@router.post(\"/automation/engage\")" in api
    assert "async def engage_automation_target" in api
    assert "async ft8EngageBackendTarget" in modal
    assert "ft8QueueTxMessage(firstMessage" not in modal


def test_frontend_auto_call_uses_filters_and_real_tx_queue():
    modal = read_text("frontend/js/ft8-modal.js")

    assert "ft8MaybeAutoCall" in modal
    assert "ft8HasActiveQsoAttempt" in modal
    assert "ft8PassesAutomationFilters(message, directedCaller)" in modal
    assert "ft8ShouldAutoRespond(message, meta, spotTargetHeard)" in modal
    assert "ft8MessageIsCallingUs(message)" in modal
    assert "await this.ft8SubmitAutomationTarget(message)" in modal
    assert "await this.ft8ArmAutomationTx()" in modal
    assert "autoCallQueued" in modal
    assert "ft8AutoIgnoreCall(meta.call, 'auto-call')" in modal
    assert "ft8LogCompletedQso" not in modal
    assert "'/api/qso/log'" not in modal
    assert "queue_message:" not in modal


def test_frontend_mode_changes_sync_running_backend_service():
    modal = read_text("frontend/js/ft8-modal.js")

    assert "ft8SyncServiceConfig" in modal
    assert "if (this.ft8.connected)" in modal
    assert "await this.ft8SyncServiceConfig()" in modal


def test_backend_target_enrichment_preserves_grid_hunting_when_status_present():
    from backend.api.ft8 import _enrich_automation_target

    class FakeClassifier:
        async def grid_flags(self, grid, band, mode):
            assert grid == "JO70"
            assert band == "20m"
            assert mode == "FT8"
            return True, True, False

        async def call_status_flags(self, *args, **kwargs):
            raise AssertionError("call status should not be recomputed when status is already present")

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                cty_resolver=None,
                classifier=FakeClassifier(),
            )
        )
    )
    enriched = asyncio.run(_enrich_automation_target(
        {
            "callsign": "OK1ABC",
            "grid": "JO70",
            "band": "20m",
            "mode": "FT8",
            "call_status": "Confirmed",
            "dxcc_status": "Confirmed",
        },
        request,
    ))

    assert enriched["needed"]["grid"] is True
    assert enriched["needed_on_band"]["grid"] is True


def test_backend_decoded_messages_are_enriched_for_automation_targets():
    from services.ft8_rx_decoder import FT8DecodedMessage
    from services.ft8_service import FT8Service

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    service.automation_controller.apply_operator_settings({"automation": {"enabled": True}})

    async def enrich(target):
        assert target["callsign"] == "OK1ABC"
        assert target["grid"] == "JO70"
        assert target["heard"] is True
        return {
            **target,
            "call_status": "New Call",
            "dxcc_status": "ATNO",
        }

    service.on_automation_target_enrich = enrich
    message = FT8DecodedMessage(
        timestamp=datetime.now(timezone.utc),
        message="CQ OK1ABC JO70",
        snr=-8,
        dt=0.2,
        freq=1500,
        mode="FT8",
    )

    asyncio.run(service._handle_decoded_message(message))

    queued = service.automation_controller.status()["targets"][0]
    assert queued["call"] == "OK1ABC"
    assert queued["score"] == 1000
    assert queued["reason"] == "new-dxcc"


def test_auto_call_uses_decoded_slot_timestamp_for_opposite_tx_over():
    from services.ft8_service import FT8Service

    class FakeTxEngine:
        class Status:
            available = True
            reason = "ok"

            def to_dict(self):
                return {"available": True}

        status = Status()

        def abort(self):
            pass

    class Service(FT8Service):
        async def _automation_prepare_radio(self, target):
            self.prepared_target = target

        async def transmit_queued_now_if_possible(self, force_current_slot=False):
            self.transmit_requested = force_current_slot
            return False

    service = Service(mycall="OM0RX", mygrid="JN88")
    service.tx_engine = FakeTxEngine()
    service.tx_capability_enabled = True
    service.enable_tx()
    service.auto_call_enabled = True
    service.auto_call_cq_only = True
    slot_start = datetime(2026, 6, 3, 6, 14, 15, tzinfo=timezone.utc)
    station_was_even = int(slot_start.timestamp() // 15) % 2 == 0
    service.automation_controller.ingest_target({
        "message": "CQ YU7GMN KN05",
        "callsign": "YU7GMN",
        "band": "40m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "timestamp": slot_start.isoformat(),
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    asyncio.run(service._automation_tick())

    assert service.active_tx_message == "YU7GMN OM0RX JN88"
    assert service.tx_even_first is (not station_was_even)
    assert service.pending_tx_intent["scheduled_slot_utc"] is not None
    assert service.pending_tx_intent["heard_slot_utc"] == slot_start.isoformat()
    assert service.transmit_requested is True


def test_auto_call_uses_live_heard_slot_start_for_tx_parity():
    from services.ft8_service import FT8Service

    service = FT8Service(mycall="OM0RX", mygrid="JN88")
    heard_slot = datetime(2026, 6, 3, 10, 17, 15, tzinfo=timezone.utc)
    heard_was_even = int(heard_slot.timestamp() // 15) % 2 == 0

    service._infer_tx_slot_from_target({
        "callsign": "F4IFO",
        "heard_slot_start_at": heard_slot.isoformat(),
        "timestamp": (heard_slot + timedelta(seconds=14)).isoformat(),
    })

    assert service.tx_even_first is (not heard_was_even)
    assert service._desired_tx_cycle_parity() != (0 if heard_was_even else 1)


def test_next_tx_slot_is_forward_and_matches_selected_parity():
    from services.ft8_service import FT8Service

    class ClockedService(FT8Service):
        def __init__(self, now):
            super().__init__(mycall="OM0RX", mygrid="JN88")
            self.clock = now

        def _now(self):
            return self.clock

        def _clock_offset_seconds(self):
            return 0.0

    service = ClockedService(datetime(2026, 6, 3, 10, 17, 17, tzinfo=timezone.utc))
    service.tx_even_first = True

    next_slot = service._next_tx_slot_start()

    assert next_slot == datetime(2026, 6, 3, 10, 17, 30, tzinfo=timezone.utc)
    assert int(next_slot.timestamp() // 15) % 2 == service._desired_tx_cycle_parity()

    service.clock = datetime(2026, 6, 3, 10, 17, 30, 500000, tzinfo=timezone.utc)
    late_slot = service._next_tx_slot_start()

    assert late_slot == datetime(2026, 6, 3, 10, 18, 0, tzinfo=timezone.utc)
    assert int(late_slot.timestamp() // 15) % 2 == service._desired_tx_cycle_parity()


def test_spot_hunt_uses_standard_dial_and_heard_before_call():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")

    assert "ft8ResolveDigitalSpotTuning" in modal
    assert "const deltaHz = Math.round((spotFrequency - standardDial) * 1000000)" in modal
    assert "radioFrequency = standardDial" in modal
    assert "ft8RegisterSpotTarget" in modal
    assert "ft8IsActiveSpotTarget" in modal
    assert "message?.source === 'spot'" in modal
    assert "spotTargetHeard" in modal
    assert "Spot listen s" in template


def test_wsjtz_automation_settings_are_wired_to_runtime_behaviour():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")

    assert "startFT8AutomationTimer" in modal
    assert "ft8RunScheduledAutomation" in modal
    assert "ft8NextAutomationTarget" in modal
    assert "FT8_DEFAULT_BAND_PLAN = '05:20m,17m,15m,12m,10m\\n20:30m,40m,80m,160m'" in modal
    assert "allowedModes: { FT8: true, FT4: true, FT2: false }" in modal
    assert "ft8AutomationAllowedModes" in modal
    assert "ft8AutomationModeAllowed(meta.mode)" in modal
    assert "ft8BuildAutomationCandidates" in modal
    assert "ft8ScoreAutomationCandidate" in modal
    assert "ft8AutomationGoalScore" in modal
    assert "return 1000" in modal
    assert "return 800" in modal
    assert "return 500" in modal
    assert "return 350" in modal
    assert "activeTargets.length * 260" in modal
    assert "best.score >= 175" in modal
    assert "hopIntervalSeconds" in modal
    assert "Hop interval s" in template
    assert "Use FT8" in template
    assert "Use FT4" in template
    assert "Use FT2" in template
    assert "ft8SortDigitalMessages" in modal
    assert "ft8SortAutomationMessages" in modal
    assert "priority === 'signal'" in modal
    assert "priority === 'distance'" in modal
    assert "ft8FindFreeTxOffset" in modal
    assert "ft8MaybeUpdateFreeTxOffset('manual')" in template
    assert "ft8PruneAutoIgnoreList" in modal
    assert "ft8RecordAutoCallAttempt" in modal
    assert "ft8IsAutoCallBackedOff" in modal
    assert "maxAttemptsPerTarget" in modal
    assert "Retry backoff min" in template
    assert "autoIgnoredStations" in modal
    service = read_text("services/ft8_service.py")
    assert "async def _automation_loop" in service
    assert "await self._automation_prepare_radio(target)" in service
    assert "await self.engage_target(" in service
    assert "await asyncio.sleep(0.25)" in service
    assert "or self.auto_call_enabled" in service
    assert "abort_current_attempt" in service
    assert "automation_status" in service


def test_wsjtx_prepare_summary_shows_clear_tx_offset_plan():
    modal = read_text("frontend/js/ft8-modal.js")

    assert "payload.tx_df_plan?.reason" in modal
    assert "payload.tx_df_plan?.occupied" in modal
    assert "TX ${txDf} Hz" in modal
    assert "prepared ${prepared.call}" in modal
    assert "prepared.txDfReason.replace" in modal


def test_special_activity_controls_and_automation_hooks_are_wired():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")
    api = read_text("backend/api/ft8.py")

    assert "ft8DetectSpotSpecialActivity" in modal
    assert "ft8ApplySpecialActivity" in modal
    assert "ft8SpecialActivityAllowsAutoCall" in modal
    assert "ft8IsSuperFoxDecode" in modal
    assert "specialActivity: this.ft8SpecialActivityPayload()" in modal
    assert "SuperFox RX decoder is not available" in modal
    assert "FT8_SF|SF" not in modal
    assert "ft8TxOffsetRange" in modal
    assert "Special Operating Activity" in template
    assert "Fox/Hound" in template
    assert "SuperFox" in template
    assert "specialActivity: Optional[dict[str, Any]]" in api


def test_digital_status_colors_are_configurable():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")
    css = read_text("frontend/ft8-modal.css")
    utils = read_text("frontend/js/utils.js")

    assert "FT8_DEFAULT_STATUS_COLORS" in modal
    assert "statusColors" in modal
    assert "ft8SetStatusColor" in modal
    assert "ft8StatusColor" in modal
    assert "Station Status Colors" in template
    assert "ft8MessageRowStyle" in template
    assert ".ft8-status-color-grid" in css
    assert "getConfiguredStatusColor" in utils
