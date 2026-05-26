from pathlib import Path
from tempfile import TemporaryDirectory

import _bootstrap  # noqa: F401

from radio_control.qso_outbox import QSOOutbox


class FakeWavelogClient:
    def __init__(self, fail_first=False):
        self.fail_first = fail_first
        self.submitted = []

    async def submit_adif_string(self, adif_string):
        self.submitted.append(adif_string)
        if self.fail_first and len(self.submitted) == 1:
            return {"success": False, "message": "offline"}
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


if __name__ == "__main__":
    test_qso_outbox_enqueue_deduplicates_and_replays()
    test_qso_outbox_keeps_remaining_records_after_failure()
    print("qso outbox smoke checks passed")
