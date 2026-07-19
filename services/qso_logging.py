"""
QSO Logging Service Module
Extracted from main.py - provides QSO logging endpoints for Wavelog integration,
QRZ lookups, and recent QSOs retrieval.
"""

import asyncio
import hashlib
import json
import logging
import re
from typing import Optional, Dict, Any
from datetime import date, datetime, time, timezone
from threading import RLock
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel
import duckdb

# Import required clients and handlers
from radio_control.wavelog_api import WavelogClient
from radio_control.qrz_api import QRZClient
from radio_control.adif_handler import ADIFHandler
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.qso_outbox import get_qso_outbox
from radio_control import config
from radio_control.postgres_store import connect as connect_postgres
from radio_control.postgres_store import should_use_postgres
from services.wavelog_log import get_wavelog_log_service

logger = logging.getLogger(__name__)

# Create router for QSO logging endpoints
router = APIRouter()

# Global clients (will be initialized when module is imported)
wavelog_client: Optional[WavelogClient] = None
qrz_client: Optional[QRZClient] = None
adif_handler: Optional[ADIFHandler] = None
cty_resolver: Optional[CtyDatResolver] = None
qso_status_store = None
_dedupe_lock = RLock()
_dedupe_ledger_path = config.LOGS_DIR / "qso_log_dedupe.json"
_pending_dedupe_claims: Dict[str, Dict[str, Any]] = {}
_PENDING_DEDUPE_TTL_SECONDS = 600
_WSJT_DIGITAL_MODES = {"FT8", "FT4", "FT2"}


class QSORequest(BaseModel):
    callsign: str
    frequency: float
    band: Optional[str] = None
    mode: str
    # RST values can be integers (SSB/CW) or strings (FT8/FT4 SNR like "-12", "+15")
    rst_sent: Optional[str] = None
    rst_received: Optional[str] = None
    date: Optional[str] = None
    time_off: Optional[str] = None
    name: Optional[str] = None
    qth: Optional[str] = None
    gridsquare: Optional[str] = None
    notes: Optional[str] = None
    pota: Optional[str] = None
    sota: Optional[str] = None
    iota: Optional[str] = None
    wwff: Optional[str] = None
    sig: Optional[str] = None
    sig_info: Optional[str] = None
    date_time: Optional[str] = None
    continent: Optional[str] = None
    cq_zone: Optional[int] = None
    itu_zone: Optional[int] = None
    region: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    us_county: Optional[str] = None
    tx_pwr: Optional[str] = None
    ant: Optional[str] = None
    qsl_rcvd: Optional[str] = None
    qsl_sent: Optional[str] = None
    lotw_member: Optional[bool] = None
    qsl_manager: Optional[str] = None
    email: Optional[str] = None
    prop_mode: Optional[str] = None
    ant_path: Optional[str] = None
    sat_name: Optional[str] = None
    sat_mode: Optional[str] = None
    freq_rx: Optional[str] = None
    mode_rx: Optional[str] = None
    qso_key: Optional[str] = None


def build_qso_dedupe_key(qso_data: Dict[str, Any]) -> str:
    """Build a stable logical key used to make QSO logging restart-safe."""
    return _build_qso_dedupe_key(qso_data, bucket_seconds=300, include_reports=True)


def build_qso_loose_dedupe_key(qso_data: Dict[str, Any]) -> str:
    """Build a broader duplicate key for repeated digital-mode logged-ADIF events."""
    return _build_qso_dedupe_key(qso_data, bucket_seconds=900, include_reports=False)


def build_qso_loose_dedupe_keys(qso_data: Dict[str, Any]) -> list[str]:
    """Build loose duplicate keys across adjacent buckets for near-boundary repeats."""
    keys: list[str] = []
    for bucket_offset in (-1, 0, 1):
        key = _build_qso_dedupe_key(
            qso_data,
            bucket_seconds=900,
            include_reports=False,
            bucket_offset=bucket_offset,
        )
        if key not in keys:
            keys.append(key)
    return keys


def normalise_digital_qso_mode(qso_data: Dict[str, Any]) -> str:
    """Return the logical FT mode for duplicate/status checks, not ADIF's raw family."""
    mode = str(qso_data.get("mode") or "").strip().upper()
    submode = str(qso_data.get("submode") or qso_data.get("mode_rx") or "").strip().upper()
    if submode in _WSJT_DIGITAL_MODES:
        return submode
    if mode in _WSJT_DIGITAL_MODES:
        return mode
    if mode == "MFSK":
        text = " ".join(
            str(qso_data.get(field) or "").upper()
            for field in ("notes", "comment", "comments")
        )
        for candidate in ("FT4", "FT8", "FT2"):
            if candidate in text:
                return candidate
    return mode


def _qso_modes_duplicate_compatible(requested_mode: str, existing_mode: str) -> bool:
    requested = (requested_mode or "").strip().upper()
    existing = (existing_mode or "").strip().upper()
    if not requested or not existing or requested == existing:
        return True
    if requested in _WSJT_DIGITAL_MODES and existing == "MFSK":
        return True
    if requested == "MFSK" and existing in _WSJT_DIGITAL_MODES:
        return True
    return False


