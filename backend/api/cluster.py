"""
Cluster API Router
Handles DX cluster commands and connection management
"""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

from radio_control import config
from radio_control.cluster_commands import build_rbl_command_plan, merged_rbl_profiles

logger = logging.getLogger(__name__)

router = APIRouter()


class ClusterCommandRequest(BaseModel):
    command: str


class ClusterRblRequest(BaseModel):
    enabled: bool
    modes: Optional[List[str]] = None
    profile: Optional[str] = None


async def _write_cluster_command(cluster_client, command: str) -> tuple[bool, str]:
    """Write one command to the currently active cluster connection."""
    if not cluster_client:
        return False, "Cluster client not initialized"

    if not cluster_client.connected:
        return False, "Cluster not connected"

    command = command.strip()
    if not command:
        return False, "Empty command"

    writer = None
    command_client = cluster_client
    if hasattr(cluster_client, 'active_client') and cluster_client.active_client:
        command_client = cluster_client.active_client
        writer = command_client.writer
    elif hasattr(cluster_client, 'writer'):
        writer = cluster_client.writer

    if not writer:
        return False, "Cluster writer not available"

    try:
        writer.write((command + "\r\n").encode())
        await writer.drain()
        logger.info(f"✅ Sent cluster command: {command}")
        message = f"Command sent: {command}"
        if hasattr(command_client, "record_command_sent"):
            command_client.record_command_sent(command, True, message)
        return True, message
    except Exception as e:
        logger.error(f"Failed to send cluster command: {e}")
        message = f"Send failed: {str(e)}"
        if hasattr(command_client, "record_command_sent"):
            command_client.record_command_sent(command, False, message)
        return False, message


def _cluster_command_telemetry(cluster_client) -> dict:
    """Return recent command/response context from the active cluster client."""
    if not cluster_client:
        return {
            "connected": False,
            "last_line": "",
            "last_response": "",
            "last_line_at": None,
            "recent_lines": [],
            "command_history": [],
        }
    try:
        status = cluster_client.get_status() if hasattr(cluster_client, "get_status") else {}
    except Exception:
        status = {}
    recent_lines = status.get("recent_lines") or []
    last_response = ""
    if recent_lines:
        last_response = recent_lines[0].get("text", "")

    return {
        "connected": bool(status.get("connected", getattr(cluster_client, "connected", False))),
        "last_line": status.get("last_line") or "",
        "last_response": last_response or status.get("last_line") or "",
        "last_line_at": status.get("last_line_at"),
        "recent_lines": recent_lines,
        "command_history": status.get("command_history") or [],
    }


@router.post("/api/cluster/command")
async def send_cluster_command(req: ClusterCommandRequest, request: Request):
    """Send a command to the active DX cluster"""
    try:
        cluster_client = getattr(request.app.state, 'cluster_client', None)
        success, message = await _write_cluster_command(cluster_client, req.command)
        return {"success": success, "message": message}
            
    except Exception as e:
        logger.error(f"Cluster command error: {e}")
        raise HTTPException(status_code=503, detail="Cluster command failed") from e


@router.post("/api/cluster/rbl")
async def set_cluster_rbl(req: ClusterRblRequest, request: Request):
    """Toggle RBL/RBN skimmer spots on the cluster using configurable commands."""
    cluster_client = getattr(request.app.state, 'cluster_client', None)
    configured_profiles = getattr(config, "RBL_COMMAND_PROFILES", {})
    profiles = merged_rbl_profiles(configured_profiles)
    use_legacy_commands = not configured_profiles and not req.profile
    profile, commands = build_rbl_command_plan(
        req.enabled,
        modes=req.modes,
        profile_name=req.profile or getattr(config, "RBL_COMMAND_PROFILE", "dxspider"),
        configured_profiles=configured_profiles,
        legacy_enable_command=getattr(config, "RBL_ENABLE_COMMAND", None) if use_legacy_commands else None,
        legacy_disable_command=getattr(config, "RBL_DISABLE_COMMAND", None) if use_legacy_commands else None,
        legacy_mode_commands=getattr(config, "RBL_MODE_COMMANDS", {}) if use_legacy_commands else {},
    )
    profile_label = profiles.get(profile, {}).get("name", profile)
    if not commands:
        return {
            "success": False,
            "message": "No RBL command configured",
            "commands": [],
            "profile": profile,
            "profile_label": profile_label,
            "telemetry": _cluster_command_telemetry(cluster_client),
        }

    sent_commands = []
    command_results = []
    for command in commands:
        success, message = await _write_cluster_command(cluster_client, command)
        command_results.append({"command": command, "success": success, "message": message})
        if not success:
            return {
                "success": False,
                "message": message,
                "commands": sent_commands + [command],
                "command_results": command_results,
                "profile": profile,
                "profile_label": profile_label,
                "telemetry": _cluster_command_telemetry(cluster_client),
            }
        sent_commands.append(command)

    request.app.state.cluster_rbl_enabled = req.enabled
    await asyncio.sleep(0.2)
    return {
        "success": True,
        "enabled": req.enabled,
        "profile": profile,
        "profile_label": profile_label,
        "message": "RBL enabled" if req.enabled else "RBL disabled",
        "commands": sent_commands,
        "command_results": command_results,
        "telemetry": _cluster_command_telemetry(cluster_client),
    }


@router.get("/api/cluster/rbl/status")
async def get_cluster_rbl_status(request: Request):
    """Return recent RBL command telemetry for operator feedback."""
    cluster_client = getattr(request.app.state, 'cluster_client', None)
    profiles = merged_rbl_profiles(getattr(config, "RBL_COMMAND_PROFILES", {}))
    profile = getattr(config, "RBL_COMMAND_PROFILE", "dxspider")
    profile_data = profiles.get(profile, {})
    return {
        "ok": True,
        "enabled": getattr(request.app.state, "cluster_rbl_enabled", False),
        "profile": profile,
        "profile_label": profile_data.get("name", profile),
        "telemetry": _cluster_command_telemetry(cluster_client),
    }


@router.get("/api/cluster/rbl/profiles")
async def get_cluster_rbl_profiles():
    """Return known RBL command profiles and the configured default."""
    profiles = merged_rbl_profiles(getattr(config, "RBL_COMMAND_PROFILES", {}))
    return {
        "ok": True,
        "default_profile": getattr(config, "RBL_COMMAND_PROFILE", "dxspider"),
        "profiles": [
            {
                "id": key,
                "name": profile.get("name", key),
                "enable": profile.get("enable", ""),
                "disable": profile.get("disable", ""),
                "modes": profile.get("modes", {}),
                "supports_mode_commands": bool(profile.get("supports_mode_commands") or profile.get("modes")),
                "mode_note": profile.get("mode_note", ""),
            }
            for key, profile in sorted(profiles.items())
        ],
    }


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
        raise HTTPException(status_code=503, detail="Cluster reconnect failed") from e
