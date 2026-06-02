"""Read worked/confirmed status from Wavelog for spot classification."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import time

import pymysql
from pymysql.cursors import DictCursor
import duckdb

from radio_control import config
from radio_control.postgres_store import connect as connect_postgres
from radio_control.postgres_store import should_use_postgres

logger = logging.getLogger(__name__)


class DuckDBQSOStatusStore:
    """Small cached query layer for spot classification against Wavelog QSOs."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else config.DATA_DIR / "qso_log.duckdb"
        self._use_duckdb = db_path is not None
        self._unavailable_logged = False
        self._loaded_mtime: float | None = None
        self._loaded_at: float | None = None
        self._cache_ttl = 300
        self.dxcc_worked: set[int] = set()
        self.dxcc_confirmed: set[int] = set()
        self.dxcc_band_worked: set[tuple[int, str]] = set()
        self.dxcc_mode_worked: set[tuple[int, str]] = set()
        self.dxcc_bandmode_confirmed: set[tuple[int, str, str]] = set()

    def available(self) -> bool:
        if self._use_duckdb:
            return self.db_path.exists()
        return bool(config.DB_HOST and config.DB_NAME and config.DB_USER)

    def diagnostics(self) -> dict[str, object]:
        """Return cache health details for classification diagnostics."""
        loaded = self._ensure_loaded()
        return {
            "db_path": str(self.db_path),
            "available": self.available(),
            "loaded": loaded,
            "loaded_mtime": self._loaded_mtime,
            "dxcc_worked_count": len(self.dxcc_worked),
            "dxcc_confirmed_count": len(self.dxcc_confirmed),
            "dxcc_band_worked_count": len(self.dxcc_band_worked),
            "dxcc_mode_worked_count": len(self.dxcc_mode_worked),
            "dxcc_bandmode_confirmed_count": len(self.dxcc_bandmode_confirmed),
        }

    def dxcc_overall(self, dxcc: int | None) -> Optional[tuple[bool, bool]]:
        """Return (worked, confirmed) for a DXCC, or None when the DB is unavailable."""
        if dxcc is None:
            return False, False
        if not self._ensure_loaded():
            return None
        dxcc_int = int(dxcc)
        return dxcc_int in self.dxcc_worked, dxcc_int in self.dxcc_confirmed

    def dxcc_bandmode_flags(
        self,
        dxcc: int | None,
        band: str | None,
        mode: str | None,
    ) -> Optional[tuple[bool, bool, bool]]:
        """Return (new_band, new_mode, bandmode_confirmed) for a DXCC."""
        if dxcc is None:
            return False, False, False
        band_value = (band or "").strip()
        mode_value = (mode or "").strip().upper()
        if not band_value or not mode_value:
            return None
        if not self._ensure_loaded():
            return None

        dxcc_int = int(dxcc)
        band_worked = (dxcc_int, band_value) in self.dxcc_band_worked
        mode_worked = (dxcc_int, mode_value) in self.dxcc_mode_worked
        bandmode_confirmed = (
            dxcc_int,
            band_value,
            mode_value,
        ) in self.dxcc_bandmode_confirmed
        return not band_worked, not mode_worked, bandmode_confirmed

    def _ensure_loaded(self) -> bool:
        if not self.available():
            if not self._unavailable_logged:
                logger.warning("Wavelog database config is not available for QSO status cache")
                self._unavailable_logged = True
            return False

        now = time.monotonic()
        if self._loaded_at is not None and now - self._loaded_at < self._cache_ttl:
            return True

        try:
            if should_use_postgres() and not self._use_duckdb:
                with connect_postgres() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT dxcc, band, mode, submode, lotw_qsl_rcvd
                            FROM qso_records
                            WHERE dxcc IS NOT NULL
                            """
                        )
                        rows = [
                            {
                                "dxcc": dxcc,
                                "band": band,
                                "mode": mode,
                                "submode": submode,
                                "lotw_qsl_rcvd": lotw_qsl_rcvd,
                            }
                            for dxcc, band, mode, submode, lotw_qsl_rcvd in cur.fetchall()
                        ]
            elif self._use_duckdb:
                conn = duckdb.connect(str(self.db_path))
                try:
                    rows = [
                        {
                            "dxcc": dxcc,
                            "band": band,
                            "mode": mode,
                            "submode": submode,
                            "lotw_qsl_rcvd": lotw_qsl_rcvd,
                        }
                        for dxcc, band, mode, submode, lotw_qsl_rcvd in conn.execute(
                            """
                            SELECT dxcc, band, mode, submode, lotw_qsl_rcvd
                            FROM qso_records
                            WHERE dxcc IS NOT NULL
                            """
                        ).fetchall()
                    ]
                finally:
                    conn.close()
            else:
                conn = pymysql.connect(
                    host=config.DB_HOST,
                    port=config.DB_PORT,
                    user=config.DB_USER,
                    password=config.DB_PASS,
                    database=config.DB_NAME,
                    charset="utf8mb4",
                    cursorclass=DictCursor,
                    connect_timeout=3,
                    read_timeout=10,
                    write_timeout=5,
                )
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT COL_DXCC AS dxcc,
                                   COL_BAND AS band,
                                   COL_MODE AS mode,
                                   COL_SUBMODE AS submode,
                                   COL_LOTW_QSL_RCVD AS lotw_qsl_rcvd
                            FROM TABLE_HRD_CONTACTS_V01
                            WHERE station_id = %s
                              AND COL_DXCC IS NOT NULL
                            """,
                            (int(getattr(config, "WAVELOG_STATION_ID", 1)),),
                        )
                        rows = cursor.fetchall()
                finally:
                    conn.close()

            dxcc_worked: set[int] = set()
            dxcc_confirmed: set[int] = set()
            dxcc_band_worked: set[tuple[int, str]] = set()
            dxcc_mode_worked: set[tuple[int, str]] = set()
            dxcc_bandmode_confirmed: set[tuple[int, str, str]] = set()

            for row in rows:
                dxcc_int = int(row.get("dxcc"))
                band_value = (row.get("band") or "").strip()
                mode_value = (row.get("submode") or row.get("mode") or "").strip().upper()
                confirmed = str(row.get("lotw_qsl_rcvd") or "").strip().upper() in {
                    "Y",
                    "YES",
                    "TRUE",
                    "1",
                }

                dxcc_worked.add(dxcc_int)
                if confirmed:
                    dxcc_confirmed.add(dxcc_int)
                if band_value:
                    dxcc_band_worked.add((dxcc_int, band_value))
                if mode_value:
                    dxcc_mode_worked.add((dxcc_int, mode_value))
                if band_value and mode_value and confirmed:
                    dxcc_bandmode_confirmed.add((dxcc_int, band_value, mode_value))

            self.dxcc_worked = dxcc_worked
            self.dxcc_confirmed = dxcc_confirmed
            self.dxcc_band_worked = dxcc_band_worked
            self.dxcc_mode_worked = dxcc_mode_worked
            self.dxcc_bandmode_confirmed = dxcc_bandmode_confirmed
            self._loaded_at = now
            self._loaded_mtime = now
            if should_use_postgres() and not self._use_duckdb:
                source = "PostgreSQL"
            elif self._use_duckdb:
                source = "DuckDB"
            else:
                source = "Wavelog DB"
            logger.info(
                "Loaded QSO status sets from %s: dxcc=%d confirmed=%d band=%d mode=%d bandmode_cnf=%d",
                source,
                len(self.dxcc_worked),
                len(self.dxcc_confirmed),
                len(self.dxcc_band_worked),
                len(self.dxcc_mode_worked),
                len(self.dxcc_bandmode_confirmed),
            )
            return True
        except Exception as exc:
            if self._loaded_mtime is not None:
                logger.debug("Keeping existing QSO status cache after DuckDB reload failed: %s", exc)
                return True
            if not self._unavailable_logged:
                logger.warning("QSO status DuckDB load failed: %s", exc)
                self._unavailable_logged = True
            return False
