"""
WSJT-X Service Module

Extracted WSJT-X integration from main.py for modularization.
Includes auto-logging to Wavelog, QRZ data enrichment, and auto-rotation features.
"""

import logging
import json
import platform
import os
import socket
import subprocess
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from typing import Optional, Dict, Any
from fastapi import HTTPException

# Import required modules
from radio_control.spot_processor import band_from_khz, infer_mode
from radio_control.qso_outbox import get_qso_outbox
from radio_control import config
logger = logging.getLogger(__name__)


WSJT_TARGET_MODES = {"FT8", "FT4", "FT2"}
WSJT_MODE_PERIODS = {
    "FT8": 15,
    "FT4": 7,
    "FT2": 4,
}
WSJT_CLIENT_FRESH_MS = 30_000
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATCHED_ENGINE_BUILD_ROOT = PROJECT_ROOT / "data" / "build" / "wsjtx-improved-om0rx" / "build-msys"
PATCHED_ENGINE_RUN_SCRIPT = PROJECT_ROOT / "scripts" / "wsjtx" / "run_om0rx_wsjtx.ps1"
PATCHED_ENGINE_MSYS_ROOT = Path(os.environ.get("WSJTX_MSYS_ROOT", r"C:\JTSDK64-Tools\tools\msys64"))


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


def _patched_engine_log_paths(rig_name: str) -> dict[str, Path]:
    log_root = PROJECT_ROOT / "logs"
    log_safe_name = "".join(
        ch if ch.isalnum() or ch in "._-" else "-"
        for ch in f"wsjt-x-{rig_name}"
    ).strip("-").lower()
    if not log_safe_name:
        log_safe_name = "wsjt-x-om0rx-auto"
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


