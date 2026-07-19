"""
WebSocket broadcasting and endpoint management for FlexRadio Web Control
"""

import asyncio
import logging
import json
from typing import List, Dict, Iterable
from fastapi import WebSocket, WebSocketDisconnect

from backend.core.security import authorize_websocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Track WebSocket clients and broadcast from stable snapshots."""

    def __init__(self, legacy_clients: List[WebSocket] | None = None):
        self._clients: set[WebSocket] = set()
        self._legacy_clients = legacy_clients
        self._lock = asyncio.Lock()
        if legacy_clients:
            self._clients.update(legacy_clients)

    def bind_legacy_clients(self, clients: List[WebSocket]) -> None:
        self._legacy_clients = clients
        self._clients = set(clients)

    async def connect(self, websocket: WebSocket) -> int:
        async with self._lock:
            self._clients.add(websocket)
            if self._legacy_clients is not None and websocket not in self._legacy_clients:
                self._legacy_clients.append(websocket)
            return len(self._clients)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
            if self._legacy_clients is not None and websocket in self._legacy_clients:
                self._legacy_clients.remove(websocket)

    async def broadcast(self, message_type: str, data) -> None:
        async with self._lock:
            clients = tuple(self._clients)

        if not clients:
            return

        message = json.dumps({"type": message_type, "data": data})
        async def send(client):
            try:
                await asyncio.wait_for(client.send_text(message), timeout=0.5)
                return None
            except Exception as exc:
                logger.warning("Failed to send %s WebSocket message: %s", message_type, exc)
                return client

        results = await asyncio.gather(*(send(client) for client in clients))
        disconnected = [client for client in results if client is not None]

        if disconnected:
            await self.disconnect_many(disconnected)

    async def disconnect_many(self, clients: Iterable[WebSocket]) -> None:
        async with self._lock:
            for client in clients:
                self._clients.discard(client)
                if self._legacy_clients is not None and client in self._legacy_clients:
                    self._legacy_clients.remove(client)

    async def close_all(self, reason: str) -> None:
        async with self._lock:
            clients = tuple(self._clients)
            self._clients.clear()
            if self._legacy_clients is not None:
                self._legacy_clients.clear()

        async def close(client):
            try:
                await asyncio.wait_for(client.close(code=1001, reason=reason), timeout=0.5)
            except Exception:
                pass
        await asyncio.gather(*(close(client) for client in clients))


# Compatibility list while older code still reads app.state.websocket_clients.
websocket_clients: List[WebSocket] = []
websocket_manager = ConnectionManager(websocket_clients)


async def broadcast_status(data: dict):
    """Broadcast status to all WebSocket clients"""
    await websocket_manager.broadcast("status", data)


async def broadcast_spots(spots: List[Dict]):
    """Broadcast DX spots to all WebSocket clients"""
    await websocket_manager.broadcast("spots", spots)


def register_websocket_endpoint(app, flex=None, dx_spots_cache=None, ws_clients=None):
    """Register the WebSocket endpoint with the FastAPI app"""
    global websocket_clients, websocket_manager

    if ws_clients is not None:
        websocket_clients = ws_clients
        websocket_manager.bind_legacy_clients(ws_clients)

    @app.websocket("/ws/radio")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket for real-time updates"""
        if not await authorize_websocket(websocket):
            return
        await websocket.accept()
        total_clients = await websocket_manager.connect(websocket)
        logger.info(f"✅ WebSocket connected (total: {total_clients})")

        try:
            runtime_context = getattr(app.state, "context", None)
            active_flex = getattr(runtime_context, "flex", None) or flex
            active_spots = getattr(runtime_context, "dx_spots_cache", None) or dx_spots_cache
            # Send initial status
            if active_flex:
                initial_status = dict(getattr(runtime_context, "radio_snapshot", {}) or {})
                await asyncio.wait_for(
                    websocket.send_text(json.dumps({"type": "status", "data": initial_status})),
                    timeout=0.5,
                )

            # Send initial spots
            if active_spots:
                await asyncio.wait_for(
                    websocket.send_text(json.dumps({"type": "spots", "data": active_spots})),
                    timeout=0.5,
                )

            # Keep alive
            while True:
                await websocket.receive_text()
                # Handle ping/pong if needed

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            await websocket_manager.disconnect(websocket)

    return websocket_manager
