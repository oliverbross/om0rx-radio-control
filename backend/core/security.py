"""Network trust boundary for the station-control API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import logging
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from radio_control import config


logger = logging.getLogger(__name__)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOOPBACK_NAMES = {"localhost", "testclient", "testserver"}
FRONTEND_PATH = Path(__file__).resolve().parents[2] / "frontend"
INLINE_SCRIPT_PATTERN = re.compile(
    r"<script(?P<attributes>[^>]*)>(?P<body>[\s\S]*?)</script>",
    re.IGNORECASE,
)


def _inline_script_sources(request_path: str) -> list[str]:
    """Return CSP hashes for trusted inline scripts in the requested HTML file."""
    relative_path = request_path.lstrip("/") or "index.html"
    if relative_path in {"radio-control.html", "logging.html", "launcher.html"}:
        relative_path = "index.html"
    if not relative_path.lower().endswith(".html"):
        return []

    candidate = (FRONTEND_PATH / relative_path).resolve()
    try:
        if not candidate.is_relative_to(FRONTEND_PATH.resolve()) or not candidate.is_file():
            return []
        html = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        logger.exception("Unable to calculate CSP hashes for %s", candidate)
        return []

    sources = []
    for match in INLINE_SCRIPT_PATTERN.finditer(html):
        attributes = match.group("attributes")
        body = match.group("body")
        if re.search(r"(?:^|\s)src\s*=", attributes, re.IGNORECASE) or not body:
            continue
        digest = hashlib.sha256(body.encode("utf-8")).digest()
        sources.append(f"'sha256-{base64.b64encode(digest).decode('ascii')}'")
    return sources


def _host_only(value: str | None) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "://" in value:
        return (urlsplit(value).hostname or "").lower()
    if value.startswith("["):
        return value[1:value.find("]")]
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def _is_loopback(value: str | None) -> bool:
    host = _host_only(value)
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _trusted_origins() -> set[str]:
    configured = {
        str(origin).rstrip("/").lower()
        for origin in getattr(config, "CORS_ALLOWED_ORIGINS", [])
        if str(origin).strip()
    }
    port = int(getattr(config, "BACKEND_PORT", 8080))
    configured.update({f"http://localhost:{port}", f"http://127.0.0.1:{port}"})
    return configured


def _origin_allowed(origin: str | None, host: str | None) -> bool:
    if not origin:
        return True
    normalized = origin.rstrip("/").lower()
    if normalized in _trusted_origins():
        return True
    parsed = urlsplit(normalized)
    return bool(parsed.netloc and parsed.netloc.lower() == (host or "").lower())


def _token_matches(value: str | None) -> bool:
    expected = str(getattr(config, "CONTROL_TOKEN", "") or "")
    if not expected or not value:
        return False
    supplied = value.removeprefix("Bearer ").removeprefix("bearer ").strip()
    return hmac.compare_digest(supplied, expected)


def _request_token(headers, query_params=None) -> str:
    return (
        headers.get("authorization", "")
        or headers.get("x-om0rx-control-token", "")
        or (query_params or {}).get("control_token", "")
    )


def authorize_control(headers, client_host: str | None, method: str, query_params=None) -> tuple[bool, str]:
    host = headers.get("host", "")
    origin = headers.get("origin")
    token_ok = _token_matches(_request_token(headers, query_params))
    local_request = _is_loopback(client_host) and _is_loopback(host)
    if not _origin_allowed(origin, host) and not token_ok:
        return False, "Untrusted request origin"
    if local_request:
        return True, ""
    if method.upper() in SAFE_METHODS and not bool(getattr(config, "REMOTE_CONTROL_ENABLED", False)):
        return False, "Remote access is disabled"
    if not bool(getattr(config, "REMOTE_CONTROL_ENABLED", False)):
        return False, "Remote station control is disabled"
    if not token_ok:
        return False, "A valid control token is required"
    return True, ""


class ControlBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        client_host = request.client.host if request.client else ""
        allowed, reason = authorize_control(request.headers, client_host, request.method, request.query_params)
        if not allowed:
            logger.warning("Rejected request method=%s path=%s reason=%s", request.method, request.url.path, reason)
            return JSONResponse(
                status_code=403 if "origin" in reason.lower() or "disabled" in reason.lower() else 401,
                content={"success": False, "code": "CONTROL_ACCESS_DENIED", "message": reason},
            )
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request.state.request_id)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        inline_script_sources = " ".join(_inline_script_sources(request.url.path))
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; "
            "connect-src 'self' ws: wss:; img-src 'self' data: https:; "
            f"script-src 'self' 'unsafe-eval' {inline_script_sources}; "
            "style-src 'self' 'unsafe-inline'",
        )
        return response


async def authorize_websocket(websocket: WebSocket) -> bool:
    client_host = websocket.client.host if websocket.client else ""
    allowed, reason = authorize_control(websocket.headers, client_host, "POST", websocket.query_params)
    if allowed:
        return True
    logger.warning("Rejected WebSocket path=%s reason=%s", websocket.url.path, reason)
    await websocket.close(code=1008, reason="Station control access denied")
    return False
