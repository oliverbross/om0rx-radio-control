"""Safe lazy loading for the optional soundcard audio fallback."""

from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys
from types import ModuleType
from typing import Optional

logger = logging.getLogger(__name__)

_checked = False
_module: Optional[ModuleType] = None
_reason = "soundcard has not been checked yet"


def _env_flag_enabled(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def get_soundcard() -> Optional[ModuleType]:
    """Return soundcard if it imports safely."""
    global _checked, _module, _reason

    if _checked:
        return _module

    _checked = True

    if _env_flag_enabled("FT8_DISABLE_SOUNDCARD"):
        _reason = "soundcard disabled by FT8_DISABLE_SOUNDCARD"
        logger.info(_reason)
        return None

    try:
        probe = subprocess.run(
            [sys.executable, "-c", "import soundcard"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        _reason = f"soundcard import probe failed: {exc}"
        logger.warning("%s; fallback audio devices will be unavailable", _reason)
        return None
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or f"exit code {probe.returncode}").strip()
        _reason = f"soundcard import probe failed: {detail}"
        logger.warning("%s; fallback audio devices will be unavailable", _reason)
        return None

    try:
        _module = importlib.import_module("soundcard")
        _reason = "soundcard available"
        logger.info("soundcard library available for digital audio fallback")
        return _module
    except BaseException as exc:
        _module = None
        _reason = f"soundcard import failed: {exc}"
        logger.warning("%s; fallback audio devices will be unavailable", _reason, exc_info=True)
        return None


def is_soundcard_available() -> bool:
    return get_soundcard() is not None


def soundcard_unavailable_reason() -> str:
    if not _checked:
        get_soundcard()
    return _reason
