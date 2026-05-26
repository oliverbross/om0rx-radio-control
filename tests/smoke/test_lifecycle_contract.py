#!/usr/bin/env python3
"""Smoke checks for the backend/launcher lifecycle contract."""

import json
import os
import tempfile
from pathlib import Path

import _bootstrap  # noqa: F401
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.server_control import router
from radio_control.lifecycle import (
    RELOAD_ENV_VAR,
    SUPERVISOR_ENV_VAR,
    supervisor_enabled,
    write_lifecycle_request,
)


def restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


original_supervisor = os.environ.get(SUPERVISOR_ENV_VAR)
original_reload = os.environ.get(RELOAD_ENV_VAR)

try:
    with tempfile.TemporaryDirectory() as temp_dir:
        request_path = Path(temp_dir) / "app_lifecycle_request.json"
        payload = write_lifecycle_request("restart", source="smoke", path=request_path)
        saved = json.loads(request_path.read_text(encoding="utf-8"))

        assert payload["action"] == "restart"
        assert saved["action"] == "restart"
        assert saved["source"] == "smoke"
        assert isinstance(saved["pid"], int)
        assert saved["created_at"]

    os.environ.pop(SUPERVISOR_ENV_VAR, None)
    os.environ.pop(RELOAD_ENV_VAR, None)
    assert supervisor_enabled() is False

    app = FastAPI()
    app.state.websocket_clients = []
    app.include_router(router)
    client = TestClient(app)

    restart_response = client.post("/api/restart")
    assert restart_response.status_code == 409
    assert "lifecycle-aware launcher" in restart_response.json()["detail"]

    os.environ[SUPERVISOR_ENV_VAR] = "1"
    os.environ[RELOAD_ENV_VAR] = "1"
    assert supervisor_enabled() is True

    shutdown_response = client.post("/api/shutdown")
    assert shutdown_response.status_code == 409
    assert "reload mode" in shutdown_response.json()["detail"]

    print("✅ Lifecycle contract guards restart/shutdown ownership")
finally:
    restore_env(SUPERVISOR_ENV_VAR, original_supervisor)
    restore_env(RELOAD_ENV_VAR, original_reload)
