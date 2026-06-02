"""Persistence for Activity Intelligence."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from radio_control import config
from radio_control.postgres_store import connect as connect_postgres
from radio_control.postgres_store import should_use_postgres

from .adapters import iso_utc, stable_id
from .models import (
    ContestEvent,
    Dxpedition,
    PortableActivation,
    PortableReference,
    RbnSpot,
    SourceSyncState,
    SpaceWeatherSnapshot,
    StationStateSample,
    compact_dict,
)

logger = logging.getLogger(__name__)


def _json(value: Any) -> str:
    return json.dumps(compact_dict(value), ensure_ascii=True, sort_keys=True, default=str)


def _from_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


class _PostgresActivityResult:
    def __init__(self, rows: list[tuple[Any, ...]] | None = None):
        self._rows = rows or []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class _PostgresActivityConnection:
    """Tiny DuckDB-style adapter for the activity repository's simple SQL."""

    def __init__(self):
        self._context = connect_postgres()
        self._conn = self._context.__enter__()

    def execute(self, query: str, params: list[Any] | tuple[Any, ...] | None = None) -> _PostgresActivityResult:
        sql = self._translate_sql(query)
        with self._conn.cursor() as cur:
            cur.execute(sql, params or [])
            rows = cur.fetchall() if cur.description else []
        return _PostgresActivityResult(rows)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._context.__exit__(None, None, None)

    def _translate_sql(self, query: str) -> str:
        sql = query.replace("?", "%s")
        sql = sql.replace("DOUBLE DEFAULT", "DOUBLE PRECISION DEFAULT")
        sql = sql.replace(" DOUBLE,", " DOUBLE PRECISION,")
        sql = sql.replace(" DOUBLE\n", " DOUBLE PRECISION\n")
        sql = sql.replace("INSERT OR IGNORE INTO ai_raw_source_payloads", "INSERT INTO ai_raw_source_payloads")
        if "INSERT INTO ai_raw_source_payloads" in sql and "ON CONFLICT" not in sql:
            sql += " ON CONFLICT (source_id, content_hash) DO NOTHING"
        return sql


