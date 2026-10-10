"""Small process-local throttle for repetitive optional-service warnings."""
from __future__ import annotations

import time
from threading import Lock
from typing import Any


_LOCK = Lock()
_LAST: dict[str, float] = {}


def warning(logger: Any, key: str, interval_seconds: float, message: str, *args: Any) -> bool:
    now = time.monotonic()
    with _LOCK:
        last = _LAST.get(key)
        if last is not None and now - last < interval_seconds:
            return False
        _LAST[key] = now
    logger.warning(message, *args)
    return True
