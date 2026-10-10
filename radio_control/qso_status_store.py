"""Read worked/confirmed status from Wavelog for spot classification."""

from __future__ import annotations

import logging
import json
from pathlib import Path
import threading
from typing import Optional
import time

import pymysql
from pymysql.cursors import DictCursor
import duckdb

from radio_control import config
from radio_control.postgres_store import connect as connect_postgres
from radio_control.postgres_store import should_use_postgres

logger = logging.getLogger(__name__)

CONFIRMED_VALUES = {"Y", "V", "YES", "TRUE", "1", "CONFIRMED"}
US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
US_STATE_DXCC = frozenset({6, 110, 291})  # Alaska, Hawaii, contiguous United States
MSHV_BAND_INDEXES = {
    "160m": 3, "80m": 4, "40m": 6, "30m": 7, "20m": 8,
    "17m": 9, "15m": 10, "12m": 11, "10m": 12,
}


def _band_from_mhz(mhz: float) -> str:
    if 1.8 <= mhz < 2.0:
        return "160m"
    if 3.5 <= mhz < 4.0:
        return "80m"
    if 5.0 <= mhz < 5.5:
        return "60m"
    if 7.0 <= mhz < 7.3:
        return "40m"
    if 10.0 <= mhz < 10.2:
        return "30m"
    if 14.0 <= mhz < 14.35:
        return "20m"
    if 18.0 <= mhz < 18.2:
        return "17m"
    if 21.0 <= mhz < 21.45:
        return "15m"
    if 24.8 <= mhz < 25.0:
        return "12m"
    if 28.0 <= mhz < 29.7:
        return "10m"
    if 50.0 <= mhz < 54.0:
        return "6m"
    if 144.0 <= mhz < 148.0:
        return "2m"
    return f"{mhz:g}mhz"