def _build_qso_dedupe_key(
    qso_data: Dict[str, Any],
    *,
    bucket_seconds: int,
    include_reports: bool,
    bucket_offset: int = 0,
) -> str:
    callsign = str(qso_data.get("callsign") or qso_data.get("call") or "").strip().upper()
    own_call = str(qso_data.get("station_callsign") or config.MY_STATION or "").strip().upper()
    mode = normalise_digital_qso_mode(qso_data)
    frequency = float(qso_data.get("frequency") or qso_data.get("freq") or 0)
    band = str(qso_data.get("band") or "").strip().lower()
    if not band and frequency:
        try:
            from radio_control.spot_processor import band_from_khz
            band = band_from_khz(frequency * 1000).lower()
        except Exception:
            band = ""

    timestamp = qso_data.get("date_time") or ""
    if not timestamp:
        date_value = str(qso_data.get("date") or "").strip()
        time_value = str(qso_data.get("time_off") or "").strip()
        timestamp = f"{date_value}T{time_value}" if date_value and time_value else ""
    try:
        dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)
    bucket = int(dt.timestamp() // bucket_seconds) + int(bucket_offset)

    payload = {
        "dx": callsign,
        "own": own_call,
        "band": band,
        "mode": mode,
        "bucket": bucket,
    }
    if include_reports:
        payload["freq"] = round(frequency, 3)
        payload["rst_sent"] = str(qso_data.get("rst_sent") or "").strip()
        payload["rst_received"] = str(qso_data.get("rst_received") or qso_data.get("rst_rcvd") or "").strip()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "qso:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def _enrich_qso_from_qrz(qso_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing log fields from QRZ without making logging depend on QRZ."""
    global qrz_client

    callsign = str(qso_dict.get("callsign") or qso_dict.get("call") or "").strip().upper()
    if not callsign:
        return qso_dict

    needs_enrichment = any(
        not str(qso_dict.get(field) or "").strip()
        for field in ("name", "gridsquare", "state", "country", "email")
    ) or not qso_dict.get("cq_zone") or not qso_dict.get("itu_zone")
    if not needs_enrichment:
        return qso_dict

    try:
        if not qrz_client:
            qrz_client = QRZClient()
        profile = await asyncio.wait_for(qrz_client.lookup(callsign), timeout=7)
    except Exception as exc:
        logger.debug("QRZ enrichment skipped for %s: %s", callsign, exc)
        return qso_dict

    if not profile.get("success"):
        logger.debug("QRZ enrichment unavailable for %s: %s", callsign, profile.get("message"))
        return qso_dict

    field_map = {
        "name": "fname",
        "gridsquare": "grid",
        "state": "state",
        "country": "country",
        "email": "email",
        "cq_zone": "cqzone",
        "itu_zone": "ituzone",
        "lotw_member": "lotw",
    }
    for qso_field, profile_field in field_map.items():
        if qso_dict.get(qso_field) in (None, "", 0):
            value = profile.get(profile_field)
            if value not in (None, ""):
                if qso_field in {"cq_zone", "itu_zone"}:
                    try:
                        qso_dict[qso_field] = int(value)
                    except (TypeError, ValueError):
                        continue
                else:
                    qso_dict[qso_field] = value

    logger.info("✅ QRZ enrichment applied for %s", callsign)
    return qso_dict


def _load_dedupe_ledger() -> Dict[str, Any]:
    if _dedupe_ledger_path is None:
        return {}
    if not _dedupe_ledger_path.exists():
        return {}
    try:
        data = json.loads(_dedupe_ledger_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.warning("Unable to read QSO dedupe ledger %s", _dedupe_ledger_path, exc_info=True)
        return {}


def _save_dedupe_ledger(ledger: Dict[str, Any]) -> None:
    if _dedupe_ledger_path is None:
        return
    _dedupe_ledger_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _dedupe_ledger_path.with_suffix(_dedupe_ledger_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(_dedupe_ledger_path)


def _dedupe_entry(qso_key: str) -> Optional[Dict[str, Any]]:
    with _dedupe_lock:
        entry = _load_dedupe_ledger().get(qso_key)
        return entry if isinstance(entry, dict) else None


def _prune_pending_dedupe_claims(now_ts: Optional[float] = None) -> None:
    now_ts = now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp()
    expired = [
        key
        for key, entry in _pending_dedupe_claims.items()
        if now_ts - float(entry.get("claimed_ts") or 0) > _PENDING_DEDUPE_TTL_SECONDS
    ]
    for key in expired:
        _pending_dedupe_claims.pop(key, None)


def _claim_dedupe_keys(qso_keys: list[str], qso_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Claim all equivalent QSO keys before upload so parallel log paths cannot double-post."""
    keys = [str(key or "").strip() for key in qso_keys if str(key or "").strip()]
    if not keys:
        return None
    with _dedupe_lock:
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        _prune_pending_dedupe_claims(now_ts)
        ledger = _load_dedupe_ledger()
        for key in keys:
            entry = ledger.get(key)
            if isinstance(entry, dict):
                return entry
        for key in keys:
            entry = _pending_dedupe_claims.get(key)
            if isinstance(entry, dict):
                return entry

        claim = {
            "pending": True,
            "claimed_at": now.isoformat(),
            "claimed_ts": now_ts,
            "callsign": str(qso_data.get("callsign") or qso_data.get("call") or "").upper(),
            "own_call": str(config.MY_STATION or "").upper(),
            "frequency": qso_data.get("frequency"),
            "band": qso_data.get("band") or "",
            "mode": normalise_digital_qso_mode(qso_data),
            "date_time": qso_data.get("date_time") or "",
            "wavelog_success": False,
            "adif_saved": False,
            "outbox_queued": False,
        }
        for key in keys:
            _pending_dedupe_claims[key] = claim
        return None


def _release_dedupe_keys(qso_keys: list[str]) -> None:
    keys = [str(key or "").strip() for key in qso_keys if str(key or "").strip()]
    if not keys:
        return
    with _dedupe_lock:
        for key in keys:
            _pending_dedupe_claims.pop(key, None)


def _record_dedupe_entries(qso_keys: list[str], qso_data: Dict[str, Any], result: Dict[str, Any]) -> None:
    keys = [str(key or "").strip() for key in qso_keys if str(key or "").strip()]
    if not keys:
        return
    wavelog_result = result.get("wavelog") or {}
    durable = bool(wavelog_result.get("success") or result.get("outbox_queued"))
    if not durable:
        _release_dedupe_keys(keys)
        return
    with _dedupe_lock:
        ledger = _load_dedupe_ledger()
        entry = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "callsign": str(qso_data.get("callsign") or "").upper(),
            "own_call": str(config.MY_STATION or "").upper(),
            "frequency": qso_data.get("frequency"),
            "band": qso_data.get("band") or "",
            "mode": normalise_digital_qso_mode(qso_data),
            "date_time": qso_data.get("date_time") or "",
            "rst_sent": qso_data.get("rst_sent") or "",
            "rst_received": qso_data.get("rst_received") or "",
            "wavelog_success": bool((result.get("wavelog") or {}).get("success")),
            "adif_saved": bool(result.get("adif_saved")),
            "outbox_queued": bool(result.get("outbox_queued")),
        }
        for qso_key in keys:
            _pending_dedupe_claims.pop(qso_key, None)
            ledger[qso_key] = dict(entry)
        _save_dedupe_ledger(ledger)


def _record_dedupe_entry(qso_key: str, qso_data: Dict[str, Any], result: Dict[str, Any]) -> None:
    _record_dedupe_entries([qso_key], qso_data, result)


def _parse_adif_fields(adif_text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for match in re.finditer(r"<([^:>]+):(\d+)(?::[^>]*)?>", adif_text or ""):
        name = match.group(1).strip().lower()
        try:
            length = int(match.group(2))
        except ValueError:
            continue
        fields[name] = adif_text[match.end():match.end() + length].strip()
    return fields


def _qso_data_from_adif_record(adif_record: str) -> Dict[str, Any]:
    fields = _parse_adif_fields(adif_record)
    frequency = None
    try:
        if fields.get("freq"):
            frequency = float(fields["freq"])
    except (TypeError, ValueError):
        frequency = None
    qso_data = {
        "callsign": (fields.get("call") or "").upper(),
        "frequency": frequency,
        "band": fields.get("band") or "",
        "mode": (fields.get("submode") or fields.get("mode") or "").upper(),
        "submode": (fields.get("submode") or "").upper(),
        "gridsquare": (fields.get("gridsquare") or "").upper(),
        "dxcc": fields.get("dxcc") or None,
        "lotw_qsl_rcvd": fields.get("lotw_qsl_rcvd") or "",
        "qsl_rcvd": fields.get("qsl_rcvd") or "",
    }
    qso_data["mode"] = normalise_digital_qso_mode(qso_data)
    return qso_data


def _enrich_qso_with_cty(qso_dict: Dict[str, Any]) -> Dict[str, Any]:
    call = str(qso_dict.get("callsign") or qso_dict.get("call") or "").strip().upper()
    if not call or not cty_resolver:
        return qso_dict
    try:
        info = cty_resolver.lookup(call) or {}
    except Exception as exc:
        logger.debug("CTY QSO enrichment skipped for %s: %s", call, exc)
        return qso_dict

    if info.get("dxcc") and not qso_dict.get("dxcc"):
        qso_dict["dxcc"] = info.get("dxcc")
    if info.get("country") and not qso_dict.get("country"):
        qso_dict["country"] = info.get("country")
    if info.get("continent") and not qso_dict.get("continent"):
        qso_dict["continent"] = info.get("continent")
    if info.get("cq") and not qso_dict.get("cq_zone"):
        qso_dict["cq_zone"] = info.get("cq")
    if info.get("itu") and not qso_dict.get("itu_zone"):
        qso_dict["itu_zone"] = info.get("itu")
    return qso_dict


def _record_qso_status(qso_dict: Dict[str, Any]) -> None:
    if not qso_status_store or not hasattr(qso_status_store, "record_qso"):
        return
    try:
        enriched = _enrich_qso_with_cty(dict(qso_dict))
        if qso_status_store.record_qso(enriched):
            logger.info("✅ Local QSO status cache updated for %s", enriched.get("callsign"))
    except Exception as exc:
        logger.debug("Unable to update local QSO status cache for %s: %s", qso_dict.get("callsign"), exc)


def _coerce_optional_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_log_datetime(qso_dict: Dict[str, Any]) -> tuple[Optional[str], Optional[datetime], Optional[datetime], Optional[datetime]]:
    date_time_value = qso_dict.get("date_time") or qso_dict.get("qso_datetime")
    parsed_dt = None
    if date_time_value:
        try:
            parsed_dt = datetime.fromisoformat(str(date_time_value).replace("Z", "+00:00"))
            if parsed_dt.tzinfo is not None:
                parsed_dt = parsed_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            parsed_dt = None

    qso_date = _format_qso_date(qso_dict.get("date") or qso_dict.get("qso_date") or parsed_dt)
    time_value = qso_dict.get("time_on") or qso_dict.get("time_off") or parsed_dt
    time_text = _format_qso_time(time_value)
    if parsed_dt is None and qso_date and time_text:
        try:
            parsed_dt = datetime.strptime(f"{qso_date}{time_text[:6]}", "%Y%m%d%H%M%S")
        except ValueError:
            parsed_dt = None
    return qso_date or None, parsed_dt, parsed_dt, parsed_dt


def write_qso_to_postgres_read_cache(qso_dict: Dict[str, Any]) -> bool:
    """Write one logged QSO into the PostgreSQL read cache when PostgreSQL is active."""
    if not should_use_postgres():
        return False

    qso = _enrich_qso_with_cty(dict(qso_dict))
    call = str(qso.get("callsign") or qso.get("call") or "").strip().upper()
    if not call:
        return False

    qso_date, time_on, time_off, qso_datetime = _parse_log_datetime(qso)
    mode = normalise_digital_qso_mode(qso) or None
    submode = str(qso.get("submode") or "").strip().upper() or None
    band = str(qso.get("band") or "").strip() or None
    try:
        with connect_postgres() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO qso_records (
                        call, qso_date, time_on, time_off, qso_datetime, mode, submode,
                        frequency, band, rst_sent, rst_rcvd, name, qth, state, county,
                        gridsquare, pota_ref, sota_ref, iota, wwff_ref, sig, sig_info,
                        comment, country, dxcc, cqz, ituz, continent, lotw_qsl_sent,
                        lotw_qsl_rcvd, eqsl_qsl_sent, eqsl_qsl_rcvd, qsl_sent, qsl_rcvd,
                        tx_pwr, operator, station_callsign, station_id, creation_date,
                        last_modified, sync_timestamp
                    )
                    SELECT
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, now(),
                        now(), now()
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM qso_records
                        WHERE upper(call) = upper(%s)
                          AND COALESCE(qso_date, '') = COALESCE(%s, '')
                          AND COALESCE(band, '') = COALESCE(%s, '')
                          AND COALESCE(mode, '') = COALESCE(%s, '')
                          AND (
                              %s IS NULL
                              OR qso_datetime IS NULL
                              OR ABS(EXTRACT(EPOCH FROM (qso_datetime - %s))) < 300
                          )
                    )
                    """,
                    (
                        call,
                        qso_date,
                        time_on,
                        time_off,
                        qso_datetime,
                        mode,
                        submode,
                        _coerce_optional_float(qso.get("frequency") or qso.get("freq")),
                        band,
                        qso.get("rst_sent") or "",
                        qso.get("rst_received") or qso.get("rst_rcvd") or "",
                        qso.get("name") or "",
                        qso.get("qth") or "",
                        qso.get("state") or "",
                        qso.get("us_county") or qso.get("county") or "",
                        qso.get("gridsquare") or qso.get("grid") or "",
                        qso.get("pota") or qso.get("pota_ref") or "",
                        qso.get("sota") or qso.get("sota_ref") or "",
                        qso.get("iota") or "",
                        qso.get("wwff") or qso.get("wwff_ref") or "",
                        qso.get("sig") or "",
                        qso.get("sig_info") or "",
                        qso.get("notes") or qso.get("comment") or "",
                        qso.get("country") or "",
                        _coerce_optional_int(qso.get("dxcc") or qso.get("dxcc_id")),
                        _coerce_optional_int(qso.get("cq_zone") or qso.get("cqz")),
                        _coerce_optional_int(qso.get("itu_zone") or qso.get("ituz")),
                        qso.get("continent") or "",
                        qso.get("lotw_qsl_sent") or "",
                        qso.get("lotw_qsl_rcvd") or "",
                        qso.get("eqsl_qsl_sent") or "",
                        qso.get("eqsl_qsl_rcvd") or "",
                        qso.get("qsl_sent") or "",
                        qso.get("qsl_rcvd") or "",
                        _coerce_optional_float(qso.get("tx_pwr")),
                        qso.get("operator") or "",
                        qso.get("station_callsign") or config.MY_STATION or "",
                        _coerce_optional_int(qso.get("station_id") or getattr(config, "WAVELOG_STATION_ID", 1)),
                        call,
                        qso_date,
                        band,
                        mode,
                        qso_datetime,
                        qso_datetime,
                    ),
                )
                inserted = cur.rowcount > 0
            conn.commit()
        if inserted:
            logger.info("✅ PostgreSQL QSO read cache write-through inserted %s", call)
        return bool(inserted)
    except Exception as exc:
        logger.debug("PostgreSQL QSO read cache write-through skipped for %s: %s", call, exc, exc_info=True)
        return False


def record_qso_in_local_read_cache(qso_dict: Dict[str, Any]) -> None:
    """Update both hot in-memory and PostgreSQL read-cache status for a logged QSO."""
    _record_qso_status(qso_dict)
    write_qso_to_postgres_read_cache(qso_dict)


def record_qso_status_from_adif(adif_record: str) -> None:
    """Record one resolved outbox ADIF record in the hot local status cache."""
    qso_data = _qso_data_from_adif_record(adif_record)
    if qso_data.get("callsign"):
        record_qso_in_local_read_cache(qso_data)


class RecentQSOsRequest(BaseModel):
    callsign: str
    limit: int = 5


def _format_qso_date(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10].replace("-", "")
    return text.replace("-", "")[:8]


def _format_qso_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H%M%S")
    if isinstance(value, time):
        return value.strftime("%H%M%S")
    text = str(value or "").strip()
    if not text:
        return ""
    if " " in text:
        text = text.split(" ", 1)[1]
    return text.replace(":", "")[:6]


def _format_recent_qso_rows(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    qsos: list[dict[str, Any]] = []
    for row in rows:
        (
            call,
            qso_date,
            time_on,
            mode,
            submode,
            frequency,
            band,
            rst_sent,
            rst_rcvd,
            lotw_qsl_rcvd,
            country,
            gridsquare,
            name,
        ) = row
        qsos.append(
            {
                "call": (call or "").upper(),
                "qso_date": _format_qso_date(qso_date),
                "time_on": _format_qso_time(time_on),
                "mode": (submode or mode or "").upper(),
                "frequency": frequency or 0,
                "rst_sent": rst_sent or "",
                "rst_rcvd": rst_rcvd or "",
                "band": band or "",
                "lotw_qsl": "Y"
                if str(lotw_qsl_rcvd or "").strip().upper() in {"Y", "YES", "1", "TRUE"}
                else "N",
                "country": country or "",
                "gridsquare": gridsquare or "",
                "name": name or "",
            }
        )
    return qsos


def _get_recent_qsos_from_duckdb(callsign: str, limit: int) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit or 5), 100))
    if should_use_postgres():
        with connect_postgres() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT call, qso_date, time_on, mode, submode, frequency, band,
                           rst_sent, rst_rcvd, lotw_qsl_rcvd, country, gridsquare, name
                    FROM qso_records
                    WHERE UPPER(call) = UPPER(%s)
                    ORDER BY COALESCE(qso_datetime, time_on) DESC
                    LIMIT %s
                    """,
                    (callsign, normalized_limit),
                )
                return _format_recent_qso_rows(cur.fetchall())

    db_path = config.DATA_DIR / "qso_log.duckdb"
    if not db_path.exists():
        return []

    conn = duckdb.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT call, qso_date, time_on, mode, submode, frequency, band,
                   rst_sent, rst_rcvd, lotw_qsl_rcvd, country, gridsquare, name
            FROM qso_records
            WHERE UPPER(call) = UPPER(?)
            ORDER BY COALESCE(qso_datetime, time_on) DESC
            LIMIT ?
            """,
            [callsign, normalized_limit],
        ).fetchall()
        return _format_recent_qso_rows(rows)
    finally:
        conn.close()


