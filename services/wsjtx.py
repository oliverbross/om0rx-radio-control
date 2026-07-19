"""
WSJT-X Service Module

Extracted WSJT-X integration from main.py for modularization.
Includes auto-logging to Wavelog, QRZ data enrichment, and auto-rotation features.
"""

import logging
import asyncio
import json
import platform
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from typing import Optional, Dict, Any
from fastapi import Body, HTTPException, Request

# Import required modules
from radio_control.activity_references import extract_activity_references, reference_items_to_qso_fields
from radio_control.spot_processor import band_from_khz, infer_mode
from radio_control.qso_outbox import get_qso_outbox
from radio_control.spot_classification import classify_call_status, classify_dxcc_status
from radio_control import config
logger = logging.getLogger(__name__)


WSJT_TARGET_MODES = {"FT8", "FT4", "FT2"}
WSJT_MODE_PERIODS = {
    "FT8": 15,
    "FT4": 7,
    "FT2": 4,
}
WSJT_DEFAULT_DIAL_FREQUENCIES_HZ = {
    "FT8": {
        "160m": 1_840_000,
        "80m": 3_573_000,
        "60m": 5_357_000,
        "40m": 7_074_000,
        "30m": 10_136_000,
        "20m": 14_074_000,
        "17m": 18_100_000,
        "15m": 21_074_000,
        "12m": 24_915_000,
        "10m": 28_074_000,
        "6m": 50_313_000,
    },
    "FT4": {
        "80m": 3_575_000,
        "40m": 7_047_500,
        "30m": 10_140_000,
        "20m": 14_080_000,
        "17m": 18_104_000,
        "15m": 21_140_000,
        "12m": 24_919_000,
        "10m": 28_180_000,
    },
    "FT2": {
        "160m": 1_843_000,
        "80m": 3_578_000,
        "60m": 5_357_000,
        "40m": 7_052_000,
        "30m": 10_144_000,
        "20m": 14_084_000,
        "17m": 18_108_000,
        "15m": 21_144_000,
        "12m": 24_923_000,
        "10m": 28_184_000,
        "6m": 50_320_000,
        "2m": 144_177_000,
    },
}
GRID_RE = re.compile(r"^[A-R]{2}\d{2}([A-X]{2})?$")
NON_GRID_TOKENS = {"CQ", "DE", "QRZ", "RRR", "RR73", "73"}
WSJT_CLIENT_FRESH_MS = 300_000
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATCHED_ENGINE_BUILD_ROOT = PROJECT_ROOT / "data" / "build" / "wsjtx-improved-om0rx" / "build-msys"
PATCHED_ENGINE_RUN_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtx" / "run_om0rx_wsjtx.ps1"
WSJTZ_ENGINE_BUILD_ROOT = PROJECT_ROOT / "data" / "build" / "wsjt-z-clean" / "build-msys"
WSJTZ_ENGINE_RUN_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtz" / "run_clean_wsjtz.ps1"
PATCHED_ENGINE_MSYS_ROOT = Path(os.environ.get("WSJTX_MSYS_ROOT", r"C:\JTSDK64-Tools\tools\msys64"))
WSJTX_DECODE_CTY_CACHE_MAX = 4096
_wsjtx_decode_cty_cache: Dict[str, Dict[str, Any]] = {}


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalise_grid_value(value: Any) -> str:
    grid = str(value or "").strip().upper().strip("<>,;")
    if not grid or grid in NON_GRID_TOKENS:
        return ""
    return grid[:4] if GRID_RE.match(grid) else ""


def _parse_adif_fields(adif_text: Any) -> Dict[str, str]:
    """Parse one ADIF record, respecting ADIF field lengths."""
    fields: Dict[str, str] = {}
    if not isinstance(adif_text, str) or not adif_text.strip():
        return fields

    for match in re.finditer(r"<([^:>]+):(\d+)(?::[^>]*)?>", adif_text):
        name = match.group(1).strip().lower()
        try:
            length = int(match.group(2))
        except ValueError:
            continue
        value_start = match.end()
        fields[name] = adif_text[value_start:value_start + length].strip()
    return fields


def _ensure_adif_eor(adif_text: str) -> str:
    text = (adif_text or "").strip()
    if text and "<eor>" not in text.lower():
        text = f"{text} <eor>"
    return text


def _iso_from_adif_datetime(date_value: str, time_value: str) -> Optional[str]:
    date_digits = re.sub(r"\D", "", date_value or "")
    time_digits = re.sub(r"\D", "", time_value or "")
    if len(date_digits) != 8:
        return None
    time_digits = (time_digits + "000000")[:6]
    try:
        dt = datetime.strptime(f"{date_digits}{time_digits}", "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat()


def _frequency_hz_from_adif(fields: Dict[str, str]) -> Optional[int]:
    freq = _coerce_float(fields.get("freq"))
    if freq is not None:
        return int(round(freq * 1_000_000))
    freq_rx = _coerce_float(fields.get("freq_rx"))
    if freq_rx is not None:
        return int(round(freq_rx * 1_000_000))
    return None


def _frequency_hz_from_payload(req: Dict[str, Any]) -> Optional[int]:
    """Accept Hz, kHz, or MHz frequency fields and return integer Hz."""
    explicit_hz = _coerce_float(req.get("frequency_hz") or req.get("dialFrequency"))
    if explicit_hz is not None:
        return int(round(explicit_hz))

    explicit_khz = _coerce_float(req.get("frequency_khz"))
    if explicit_khz is not None:
        return int(round(explicit_khz * 1000))

    explicit_mhz = _coerce_float(req.get("frequency_mhz"))
    if explicit_mhz is not None:
        return int(round(explicit_mhz * 1_000_000))

    frequency = _coerce_float(req.get("frequency") or req.get("freq"))
    if frequency is None:
        return None
    if frequency >= 1_000_000:
        return int(round(frequency))
    if frequency >= 1000:
        return int(round(frequency * 1000))
    return int(round(frequency * 1_000_000))


def _first_present(req: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in req and req[key] not in (None, ""):
            return req[key]
    return None


def _normalise_status_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _default_wsjtx_dial_frequency_hz(band: Any, mode: Any) -> Optional[int]:
    mode_text = str(mode or "FT8").strip().upper() or "FT8"
    band_text = str(band or "").strip().lower()
    return WSJT_DEFAULT_DIAL_FREQUENCIES_HZ.get(mode_text, {}).get(band_text)


def _dxcc_priority_target(payload: Dict[str, Any]) -> bool:
    try:
        from services.digital_automation import payload_has_dxcc_hunt_interest

        return payload_has_dxcc_hunt_interest(payload)
    except Exception:
        dxcc_status = str(_first_present(payload, "dxcc_status", "dxccStatus") or "").strip().lower()
        return dxcc_status in {"atno", "worked"} or "new band" in dxcc_status or "new mode" in dxcc_status


def _reference_priority_target(payload: Dict[str, Any]) -> bool:
    try:
        from services.digital_automation import reference_is_needed, normalise_reference_items

        return any(reference_is_needed(item) for item in normalise_reference_items(payload))
    except Exception:
        return bool(extract_activity_references(payload))


def _automation_current_dial_frequency_hz(automation_payload: Dict[str, Any]) -> Optional[int]:
    return _frequency_hz_from_payload({
        "frequency_hz": _first_present(
            automation_payload,
            "currentDialFrequency",
            "current_dial_frequency",
            "dialFrequency",
            "frequency_hz",
        ),
        "frequency_mhz": _first_present(automation_payload, "currentFrequency", "current_frequency", "frequency_mhz"),
        "frequency": _first_present(automation_payload, "frequency"),
    })


def _direct_ft8_reply_tx_first(payload: Dict[str, Any]) -> Optional[bool]:
    """Return the TX parity for the slot immediately after a directed FT8 decode."""
    if not _coerce_bool(_first_present(payload, "direct_caller", "directCaller"), False):
        return None
    if str(_first_present(payload, "mode") or "FT8").strip().upper() != "FT8":
        return None
    heard_slot = _first_present(payload, "heard_slot_start_at", "heardSlotStartAt")
    if not heard_slot:
        return None
    try:
        parsed = datetime.fromisoformat(str(heard_slot).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    slot_seconds = parsed.second + (parsed.microsecond / 1_000_000.0)
    # A call heard in the odd FT8 slot (15/45) is answered in the next
    # even/first slot (00/30), and vice versa.
    return (slot_seconds % 30.0) >= 15.0


def _normalise_trace_id(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in text)[:80]


def _wsjtx_trace_id(req: Optional[Dict[str, Any]] = None) -> str:
    req = req or {}
    target = req.get("target") if isinstance(req.get("target"), dict) else {}
    existing = _first_present(
        req,
        "traceId",
        "trace_id",
        "correlationId",
        "correlation_id",
        "requestId",
        "request_id",
    ) or _first_present(
        target,
        "traceId",
        "trace_id",
        "correlationId",
        "correlation_id",
        "requestId",
        "request_id",
    )
    normalised = _normalise_trace_id(existing)
    return normalised or f"wsjtx-{uuid.uuid4().hex[:12]}"


def _command_url_to_status_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path.endswith("/command"):
        path = parsed.path[:-len("/command")] + "/status"
    else:
        path = parsed.path.rstrip("/") + "/status"
    return urlunparse(parsed._replace(path=path, query="", fragment=""))


def _format_age_ms(age_ms: Optional[int]) -> str:
    if age_ms is None:
        return "age unknown"
    seconds = max(0, round(age_ms / 1000))
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    return f"{minutes // 60}h ago"


def _normalise_bridge_timeline(raw_events: Any, now_ms: Optional[int] = None) -> list[Dict[str, Any]]:
    if not isinstance(raw_events, list):
        return []
    now_ms = now_ms or int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    normalised: list[Dict[str, Any]] = []
    for event in raw_events[-25:]:
        if not isinstance(event, dict):
            continue
        ts = _coerce_int(event.get("ts"))
        age_ms = max(0, now_ms - ts) if ts else None
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_client = event.get("client") if isinstance(event.get("client"), dict) else {}
        trace_id = _normalise_trace_id(_first_present(event, "traceId", "trace_id") or _first_present(payload, "traceId", "trace_id"))
        label_parts = [
            str(event.get("command") or event.get("type") or "event").strip(),
            str(event.get("dxCall") or event.get("call") or payload.get("call") or "").strip(),
            str(event.get("message") or "").strip(),
        ]
        label = " ".join(part for part in label_parts if part)
        normalised.append({
            "ts": ts,
            "age_ms": age_ms,
            "age": _format_age_ms(age_ms),
            "direction": str(event.get("direction") or "").strip() or "unknown",
            "type": str(event.get("type") or "").strip() or "event",
            "command": str(event.get("command") or "").strip(),
            "trace_id": trace_id,
            "success": event.get("success"),
            "error": str(event.get("error") or "").strip(),
            "bytes": _coerce_int(event.get("bytes")),
            "client_id": str(event.get("clientId") or event_client.get("id") or "").strip(),
            "label": label,
            "payload": payload,
            "message": str(event.get("message") or "").strip(),
            "dx_call": str(event.get("dxCall") or payload.get("call") or "").strip(),
            "dx_grid": str(event.get("dxGrid") or payload.get("grid") or "").strip(),
            "mode": str(event.get("mode") or payload.get("mode") or "").strip(),
            "dial_frequency": event.get("dialFrequency") or payload.get("dialFrequency"),
            "rx_df": event.get("rxDf") or payload.get("rxDf"),
            "tx_df": event.get("txDf") or payload.get("txDf"),
        })
    return normalised


def _tcp_endpoint_check(host: str, port: int, timeout_seconds: float = 1.0) -> Dict[str, Any]:
    host = str(host or "").strip() or "127.0.0.1"
    port = int(port or 0)
    if port <= 0:
        return {
            "ok": False,
            "host": host,
            "port": port,
            "error": "missing port",
        }
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {
                "ok": True,
                "host": host,
                "port": port,
            }
    except Exception as exc:
        return {
            "ok": False,
            "host": host,
            "port": port,
            "error": str(exc),
        }


def _visible_process_names(names: set[str]) -> Dict[str, bool]:
    """Return best-effort local process visibility without adding dependencies."""
    wanted = {name.lower() for name in names}
    found = {name: False for name in wanted}
    system = platform.system().lower()

    try:
        if system == "windows":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                text=True,
                capture_output=True,
                timeout=1.2,
                check=False,
            )
            output = result.stdout.lower()
            for name in wanted:
                found[name] = name in output
        else:
            result = subprocess.run(
                ["ps", "-axo", "comm="],
                text=True,
                capture_output=True,
                timeout=1.2,
                check=False,
            )
            processes = {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
            for name in wanted:
                stem = name.rsplit(".", 1)[0]
                found[name] = name in processes or stem in processes
    except Exception as exc:
        logger.debug("WSJT process health probe failed: %s", exc)

    return found


def _process_creation_flags() -> int:
    if platform.system().lower() != "windows":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def _patched_engine_log_paths(rig_name: str, app_prefix: str = "wsjt-x") -> dict[str, Path]:
    log_root = PROJECT_ROOT / "logs"
    log_safe_name = "".join(
        ch if ch.isalnum() or ch in "._-" else "-"
        for ch in f"{app_prefix}-{rig_name}"
    ).strip("-").lower()
    if not log_safe_name:
        log_safe_name = f"{app_prefix}-om0rx-auto"
    return {
        "stdout": log_root / f"{log_safe_name}.out.log",
        "stderr": log_root / f"{log_safe_name}.err.log",
    }


def _tail_text_file(path: Path, max_lines: int, max_bytes: int = 256_000) -> dict[str, Any]:
    resolved = path.resolve()
    log_root = (PROJECT_ROOT / "logs").resolve()
    if log_root not in resolved.parents and resolved != log_root:
        raise HTTPException(status_code=403, detail="WSJT log path is outside the application logs directory")

    if not resolved.exists():
        return {
            "path": str(resolved),
            "exists": False,
            "size": 0,
            "modified": None,
            "lines": [],
            "text": "",
            "truncated": False,
        }
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"WSJT log path is not a file: {resolved}")

    stat = resolved.stat()
    start = max(0, stat.st_size - max_bytes)
    with resolved.open("rb") as handle:
        handle.seek(start)
        data = handle.read()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()[-max_lines:]
    return {
        "path": str(resolved),
        "exists": True,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "lines": lines,
        "text": "\n".join(lines),
        "truncated": start > 0,
    }


def _wsjt_engine_process_ids(exe_name: str, rig_name: str, test_mode: bool = False) -> list[int]:
    """Return running WSJT engine PIDs for this OM0RX rig profile."""
    if platform.system().lower() != "windows":
        return []
    safe_exe = exe_name.replace("'", "''")
    safe_rig = rig_name.replace("'", "''")
    test_filter = " -and $_.CommandLine -like '*--test-mode*'" if test_mode else ""
    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"Get-CimInstance Win32_Process -Filter \"Name='{safe_exe}'\" | "
        f"Where-Object {{ $_.CommandLine -like '*--rig-name {safe_rig}*'{test_filter} }} | "
        "ForEach-Object { $_.ProcessId }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            text=True,
            capture_output=True,
            timeout=2.0,
            check=False,
            creationflags=_process_creation_flags(),
        )
    except Exception as exc:
        logger.debug("Could not check patched WSJT process ids: %s", exc)
        return []
    pids = []
    for line in result.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    return pids


def _patched_engine_process_ids(rig_name: str, test_mode: bool = False) -> list[int]:
    return _wsjt_engine_process_ids("wsjtx.exe", rig_name, test_mode=test_mode)


def _patched_engine_decoder_process_ids(rig_name: str) -> list[int]:
    """Return running jt9.exe PIDs attached to this OM0RX WSJT profile."""
    if platform.system().lower() != "windows":
        return []
    app_name = f"WSJT-X - {rig_name}".replace("'", "''")
    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "Get-CimInstance Win32_Process -Filter \"Name='jt9.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*-s \"{app_name}\"*' }} | "
        "ForEach-Object { $_.ProcessId }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            text=True,
            capture_output=True,
            timeout=2.0,
            check=False,
            creationflags=_process_creation_flags(),
        )
    except Exception as exc:
        logger.debug("Could not check patched WSJT decoder process ids: %s", exc)
        return []
    pids = []
    for line in result.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    return pids


