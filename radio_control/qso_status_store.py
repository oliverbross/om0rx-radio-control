"""Read worked/confirmed status from the local Wavelog DuckDB mirror."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import duckdb

from radio_control import config

logger = logging.getLogger(__name__)


class DuckDBQSOStatusStore:
    """Small query layer for spot classification against synced QSOs."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else config.DATA_DIR / "qso_log.duckdb"
        self._unavailable_logged = False
        self._loaded_mtime: float | None = None
        self.dxcc_worked: set[int] = set()
        self.dxcc_confirmed: set[int] = set()
        self.dxcc_band_worked: set[tuple[int, str]] = set()
        self.dxcc_mode_worked: set[tuple[int, str]] = set()
        self.dxcc_bandmode_confirmed: set[tuple[int, str, str]] = set()

    def available(self) -> bool:
        return self.db_path.exists()

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
        if not self.db_path.exists():
            if not self._unavailable_logged:
                logger.warning("QSO status DuckDB mirror is not available: %s", self.db_path)
                self._unavailable_logged = True
            return False

        mtime = self.db_path.stat().st_mtime
        if self._loaded_mtime == mtime:
            return True

        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            try:
                rows = conn.execute(
                    """
                    SELECT dxcc, band, mode, submode, lotw_qsl_rcvd
                    FROM qso_records
                    WHERE dxcc IS NOT NULL
                    """
                ).fetchall()

                dxcc_worked: set[int] = set()
                dxcc_confirmed: set[int] = set()
                dxcc_band_worked: set[tuple[int, str]] = set()
                dxcc_mode_worked: set[tuple[int, str]] = set()
                dxcc_bandmode_confirmed: set[tuple[int, str, str]] = set()

                for dxcc, band, mode, submode, lotw_qsl_rcvd in rows:
                    dxcc_int = int(dxcc)
                    band_value = (band or "").strip()
                    mode_value = (submode or mode or "").strip().upper()
                    confirmed = str(lotw_qsl_rcvd or "").strip().upper() in {
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
                self._loaded_mtime = mtime
                logger.info(
                    "Loaded QSO status sets: dxcc=%d confirmed=%d band=%d mode=%d bandmode_cnf=%d",
                    len(self.dxcc_worked),
                    len(self.dxcc_confirmed),
                    len(self.dxcc_band_worked),
                    len(self.dxcc_mode_worked),
                    len(self.dxcc_bandmode_confirmed),
                )
                return True
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("QSO status DuckDB load failed: %s", exc)
            return False
