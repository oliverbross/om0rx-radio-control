"""Read-only station telemetry, event, and tune-result persistence.

This module deliberately has no dependency on radio drivers or command services.  It
accepts already-normalized observations from a future station coordinator and stores
them in PostgreSQL.  Database failures are reported as values so telemetry loss can
never interfere with station operation.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from radio_control.postgres_store import connect

logger = logging.getLogger(__name__)

DEFAULT_QUERY_LIMIT = 1_000
MAX_QUERY_LIMIT = 5_000
DEFAULT_RETENTION_BATCH_SIZE = 5_000
MAX_RETENTION_BATCH_SIZE = 50_000

ConnectionFactory = Callable[[], AbstractContextManager[object]]


@dataclass(frozen=True, slots=True)
class StationSnapshot:
    """A normalized station observation and its scalar telemetry measurements."""

    observed_at: datetime
    received_at: datetime
    source: str
    quality: str
    stale_after_seconds: float | None
    state: Mapping[str, Any]
    metrics: Mapping[str, float | int | bool | None] = field(default_factory=dict)
    units: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StationEvent:
    """A permanent operator, warning, fault, route, or lifecycle event."""

    occurred_at: datetime
    event_type: str
    severity: str
    source: str
    details: Mapping[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class TuneResult:
    """The permanent outcome of one tune transaction."""

    transaction_id: str
    started_at: datetime
    completed_at: datetime
    outcome: str
    source: str
    route_id: str | None = None
    frequency_hz: int | None = None
    swr_before: float | None = None
    swr_after: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    persisted: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class QueryResult:
    records: list[dict[str, Any]]
    available: bool = True
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RetentionResult:
    telemetry_deleted: int = 0
    snapshots_deleted: int = 0
    available: bool = True
    reason: str | None = None


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS station_state_snapshot (
        id BIGSERIAL PRIMARY KEY,
        observed_at TIMESTAMPTZ NOT NULL,
        received_at TIMESTAMPTZ NOT NULL,
        source TEXT NOT NULL,
        quality TEXT NOT NULL,
        stale_after_seconds DOUBLE PRECISION,
        state JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_station_snapshot_observed
    ON station_state_snapshot(observed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS telemetry_sample (
        id BIGSERIAL PRIMARY KEY,
        snapshot_id BIGINT REFERENCES station_state_snapshot(id) ON DELETE CASCADE,
        observed_at TIMESTAMPTZ NOT NULL,
        received_at TIMESTAMPTZ NOT NULL,
        source TEXT NOT NULL,
        quality TEXT NOT NULL,
        stale_after_seconds DOUBLE PRECISION,
        metric TEXT NOT NULL,
        value DOUBLE PRECISION NOT NULL,
        unit TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_metric_observed
    ON telemetry_sample(metric, observed_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_source_observed
    ON telemetry_sample(source, observed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS station_event (
        id BIGSERIAL PRIMARY KEY,
        occurred_at TIMESTAMPTZ NOT NULL,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        source TEXT NOT NULL,
        correlation_id TEXT,
        details JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_station_event_occurred
    ON station_event(occurred_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_station_event_type_occurred
    ON station_event(event_type, occurred_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS tune_result (
        id BIGSERIAL PRIMARY KEY,
        transaction_id TEXT NOT NULL UNIQUE,
        started_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ NOT NULL,
        outcome TEXT NOT NULL,
        source TEXT NOT NULL,
        route_id TEXT,
        frequency_hz BIGINT,
        swr_before DOUBLE PRECISION,
        swr_after DOUBLE PRECISION,
        details JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tune_result_completed
    ON tune_result(completed_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tune_result_route_frequency
    ON tune_result(route_id, frequency_hz, completed_at DESC)
    """,
)


