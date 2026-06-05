"""PostgreSQL connection and schema helpers for OM0RX local data.

The application can run in ``DATABASE_BACKEND=auto`` while a station is being
set up. In auto mode PostgreSQL is used only when a DSN or host/user/database
settings are present; otherwise the legacy local cache remains available.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from radio_control import config

logger = logging.getLogger(__name__)


def get_database_backend() -> str:
    return str(getattr(config, "DATABASE_BACKEND", "auto") or "auto").strip().lower()


def get_postgres_dsn() -> str:
    explicit = str(getattr(config, "POSTGRES_DSN", "") or "").strip()
    if explicit:
        return explicit

    host = str(getattr(config, "POSTGRES_HOST", "") or "").strip()
    dbname = str(getattr(config, "POSTGRES_DB", "") or "").strip()
    user = str(getattr(config, "POSTGRES_USER", "") or "").strip()
    password = str(getattr(config, "POSTGRES_PASSWORD", "") or "")
    port = int(getattr(config, "POSTGRES_PORT", 5432) or 5432)
    if not host or not dbname or not user:
        return ""

    # Keyword DSN avoids URL escaping issues with special characters.
    parts = [f"host={host}", f"port={port}", f"dbname={dbname}", f"user={user}"]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


def get_postgres_dsn_from_values(values: dict[str, Any]) -> str:
    """Build a PostgreSQL DSN from config-like values without reading global config."""
    explicit = str(values.get("POSTGRES_DSN", "") or "").strip()
    if explicit:
        return explicit

    host = str(values.get("POSTGRES_HOST", "") or "").strip()
    dbname = str(values.get("POSTGRES_DB", "") or "").strip()
    user = str(values.get("POSTGRES_USER", "") or "").strip()
    password = str(values.get("POSTGRES_PASSWORD", "") or "")
    try:
        port = int(values.get("POSTGRES_PORT", 5432) or 5432)
    except (TypeError, ValueError):
        port = 5432
    if not host or not dbname or not user:
        return ""

    parts = [f"host={host}", f"port={port}", f"dbname={dbname}", f"user={user}"]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


def should_use_postgres() -> bool:
    backend = get_database_backend()
    if backend in {"postgres", "postgresql"}:
        return True
    if backend in {"duckdb", "legacy"}:
        return False
    return bool(get_postgres_dsn())


def require_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL backend requires psycopg. Install dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc
    return psycopg


@contextmanager
def connect() -> Iterator[object]:
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError(
            "PostgreSQL is selected but POSTGRES_DSN or POSTGRES_HOST/DB/USER is not configured."
        )
    psycopg = require_psycopg()
    conn = psycopg.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def test_connection(dsn: str | None = None, timeout_seconds: int = 5) -> dict[str, Any]:
    """Open a short PostgreSQL connection and return sanitized server metadata."""
    conninfo = dsn if dsn is not None else get_postgres_dsn()
    if not conninfo:
        raise RuntimeError(
            "POSTGRES_DSN or POSTGRES_HOST/POSTGRES_DB/POSTGRES_USER is not configured."
        )

    psycopg = require_psycopg()
    started = time.perf_counter()
    conn = psycopg.connect(conninfo, connect_timeout=timeout_seconds)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT current_database(), current_user,
                       inet_server_addr()::text, inet_server_port(),
                       current_setting('server_version')
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()

    return {
        "database": row[0] if row else None,
        "user": row[1] if row else None,
        "server_addr": row[2] if row else None,
        "server_port": row[3] if row else None,
        "server_version": row[4] if row else None,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def initialize_schema() -> None:
    """Create the shared PostgreSQL schema used by operational local data."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS spots (
                    id BIGSERIAL PRIMARY KEY,
                    received_at TIMESTAMPTZ NOT NULL,
                    date_utc DATE NOT NULL,
                    time_utc TIME NOT NULL,
                    frequency_khz DOUBLE PRECISION NOT NULL CHECK (frequency_khz > 0),
                    callsign TEXT NOT NULL CHECK (length(callsign) > 0),
                    spotter TEXT NOT NULL CHECK (length(spotter) > 0),
                    comment TEXT,
                    band TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    spot_source TEXT DEFAULT 'cluster',
                    rbl_mode_group TEXT,
                    country TEXT,
                    zone_cq INTEGER,
                    zone_itu INTEGER,
                    continent TEXT,
                    special_tags TEXT,
                    call_status TEXT DEFAULT 'Unknown',
                    dxcc_status TEXT DEFAULT 'Unknown',
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_spot_received ON spots(received_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_spot_source ON spots(spot_source)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_spot_band ON spots(band)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_spot_mode ON spots(mode)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_spot_callsign ON spots(upper(callsign))")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_spot_band_mode ON spots(band, mode)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_spot_status ON spots(call_status, dxcc_status)")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS qso_records (
                    id BIGSERIAL PRIMARY KEY,
                    wavelog_id BIGINT UNIQUE,
                    call TEXT,
                    qso_date TEXT,
                    time_on TIMESTAMP,
                    time_off TIMESTAMP,
                    qso_datetime TIMESTAMP,
                    mode TEXT,
                    submode TEXT,
                    frequency DOUBLE PRECISION,
                    band TEXT,
                    rst_sent TEXT,
                    rst_rcvd TEXT,
                    name TEXT,
                    qth TEXT,
                    state TEXT,
                    county TEXT,
                    gridsquare TEXT,
                    pota_ref TEXT,
                    sota_ref TEXT,
                    iota TEXT,
                    wwff_ref TEXT,
                    sig TEXT,
                    sig_info TEXT,
                    comment TEXT,
                    country TEXT,
                    dxcc INTEGER,
                    cqz INTEGER,
                    ituz INTEGER,
                    continent TEXT,
                    lotw_qsl_sent TEXT,
                    lotw_qsl_rcvd TEXT,
                    eqsl_qsl_sent TEXT,
                    eqsl_qsl_rcvd TEXT,
                    qsl_sent TEXT,
                    qsl_rcvd TEXT,
                    tx_pwr DOUBLE PRECISION,
                    operator TEXT,
                    station_callsign TEXT,
                    station_id INTEGER,
                    creation_date TIMESTAMP,
                    last_modified TIMESTAMP,
                    sync_timestamp TIMESTAMP DEFAULT now()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_wavelog_id ON qso_records(wavelog_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_call ON qso_records(upper(call))")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_date ON qso_records(qso_date)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_band ON qso_records(band)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_mode ON qso_records(mode)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_dxcc ON qso_records(dxcc)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_dxcc_band_mode ON qso_records(dxcc, band, mode)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_datetime ON qso_records(qso_datetime DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_qso_last_modified ON qso_records(last_modified)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_pg_qso_call_band_mode ON qso_records(upper(call), band, mode)"
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS digital_targets (
                    key TEXT PRIMARY KEY,
                    call TEXT NOT NULL CHECK (length(call) > 0),
                    target_id TEXT,
                    command_id TEXT,
                    band TEXT,
                    mode TEXT NOT NULL DEFAULT 'FT8',
                    source TEXT NOT NULL DEFAULT 'decoded',
                    message TEXT,
                    grid TEXT,
                    country TEXT,
                    dxcc INTEGER,
                    continent TEXT,
                    cq_zone TEXT,
                    itu_zone TEXT,
                    call_status TEXT DEFAULT 'Unknown',
                    dxcc_status TEXT DEFAULT 'Unknown',
                    status_source TEXT,
                    need_reasons TEXT[],
                    reference_items TEXT,
                    score INTEGER DEFAULT 0,
                    snr DOUBLE PRECISION,
                    audio_offset INTEGER,
                    dial_frequency DOUBLE PRECISION,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ,
                    first_heard_at TIMESTAMPTZ,
                    last_heard_at TIMESTAMPTZ,
                    heard_slot_start_at TIMESTAMPTZ,
                    last_attempt_at TIMESTAMPTZ,
                    backoff_until TIMESTAMPTZ,
                    attempts INTEGER DEFAULT 0,
                    state TEXT DEFAULT 'queued',
                    lifecycle TEXT DEFAULT 'queued',
                    active_state TEXT DEFAULT 'idle',
                    reason TEXT,
                    skip_reason TEXT,
                    completion_reason TEXT,
                    heard BOOLEAN DEFAULT false,
                    direct_caller BOOLEAN DEFAULT false,
                    last_command_at TIMESTAMPTZ
                )
                """
            )
            for column, definition in (
                ("target_id", "TEXT"),
                ("command_id", "TEXT"),
                ("need_reasons", "TEXT[]"),
                ("reference_items", "TEXT"),
                ("lifecycle", "TEXT DEFAULT 'queued'"),
                ("active_state", "TEXT DEFAULT 'idle'"),
                ("skip_reason", "TEXT"),
                ("completion_reason", "TEXT"),
                ("direct_caller", "BOOLEAN DEFAULT false"),
                ("last_command_at", "TIMESTAMPTZ"),
            ):
                cur.execute(f"ALTER TABLE digital_targets ADD COLUMN IF NOT EXISTS {column} {definition}")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_digital_targets_updated ON digital_targets(updated_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_digital_targets_call ON digital_targets(upper(call))")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_digital_targets_state ON digital_targets(state)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_digital_targets_lifecycle ON digital_targets(lifecycle)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_digital_targets_direct ON digital_targets(direct_caller)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_digital_targets_source ON digital_targets(source)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pg_digital_targets_band_mode ON digital_targets(band, mode)")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    id INTEGER PRIMARY KEY,
                    last_sync_timestamp TIMESTAMP,
                    last_wavelog_modified TIMESTAMP,
                    last_wavelog_id BIGINT,
                    total_records_synced INTEGER,
                    last_sync_added INTEGER,
                    last_sync_updated INTEGER
                )
                """
            )
        conn.commit()
    logger.info("✅ PostgreSQL schema initialized")
