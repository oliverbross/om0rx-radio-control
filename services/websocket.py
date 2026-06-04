"""
WebSocket broadcasting and endpoint management for FlexRadio Web Control
"""

import asyncio
import logging
import json
from typing import List, Dict, Iterable
from fastapi import WebSocket, WebSocketDisconnect

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
        disconnected = []

        for client in clients:
            try:
                await asyncio.wait_for(client.send_text(message), timeout=0.5)
            except Exception as e:
                logger.warning("Failed to send %s WebSocket message: %s", message_type, e)
                disconnected.append(client)

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

        for client in clients:
            try:
                await client.close(code=1001, reason=reason)
            except Exception:
                pass


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
        await websocket.accept()
        total_clients = await websocket_manager.connect(websocket)
        logger.info(f"✅ WebSocket connected (total: {total_clients})")

        try:
            # Send initial status
            if flex:
                levels = await asyncio.to_thread(flex.get_current_levels, timeout=0.5)
                initial_status = {
                    "frequency": flex.current_freq or levels.get("freq", 14.074),
                    "mode": flex.current_mode or levels.get("mode", "USB"),
                    "filter_lo": flex.current_filter_lo or levels.get("filter_lo", 100),
                    "filter_hi": flex.current_filter_hi or levels.get("filter_hi", 2900),
                    "volume": levels.get("audio_level", 50),
                    "drive": flex.current_rfpower or levels.get("rfpower", 31),
                    "tune_power": flex.current_tunepower or levels.get("tunepower", 18),
                    "mic_level": flex.current_miclevel or levels.get("miclevel", 32),
                    "mox": bool(flex.current_mox if flex.current_mox is not None else levels.get("mox", False)),
                    "monitor": levels.get("mon", 0),
                    "vox_enabled": flex.current_vox_enable or False,
                    "agc_mode": levels.get("agc_mode", "med"),
                    "nb_enabled": levels.get("nb", False),
                    "nr_enabled": levels.get("nr", False),
                    "anf_enabled": levels.get("anf", False),
                    "apf_enabled": levels.get("apf", False),
                    "rx2_enabled": levels.get("rx2", False),
                    "split_enabled": levels.get("split", False),
                }
                await asyncio.wait_for(
                    websocket.send_text(json.dumps({"type": "status", "data": initial_status})),
                    timeout=0.5,
                )

            # Send initial spots
            if dx_spots_cache:
                await asyncio.wait_for(
                    websocket.send_text(json.dumps({"type": "spots", "data": dx_spots_cache})),
                    timeout=0.5,
                )

            # Keep alive
            while True:
                data = await websocket.receive_text()
                # Handle ping/pong if needed

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            await websocket_manager.disconnect(websocket)

    return websocket_manager