class StationTelemetryStore:
    """PostgreSQL persistence that fails open with respect to station operation."""

    def __init__(self, connection_factory: ConnectionFactory = connect) -> None:
        self._connect = connection_factory
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def ensure_schema(self) -> PersistenceResult:
        """Create storage tables once, returning a failure value if PostgreSQL is offline."""
        if self._schema_ready:
            return PersistenceResult(True)
        with self._schema_lock:
            if self._schema_ready:
                return PersistenceResult(True)
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        for statement in SCHEMA_STATEMENTS:
                            cur.execute(statement)
                    conn.commit()
            except Exception as exc:
                return self._unavailable("initialize telemetry schema", exc)
            self._schema_ready = True
        return PersistenceResult(True)

    def record_snapshot(self, snapshot: StationSnapshot) -> PersistenceResult:
        """Persist a normalized state snapshot and its finite scalar measurements."""
        schema = self.ensure_schema()
        if not schema.persisted:
            return schema

        observed_at = _as_utc(snapshot.observed_at)
        received_at = _as_utc(snapshot.received_at)
        source = _required_text(snapshot.source, "source")
        quality = _required_text(snapshot.quality, "quality")
        stale_after = _optional_nonnegative(snapshot.stale_after_seconds, "stale_after_seconds")
        state_json = _json(snapshot.state)
        measurements = list(_measurements(snapshot.metrics, snapshot.units))

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO station_state_snapshot (
                            observed_at, received_at, source, quality,
                            stale_after_seconds, state
                        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        RETURNING id
                        """,
                        (
                            observed_at,
                            received_at,
                            source,
                            quality,
                            stale_after,
                            state_json,
                        ),
                    )
                    row = cur.fetchone()
                    snapshot_id = row[0] if row else None
                    if snapshot_id is None:
                        raise RuntimeError("snapshot insert returned no id")
                    for metric, value, unit in measurements:
                        cur.execute(
                            """
                            INSERT INTO telemetry_sample (
                                snapshot_id, observed_at, received_at, source, quality,
                                stale_after_seconds, metric, value, unit
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                snapshot_id,
                                observed_at,
                                received_at,
                                source,
                                quality,
                                stale_after,
                                metric,
                                value,
                                unit,
                            ),
                        )
                conn.commit()
        except Exception as exc:
            return self._unavailable("record station snapshot", exc)
        return PersistenceResult(True)

    def record_event(self, event: StationEvent) -> PersistenceResult:
        """Persist an event; event rows are intentionally excluded from raw retention."""
        schema = self.ensure_schema()
        if not schema.persisted:
            return schema
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO station_event (
                            occurred_at, event_type, severity, source, correlation_id, details
                        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            _as_utc(event.occurred_at),
                            _required_text(event.event_type, "event_type"),
                            _required_text(event.severity, "severity"),
                            _required_text(event.source, "source"),
                            _optional_text(event.correlation_id),
                            _json(event.details),
                        ),
                    )
                conn.commit()
        except Exception as exc:
            return self._unavailable("record station event", exc)
        return PersistenceResult(True)

    def record_tune_result(self, result: TuneResult) -> PersistenceResult:
        """Persist a tune outcome idempotently by transaction id."""
        schema = self.ensure_schema()
        if not schema.persisted:
            return schema
        started_at = _as_utc(result.started_at)
        completed_at = _as_utc(result.completed_at)
        if completed_at < started_at:
            raise ValueError("completed_at must not be before started_at")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO tune_result (
                            transaction_id, started_at, completed_at, outcome, source,
                            route_id, frequency_hz, swr_before, swr_after, details
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (transaction_id) DO NOTHING
                        """,
                        (
                            _required_text(result.transaction_id, "transaction_id"),
                            started_at,
                            completed_at,
                            _required_text(result.outcome, "outcome"),
                            _required_text(result.source, "source"),
                            _optional_text(result.route_id),
                            result.frequency_hz,
                            _optional_finite(result.swr_before, "swr_before"),
                            _optional_finite(result.swr_after, "swr_after"),
                            _json(result.details),
                        ),
                    )
                conn.commit()
        except Exception as exc:
            return self._unavailable("record tune result", exc)
        return PersistenceResult(True)

    def query_telemetry(
        self,
        metric: str,
        start: datetime,
        end: datetime,
        *,
        bucket_seconds: int | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> QueryResult:
        """Read a bounded raw or server-side bucketed metric series."""
        schema = self.ensure_schema()
        if not schema.persisted:
            return QueryResult([], False, schema.reason)
        metric = _required_text(metric, "metric")
        start, end = _time_range(start, end)
        limit = _bounded_limit(limit)
        if bucket_seconds is not None and bucket_seconds <= 0:
            raise ValueError("bucket_seconds must be positive")

        if bucket_seconds:
            sql = """
                SELECT
                    to_timestamp(
                        floor(extract(epoch FROM observed_at) / %s) * %s
                    ) AS bucket_at,
                    metric,
                    min(value), avg(value), max(value), count(*), unit
                FROM telemetry_sample
                WHERE metric = %s AND observed_at >= %s AND observed_at < %s
                GROUP BY bucket_at, metric, unit
                ORDER BY bucket_at ASC
                LIMIT %s
            """
            params = (bucket_seconds, bucket_seconds, metric, start, end, limit)
        else:
            sql = """
                SELECT observed_at, received_at, source, quality,
                       stale_after_seconds, metric, value, unit
                FROM telemetry_sample
                WHERE metric = %s AND observed_at >= %s AND observed_at < %s
                ORDER BY observed_at ASC, id ASC
                LIMIT %s
            """
            params = (metric, start, end, limit)

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
        except Exception as exc:
            reason = self._unavailable("query station telemetry", exc).reason
            return QueryResult([], False, reason)

        if bucket_seconds:
            records = [
                {
                    "observed_at": row[0],
                    "metric": row[1],
                    "min": row[2],
                    "avg": row[3],
                    "max": row[4],
                    "count": row[5],
                    "unit": row[6],
                    "bucket_seconds": bucket_seconds,
                }
                for row in rows
            ]
        else:
            records = [
                {
                    "observed_at": row[0],
                    "received_at": row[1],
                    "source": row[2],
                    "quality": row[3],
                    "stale_after_seconds": row[4],
                    "metric": row[5],
                    "value": row[6],
                    "unit": row[7],
                }
                for row in rows
            ]
        return QueryResult(records)

    def query_events(
        self,
        start: datetime,
        end: datetime,
        *,
        event_type: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> QueryResult:
        """Read a bounded event range for synchronized chart overlays."""
        schema = self.ensure_schema()
        if not schema.persisted:
            return QueryResult([], False, schema.reason)
        start, end = _time_range(start, end)
        limit = _bounded_limit(limit)
        event_type = _optional_text(event_type)
        sql = """
            SELECT occurred_at, event_type, severity, source, correlation_id, details
            FROM station_event
            WHERE occurred_at >= %s AND occurred_at < %s
        """
        params: tuple[Any, ...] = (start, end)
        if event_type:
            sql += " AND event_type = %s"
            params += (event_type,)
        sql += " ORDER BY occurred_at ASC, id ASC LIMIT %s"
        params += (limit,)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
        except Exception as exc:
            reason = self._unavailable("query station events", exc).reason
            return QueryResult([], False, reason)
        return QueryResult(
            [
                {
                    "occurred_at": row[0],
                    "event_type": row[1],
                    "severity": row[2],
                    "source": row[3],
                    "correlation_id": row[4],
                    "details": row[5],
                }
                for row in rows
            ]
        )

    def query_tune_results(
        self,
        start: datetime,
        end: datetime,
        *,
        route_id: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> QueryResult:
        """Read bounded tune history, optionally restricted to one route."""
        schema = self.ensure_schema()
        if not schema.persisted:
            return QueryResult([], False, schema.reason)
        start, end = _time_range(start, end)
        limit = _bounded_limit(limit)
        route_id = _optional_text(route_id)
        sql = """
            SELECT transaction_id, started_at, completed_at, outcome, source,
                   route_id, frequency_hz, swr_before, swr_after, details
            FROM tune_result
            WHERE completed_at >= %s AND completed_at < %s
        """
        params: tuple[Any, ...] = (start, end)
        if route_id:
            sql += " AND route_id = %s"
            params += (route_id,)
        sql += " ORDER BY completed_at ASC, id ASC LIMIT %s"
        params += (limit,)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
        except Exception as exc:
            reason = self._unavailable("query tune results", exc).reason
            return QueryResult([], False, reason)
        return QueryResult(
            [
                {
                    "transaction_id": row[0],
                    "started_at": row[1],
                    "completed_at": row[2],
                    "outcome": row[3],
                    "source": row[4],
                    "route_id": row[5],
                    "frequency_hz": row[6],
                    "swr_before": row[7],
                    "swr_after": row[8],
                    "details": row[9],
                }
                for row in rows
            ]
        )

    def prune_raw_data(
        self,
        *,
        telemetry_days: int = 7,
        snapshot_days: int = 7,
        now: datetime | None = None,
        batch_size: int = DEFAULT_RETENTION_BATCH_SIZE,
    ) -> RetentionResult:
        """Delete one bounded batch of raw data; permanent events/tunes are untouched."""
        if telemetry_days < 1 or snapshot_days < 1:
            raise ValueError("retention days must be positive")
        schema = self.ensure_schema()
        if not schema.persisted:
            return RetentionResult(available=False, reason=schema.reason)
        batch_size = min(max(1, int(batch_size)), MAX_RETENTION_BATCH_SIZE)
        current = _as_utc(now or datetime.now(UTC))
        telemetry_before = current - timedelta(days=telemetry_days)
        snapshot_before = current - timedelta(days=snapshot_days)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM telemetry_sample
                        WHERE id IN (
                            SELECT id FROM telemetry_sample
                            WHERE observed_at < %s
                            ORDER BY observed_at ASC
                            LIMIT %s
                        )
                        """,
                        (telemetry_before, batch_size),
                    )
                    telemetry_deleted = max(0, cur.rowcount)
                    cur.execute(
                        """
                        DELETE FROM station_state_snapshot
                        WHERE id IN (
                            SELECT id FROM station_state_snapshot
                            WHERE observed_at < %s
                            ORDER BY observed_at ASC
                            LIMIT %s
                        )
                        """,
                        (snapshot_before, batch_size),
                    )
                    snapshots_deleted = max(0, cur.rowcount)
                conn.commit()
        except Exception as exc:
            reason = self._unavailable("prune raw station telemetry", exc).reason
            return RetentionResult(available=False, reason=reason)
        return RetentionResult(telemetry_deleted, snapshots_deleted)

    @staticmethod
    def _unavailable(action: str, exc: Exception) -> PersistenceResult:
        reason = f"{action} unavailable: {type(exc).__name__}: {exc}"
        logger.warning("Station persistence degraded: %s", reason)
        return PersistenceResult(False, reason)


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _time_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start, end = _as_utc(start), _as_utc(end)
    if end <= start:
        raise ValueError("end must be after start")
    return start, end


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _optional_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _optional_finite(value: float | int | None, field_name: str) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _optional_nonnegative(value: float | int | None, field_name: str) -> float | None:
    result = _optional_finite(value, field_name)
    if result is not None and result < 0:
        raise ValueError(f"{field_name} must not be negative")
    return result


def _measurements(
    metrics: Mapping[str, float | int | bool | None], units: Mapping[str, str]
) -> Iterator[tuple[str, float, str | None]]:
    for name, raw_value in metrics.items():
        if raw_value is None:
            continue
        metric = _required_text(name, "metric")
        value = _optional_finite(raw_value, f"metric {metric}")
        if value is None:
            continue
        yield metric, value, _optional_text(units.get(name))


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)


def _bounded_limit(limit: int) -> int:
    return min(max(1, int(limit)), MAX_QUERY_LIMIT)
