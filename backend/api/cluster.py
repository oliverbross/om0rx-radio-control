"""
Cluster API Router
Handles DX cluster commands and connection management
"""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()


class ClusterCommandRequest(BaseModel):
    command: str


@router.post("/api/cluster/command")
async def send_cluster_command(req: ClusterCommandRequest, request: Request):
    """Send a command to the active DX cluster"""
    try:
        cluster_client = getattr(request.app.state, 'cluster_client', None)
        
        if not cluster_client:
            return {"success": False, "message": "Cluster client not initialized"}
        
        if not cluster_client.connected:
            return {"success": False, "message": "Cluster not connected"}
        
        command = req.command.strip()
        if not command:
            return {"success": False, "message": "Empty command"}
        
        # Get the active writer (handle both ClusterClient and ClusterManager)
        writer = None
        if hasattr(cluster_client, 'active_client') and cluster_client.active_client:
            # ClusterManager - get writer from active_client
            writer = cluster_client.active_client.writer
        elif hasattr(cluster_client, 'writer'):
            # ClusterClient - get writer directly
            writer = cluster_client.writer
        
        # Send the command to cluster
        if writer:
            try:
                writer.write((command + "\r\n").encode())
                await writer.drain()
                logger.info(f"✅ Sent cluster command: {command}")
                return {"success": True, "message": f"Command sent: {command}"}
            except Exception as e:
                logger.error(f"Failed to send cluster command: {e}")
                return {"success": False, "message": f"Send failed: {str(e)}"}
        else:
            return {"success": False, "message": "Cluster writer not available"}
            
    except Exception as e:
        logger.error(f"Cluster command error: {e}")
        return {"success": False, "message": str(e)}


@router.post("/api/cluster/reconnect")
async def reconnect_cluster(request: Request):
    """Attempt to reconnect to the DX cluster"""
    try:
        cluster_client = getattr(request.app.state, 'cluster_client', None)
        
        if not cluster_client:
            return {"success": False, "message": "Cluster client not initialized"}
        
        # Disconnect if already connected
        if cluster_client.connected:
            cluster_client.disconnect()
            await asyncio.sleep(0.5)
        
        # Attempt to reconnect
        logger.info("🔗 Attempting cluster reconnect...")
        success = await cluster_client.connect()
        
        if success:
            logger.info("✅ Cluster reconnected successfully")
            return {"success": True, "message": "Reconnected to cluster"}
        else:
            logger.error("❌ Cluster reconnect failed")
            return {"success": False, "message": "Reconnection attempt failed"}
            
    except Exception as e:
        logger.error(f"Cluster reconnect error: {e}")
        return {"success": False, "message": str(e)}