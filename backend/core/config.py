"""
Configuration management endpoints for FlexRadio Web Control
Extracted from main.py lines 1440-1679
"""

import asyncio
import logging
import time
from datetime import datetime
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
import os
from pathlib import Path
import json
import importlib
import inspect
import re as _re

# Configure logging
logger = logging.getLogger(__name__)

# Pydantic Models
class ConfigUpdate(BaseModel):
    """Configuration update model"""
    config: Dict[str, Any]


def get_config():
    """Get current configuration"""
    try:
        import importlib
        import sys

        # Force reload by removing from cache and deleting bytecode
        if 'config' in sys.modules:
            del sys.modules['config']

        # Delete bytecode cache to ensure fresh load
        pycache_dir = Path(__file__).parent.parent.parent / '__pycache__'
        if pycache_dir.exists():
            for pyc in pycache_dir.glob('config*.pyc'):
                try:
                    pyc.unlink()
                except:
                    pass

        # Re-import fresh module
        from radio_control import config as cfg
        importlib.reload(cfg)

        config_data = {
            "DB_HOST": cfg.DB_HOST,
            "DB_PORT": cfg.DB_PORT,
            "DB_NAME": cfg.DB_NAME,
            "DB_USER": cfg.DB_USER,
            "DB_PASS": cfg.DB_PASS,
            "MY_STATION": cfg.MY_STATION,
            "CLUSTER_HOST": cfg.CLUSTER_HOST,
            "CLUSTER_PORT": cfg.CLUSTER_PORT,
            "CLUSTER_USER": cfg.CLUSTER_USER,
            "CLUSTER_PASS": cfg.CLUSTER_PASS,
            "SDR_UDP_HOST": cfg.SDR_UDP_HOST,
            "SDR_UDP_PORT": cfg.SDR_UDP_PORT,
            "UDP_ENABLED_DEFAULT": cfg.UDP_ENABLED_DEFAULT,
            "FLEX_TCP_HOST": cfg.FLEX_TCP_HOST,
            "FLEX_TCP_PORT": cfg.FLEX_TCP_PORT,
            "FLEX_ENABLED_DEFAULT": cfg.FLEX_ENABLED_DEFAULT,
            # Rotor Configuration
            "ROTOR_ENABLED": getattr(cfg, 'ROTOR_ENABLED', False),
            "ROTOR_TYPE": getattr(cfg, 'ROTOR_TYPE', 'Microham ARCO'),
            "ROTOR_HOST": getattr(cfg, 'ROTOR_HOST', '192.168.0.198'),
            "ROTOR_PORT": getattr(cfg, 'ROTOR_PORT', 4001),
            "ROTOR_PROTOCOL": getattr(cfg, 'ROTOR_PROTOCOL', 'DCU-1'),
            "ROTOR_TIMEOUT_SEC": getattr(cfg, 'ROTOR_TIMEOUT_SEC', 2.5),
            "ROTOR_HOME_GRID": getattr(cfg, 'ROTOR_HOME_GRID', ''),
            "ROTOR_HOME_LAT": getattr(cfg, 'ROTOR_HOME_LAT', 0),
            "ROTOR_HOME_LON": getattr(cfg, 'ROTOR_HOME_LON', 0),
            "ROTOR_BANDS": getattr(cfg, 'ROTOR_BANDS', {}),
            "ROTOR_AUTO_ENABLED": getattr(cfg, 'ROTOR_AUTO_ENABLED', False),
            "ROTOR_AUTO_DELAY_SEC": getattr(cfg, 'ROTOR_AUTO_DELAY_SEC', 2),
            # Country/CTY Configuration
            "CTY_CSV_PATH": cfg.CTY_CSV_PATH,
            "CTY_DAT_PATH": getattr(cfg, 'CTY_DAT_PATH', ''),
            "LOG_LEVEL": cfg.LOG_LEVEL,
            "COLORS": getattr(cfg, 'COLORS', {}),
            # External Services
            "WAVELOG_ENABLED": getattr(cfg, 'WAVELOG_ENABLED', True),
            "WAVELOG_API_URL": getattr(cfg, 'WAVELOG_API_URL', ''),
            "WAVELOG_API_KEY": getattr(cfg, 'WAVELOG_API_KEY', ''),
            "WAVELOG_STATION_ID": getattr(cfg, 'WAVELOG_STATION_ID', '1'),
            "QRZ_ENABLED": getattr(cfg, 'QRZ_ENABLED', True),
            "QRZ_USERNAME": getattr(cfg, 'QRZ_USERNAME', ''),
            "QRZ_PASSWORD": getattr(cfg, 'QRZ_PASSWORD', ''),
            "CLUSTER_ENABLED": getattr(cfg, 'CLUSTER_ENABLED', False),
            "ADIF_LOG_PATH": getattr(cfg, 'ADIF_LOG_PATH', ''),
            # WSJT-X Configuration
            "WSJTX_ENABLED": getattr(cfg, 'WSJTX_ENABLED', True),
            "WSJTX_UDP_PORT": getattr(cfg, 'WSJTX_UDP_PORT', 2237),
            "WSJTX_UDP_MULTICAST": getattr(cfg, 'WSJTX_UDP_MULTICAST', '224.0.0.1'),
            "WSJTX_WS_PORT": getattr(cfg, 'WSJTX_WS_PORT', 8091),
            "WSJTX_AUTO_LOG": getattr(cfg, 'WSJTX_AUTO_LOG', True),
            "WSJTX_AUTO_ROTATE": getattr(cfg, 'WSJTX_AUTO_ROTATE', True),
            # WinKeyer Configuration
            "WINKEYER_ENABLED": getattr(cfg, 'WINKEYER_ENABLED', False),
            "WINKEYER_PORT": getattr(cfg, 'WINKEYER_PORT', 'COM3'),
            "WINKEYER_BAUDRATE": getattr(cfg, 'WINKEYER_BAUDRATE', 1200),
            "WINKEYER_DEFAULT_WPM": getattr(cfg, 'WINKEYER_DEFAULT_WPM', 20),
            "WINKEYER_MEMORIES": getattr(cfg, 'WINKEYER_MEMORIES', {}),
            # Multi-Cluster Configuration
            "CLUSTERS": getattr(cfg, 'CLUSTERS', []),
        }

        return {"success": True, "config": config_data}
    except Exception as e:
        logger.error(f"Get config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def update_config(config_update: ConfigUpdate):
    """Update configuration"""
    try:
        import re as _re
        import importlib
        import inspect
        import sys

        # Get config file path
        config_path = os.path.abspath(inspect.getsourcefile(sys.modules.get('config')))
        logger.info(f"📝 Config path: {config_path}")
        logger.info(f"📝 Saving config keys: {list(config_update.config.keys())}")

        # Read current config file
        with open(config_path, 'r', encoding='utf-8') as f:
            txt = f.read()

        original_txt = txt

        def _format_py_value(v):
            if isinstance(v, str):
                s = v.replace("\\", "\\\\").replace('"', '\\"')
                return f'"{s}"'
            if isinstance(v, bool):
                return "True" if v else "False"
            if isinstance(v, (int, float)):
                return str(v)
            if isinstance(v, dict):
                items = []
                for k, val in v.items():
                    if isinstance(val, str):
                        # Properly escape string values in dict
                        escaped_val = val.replace("\\", "\\\\").replace('"', '\\"')
                        items.append(f'"{k}": "{escaped_val}"')
                    elif isinstance(val, bool):
                        items.append(f'"{k}": {"True" if val else "False"}')
                    else:
                        items.append(f'"{k}": {val}')
                return "{" + ", ".join(items) + "}"
            if isinstance(v, (list, tuple)):
                # Handle lists and tuples (e.g., CLUSTERS array)
                formatted_items = []
                for item in v:
                    if isinstance(item, dict):
                        # Format each dict in the list
                        dict_items = []
                        for k, val in item.items():
                            if isinstance(val, str):
                                escaped_val = val.replace("\\", "\\\\").replace('"', '\\"')
                                dict_items.append(f'"{k}": "{escaped_val}"')
                            elif isinstance(val, bool):
                                dict_items.append(f'"{k}": {"True" if val else "False"}')
                            else:
                                dict_items.append(f'"{k}": {val}')
                        formatted_items.append("{" + ", ".join(dict_items) + "}")
                    else:
                        formatted_items.append(_format_py_value(item))
                return "[" + ", ".join(formatted_items) + "]"
            return repr(v)

        def _replace_block(text, key, new_value_src):
            start_re = _re.compile(rf"^[ \t]*{_re.escape(key)}\s*=", _re.M)
            m = start_re.search(text)
            rep = f"{key} = {new_value_src}"
            if not m:
                logger.warning(f"⚠️  Key '{key}' not found in config, appending")
                if not text.endswith("\n"):
                    text += "\n"
                return text + rep + "\n"
            end_re = _re.compile(r"^([A-Z_][A-Z0-9_]*\s*=)", _re.M)
            m_end = end_re.search(text, pos=m.end())
            if m_end:
                logger.info(f"✏️  Replacing {key}: found next key at {m_end.group()}")
                return text[:m.start()] + rep + "\n" + text[m_end.start():]
            else:
                logger.info(f"✏️  Replacing {key}: at end of file")
                return text[:m.start()] + rep + "\n"

        # Update each config value
        for key, value in config_update.config.items():
            logger.info(f"   Setting {key} = {_format_py_value(value)}")
            txt = _replace_block(txt, key, _format_py_value(value))

        # Check if text changed
        if txt == original_txt:
            logger.warning("⚠️  Config text unchanged after replacements!")
        else:
            logger.info(f"✅ Config text changed, {len(txt)} bytes")

        # Write updated config
        logger.info(f"💾 Writing to {config_path}")
        with open(config_path, 'w', encoding='utf-8') as f:
            bytes_written = f.write(txt)
            logger.info(f"💾 Wrote {bytes_written} bytes")

        # Verify file was written
        with open(config_path, 'r', encoding='utf-8') as f:
            verify_txt = f.read()
            if verify_txt == txt:
                logger.info(f"✅ File verified: {len(verify_txt)} bytes match")
            else:
                logger.error(f"❌ File verification failed! Written: {len(txt)}, Read: {len(verify_txt)}")

        # Log cluster configuration if updated
        if "CLUSTERS" in config_update.config:
            clusters = config_update.config.get("CLUSTERS", [])
            logger.info(f"📡 Cluster configuration updated: {len(clusters)} cluster(s)")
            for idx, cluster in enumerate(clusters):
                enabled_status = "✅ ENABLED" if cluster.get("enabled", False) else "❌ DISABLED"
                host_port = f"{cluster.get('host', '?')}:{cluster.get('port', '?')}"
                logger.info(f"   Cluster {idx+1} ({cluster.get('name', 'Unknown')}): {host_port} - {enabled_status}")

        # Clear Python bytecode cache to force fresh import
        logger.info(f"🔄 Clearing Python bytecode cache")
        pycache_dir = Path(__file__).parent.parent.parent / '__pycache__'
        if pycache_dir.exists():
            for pyc in pycache_dir.glob('config*.pyc'):
                try:
                    pyc.unlink()
                    logger.info(f"   Deleted {pyc.name}")
                except Exception as e:
                    logger.warning(f"   Could not delete {pyc.name}: {e}")

        # Remove from module cache
        if 'config' in sys.modules:
            del sys.modules['config']

        # Re-import and reload config module (updates in-memory values)
        logger.info(f"🔄 Reloading config module")
        from radio_control import config as cfg_fresh
        importlib.reload(cfg_fresh)
        logger.info(f"✅ Config module reloaded")

        return {"success": True, "message": "Configuration updated successfully!"}

    except Exception as e:
        import traceback
        error_msg = str(e)
        logger.error(f"❌ Update config error: {e}")
        logger.error(traceback.format_exc())
        return {"success": False, "message": f"Configuration update failed: {error_msg}"}


def register_config_endpoints(app: FastAPI):
    """Register configuration endpoints with the FastAPI app"""

    @app.get("/api/config")
    async def api_get_config():
        """Get current configuration"""
        return get_config()

    @app.post("/api/config")
    async def api_update_config(req: ConfigUpdate):
        """Update configuration"""
        return update_config(req)
    
    @app.get("/api/config/ft8")
    async def api_get_ft8_config():
        """Get FT8 configuration - delegates to FT8 API"""
        # Import here to avoid circular imports
        from backend.api.ft8 import get_ft8_config
        return await get_ft8_config()
    
    @app.post("/api/config/ft8")
    async def api_update_ft8_config(new_config: dict):
        """Update FT8 configuration - delegates to FT8 API"""
        # Import here to avoid circular imports
        from backend.api.ft8 import update_ft8_config
        return await update_ft8_config(new_config)