class DuckDBQSOStatusStore:
    """Small cached query layer for spot classification against Wavelog QSOs."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else config.DATA_DIR / "qso_log.duckdb"
        self._use_duckdb = db_path is not None
        self._unavailable_logged = False
        self._loaded_mtime: float | None = None
        self._loaded_at: float | None = None
        self._cache_ttl = 300
        self._load_lock = threading.Lock()
        self.dxcc_worked: set[int] = set()
        self.dxcc_confirmed: set[int] = set()
        self.dxcc_band_worked: set[tuple[int, str]] = set()
        self.dxcc_mode_worked: set[tuple[int, str]] = set()
        self.dxcc_bandmode_confirmed: set[tuple[int, str, str]] = set()
        self.call_worked: set[str] = set()
        self.call_confirmed: set[str] = set()
        self.call_band_worked: set[tuple[str, str]] = set()
        self.call_mode_worked: set[tuple[str, str]] = set()
        self.call_bandmode_worked: set[tuple[str, str, str]] = set()
        self.call_bandmode_confirmed: set[tuple[str, str, str]] = set()
        self.call_bandmode_latest_date: dict[tuple[str, str, str], str] = {}
        self.grid_worked: set[str] = set()
        self.grid_band_worked: set[tuple[str, str]] = set()
        self.grid_mode_worked: set[tuple[str, str]] = set()
        self.us_state_by_call: dict[str, str] = {}
        self.us_state_band_worked_calls: dict[tuple[str, str], set[str]] = {}
        self.us_state_band_confirmed_calls: dict[tuple[str, str], set[str]] = {}

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
            "call_bandmode_worked_count": len(self.call_bandmode_worked),
            "call_bandmode_confirmed_count": len(self.call_bandmode_confirmed),
            "call_bandmode_latest_date_count": len(self.call_bandmode_latest_date),
            "grid_worked_count": len(self.grid_worked),
            "grid_band_worked_count": len(self.grid_band_worked),
            "grid_mode_worked_count": len(self.grid_mode_worked),
            "us_state_call_count": len(self.us_state_by_call),
            "us_state_band_slot_count": len(self.us_state_band_worked_calls),
        }

    def mshv_confirmation_index(self) -> list[str] | None:
        """Return the confirmation facts consumed by the native MSHV UI.

        The same cached Wavelog rows and LoTW/paper confirmation rule used by
        the Spots classifier are the authority.  ``None`` deliberately means
        unavailable; callers must retain the last good index rather than
        publishing an empty file that would turn every confirmed QSO into W.
        """
        if not self._ensure_loaded():
            return None
        band_indexes = {
            "160m": 3, "80m": 4, "60m": 5, "40m": 6, "30m": 7,
            "20m": 8, "17m": 9, "15m": 10, "12m": 11, "10m": 12,
            "6m": 14, "2m": 17,
        }
        lines = ["# OM0RX Wavelog confirmation index v1"]
        lines.extend(f"DXCC|{dxcc}" for dxcc in sorted(self.dxcc_confirmed))
        lines.extend(f"CALL|{call}" for call in sorted(self.call_confirmed))
        lines.extend(
            f"DXCC_BAND_MODE|{dxcc}|{band_indexes[band]}|{mode}"
            for dxcc, band, mode in sorted(self.dxcc_bandmode_confirmed)
            if band in band_indexes and mode in {"FT8", "FT4"}
        )
        lines.extend(
            f"CALL_BAND_MODE|{call}|{band_indexes[band]}|{mode}"
            for call, band, mode in sorted(self.call_bandmode_confirmed)
            if band in band_indexes and mode in {"FT8", "FT4"}
        )
        return lines

    def mshv_us_state_index(self) -> list[str] | None:
        """Return the distinct-call state/band facts consumed by native MSHV."""
        if not self._ensure_loaded():
            return None
        state_by_call = dict(self.us_state_by_call)
        lotw_calls: set[str] = set()
        cache_path = config.DATA_DIR / "qrz_profile_cache.json"
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            cache = {}
        if isinstance(cache, dict):
            for raw_call, item in cache.items():
                profile = item.get("profile", {}) if isinstance(item, dict) else {}
                if not isinstance(profile, dict):
                    continue
                call = self._normalise_call(raw_call)
                state = self._normalise_state(profile.get("state"))
                country = str(profile.get("country") or "").strip().upper()
                is_us_state_country = country in {
                    "UNITED STATES", "UNITED STATES OF AMERICA", "USA", "ALASKA", "HAWAII",
                }
                if call and state and is_us_state_country:
                    state_by_call[call] = state
                    if self._confirmed_value(profile.get("lotw")):
                        lotw_calls.add(call)
        lines = ["# OM0RX Wavelog US state chase index v1"]
        lines.extend(
            f"CALL|{call}|{state}|{1 if call in lotw_calls else 0}|291"
            for call, state in sorted(state_by_call.items())
        )
        for (state, band), calls in sorted(self.us_state_band_worked_calls.items()):
            band_index = MSHV_BAND_INDEXES.get(band)
            if band_index is None:
                continue
            confirmed = self.us_state_band_confirmed_calls.get((state, band), set())
            lines.extend(
                f"WORKED|{call}|{state}|{band_index}|{1 if call in confirmed else 0}|291"
                for call in sorted(calls)
            )
        return lines

    def mshv_lotw_members(self) -> list[str] | None:
        """Return cached QRZ LoTW participants for native preference filters."""
        if not self._ensure_loaded():
            return None
        try:
            cache = json.loads((config.DATA_DIR / "qrz_profile_cache.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        calls: set[str] = set()
        if isinstance(cache, dict):
            for raw_call, item in cache.items():
                profile = item.get("profile", {}) if isinstance(item, dict) else {}
                if isinstance(profile, dict) and self._confirmed_value(profile.get("lotw")):
                    call = self._normalise_call(raw_call)
                    if call:
                        calls.add(call)
        return sorted(calls)

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

        band_value = self._normalise_band(band)
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

    def worked_before_date(
        self,
        callsign: str | None,
        band: str | None,
        mode: str | None,
    ) -> Optional[str]:
        """Return the latest YYYYMMDD date for an exact call/band/mode slot."""
        call_value = self._normalise_call(callsign)
        band_value = self._normalise_band(band)
        mode_value = str(mode or "").strip().upper()
        if not call_value or not band_value or not mode_value:
            return None
        if not self._ensure_loaded():
            return None
        return self.call_bandmode_latest_date.get((call_value, band_value, mode_value))

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
        band_value = self._normalise_band(band)
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

        band_value = self._normalise_band(band)
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
        band_value = self._normalise_band(qso_data.get("band"))
        mode_value = str(qso_data.get("submode") or qso_data.get("mode") or "").strip().upper()
        grid_value = self._normalise_grid(
            qso_data.get("gridsquare") or qso_data.get("grid")
        )
        confirmed = self._row_confirmed(qso_data)
        qso_date = self._normalise_qso_date(qso_data)
        qso_dxcc = self._coerce_dxcc(qso_data.get("dxcc") or qso_data.get("dxcc_id"))
        state_value = (
            self._normalise_state(qso_data.get("state"))
            if qso_dxcc in US_STATE_DXCC else ""
        )

        changed = False
        if call_value:
            changed |= self._add(self.call_worked, call_value)
            if confirmed:
                changed |= self._add(self.call_confirmed, call_value)
            if band_value:
                changed |= self._add(self.call_band_worked, (call_value, band_value))
            if mode_value:
                changed |= self._add(self.call_mode_worked, (call_value, mode_value))
            if band_value and mode_value:
                changed |= self._add(self.call_bandmode_worked, (call_value, band_value, mode_value))
            if band_value and mode_value and confirmed:
                changed |= self._add(self.call_bandmode_confirmed, (call_value, band_value, mode_value))
            if band_value and mode_value and qso_date:
                slot = (call_value, band_value, mode_value)
                if qso_date > self.call_bandmode_latest_date.get(slot, ""):
                    self.call_bandmode_latest_date[slot] = qso_date
                    changed = True
            if state_value:
                if self.us_state_by_call.get(call_value) != state_value:
                    self.us_state_by_call[call_value] = state_value
                    changed = True
                if band_value in MSHV_BAND_INDEXES and mode_value in {"FT8", "FT4"}:
                    state_slot = (state_value, band_value)
                    changed |= self._add(
                        self.us_state_band_worked_calls.setdefault(state_slot, set()), call_value
                    )
                    if confirmed:
                        changed |= self._add(
                            self.us_state_band_confirmed_calls.setdefault(state_slot, set()), call_value
                        )

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
    def _normalise_state(state: object) -> str:
        value = str(state or "").strip().upper()
        return value if value in US_STATES else ""

    @staticmethod
    def _normalise_band(band: object) -> str:
        value = "".join(str(band or "").lower().split())
        if not value:
            return ""
        if value.endswith("meters"):
            value = value[:-6] + "m"
        elif value.endswith("meter"):
            value = value[:-5] + "m"
        if value.endswith("mhz"):
            try:
                mhz = float(value[:-3])
            except ValueError:
                return value
            return _band_from_mhz(mhz)
        if value.endswith("m"):
            numeric = value[:-1]
            if numeric.replace(".", "", 1).isdigit():
                if "." in numeric:
                    return _band_from_mhz(float(numeric))
                return f"{int(numeric)}m"
        if value.replace(".", "", 1).isdigit():
            numeric = float(value)
            if numeric > 1000:
                numeric /= 1_000_000
            return _band_from_mhz(numeric)
        return value

    @staticmethod
    def _coerce_dxcc(dxcc: object) -> int | None:
        try:
            if dxcc is None or dxcc == "":
                return None
            return int(dxcc)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalise_qso_date(row: dict[str, object]) -> str:
        value = row.get("time_on") or row.get("qso_datetime") or row.get("qso_date")
        digits = "".join(char for char in str(value or "")[:10] if char.isdigit())
        return digits[:8] if len(digits) >= 8 else ""

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
        now = time.monotonic()
        if self._loaded_at is not None and now - self._loaded_at < self._cache_ttl:
            return True

        if not self.available():
            if not self._unavailable_logged:
                logger.warning("Wavelog database config is not available for QSO status cache")
                self._unavailable_logged = True
            return False

        # Spot classification is highly concurrent.  When the five-minute
        # cache expires, let one worker refresh it while every other worker
        # keeps using the last complete snapshot.  Previously all workers
        # could start the same database scan and hit the classifier's
        # 750-millisecond timeout, leaving otherwise-known DXCCs as Unknown.
        if not self._load_lock.acquire(blocking=False):
            return self._loaded_at is not None

        try:
            # Another worker may have completed the refresh between the first
            # freshness check and acquiring the lock.
            now = time.monotonic()
            if self._loaded_at is not None and now - self._loaded_at < self._cache_ttl:
                return True

            if should_use_postgres() and not self._use_duckdb:
                with connect_postgres() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT call, dxcc, band, mode, submode,
                                   lotw_qsl_rcvd, eqsl_qsl_rcvd, qsl_rcvd,
                                   gridsquare, time_on, state
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
                                "time_on": time_on,
                                "state": state,
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
                                time_on,
                                state,
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
                    time_expr = (
                        "time_on"
                        if "time_on" in columns
                        else "qso_datetime"
                        if "qso_datetime" in columns
                        else "qso_date"
                        if "qso_date" in columns
                        else "NULL AS time_on"
                    )
                    state_expr = "state" if "state" in columns else "NULL AS state"
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
                            "time_on": time_on,
                            "state": state,
                        }
                        for call, dxcc, band, mode, submode, lotw_qsl_rcvd, eqsl_qsl_rcvd, qsl_rcvd, gridsquare, time_on, state in conn.execute(
                            f"""
                            SELECT {call_expr}, dxcc, band, mode, submode,
                                   lotw_qsl_rcvd, {eqsl_expr}, {qsl_expr}, gridsquare,
                                   {time_expr}, {state_expr}
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
                                   COL_GRIDSQUARE AS gridsquare,
                                   COL_TIME_ON AS time_on,
                                   COL_STATE AS state
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
            call_bandmode_worked: set[tuple[str, str, str]] = set()
            call_bandmode_confirmed: set[tuple[str, str, str]] = set()
            call_bandmode_latest_date: dict[tuple[str, str, str], str] = {}
            grid_worked: set[str] = set()
            grid_band_worked: set[tuple[str, str]] = set()
            grid_mode_worked: set[tuple[str, str]] = set()
            us_state_by_call: dict[str, str] = {}
            us_state_band_worked_calls: dict[tuple[str, str], set[str]] = {}
            us_state_band_confirmed_calls: dict[tuple[str, str], set[str]] = {}

            for row in rows:
                band_value = self._normalise_band(row.get("band"))
                mode_value = (row.get("submode") or row.get("mode") or "").strip().upper()
                confirmed = self._row_confirmed(row)
                grid_value = self._normalise_grid(row.get("gridsquare"))
                call_value = self._normalise_call(row.get("call"))
                qso_date = self._normalise_qso_date(row)
                row_dxcc = self._coerce_dxcc(row.get("dxcc"))
                state_value = (
                    self._normalise_state(row.get("state"))
                    if row_dxcc in US_STATE_DXCC else ""
                )

                if call_value:
                    call_worked.add(call_value)
                    if confirmed:
                        call_confirmed.add(call_value)
                    if band_value:
                        call_band_worked.add((call_value, band_value))
                    if mode_value:
                        call_mode_worked.add((call_value, mode_value))
                    if band_value and mode_value:
                        call_bandmode_worked.add((call_value, band_value, mode_value))
                    if band_value and mode_value and confirmed:
                        call_bandmode_confirmed.add((call_value, band_value, mode_value))
                    if band_value and mode_value and qso_date:
                        slot = (call_value, band_value, mode_value)
                        if qso_date > call_bandmode_latest_date.get(slot, ""):
                            call_bandmode_latest_date[slot] = qso_date
                    if state_value:
                        us_state_by_call[call_value] = state_value
                        if band_value in MSHV_BAND_INDEXES and mode_value in {"FT8", "FT4"}:
                            state_slot = (state_value, band_value)
                            us_state_band_worked_calls.setdefault(state_slot, set()).add(call_value)
                            if confirmed:
                                us_state_band_confirmed_calls.setdefault(state_slot, set()).add(call_value)

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
            self.call_bandmode_worked = call_bandmode_worked
            self.call_bandmode_confirmed = call_bandmode_confirmed
            self.call_bandmode_latest_date = call_bandmode_latest_date
            self.grid_worked = grid_worked
            self.grid_band_worked = grid_band_worked
            self.grid_mode_worked = grid_mode_worked
            self.us_state_by_call = us_state_by_call
            self.us_state_band_worked_calls = us_state_band_worked_calls
            self.us_state_band_confirmed_calls = us_state_band_confirmed_calls
            self._loaded_at = now
            self._loaded_mtime = now
            if should_use_postgres() and not self._use_duckdb:
                source = "PostgreSQL"
            elif self._use_duckdb:
                source = "DuckDB"
            else:
                source = "Wavelog DB"
            logger.info(
                "Loaded QSO status sets from %s: calls=%d dxcc=%d confirmed=%d band=%d mode=%d bandmode_cnf=%d worked_dates=%d grids=%d",
                source,
                len(self.call_worked),
                len(self.dxcc_worked),
                len(self.dxcc_confirmed),
                len(self.dxcc_band_worked),
                len(self.dxcc_mode_worked),
                len(self.dxcc_bandmode_confirmed),
                len(self.call_bandmode_latest_date),
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
        finally:
            self._load_lock.release()
