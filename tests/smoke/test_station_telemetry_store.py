from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from radio_control.station_telemetry_store import (
    MAX_QUERY_LIMIT,
    StationEvent,
    StationSnapshot,
    StationTelemetryStore,
    TuneResult,
)


NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=None):
        self.connection.executed.append((" ".join(sql.split()), params))
        self.rowcount = self.connection.rowcounts.pop(0) if self.connection.rowcounts else 0

    def fetchone(self):
        return self.connection.fetchone_rows.pop(0) if self.connection.fetchone_rows else None

    def fetchall(self):
        return self.connection.fetchall_rows.pop(0) if self.connection.fetchall_rows else []


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.fetchone_rows = []
        self.fetchall_rows = []
        self.rowcounts = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def connection_factory(connection):
    @contextmanager
    def factory():
        yield connection

    return factory


def ready_store(connection):
    store = StationTelemetryStore(connection_factory(connection))
    store._schema_ready = True
    return store


def test_schema_contains_normalized_persistence_entities_and_indexes():
    connection = FakeConnection()
    store = StationTelemetryStore(connection_factory(connection))

    result = store.ensure_schema()

    sql = " ".join(statement for statement, _params in connection.executed)
    assert result.persisted is True
    assert "CREATE TABLE IF NOT EXISTS station_state_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS telemetry_sample" in sql
    assert "CREATE TABLE IF NOT EXISTS station_event" in sql
    assert "CREATE TABLE IF NOT EXISTS tune_result" in sql
    assert "idx_telemetry_metric_observed" in sql
    assert connection.commits == 1


def test_snapshot_stores_state_and_scalar_metrics_with_freshness_metadata():
    connection = FakeConnection()
    connection.fetchone_rows = [(42,)]
    store = ready_store(connection)

    result = store.record_snapshot(
        StationSnapshot(
            observed_at=NOW,
            received_at=NOW + timedelta(milliseconds=20),
            source="kat500",
            quality="measured",
            stale_after_seconds=3,
            state={"mode": "AUTO", "antenna": 2},
            metrics={"swr": 1.28, "forward_w": 100, "unknown": None},
            units={"swr": "ratio", "forward_w": "W"},
        )
    )

    assert result.persisted is True
    assert len(connection.executed) == 3
    snapshot_sql, snapshot_params = connection.executed[0]
    assert "INSERT INTO station_state_snapshot" in snapshot_sql
    assert snapshot_params[2:5] == ("kat500", "measured", 3.0)
    assert snapshot_params[5] == '{"antenna":2,"mode":"AUTO"}'
    metric_params = [params for _sql, params in connection.executed[1:]]
    assert metric_params[0][-3:] == ("swr", 1.28, "ratio")
    assert metric_params[1][-3:] == ("forward_w", 100.0, "W")
    assert connection.commits == 1


def test_event_and_tune_result_are_permanent_idempotent_records():
    connection = FakeConnection()
    store = ready_store(connection)

    event_result = store.record_event(
        StationEvent(NOW, "route_changed", "info", "coordinator", {"route": "40m"}, "tx-1")
    )
    tune_result = store.record_tune_result(
        TuneResult(
            transaction_id="tune-1",
            started_at=NOW,
            completed_at=NOW + timedelta(seconds=2),
            outcome="matched",
            source="coordinator",
            route_id="40m",
            frequency_hz=7_074_000,
            swr_before=2.4,
            swr_after=1.2,
            details={"memory_stored": True},
        )
    )

    assert event_result.persisted is True
    assert tune_result.persisted is True
    tune_sql, tune_params = connection.executed[1]
    assert "ON CONFLICT (transaction_id) DO NOTHING" in tune_sql
    assert tune_params[0] == "tune-1"
    assert tune_params[7:9] == (2.4, 1.2)


def test_database_failure_degrades_without_raising_or_retrying_device_work():
    attempts = 0

    @contextmanager
    def offline_database():
        nonlocal attempts
        attempts += 1
        raise OSError("postgres offline")
        yield

    store = StationTelemetryStore(offline_database)
    result = store.record_event(StationEvent(NOW, "fault", "error", "kpa500"))
    query = store.query_events(NOW - timedelta(hours=1), NOW)

    assert result.persisted is False
    assert "postgres offline" in result.reason
    assert query.available is False
    assert query.records == []
    assert attempts == 2


def test_telemetry_queries_are_capped_and_support_server_side_buckets():
    connection = FakeConnection()
    connection.fetchall_rows = [
        [(NOW, "swr", 1.1, 1.2, 1.3, 4, "ratio")],
    ]
    store = ready_store(connection)

    result = store.query_telemetry(
        "swr",
        NOW - timedelta(hours=1),
        NOW,
        bucket_seconds=60,
        limit=MAX_QUERY_LIMIT + 999,
    )

    sql, params = connection.executed[0]
    assert "floor(extract(epoch FROM observed_at) / %s)" in sql
    assert params == (60, 60, "swr", NOW - timedelta(hours=1), NOW, MAX_QUERY_LIMIT)
    assert result.available is True
    assert result.records[0]["avg"] == 1.2
    assert result.records[0]["bucket_seconds"] == 60


def test_tune_history_query_is_bounded_and_route_filterable():
    connection = FakeConnection()
    connection.fetchall_rows = [
        [
            (
                "tune-1",
                NOW - timedelta(seconds=2),
                NOW,
                "matched",
                "coordinator",
                "40m",
                7_074_000,
                2.4,
                1.2,
                {"memory_stored": True},
            )
        ]
    ]
    store = ready_store(connection)

    result = store.query_tune_results(
        NOW - timedelta(hours=1), NOW + timedelta(seconds=1), route_id="40m", limit=10
    )

    sql, params = connection.executed[0]
    assert "AND route_id = %s" in sql
    assert params[-2:] == ("40m", 10)
    assert result.records[0]["transaction_id"] == "tune-1"
    assert result.records[0]["swr_after"] == 1.2


def test_retention_is_batched_and_does_not_delete_events_or_tune_results():
    connection = FakeConnection()
    connection.rowcounts = [12, 5]
    store = ready_store(connection)

    result = store.prune_raw_data(
        telemetry_days=2,
        snapshot_days=3,
        now=NOW,
        batch_size=100,
    )

    sql = " ".join(statement for statement, _params in connection.executed)
    assert result.telemetry_deleted == 12
    assert result.snapshots_deleted == 5
    assert "DELETE FROM telemetry_sample" in sql
    assert "DELETE FROM station_state_snapshot" in sql
    assert "DELETE FROM station_event" not in sql
    assert "DELETE FROM tune_result" not in sql
    assert connection.executed[0][1] == (NOW - timedelta(days=2), 100)
    assert connection.executed[1][1] == (NOW - timedelta(days=3), 100)
