"""Application runtime context.

This module gives the backend one explicit object for runtime-owned services and
state. Some routers still read legacy `app.state.*` attributes during the
transition, so helpers keep those attributes synchronized from the context.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def default_sync_status() -> Dict[str, Any]:
    return {
        "syncing": False,
        "last_sync": None,
        "total_records": 0,
        "new_records_this_sync": 0,
        "records_updated": 0,
        "next_sync_in": 0,
    }


@dataclass
class AppContext:
    flex: Any = None
    websocket_clients: List[Any] = field(default_factory=list)
    dx_spots_cache: List[Dict[str, Any]] = field(default_factory=list)
    db_connection: Any = None
    cluster_client: Any = None
    cluster_connected: bool = False
    classifier: Any = None
    cty_resolver: Any = None
    wavelog_client: Any = None
    qrz_client: Any = None
    adif_handler: Any = None
    wavelog_sync_manager: Any = None
    rotor: Any = None
    adif_sync_task: Optional[asyncio.Task] = None
    sync_status: Dict[str, Any] = field(default_factory=default_sync_status)


def install_app_context(app: Any, context: AppContext) -> None:
    app.state.context = context
    sync_app_state(app, context)


def get_app_context(request_or_app: Any) -> AppContext:
    app = getattr(request_or_app, "app", request_or_app)
    return app.state.context


def sync_app_state(app: Any, context: AppContext) -> None:
    """Expose context fields through legacy app.state attributes."""
    app.state.flex = context.flex
    app.state.sync_status = context.sync_status
    app.state.dx_spots_cache = context.dx_spots_cache
    app.state.websocket_clients = context.websocket_clients
    app.state.cluster_client = context.cluster_client
    app.state.wavelog_sync_manager = context.wavelog_sync_manager
    app.state.adif_sync_task = context.adif_sync_task