class WSJTXService:
    """
    Service class for WSJT-X operations, auto-logging, and auto-rotation.
    Encapsulates all WSJT-X related functionality extracted from main.py.
    """

    def __init__(self):
        self.wavelog_client = None
        self.qrz_client = None
        self.rotor_service = None
        self.cty_resolver = None
        self.adif_handler = None
        self.qso_status_store = None
        self._recent_logged_qso_keys: Dict[str, float] = {}
        self._outbox_replay_task: Optional[asyncio.Task] = None

    def set_dependencies(
        self,
        wavelog_client,
        qrz_client,
        rotor_service,
        cty_resolver=None,
        adif_handler=None,
        qso_status_store=None,
    ):
        """Set external dependencies"""
        self.wavelog_client = wavelog_client
        self.qrz_client = qrz_client
        self.rotor_service = rotor_service
        self.cty_resolver = cty_resolver
        self.adif_handler = adif_handler
        self.qso_status_store = qso_status_store

    def _record_logged_qso_in_status_cache(self, qso_data: Dict[str, Any]) -> None:
        store = self.qso_status_store
        if store and hasattr(store, "record_qso"):
            try:
                if store.record_qso(qso_data):
                    logger.info("✅ Local QSO status cache updated for %s", qso_data.get("callsign"))
            except Exception as exc:
                logger.debug("Unable to update local QSO status cache for %s: %s", qso_data.get("callsign"), exc)
        try:
            from services.qso_logging import write_qso_to_postgres_read_cache

            write_qso_to_postgres_read_cache(qso_data)
        except Exception as exc:
            logger.debug("Unable to write WSJT-X QSO to PostgreSQL read cache for %s: %s", qso_data.get("callsign"), exc)
        self._mark_automation_qso_logged(qso_data)

    def _mark_automation_qso_logged(self, qso_data: Dict[str, Any]) -> None:
        call = str(qso_data.get("callsign") or qso_data.get("call") or "").strip().upper()
        if not call:
            return
        try:
            from services.ft8_service import get_ft8_service

            ft8_service = get_ft8_service()
            controller = getattr(ft8_service, "automation_controller", None)
            if controller:
                controller.mark_qso_complete(
                    call,
                    band=qso_data.get("band"),
                    mode=qso_data.get("mode"),
                    reason="wsjtx-logged-qso",
                )
        except Exception as exc:
            logger.debug("Unable to mark automation QSO complete for WSJT-X logged QSO %s: %s", call, exc)

    def _logged_qso_reference_fields(
        self,
        req: Dict[str, Any],
        adif_fields: Dict[str, Any],
        *,
        call: str,
        band: str,
        mode: str,
    ) -> Dict[str, str]:
        """Resolve award references from ADIF/request and the active hunt target."""
        payload: Dict[str, Any] = {
            **req,
            "pota": req.get("pota") or adif_fields.get("pota_ref"),
            "sota": req.get("sota") or adif_fields.get("sota_ref"),
            "iota": req.get("iota") or adif_fields.get("iota"),
            "wwff": req.get("wwff") or adif_fields.get("wwff_ref"),
            "sig": req.get("sig") or adif_fields.get("sig"),
            "sig_info": req.get("sig_info") or adif_fields.get("sig_info"),
        }
        references = extract_activity_references(payload)
        try:
            from services.ft8_service import get_ft8_service

            controller = getattr(get_ft8_service(), "automation_controller", None)
            candidates = list(getattr(controller, "targets", {}).values()) if controller else []
            candidates = [
                target
                for target in candidates
                if target.call == call
                and (not band or not target.band or target.band == band)
                and (not mode or not target.mode or target.mode == mode)
                and target.reference_items
            ]
            candidates.sort(
                key=lambda target: (
                    target.key == getattr(controller, "active_target_key", None),
                    target.updated_at,
                ),
                reverse=True,
            )
            if candidates:
                references.extend(dict(item) for item in candidates[0].reference_items)
        except Exception as exc:
            logger.debug("Unable to resolve automation references for %s: %s", call, exc)

        fields = reference_items_to_qso_fields(references)
        if payload.get("sig") and payload.get("sig_info"):
            fields.setdefault("sig", str(payload["sig"]).strip().upper())
            fields.setdefault("sig_info", str(payload["sig_info"]).strip().upper())
        return fields

    def _finish_async_logged_qso(
        self,
        qso_data: Dict[str, Any],
        *,
        qso_key: str = "",
        loose_qso_key: str = "",
        outbox_queued: bool = False,
    ) -> None:
        call = str(qso_data.get("callsign") or "").strip().upper()
        adif_saved = False
        try:
            if self.adif_handler:
                adif_saved = self.adif_handler.add_qso(qso_data)
        except Exception as exc:
            logger.debug("Async WSJT-X local ADIF save failed for %s: %s", call, exc, exc_info=True)

        self._record_logged_qso_in_status_cache(qso_data)
        if qso_key:
            try:
                from services.qso_logging import _record_dedupe_entry

                record = {
                    "wavelog": {"success": False, "queued": outbox_queued},
                    "adif_saved": adif_saved,
                    "outbox_queued": outbox_queued,
                }
                _record_dedupe_entry(qso_key, qso_data, record)
                if loose_qso_key and loose_qso_key != qso_key:
                    _record_dedupe_entry(loose_qso_key, qso_data, record)
            except Exception as exc:
                logger.debug("Unable to record async WSJT-X QSO dedupe entry for %s: %s", call, exc, exc_info=True)

        logger.info(
            "✅ Accepted WSJT-X logged QSO for async Wavelog upload: %s %s %s (ADIF: %s, Outbox: %s)",
            call,
            qso_data.get("band"),
            qso_data.get("mode"),
            adif_saved,
            outbox_queued,
        )

    async def _replay_wavelog_outbox_once(self) -> None:
        try:
            from services.qso_logging import record_qso_status_from_adif

            result = await get_qso_outbox().replay(
                self.wavelog_client,
                max_records=getattr(config, "WAVELOG_OUTBOX_RETRY_BATCH_SIZE", 20),
                on_resolved_record=record_qso_status_from_adif,
            )
            if result.get("attempted"):
                logger.info("✅ Immediate Wavelog outbox replay after WSJT-X log: %s", result)
        except Exception as exc:
            logger.warning("Immediate Wavelog outbox replay after WSJT-X log failed: %s", exc)

    def _schedule_wavelog_outbox_replay(self) -> None:
        # Return the WSJT-Z UDP request immediately, but kick the queued Wavelog
        # upload outside the request path so logged QSOs do not sit in the
        # offline outbox until the periodic retry wakes up.
        task = self._outbox_replay_task
        if task and not task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._outbox_replay_task = loop.create_task(self._replay_wavelog_outbox_once())

    async def log_qso(self, req: Dict[str, Any]):
        """
        Auto-log a QSO from WSJT-X to Wavelog
        Enriches with QRZ data if available
        """
        if not self.wavelog_client:
            raise HTTPException(status_code=503, detail="Wavelog client not initialized")

        try:
            adif_text = _ensure_adif_eor(str(req.get("adif_text") or ""))
            adif_fields = _parse_adif_fields(adif_text)
            call = (req.get("call") or adif_fields.get("call") or "").strip().upper()
            if not call:
                raise HTTPException(status_code=400, detail="Missing callsign")
            submode = (adif_fields.get("submode") or req.get("submode") or "").strip().upper()
            mode = (req.get("mode") or submode or adif_fields.get("mode") or "FT8").strip().upper()
            if mode == "MFSK" and submode in WSJT_TARGET_MODES:
                mode = submode
            frequency_hz = _frequency_hz_from_payload(req) or _frequency_hz_from_adif(adif_fields)
            band = adif_fields.get("band") or (band_from_khz(frequency_hz / 1000) if frequency_hz else "Unknown")
            date_time = req.get("date_time") or _iso_from_adif_datetime(
                adif_fields.get("qso_date", ""),
                adif_fields.get("time_on") or adif_fields.get("time_off", ""),
            )
            # The WSJT-Z Logged QSO event is authoritative. Retire its active
            # automation target before any QRZ/Wavelog network work so a slow
            # upload cannot let the scheduler re-arm the just-worked station.
            self._mark_automation_qso_logged({
                "callsign": call,
                "band": band,
                "mode": mode,
            })
            reference_fields = self._logged_qso_reference_fields(
                req,
                adif_fields,
                call=call,
                band=band,
                mode=mode,
            )

            if adif_text and _coerce_bool(req.get("async_upload")):
                qrz_data = req.get("qrz_data", {}) or {}
                if not qrz_data and self.qrz_client:
                    try:
                        logger.info("📡 Fetching QRZ data for %s before WSJT-X bridge log...", call)
                        qrz_data = await self.qrz_client.lookup(call) or {}
                        if qrz_data:
                            logger.info(
                                "✅ QRZ lookup successful for %s: %s from %s",
                                call,
                                qrz_data.get("fname", "N/A"),
                                qrz_data.get("country", "N/A"),
                            )
                    except Exception as exc:
                        logger.warning("⚠️  QRZ lookup failed for %s: %s", call, exc)
                        qrz_data = {}

                cty_data = {}
                if self.cty_resolver:
                    try:
                        cty_data = self.cty_resolver.lookup(call) or {}
                    except Exception as exc:
                        logger.debug("CTY lookup failed for %s: %s", call, exc)

                qso_data = {
                    "callsign": call,
                    "frequency": frequency_hz / 1_000_000 if frequency_hz else None,
                    "mode": mode,
                    "submode": submode if submode in WSJT_TARGET_MODES else "",
                    "band": band,
                    "rst_sent": req.get("rst_sent") or adif_fields.get("rst_sent"),
                    "rst_received": req.get("rst_received") or adif_fields.get("rst_rcvd"),
                    "date": req.get("date") or adif_fields.get("qso_date") or None,
                    "time_off": req.get("time_off") or adif_fields.get("time_off") or adif_fields.get("time_on") or None,
                    "date_time": date_time,
                    "name": adif_fields.get("name") or qrz_data.get("fname", ""),
                    "qth": adif_fields.get("qth") or qrz_data.get("state") or qrz_data.get("country", ""),
                    "gridsquare": req.get("grid") or adif_fields.get("gridsquare") or qrz_data.get("grid", ""),
                    "notes": req.get("comments") or adif_fields.get("comment") or adif_fields.get("comments") or f"Auto-logged from WSJT-X ({mode})",
                    "continent": cty_data.get("continent", ""),
                    "dxcc": cty_data.get("dxcc"),
                    "country": qrz_data.get("country") or cty_data.get("entity") or cty_data.get("country") or "",
                    "state": qrz_data.get("state", ""),
                    "cq_zone": qrz_data.get("cqzone") or cty_data.get("cq"),
                    "itu_zone": qrz_data.get("ituzone") or cty_data.get("itu"),
                    "lotw_member": qrz_data.get("lotw", False),
                    "email": qrz_data.get("email", ""),
                    "tx_pwr": adif_fields.get("tx_pwr") or None,
                    "prop_mode": adif_fields.get("prop_mode") or None,
                    "freq_rx": adif_fields.get("freq_rx") or None,
                    "mode_rx": adif_fields.get("mode_rx") or None,
                    **reference_fields,
                }
                qso_key = ""
                loose_qso_key = ""
                dedupe_keys = []
                try:
                    from services.qso_logging import (
                        _claim_dedupe_keys,
                        _record_dedupe_entries,
                        _recent_wavelog_duplicate_entry,
                        build_qso_dedupe_key,
                        build_qso_loose_dedupe_keys,
                    )

                    qso_key = str(req.get("qso_key") or build_qso_dedupe_key(qso_data))
                    loose_qso_keys = build_qso_loose_dedupe_keys(qso_data)
                    loose_qso_key = loose_qso_keys[1] if len(loose_qso_keys) > 1 else (loose_qso_keys[0] if loose_qso_keys else "")
                    qso_data["qso_key"] = qso_key
                    dedupe_keys = [key for key in (qso_key, *loose_qso_keys) if key]
                    dedupe_entry = _claim_dedupe_keys(dedupe_keys, qso_data)
                    if dedupe_entry:
                        asyncio.create_task(asyncio.to_thread(self._record_logged_qso_in_status_cache, qso_data))
                        return {
                            "success": True,
                            "duplicate": True,
                            "async_upload": True,
                            "message": "Duplicate WSJT-X QSO log request ignored",
                            "outbox_queued": bool(dedupe_entry.get("outbox_queued")),
                            "qso_key": qso_key,
                            "loose_qso_key": loose_qso_key,
                            "dedupe": dedupe_entry,
                        }
                    recent_duplicate = _recent_wavelog_duplicate_entry(qso_data)
                    if recent_duplicate:
                        logger.info("Skipping WSJT-X bridge QSO already present in Wavelog/read-cache: %s", call)
                        _record_dedupe_entries(dedupe_keys, qso_data, {"wavelog": {"success": True}, "adif_saved": True})
                        asyncio.create_task(asyncio.to_thread(self._record_logged_qso_in_status_cache, qso_data))
                        return {
                            "success": True,
                            "duplicate": True,
                            "async_upload": True,
                            "message": "QSO already present in Wavelog/read-cache",
                            "outbox_queued": False,
                            "qso_key": qso_key,
                            "loose_qso_key": loose_qso_key,
                            "dedupe": recent_duplicate,
                            "qso_data": {
                                "callsign": call,
                                "frequency": qso_data["frequency"],
                                "mode": mode,
                                "gridsquare": qso_data["gridsquare"],
                                "rst_sent": qso_data["rst_sent"],
                                "rst_received": qso_data["rst_received"],
                                "country": qso_data["country"],
                                "continent": qso_data["continent"],
                            },
                        }
                except Exception as exc:
                    logger.debug("Async WSJT-X QSO dedupe guard unavailable for %s: %s", call, exc, exc_info=True)

                result = await self.wavelog_client.log_qso(qso_data)
                adif_saved = False
                try:
                    if self.adif_handler:
                        adif_saved = self.adif_handler.add_qso(qso_data)
                except Exception as exc:
                    logger.debug("Async WSJT-X local ADIF save failed for %s: %s", call, exc, exc_info=True)

                outbox_queued = False
                if not result.get("success"):
                    outbox_queued = get_qso_outbox().enqueue(
                        qso_data,
                        reason=result.get("message") or result.get("error") or "WSJT-X bridge Wavelog upload failed",
                    )
                    self._schedule_wavelog_outbox_replay()

                if result.get("success") or outbox_queued:
                    self._record_logged_qso_in_status_cache(qso_data)
                if qso_key:
                    try:
                        from services.qso_logging import _record_dedupe_entries, _release_dedupe_keys

                        response_for_dedupe = {
                            "wavelog": result,
                            "adif_saved": adif_saved,
                            "outbox_queued": outbox_queued,
                        }
                        if result.get("success") or outbox_queued:
                            _record_dedupe_entries(dedupe_keys, qso_data, response_for_dedupe)
                        else:
                            _release_dedupe_keys(dedupe_keys)
                    except Exception as exc:
                        logger.debug("Unable to record async WSJT-X QSO dedupe entry for %s: %s", call, exc, exc_info=True)

                logger.info(
                    "✅ Processed WSJT-X bridge logged QSO: %s %s %s (Wavelog: %s, ADIF: %s, Outbox: %s)",
                    call,
                    qso_data.get("band"),
                    qso_data.get("mode"),
                    result.get("success"),
                    adif_saved,
                    outbox_queued,
                )
                return {
                    "success": bool(result.get("success") or outbox_queued),
                    "async_upload": True,
                    "wavelog": result,
                    "adif_saved": adif_saved,
                    "outbox_queued": outbox_queued,
                    "qso_key": qso_key,
                    "loose_qso_key": loose_qso_key,
                    "message": result.get("message") or "QSO processed from WSJT-X bridge",
                    "qso_data": {
                        "callsign": call,
                        "frequency": qso_data["frequency"],
                        "mode": mode,
                        "gridsquare": qso_data["gridsquare"],
                        "rst_sent": qso_data["rst_sent"],
                        "rst_received": qso_data["rst_received"],
                        "country": qso_data["country"],
                        "continent": qso_data["continent"],
                    },
                }

            # Fetch QRZ data if not already provided
            qrz_data = req.get('qrz_data', {}) or {}
            if not qrz_data and self.qrz_client:
                try:
                    logger.info(f"📡 Fetching QRZ data for {call}...")
                    qrz_data = await self.qrz_client.lookup(call) or {}
                    if qrz_data:
                        logger.info(f"✅ QRZ lookup successful for {call}: {qrz_data.get('fname', 'N/A')} from {qrz_data.get('country', 'N/A')}")
                    else:
                        logger.debug(f"ℹ️  No QRZ data found for {call}")
                except Exception as e:
                    logger.warning(f"⚠️  QRZ lookup failed for {call}: {e}")
                    qrz_data = {}

            # Enrich with CTY data if available (for continent and other metadata)
            cty_data = {}
            if self.cty_resolver:
                try:
                    cty_data = self.cty_resolver.lookup(call) or {}
                    if cty_data and cty_data.get('continent'):
                        logger.debug(f"📍 CTY lookup for {call}: continent={cty_data.get('continent')}")
                except Exception as e:
                    logger.debug(f"CTY lookup failed for {call}: {e}")

            # Build QSO data from WSJT-X and QRZ
            # Match the standard QSORequest structure to ensure consistency with regular QSO logging
            qso_data = {
                # Core fields (required)
                "callsign": call,
                "frequency": frequency_hz / 1_000_000 if frequency_hz else None,
                "mode": mode,
                "submode": submode if submode in WSJT_TARGET_MODES else "",
                "band": band,  # Include band for ADIF saving
                
                # RST values: keep as-is or use defaults (wavelog_api.py handles conversion)
                "rst_sent": req.get('rst_sent') or adif_fields.get("rst_sent"),
                "rst_received": req.get('rst_received') or adif_fields.get("rst_rcvd"),
                
                # Date/Time fields
                "date": req.get("date") or adif_fields.get("qso_date") or None,
                "time_off": req.get("time_off") or adif_fields.get("time_off") or adif_fields.get("time_on") or None,
                "date_time": date_time,
                
                # Station info (enriched from QRZ/CTY)
                "name": adif_fields.get("name") or qrz_data.get("fname", ""),
                "qth": adif_fields.get("qth") or qrz_data.get("state", qrz_data.get("country", "")),
                "gridsquare": req.get('grid') or adif_fields.get("gridsquare") or qrz_data.get("grid", ""),
                "notes": req.get('comments') or adif_fields.get("comment") or adif_fields.get("comments") or f"Auto-logged from WSJT-X ({mode})",
                
                # Activation programs
                "pota": reference_fields.get("pota"),
                "sota": reference_fields.get("sota"),
                "iota": reference_fields.get("iota"),
                "wwff": reference_fields.get("wwff"),
                "sig": reference_fields.get("sig"),
                "sig_info": reference_fields.get("sig_info"),
                
                # Location info
                "continent": cty_data.get("continent", qrz_data.get("continent", "")),  # Prefer CTY continent if available
                "dxcc": cty_data.get("dxcc") or qrz_data.get("dxcc"),
                "cq_zone": qrz_data.get("cqzone"),
                "itu_zone": qrz_data.get("ituzone"),
                "region": None,
                "country": qrz_data.get("country", ""),
                "state": qrz_data.get("state", ""),
                "us_county": None,
                
                # Radio/Antenna
                "tx_pwr": adif_fields.get("tx_pwr") or None,
                "ant": None,
                
                # QSL info
                "qsl_rcvd": None,
                "qsl_sent": None,
                "lotw_member": qrz_data.get("lotw", False),
                "qsl_manager": None,
                
                # Advanced fields
                "email": qrz_data.get("email", ""),
                "prop_mode": adif_fields.get("prop_mode") or None,
                "ant_path": None,
                "sat_name": adif_fields.get("sat_name") or None,
                "sat_mode": adif_fields.get("sat_mode") or None,
                "freq_rx": adif_fields.get("freq_rx") or None,
                "mode_rx": adif_fields.get("mode_rx") or None,
            }
            try:
                from services.qso_logging import (
                    _claim_dedupe_keys,
                    _record_dedupe_entry,
                    _release_dedupe_keys,
                    _recent_wavelog_duplicate_entry,
                    build_qso_dedupe_key,
                    build_qso_loose_dedupe_key,
                )

                qso_key = str(req.get("qso_key") or build_qso_dedupe_key(qso_data))
                loose_qso_key = build_qso_loose_dedupe_key(qso_data)
                qso_data["qso_key"] = qso_key
                now_ts = datetime.now(timezone.utc).timestamp()
                self._recent_logged_qso_keys = {
                    key: ts
                    for key, ts in self._recent_logged_qso_keys.items()
                    if now_ts - ts < 900
                }
                dedupe_keys = [qso_key, loose_qso_key]
                dedupe_entry = _claim_dedupe_keys(dedupe_keys, qso_data)
                if (
                    dedupe_entry
                    or qso_key in self._recent_logged_qso_keys
                    or loose_qso_key in self._recent_logged_qso_keys
                ):
                    logger.info(
                        "Skipping duplicate WSJT-X QSO log request for %s / %s (%s)",
                        qso_key,
                        loose_qso_key,
                        call,
                    )
                    self._record_logged_qso_in_status_cache(qso_data)
                    dedupe_entry = dedupe_entry or {"recent": True}
                    return {
                        "success": True,
                        "duplicate": True,
                        "message": "Duplicate WSJT-X QSO log request ignored",
                        "qso_key": qso_key,
                        "loose_qso_key": loose_qso_key,
                        "dedupe": dedupe_entry,
                        "adif_saved": bool(dedupe_entry.get("adif_saved")),
                        "qso_data": {
                            "callsign": call,
                            "frequency": qso_data["frequency"],
                            "mode": mode,
                            "gridsquare": qso_data["gridsquare"],
                            "rst_sent": qso_data["rst_sent"],
                            "rst_received": qso_data["rst_received"],
                            "name": qso_data["name"],
                            "country": qso_data["country"],
                            "state": qso_data["state"],
                            "continent": qso_data["continent"],
                        },
                    }
                self._recent_logged_qso_keys[qso_key] = now_ts
                self._recent_logged_qso_keys[loose_qso_key] = now_ts
                recent_duplicate = _recent_wavelog_duplicate_entry(qso_data)
                if recent_duplicate:
                    logger.info("Skipping WSJT-X QSO already present in Wavelog/read-cache: %s", call)
                    self._record_logged_qso_in_status_cache(qso_data)
                    _record_dedupe_entry(qso_key, qso_data, {"wavelog": {"success": True}, "adif_saved": True})
                    if loose_qso_key and loose_qso_key != qso_key:
                        _record_dedupe_entry(loose_qso_key, qso_data, {"wavelog": {"success": True}, "adif_saved": True})
                    return {
                        "success": True,
                        "duplicate": True,
                        "message": "QSO already present in Wavelog/read-cache",
                        "qso_key": qso_key,
                        "loose_qso_key": loose_qso_key,
                        "dedupe": recent_duplicate,
                        "adif_saved": True,
                        "qso_data": {
                            "callsign": call,
                            "frequency": qso_data["frequency"],
                            "mode": mode,
                            "gridsquare": qso_data["gridsquare"],
                            "rst_sent": qso_data["rst_sent"],
                            "rst_received": qso_data["rst_received"],
                            "name": qso_data["name"],
                            "country": qso_data["country"],
                            "state": qso_data["state"],
                            "continent": qso_data["continent"],
                        },
                    }
            except Exception as exc:
                qso_key = str(req.get("qso_key") or "")
                loose_qso_key = ""
                dedupe_keys = [qso_key]
                logger.debug("WSJT-X QSO dedupe guard unavailable for %s: %s", call, exc, exc_info=True)

            logger.info(f"📝 Auto-logging QSO: {call} on {band} {mode}")
            logger.debug(f"   QSO Data: name={qso_data['name']}, country={qso_data['country']}, grid={qso_data['gridsquare']}")

            # Log to Wavelog
            if adif_text and hasattr(self.wavelog_client, "submit_adif_string"):
                result = await self.wavelog_client.submit_adif_string(adif_text)
            else:
                result = await self.wavelog_client.log_qso(qso_data)

            # Always save to local ADIF file (backup/archive with enriched data)
            adif_saved = False
            try:
                if self.adif_handler:
                    adif_saved = self.adif_handler.add_qso(qso_data)
                    if adif_saved:
                        logger.info(f"✅ QSO saved to local ADIF: {call} with enriched data (name, country, grid, etc.)")
                    else:
                        logger.warning(f"⚠️  Failed to save QSO to ADIF file: {call}")
            except Exception as e:
                logger.error(f"❌ ADIF save error for {call}: {e}", exc_info=True)
                adif_saved = False

            if result and result.get("success"):
                # Extract QSO ID from response if available
                qso_id = None
                if result.get("data"):
                    # Try different possible response formats
                    qso_id = result["data"].get("id") or result["data"].get("qso_id") or result["data"].get("lastid")
                self._record_logged_qso_in_status_cache(qso_data)
                
                logger.info(f"✅ QSO logged successfully to Wavelog: {call} (ID: {qso_id if qso_id else 'unknown'}), ADIF: {adif_saved}")
                
                # Return enriched QSO data to frontend for display in confirmation modal
                response = {
                    "success": True, 
                    "qso_id": qso_id, 
                    "message": result.get("message", "QSO logged successfully"),
                    "adif_saved": adif_saved,
                    "qso_key": qso_key,
                    "qso_data": {
                        "callsign": call,
                        "frequency": qso_data["frequency"],
                        "mode": mode,
                        "gridsquare": qso_data['gridsquare'],
                        "rst_sent": qso_data["rst_sent"],
                        "rst_received": qso_data["rst_received"],
                        "name": qso_data['name'],  # From QRZ enrichment
                        "country": qso_data['country'],  # From QRZ enrichment
                        "state": qso_data['state'],
                        "continent": qso_data['continent']
                    }
                }
                if qso_key:
                    try:
                        from services.qso_logging import _record_dedupe_entry

                        _record_dedupe_entry(qso_key, qso_data, {"wavelog": result, "adif_saved": adif_saved})
                        if loose_qso_key and loose_qso_key != qso_key:
                            _record_dedupe_entry(loose_qso_key, qso_data, {"wavelog": result, "adif_saved": adif_saved})
                    except Exception as exc:
                        logger.debug("Unable to record WSJT-X QSO dedupe entry for %s: %s", call, exc, exc_info=True)
                return response
            else:
                duplicate_text = " ".join(
                    str((result or {}).get(key) or "")
                    for key in ("message", "error")
                ).lower()
                if "duplicate" in duplicate_text:
                    logger.info("✅ WSJT-X QSO already exists in Wavelog; treating duplicate as resolved: %s", call)
                    self._record_logged_qso_in_status_cache(qso_data)
                    response = {
                        "success": True,
                        "duplicate": True,
                        "message": (result or {}).get("message") or "QSO already exists in Wavelog",
                        "adif_saved": adif_saved,
                        "qso_key": qso_key,
                        "qso_data": {
                            "callsign": call,
                            "frequency": qso_data["frequency"],
                            "mode": mode,
                            "gridsquare": qso_data['gridsquare'],
                            "rst_sent": qso_data["rst_sent"],
                            "rst_received": qso_data["rst_received"],
                            "name": qso_data['name'],
                            "country": qso_data['country'],
                            "state": qso_data['state'],
                            "continent": qso_data['continent'],
                        },
                    }
                    if qso_key:
                        try:
                            from services.qso_logging import _record_dedupe_entry

                            _record_dedupe_entry(qso_key, qso_data, {"wavelog": result or {}, "adif_saved": adif_saved})
                            if loose_qso_key and loose_qso_key != qso_key:
                                _record_dedupe_entry(loose_qso_key, qso_data, {"wavelog": result or {}, "adif_saved": adif_saved})
                        except Exception as exc:
                            logger.debug("Unable to record duplicate WSJT-X QSO dedupe entry for %s: %s", call, exc, exc_info=True)
                    return response
                logger.error(f"❌ Failed to log QSO to Wavelog: {result}")
                outbox_queued = get_qso_outbox().enqueue(
                    qso_data,
                    reason=(result or {}).get("message", "WSJT-X Wavelog upload failed"),
                )
                # If Wavelog fails but ADIF saved, still return partial success
                if adif_saved or outbox_queued:
                    # Local ADIF alone is an archive, not a durable Wavelog delivery.
                    if outbox_queued:
                        self._record_logged_qso_in_status_cache(qso_data)
                    if qso_key:
                        try:
                            from services.qso_logging import _record_dedupe_entry

                            _record_dedupe_entry(
                                qso_key,
                                qso_data,
                                {
                                    "wavelog": result or {},
                                    "adif_saved": adif_saved,
                                    "outbox_queued": outbox_queued,
                                },
                            )
                            if loose_qso_key and loose_qso_key != qso_key:
                                _record_dedupe_entry(
                                    loose_qso_key,
                                    qso_data,
                                    {
                                        "wavelog": result or {},
                                        "adif_saved": adif_saved,
                                        "outbox_queued": outbox_queued,
                                    },
                                )
                        except Exception as exc:
                            logger.debug("Unable to record failed WSJT-X QSO dedupe entry for %s: %s", call, exc, exc_info=True)
                    logger.info(
                        "ℹ️  QSO saved locally but Wavelog failed: %s (ADIF: %s, Outbox: %s)",
                        call,
                        adif_saved,
                        outbox_queued,
                    )
                    return {
                        "success": False,
                        "adif_saved": True,
                        "outbox_queued": outbox_queued,
                        "qso_key": qso_key,
                        "message": (
                            "Wavelog logging failed but QSO saved locally: "
                            f"{(result or {}).get('message', str(result))}"
                        )
                    }
                try:
                    from services.qso_logging import _release_dedupe_keys

                    _release_dedupe_keys(dedupe_keys)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to log QSO: {(result or {}).get('message', str(result))}",
                )

        except HTTPException:
            raise
        except Exception as e:
            try:
                from services.qso_logging import _release_dedupe_keys

                _release_dedupe_keys(dedupe_keys)
            except Exception:
                pass
            logger.error(f"❌ WSJT-X log error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def auto_rotate(self, req: Dict[str, Any]):
        """
        Auto-rotate to DX station based on grid square
        Only rotates if ROTOR_AUTO_ENABLED is True
        """
        if not config.ROTOR_AUTO_ENABLED or not self.rotor_service:
            return {"success": False, "reason": "Rotator auto mode not enabled"}

        try:
            call = req['call'].strip().upper()
            grid = req['grid'].strip().upper()

            if not grid or len(grid) < 4:
                logger.warning(f"⚠️  Invalid grid square for {call}: {grid}")
                return {"success": False, "reason": "Invalid grid square"}

            logger.info(f"🎯 Auto-rotating to {call} ({grid})...")

            result = await self.rotor_service.rotor_auto_goto({
                "callsign": call,
                "frequency_khz": req.get('frequency_hz') / 1000 if req.get('frequency_hz') else None,
                "gridsquare": grid,
                "location_source": "wsjtx_grid",
                "grid_source": "wsjtx",
            })

            if result.get("ok"):
                logger.info(f"✅ Rotator command sent: {call} on {result.get('bearing')}°")
                return {
                    "success": True,
                    "call": call,
                    "grid": grid,
                    "bearing": result.get("bearing"),
                    "adjusted_bearing": result.get("bearing"),
                    "band": result.get("band"),
                    "source": result.get("source"),
                    "confidence": result.get("confidence"),
                }
            else:
                logger.error(f"❌ Rotator command failed: {call}")
                return {
                    "success": False,
                    "reason": result.get("message") or result.get("error") or "Rotor command failed",
                    "bearing": result.get("bearing"),
                    "band": result.get("band"),
                    "source": result.get("source"),
                    "confidence": result.get("confidence"),
                }

        except Exception as e:
            logger.error(f"❌ Auto-rotate error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_config(self):
        """Get WSJT-X configuration"""
        return {
            "enabled": getattr(config, 'WSJTX_ENABLED', True),
            "udp_port": getattr(config, 'WSJTX_UDP_PORT', 2237),
            "multicast": getattr(config, 'WSJTX_UDP_MULTICAST', '224.0.0.1'),
            "ws_port": getattr(config, 'WSJTX_WS_PORT', 8091),
            "bridge_command_url": getattr(config, 'WSJTX_BRIDGE_COMMAND_URL', 'http://127.0.0.1:8092/wsjtx/command'),
            "auto_log": getattr(config, 'WSJTX_AUTO_LOG', True),
            "auto_rotate": getattr(config, 'WSJTX_AUTO_ROTATE', True) and getattr(config, 'ROTOR_AUTO_ENABLED', False),
            "modal_fields": getattr(config, 'WSJTX_MODAL_FIELDS', {}),
        }

    def get_patched_engine_status(self) -> Dict[str, Any]:
        """Return local patched-engine launcher prerequisites."""
        exe = PATCHED_ENGINE_BUILD_ROOT / "wsjtx.exe"
        decoder = PATCHED_ENGINE_BUILD_ROOT / "jt9.exe"
        mingw_bin = PATCHED_ENGINE_MSYS_ROOT / "mingw64" / "bin"
        usr_bin = PATCHED_ENGINE_MSYS_ROOT / "usr" / "bin"
        return {
            "platform": platform.system(),
            "supported": platform.system().lower() == "windows",
            "script": str(PATCHED_ENGINE_RUN_SCRIPT),
            "build_root": str(PATCHED_ENGINE_BUILD_ROOT),
            "exe": str(exe),
            "decoder": str(decoder),
            "msys_root": str(PATCHED_ENGINE_MSYS_ROOT),
            "mingw_bin": str(mingw_bin),
            "usr_bin": str(usr_bin),
            "script_exists": PATCHED_ENGINE_RUN_SCRIPT.exists(),
            "exe_exists": exe.exists(),
            "decoder_exists": decoder.exists(),
            "mingw_bin_exists": mingw_bin.exists(),
            "usr_bin_exists": usr_bin.exists(),
        }

    def get_wsjtz_engine_status(self) -> Dict[str, Any]:
        """Return local OM0RX WSJT-Z launcher prerequisites."""
        exe = WSJTZ_ENGINE_BUILD_ROOT / "wsjt-z-clean.exe"
        decoder = WSJTZ_ENGINE_BUILD_ROOT / "jt9.exe"
        mingw_bin = PATCHED_ENGINE_MSYS_ROOT / "mingw64" / "bin"
        usr_bin = PATCHED_ENGINE_MSYS_ROOT / "usr" / "bin"
        return {
            "platform": platform.system(),
            "supported": platform.system().lower() == "windows",
            "script": str(WSJTZ_ENGINE_RUN_SCRIPT),
            "build_root": str(WSJTZ_ENGINE_BUILD_ROOT),
            "exe": str(exe),
            "decoder": str(decoder),
            "msys_root": str(PATCHED_ENGINE_MSYS_ROOT),
            "mingw_bin": str(mingw_bin),
            "usr_bin": str(usr_bin),
            "script_exists": WSJTZ_ENGINE_RUN_SCRIPT.exists(),
            "exe_exists": exe.exists(),
            "decoder_exists": decoder.exists(),
            "mingw_bin_exists": mingw_bin.exists(),
            "usr_bin_exists": usr_bin.exists(),
        }

    def launch_patched_engine(self, req: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start the locally built OM0RX-patched WSJT-X engine on Windows."""
        req = req or {}
        status = self.get_patched_engine_status()
        if not status["supported"]:
            raise HTTPException(status_code=400, detail="Patched WSJT engine launcher is currently Windows-only")
        if not status["script_exists"]:
            raise HTTPException(status_code=404, detail=f"Run script not found: {status['script']}")
        if not status["exe_exists"]:
            raise HTTPException(status_code=404, detail="Patched wsjtx.exe not found. Build the OM0RX WSJT engine first.")
        if not status["decoder_exists"]:
            raise HTTPException(status_code=404, detail="Patched jt9.exe not found. Build the OM0RX WSJT engine first.")
        if not status["mingw_bin_exists"]:
            raise HTTPException(status_code=404, detail=f"MSYS2 MinGW bin not found: {status['mingw_bin']}")

        rig_name = str(req.get("rigName") or "OM0RX-AUTO").strip() or "OM0RX-AUTO"
        config_name = str(req.get("configName") or "OM0RX-AUTO").strip() or "OM0RX-AUTO"
        test_mode = _coerce_bool(req.get("testMode"), False)
        dry_run = _coerce_bool(req.get("dryRun"), False)

        command = [
            status["exe"],
            "--rig-name",
            rig_name,
            "--config",
            config_name,
        ]
        if test_mode:
            command.append("--test-mode")

        existing_pids = _patched_engine_process_ids(rig_name, test_mode=test_mode)
        log_paths = _patched_engine_log_paths(rig_name)

        result = {
            "success": True,
            "dry_run": dry_run,
            "rig_name": rig_name,
            "config_name": config_name,
            "test_mode": test_mode,
            "command": command,
            "existing_pids": existing_pids,
            "engine": status,
            "stdout_log": str(log_paths["stdout"]),
            "stderr_log": str(log_paths["stderr"]),
        }
        if dry_run:
            result["message"] = "Patched WSJT engine launcher prerequisites are available"
            return result
        if existing_pids:
            result["already_running"] = True
            result["message"] = f"Patched WSJT engine is already running for {rig_name}"
            return result

        log_root = log_paths["stdout"].parent
        log_root.mkdir(parents=True, exist_ok=True)
        out_log = log_paths["stdout"]
        err_log = log_paths["stderr"]
        env = os.environ.copy()
        env["PATH"] = f"{status['mingw_bin']};{status['usr_bin']};{env.get('PATH', '')}"
        out_handle = None
        err_handle = None
        try:
            out_handle = out_log.open("ab")
            err_handle = err_log.open("ab")
            process = subprocess.Popen(
                command,
                cwd=str(PATCHED_ENGINE_BUILD_ROOT),
                stdout=out_handle,
                stderr=err_handle,
                creationflags=_process_creation_flags(),
                env=env,
                close_fds=False,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not start patched WSJT engine: {exc}") from exc
        finally:
            if out_handle:
                out_handle.close()
            if err_handle:
                err_handle.close()

        result.update({
            "pid": process.pid,
            "stdout_log": str(out_log),
            "stderr_log": str(err_log),
            "message": "Patched WSJT engine launch command completed",
        })
        return result

    def launch_wsjtz_engine(self, req: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start the locally built OM0RX WSJT-Z engine on Windows."""
        req = req or {}
        status = self.get_wsjtz_engine_status()
        if not status["supported"]:
            raise HTTPException(status_code=400, detail="WSJT-Z engine launcher is currently Windows-only")
        if not status["script_exists"]:
            raise HTTPException(status_code=404, detail=f"Run script not found: {status['script']}")
        if not status["exe_exists"]:
            raise HTTPException(status_code=404, detail="Clean OM0RX WSJT-Z executable not found. Build the clean WSJT-Z engine first.")
        if not status["decoder_exists"]:
            raise HTTPException(status_code=404, detail="OM0RX WSJT-Z jt9.exe not found. Build the OM0RX WSJT-Z engine first.")
        if not status["mingw_bin_exists"]:
            raise HTTPException(status_code=404, detail=f"MSYS2 MinGW bin not found: {status['mingw_bin']}")

        rig_name = str(req.get("rigName") or "OM0RX-WSJT-Z").strip() or "OM0RX-WSJT-Z"
        config_name = str(req.get("configName") or "OM0RX-WSJT-Z").strip() or "OM0RX-WSJT-Z"
        test_mode = _coerce_bool(req.get("testMode"), False)
        dry_run = _coerce_bool(req.get("dryRun"), False)

        command = [
            status["exe"],
            "--rig-name",
            rig_name,
            "--config",
            config_name,
        ]
        if test_mode:
            command.append("--test-mode")

        exe_name = Path(status["exe"]).name
        existing_pids = _wsjt_engine_process_ids(exe_name, rig_name, test_mode=test_mode)
        log_paths = _patched_engine_log_paths(rig_name, app_prefix="wsjt-z")

        result = {
            "success": True,
            "dry_run": dry_run,
            "rig_name": rig_name,
            "config_name": config_name,
            "test_mode": test_mode,
            "command": command,
            "existing_pids": existing_pids,
            "engine": status,
            "stdout_log": str(log_paths["stdout"]),
            "stderr_log": str(log_paths["stderr"]),
        }
        if dry_run:
            result["message"] = "OM0RX WSJT-Z launcher prerequisites are available"
            return result
        if existing_pids:
            result["already_running"] = True
            result["message"] = f"OM0RX WSJT-Z is already running for {rig_name}"
            return result

        script_command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            status["script"],
            "-ProjectRoot",
            str(PROJECT_ROOT),
            "-MsysRoot",
            status["msys_root"],
            "-RigName",
            rig_name,
            "-ConfigName",
            config_name,
        ]
        if test_mode:
            script_command.append("-TestMode")
        out_handle = None
        err_handle = None
        try:
            log_paths["stdout"].parent.mkdir(parents=True, exist_ok=True)
            out_handle = open(log_paths["stdout"], "a", encoding="utf-8")
            err_handle = open(log_paths["stderr"], "a", encoding="utf-8")
            process = subprocess.Popen(
                script_command,
                cwd=str(PROJECT_ROOT),
                stdout=out_handle,
                stderr=err_handle,
                text=True,
                creationflags=_process_creation_flags(),
                close_fds=False,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not start OM0RX WSJT-Z: {exc}") from exc
        finally:
            if out_handle:
                out_handle.close()
            if err_handle:
                err_handle.close()

        time.sleep(1.0)
        launched_pids = _wsjt_engine_process_ids(exe_name, rig_name, test_mode=test_mode)

        result.update({
            "launcher_pid": process.pid,
            "pid": launched_pids[0] if launched_pids else None,
            "script_command": script_command,
            "message": "OM0RX WSJT-Z launch command completed",
        })
        return result

    def get_launch_logs(self, rig_name: str = "OM0RX-AUTO", lines: int = 120) -> Dict[str, Any]:
        """Return recent stdout/stderr lines for the patched WSJT launcher profile."""
        rig_name = str(rig_name or "OM0RX-AUTO").strip() or "OM0RX-AUTO"
        line_count = max(1, min(int(lines or 120), 500))
        log_paths = _patched_engine_log_paths(rig_name)
        stdout = _tail_text_file(log_paths["stdout"], line_count)
        stderr = _tail_text_file(log_paths["stderr"], line_count)
        return {
            "success": True,
            "rig_name": rig_name,
            "lines": line_count,
            "logs": {
                "stdout": stdout,
                "stderr": stderr,
            },
        }

    def get_launch_preflight(self, req: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Dry-run the patched WSJT launch path and verify bridge listener readiness."""
        req = req or {}
        engine_key = str(req.get("engine") or "wsjtx").strip().lower()
        is_wsjtz = engine_key in {"wsjtz", "wsjt-z"}
        default_profile = "OM0RX-WSJT-Z" if is_wsjtz else "OM0RX-AUTO"
        engine_label = "OM0RX WSJT-Z" if is_wsjtz else "patched WSJT engine"
        launcher = self.launch_wsjtz_engine if is_wsjtz else self.launch_patched_engine
        rig_name = str(req.get("rigName") or default_profile).strip() or default_profile
        config_name = str(req.get("configName") or default_profile).strip() or default_profile
        test_mode = _coerce_bool(req.get("testMode"), False)
        command_url = getattr(config, 'WSJTX_BRIDGE_COMMAND_URL', 'http://127.0.0.1:8092/wsjtx/command')
        status_url = _command_url_to_status_url(command_url)
        parsed_command = urlparse(command_url)
        command_host = parsed_command.hostname or "127.0.0.1"
        command_port = parsed_command.port or (443 if parsed_command.scheme == "https" else 80)
        ws_port = int(getattr(config, 'WSJTX_WS_PORT', 8091) or 8091)
        udp_port = int(getattr(config, 'WSJTX_UDP_PORT', 2237) or 2237)
        multicast = getattr(config, 'WSJTX_UDP_MULTICAST', '224.0.0.1')

        health = self.get_health()
        launcher_result: Dict[str, Any]
        launcher_ok = False
        launcher_error = ""
        try:
            launcher_result = launcher({
                "rigName": rig_name,
                "configName": config_name,
                "testMode": test_mode,
                "dryRun": True,
            })
            launcher_ok = bool(launcher_result.get("success"))
        except HTTPException as exc:
            launcher_result = {"success": False, "detail": exc.detail}
            launcher_error = str(exc.detail)
        except Exception as exc:
            launcher_result = {"success": False, "detail": str(exc)}
            launcher_error = str(exc)

        command_tcp = _tcp_endpoint_check(command_host, command_port)
        websocket_tcp = _tcp_endpoint_check("127.0.0.1", ws_port)
        bridge_status = health.get("bridge", {}).get("status") if isinstance(health.get("bridge"), dict) else {}
        bridge_udp_enabled = bool(bridge_status.get("enabled")) if isinstance(bridge_status, dict) else False

        checks: list[Dict[str, Any]] = []

        def add_check(
            check_id: str,
            label: str,
            check_status: str,
            check_detail: str,
            *,
            critical: bool = False,
            value_text: str = "",
        ) -> None:
            checks.append({
                "id": check_id,
                "label": label,
                "status": check_status,
                "detail": check_detail,
                "critical": critical,
                "value": value_text,
            })

        add_check(
            "launcher-dry-run",
            "Launcher dry-run",
            "ok" if launcher_ok else "fail",
            (
                f"{engine_label} can be launched for profile {rig_name}/{config_name}"
                if launcher_ok else
                f"{engine_label} dry-run failed: {launcher_error or launcher_result.get('detail') or 'unknown error'}"
            ),
            critical=True,
            value_text=launcher_result.get("message", "") if launcher_ok else launcher_error,
        )
        add_check(
            "command-status-http",
            "Command status endpoint",
            "ok" if health.get("bridge", {}).get("reachable") else "fail",
            f"Bridge status endpoint responded at {status_url}" if health.get("bridge", {}).get("reachable") else f"Bridge status endpoint is not reachable at {status_url}",
            critical=True,
            value_text=status_url,
        )
        add_check(
            "command-port",
            "Command TCP port",
            "ok" if command_tcp.get("ok") else "fail",
            f"TCP connection succeeded to {command_host}:{command_port}" if command_tcp.get("ok") else f"TCP connection failed to {command_host}:{command_port}: {command_tcp.get('error')}",
            critical=True,
            value_text=command_url,
        )
        add_check(
            "websocket-port",
            "Bridge WebSocket port",
            "ok" if websocket_tcp.get("ok") else "warn",
            f"Bridge websocket listener accepted TCP on 127.0.0.1:{ws_port}" if websocket_tcp.get("ok") else f"Bridge websocket TCP probe failed on 127.0.0.1:{ws_port}: {websocket_tcp.get('error')}",
            value_text=f"ws://127.0.0.1:{ws_port}",
        )
        add_check(
            "udp-reporting",
            "WSJT UDP reporting",
            "ok" if bridge_udp_enabled else "warn",
            (
                f"Bridge reports WSJT UDP listener enabled on {multicast}:{udp_port}"
                if bridge_udp_enabled else
                f"Bridge status did not report WSJT UDP listener enabled for {multicast}:{udp_port}"
            ),
            value_text=f"{multicast}:{udp_port}",
        )
        add_check(
            "active-client",
            "Active WSJT client",
            "ok" if health.get("client_fresh") else ("warn" if health.get("client") else "warn"),
            (
                f"{(health.get('client') or {}).get('id')} heartbeat is fresh"
                if health.get("client_fresh") else
                ("A WSJT client exists but heartbeat is stale" if health.get("client") else "No active WSJT client is currently attached")
            ),
            value_text=(health.get("client") or {}).get("id", "no client") if isinstance(health.get("client"), dict) else "no client",
        )
        add_check(
            "automation-profile",
            "Automation profile",
            "ok" if health.get("extended_target_supported") else "warn",
            "OM0RX patched target command is visible" if health.get("extended_target_supported") else "OM0RX patched target command is not currently visible; start the OM0RX engine profile",
            value_text="OM0RX" if health.get("extended_target_supported") else "not detected",
        )

        ready = all(
            check["status"] == "ok"
            for check in checks
            if check.get("critical")
        )

        return {
            "success": True,
            "ready": ready,
            "engine": "wsjtz" if is_wsjtz else "wsjtx",
            "rig_name": rig_name,
            "config_name": config_name,
            "test_mode": test_mode,
            "checks": checks,
            "validation": {
                "critical_total": sum(1 for check in checks if check.get("critical")),
                "critical_ok": sum(1 for check in checks if check.get("critical") and check.get("status") == "ok"),
                "warnings": sum(1 for check in checks if check.get("status") == "warn"),
                "failures": sum(1 for check in checks if check.get("status") == "fail"),
            },
            "launcher": launcher_result,
            "health": health,
            "ports": {
                "command": command_tcp,
                "websocket": websocket_tcp,
                "udp": {
                    "host": multicast,
                    "port": udp_port,
                    "bridge_enabled": bridge_udp_enabled,
                },
            },
        }

    def get_bridge_status(self) -> Dict[str, Any]:
        url = _command_url_to_status_url(
            getattr(config, 'WSJTX_BRIDGE_COMMAND_URL', 'http://127.0.0.1:8092/wsjtx/command')
        )
        bridge_token = str(getattr(config, "WSJTX_BRIDGE_TOKEN", "") or "")
        headers = {"Accept": "application/json"}
        if bridge_token:
            headers["X-OM0RX-Control-Token"] = bridge_token
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=1.0) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}

    def get_health(self) -> Dict[str, Any]:
        """Return current WSJT bridge/client health and local engine visibility."""
        enabled = bool(getattr(config, 'WSJTX_ENABLED', True))
        command_url = getattr(config, 'WSJTX_BRIDGE_COMMAND_URL', 'http://127.0.0.1:8092/wsjtx/command')
        status_url = _command_url_to_status_url(command_url)
        bridge_status: Dict[str, Any] = {}
        bridge_error = ""

        try:
            bridge_status = self.get_bridge_status()
        except Exception as exc:
            bridge_error = str(exc)

        client = bridge_status.get("client") if isinstance(bridge_status.get("client"), dict) else None
        bridge_stats = bridge_status.get("stats") if isinstance(bridge_status.get("stats"), dict) else {}
        bridge_capabilities = bridge_status.get("capabilities") if isinstance(bridge_status.get("capabilities"), dict) else {}
        bridge_timeline = _normalise_bridge_timeline(bridge_status.get("timeline"))
        client_id = str((client or {}).get("id") or "")
        last_seen_ms = _coerce_int((client or {}).get("lastSeenMs"))
        last_decode_age_ms = _coerce_int(bridge_stats.get("lastDecodeAgeMs"))
        bridge_reachable = bool(bridge_status.get("success")) and not bridge_error
        client_fresh = bool(client) and (last_seen_ms is None or last_seen_ms <= WSJT_CLIENT_FRESH_MS)
        decode_fresh = last_decode_age_ms is not None and last_decode_age_ms <= 90_000
        patched_hint = "OM0RX" in client_id.upper()
        bridge_extended_command_supported = bool(bridge_capabilities.get("start_target_qso"))
        engine = self.get_patched_engine_status()
        patched_pids = _patched_engine_process_ids("OM0RX-AUTO")
        patched_decoder_pids = _patched_engine_decoder_process_ids("OM0RX-AUTO")
        process_names = _visible_process_names({
            "wsjtx.exe",
            "wsjt-x.exe",
            "wsjt-z.exe",
            "wsjtz.exe",
            "jt9.exe",
            "msysjt9.exe",
        })
        decoder_running = bool(process_names.get("jt9.exe") or process_names.get("msysjt9.exe") or patched_decoder_pids)
        wsjtx_running = bool(
            process_names.get("wsjtx.exe")
            or process_names.get("wsjt-x.exe")
            or process_names.get("wsjt-z.exe")
            or process_names.get("wsjtz.exe")
            or patched_pids
        )

        if not enabled:
            status = "off"
            value = "disabled"
            detail = "WSJT-X integration is disabled in config"
        elif not bridge_reachable:
            status = "warn"
            value = "bridge down"
            detail = f"Bridge status endpoint unavailable: {bridge_error or command_url}"
        elif not client:
            status = "warn"
            value = "no client"
            detail = "Bridge is running but no WSJT-X/WSJT-Z client has been seen"
        elif not client_fresh:
            status = "warn"
            value = f"stale {round((last_seen_ms or 0) / 1000)}s"
            detail = f"Last WSJT heartbeat from {client_id or 'client'} is stale"
        elif patched_hint:
            status = "ok"
            value = "OM0RX engine"
            if decode_fresh and bridge_stats.get("lastDecode"):
                detail = f"{client_id}; decoding; extended target command available"
            else:
                detail = f"{client_id}; extended target command available"
        else:
            status = "ok"
            value = "WSJT client"
            detail = f"{client_id}; stock WSJT command set"

        engine_ready = bool(
            engine.get("supported")
            and engine.get("script_exists")
            and engine.get("exe_exists")
            and engine.get("decoder_exists")
            and engine.get("mingw_bin_exists")
            and engine.get("usr_bin_exists")
        )
        checks: list[Dict[str, Any]] = []

        def add_check(
            check_id: str,
            label: str,
            check_status: str,
            check_detail: str,
            *,
            critical: bool = False,
            value_text: str = "",
        ) -> None:
            checks.append({
                "id": check_id,
                "label": label,
                "status": check_status,
                "detail": check_detail,
                "critical": critical,
                "value": value_text,
            })

        add_check(
            "enabled",
            "Integration enabled",
            "ok" if enabled else "off",
            "WSJT-X integration is enabled" if enabled else "Enable WSJT-X integration before using automation",
            critical=True,
            value_text="enabled" if enabled else "disabled",
        )
        add_check(
            "bridge",
            "Bridge command API",
            "ok" if bridge_reachable else "fail",
            f"Bridge status endpoint reachable at {status_url}" if bridge_reachable else f"Bridge status unavailable: {bridge_error or status_url}",
            critical=True,
            value_text=command_url,
        )
        if not client:
            add_check(
                "client",
                "WSJT client heartbeat",
                "fail",
                "Bridge is running, but no WSJT-X/WSJT-Z client heartbeat has been seen",
                critical=True,
                value_text="no client",
            )
        elif client_fresh:
            add_check(
                "client",
                "WSJT client heartbeat",
                "ok",
                f"{client_id or 'WSJT client'} seen {_format_age_ms(last_seen_ms)}",
                critical=True,
                value_text=client_id,
            )
        else:
            add_check(
                "client",
                "WSJT client heartbeat",
                "warn",
                f"{client_id or 'WSJT client'} heartbeat is stale ({_format_age_ms(last_seen_ms)})",
                critical=True,
                value_text=client_id,
            )
        add_check(
            "profile",
            "OM0RX automation profile",
            "ok" if patched_hint else ("warn" if client else "fail"),
            (
                f"{client_id} exposes the patched OM0RX target command"
                if patched_hint else
                (f"{client_id or 'WSJT client'} looks like a stock profile; target prepare may be limited" if client else "No WSJT client profile detected")
            ),
            critical=True,
            value_text=client_id or "none",
        )
        add_check(
            "extended-target",
            "Extended target command",
            "ok" if patched_hint else ("warn" if client else "fail"),
            "Cluster/spot prepare can use the OM0RX WSJT target command" if patched_hint else "Use the OM0RX-patched WSJT engine for full target control",
            critical=True,
            value_text="available" if patched_hint else "not detected",
        )
        if decode_fresh and bridge_stats.get("lastDecode"):
            last_decode = bridge_stats.get("lastDecode") or {}
            add_check(
                "decode",
                "Decode freshness",
                "ok",
                f"{last_decode.get('message') or 'last decode'} seen {_format_age_ms(last_decode_age_ms)}",
                value_text=f"{bridge_stats.get('decodes', 0)} decodes",
            )
        elif bridge_stats.get("lastDecode"):
            last_decode = bridge_stats.get("lastDecode") or {}
            add_check(
                "decode",
                "Decode freshness",
                "warn",
                f"Last decode is stale: {last_decode.get('message') or 'decode'} seen {_format_age_ms(last_decode_age_ms)}",
                value_text=f"{bridge_stats.get('decodes', 0)} decodes",
            )
        else:
            add_check(
                "decode",
                "Decode freshness",
                "warn",
                "No decode has been seen from the bridge yet",
                value_text=f"{bridge_stats.get('decodes', 0)} decodes",
            )
        logged_count = _coerce_int(bridge_stats.get("logged")) or 0
        logged_uploads = _coerce_int(bridge_stats.get("loggedUploads")) or 0
        logged_upload_errors = _coerce_int(bridge_stats.get("loggedUploadErrors")) or 0
        if logged_upload_errors > 0:
            last_upload = bridge_stats.get("lastLoggedUpload") or {}
            add_check(
                "logged-qso",
                "Logged QSO UDP",
                "warn",
                f"WSJT logged-QSO upload errors: {last_upload.get('error') or logged_upload_errors}",
                value_text=f"{logged_count} logged UDP, {logged_uploads} uploads",
            )
        elif logged_count > 0 or logged_uploads > 0:
            add_check(
                "logged-qso",
                "Logged QSO UDP",
                "ok",
                "WSJT logged-QSO events are reaching the bridge and backend upload path",
                value_text=f"{logged_count} logged UDP, {logged_uploads} uploads",
            )
        else:
            add_check(
                "logged-qso",
                "Logged QSO UDP",
                "warn",
                "No WSJT logged-QSO UDP event has been received in this bridge session yet",
                value_text="0 logged UDP",
            )
        add_check(
            "engine-build",
            "Patched engine build",
            "ok" if engine_ready else ("warn" if not engine.get("supported") else "fail"),
            (
                f"Launcher, wsjtx.exe, jt9.exe, and MSYS runtime are available under {engine.get('build_root')}"
                if engine_ready else
                ("Patched engine launcher is only available on Windows from this local app" if not engine.get("supported") else "One or more patched WSJT engine files are missing")
            ),
            critical=True,
            value_text="ready" if engine_ready else "missing",
        )
        add_check(
            "processes",
            "Local process visibility",
            "ok" if (wsjtx_running and decoder_running) else "warn",
            (
                "WSJT and decoder processes are visible locally"
                if wsjtx_running and decoder_running else
                "Process scan did not see both WSJT and decoder; the bridge heartbeat is the stronger live signal"
            ),
            value_text=f"WSJT {'seen' if wsjtx_running else 'not seen'}, decoder {'seen' if decoder_running else 'not seen'}",
        )
        critical_ready = all(
            check["status"] == "ok"
            for check in checks
            if check.get("critical")
        )

        return {
            "success": True,
            "enabled": enabled,
            "status": status,
            "value": value,
            "detail": detail,
            "checks": checks,
            "validation": {
                "ready": critical_ready,
                "critical_total": sum(1 for check in checks if check.get("critical")),
                "critical_ok": sum(1 for check in checks if check.get("critical") and check.get("status") == "ok"),
                "warnings": sum(1 for check in checks if check.get("status") == "warn"),
                "failures": sum(1 for check in checks if check.get("status") == "fail"),
            },
            "engine": engine,
            "bridge": {
                "reachable": bridge_reachable,
                "command_url": command_url,
                "status_url": status_url,
                "status": bridge_status,
                "stats": bridge_stats,
                "capabilities": bridge_capabilities,
                "timeline": bridge_timeline,
                "last_command": bridge_stats.get("lastCommand") if isinstance(bridge_stats, dict) else None,
                "error": bridge_error,
            },
            "client": client,
            "client_fresh": client_fresh,
            "last_seen_ms": last_seen_ms,
            "decode_fresh": decode_fresh,
            "last_decode_age_ms": last_decode_age_ms,
            "last_decode": bridge_stats.get("lastDecode") if isinstance(bridge_stats, dict) else None,
            "extended_target_supported": patched_hint,
            "bridge_extended_command_supported": bridge_extended_command_supported,
            "timeline": bridge_timeline,
            "processes": {
                "wsjtx": wsjtx_running,
                "decoder": decoder_running,
                "patched_pids": patched_pids,
                "patched_decoder_pids": patched_decoder_pids,
                "names": process_names,
            },
        }

    def normalize_spot_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Accept either a flat spot payload or {spot, options}."""
        if not isinstance(req, dict):
            raise HTTPException(status_code=400, detail="Spot payload must be an object")

        spot = req.get("spot") if isinstance(req.get("spot"), dict) else req
        options = req.get("options") if isinstance(req.get("options"), dict) else {}
        return {**spot, **options}

    def build_target_from_spot(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Build a patched-engine WSJT target command from a cluster/RBL spot."""
        req = self.normalize_spot_request(req)

        call = str(_first_present(req, "callsign", "call", "dxCall") or "").strip().upper()
        if not call:
            raise HTTPException(status_code=400, detail="Missing callsign")

        dial_frequency = _frequency_hz_from_payload(req)
        if not dial_frequency:
            raise HTTPException(status_code=400, detail="Missing frequency")

        khz = dial_frequency / 1000
        band = str(req.get("band") or band_from_khz(khz) or "").strip()
        comment = str(req.get("comment") or req.get("notes") or "")
        mode = str(req.get("mode") or "").strip().upper()
        if not mode or mode == "DIGI":
            mode = infer_mode(comment, band, khz)
        if mode not in WSJT_TARGET_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Spot mode {mode or 'unknown'} is not a WSJT target mode",
            )
        trace_id = _wsjtx_trace_id(req)

        target: Dict[str, Any] = {
            "traceId": trace_id,
            "call": call,
            "mode": mode,
            "band": band,
            "dialFrequency": dial_frequency,
            "trPeriod": _coerce_int(req.get("trPeriod")) or WSJT_MODE_PERIODS[mode],
            "rxDf": _coerce_int(_first_present(req, "rxDf", "rx_df", "rxAudio")) or 1500,
            "txDf": _coerce_int(_first_present(req, "txDf", "tx_df", "txAudio")) or 1500,
            "generateMessages": _coerce_bool(req.get("generateMessages"), True),
            "holdTxFreq": _coerce_bool(req.get("holdTxFreq"), True),
            "enableTx": _coerce_bool(req.get("enableTx"), False),
        }
        references = _first_present(req, "reference_items", "references")
        if references:
            target["references"] = references

        grid = _normalise_grid_value(_first_present(req, "grid", "dxGrid", "gridsquare"))
        if grid:
            target["grid"] = grid

        for source_key, target_key in (
            ("frequencyTolerance", "frequencyTolerance"),
            ("submode", "submode"),
            ("txMessageNumber", "txMessageNumber"),
            ("targetId", "targetId"),
            ("commandId", "commandId"),
            ("call_status", "call_status"),
            ("dxcc_status", "dxcc_status"),
            ("huntReason", "huntReason"),
        ):
            value = _first_present(req, source_key)
            if value not in (None, ""):
                target[target_key] = value

        if "fastMode" in req:
            target["fastMode"] = _coerce_bool(req.get("fastMode"), False)
        if "txFirst" in req:
            target["txFirst"] = _coerce_bool(req.get("txFirst"), False)

        return target

    def build_target_from_automation_target(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Build a patched-engine WSJT target command from a ranked Digital target."""
        if not isinstance(req, dict):
            raise HTTPException(status_code=400, detail="Automation target payload must be an object")

        payload = req.get("target") if isinstance(req.get("target"), dict) else req
        options = req.get("options") if isinstance(req.get("options"), dict) else {}
        source = {**payload, **options}

        spot_like: Dict[str, Any] = {
            "callsign": _first_present(source, "callsign", "call"),
            "mode": _first_present(source, "mode"),
            "band": _first_present(source, "band"),
            "grid": _first_present(source, "grid", "gridsquare"),
            "call_status": _first_present(source, "call_status", "callStatus"),
            "dxcc_status": _first_present(source, "dxcc_status", "dxccStatus"),
            "score": _first_present(source, "score"),
            "rxDf": _first_present(source, "rxDf", "rx_df", "freq", "audio_offset", "rx_audio_hz"),
            "txDf": _first_present(source, "txDf", "tx_df", "tx_audio_hz"),
            "generateMessages": _first_present(source, "generateMessages"),
            "holdTxFreq": _first_present(source, "holdTxFreq"),
            "frequencyTolerance": _first_present(source, "frequencyTolerance"),
            "txMessageNumber": _first_present(source, "txMessageNumber"),
            "txFirst": _first_present(source, "txFirst"),
            "traceId": _first_present(source, "traceId", "trace_id", "correlationId", "correlation_id", "requestId", "request_id"),
            "targetId": _first_present(source, "targetId", "target_id"),
            "commandId": _first_present(source, "commandId", "command_id"),
            "references": _first_present(source, "reference_items", "references"),
        }

        frequency_value = _first_present(
            source,
            "dialFrequency",
            "dial_frequency",
            "frequency_hz",
            "base_frequency",
            "frequency_mhz",
            "frequency",
        )
        if frequency_value not in (None, ""):
            parsed_frequency = _coerce_float(frequency_value)
            if parsed_frequency is not None and parsed_frequency >= 1_000_000:
                spot_like["frequency_hz"] = int(round(parsed_frequency))
            else:
                spot_like["frequency_mhz"] = parsed_frequency

        target = self.build_target_from_spot(spot_like)
        for source_key, target_key in (
            (("message",), "message"),
            (("source",), "source"),
            (("continent",), "continent"),
            (("country",), "country"),
            (("snr",), "snr"),
            (("directCaller", "direct_caller"), "directCaller"),
        ):
            value = _first_present(source, *source_key)
            if value not in (None, ""):
                target[target_key] = value
        for source_key, target_key in (
            (("targetId", "target_id"), "targetId"),
            (("commandId", "command_id"), "commandId"),
        ):
            value = _first_present(source, *source_key)
            if value not in (None, ""):
                target[target_key] = str(value)
        target["enableTx"] = _coerce_bool(_first_present(source, "enableTx"), False)
        target["generateMessages"] = _coerce_bool(_first_present(source, "generateMessages"), True)
        target["holdTxFreq"] = _coerce_bool(_first_present(source, "holdTxFreq"), True)
        return target

    def assess_target_policy(self, target: Dict[str, Any], req: Dict[str, Any], action: str = "prepare") -> Dict[str, Any]:
        """Return the operator guardrails for a prepared or armed WSJT target."""
        payload = self.normalize_spot_request(req)
        call_status = _normalise_status_text(_first_present(payload, "call_status", "callStatus"))
        dxcc_status = _normalise_status_text(_first_present(payload, "dxcc_status", "dxccStatus"))
        score = _coerce_int(_first_present(payload, "score", "spot_score"))
        mode = _normalise_status_text(target.get("mode"))
        period = _coerce_int(target.get("trPeriod")) or WSJT_MODE_PERIODS.get(mode, 15)

        status_text = f"{call_status} {dxcc_status}"
        has_needed_signal = any(
            token in status_text
            for token in ("ATNO", "NEW CALL", "NEW BAND", "NEW MODE", "NEW BAND+MODE", "NEEDED")
        )
        known_already_worked = any(token in status_text for token in ("CONFIRMED", "WORKED")) and not has_needed_signal

        reasons = []
        eligible = True
        if mode not in WSJT_TARGET_MODES:
            eligible = False
            reasons.append(f"{mode or 'unknown'} is not a WSJT target mode")
        if known_already_worked:
            eligible = False
            reasons.append("target appears already worked/confirmed with no new slot")
        if score is not None and score <= 0 and not has_needed_signal:
            eligible = False
            reasons.append("spot score is not positive")
        if not reasons:
            reasons.append("target is eligible for the requested WSJT action")

        now = datetime.now(timezone.utc)
        seconds_into_slot = (now.second + (now.microsecond / 1_000_000)) % period
        next_slot_seconds = 0 if seconds_into_slot <= 2.0 else round(period - seconds_into_slot, 2)

        return {
            "action": action,
            "eligible": eligible,
            "reasons": reasons,
            "call_status": call_status or "UNKNOWN",
            "dxcc_status": dxcc_status or "UNKNOWN",
            "score": score,
            "slot": {
                "period": period,
                "seconds_into_slot": round(seconds_into_slot, 2),
                "next_safe_tx_seconds": next_slot_seconds,
            },
        }

    def send_bridge_command(self, command: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Forward a WSJT-X command to the local Node bridge.

        The bridge owns the live UDP return endpoint because it observes WSJT-X
        heartbeat/status packets. Sending directly from FastAPI would usually
        target the wrong port.
        """
        url = getattr(config, 'WSJTX_BRIDGE_COMMAND_URL', 'http://127.0.0.1:8092/wsjtx/command')
        payload = dict(payload or {})
        trace_id = _wsjtx_trace_id(payload)
        payload.setdefault("traceId", trace_id)
        if isinstance(payload.get("target"), dict):
            target = dict(payload["target"])
            target.setdefault("traceId", trace_id)
            payload["target"] = target
        request_payload = json.dumps({
            "command": command,
            "payload": payload,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        bridge_token = str(getattr(config, "WSJTX_BRIDGE_TOKEN", "") or "")
        if bridge_token:
            headers["X-OM0RX-Control-Token"] = bridge_token
        request = urllib.request.Request(
            url,
            data=request_payload,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=2.0) as response:
                data = response.read().decode("utf-8")
                result = json.loads(data) if data else {"success": True}
                if isinstance(result, dict):
                    result.setdefault("traceId", trace_id)
                return result
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
            except Exception:
                parsed = {"success": False, "error": detail or str(e)}
            raise HTTPException(status_code=e.code, detail=parsed)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"WSJT-X bridge command API unavailable: {e}")


# Global service instance
_wsjtx_service: Optional[WSJTXService] = None


def get_wsjtx_service() -> WSJTXService:
    """Get the global WSJT-X service instance"""
    global _wsjtx_service
    if _wsjtx_service is None:
        _wsjtx_service = WSJTXService()
    return _wsjtx_service


def _normalise_wsjtx_automation_policy(req: Dict[str, Any]) -> Dict[str, Any]:
    """Translate native OM0RX WSJT-X automation controls into backend settings."""
    automation = req.get("automation") if isinstance(req.get("automation"), dict) else dict(req)
    auto_call = _coerce_bool(_first_present(automation, "autoCall", "auto_call"), False)
    auto_cq = _coerce_bool(_first_present(automation, "autoCQ", "auto_cq"), False)
    cq_only = _coerce_bool(_first_present(automation, "cqOnly", "cq_only"), True)
    min_signal = _coerce_int(_first_present(automation, "minSignal", "min_signal"))
    auto_call_limit = _coerce_int(_first_present(automation, "autoCallLimit", "auto_call_limit"))
    auto_cq_limit = _coerce_int(_first_present(automation, "autoCQLimit", "auto_cq_limit"))
    watchdog_ft8 = _coerce_int(_first_present(automation, "watchdogFT8", "watchdog_ft8"))
    watchdog_ft4 = _coerce_int(_first_present(automation, "watchdogFT4", "watchdog_ft4"))
    hop_interval_seconds = _coerce_int(_first_present(automation, "hopIntervalSeconds", "hop_interval_seconds"))
    band_hopping = _coerce_bool(_first_present(automation, "bandHopping", "band_hopping"), False)
    mode_switching = _coerce_bool(_first_present(automation, "modeSwitching", "mode_switching"), False)
    current_mode = str(_first_present(automation, "currentMode", "current_mode", "mode") or "").strip().upper()
    if current_mode not in {"FT8", "FT4", "FT2"}:
        current_mode = ""
    priority = str(_first_present(automation, "priority") or "last").strip() or "last"
    priority_aliases = {
        "last_decoded": "last",
        "last decoded": "last",
        "signal strength": "signal",
    }
    priority = priority_aliases.get(priority.lower(), priority)

    operator_automation = {
        "enabled": auto_call or auto_cq or _coerce_bool(_first_present(automation, "enabled"), False),
        "spotHuntEnabled": _coerce_bool(_first_present(automation, "spotHuntEnabled", "spot_hunt_enabled"), auto_call and band_hopping),
        "bandHopping": band_hopping,
        "modeSwitching": mode_switching,
        "treat73AsCQ": _coerce_bool(_first_present(automation, "treat73AsCQ", "treat_73_as_cq"), False),
        "avoidLogged": _coerce_bool(_first_present(automation, "avoidLogged", "avoid_logged"), True),
        "requireHeardBeforeCall": _coerce_bool(_first_present(automation, "requireHeardBeforeCall", "require_heard_before_call"), True),
        "autoLogToWavelog": _coerce_bool(_first_present(automation, "autoLogToWavelog", "auto_log_to_wavelog"), True),
        "needCall": _coerce_bool(_first_present(automation, "needCall", "need_call"), True),
        "needDxcc": _coerce_bool(_first_present(automation, "needDxcc", "need_dxcc"), True),
        "needBand": _coerce_bool(_first_present(automation, "needBand", "need_band"), True),
        "needMode": _coerce_bool(_first_present(automation, "needMode", "need_mode"), True),
        "needGrid": _coerce_bool(_first_present(automation, "needGrid", "need_grid"), True),
        "needReference": _coerce_bool(_first_present(automation, "needReference", "need_reference"), False),
        "filterMatrixEnabled": _coerce_bool(
            _first_present(automation, "filterMatrixEnabled", "filter_matrix_enabled"),
            False,
        ),
        "filterNew": _first_present(automation, "filterNew", "filter_new") or {},
        "filterNewOnBand": _first_present(automation, "filterNewOnBand", "filter_new_on_band") or {},
        "filterContinents": _first_present(automation, "filterContinents", "filter_continents", "continents") or {},
        "lotwOnly": _coerce_bool(_first_present(automation, "lotwOnly", "lotw_only"), False),
        "answerDirectCallers": _coerce_bool(_first_present(automation, "answerDirectCallers", "answer_direct_callers"), True),
        "dryRun": _coerce_bool(_first_present(automation, "dryRun", "dry_run"), False),
        "priority": priority,
    }
    current_band = str(_first_present(automation, "currentBand", "current_band") or "").strip().lower()
    if current_band:
        operator_automation["currentBand"] = current_band
    if not mode_switching and current_mode:
        operator_automation["allowedModes"] = {current_mode: True}
    if hop_interval_seconds is not None:
        operator_automation["hopIntervalSeconds"] = max(30, min(7200, hop_interval_seconds))
    band_plan = _first_present(automation, "bandPlan", "band_plan")
    if band_plan is not None:
        operator_automation["bandPlan"] = str(band_plan)
    for ignore_key in ("ignoreList", "ignore_list", "ignoredCalls"):
        if ignore_key in automation:
            operator_automation["ignoreList"] = automation.get(ignore_key) or ""
            break
    if min_signal is not None:
        operator_automation["minSignal"] = max(-40, min(30, min_signal))
    if auto_call_limit is not None:
        operator_automation["autoCallCount"] = max(0, min(99, auto_call_limit))
    if auto_cq_limit is not None:
        operator_automation["autoCQCount"] = max(0, min(99, auto_cq_limit))

    tx_options = {
        "tx_audio_frequency": _coerce_int(_first_present(automation, "txDf", "tx_df", "txAudioHz", "tx_audio_hz")),
        "tx_even_first": _coerce_bool(_first_present(automation, "txEvenFirst", "tx_even_first"), False),
        "watchdog_ft8": watchdog_ft8,
        "watchdog_ft4": watchdog_ft4,
        "watchdog_enabled": _coerce_bool(_first_present(automation, "watchdogEnabled", "watchdog_enabled"), True),
        "auto_cq": auto_cq,
        "auto_call": auto_call,
        "cq_only": cq_only,
        "auto_cq_limit": auto_cq_limit,
        "auto_call_limit": auto_call_limit,
    }
    return {
        "operatorSettings": {"automation": operator_automation},
        "txOptions": tx_options,
        "source": str(req.get("source") or "native-wsjtx"),
    }


def _attach_wsjtx_status_sources(ft8_service: Any, request: Request, *, include_diagnostics: bool = True) -> Dict[str, Any]:
    """Attach local Wavelog/CTY caches to the WSJT automation controller."""
    classifier = getattr(request.app.state, "classifier", None)
    qso_status_store = getattr(classifier, "qso_status_store", None) if classifier else None
    cty_resolver = getattr(request.app.state, "cty_resolver", None)
    controller = getattr(ft8_service, "automation_controller", None)
    if controller and hasattr(controller, "set_status_sources"):
        controller.set_status_sources(
            qso_status_store=qso_status_store,
            cty_resolver=cty_resolver,
        )

    diagnostics: Dict[str, Any] = {
        "qso_status_store": bool(qso_status_store),
        "cty_resolver": bool(cty_resolver),
    }
    if include_diagnostics and qso_status_store and hasattr(qso_status_store, "diagnostics"):
        try:
            diagnostics["qso_status"] = qso_status_store.diagnostics()
        except Exception as exc:
            diagnostics["qso_status_error"] = str(exc)
    return diagnostics


def _local_wsjtx_decode_status(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    call = str(req.get("call") or req.get("callsign") or "").strip().upper().replace("<", "").replace(">", "")
    if not call:
        return {"success": False, "reason": "missing-call"}

    band = str(req.get("band") or "").strip()
    frequency_hz = _frequency_hz_from_payload(req)
    if not band and frequency_hz:
        band = band_from_khz(frequency_hz / 1000.0) or ""
    mode = str(req.get("mode") or "").strip().upper()

    classifier = getattr(request.app.state, "classifier", None)
    store = getattr(classifier, "qso_status_store", None) if classifier else None
    cty_resolver = getattr(request.app.state, "cty_resolver", None)

    country = ""
    dxcc = None
    continent = ""
    cq_zone = ""
    itu_zone = ""
    if cty_resolver:
        try:
            cty_info = _wsjtx_decode_cty_cache.get(call)
            if cty_info is None:
                cty_info = dict(cty_resolver.lookup(call) or {})
                if len(_wsjtx_decode_cty_cache) >= WSJTX_DECODE_CTY_CACHE_MAX:
                    _wsjtx_decode_cty_cache.clear()
                _wsjtx_decode_cty_cache[call] = cty_info
            country = cty_info.get("entity") or cty_info.get("country") or ""
            dxcc = cty_info.get("dxcc")
            continent = cty_info.get("continent") or cty_info.get("cont") or ""
            cq_zone = cty_info.get("cq") or cty_info.get("cq_zone") or ""
            itu_zone = cty_info.get("itu") or cty_info.get("itu_zone") or ""
        except Exception as exc:
            logger.debug("WSJT-Z CTY decode lookup failed for %s: %s", call, exc)

    call_status = "Unknown"
    dxcc_status = "Unknown"
    dxcc_tag = ""
    needed: Dict[str, Any] = {}
    needed_on_band: Dict[str, Any] = {}
    status_sources: list[str] = []

    if store:
        try:
            # This endpoint is called for every decoded line. Do not call the
            # store's public methods here: they may refresh from Wavelog/MySQL
            # when their TTL expires, blocking the WSJT-Z UI at "..." during
            # busy decode bursts. Use only the already-loaded hot sets.
            cache_loaded = getattr(store, "_loaded_at", None) is not None
            if cache_loaded:
                normalise_call = getattr(store, "_normalise_call", lambda value: str(value or "").upper().strip())
                normalise_band = getattr(store, "_normalise_band", lambda value: str(value or "").lower().strip())
                call_value = normalise_call(call)
                band_value = normalise_band(band)
                mode_value = str(mode or "").strip().upper()

                call_worked = call_value in getattr(store, "call_worked", set())
                call_new_band = bool(band_value) and (
                    call_value,
                    band_value,
                ) not in getattr(store, "call_band_worked", set())
                call_new_mode = bool(mode_value) and (
                    call_value,
                    mode_value,
                ) not in getattr(store, "call_mode_worked", set())
                call_bandmode_confirmed = (
                    bool(band_value)
                    and bool(mode_value)
                    and (
                        call_value,
                        band_value,
                        mode_value,
                    ) in getattr(store, "call_bandmode_confirmed", set())
                )
                call_status = classify_call_status(
                    call_worked,
                    call_new_band,
                    call_new_mode,
                    call_bandmode_confirmed,
                )
                needed["call"] = not call_worked
                needed_on_band["call"] = bool(call_new_band)
                needed_on_band["mode"] = bool(call_new_mode)
                status_sources.append("qso-call-hot-cache")

                if dxcc is not None:
                    dxcc_int = int(dxcc)
                    dxcc_worked = dxcc_int in getattr(store, "dxcc_worked", set())
                    dxcc_confirmed = dxcc_int in getattr(store, "dxcc_confirmed", set())
                    dxcc_new_band = bool(band_value) and (
                        dxcc_int,
                        band_value,
                    ) not in getattr(store, "dxcc_band_worked", set())
                    dxcc_new_mode = bool(mode_value) and (
                        dxcc_int,
                        mode_value,
                    ) not in getattr(store, "dxcc_mode_worked", set())
                    dxcc_bandmode_confirmed = (
                        bool(band_value)
                        and bool(mode_value)
                        and (
                            dxcc_int,
                            band_value,
                            mode_value,
                        ) in getattr(store, "dxcc_bandmode_confirmed", set())
                    )
                    display = classify_dxcc_status(
                        dxcc_worked,
                        dxcc_confirmed,
                        dxcc_new_band,
                        dxcc_new_mode,
                        dxcc_bandmode_confirmed,
                    )
                    dxcc_status = display.status
                    dxcc_tag = display.tag or ""
                    needed["dxcc"] = not dxcc_worked
                    needed_on_band["dxcc"] = bool(dxcc_new_band)
                    needed_on_band["dxcc_mode"] = bool(dxcc_new_mode)
                    status_sources.append("qso-dxcc-hot-cache")
            else:
                status_sources.append("qso-cache-not-loaded")
        except Exception as exc:
            logger.debug("WSJT-Z local decode status failed for %s: %s", call, exc, exc_info=True)

    if cty_resolver:
        status_sources.append("cty")

    return {
        "success": True,
        "call": call,
        "band": band,
        "mode": mode,
        "grid": str(req.get("grid") or req.get("gridsquare") or "").strip().upper(),
        "country": country,
        "dxcc": dxcc,
        "continent": continent,
        "cq_zone": str(cq_zone),
        "itu_zone": str(itu_zone),
        "call_status": call_status,
        "dxcc_status": dxcc_status,
        "dxcc_tag": dxcc_tag,
        "needed": needed,
        "needed_on_band": needed_on_band,
        "status_source": ",".join(dict.fromkeys(status_sources)),
        "status_sources": {
            "qso_status_store": bool(store),
            "cty_resolver": bool(cty_resolver),
        },
        "automation_target": None,
        "automation_decision": {},
    }


def register_wsjtx_endpoints(app):
    """
    Register WSJT-X related endpoints with the FastAPI app.
    This function can be called from main.py to register all WSJT-X endpoints.
    """

    @app.post("/api/wsjtx/log-qso")
    async def wsjtx_log_qso(req: Dict[str, Any]):
        """
        Auto-log a QSO from WSJT-X to Wavelog
        Enriches with QRZ data if available
        """
        service = get_wsjtx_service()
        return await service.log_qso(req)

    @app.post("/api/wsjtx/auto-rotate")
    async def wsjtx_auto_rotate(req: Dict[str, Any]):
        """
        Auto-rotate to DX station based on grid square
        Only rotates if ROTOR_AUTO_ENABLED is True
        """
        service = get_wsjtx_service()
        return await service.auto_rotate(req)

    @app.get("/api/wsjtx/config")
    async def get_wsjtx_config():
        """Get WSJT-X configuration"""
        service = get_wsjtx_service()
        return service.get_config()

    @app.get("/api/wsjtx/health")
    async def get_wsjtx_health():
        """Get WSJT-X/WSJT-Z bridge and engine health."""
        service = get_wsjtx_service()
        return service.get_health()

    @app.get("/api/wsjtx/automation/status")
    async def wsjtx_automation_status(request: Request):
        """Return backend Digital automation state for the native OM0RX WSJT-X UI."""
        from services.ft8_service import get_ft8_service

        ft8_service = get_ft8_service()
        status_sources = _attach_wsjtx_status_sources(ft8_service, request)
        return {
            "success": True,
            "automation": ft8_service.automation_controller.status(),
            "stats": ft8_service.get_stats(),
            "status_sources": status_sources,
        }

    @app.post("/api/wsjtx/automation/settings")
    async def wsjtx_automation_settings(req: Dict[str, Any], request: Request):
        """Update backend Digital automation from native OM0RX WSJT-X controls."""
        from services.ft8_service import get_ft8_service

        ft8_service = get_ft8_service()
        status_sources = _attach_wsjtx_status_sources(ft8_service, request)
        policy = _normalise_wsjtx_automation_policy(req)
        ft8_service.automation_controller.apply_operator_settings(policy["operatorSettings"])
        ft8_service.set_tx_options(**policy["txOptions"])
        return {
            "success": True,
            "source": policy["source"],
            "automation": ft8_service.automation_controller.status(),
            "stats": ft8_service.get_stats(),
            "status_sources": status_sources,
        }

    @app.post("/api/wsjtx/automation/tick")
    async def wsjtx_automation_tick(req: Dict[str, Any], request: Request):
        """Let the backend planner arm the next eligible WSJT-X target."""
        from services.ft8_service import get_ft8_service

        ft8_service = get_ft8_service()
        status_sources = _attach_wsjtx_status_sources(ft8_service, request)
        policy = _normalise_wsjtx_automation_policy(req)
        ft8_service.automation_controller.apply_operator_settings(policy["operatorSettings"])
        ft8_service.set_tx_options(**policy["txOptions"])

        automation_payload = req.get("automation") if isinstance(req.get("automation"), dict) else req
        auto_call = bool(policy["txOptions"].get("auto_call"))
        auto_cq = bool(policy["txOptions"].get("auto_cq"))
        force = _coerce_bool(_first_present(automation_payload, "force"), False)
        if not (auto_call or auto_cq or force):
            return {
                "success": True,
                "action": "idle",
                "reason": "automation-disabled",
                "automation": ft8_service.automation_controller.status(),
                "stats": ft8_service.get_stats(),
                "status_sources": status_sources,
            }

        tx_slot_hold = None
        if auto_call and not force and hasattr(ft8_service, "_live_cycle_state") and hasattr(ft8_service, "_max_safe_late_start_seconds"):
            try:
                cycle_duration, cycle_position, cycle_number, slot_is_tx = ft8_service._live_cycle_state()
                mode = str(policy["txOptions"].get("mode") or policy["operatorSettings"].get("current_mode") or getattr(ft8_service, "mode", "FT8") or "FT8")
                max_safe_late = float(ft8_service._max_safe_late_start_seconds(mode))
                if slot_is_tx and float(cycle_position or 0.0) > max(0.0, max_safe_late - 0.05):
                    tx_slot_hold = {
                        "cycle_duration": cycle_duration,
                        "cycle_position": cycle_position,
                        "cycle_number": cycle_number,
                        "slot_is_tx": bool(slot_is_tx),
                        "max_safe_late_start": max_safe_late,
                    }
            except Exception:
                tx_slot_hold = None
        if tx_slot_hold:
            ft8_service.automation_controller._set_decision({
                "decision": "hold",
                "reason": "tx-slot-too-late-for-new-target",
                **tx_slot_hold,
            })
            return {
                "success": True,
                "action": "idle",
                "reason": "tx-slot-too-late-for-new-target",
                "slot": tx_slot_hold,
                "automation": ft8_service.automation_controller.status(),
                "stats": ft8_service.get_stats(),
                "status_sources": status_sources,
            }

        service = get_wsjtx_service()
        pending_return = (
            ft8_service.automation_controller.pending_return_to_origin()
            if hasattr(ft8_service.automation_controller, "pending_return_to_origin")
            else None
        )
        if pending_return and not ft8_service.automation_controller.active_target_key:
            return_mode = str(pending_return.get("mode") or policy["operatorSettings"].get("current_mode") or getattr(ft8_service, "mode", "FT8") or "FT8").upper()
            return_band = str(pending_return.get("band") or "").strip().lower()
            return_frequency = _coerce_int(pending_return.get("dial_frequency")) or _default_wsjtx_dial_frequency_hz(return_band, return_mode)
            if return_frequency:
                wsjtx_target = {
                    "traceId": _wsjtx_trace_id({"call": pending_return.get("call"), "band": return_band, "mode": return_mode}),
                    "call": "",
                    "mode": return_mode,
                    "band": return_band,
                    "dialFrequency": return_frequency,
                    "trPeriod": WSJT_MODE_PERIODS.get(return_mode, 15),
                    "rxDf": _coerce_int(_first_present(automation_payload, "rxDf", "rx_df")) or 1500,
                    "txDf": policy["txOptions"].get("tx_audio_frequency") or 1500,
                    "generateMessages": False,
                    "holdTxFreq": True,
                    "enableTx": False,
                    "listenOnly": True,
                    "returnToOrigin": True,
                    "targetId": pending_return.get("target_key") or "",
                    "watchdogMinutes": ft8_service.automation_controller.settings.hunter_restore_watchdog_minutes,
                }
                if ft8_service.automation_controller.settings.dry_run:
                    ft8_service.automation_controller._set_decision({
                        "decision": "dry-run",
                        "reason": "would-return-wsjtz-to-origin",
                        "call": pending_return.get("call"),
                        "band": return_band,
                        "mode": return_mode,
                    })
                    bridge_result = {
                        "success": True,
                        "dry_run": True,
                        "sent": False,
                        "command": "start_target_qso",
                    }
                else:
                    bridge_result = service.send_bridge_command("start_target_qso", {"target": wsjtx_target})
                    if isinstance(bridge_result, dict) and bridge_result.get("success") is not False:
                        ft8_service.automation_controller.mark_return_command_sent(pending_return.get("target_key"))
                return {
                    "success": True,
                    "action": "returning",
                    "reason": pending_return.get("reason") or "return-to-origin",
                    "target": pending_return,
                    "wsjtx_target": wsjtx_target,
                    "bridge": bridge_result,
                    "automation": ft8_service.automation_controller.status(),
                    "stats": ft8_service.get_stats(),
                    "status_sources": status_sources,
                }

        target = ft8_service.automation_controller.next_target(
            cq_only=bool(policy["txOptions"].get("cq_only")),
            auto_call_start_only=True,
        )
        if not target:
            listen_target = None
            if hasattr(ft8_service.automation_controller, "next_listen_target"):
                listen_target = ft8_service.automation_controller.next_listen_target()
            if listen_target:
                if hasattr(ft8_service.automation_controller, "prepare_command"):
                    ft8_service.automation_controller.prepare_command(listen_target.key)
                origin_band = str(_first_present(automation_payload, "currentBand", "current_band") or "").strip().lower()
                origin_mode = str(_first_present(automation_payload, "currentMode", "current_mode", "mode") or getattr(ft8_service, "mode", "FT8") or "FT8").strip().upper()
                origin_frequency = (
                    _automation_current_dial_frequency_hz(automation_payload)
                    or _default_wsjtx_dial_frequency_hz(origin_band, origin_mode)
                )
                if hasattr(ft8_service.automation_controller, "set_target_origin"):
                    ft8_service.automation_controller.set_target_origin(
                        listen_target.key,
                        band=origin_band,
                        mode=origin_mode,
                        dial_frequency=origin_frequency,
                    )
                target_payload = listen_target.to_dict()
                wsjtx_target = service.build_target_from_automation_target(target_payload)
                wsjtx_target["enableTx"] = False
                wsjtx_target["generateMessages"] = False
                wsjtx_target["listenOnly"] = True
                wsjtx_target["holdTxFreq"] = _coerce_bool(
                    _first_present(automation_payload, "holdTxFreq", "hold_tx_freq"),
                    True,
                )
                wsjtx_target["txDf"] = policy["txOptions"].get("tx_audio_frequency") or wsjtx_target.get("txDf") or 1500
                wsjtx_target["txFirst"] = bool(policy["txOptions"].get("tx_even_first"))
                wsjtx_target.setdefault("targetId", listen_target.target_id)
                wsjtx_target.setdefault("commandId", listen_target.command_id or "")
                wsjtx_target["priorityHunt"] = _dxcc_priority_target(target_payload)
                if _reference_priority_target(target_payload):
                    wsjtx_target["priorityHunt"] = True
                    wsjtx_target["watchdogMinutes"] = ft8_service.automation_controller.settings.hunter_watchdog_minutes
                    wsjtx_target["huntReason"] = listen_target.reason or "reference-hunt"

                if ft8_service.automation_controller.settings.dry_run:
                    ft8_service.automation_controller._set_decision({
                        "decision": "dry-run",
                        "reason": "would-send-spot-listen-qsy",
                        "call": listen_target.call,
                        "band": listen_target.band,
                        "mode": listen_target.mode,
                        "score": listen_target.score,
                        "need_reasons": sorted(listen_target.need_reasons),
                    })
                    bridge_result = {
                        "success": True,
                        "dry_run": True,
                        "sent": False,
                        "command": "start_target_qso",
                    }
                else:
                    bridge_result = service.send_bridge_command("start_target_qso", {"target": wsjtx_target})
                return {
                    "success": True,
                    "action": "listening",
                    "reason": "spot-reference-listen-probe" if _reference_priority_target(target_payload) else "spot-dxcc-listen-probe",
                    "target": target_payload,
                    "wsjtx_target": wsjtx_target,
                    "bridge": bridge_result,
                    "automation": ft8_service.automation_controller.status(),
                    "stats": ft8_service.get_stats(),
                    "status_sources": status_sources,
                }
            return {
                "success": True,
                "action": "idle",
                "reason": "no-eligible-target",
                "automation": ft8_service.automation_controller.status(),
                "stats": ft8_service.get_stats(),
                "status_sources": status_sources,
            }

        target_payload = target.to_dict()
        prepared_command_id = None
        if hasattr(ft8_service.automation_controller, "prepare_command"):
            prepared_command_id = ft8_service.automation_controller.prepare_command(target.key)
            target_payload = target.to_dict()
        final_eligibility = ft8_service.automation_controller._target_eligibility(
            target,
            cq_only=bool(policy["txOptions"].get("cq_only")),
            auto_call_start_only=True,
        )
        if not final_eligibility.get("eligible"):
            ft8_service.automation_controller.release_target(
                target.key,
                reason="final-transmit-eligibility-failed",
            )
            ft8_service.automation_controller._set_decision({
                "decision": "blocked",
                "reason": "final-transmit-eligibility-failed",
                "call": target.call,
                "band": target.band,
                "mode": target.mode,
                "eligibility_reasons": final_eligibility.get("reasons", []),
            })
            return {
                "success": True,
                "action": "idle",
                "reason": "final-transmit-eligibility-failed",
                "eligibility": final_eligibility,
                "automation": ft8_service.automation_controller.status(),
                "stats": ft8_service.get_stats(),
                "status_sources": status_sources,
            }
        wsjtx_target = service.build_target_from_automation_target(target_payload)
        wsjtx_target["enableTx"] = _coerce_bool(
            _first_present(automation_payload, "enableTx", "enable_tx"),
            auto_call,
        )
        wsjtx_target["holdTxFreq"] = _coerce_bool(
            _first_present(automation_payload, "holdTxFreq", "hold_tx_freq"),
            True,
        )
        wsjtx_target["txDf"] = policy["txOptions"].get("tx_audio_frequency") or wsjtx_target.get("txDf") or 1500
        direct_reply_tx_first = _direct_ft8_reply_tx_first(target_payload)
        wsjtx_target["txFirst"] = (
            direct_reply_tx_first
            if direct_reply_tx_first is not None
            else bool(policy["txOptions"].get("tx_even_first"))
        )
        wsjtx_target.setdefault("targetId", target.target_id)
        wsjtx_target.setdefault("commandId", target.command_id or "")
        if _reference_priority_target(target_payload):
            wsjtx_target["priorityHunt"] = True
            wsjtx_target["watchdogMinutes"] = ft8_service.automation_controller.settings.hunter_watchdog_minutes
            wsjtx_target["huntReason"] = target.reason or "reference-hunt"
        elif _dxcc_priority_target(target_payload):
            wsjtx_target["priorityHunt"] = True
            wsjtx_target["watchdogMinutes"] = 20
            wsjtx_target["huntReason"] = target.reason or "dxcc-hunt"

        bridge_failed = False
        if ft8_service.automation_controller.settings.dry_run:
            ft8_service.automation_controller._set_decision({
                "decision": "dry-run",
                "reason": "would-send-start-target-qso",
                "call": target.call,
                "band": target.band,
                "mode": target.mode,
                "score": target.score,
                "need_reasons": sorted(target.need_reasons),
            })
            bridge_result = {
                "success": True,
                "dry_run": True,
                "sent": False,
                "command": "start_target_qso",
            }
        else:
            try:
                bridge_result = service.send_bridge_command("start_target_qso", {"target": wsjtx_target})
            except HTTPException:
                ft8_service.automation_controller.release_target(target.key, reason="bridge-command-failed")
                raise
            except Exception:
                ft8_service.automation_controller.release_target(target.key, reason="bridge-command-failed")
                raise
            if isinstance(bridge_result, dict) and bridge_result.get("success") is False:
                ft8_service.automation_controller.release_target(target.key, reason="bridge-command-failed")
                bridge_failed = True
            else:
                recorded = ft8_service.automation_controller.record_attempt(
                    target.key,
                    command_id=prepared_command_id,
                )
                if recorded:
                    wsjtx_target["commandId"] = recorded.command_id
                    target_payload = recorded.to_dict()
        return {
            "success": True,
            "action": (
                "dry-run"
                if ft8_service.automation_controller.settings.dry_run
                else "bridge-failed"
                if bridge_failed
                else "armed"
            ),
            "target": target_payload,
            "wsjtx_target": wsjtx_target,
            "bridge": bridge_result,
            "automation": ft8_service.automation_controller.status(),
            "stats": ft8_service.get_stats(),
            "status_sources": status_sources,
        }

    @app.post("/api/wsjtx/decode-status")
    async def wsjtx_decode_status(req: Dict[str, Any], request: Request):
        """Return fast local Wavelog/CTY status for one native WSJT-X decode."""
        return _local_wsjtx_decode_status(req, request)

    @app.get("/api/wsjtx/qso-history/{callsign:path}")
    async def wsjtx_qso_history(callsign: str, limit: int = 20):
        """Return previous QSOs from the local Wavelog mirror for the native WSJT-Z popup."""
        call = str(callsign or "").strip().upper()
        if not call:
            raise HTTPException(status_code=400, detail="callsign is required")

        actual_limit = max(1, min(int(limit or 20), 100))
        rows: list[Dict[str, Any]] = []
        try:
            from radio_control.postgres_store import connect as connect_postgres
            from radio_control.postgres_store import should_use_postgres

            if should_use_postgres():
                columns = [
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
                    "country",
                    "gridsquare",
                    "lotw_qsl_sent",
                    "lotw_qsl_rcvd",
                    "eqsl_qsl_rcvd",
                    "qsl_rcvd",
                ]
                with connect_postgres() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            SELECT {", ".join(columns)}
                            FROM qso_records
                            WHERE UPPER(call) = UPPER(%s)
                            ORDER BY COALESCE(qso_datetime, time_on) DESC NULLS LAST
                            LIMIT %s
                            """,
                            (call, actual_limit),
                        )
                        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as exc:
            logger.debug("PostgreSQL QSO history lookup failed for %s: %s", call, exc)

        if not rows:
            from radio_control.wavelog_db import get_wavelog_db

            rows = get_wavelog_db().get_qsos_by_callsign(call, limit=actual_limit)
        qsos: list[Dict[str, Any]] = []
        matrix: Dict[str, Dict[str, Dict[str, bool]]] = {}
        summary: Dict[str, Any] = {}

        def history_time_on(row: Dict[str, Any]) -> str:
            qso_date = str(row.get("qso_date") or "").strip()
            time_on = str(row.get("time_on") or "").strip()
            if qso_date and time_on.startswith(qso_date):
                return time_on
            if qso_date and time_on:
                return f"{qso_date} {time_on}"
            return time_on or qso_date

        for row in rows:
            mode = str(row.get("mode_rx") or row.get("mode") or "").strip().upper()
            band = str(row.get("band") or "").strip().lower()
            lotw_rcvd = str(row.get("lotw_qsl_rcvd") or row.get("lotw_rcvd") or "").strip().upper()
            qso = {
                "time_on": history_time_on(row),
                "callsign": row.get("callsign") or row.get("call") or call,
                "band": band,
                "mode": mode,
                "submode": str(row.get("submode") or "").strip().upper(),
                "rst_sent": str(row.get("rst_sent") or ""),
                "rst_rcvd": str(row.get("rst_rcvd") or ""),
                "lotw_sent": str(row.get("lotw_qsl_sent") or row.get("lotw_sent") or ""),
                "lotw_rcvd": lotw_rcvd,
                "country": row.get("country") or "",
                "gridsquare": row.get("gridsquare") or "",
            }
            qsos.append(qso)
            if not summary:
                summary = {
                    "country": qso["country"],
                    "gridsquare": qso["gridsquare"],
                }
            if mode and band:
                matrix.setdefault(mode, {}).setdefault(band, {"worked": False, "confirmed": False})
                matrix[mode][band]["worked"] = True
                if lotw_rcvd == "Y":
                    matrix[mode][band]["confirmed"] = True

        return {
            "success": True,
            "callsign": call,
            "count": len(qsos),
            "qsos": qsos,
            "summary": summary,
            "matrix": matrix,
        }

    @app.post("/api/wsjtx/launch-wsjtz-engine")
    async def wsjtx_launch_wsjtz_engine(req: Dict[str, Any]):
        """Launch the locally built OM0RX WSJT-Z engine."""
        service = get_wsjtx_service()
        return await asyncio.to_thread(service.launch_wsjtz_engine, req)

    @app.post("/api/wsjtx/launch-patched-engine")
    async def wsjtx_launch_patched_engine(req: Dict[str, Any]):
        """Compatibility alias for the current OM0RX WSJT-Z engine launcher."""
        service = get_wsjtx_service()
        return await asyncio.to_thread(service.launch_wsjtz_engine, req)

    @app.post("/api/wsjtx/launch-wsjtz-preflight")
    async def wsjtx_launch_wsjtz_preflight(req: Dict[str, Any]):
        """Dry-run OM0RX WSJT-Z launch/profile checks without starting the engine."""
        service = get_wsjtx_service()
        req = dict(req or {})
        req["engine"] = "wsjtz"
        return await asyncio.to_thread(service.get_launch_preflight, req)

    @app.post("/api/wsjtx/launch-preflight")
    async def wsjtx_launch_preflight(req: Dict[str, Any]):
        """Compatibility alias for OM0RX WSJT-Z launch/profile preflight."""
        service = get_wsjtx_service()
        req = dict(req or {})
        req["engine"] = "wsjtz"
        return await asyncio.to_thread(service.get_launch_preflight, req)

    @app.get("/api/wsjtx/launch-logs")
    async def wsjtx_launch_logs(rigName: str = "OM0RX-AUTO", lines: int = 120):
        """Read recent stdout/stderr lines from the local patched WSJT launcher logs."""
        service = get_wsjtx_service()
        return service.get_launch_logs(rigName, lines)

    @app.post("/api/wsjtx/command")
    async def wsjtx_command(req: Dict[str, Any]):
        """Send a low-level command to the active WSJT-X/WSJT-Z client."""
        command = str(req.get("command") or "").strip()
        if not command:
            raise HTTPException(status_code=400, detail="Missing command")
        payload = req.get("payload") or {}
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="payload must be an object")
        service = get_wsjtx_service()
        return service.send_bridge_command(command, payload)

    @app.post("/api/wsjtx/halt-tx")
    async def wsjtx_halt_tx(req: Optional[Dict[str, Any]] = Body(default=None)):
        """Stop WSJT-X transmission through the bridge command API."""
        service = get_wsjtx_service()
        req = req or {}
        return service.send_bridge_command("halt_tx", {"autoOnly": bool(req.get("autoOnly", False))})

    @app.post("/api/wsjtx/free-text")
    async def wsjtx_free_text(req: Dict[str, Any]):
        """Set/send WSJT-X free text through the bridge command API."""
        service = get_wsjtx_service()
        return service.send_bridge_command(
            "free_text",
            {"text": str(req.get("text") or ""), "send": bool(req.get("send", True))},
        )

    @app.post("/api/wsjtx/configure")
    async def wsjtx_configure(req: Dict[str, Any]):
        """Configure WSJT-X mode/target fields through the bridge command API."""
        service = get_wsjtx_service()
        return service.send_bridge_command("configure", req)

    @app.post("/api/wsjtx/reply")
    async def wsjtx_reply(req: Dict[str, Any]):
        """Ask stock WSJT-X/WSJT-Z to reply to a prior CQ/QRZ decode."""
        service = get_wsjtx_service()
        return service.send_bridge_command("reply", req)

    @app.post("/api/wsjtx/start-target")
    async def wsjtx_start_target(req: Dict[str, Any]):
        """Send the OM0RX extended target-QSO command to a patched engine."""
        service = get_wsjtx_service()
        target = req.get("target") if isinstance(req.get("target"), dict) else req
        return service.send_bridge_command("start_target_qso", {"target": target})

    @app.post("/api/wsjtx/start-target-from-spot")
    async def wsjtx_start_target_from_spot(req: Dict[str, Any]):
        """Convert a cluster/RBL spot into a prepared patched target-QSO command."""
        service = get_wsjtx_service()
        target = service.build_target_from_spot(req)
        target["enableTx"] = False
        policy = service.assess_target_policy(target, req, action="prepare")
        result = service.send_bridge_command("start_target_qso", {"target": target})
        if isinstance(result, dict):
            result.setdefault("target", target)
            result.setdefault("policy", policy)
        return result

    @app.post("/api/wsjtx/prepare-target-from-spot")
    async def wsjtx_prepare_target_from_spot(req: Dict[str, Any]):
        """Alias for preparing a cluster/RBL spot without arming TX."""
        service = get_wsjtx_service()
        target = service.build_target_from_spot(req)
        target["enableTx"] = False
        policy = service.assess_target_policy(target, req, action="prepare")
        result = service.send_bridge_command("start_target_qso", {"target": target})
        if isinstance(result, dict):
            result.setdefault("target", target)
            result.setdefault("policy", policy)
        return result

    @app.post("/api/wsjtx/arm-target-from-spot")
    async def wsjtx_arm_target_from_spot(req: Dict[str, Any]):
        """Prepare and explicitly arm a cluster/RBL spot in the patched engine."""
        service = get_wsjtx_service()
        target = service.build_target_from_spot(req)
        target["enableTx"] = True
        payload = service.normalize_spot_request(req)
        policy = service.assess_target_policy(target, payload, action="arm")

        if not _coerce_bool(payload.get("confirmArm"), False):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Arm confirmation required",
                    "policy": policy,
                },
            )
        if not policy["eligible"] and not _coerce_bool(payload.get("overrideEligibility"), False):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Target is blocked by WSJT automation policy",
                    "policy": policy,
                },
            )

        result = service.send_bridge_command("start_target_qso", {"target": target})
        if isinstance(result, dict):
            result.setdefault("target", target)
            result.setdefault("policy", policy)
        return result
