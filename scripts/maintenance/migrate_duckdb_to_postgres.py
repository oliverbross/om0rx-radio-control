"""Migrate legacy DuckDB caches into the PostgreSQL backend.

Run from the project root after configuring POSTGRES_DSN or
POSTGRES_HOST/POSTGRES_DB/POSTGRES_USER in app settings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radio_control import config  # noqa: E402
from radio_control.postgres_store import connect, initialize_schema  # noqa: E402
from activity_intelligence.repository import ActivityRepository  # noqa: E402


SPOT_COLUMNS = [
    "received_at",
    "date_utc",
    "time_utc",
    "frequency_khz",
    "callsign",
    "spotter",
    "comment",
    "band",
    "mode",
    "spot_source",
    "rbl_mode_group",
    "country",
    "zone_cq",
    "zone_itu",
    "continent",
    "special_tags",
    "call_status",
    "dxcc_status",
]

QSO_COLUMNS = [
    "wavelog_id",
    "call",
    "qso_date",
    "time_on",
    "time_off",
    "qso_datetime",
    "mode",
    "submode",
    "frequency",
    "band",
    "rst_sent",
    "rst_rcvd",
    "name",
    "qth",
    "state",
    "county",
    "gridsquare",
    "pota_ref",
    "sota_ref",
    "iota",
    "wwff_ref",
    "sig",
    "sig_info",
    "comment",
    "country",
    "dxcc",
    "cqz",
    "ituz",
    "continent",
    "lotw_qsl_sent",
    "lotw_qsl_rcvd",
    "eqsl_qsl_sent",
    "eqsl_qsl_rcvd",
    "qsl_sent",
    "qsl_rcvd",
    "tx_pwr",
    "operator",
    "station_callsign",
    "station_id",
    "creation_date",
    "last_modified",
]

AI_TABLES = [
    "ai_source_sync_state",
    "ai_raw_source_payloads",
    "ai_dxpeditions",
    "ai_dxpedition_aliases",
    "ai_contests",
    "ai_portable_references",
    "ai_portable_activations",
    "ai_space_weather_snapshots",
    "ai_rbn_spots",
    "ai_station_state_samples",
]


def _table_columns(conn: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    except Exception:
        return set()
    return {str(row[1]) for row in rows}


def _copy_rows(
    *,
    duckdb_path: Path,
    table: str,
    columns: list[str],
    batch_size: int,
    clear: bool,
) -> int:
    if not duckdb_path.exists():
        print(f"skip {table}: {duckdb_path} does not exist")
        return 0

    source = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        available = _table_columns(source, table)
        if not available:
            print(f"skip {table}: table not found in {duckdb_path}")
            return 0
        selected = [column for column in columns if column in available]
        missing = [column for column in columns if column not in available]
        if missing:
            print(f"{table}: {len(missing)} missing legacy columns will be imported as NULL")

        select_exprs = [column if column in available else f"NULL AS {column}" for column in columns]
        total = int(source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        if total <= 0:
            print(f"skip {table}: no rows")
            return 0

        insert_sql = f"""
            INSERT INTO {table} ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
        """
        if table == "qso_records":
            updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns if column != "wavelog_id")
            insert_sql += f" ON CONFLICT (wavelog_id) DO UPDATE SET {updates}, sync_timestamp = now()"

        copied = 0
        with connect() as target:
            with target.cursor() as cur:
                if clear:
                    cur.execute(f"DELETE FROM {table}")
                for offset in range(0, total, batch_size):
                    rows = source.execute(
                        f"""
                        SELECT {", ".join(select_exprs)}
                        FROM {table}
                        ORDER BY id
                        LIMIT ? OFFSET ?
                        """,
                        [batch_size, offset],
                    ).fetchall()
                    if not rows:
                        break
                    cur.executemany(insert_sql, rows)
                    target.commit()
                    copied += len(rows)
                    print(f"{table}: copied {copied}/{total}")
        if selected:
            print(f"{table}: imported columns: {', '.join(selected)}")
        return copied
    finally:
        source.close()


def _copy_sync_metadata(duckdb_path: Path, clear: bool) -> int:
    if not duckdb_path.exists():
        return 0
    source = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        if not _table_columns(source, "sync_metadata"):
            return 0
        rows = source.execute(
            """
            SELECT id, last_sync_timestamp, last_wavelog_modified, last_wavelog_id,
                   total_records_synced, last_sync_added, last_sync_updated
            FROM sync_metadata
            """
        ).fetchall()
        if not rows:
            return 0
        with connect() as target:
            with target.cursor() as cur:
                if clear:
                    cur.execute("DELETE FROM sync_metadata")
                cur.executemany(
                    """
                    INSERT INTO sync_metadata (
                        id, last_sync_timestamp, last_wavelog_modified, last_wavelog_id,
                        total_records_synced, last_sync_added, last_sync_updated
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        last_sync_timestamp = EXCLUDED.last_sync_timestamp,
                        last_wavelog_modified = EXCLUDED.last_wavelog_modified,
                        last_wavelog_id = EXCLUDED.last_wavelog_id,
                        total_records_synced = EXCLUDED.total_records_synced,
                        last_sync_added = EXCLUDED.last_sync_added,
                        last_sync_updated = EXCLUDED.last_sync_updated
                    """,
                    rows,
                )
            target.commit()
        print(f"sync_metadata: copied {len(rows)} rows")
        return len(rows)
    finally:
        source.close()


def _copy_activity_tables(duckdb_path: Path, batch_size: int, clear: bool) -> int:
    if not duckdb_path.exists():
        print(f"skip activity intelligence: {duckdb_path} does not exist")
        return 0
    # Ensure the PostgreSQL activity tables exist.
    ActivityRepository().close()

    copied_total = 0
    source = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        for table in AI_TABLES:
            columns = list(_table_columns(source, table))
            if not columns:
                continue
            info = source.execute(f"PRAGMA table_info('{table}')").fetchall()
            columns = [str(row[1]) for row in info]
            total = int(source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
            if total <= 0:
                continue
            conflict_column = columns[0]
            updates = ", ".join(
                f"{column} = EXCLUDED.{column}" for column in columns if column != conflict_column
            )
            insert_sql = f"""
                INSERT INTO {table} ({", ".join(columns)})
                VALUES ({", ".join(["%s"] * len(columns))})
                ON CONFLICT ({conflict_column}) DO UPDATE SET {updates}
            """
            table_copied = 0
            with connect() as target:
                with target.cursor() as cur:
                    if clear:
                        cur.execute(f"DELETE FROM {table}")
                    for offset in range(0, total, batch_size):
                        rows = source.execute(
                            f"""
                            SELECT {", ".join(columns)}
                            FROM {table}
                            LIMIT ? OFFSET ?
                            """,
                            [batch_size, offset],
                        ).fetchall()
                        if not rows:
                            break
                        cur.executemany(insert_sql, rows)
                        target.commit()
                        table_copied += len(rows)
                copied_total += table_copied
            print(f"{table}: copied {table_copied}/{total}")
        return copied_total
    finally:
        source.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="clear target PostgreSQL rows before importing")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--spots-db", type=Path, default=config.DATA_DIR / "spots.duckdb")
    parser.add_argument("--qso-db", type=Path, default=config.DATA_DIR / "qso_log.duckdb")
    parser.add_argument("--activity-db", type=Path, default=config.DATA_DIR / "activity_intelligence.duckdb")
    args = parser.parse_args(argv)

    initialize_schema()
    spots = _copy_rows(
        duckdb_path=args.spots_db,
        table="spots",
        columns=SPOT_COLUMNS,
        batch_size=max(100, args.batch_size),
        clear=args.clear,
    )
    qsos = _copy_rows(
        duckdb_path=args.qso_db,
        table="qso_records",
        columns=QSO_COLUMNS,
        batch_size=max(100, args.batch_size),
        clear=args.clear,
    )
    sync_rows = _copy_sync_metadata(args.qso_db, clear=args.clear)
    ai_rows = _copy_activity_tables(args.activity_db, batch_size=max(100, args.batch_size), clear=args.clear)
    print(f"done: {spots} spots, {qsos} qso records, {sync_rows} sync metadata rows, {ai_rows} AI rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
