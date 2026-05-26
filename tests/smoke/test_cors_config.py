#!/usr/bin/env python3
"""Smoke test local-only CORS defaults."""

import _bootstrap  # noqa: F401
import backend.main
from fastapi.testclient import TestClient
from radio_control import config


backend.main.register_all_services()
client = TestClient(backend.main.app)

allowed_origin = f"http://127.0.0.1:{config.BACKEND_PORT}"
blocked_origin = "http://example.com"

allowed_response = client.options(
    "/api/config",
    headers={
        "Origin": allowed_origin,
        "Access-Control-Request-Method": "GET",
    },
)
assert allowed_response.headers.get("access-control-allow-origin") == allowed_origin

blocked_response = client.options(
    "/api/config",
    headers={
        "Origin": blocked_origin,
        "Access-Control-Request-Method": "GET",
    },
)
assert blocked_response.headers.get("access-control-allow-origin") is None

print("✅ CORS allows local UI origins and blocks unconfigured origins")
