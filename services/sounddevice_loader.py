"""Safe, lazy loading for the optional sounddevice dependency.

Some Windows/Python combinations can terminate the interpreter while importing
sounddevice/PortAudio. Probe in a child process before importing it here so a
broken optional audio stack cannot take down the backend at startup.
"""

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
_reason = "sounddevice has not been checked yet"


def _env_flag_enabled(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def get_sounddevice() -> Optional[ModuleType]:
    """Return sounddevice if it can be imported without killing Python."""
    global _checked, _module, _reason

    if _checked:
        return _module

    _checked = True

    if _env_flag_enabled("FT8_DISABLE_SOUNDDEVICE"):
        _reason = "sounddevice disabled by FT8_DISABLE_SOUNDDEVICE"
        logger.info(_reason)
        return None

    try:
        probe = subprocess.run(
            [sys.executable, "-c", "import sounddevice"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        _reason = f"sounddevice import probe failed: {exc}"
        logger.warning("%s; audio devices will be unavailable", _reason)
        return None
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or f"exit code {probe.returncode}").strip()
        _reason = f"sounddevice import probe failed: {detail}"
        logger.warning("%s; audio devices will be unavailable", _reason)
        return None

    try:
        _module = importlib.import_module("sounddevice")
        _reason = "sounddevice available"
        logger.info("sounddevice library available for digital audio")
        return _module
    except BaseException as exc:
        _module = None
        _reason = f"sounddevice import failed: {exc}"
        logger.warning("%s; audio devices will be unavailable", _reason, exc_info=True)
        return None


def is_sounddevice_available() -> bool:
    return get_sounddevice() is not None


def sounddevice_unavailable_reason() -> str:
    if not _checked:
        get_sounddevice()
    return _reason
