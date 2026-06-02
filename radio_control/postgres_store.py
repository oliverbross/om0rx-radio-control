"""PostgreSQL connection and schema helpers for OM0RX local data.

The application can run in ``DATABASE_BACKEND=auto`` while a station is being
set up. In auto mode PostgreSQL is used only when a DSN or host/user/database
settings are present; otherwise the legacy local cache remains available.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

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
