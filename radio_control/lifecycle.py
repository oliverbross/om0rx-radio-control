"""Runtime lifecycle request helpers.

The backend can request process lifecycle actions, but the launcher/supervisor
owns actually stopping and restarting sibling processes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict

from radio_control import config
from radio_control.persistence import atomic_write_json


LIFECYCLE_REQUEST_PATH = config.LOGS_DIR / "app_lifecycle_request.json"
SUPPORTED_ACTIONS = {"shutdown", "restart"}
SUPERVISOR_ENV_VAR = "APP_LIFECYCLE_SUPERVISOR"
RELOAD_ENV_VAR = "APP_UVICORN_RELOAD"


def supervisor_enabled() -> bool:
    """Return true when the backend was started by a lifecycle-aware launcher."""
    return _env_flag(SUPERVISOR_ENV_VAR)


def reload_enabled() -> bool:
    """Return true when Uvicorn reload mode is enabled by the launcher."""
    return _env_flag(RELOAD_ENV_VAR)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def write_lifecycle_request(
    action: str,
    *,
    source: str = "api",
    path: Path = LIFECYCLE_REQUEST_PATH,
) -> Dict[str, Any]:
    """Write a lifecycle request for the local launcher/supervisor to consume."""
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"Unsupported lifecycle action: {action}")

    payload = {
        "action": action,
        "source": source,
        "pid": os.getpid(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    atomic_write_json(path, payload, backup=False)
    return payload
