import asyncio
from types import SimpleNamespace

import _bootstrap  # noqa: F401

from backend.api.spots import SpotTuneRequest, add_spot_to_radio, tune_to_spot
import services.websocket as websocket_module
import services.wsjtx as wsjtx_module


def _request_for(flex):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(flex=flex)))


def test_spot_qsy_halts_wsjtx_and_dekeys_radio_before_tuning(monkeypatch):
    events = []

    class FakeWsjtx:
        def get_bridge_status(self):
            return {
                "stats": {
                    "lastStatus": {
                        "dialFrequency": 21_074_000,
                        "txEnabled": False,
                        "transmitting": True,
                    }
                }
            }

        def send_bridge_command(self, command, payload):
            events.append(("wsjtx", command, payload))
            return {"success": True}

    class FakeFlex:
        current_freq = 21.074
        current_mox = True

        def set_mox(self, enabled):
            events.append(("mox", enabled))
            self.current_mox = enabled
            return True

        def tune_mhz(self, frequency):
            events.append(("tune", frequency))
            self.current_freq = frequency
            return True

        def set_mode(self, mode):
            events.append(("mode", mode))
            return True

    async def fake_broadcast(payload):
        events.append(("broadcast", payload))

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FakeWsjtx())
    monkeypatch.setattr(websocket_module, "broadcast_status", fake_broadcast)

    result = asyncio.run(
        tune_to_spot(
            SpotTuneRequest(frequency=24.915, mode="FT8", callsign="EL2BG"),
            _request_for(FakeFlex()),
        )
    )

    assert events[:4] == [
        ("wsjtx", "halt_tx", {"autoOnly": False, "reason": "radio-qsy"}),
        ("mox", False),
        ("tune", 24.915),
        ("mode", "DIGU"),
    ]
    assert result["tx_interlock"] == {
        "frequency_changed": True,
        "wsjtx_halted": True,
        "radio_dekeyed": True,
    }


def test_add_to_radio_adds_panadapter_marker_without_retuning():
    calls = []

    class FakeFlex:
        def add_spot(self, *args):
            calls.append(args)
            return True

        def tune_mhz(self, _frequency):
            raise AssertionError("add-to-radio must never retune the receiver")

    result = asyncio.run(
        add_spot_to_radio(
            SpotTuneRequest(
                frequency=24.915,
                mode="FT8",
                callsign="EL2BG",
                spotter="OM0RX-#",
                source="rbl",
                comment="RBN FT8 -10 dB",
            ),
            _request_for(FakeFlex()),
        )
    )

    assert calls == [
        (24.915, "EL2BG", "DIGU", "rbl", "OM0RX-#", "RBN FT8 -10 dB")
    ]
    assert result == {"success": True, "mode": "DIGU", "tuned": False}
