import asyncio
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import _bootstrap  # noqa: F401

from radio_control.qso_outbox import QSOOutbox


class FakeWavelogClient:
    def __init__(self, fail_first=False, duplicate_first=False, unverified_duplicate_first=False):
        self.fail_first = fail_first
        self.duplicate_first = duplicate_first
        self.unverified_duplicate_first = unverified_duplicate_first
        self.submitted = []

    async def submit_adif_string(self, adif_string):
        self.submitted.append(adif_string)
        if self.fail_first and len(self.submitted) == 1:
            return {"success": False, "message": "offline"}
        if self.duplicate_first and len(self.submitted) == 1:
            return {
                "success": False, "duplicate": True, "identity_verified": True,
                "identity": {"call": "OM0RX", "band": "20m", "mode": "FT8"},
            }
        if self.unverified_duplicate_first and len(self.submitted) == 1:
            return {"success": False, "error": "Duplicate for OM0RX"}
        return {"success": True, "message": "ok"}


def sample_qso():
    return {
        "callsign": "OM0RX",
        "frequency": 14.074,
        "mode": "FT8",
        "rst_sent": "-01",
        "rst_received": "-02",
        "band": "20m",
        "date_time": "2026-05-26T04:50:00Z",
        "notes": "outbox smoke test",
    }


def test_qso_outbox_enqueue_deduplicates_and_replays():
    with TemporaryDirectory() as temp_dir:
        outbox = QSOOutbox(Path(temp_dir) / "wavelog_outbox.adif")

        assert outbox.enqueue(sample_qso(), reason="offline")
        assert outbox.enqueue(sample_qso(), reason="offline")
        assert outbox.count() == 1

        import asyncio

        result = asyncio.run(outbox.replay(FakeWavelogClient()))
        assert result["success"] is True
        assert result["uploaded"] == 1
        assert result["remaining"] == 0
        assert outbox.count() == 0


def test_qso_outbox_preserves_legitimate_repeat_contact_45_seconds_later():
    with TemporaryDirectory() as temp_dir:
        outbox = QSOOutbox(Path(temp_dir) / "wavelog_outbox.adif")
        first = (
            "<call:5>M6OTU <qso_date:8>20260605 <time_on:6>104245 "
            "<band:3>12m <mode:3>FT8 <rst_sent:3>-10 <rst_rcvd:3>-07 <eor>"
        )
        second = (
            "<call:5>M6OTU <qso_date:8>20260605 <time_on:6>104330 "
            "<band:3>12m <mode:3>FT8 <rst_sent:3>-11 <rst_rcvd:3>-08 "
            "<comment:18>bridge duplicate <eor>"
        )

        assert outbox.enqueue_adif(first)
        assert outbox.enqueue_adif(second)

        records = outbox.records()
        assert len(records) == 2
        assert "<call:5>M6OTU" in records[0]
        assert "<time_on:6>104245" in records[0]
        assert "<time_on:6>104330" in records[1]


def test_qso_outbox_embeds_full_bridge_replay_identity():
    with TemporaryDirectory() as temp_dir:
        outbox = QSOOutbox(Path(temp_dir) / "wavelog_outbox.adif")
        qso = sample_qso()
        qso.update({
            "provider": "mshv_auto_dx", "station_callsign": "OM0RX",
            "client_id": "MSHV-OM0RX-AUTO-DX", "event_id": "a" * 64,
            "time_on": "104245", "time_off": "104330", "frequency_hz": 24915000,
        })
        assert outbox.enqueue(qso, reason="offline")
        record = outbox.records()[0].lower()
        for field in (
            "app_om0rx_provider", "app_om0rx_station", "app_om0rx_client_id",
            "app_om0rx_event_id", "app_om0rx_time_on", "app_om0rx_time_off",
            "app_om0rx_frequency_hz",
        ):
            assert f"<{field}:" in record


def test_successful_replay_reconstructs_missing_mshv_pending_before_removal(tmp_path, monkeypatch):
    from services import mshv_history

    monkeypatch.setattr(mshv_history, "DELTA_PATH", tmp_path / "deltas.json")
    outbox = QSOOutbox(tmp_path / "outbox.adif")
    adif = (
        "<station_callsign:5>OM0RX <call:5>EA1AA <band:3>20m <freq:6>14.074 "
        "<mode:3>FT8 <qso_date:8>20261004 <time_on:6>120000 <time_off:6>120045 <eor>"
    )
    qso = {
        **sample_qso(), "adif_text": adif, "provider": "mshv_auto_dx",
        "station_callsign": "OM0RX", "client_id": "MSHV-OM0RX-AUTO-DX",
        "event_id": "a" * 64, "time_on": "120000", "time_off": "120045",
        "frequency_hz": 14074000,
    }
    assert outbox.enqueue(qso, reason="offline")

    result = asyncio.run(outbox.replay(FakeWavelogClient()))

    assert result["success"] is True
    assert result["remaining"] == 0
    journal = json.loads((tmp_path / "deltas.json").read_text(encoding="utf-8"))
    assert journal["pending"] == {}
    assert len(journal["records"]) == 1


