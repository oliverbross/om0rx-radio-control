#!/usr/bin/env python3
"""Smoke checks for backend application context wiring."""

import _bootstrap  # noqa: F401

from fastapi import FastAPI

from backend.core import app, context, sync_app_state
from services import websocket as websocket_service


sentinel_client = object()
sentinel_spot = {"callsign": "TEST"}

try:
    context.websocket_clients.append(sentinel_client)
    context.dx_spots_cache.append(sentinel_spot)
    context.wavelog_sync_manager = object()
    sync_app_state(app, context)

    assert app.state.context is context
    assert app.state.websocket_clients is context.websocket_clients
    assert app.state.dx_spots_cache is context.dx_spots_cache
    assert app.state.wavelog_sync_manager is context.wavelog_sync_manager

    temp_app = FastAPI()
    websocket_service.register_websocket_endpoint(
        temp_app,
        context.flex,
        context.dx_spots_cache,
        context.websocket_clients,
    )
    assert websocket_service.websocket_clients is context.websocket_clients

    print("✅ App context is shared through app.state and WebSocket wiring")
finally:
    context.websocket_clients.clear()
    context.dx_spots_cache.clear()
    context.wavelog_sync_manager = None
    sync_app_state(app, context)
