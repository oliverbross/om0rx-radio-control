"""Small local WSJT-Z decode enrichment server.

This intentionally stays independent from the main radio-control FastAPI app.
WSJT-Z calls this on every decoded row, so the endpoint must remain memory-only
after startup and must not share the main backend's busy event loop.
"""

from __future__ import annotations

import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radio_control import config  # noqa: E402
from radio_control.cty_resolvers import CtyDatResolver  # noqa: E402
from radio_control.qso_status_store import DuckDBQSOStatusStore  # noqa: E402
from radio_control.spot_classification import classify_call_status, classify_dxcc_status  # noqa: E402
from radio_control.spot_processor import band_from_khz  # noqa: E402


HOST = "127.0.0.1"
PORT = 8765

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("om0rx-wsjtz-enrichment")

store = DuckDBQSOStatusStore()
cty_resolver = CtyDatResolver(
    getattr(config, "CTY_DAT_PATH", None),
    csv_path=getattr(config, "CTY_CSV_PATH", None),
    ignore_suffixes=getattr(config, "CTY_IGNORE_SUFFIXES", []),
)
cty_cache: dict[str, dict[str, Any]] = {}


def _frequency_hz(payload: dict[str, Any]) -> int | None:
    for key in ("frequency_hz", "frequencyHz", "dialFrequency", "dial_frequency"):
        value = payload.get(key)
        try:
            if value is not None and str(value).strip() != "":
                return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _normalise_call(value: Any) -> str:
    return str(value or "").strip().upper().replace("<", "").replace(">", "")


def _decode_status(payload: dict[str, Any]) -> dict[str, Any]:
    call = _normalise_call(payload.get("call") or payload.get("callsign"))
    if not call:
        return {"success": False, "reason": "missing-call"}

    band = str(payload.get("band") or "").strip()
    frequency_hz = _frequency_hz(payload)
    if not band and frequency_hz:
        band = band_from_khz(frequency_hz / 1000.0) or ""
    mode = str(payload.get("mode") or "").strip().upper()

    if getattr(store, "_loaded_at", None) is None:
        store.diagnostics()

    cty_info = cty_cache.get(call)
    if cty_info is None:
        cty_info = dict(cty_resolver.lookup(call) or {})
        if len(cty_cache) >= 4096:
            cty_cache.clear()
        cty_cache[call] = cty_info

    country = cty_info.get("entity") or cty_info.get("country") or ""
    dxcc = cty_info.get("dxcc")
    continent = cty_info.get("continent") or cty_info.get("cont") or ""
    cq_zone = cty_info.get("cq") or cty_info.get("cq_zone") or ""
    itu_zone = cty_info.get("itu") or cty_info.get("itu_zone") or ""

    call_status = "Unknown"
    dxcc_status = "Unknown"
    dxcc_tag = ""
    needed: dict[str, Any] = {}
    needed_on_band: dict[str, Any] = {}
    status_sources: list[str] = ["cty"]

    if getattr(store, "_loaded_at", None) is not None:
        call_value = store._normalise_call(call)
        band_value = store._normalise_band(band)
        mode_value = mode

        call_worked = call_value in store.call_worked
        call_confirmed = call_value in store.call_confirmed
        call_new_band = bool(band_value) and (call_value, band_value) not in store.call_band_worked
        call_new_mode = bool(mode_value) and (call_value, mode_value) not in store.call_mode_worked
        call_bandmode_confirmed = (
            bool(band_value)
            and bool(mode_value)
            and (call_value, band_value, mode_value) in store.call_bandmode_confirmed
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
            dxcc_worked = dxcc_int in store.dxcc_worked
            dxcc_confirmed = dxcc_int in store.dxcc_confirmed
            dxcc_new_band = bool(band_value) and (dxcc_int, band_value) not in store.dxcc_band_worked
            dxcc_new_mode = bool(mode_value) and (dxcc_int, mode_value) not in store.dxcc_mode_worked
            dxcc_bandmode_confirmed = (
                bool(band_value)
                and bool(mode_value)
                and (dxcc_int, band_value, mode_value) in store.dxcc_bandmode_confirmed
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

    return {
        "success": True,
        "call": call,
        "band": band,
        "mode": mode,
        "grid": str(payload.get("grid") or payload.get("gridsquare") or "").strip().upper(),
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
            "qso_status_store": getattr(store, "_loaded_at", None) is not None,
            "cty_resolver": True,
        },
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"success": True, "service": "om0rx-wsjtz-enrichment"})
            return
        self._send_json(404, {"success": False, "reason": "not-found"})

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/wsjtx/decode-status":
            self._send_json(404, {"success": False, "reason": "not-found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8") or "{}")
            self._send_json(200, _decode_status(payload if isinstance(payload, dict) else {}))
        except Exception as exc:
            logger.exception("decode-status failed")
            self._send_json(500, {"success": False, "reason": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)


def main() -> None:
    diagnostics = store.diagnostics()
    logger.info(
        "QSO status cache loaded=%s calls=%s dxcc=%s",
        diagnostics.get("loaded"),
        diagnostics.get("call_worked_count"),
        diagnostics.get("dxcc_worked_count"),
    )
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    logger.info("Listening on http://%s:%s", HOST, PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