def test_successful_upload_with_malformed_mshv_identity_retains_outbox(tmp_path, monkeypatch):
    from services import mshv_history

    monkeypatch.setattr(mshv_history, "DELTA_PATH", tmp_path / "deltas.json")
    outbox = QSOOutbox(tmp_path / "outbox.adif")
    adif = (
        "<station_callsign:5>OM0RX <call:5>EA1AA <band:3>20m <freq:6>14.074 "
        "<mode:3>FT8 <qso_date:8>20261004 <time_on:6>120000 <time_off:6>120045 <eor>"
    )
    qso = {
        **sample_qso(), "adif_text": adif, "provider": "mshv_auto_dx",
        "station_callsign": "OM0RX", "client_id": "MSHV-OM0RX-AUTO-DX",
        "event_id": "legacy-event", "time_on": "120000", "time_off": "120045",
        "frequency_hz": 14074000,
    }
    assert outbox.enqueue(qso, reason="offline")
    result = asyncio.run(outbox.replay(FakeWavelogClient()))
    assert result["success"] is False
    assert result["remaining"] == 1
    assert "reconstruction-identity-incomplete" in result["failures"][0]
    assert not (tmp_path / "deltas.json").exists()


def test_qso_outbox_keeps_remaining_records_after_failure():
    with TemporaryDirectory() as temp_dir:
        outbox = QSOOutbox(Path(temp_dir) / "wavelog_outbox.adif")
        assert outbox.enqueue(sample_qso(), reason="offline")

        import asyncio

        result = asyncio.run(outbox.replay(FakeWavelogClient(fail_first=True)))
        assert result["success"] is False
        assert result["uploaded"] == 0
        assert result["remaining"] == 1
        assert outbox.count() == 1


def test_qso_outbox_treats_wavelog_duplicate_as_resolved():
    with TemporaryDirectory() as temp_dir:
        outbox = QSOOutbox(Path(temp_dir) / "wavelog_outbox.adif")
        assert outbox.enqueue(sample_qso(), reason="offline")

        import asyncio

        result = asyncio.run(outbox.replay(FakeWavelogClient(duplicate_first=True)))
        assert result["success"] is True
        assert result["uploaded"] == 0
        assert result["duplicates"] == 1
        assert result["remaining"] == 0
        assert outbox.count() == 0


def test_qso_outbox_does_not_trust_duplicate_substring_without_identity_readback():
    with TemporaryDirectory() as temp_dir:
        outbox = QSOOutbox(Path(temp_dir) / "wavelog_outbox.adif")
        assert outbox.enqueue(sample_qso(), reason="offline")
        import asyncio
        result = asyncio.run(outbox.replay(FakeWavelogClient(unverified_duplicate_first=True)))
        assert result["success"] is False
        assert result["duplicates"] == 0
        assert result["remaining"] == 1


def test_qso_outbox_notifies_when_record_resolves():
    with TemporaryDirectory() as temp_dir:
        outbox = QSOOutbox(Path(temp_dir) / "wavelog_outbox.adif")
        assert outbox.enqueue(sample_qso(), reason="offline")
        resolved = []

        import asyncio

        result = asyncio.run(
            outbox.replay(FakeWavelogClient(), on_resolved_record=resolved.append)
        )

        assert result["success"] is True
        assert result["uploaded"] == 1
        assert len(resolved) == 1
        assert "<call:5>OM0RX" in resolved[0]


def test_qso_outbox_keeps_record_when_history_acknowledgement_fails(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        outbox = QSOOutbox(Path(temp_dir) / "wavelog_outbox.adif")
        assert outbox.enqueue(sample_qso(), reason="offline")
        monkeypatch.setattr(
            outbox, "_acknowledge_mshv_history",
            lambda _record: (_ for _ in ()).throw(RuntimeError("history journal unavailable")),
        )
        import asyncio
        result = asyncio.run(outbox.replay(FakeWavelogClient()))
        assert result["success"] is False
        assert result["remaining"] == 1
        assert "history acknowledgement failed" in result["failures"][0].lower()


if __name__ == "__main__":
    test_qso_outbox_enqueue_deduplicates_and_replays()
    test_qso_outbox_keeps_remaining_records_after_failure()
    test_qso_outbox_treats_wavelog_duplicate_as_resolved()
    test_qso_outbox_notifies_when_record_resolves()
    print("qso outbox smoke checks passed")
