"""Contracts for the native MSHV KPA/KAT station panel."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/build/mshv-auto-dx/src/MSHV_2762/src"


def test_panel_uses_read_only_telemetry_and_guarded_actions():
    panel = (SOURCE / "HvTxW/om0rxstationpanel.h").read_text(encoding="utf-8")
    assert 'endpoint("/api/elecraft/status")' in panel
    assert 'endpoint("/api/station/state")' in panel
    assert 'endpoint("/api/station/actions/" + action)' in panel
    assert '/api/elecraft/kpa500/operate' not in panel
    assert 'qgetenv("OM0RX_CONTROL_TOKEN")' in panel
    assert 'url.host() == "127.0.0.1" || url.host() == "localhost"' in panel
    assert 'action == "operate" || action == "prepare-route"' in panel


def test_panel_shows_rf_kpa_kat_and_locks_controls_during_rf():
    panel = (SOURCE / "HvTxW/om0rxstationpanel.h").read_text(encoding="utf-8")
    tx = (SOURCE / "HvTxW/hvtxw.cpp").read_text(encoding="utf-8")
    for label in ("STATION RF", "RF:", "KPA:", "KAT:", "KPA ON", "KPA OFF"):
        assert label in panel
    assert 'pa.value("output_power_w")' in panel
    assert 'tuner.value("swr")' in panel
    assert "!actionInFlight && !transmitting" in panel
    assert 'V_dt->addWidget(new Om0rxStationPanel(dsty))' in tx


def test_panel_actions_have_bounded_network_requests():
    panel = (SOURCE / "HvTxW/om0rxstationpanel.h").read_text(encoding="utf-8")
    assert "QTimer::singleShot(2500, reply" in panel
    assert "QTimer::singleShot(75000, reply" in panel
    assert "requestInFlight" in panel
    assert "actionInFlight" in panel


def test_mshv_does_not_override_station_managed_flex_drive_on_connect():
    network = (SOURCE / "HvRigControl/HvRigCat/network/network.cpp").read_text(
        encoding="utf-8"
    )
    assert 'writeData("PC050;"' not in network
    assert "RF drive is owned by the OM0RX station coordinator" in network
