"""Wavelog to PostgreSQL read-cache synchronization."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Dict, Optional

import pymysql
from pymysql.cursors import DictCursor

from radio_control import config
from radio_control.postgres_store import connect, initialize_schema
from radio_control.wavelog_duckdb_sync import WavelogDuckDBSync

logger = logging.getLogger(__name__)


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


class PostgresWavelogSync(WavelogDuckDBSync):
    """Manage synchronization from Wavelog MySQL to the PostgreSQL read cache."""

    def __init__(self):
        self.wavelog_config = {
            "host": config.DB_HOST,
            "port": config.DB_PORT,
            "user": config.DB_USER,
            "password": config.DB_PASS,
            "database": config.DB_NAME,
            "charset": "utf8mb4",
            "cursorclass": DictCursor,
        }
        self.station_id = int(getattr(config, "WAVELOG_STATION_ID", 1))
        self.last_sync_error: Optional[str] = None
        self._db_lock = threading.RLock()
        self._sync_active = False
        self._cached_status: Dict[str, Any] = {
            "initialized": False,
            "status": "not_initialized",
            "last_sync_error": None,
            "total_records": 0,
            "message": "Sync not yet initialized",
        }
        initialize_schema()
        logger.info("✅ Wavelog→PostgreSQL Sync initialized - Station ID: %s", self.station_id)

    def _get_wavelog_connection(self):
        try:
            return pymysql.connect(**self.wavelog_config)
        except Exception as exc:
            logger.error("❌ Failed to connect to Wavelog database: %s", exc)
            raise

    def _get_sync_metadata(self, conn) -> Optional[Dict[str, Any]]:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM sync_metadata WHERE id = 1")
                row = cur.fetchone()
            if not row:
                return None
            return {
                "last_sync_timestamp": row[1],
                "last_wavelog_modified": row[2],
                "last_wavelog_id": row[3],
                "total_records_synced": row[4],
                "last_sync_added": row[5],
                "last_sync_updated": row[6],
            }
        except Exception as exc:
            logger.warning("⚠️ Could not retrieve sync metadata: %s", exc)
            return None

    def _update_sync_metadata(
        self,
        conn,
        last_modified: datetime,
        last_id: int,
        total_records: int,
        added: int,
        updated: int,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sync_metadata (
                    id, last_sync_timestamp, last_wavelog_modified, last_wavelog_id,
                    total_records_synced, last_sync_added, last_sync_updated
                )
                VALUES (1, now(), %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    last_sync_timestamp = now(),
                    last_wavelog_modified = EXCLUDED.last_wavelog_modified,
                    last_wavelog_id = EXCLUDED.last_wavelog_id,
                    total_records_synced = EXCLUDED.total_records_synced,
                    last_sync_added = EXCLUDED.last_sync_added,
                    last_sync_updated = EXCLUDED.last_sync_updated
                """,
                (last_modified, last_id, total_records, added, updated),
            )
        conn.commit()

    def _upsert_record(self, conn, record: Dict[str, Any]) -> str:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM qso_records WHERE wavelog_id = %s", (record["wavelog_id"],))
            exists = cur.fetchone() is not None
            update_assignments = ", ".join(
                f"{column} = EXCLUDED.{column}" for column in QSO_COLUMNS if column != "wavelog_id"
            )
            cur.execute(
                f"""
                INSERT INTO qso_records ({", ".join(QSO_COLUMNS)})
                VALUES ({", ".join(["%s"] * len(QSO_COLUMNS))})
                ON CONFLICT (wavelog_id) DO UPDATE SET
                    {update_assignments},
                    sync_timestamp = now()
                """,
                tuple(record.get(column) for column in QSO_COLUMNS),
            )
        return "updated" if exists else "added"

    def sync(self, batch_size: int = 1000) -> Dict[str, Any]:
        self._sync_active = True
        try:
            with self._db_lock, connect() as conn:
                metadata = self._get_sync_metadata(conn)
                last_modified = metadata["last_wavelog_modified"] if metadata else None
                last_id = metadata["last_wavelog_id"] if metadata else None

                is_initial_sync = last_modified is None
                added_count = 0
                updated_count = 0
                latest_modified = last_modified
                latest_id = last_id or 0
                initial_cursor_id = last_id or 0
                batch_num = 0

                if is_initial_sync:
                    logger.info("🔄 Starting PostgreSQL initial sync (%s records per batch)", batch_size)

                while True:
                    if is_initial_sync:
                        wavelog_records = self._fetch_changed_records(None, initial_cursor_id, batch_size)
                    else:
                        wavelog_records = self._fetch_changed_records(last_modified, last_id, batch_size)

                    if not wavelog_records:
                        break

                    batch_num += 1
                    batch_added = 0
                    batch_updated = 0
                    for wavelog_record in wavelog_records:
                        try:
                            record = self._convert_wavelog_to_duckdb(wavelog_record)
                            action = self._upsert_record(conn, record)
                            if action == "added":
                                added_count += 1
                                batch_added += 1
                            else:
                                updated_count += 1
                                batch_updated += 1

                            record_modified = wavelog_record.get("last_modified")
                            record_id = wavelog_record.get("COL_PRIMARY_KEY")
                            if is_initial_sync and record_id and record_id > initial_cursor_id:
                                initial_cursor_id = record_id
                            if record_modified and (latest_modified is None or record_modified > latest_modified):
                                latest_modified = record_modified
                                latest_id = record_id
                            elif record_modified == latest_modified and record_id > latest_id:
                                latest_id = record_id
                            elif is_initial_sync and latest_modified is None and record_id > latest_id:
                                latest_id = record_id
                        except Exception as exc:
                            logger.error(
                                "❌ Error processing Wavelog record %s: %s",
                                wavelog_record.get("COL_PRIMARY_KEY"),
                                exc,
                            )
                            continue

                    conn.commit()
                    total_records = self._count_records(conn)
                    if is_initial_sync:
                        logger.info(
                            "✅ PostgreSQL batch %s: +%s new, ~%s updated | Total: %s QSOs synced",
                            batch_num,
                            batch_added,
                            batch_updated,
                            total_records,
                        )
                    if not is_initial_sync or len(wavelog_records) < batch_size:
                        break

                conn.commit()
                total_records = self._count_records(conn)
                self._update_sync_metadata(conn, latest_modified, latest_id, total_records, added_count, updated_count)
                self.last_sync_error = None
                self._cached_status = {
                    "initialized": True,
                    "last_sync": datetime.now(),
                    "last_wavelog_modified": latest_modified,
                    "last_wavelog_id": latest_id,
                    "total_records": total_records,
                    "last_sync_added": added_count,
                    "last_sync_updated": updated_count,
                    "last_sync_error": None,
                    "status": "ok",
                }
                return {
                    "synced": True,
                    "records_added": added_count,
                    "records_updated": updated_count,
                    "total_records": total_records,
                    "message": f"Synced {added_count + updated_count} records from Wavelog",
                }
        except Exception as exc:
            logger.error("❌ Wavelog PostgreSQL sync failed: %s", exc, exc_info=True)
            self.last_sync_error = str(exc)
            self._cached_status = {
                **self._cached_status,
                "status": "failed",
                "last_sync_error": self.last_sync_error,
                "error": str(exc),
            }
            return {"synced": False, "error": str(exc), "message": f"Sync failed: {exc}"}
        finally:
            self._sync_active = False

    def _count_records(self, conn) -> int:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM qso_records")
            row = cur.fetchone()
        return int(row[0] or 0) if row else 0

    def get_sync_status(self) -> Dict[str, Any]:
        if self._sync_active or not self._db_lock.acquire(blocking=False):
            return {**self._cached_status, "syncing": self._sync_active}

        try:
            with connect() as conn:
                metadata = self._get_sync_metadata(conn)
                if not metadata:
                    self._cached_status = {
                        "initialized": False,
                        "status": "failed" if self.last_sync_error else "not_initialized",
                        "last_sync_error": self.last_sync_error,
                        "total_records": 0,
                        "message": "Sync not yet initialized",
                    }
                    return self._cached_status
                total_records = self._count_records(conn)
                self._cached_status = {
                    "initialized": True,
                    "last_sync": metadata["last_sync_timestamp"],
                    "last_wavelog_modified": metadata["last_wavelog_modified"],
                    "last_wavelog_id": metadata["last_wavelog_id"],
                    "total_records": total_records,
                    "last_sync_added": metadata["last_sync_added"],
                    "last_sync_updated": metadata["last_sync_updated"],
                    "last_sync_error": self.last_sync_error,
                    "status": "failed" if self.last_sync_error else "ok",
                }
                return self._cached_status
        except Exception as exc:
            logger.debug("Could not read PostgreSQL sync status, returning cached status: %s", exc)
            self.last_sync_error = str(exc)
            return {
                **self._cached_status,
                "status": "failed",
                "error": str(exc),
                "last_sync_error": self.last_sync_error,
            }
        finally:
            self._db_lock.release()

    def reset_sync(self, clear_data: bool = False) -> Dict[str, Any]:
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM sync_metadata WHERE id = 1")
                    if clear_data:
                        cur.execute("DELETE FROM qso_records")
                        logger.info("🔄 Cleared all QSO records from PostgreSQL")
                conn.commit()
            logger.info("✅ PostgreSQL sync metadata reset - next sync will be a full initial sync")
            return {"success": True, "message": "Sync reset successfully", "data_cleared": clear_data}
        except Exception as exc:
            logger.error("❌ Failed to reset PostgreSQL sync: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}
