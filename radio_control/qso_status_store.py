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

CONFIRMED_VALUES = {"Y", "YES", "TRUE", "1", "CONFIRMED"}


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
        self.call_worked: set[str] = set()
        self.call_confirmed: set[str] = set()
        self.call_band_worked: set[tuple[str, str]] = set()
        self.call_mode_worked: set[tuple[str, str]] = set()
        self.call_bandmode_confirmed: set[tuple[str, str, str]] = set()
        self.grid_worked: set[str] = set()
        self.grid_band_worked: set[tuple[str, str]] = set()
        self.grid_mode_worked: set[tuple[str, str]] = set()

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
            "call_worked_count": len(self.call_worked),
            "call_confirmed_count": len(self.call_confirmed),
            "call_band_worked_count": len(self.call_band_worked),
            "call_mode_worked_count": len(self.call_mode_worked),
            "call_bandmode_confirmed_count": len(self.call_bandmode_confirmed),
            "grid_worked_count": len(self.grid_worked),
            "grid_band_worked_count": len(self.grid_band_worked),
            "grid_mode_worked_count": len(self.grid_mode_worked),
        }

    def call_flags(
        self,
        callsign: str | None,
        band: str | None,
        mode: str | None,
    ) -> Optional[tuple[bool, bool, bool, bool, bool]]:
        """Return call worked/confirmed and band/mode slot flags from the local cache."""
        call_value = self._normalise_call(callsign)
        if not call_value:
            return False, False, True, True, False
        if not self._ensure_loaded():
            return None

        band_value = (band or "").strip()
        mode_value = (mode or "").strip().upper()
        call_worked = call_value in self.call_worked
        call_confirmed = call_value in self.call_confirmed
        new_band = bool(band_value) and (call_value, band_value) not in self.call_band_worked
        new_mode = bool(mode_value) and (call_value, mode_value) not in self.call_mode_worked
        bandmode_confirmed = (
            bool(band_value)
            and bool(mode_value)
            and (call_value, band_value, mode_value) in self.call_bandmode_confirmed
        )
        return call_worked, call_confirmed, new_band, new_mode, bandmode_confirmed

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

    def grid_flags(
        self,
        grid: str | None,
        band: str | None,
        mode: str | None,
    ) -> Optional[tuple[bool, bool, bool]]:
        """Return (new_grid, new_grid_band, new_grid_mode) for a Maidenhead square."""
        grid_value = self._normalise_grid(grid)
        if not grid_value:
            return False, False, False
        if not self._ensure_loaded():
            return None

        band_value = (band or "").strip()
        mode_value = (mode or "").strip().upper()
        new_grid = grid_value not in self.grid_worked
        new_grid_band = bool(band_value) and (grid_value, band_value) not in self.grid_band_worked
        new_grid_mode = bool(mode_value) and (grid_value, mode_value) not in self.grid_mode_worked
        return new_grid, new_grid_band, new_grid_mode

    def record_qso(self, qso_data: dict[str, object] | None) -> bool:
        """Record one newly logged QSO in the hot in-memory status sets."""
        if not isinstance(qso_data, dict):
            return False

        call_value = self._normalise_call(
            qso_data.get("callsign") or qso_data.get("call")
        )
        band_value = str(qso_data.get("band") or "").strip()
        mode_value = str(qso_data.get("submode") or qso_data.get("mode") or "").strip().upper()
        grid_value = self._normalise_grid(
            qso_data.get("gridsquare") or qso_data.get("grid")
        )
        confirmed = self._row_confirmed(qso_data)

        changed = False
        if call_value:
            changed |= self._add(self.call_worked, call_value)
            if confirmed:
                changed |= self._add(self.call_confirmed, call_value)
            if band_value:
                changed |= self._add(self.call_band_worked, (call_value, band_value))
            if mode_value:
                changed |= self._add(self.call_mode_worked, (call_value, mode_value))
            if band_value and mode_value and confirmed:
                changed |= self._add(self.call_bandmode_confirmed, (call_value, band_value, mode_value))

        dxcc_value = self._coerce_dxcc(qso_data.get("dxcc") or qso_data.get("dxcc_id"))
        if dxcc_value is not None:
            changed |= self._add(self.dxcc_worked, dxcc_value)
            if confirmed:
                changed |= self._add(self.dxcc_confirmed, dxcc_value)
            if band_value:
                changed |= self._add(self.dxcc_band_worked, (dxcc_value, band_value))
            if mode_value:
                changed |= self._add(self.dxcc_mode_worked, (dxcc_value, mode_value))
            if band_value and mode_value and confirmed:
                changed |= self._add(self.dxcc_bandmode_confirmed, (dxcc_value, band_value, mode_value))

        if grid_value:
            changed |= self._add(self.grid_worked, grid_value)
            if band_value:
                changed |= self._add(self.grid_band_worked, (grid_value, band_value))
            if mode_value:
                changed |= self._add(self.grid_mode_worked, (grid_value, mode_value))

        if changed:
            now = time.monotonic()
            self._loaded_at = now
            self._loaded_mtime = now
        return changed

    @staticmethod
    def _normalise_grid(grid: str | None) -> str:
        value = "".join(str(grid or "").upper().split())
        if len(value) < 4:
            return ""
        prefix = value[:4]
        return prefix if prefix[:2].isalpha() and prefix[2:].isdigit() else ""

    @staticmethod
    def _normalise_call(callsign: str | None) -> str:
        return "".join(str(callsign or "").upper().split())

    @staticmethod
    def _coerce_dxcc(dxcc: object) -> int | None:
        try:
            if dxcc is None or dxcc == "":
                return None
            return int(dxcc)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _confirmed_value(value: object) -> bool:
        return str(value or "").strip().upper() in CONFIRMED_VALUES

    @classmethod
    def _row_confirmed(cls, row: dict[str, object]) -> bool:
        return any(
            cls._confirmed_value(row.get(field))
            for field in (
                "lotw_qsl_rcvd",
                "lotw_qsl",
                "eqsl_qsl_rcvd",
                "eqsl_qsl",
                "qsl_rcvd",
            )
        )

    @staticmethod
    def _add(values: set, value: object) -> bool:
        if value in values:
            return False
        values.add(value)
        return True

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
                            SELECT call, dxcc, band, mode, submode,
                                   lotw_qsl_rcvd, eqsl_qsl_rcvd, qsl_rcvd,
                                   gridsquare
                            FROM qso_records
                            WHERE NULLIF(call, '') IS NOT NULL
                               OR dxcc IS NOT NULL
                               OR NULLIF(gridsquare, '') IS NOT NULL
                            """
                        )
                        rows = [
                            {
                                "call": call,
                                "dxcc": dxcc,
                                "band": band,
                                "mode": mode,
                                "submode": submode,
                                "lotw_qsl_rcvd": lotw_qsl_rcvd,
                                "eqsl_qsl_rcvd": eqsl_qsl_rcvd,
                                "qsl_rcvd": qsl_rcvd,
                                "gridsquare": gridsquare,
                            }
                            for (
                                call,
                                dxcc,
                                band,
                                mode,
                                submode,
                                lotw_qsl_rcvd,
                                eqsl_qsl_rcvd,
                                qsl_rcvd,
                                gridsquare,
                            ) in cur.fetchall()
                        ]
            elif self._use_duckdb:
                conn = duckdb.connect(str(self.db_path))
                try:
                    columns = {
                        str(row[1]).lower()
                        for row in conn.execute("PRAGMA table_info(qso_records)").fetchall()
                    }
                    call_expr = "call" if "call" in columns else "NULL AS call"
                    call_where = "NULLIF(call, '') IS NOT NULL OR" if "call" in columns else ""
                    eqsl_expr = "eqsl_qsl_rcvd" if "eqsl_qsl_rcvd" in columns else "NULL AS eqsl_qsl_rcvd"
                    qsl_expr = "qsl_rcvd" if "qsl_rcvd" in columns else "NULL AS qsl_rcvd"
                    rows = [
                        {
                            "call": call,
                            "dxcc": dxcc,
                            "band": band,
                            "mode": mode,
                            "submode": submode,
                            "lotw_qsl_rcvd": lotw_qsl_rcvd,
                            "eqsl_qsl_rcvd": eqsl_qsl_rcvd,
                            "qsl_rcvd": qsl_rcvd,
                            "gridsquare": gridsquare,
                        }
                        for call, dxcc, band, mode, submode, lotw_qsl_rcvd, eqsl_qsl_rcvd, qsl_rcvd, gridsquare in conn.execute(
                            f"""
                            SELECT {call_expr}, dxcc, band, mode, submode,
                                   lotw_qsl_rcvd, {eqsl_expr}, {qsl_expr}, gridsquare
                            FROM qso_records
                            WHERE {call_where}
                               dxcc IS NOT NULL
                               OR NULLIF(gridsquare, '') IS NOT NULL
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
                            SELECT COL_CALL AS call,
                                   COL_DXCC AS dxcc,
                                   COL_BAND AS band,
                                   COL_MODE AS mode,
                                   COL_SUBMODE AS submode,
                                   COL_LOTW_QSL_RCVD AS lotw_qsl_rcvd,
                                   COL_EQSL_QSL_RCVD AS eqsl_qsl_rcvd,
                                   COL_QSL_RCVD AS qsl_rcvd,
                                   COL_GRIDSQUARE AS gridsquare
                            FROM TABLE_HRD_CONTACTS_V01
                            WHERE station_id = %s
                              AND (
                                  (COL_CALL IS NOT NULL AND COL_CALL <> '')
                                  OR COL_DXCC IS NOT NULL
                                  OR (COL_GRIDSQUARE IS NOT NULL AND COL_GRIDSQUARE <> '')
                              )
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
            call_worked: set[str] = set()
            call_confirmed: set[str] = set()
            call_band_worked: set[tuple[str, str]] = set()
            call_mode_worked: set[tuple[str, str]] = set()
            call_bandmode_confirmed: set[tuple[str, str, str]] = set()
            grid_worked: set[str] = set()
            grid_band_worked: set[tuple[str, str]] = set()
            grid_mode_worked: set[tuple[str, str]] = set()

            for row in rows:
                band_value = (row.get("band") or "").strip()
                mode_value = (row.get("submode") or row.get("mode") or "").strip().upper()
                confirmed = self._row_confirmed(row)
                grid_value = self._normalise_grid(row.get("gridsquare"))
                call_value = self._normalise_call(row.get("call"))

                if call_value:
                    call_worked.add(call_value)
                    if confirmed:
                        call_confirmed.add(call_value)
                    if band_value:
                        call_band_worked.add((call_value, band_value))
                    if mode_value:
                        call_mode_worked.add((call_value, mode_value))
                    if band_value and mode_value and confirmed:
                        call_bandmode_confirmed.add((call_value, band_value, mode_value))

                if row.get("dxcc") is not None:
                    dxcc_int = int(row.get("dxcc"))
                    dxcc_worked.add(dxcc_int)
                    if confirmed:
                        dxcc_confirmed.add(dxcc_int)
                    if band_value:
                        dxcc_band_worked.add((dxcc_int, band_value))
                    if mode_value:
                        dxcc_mode_worked.add((dxcc_int, mode_value))
                    if band_value and mode_value and confirmed:
                        dxcc_bandmode_confirmed.add((dxcc_int, band_value, mode_value))
                if grid_value:
                    grid_worked.add(grid_value)
                    if band_value:
                        grid_band_worked.add((grid_value, band_value))
                    if mode_value:
                        grid_mode_worked.add((grid_value, mode_value))

            self.dxcc_worked = dxcc_worked
            self.dxcc_confirmed = dxcc_confirmed
            self.dxcc_band_worked = dxcc_band_worked
            self.dxcc_mode_worked = dxcc_mode_worked
            self.dxcc_bandmode_confirmed = dxcc_bandmode_confirmed
            self.call_worked = call_worked
            self.call_confirmed = call_confirmed
            self.call_band_worked = call_band_worked
            self.call_mode_worked = call_mode_worked
            self.call_bandmode_confirmed = call_bandmode_confirmed
            self.grid_worked = grid_worked
            self.grid_band_worked = grid_band_worked
            self.grid_mode_worked = grid_mode_worked
            self._loaded_at = now
            self._loaded_mtime = now
            if should_use_postgres() and not self._use_duckdb:
                source = "PostgreSQL"
            elif self._use_duckdb:
                source = "DuckDB"
            else:
                source = "Wavelog DB"
            logger.info(
                "Loaded QSO status sets from %s: calls=%d dxcc=%d confirmed=%d band=%d mode=%d bandmode_cnf=%d grids=%d",
                source,
                len(self.call_worked),
                len(self.dxcc_worked),
                len(self.dxcc_confirmed),
                len(self.dxcc_band_worked),
                len(self.dxcc_mode_worked),
                len(self.dxcc_bandmode_confirmed),
                len(self.grid_worked),
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
