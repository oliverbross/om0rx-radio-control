"""Small scoring and noise-control helpers for DX spots."""

from __future__ import annotations

import re
from typing import Any, Mapping


_SNR_RE = re.compile(r"(?<![A-Z0-9])([+-]?\d{1,2}(?:\.\d+)?)\s*dB\b", re.IGNORECASE)


def extract_rbl_snr(comment: Any) -> float | None:
    """Extract an RBL/RBN signal report from a spot comment."""
    match = _SNR_RE.search(str(comment or ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _status_value(spot: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = spot.get(key)
        if value:
            return str(value)
    return ""


def score_spot(spot: Mapping[str, Any]) -> tuple[int, list[str]]:
    """Return an operator-usefulness score from 0-100 plus concise reasons."""
    score = 0
    reasons: list[str] = []

    call_status = _status_value(spot, "call_status")
    dxcc_status = _status_value(spot, "tag", "dxcc_status")
    special = _status_value(spot, "special", "special_tags")
    source = _status_value(spot, "spot_source") or "cluster"
    rbl_snr = spot.get("rbl_snr")
    if rbl_snr is None:
        rbl_snr = extract_rbl_snr(spot.get("comment"))

    dxcc_weights = {
        "ATNO": (85, "ATNO"),
        "C/New Band+Mode": (68, "new confirmed DXCC band+mode"),
        "W/New Band+Mode": (62, "new worked DXCC band+mode"),
        "C/New Band": (58, "new confirmed DXCC band"),
        "W/New Band": (52, "new worked DXCC band"),
        "C/New Mode": (48, "new confirmed DXCC mode"),
        "W/New Mode": (42, "new worked DXCC mode"),
        "Worked": (18, "worked DXCC"),
        "Confirmed": (8, "confirmed DXCC"),
    }
    if dxcc_status in dxcc_weights:
        value, reason = dxcc_weights[dxcc_status]
        score += value
        reasons.append(reason)

    call_weights = {
        "New Call": (42, "new call"),
        "New Band+Mode": (34, "new call band+mode"),
        "New Band": (28, "new call band"),
        "New Mode": (22, "new call mode"),
        "Worked": (8, "worked call"),
        "Confirmed": (4, "confirmed call"),
    }
    if call_status in call_weights:
        value, reason = call_weights[call_status]
        score += value
        reasons.append(reason)

    if special:
        score += 14
        reasons.append(f"special: {special}")

    if spot.get("local_heard"):
        score += 25
        snr = spot.get("local_heard_snr")
        reasons.append(f"heard locally{f' {snr:g} dB' if isinstance(snr, (int, float)) else ''}")

    if source == "rbl":
        score += 5
        reasons.append("RBL")
        if isinstance(rbl_snr, (int, float)):
            if rbl_snr >= 15:
                score += 8
                reasons.append(f"strong {rbl_snr:g} dB")
            elif rbl_snr >= 8:
                score += 4
                reasons.append(f"{rbl_snr:g} dB")
            elif rbl_snr < 0:
                score -= 6
                reasons.append(f"weak {rbl_snr:g} dB")

    score = max(0, min(100, score))
    if not reasons:
        reasons.append("recent spot")
    return score, reasons[:4]


def enrich_spot_intelligence(spot: dict[str, Any]) -> dict[str, Any]:
    """Add rbl_snr, spot_score, and spot_score_reasons in-place."""
    if (spot.get("spot_source") or "cluster") == "rbl" and spot.get("rbl_snr") is None:
        spot["rbl_snr"] = extract_rbl_snr(spot.get("comment"))
    elif (spot.get("spot_source") or "cluster") != "rbl":
        spot["rbl_snr"] = None
    score, reasons = score_spot(spot)
    spot["spot_score"] = score
    spot["spot_score_reasons"] = reasons
    return spot
