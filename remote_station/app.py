"""Authenticated versioned HTTP/WebSocket API for OM0RX-xCat."""

from __future__ import annotations

import asyncio
import hmac
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import AgentConfig, AgentConfigError, load_agent_config, save_public_config
from .runtime import PROTOCOL_VERSION, RemoteCommandError, RemoteStationRuntime

logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class CommandRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    command: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]


def _bearer_token(value: str | None) -> str:
    candidate = str(value or "").strip()
    if candidate.lower().startswith("bearer "):
        return candidate[7:].strip()
    return ""


def create_app(
    config: AgentConfig | None = None,
    *,
    runtime: RemoteStationRuntime | None = None,
    config_path: Path | None = None,
) -> FastAPI:
    resolved_config = config or load_agent_config(config_path)
    station_runtime = runtime or RemoteStationRuntime(resolved_config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if runtime is None:
            await station_runtime.start()
        try:
            yield
        finally:
            if runtime is None:
                await station_runtime.stop()

    app = FastAPI(
        title="OM0RX Remote Station Agent",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.remote_station = station_runtime
    app.state.agent_config = resolved_config

    def config_response(saved: AgentConfig) -> dict[str, Any]:
        active = getattr(station_runtime, "config", resolved_config)
        active_fingerprint = active.fingerprint()
        saved_fingerprint = saved.fingerprint()
        return {
            "success": True,
            # Compatibility field: this is the validated saved profile that
            # the Settings UI edits.  active_config is authoritative until
            # restart when the fingerprints differ.
            "config": saved.public_summary(),
            "saved_config": saved.public_summary(),
            "active_config": active.public_summary(),
            "config_status": {
                "path": str(active.path),
                "active_fingerprint": active_fingerprint,
                "saved_fingerprint": saved_fingerprint,
                "restart_required": saved_fingerprint != active_fingerprint,
            },
        }

    async def authorize(authorization: str | None = Header(default=None)) -> None:
        supplied = _bearer_token(authorization)
        if not supplied or not hmac.compare_digest(supplied, resolved_config.control_token):
            raise HTTPException(status_code=401, detail="A valid agent bearer token is required")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        started = time.monotonic()
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Server-Timing"] = f"app;dur={(time.monotonic() - started) * 1000:.1f}"
        return response

    @app.exception_handler(RemoteCommandError)
    async def command_error(_request: Request, exc: RemoteCommandError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/api/v1/health", dependencies=[Depends(authorize)])
    async def health():
        state = station_runtime.snapshot()
        return {
            "success": True,
            "protocol_version": PROTOCOL_VERSION,
            "radio_connected": bool((state.get("radio") or {}).get("connected")),
            "station_bound": bool((state.get("radio") or {}).get("station_bound")),
            "radio_state_fresh": bool(
                (state.get("radio") or {}).get("known")
                and (state.get("radio") or {}).get("stale") is False
            ),
            "commissioned": bool((state.get("station") or {}).get("commissioned")),
            "last_error": (state.get("agent") or {}).get("last_error"),
        }

    @app.get("/api/v1/config", dependencies=[Depends(authorize)])
    async def public_config():
        return config_response(app.state.agent_config)

    @app.put("/api/v1/config", dependencies=[Depends(authorize)])
    async def update_config(body: ConfigUpdateRequest):
        try:
            saved = save_public_config(app.state.agent_config, body.config)
        except AgentConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        app.state.agent_config = saved
        note_saved = getattr(station_runtime, "note_saved_config", None)
        if callable(note_saved):
            note_saved(saved)
        response = config_response(saved)
        response["restart_required"] = response["config_status"]["restart_required"]
        return response

    @app.get("/api/v1/state", dependencies=[Depends(authorize)])
    async def state():
        return {"success": True, "state": station_runtime.snapshot()}

    @app.post("/api/v1/commands", dependencies=[Depends(authorize)])
    async def command(body: CommandRequest):
        if not REQUEST_ID_PATTERN.fullmatch(body.request_id):
            raise HTTPException(
                status_code=422, detail="request_id contains unsupported characters"
            )
        return await station_runtime.execute(body.request_id, body.command, body.arguments)

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket):
        supplied = _bearer_token(websocket.headers.get("authorization"))
        if not supplied or not hmac.compare_digest(supplied, resolved_config.control_token):
            await websocket.close(code=1008, reason="Agent authentication required")
            return
        await websocket.accept()
        last_revision = -1
        last_heartbeat = time.monotonic()
        try:
            while True:
                revision = station_runtime.revision
                if revision != last_revision:
                    last_revision = revision
                    await websocket.send_json(
                        {"type": "state", "state": station_runtime.snapshot()}
                    )
                    last_heartbeat = time.monotonic()
                elif time.monotonic() - last_heartbeat >= 15:
                    await websocket.send_json({"type": "heartbeat", "revision": revision})
                    last_heartbeat = time.monotonic()
                await asyncio.sleep(0.25)
        except (WebSocketDisconnect, RuntimeError):
            return

    return app
