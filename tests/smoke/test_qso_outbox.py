from pathlib import Path
from tempfile import TemporaryDirectory

import _bootstrap  # noqa: F401

from radio_control.qso_outbox import QSOOutbox


class FakeWavelogClient:
    def __init__(self, fail_first=False, duplicate_first=False):
        self.fail_first = fail_first
        self.duplicate_first = duplicate_first
        self.submitted = []

    async def submit_adif_string(self, adif_string):
        self.submitted.append(adif_string)
        if self.fail_first and len(self.submitted) == 1:
            return {"success": False, "message": "offline"}
        if self.duplicate_first and len(self.submitted) == 1:
            return {
                "success": False,
                "message": "Wavelog API error: 400",
                "error": "Date/Time: 2026-05-26 04:50:00 Callsign: OM0RX Band: 20m Duplicate for OM0RX",
            }
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


def test_qso_outbox_deduplicates_same_contact_from_multiple_log_paths():
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
        assert len(records) == 1
        assert "<call:5>M6OTU" in records[0]
        assert "<time_on:6>104245" in records[0]


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


if __name__ == "__main__":
    test_qso_outbox_enqueue_deduplicates_and_replays()
    test_qso_outbox_keeps_remaining_records_after_failure()
    test_qso_outbox_treats_wavelog_duplicate_as_resolved()
    test_qso_outbox_notifies_when_record_resolves()
    print("qso outbox smoke checks passed")