def _get_recent_qsos_from_wavelog_db(callsign: str, limit: int) -> list[dict[str, Any]]:
    service = get_wavelog_log_service()
    result = service.search_callsign(callsign, limit=max(1, min(int(limit or 5), 100)))
    qsos: list[dict[str, Any]] = []
    for qso in result.get("qsos", []):
        time_on_raw = str(qso.get("time_on") or "")
        qso_date = ""
        time_on = ""
        if " " in time_on_raw:
            date_part, time_part = time_on_raw.split(" ", 1)
            qso_date = _format_qso_date(date_part)
            time_on = _format_qso_time(time_part)
        else:
            qso_date = _format_qso_date(time_on_raw)

        qsos.append(
            {
                "call": (qso.get("callsign") or callsign).upper(),
                "qso_date": qso_date,
                "time_on": time_on,
                "mode": (qso.get("submode") or qso.get("mode") or "").upper(),
                "frequency": qso.get("frequency") or 0,
                "rst_sent": qso.get("rst_sent") or "",
                "rst_rcvd": qso.get("rst_rcvd") or "",
                "band": qso.get("band") or "",
                "lotw_qsl": "Y" if str(qso.get("lotw_rcvd") or "").strip().upper() == "Y" else "N",
                "country": qso.get("country") or "",
                "gridsquare": qso.get("gridsquare") or "",
                "name": qso.get("name") or "",
            }
        )
    return qsos


