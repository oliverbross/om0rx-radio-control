#!/usr/bin/env python3
"""Smoke checks for Wavelog sync pagination and failure status."""

from datetime import datetime
from tempfile import TemporaryDirectory
from pathlib import Path

import _bootstrap  # noqa: F401

from radio_control.wavelog_duckdb_sync import WavelogDuckDBSync
from radio_control import wavelog_duckdb_sync


class FakeWavelogSync(WavelogDuckDBSync):
    def __init__(self, db_path: str, records: list[dict], fail: bool = False):
        self.records = records
        self.fail = fail
        self.fetch_after_ids = []
        super().__init__(db_path)

    def _fetch_changed_records(self, last_modified=None, last_id=None, batch_size=1000):
        if self.fail:
            raise RuntimeError("synthetic sync failure")

        after_id = last_id or 0
        self.fetch_after_ids.append(after_id)
        records = [record for record in self.records if record["COL_PRIMARY_KEY"] > after_id]
        return records[:batch_size]

    def _convert_wavelog_to_duckdb(self, wavelog_record):
        return {"wavelog_id": wavelog_record["COL_PRIMARY_KEY"]}

    def _upsert_record(self, conn, record):
        conn.execute("INSERT INTO qso_records (wavelog_id) VALUES (?)", (record["wavelog_id"],))
        return "added"


def test_initial_sync_uses_keyset_pagination():
    records = [
        {"COL_PRIMARY_KEY": 10, "last_modified": datetime(2026, 1, 1, 12, 0, 0)},
        {"COL_PRIMARY_KEY": 20, "last_modified": datetime(2026, 1, 1, 12, 1, 0)},
        {"COL_PRIMARY_KEY": 30, "last_modified": datetime(2026, 1, 1, 12, 2, 0)},
    ]

    with TemporaryDirectory() as temp_dir:
        sync = FakeWavelogSync(str(Path(temp_dir) / "qso_log.duckdb"), records)
        result = sync.sync(batch_size=2)
        status = sync.get_sync_status()

    assert result["synced"] is True
    assert result["records_added"] == 3
    assert sync.fetch_after_ids == [0, 20]
    assert status["last_wavelog_id"] == 30
    assert status["status"] == "ok"
    assert status["last_sync_error"] is None


def test_sync_failure_is_reported_in_status():
    with TemporaryDirectory() as temp_dir:
        sync = FakeWavelogSync(str(Path(temp_dir) / "qso_log.duckdb"), [], fail=True)
        original_logger_disabled = wavelog_duckdb_sync.logger.disabled
        wavelog_duckdb_sync.logger.disabled = True
        try:
            result = sync.sync(batch_size=2)
        finally:
            wavelog_duckdb_sync.logger.disabled = original_logger_disabled
        status = sync.get_sync_status()

    assert result["synced"] is False
    assert "synthetic sync failure" in result["error"]
    assert status["status"] == "failed"
    assert "synthetic sync failure" in status["last_sync_error"]


if __name__ == "__main__":
    test_initial_sync_uses_keyset_pagination()
    test_sync_failure_is_reported_in_status()
    print("Wavelog sync pagination smoke checks passed")
