"""Shared Digital callsign status helpers."""

from __future__ import annotations

import asyncio
from typing import Any, Optional


def _same_text(left: Any, right: Any) -> bool:
    return str(left or "").strip().upper() == str(right or "").strip().upper()


def _confirmed(qso: dict[str, Any]) -> bool:
    return str(qso.get("lotw_qsl") or qso.get("lotw_rcvd") or "").strip().upper() in {"Y", "YES", "1", "TRUE"}


async def call_status_from_recent_qsos(callsign: str, band: Optional[str], mode: Optional[str]) -> Optional[str]:
    """Return a callsign status from the same recent-QSO source used by the UI modal."""
    call = str(callsign or "").strip().upper()
    if not call:
        return None
    try:
        from services.qso_logging import _get_recent_qsos_from_duckdb, _get_recent_qsos_from_wavelog_db

        try:
            qsos = await asyncio.wait_for(
                asyncio.to_thread(_get_recent_qsos_from_wavelog_db, call, 100),
                timeout=2.0,
            )
        except Exception:
            qsos = await asyncio.wait_for(
                asyncio.to_thread(_get_recent_qsos_from_duckdb, call, 100),
                timeout=2.0,
            )
    except Exception:
        return None

    if not qsos:
        return None

    same_band = [qso for qso in qsos if _same_text(qso.get("band"), band)]
    same_mode = [qso for qso in qsos if _same_text(qso.get("mode"), mode)]
    same_band_mode = [qso for qso in same_band if _same_text(qso.get("mode"), mode)]
    if same_band_mode:
        return "Confirmed" if any(_confirmed(qso) for qso in same_band_mode) else "Worked"
    if not same_band and not same_mode:
        return "New Band+Mode"
    if not same_band:
        return "New Band"
    if not same_mode:
        return "New Mode"
    return "Worked"