class ActivityRepository:
    """Small cache for external source state and normalized activities."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else config.DATA_DIR / "activity_intelligence.duckdb"
        if db_path is None and should_use_postgres():
            self.conn = _PostgresActivityConnection()
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = duckdb.connect(str(self.db_path))
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_source_sync_state (
                source_id VARCHAR PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                last_success_at_utc VARCHAR,
                last_attempt_at_utc VARCHAR,
                last_http_status INTEGER,
                last_error VARCHAR,
                etag VARCHAR,
                last_modified VARCHAR,
                next_allowed_at_utc VARCHAR,
                consecutive_failures INTEGER DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_raw_source_payloads (
                id VARCHAR PRIMARY KEY,
                source_id VARCHAR NOT NULL,
                fetched_at_utc VARCHAR NOT NULL,
                content_hash VARCHAR NOT NULL,
                content_type VARCHAR,
                payload VARCHAR NOT NULL,
                UNIQUE(source_id, content_hash)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_dxpeditions (
                id VARCHAR PRIMARY KEY,
                source_id VARCHAR NOT NULL,
                callsign VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL,
                status VARCHAR,
                start_date_utc VARCHAR,
                end_date_utc VARCHAR,
                last_updated_utc VARCHAR
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_dxpedition_aliases (
                id VARCHAR PRIMARY KEY,
                dxpedition_id VARCHAR NOT NULL,
                alias_call VARCHAR NOT NULL,
                confidence DOUBLE DEFAULT 1.0,
                source VARCHAR,
                UNIQUE(dxpedition_id, alias_call)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_contests (
                id VARCHAR PRIMARY KEY,
                source_id VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                start_utc VARCHAR NOT NULL,
                end_utc VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL,
                last_updated_utc VARCHAR
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_portable_references (
                id VARCHAR PRIMARY KEY,
                program VARCHAR NOT NULL,
                reference VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL,
                last_verified_utc VARCHAR,
                UNIQUE(program, reference)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_portable_activations (
                id VARCHAR PRIMARY KEY,
                program VARCHAR NOT NULL,
                type VARCHAR NOT NULL,
                activator_call VARCHAR NOT NULL,
                references_json VARCHAR NOT NULL,
                frequency_khz DOUBLE,
                mode VARCHAR,
                start_utc VARCHAR,
                end_utc VARCHAR,
                expires_utc VARCHAR,
                source_id VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL,
                last_seen_utc VARCHAR NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_space_weather_snapshots (
                id VARCHAR PRIMARY KEY,
                timestamp_utc VARCHAR NOT NULL,
                kp DOUBLE,
                xray_class VARCHAR,
                raw_json VARCHAR
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_rbn_spots (
                id VARCHAR PRIMARY KEY,
                timestamp_utc VARCHAR NOT NULL,
                spotted_call VARCHAR NOT NULL,
                skimmer_call VARCHAR NOT NULL,
                frequency_khz DOUBLE NOT NULL,
                band VARCHAR,
                mode VARCHAR,
                snr_db DOUBLE,
                speed_wpm DOUBLE,
                cq_flag BOOLEAN,
                payload_json VARCHAR NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_station_state_samples (
                id VARCHAR PRIMARY KEY,
                timestamp_utc VARCHAR NOT NULL,
                frequency_khz DOUBLE,
                mode VARCHAR,
                rotator_bearing_deg DOUBLE,
                antenna_name VARCHAR,
                power_watts DOUBLE,
                tx_state BOOLEAN,
                payload_json VARCHAR NOT NULL
            )
            """
        )
        self.conn.commit()

    def get_source_state(self, source_id: str) -> SourceSyncState:
        row = self.conn.execute(
            """
            SELECT source_id, enabled, last_success_at_utc, last_attempt_at_utc, last_http_status,
                   last_error, etag, last_modified, next_allowed_at_utc, consecutive_failures
            FROM ai_source_sync_state
            WHERE source_id = ?
            """,
            [source_id],
        ).fetchone()
        if not row:
            state = SourceSyncState(source_id=source_id)
            self.upsert_source_state(state)
            return state
        return SourceSyncState(
            source_id=row[0],
            enabled=bool(row[1]),
            last_success_at_utc=row[2],
            last_attempt_at_utc=row[3],
            last_http_status=row[4],
            last_error=row[5],
            etag=row[6],
            last_modified=row[7],
            next_allowed_at_utc=row[8],
            consecutive_failures=int(row[9] or 0),
        )

    def upsert_source_state(self, state: SourceSyncState) -> None:
        self.conn.execute("DELETE FROM ai_source_sync_state WHERE source_id = ?", [state.source_id])
        self.conn.execute(
            """
            INSERT INTO ai_source_sync_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                state.source_id,
                state.enabled,
                state.last_success_at_utc,
                state.last_attempt_at_utc,
                state.last_http_status,
                state.last_error,
                state.etag,
                state.last_modified,
                state.next_allowed_at_utc,
                state.consecutive_failures,
            ],
        )
        self.conn.commit()

    def list_source_states(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT source_id, enabled, last_success_at_utc, last_attempt_at_utc, last_http_status,
                   last_error, etag, last_modified, next_allowed_at_utc, consecutive_failures
            FROM ai_source_sync_state
            ORDER BY source_id
            """
        ).fetchall()
        return [
            compact_dict(
                SourceSyncState(
                    source_id=row[0],
                    enabled=bool(row[1]),
                    last_success_at_utc=row[2],
                    last_attempt_at_utc=row[3],
                    last_http_status=row[4],
                    last_error=row[5],
                    etag=row[6],
                    last_modified=row[7],
                    next_allowed_at_utc=row[8],
                    consecutive_failures=int(row[9] or 0),
                )
            )
            for row in rows
        ]

    def store_raw_payload(self, source_id: str, content_type: str | None, payload: str, fetched_at_utc: str) -> str:
        content_hash = stable_id(payload)
        payload_id = stable_id(source_id, content_hash)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO ai_raw_source_payloads
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [payload_id, source_id, fetched_at_utc, content_hash, content_type, payload],
        )
        self.conn.commit()
        return content_hash

    def prune_raw_payloads(self, keep_days: int) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=max(1, int(keep_days)))
        self.conn.execute(
            "DELETE FROM ai_raw_source_payloads WHERE fetched_at_utc < ?",
            [iso_utc(cutoff)],
        )
        self.conn.commit()

    def delete_current_source_records(self, source_id: str) -> None:
        """Remove current normalized rows for a source before inserting a fresh snapshot."""
        dx_ids = [row[0] for row in self.conn.execute("SELECT id FROM ai_dxpeditions WHERE source_id = ?", [source_id]).fetchall()]
        if dx_ids:
            placeholders = ",".join("?" for _ in dx_ids)
            self.conn.execute(f"DELETE FROM ai_dxpedition_aliases WHERE dxpedition_id IN ({placeholders})", dx_ids)
        self.conn.execute("DELETE FROM ai_dxpeditions WHERE source_id = ?", [source_id])
        self.conn.execute("DELETE FROM ai_contests WHERE source_id = ?", [source_id])
        self.conn.execute("DELETE FROM ai_portable_activations WHERE source_id = ?", [source_id])
        self.conn.execute(
            "DELETE FROM ai_portable_references WHERE payload_json LIKE ?",
            [f'%"source_id": "{source_id}"%'],
        )
        self.conn.commit()

    def upsert_dxpeditions(self, items: list[Dxpedition]) -> None:
        for item in items:
            self.conn.execute("DELETE FROM ai_dxpeditions WHERE id = ?", [item.id])
            self.conn.execute(
                "INSERT INTO ai_dxpeditions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    item.id,
                    item.source_id,
                    item.callsign,
                    _json(item),
                    item.status,
                    item.start_date_utc,
                    item.end_date_utc,
                    item.last_updated_utc,
                ],
            )
            aliases = list(dict.fromkeys([item.callsign, *item.aliases]))
            for alias in aliases:
                alias_id = stable_id(item.id, alias)
                self.conn.execute("DELETE FROM ai_dxpedition_aliases WHERE id = ?", [alias_id])
                self.conn.execute(
                    "INSERT INTO ai_dxpedition_aliases VALUES (?, ?, ?, ?, ?)",
                    [alias_id, item.id, alias.upper(), 1.0, item.source_id],
                )
        self.conn.commit()

    def upsert_contests(self, items: list[ContestEvent]) -> None:
        for item in items:
            self.conn.execute("DELETE FROM ai_contests WHERE id = ?", [item.id])
            self.conn.execute(
                "INSERT INTO ai_contests VALUES (?, ?, ?, ?, ?, ?, ?)",
                [item.id, item.source_id, item.name, item.start_utc, item.end_utc, _json(item), item.last_updated_utc],
            )
        self.conn.commit()

    def upsert_portable_activations(self, items: list[PortableActivation]) -> None:
        for item in items:
            self.conn.execute("DELETE FROM ai_portable_activations WHERE id = ?", [item.id])
            self.conn.execute(
                """
                INSERT INTO ai_portable_activations
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    item.id,
                    item.program,
                    item.type,
                    item.activator_call,
                    _json(item.references),
                    item.frequency_khz,
                    item.mode,
                    item.start_utc,
                    item.end_utc,
                    item.expires_utc,
                    item.source_id,
                    _json(item),
                    item.last_seen_utc,
                ],
            )
        self.conn.commit()

    def upsert_portable_references(self, items: list[PortableReference]) -> None:
        for item in items:
            ref_id = stable_id(item.program, item.reference)
            self.conn.execute(
                "DELETE FROM ai_portable_references WHERE program = ? AND reference = ?",
                [item.program, item.reference],
            )
            self.conn.execute(
                "INSERT INTO ai_portable_references VALUES (?, ?, ?, ?, ?)",
                [ref_id, item.program, item.reference, _json(item), item.last_verified_utc],
            )
        self.conn.commit()

    def upsert_space_weather(self, items: list[SpaceWeatherSnapshot]) -> None:
        for item in items:
            self.conn.execute("DELETE FROM ai_space_weather_snapshots WHERE id = ?", [item.id])
            self.conn.execute(
                "INSERT INTO ai_space_weather_snapshots VALUES (?, ?, ?, ?, ?)",
                [item.id, item.timestamp_utc, item.kp, item.xray_class, _json(item)],
            )
        self.conn.commit()

    def upsert_rbn_spot(self, item: RbnSpot) -> None:
        self.conn.execute("DELETE FROM ai_rbn_spots WHERE id = ?", [item.id])
        self.conn.execute(
            "INSERT INTO ai_rbn_spots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                item.id,
                item.timestamp_utc,
                item.spotted_call,
                item.skimmer_call,
                item.frequency_khz,
                item.band,
                item.mode,
                item.snr_db,
                item.speed_wpm,
                item.cq_flag,
                _json(item),
            ],
        )
        self.conn.commit()

    def upsert_station_state_sample(self, item: StationStateSample) -> None:
        self.conn.execute("DELETE FROM ai_station_state_samples WHERE id = ?", [item.id])
        self.conn.execute(
            """
            INSERT INTO ai_station_state_samples
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item.id,
                item.timestamp_utc,
                item.frequency_khz,
                item.mode,
                item.rotator_bearing_deg,
                item.antenna_name,
                item.power_watts,
                item.tx_state,
                _json(item),
            ],
        )
        self.conn.commit()

    def nearest_station_state(self, timestamp_utc: str, window_seconds: int = 120) -> dict[str, Any] | None:
        if not timestamp_utc:
            return None
        try:
            target = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
        except ValueError:
            return None
        start = iso_utc(target - timedelta(seconds=window_seconds))
        end = iso_utc(target + timedelta(seconds=window_seconds))
        rows = self.conn.execute(
            """
            SELECT timestamp_utc, payload_json FROM ai_station_state_samples
            WHERE timestamp_utc BETWEEN ? AND ?
            ORDER BY timestamp_utc
            """,
            [start, end],
        ).fetchall()
        best: tuple[float, dict[str, Any]] | None = None
        for row in rows:
            try:
                sample_time = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            except ValueError:
                continue
            payload = _from_json(row[1])
            if not payload:
                continue
            distance = abs((sample_time - target).total_seconds())
            if best is None or distance < best[0]:
                best = (distance, payload)
        return best[1] if best else None

    def active_dxpeditions(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT payload_json FROM ai_dxpeditions
            WHERE status IN ('ACTIVE', 'UPCOMING', 'UNKNOWN')
            ORDER BY CASE status WHEN 'ACTIVE' THEN 0 WHEN 'UPCOMING' THEN 1 ELSE 2 END, start_date_utc
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [_from_json(row[0]) for row in rows if _from_json(row[0])]

    def get_dxpedition(self, dxpedition_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload_json FROM ai_dxpeditions WHERE id = ?",
            [dxpedition_id],
        ).fetchone()
        return _from_json(row[0]) if row else None

    def find_dxpedition_by_call(self, callsign: str) -> dict[str, Any] | None:
        call = callsign.upper()
        row = self.conn.execute(
            """
            SELECT d.payload_json
            FROM ai_dxpeditions d
            JOIN ai_dxpedition_aliases a ON d.id = a.dxpedition_id
            WHERE a.alias_call = ?
            ORDER BY CASE d.status WHEN 'ACTIVE' THEN 0 WHEN 'UPCOMING' THEN 1 ELSE 2 END
            LIMIT 1
            """,
            [call],
        ).fetchone()
        return _from_json(row[0]) if row else None

    def current_contests(self, now: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        now = now or iso_utc()
        rows = self.conn.execute(
            """
            SELECT payload_json FROM ai_contests
            WHERE start_utc <= ? AND end_utc >= ?
            ORDER BY end_utc
            LIMIT ?
            """,
            [now, now, limit],
        ).fetchall()
        return [_from_json(row[0]) for row in rows if _from_json(row[0])]

    def get_contest(self, contest_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload_json FROM ai_contests WHERE id = ?",
            [contest_id],
        ).fetchone()
        return _from_json(row[0]) if row else None

    def upcoming_contests(self, limit: int = 80) -> list[dict[str, Any]]:
        now = iso_utc()
        rows = self.conn.execute(
            """
            SELECT payload_json FROM ai_contests
            WHERE end_utc >= ?
            ORDER BY start_utc
            LIMIT ?
            """,
            [now, limit],
        ).fetchall()
        return [_from_json(row[0]) for row in rows if _from_json(row[0])]

    def portable_activations(self, limit: int = 150) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT payload_json FROM ai_portable_activations
            ORDER BY last_seen_utc DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [_from_json(row[0]) for row in rows if _from_json(row[0])]

    def find_portable_by_call_or_ref(self, callsign: str, text: str = "") -> list[dict[str, Any]]:
        call = callsign.upper()
        needle = (text or "").upper()
        if needle:
            tokens = [token for token in needle.split() if token]
            clauses = ["activator_call = ?"]
            params: list[Any] = [call]
            for token in tokens[:6]:
                if isinstance(self.conn, _PostgresActivityConnection):
                    clauses.append("position(? in upper(references_json)) > 0")
                else:
                    clauses.append("contains(upper(references_json), ?)")
                params.append(token)
            rows = self.conn.execute(
                f"""
                SELECT payload_json FROM ai_portable_activations
                WHERE {" OR ".join(clauses)}
                ORDER BY last_seen_utc DESC
                LIMIT 8
                """,
                params,
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT payload_json FROM ai_portable_activations
                WHERE activator_call = ?
                ORDER BY last_seen_utc DESC
                LIMIT 8
                """,
                [call],
            ).fetchall()
        return [_from_json(row[0]) for row in rows if _from_json(row[0])]

    def lookup_reference(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = f"%{query.upper()}%"
        rows = self.conn.execute(
            """
            SELECT payload_json FROM ai_portable_references
            WHERE upper(reference) LIKE ? OR upper(payload_json) LIKE ?
            ORDER BY reference
            LIMIT ?
            """,
            [q, q, limit],
        ).fetchall()
        return [_from_json(row[0]) for row in rows if _from_json(row[0])]

    def latest_space_weather(self) -> dict[str, Any] | None:
        rows = self.conn.execute(
            """
            SELECT raw_json FROM ai_space_weather_snapshots
            ORDER BY timestamp_utc DESC
            LIMIT 25
            """
        ).fetchall()
        merged: dict[str, Any] = {"source_ids": []}
        latest_timestamp = None
        for row in rows:
            payload = _from_json(row[0])
            if not payload:
                continue
            timestamp = payload.get("timestamp_utc")
            if timestamp and latest_timestamp is None:
                latest_timestamp = timestamp
            for key in (
                "kp",
                "xray_class",
                "noaa_r_scale",
                "noaa_g_scale",
                "solar_wind_speed_kms",
                "solar_wind_bz_nt",
                "solar_flux_sfu",
                "drap_affected_frequency_mhz",
            ):
                if merged.get(key) in (None, "", []) and payload.get(key) not in (None, "", []):
                    merged[key] = payload.get(key)
            for source_id in payload.get("source_ids") or []:
                if source_id not in merged["source_ids"]:
                    merged["source_ids"].append(source_id)
        if not latest_timestamp and len(merged) <= 1:
            return None
        merged["timestamp_utc"] = latest_timestamp
        return merged

    def rbn_reports(self, station_calls: list[str], minutes: int = 60, limit: int = 200) -> list[dict[str, Any]]:
        if not station_calls:
            return []
        cutoff = iso_utc(datetime.now(UTC) - timedelta(minutes=max(1, minutes)))
        placeholders = ",".join("?" for _ in station_calls)
        rows = self.conn.execute(
            f"""
            SELECT payload_json FROM ai_rbn_spots
            WHERE timestamp_utc >= ? AND spotted_call IN ({placeholders})
            ORDER BY timestamp_utc DESC
            LIMIT ?
            """,
            [cutoff, *[call.upper() for call in station_calls], limit],
        ).fetchall()
        return [_from_json(row[0]) for row in rows if _from_json(row[0])]

    def rbn_band_report_count(self, station_calls: list[str], band: str, minutes: int = 30) -> int:
        if not station_calls or not band:
            return 0
        cutoff = iso_utc(datetime.now(UTC) - timedelta(minutes=max(1, minutes)))
        placeholders = ",".join("?" for _ in station_calls)
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) FROM ai_rbn_spots
            WHERE timestamp_utc >= ? AND band = ? AND spotted_call IN ({placeholders})
            """,
            [cutoff, band, *[call.upper() for call in station_calls]],
        ).fetchone()
        return int(row[0] or 0) if row else 0

    def close(self) -> None:
        self.conn.close()
