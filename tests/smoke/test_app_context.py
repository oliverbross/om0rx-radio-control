#!/usr/bin/env python3
"""Smoke checks for backend application context wiring."""

import asyncio

import _bootstrap  # noqa: F401

from fastapi import FastAPI

from backend.core import app, context, sync_app_state
from services import websocket as websocket_service


sentinel_client = object()
sentinel_spot = {"callsign": "TEST"}


class FakeWebSocket:
    def __init__(self, fail_send=False):
        self.fail_send = fail_send
        self.sent = []
        self.closed = False

    async def send_text(self, message):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append(message)

    async def close(self, code=1000, reason=""):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


async def exercise_websocket_manager():
    legacy_clients = []
    manager = websocket_service.ConnectionManager(legacy_clients)
    live_client = FakeWebSocket()
    stale_client = FakeWebSocket(fail_send=True)

    assert await manager.connect(live_client) == 1
    assert await manager.connect(stale_client) == 2
    assert legacy_clients == [live_client, stale_client]

    original_logger_disabled = websocket_service.logger.disabled
    websocket_service.logger.disabled = True
    try:
        await manager.broadcast("status", {"frequency": 14.074})
    finally:
        websocket_service.logger.disabled = original_logger_disabled
    assert live_client.sent
    assert stale_client not in legacy_clients

    await manager.close_all("smoke")
    assert live_client.closed
    assert legacy_clients == []


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
    context.websocket_manager = websocket_service.register_websocket_endpoint(
        temp_app,
        context.flex,
        context.dx_spots_cache,
        context.websocket_clients,
    )
    sync_app_state(app, context)
    assert websocket_service.websocket_clients is context.websocket_clients
    assert websocket_service.websocket_manager is context.websocket_manager

    asyncio.run(exercise_websocket_manager())

    print("✅ App context is shared through app.state and WebSocket wiring")
finally:
    context.websocket_clients.clear()
    context.dx_spots_cache.clear()
    websocket_service.websocket_manager.bind_legacy_clients([])
    context.websocket_manager = None
    context.wavelog_sync_manager = None
    sync_app_state(app, context)
