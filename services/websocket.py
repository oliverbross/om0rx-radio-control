"""
WebSocket broadcasting and endpoint management for FlexRadio Web Control
"""

import asyncio
import logging
import json
from typing import List, Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Global WebSocket clients list
websocket_clients: List[WebSocket] = []


async def broadcast_status(data: dict):
    """Broadcast status to all WebSocket clients"""
    if not websocket_clients:
        return

    message = json.dumps({"type": "status", "data": data})
    disconnected = []

    for client in websocket_clients:
        try:
            await client.send_text(message)
        except Exception as e:
            logger.warning(f"Failed to send to WebSocket: {e}")
            disconnected.append(client)

    for client in disconnected:
        websocket_clients.remove(client)


async def broadcast_spots(spots: List[Dict]):
    """Broadcast DX spots to all WebSocket clients"""
    if not websocket_clients:
        return

    message = json.dumps({"type": "spots", "data": spots})
    disconnected = []

    for client in websocket_clients:
        try:
            await client.send_text(message)
        except Exception as e:
            logger.warning(f"Failed to broadcast spots: {e}")
            disconnected.append(client)

    for client in disconnected:
        websocket_clients.remove(client)


def register_websocket_endpoint(app, flex=None, dx_spots_cache=None):
    """Register the WebSocket endpoint with the FastAPI app"""

    @app.websocket("/ws/radio")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket for real-time updates"""
        await websocket.accept()
        websocket_clients.append(websocket)
        logger.info(f"✅ WebSocket connected (total: {len(websocket_clients)})")

        try:
            # Send initial status
            if flex:
                levels = flex.get_current_levels(timeout=0.5)
                initial_status = {
                    "frequency": flex.current_freq or levels.get("freq", 14.074),
                    "mode": flex.current_mode or levels.get("mode", "USB"),
                    "filter_lo": flex.current_filter_lo or levels.get("filter_lo", 100),
                    "filter_hi": flex.current_filter_hi or levels.get("filter_hi", 2900),
                    "volume": levels.get("audio_level", 50),
                    "drive": flex.current_rfpower or levels.get("rfpower", 31),
                    "tune_power": flex.current_tunepower or levels.get("tunepower", 18),
                    "mic_level": flex.current_miclevel or levels.get("miclevel", 32),
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
                await websocket.send_text(json.dumps({"type": "status", "data": initial_status}))

            # Send initial spots
            if dx_spots_cache:
                await websocket.send_text(json.dumps({"type": "spots", "data": dx_spots_cache}))

            # Keep alive
            while True:
                data = await websocket.receive_text()
                # Handle ping/pong if needed

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if websocket in websocket_clients:
                websocket_clients.remove(websocket)