def _recent_qso_datetime(qso: Dict[str, Any]) -> Optional[datetime]:
    date_value = _format_qso_date(qso.get("qso_date") or qso.get("date"))
    time_value = _format_qso_time(qso.get("time_on") or qso.get("time_off"))
    if not date_value or not time_value:
        return None
    try:
        return datetime.strptime(f"{date_value}{time_value[:6]}", "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _recent_wavelog_duplicate_entry(qso_dict: Dict[str, Any], *, window_seconds: int = 1800) -> Optional[Dict[str, Any]]:
    call = str(qso_dict.get("callsign") or qso_dict.get("call") or "").strip().upper()
    if not call:
        return None
    requested_band = str(qso_dict.get("band") or "").strip().lower()
    requested_mode = normalise_digital_qso_mode(qso_dict)
    _, requested_dt, _, _ = _parse_log_datetime(qso_dict)
    if requested_dt is None:
        return None

    recent: list[dict[str, Any]] = []
    for fetcher in (_get_recent_qsos_from_duckdb, _get_recent_qsos_from_wavelog_db):
        try:
            recent.extend(fetcher(call, 20))
        except Exception as exc:
            logger.debug("Recent QSO duplicate lookup skipped for %s via %s: %s", call, fetcher.__name__, exc)

    for existing in recent:
        existing_call = str(existing.get("call") or existing.get("callsign") or "").strip().upper()
        existing_band = str(existing.get("band") or "").strip().lower()
        existing_mode = normalise_digital_qso_mode(existing)
        if existing_call and existing_call != call:
            continue
        if requested_band and existing_band and existing_band != requested_band:
            continue
        if not _qso_modes_duplicate_compatible(requested_mode, existing_mode):
            continue
        existing_dt = _recent_qso_datetime(existing)
        if existing_dt is None:
            continue
        if abs((requested_dt - existing_dt).total_seconds()) <= window_seconds:
            return {
                "recent_wavelog": True,
                "callsign": call,
                "band": existing.get("band") or qso_dict.get("band") or "",
                "mode": existing.get("mode") or qso_dict.get("mode") or "",
                "qso_date": existing.get("qso_date") or "",
                "time_on": existing.get("time_on") or "",
                "wavelog_success": True,
                "adif_saved": True,
                "outbox_queued": False,
            }
    return None


def init_qso_logging_clients(
    w_client: WavelogClient,
    q_client: QRZClient,
    a_handler: ADIFHandler,
    c_resolver: CtyDatResolver,
    status_store=None,
):
    """Initialize the global clients for QSO logging"""
    global wavelog_client, qrz_client, adif_handler, cty_resolver, qso_status_store
    wavelog_client = w_client
    qrz_client = q_client
    adif_handler = a_handler
    cty_resolver = c_resolver
    qso_status_store = status_store
    logger.info("✅ QSO logging clients initialized")


@router.post("/api/qso/log")
async def log_qso(qso: QSORequest):
    """Log a QSO to Wavelog and local ADIF file"""
    global wavelog_client, adif_handler

    try:
        logger.info(f"📝 QSO Log Request - Callsign: {qso.callsign}, Freq: {qso.frequency}, Mode: {qso.mode}, RST_sent: {qso.rst_sent}, RST_rcvd: {qso.rst_received}")

        # Initialize clients if needed (with error handling)
        try:
            if not wavelog_client:
                logger.debug("🔌 Initializing WavelogClient...")
                wavelog_client = WavelogClient()
                logger.info("✅ WavelogClient initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WavelogClient: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to initialize Wavelog client: {str(e)}")

        try:
            if not adif_handler:
                logger.debug("🔌 Initializing ADIFHandler...")
                adif_handler = ADIFHandler()
                logger.info("✅ ADIFHandler initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ADIFHandler: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to initialize ADIF handler: {str(e)}")

        # Convert request to dict and preserve RST values as-is
        # They can be strings (FT8 SNR like "-12") or will be converted by wavelog_api
        qso_dict = qso.model_dump(exclude_unset=False)  # Include all fields
        qso_dict = await _enrich_qso_from_qrz(qso_dict)
        qso_dict = _enrich_qso_with_cty(qso_dict)
        requested_qso_key = qso_dict.get("qso_key")
        qso_key = requested_qso_key or build_qso_dedupe_key(qso_dict)
        loose_qso_keys = build_qso_loose_dedupe_keys(qso_dict)
        loose_qso_key = loose_qso_keys[1] if len(loose_qso_keys) > 1 else build_qso_loose_dedupe_key(qso_dict)
        qso_dict["qso_key"] = qso_key
        dedupe_keys = [qso_key, *loose_qso_keys]

        dedupe_entry = _claim_dedupe_keys(dedupe_keys, qso_dict)
        if dedupe_entry:
            logger.info("Skipping duplicate QSO log request for stable key %s / %s (%s)", qso_key, loose_qso_key, qso.callsign)
            record_qso_in_local_read_cache(qso_dict)
            return {
                "success": True,
                "message": "Duplicate QSO log request ignored",
                "duplicate": True,
                "qso_key": qso_key,
                "loose_qso_key": loose_qso_key,
                "dedupe": dedupe_entry,
                "wavelog": {"success": bool(dedupe_entry.get("wavelog_success"))},
                "adif_saved": bool(dedupe_entry.get("adif_saved")),
                "outbox_queued": bool(dedupe_entry.get("outbox_queued")),
                "outbox": get_qso_outbox().status(),
            }
        notes = str(qso_dict.get("notes") or qso_dict.get("comment") or "").lower()
        should_check_recent_wavelog = bool(requested_qso_key) or "built-in digital" in notes
        recent_duplicate = _recent_wavelog_duplicate_entry(qso_dict) if should_check_recent_wavelog else None
        if recent_duplicate:
            logger.info("Skipping QSO log already present in Wavelog/read-cache for %s on %s %s", qso.callsign, qso.band, qso.mode)
            try:
                adif_saved = bool(adif_handler.add_qso(qso_dict))
            except Exception:
                logger.warning("Unable to archive Wavelog duplicate locally", exc_info=True)
                adif_saved = False
            _record_dedupe_entries(dedupe_keys, qso_dict, {"wavelog": {"success": True}, "adif_saved": adif_saved})
            record_qso_in_local_read_cache(qso_dict)
            return {
                "success": True,
                "message": "QSO already present in Wavelog/read-cache",
                "duplicate": True,
                "qso_key": qso_key,
                "loose_qso_key": loose_qso_key,
                "dedupe": recent_duplicate,
                "wavelog": {"success": True},
                "adif_saved": adif_saved,
                "outbox_queued": False,
                "outbox": get_qso_outbox().status(),
            }

        # Don't override RST values here - let wavelog_api handle the conversion
        # It will use 599 as default for empty values
        logger.debug(f"QSO dict: {qso_dict}")

        # Log to Wavelog API with error handling
        try:
            logger.debug("📤 Sending QSO to Wavelog API...")
            wavelog_result = await wavelog_client.log_qso(qso_dict)
            logger.debug(f"✅ Wavelog result: {wavelog_result}")
        except Exception as e:
            logger.error(f"❌ Wavelog API call failed: {str(e)}", exc_info=True)
            wavelog_result = {'success': False, 'message': f'Wavelog error: {str(e)}'}

        # Always save to local ADIF file (backup/archive)
        try:
            adif_saved = adif_handler.add_qso(qso_dict)
            if not adif_saved:
                logger.warning(f"Failed to save QSO to ADIF file after retries: {qso.callsign}")
        except Exception as e:
            logger.error(f"ADIF save failed: {str(e)}", exc_info=True)
            adif_saved = False

        outbox_queued = False
        if not wavelog_result.get('success'):
            reason = wavelog_result.get('message') or wavelog_result.get('error') or 'Wavelog upload failed'
            outbox_queued = get_qso_outbox().enqueue(qso_dict, reason=reason)

        logger.info(
            "✅ QSO processed: %s on %s MHz (Wavelog: %s, ADIF: %s, Outbox: %s)",
            qso.callsign,
            qso.frequency,
            wavelog_result.get('success'),
            adif_saved,
            outbox_queued,
        )

        response = {
            "success": wavelog_result.get('success', False) or outbox_queued,
            "message": wavelog_result.get('message', 'QSO logged successfully'),
            "wavelog": wavelog_result,
            "adif_saved": adif_saved,
            "outbox_queued": outbox_queued,
            "outbox": get_qso_outbox().status(),
            "qso_key": qso_key,
            "loose_qso_key": loose_qso_key,
        }
        if wavelog_result.get("success") or outbox_queued:
            _record_dedupe_entries(dedupe_keys, qso_dict, response)
        else:
            _release_dedupe_keys(dedupe_keys)
        if response["success"]:
            record_qso_in_local_read_cache(qso_dict)
        return response

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected QSO logging error: {str(e)}", exc_info=True)
        logger.error("   Full traceback available above", exc_info=False)
        raise HTTPException(
            status_code=500,
            detail=f"QSO logging failed: {type(e).__name__}: {str(e)}"
        )


@router.get("/api/qrz/profile/{callsign:path}")
async def get_qrz_profile(callsign: str):
    """Get QRZ profile picture and info for a callsign"""
    global qrz_client

    try:
        if not qrz_client:
            qrz_client = QRZClient()

        result = await asyncio.wait_for(qrz_client.get_profile_picture(callsign), timeout=9)

        if result.get('success'):
            logger.info(f"✅ QRZ profile retrieved for {callsign}")
        else:
            logger.warning(f"QRZ profile not found for {callsign}")

        return result

    except asyncio.TimeoutError:
        logger.warning("QRZ profile lookup timed out for %s", callsign)
        return {'success': False, 'message': 'QRZ lookup timed out'}
    except Exception as e:
        logger.error(f"QRZ profile error: {str(e)}")
        return {'success': False, 'message': str(e)}


@router.get("/api/qrz/history/{callsign:path}")
async def get_qrz_history(callsign: str, limit: int = 20):
    """Get QRZ contact history for a callsign"""
    global qrz_client

    try:
        if not qrz_client:
            qrz_client = QRZClient()

        result = await asyncio.wait_for(qrz_client.get_contact_history(callsign, limit), timeout=9)
        return result

    except asyncio.TimeoutError:
        logger.warning("QRZ history lookup timed out for %s", callsign)
        return {'success': False, 'data': [], 'message': 'QRZ history lookup timed out'}
    except Exception as e:
        logger.error(f"QRZ history error: {str(e)}")
        return {'success': False, 'data': []}


@router.post("/api/wavelog/private_lookup")
async def wavelog_private_lookup(data: dict):
    """
    Perform private lookup in Wavelog logbook for a callsign
    Returns comprehensive info including worked/confirmed status by band/mode
    Enhanced with DXCC entity name and geographic data for country modal
    """
    global wavelog_client, cty_resolver

    try:
        if not wavelog_client:
            wavelog_client = WavelogClient()

        callsign = data.get('callsign', '').strip().upper()
        band = data.get('band', '')
        mode = data.get('mode', '')

        if not callsign:
            return {'success': False, 'message': 'Callsign required'}

        result = await asyncio.wait_for(
            wavelog_client.private_lookup(callsign, band or None, mode or None),
            timeout=9,
        )

        # Enrich response with DXCC entity name and geographic data
        if result.get('success') and result.get('data'):
            response_data = result['data']

            # Try to get DXCC info using cty_resolver
            if cty_resolver:
                try:
                    info = cty_resolver.lookup(callsign)
                    if info:
                        # Add DXCC entity name (country name)
                        if 'country' in info and not response_data.get('dxcc_entity'):
                            response_data['dxcc_entity'] = info['country']

                        # Add continent
                        if 'continent' in info and not response_data.get('continent'):
                            response_data['continent'] = info['continent']

                        # Add CQ zone
                        if 'cq' in info and not response_data.get('cq'):
                            response_data['cq'] = info['cq']

                        # Add DXCC ID
                        if 'dxcc' in info and not response_data.get('dxcc'):
                            response_data['dxcc'] = info['dxcc']

                        # Add ITU zone
                        if 'itu' in info and not response_data.get('itu'):
                            response_data['itu'] = info['itu']

                        # Add latitude/longitude
                        if 'latitude' in info and not response_data.get('latitude'):
                            response_data['latitude'] = info['latitude']
                        if 'longitude' in info and not response_data.get('longitude'):
                            response_data['longitude'] = info['longitude']

                        # Add grid square
                        if 'grid' in info and not response_data.get('grid'):
                            response_data['grid'] = info['grid']

                        logger.debug(f"✅ Enhanced DXCC lookup for {callsign}: {info}")
                except Exception as e:
                    logger.debug(f"Could not enrich DXCC data for {callsign}: {e}")

        return result

    except asyncio.TimeoutError:
        logger.warning("Wavelog private lookup timed out for %s", data.get('callsign', ''))
        return {'success': False, 'message': 'Wavelog lookup timed out'}
    except Exception as e:
        logger.error(f"Wavelog private lookup error: {str(e)}")
        return {'success': False, 'message': str(e)}


@router.post("/api/wavelog/recent_qsos")
async def wavelog_recent_qsos(req: RecentQSOsRequest):
    """
    Get recent QSOs with a specific callsign from Wavelog API.
    Uses Wavelog's api/get_contacts_adif endpoint to fetch QSO history.
    Returns last N QSOs (default 5) with date, band, mode, RST, LoTW status, etc.

    Response format (per QSO):
    {
        "call": "OM0AAO",
        "qso_date": "20251014",
        "time_on": "174200",
        "mode": "SSB",
        "frequency": 14.074,
        "rst_sent": "599",
        "rst_rcvd": "599",
        "band": "20m",
        "lotw_qsl": "Y"
    }
    """
    global adif_handler, wavelog_client

    try:
        callsign = req.callsign.strip().upper()
        limit = req.limit

        logger.info(f"🔍 Recent QSOs request for {callsign} (limit={limit})")

        if not callsign:
            return {'success': False, 'message': 'Callsign required'}

        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(_get_recent_qsos_from_wavelog_db, callsign, limit),
                timeout=3,
            )
        except Exception as db_error:
            logger.debug("Direct Wavelog QSO lookup failed for %s, trying read cache: %s", callsign, db_error)
            data = await asyncio.wait_for(
                asyncio.to_thread(_get_recent_qsos_from_duckdb, callsign, limit),
                timeout=2,
            )

        if data:
            logger.info(f"✅ Found {len(data)} recent QSOs for {callsign}")
            # Validate that all required fields are present
            required_fields = ['call', 'qso_date', 'mode', 'rst_sent', 'rst_rcvd', 'band', 'lotw_qsl']
            for qso in data:
                missing = [f for f in required_fields if f not in qso]
                if missing:
                    logger.debug(f"  QSO missing fields: {missing}")

            return {'success': True, 'data': data}
        else:
            logger.debug(f"ℹ️ No recent QSOs found for {callsign} in Wavelog read cache")
            return {'success': True, 'data': []}

    except asyncio.TimeoutError:
        logger.warning("Recent QSO lookup timed out for %s", req.callsign)
        return {'success': False, 'message': 'Previous QSO lookup timed out', 'data': []}
    except Exception as e:
        logger.error(f"❌ Recent QSOs error for {req.callsign}: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
        return {'success': False, 'message': str(e)}


@router.get("/api/qso/outbox/status")
async def qso_outbox_status():
    """Return the offline Wavelog upload outbox status."""
    return {"success": True, "outbox": get_qso_outbox().status()}


@router.get("/api/qso/worked-status")
async def qso_worked_status():
    """Return only non-sensitive worked matching fields from the local archive."""
    global adif_handler
    handler = adif_handler or ADIFHandler()
    records = await asyncio.to_thread(handler.read_all_qsos)
    worked = [
        {
            "call": str(record.get("call") or "").upper(),
            "band": str(record.get("band") or "").lower(),
            "mode": str(record.get("mode") or record.get("submode") or "").upper(),
            "qso_date": str(record.get("qso_date") or ""),
        }
        for record in records
        if record.get("call")
    ]
    return {"success": True, "data": worked, "count": len(worked)}


@router.post("/api/qso/outbox/retry")
async def retry_qso_outbox(max_records: int = 20):
    """Retry queued Wavelog uploads from the offline ADIF outbox."""
    global wavelog_client
    if not wavelog_client:
        wavelog_client = WavelogClient()
    result = await get_qso_outbox().replay(
        wavelog_client,
        max_records=max_records,
        on_resolved_record=record_qso_status_from_adif,
    )
    return {"success": result.get("success", False), "result": result, "outbox": get_qso_outbox().status()}


@router.get("/api/wavelog/contacts")
async def get_wavelog_contacts(limit: int = 100):
    """Get recent contacts directly from Wavelog API (fresh data, not cached)"""
    global wavelog_client
    
    try:
        if not wavelog_client:
            wavelog_client = WavelogClient()
        
        # Fetch directly from Wavelog API for fresh, up-to-date contacts
        result = await wavelog_client.get_contacts_from_wavelog_api(limit)
        
        if result.get('success'):
            contact_count = len(result.get('data', []))
            logger.info(f"✅ Retrieved {contact_count} fresh contacts from Wavelog API (limit: {limit})")
            return result
        else:
            logger.warning(f"Failed to retrieve contacts from API: {result.get('message', 'Unknown error')}")
            # Return empty success response instead of error
            return {'success': True, 'data': []}
    
    except Exception as e:
        logger.error(f"Error fetching Wavelog contacts: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
        return {'success': True, 'data': []}


def register_qso_logging_endpoints(app):
    """Register all QSO logging endpoints with the FastAPI app"""
    app.include_router(router)
    logger.info("✅ QSO logging endpoints registered with FastAPI app")