def _patched_engine_process_ids(rig_name: str, test_mode: bool = False) -> list[int]:
    """Return running wsjtx.exe PIDs for this OM0RX rig profile."""
    if platform.system().lower() != "windows":
        return []
    safe_rig = rig_name.replace("'", "''")
    test_filter = " -and $_.CommandLine -like '*--test-mode*'" if test_mode else ""
    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"Get-CimInstance Win32_Process -Filter \"Name='wsjtx.exe'\" | "
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

    def set_dependencies(self, wavelog_client, qrz_client, rotor_service, cty_resolver=None, adif_handler=None):
        """Set external dependencies"""
        self.wavelog_client = wavelog_client
        self.qrz_client = qrz_client
        self.rotor_service = rotor_service
        self.cty_resolver = cty_resolver
        self.adif_handler = adif_handler

    async def log_qso(self, req: Dict[str, Any]):
        """
        Auto-log a QSO from WSJT-X to Wavelog
        Enriches with QRZ data if available
        """
        if not self.wavelog_client:
            raise HTTPException(status_code=503, detail="Wavelog client not initialized")

        try:
            call = req['call'].strip().upper()

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
            band = band_from_khz(req.get('frequency_hz') / 1000) if req.get('frequency_hz') else "Unknown"
            
            qso_data = {
                # Core fields (required)
                "callsign": call,
                "frequency": req.get('frequency_hz') / 1_000_000 if req.get('frequency_hz') else None,
                "mode": req['mode'].upper(),
                "band": band,  # Include band for ADIF saving
                
                # RST values: keep as-is or use defaults (wavelog_api.py handles conversion)
                "rst_sent": req.get('rst_sent'),
                "rst_received": req.get('rst_received'),
                
                # Date/Time fields
                "date": None,  # Will use current date in wavelog_api
                "time_off": None,  # Will use current time in wavelog_api
                "date_time": None,  # Alternative date_time field
                
                # Station info (enriched from QRZ/CTY)
                "name": qrz_data.get("fname", ""),
                "qth": qrz_data.get("state", qrz_data.get("country", "")),
                "gridsquare": req.get('grid') or qrz_data.get("grid", ""),
                "notes": req.get('comments') or f"Auto-logged from WSJT-X ({req['mode']})",
                
                # Activation programs
                "pota": None,
                "sota": None,
                "iota": None,
                "wwff": None,
                
                # Location info
                "continent": cty_data.get("continent", qrz_data.get("continent", "")),  # Prefer CTY continent if available
                "cq_zone": qrz_data.get("cqzone"),
                "itu_zone": qrz_data.get("ituzone"),
                "region": None,
                "country": qrz_data.get("country", ""),
                "state": qrz_data.get("state", ""),
                "us_county": None,
                
                # Radio/Antenna
                "tx_pwr": None,
                "ant": None,
                
                # QSL info
                "qsl_rcvd": None,
                "qsl_sent": None,
                "lotw_member": qrz_data.get("lotw", False),
                "qsl_manager": None,
                
                # Advanced fields
                "email": qrz_data.get("email", ""),
                "prop_mode": None,
                "ant_path": None,
                "sat_name": None,
                "sat_mode": None,
                "freq_rx": None,
                "mode_rx": None,
            }

            logger.info(f"📝 Auto-logging QSO: {call} on {band} {req['mode']}")
            logger.debug(f"   QSO Data: name={qso_data['name']}, country={qso_data['country']}, grid={qso_data['gridsquare']}")

            # Log to Wavelog
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
                
                logger.info(f"✅ QSO logged successfully to Wavelog: {call} (ID: {qso_id if qso_id else 'unknown'}), ADIF: {adif_saved}")
                
                # Return enriched QSO data to frontend for display in confirmation modal
                return {
                    "success": True, 
                    "qso_id": qso_id, 
                    "message": result.get("message", "QSO logged successfully"),
                    "adif_saved": adif_saved,
                    "qso_data": {
                        "callsign": call,
                        "frequency": req.get('frequency_hz') / 1_000_000 if req.get('frequency_hz') else None,
                        "mode": req['mode'].upper(),
                        "gridsquare": qso_data['gridsquare'],
                        "rst_sent": req.get('rst_sent'),
                        "rst_received": req.get('rst_received'),
                        "name": qso_data['name'],  # From QRZ enrichment
                        "country": qso_data['country'],  # From QRZ enrichment
                        "state": qso_data['state'],
                        "continent": qso_data['continent']
                    }
                }
            else:
                duplicate_text = " ".join(
                    str((result or {}).get(key) or "")
                    for key in ("message", "error")
                ).lower()
                if "duplicate" in duplicate_text:
                    logger.info("✅ WSJT-X QSO already exists in Wavelog; treating duplicate as resolved: %s", call)
                    return {
                        "success": True,
                        "duplicate": True,
                        "message": (result or {}).get("message") or "QSO already exists in Wavelog",
                        "adif_saved": adif_saved,
                        "qso_data": {
                            "callsign": call,
                            "frequency": req.get('frequency_hz') / 1_000_000 if req.get('frequency_hz') else None,
                            "mode": req['mode'].upper(),
                            "gridsquare": qso_data['gridsquare'],
                            "rst_sent": req.get('rst_sent'),
                            "rst_received": req.get('rst_received'),
                            "name": qso_data['name'],
                            "country": qso_data['country'],
                            "state": qso_data['state'],
                            "continent": qso_data['continent'],
                        },
                    }
                logger.error(f"❌ Failed to log QSO to Wavelog: {result}")
                outbox_queued = get_qso_outbox().enqueue(
                    qso_data,
                    reason=(result or {}).get("message", "WSJT-X Wavelog upload failed"),
                )
                # If Wavelog fails but ADIF saved, still return partial success
                if adif_saved or outbox_queued:
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
                        "message": (
                            "Wavelog logging failed but QSO saved locally: "
                            f"{(result or {}).get('message', str(result))}"
                        )
                    }
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to log QSO: {(result or {}).get('message', str(result))}",
                )

        except HTTPException:
            raise
        except Exception as e:
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
        rig_name = str(req.get("rigName") or "OM0RX-AUTO").strip() or "OM0RX-AUTO"
        config_name = str(req.get("configName") or "OM0RX-AUTO").strip() or "OM0RX-AUTO"
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
            launcher_result = self.launch_patched_engine({
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
                f"Patched WSJT engine can be launched for profile {rig_name}/{config_name}"
                if launcher_ok else
                f"Patched WSJT engine dry-run failed: {launcher_error or launcher_result.get('detail') or 'unknown error'}"
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
        request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
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
            "dialFrequency": dial_frequency,
            "trPeriod": _coerce_int(req.get("trPeriod")) or WSJT_MODE_PERIODS[mode],
            "rxDf": _coerce_int(_first_present(req, "rxDf", "rx_df", "rxAudio")) or 1500,
            "txDf": _coerce_int(_first_present(req, "txDf", "tx_df", "txAudio")) or 1500,
            "generateMessages": _coerce_bool(req.get("generateMessages"), True),
            "holdTxFreq": _coerce_bool(req.get("holdTxFreq"), True),
            "enableTx": _coerce_bool(req.get("enableTx"), False),
        }

        grid = str(_first_present(req, "grid", "dxGrid", "gridsquare") or "").strip().upper()
        if grid:
            target["grid"] = grid

        for source_key, target_key in (
            ("frequencyTolerance", "frequencyTolerance"),
            ("submode", "submode"),
            ("txMessageNumber", "txMessageNumber"),
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
        request = urllib.request.Request(
            url,
            data=request_payload,
            headers={"Content-Type": "application/json"},
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

    @app.post("/api/wsjtx/launch-patched-engine")
    async def wsjtx_launch_patched_engine(req: Dict[str, Any]):
        """Launch the locally built OM0RX-patched WSJT-X engine."""
        service = get_wsjtx_service()
        return service.launch_patched_engine(req)

    @app.post("/api/wsjtx/launch-preflight")
    async def wsjtx_launch_preflight(req: Dict[str, Any]):
        """Dry-run patched WSJT launch/profile checks without starting the engine."""
        service = get_wsjtx_service()
        return service.get_launch_preflight(req)

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
    async def wsjtx_halt_tx(req: Dict[str, Any]):
        """Stop WSJT-X transmission through the bridge command API."""
        service = get_wsjtx_service()
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
