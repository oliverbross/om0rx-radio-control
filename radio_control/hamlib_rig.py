"""Small Hamlib rigctl adapter for DIGITAL CAT/PTT.

The app's existing Flex controller talks directly to the SmartSDR TCP API.  For
DIGITAL modes we also support Hamlib so the transmit path can match WSJT-X more
closely and can later work with non-Flex radios.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


logger = logging.getLogger(__name__)


DEFAULT_WINDOWS_RIGCTL = Path(r"C:\JTSDK64-Tools\tools\msys64\mingw64\bin\rigctl.exe")


def resolve_rigctl_path(configured_path: str | None = None) -> Optional[str]:
    """Return a rigctl executable path when Hamlib is available."""
    candidates = [
        configured_path,
        os.environ.get("HAMLIB_RIGCTL"),
        shutil.which("rigctl"),
        shutil.which("rigctl.exe"),
        str(DEFAULT_WINDOWS_RIGCTL) if DEFAULT_WINDOWS_RIGCTL.exists() else None,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate))
        if path.exists():
            return str(path)
    return None


def parse_rigctl_ptt(output: str) -> Optional[bool]:
    """Parse rigctl get-PTT output."""
    match = re.search(r"\bPTT:\s*([01])\b", output or "")
    if not match:
        return None
    return match.group(1) == "1"


@dataclass
class HamlibRigConfig:
    rigctl_path: str
    model: int
    rig_path: str
    timeout_seconds: float = 3.0


class HamlibRig:
    """Adapter exposing the small set_mox/current_mox API used by FT8TxEngine."""

    def __init__(
        self,
        config: HamlibRigConfig,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.config = config
        self._runner = runner or subprocess.run
        self.current_mox: Optional[bool] = None
        self.current_interlock_state: Optional[str] = None
        self.last_error: Optional[str] = None
        self._last_ptt_poll = 0.0

    @property
    def backend_name(self) -> str:
        return "hamlib"

    def set_mox(self, on: bool) -> bool:
        command = f"T {1 if on else 0}"
        result = self._run_rigctl([command, "t", "q"])
        if result is None:
            return False
        ptt = parse_rigctl_ptt(result.stdout)
        if ptt is None:
            # Some rigctl backends do not echo PTT after set; treat a zero exit as
            # a successful command but keep the ownership state explicit.
            ptt = bool(on)
        self._set_ptt_state(ptt)
        return ptt == bool(on)

    def poll_ptt(self, *, max_age_seconds: float = 0.75) -> Optional[bool]:
        now = time.monotonic()
        if self.current_mox is not None and now - self._last_ptt_poll < max_age_seconds:
            return self.current_mox
        result = self._run_rigctl(["t", "q"])
        if result is None:
            return self.current_mox
        ptt = parse_rigctl_ptt(result.stdout)
        if ptt is not None:
            self._set_ptt_state(ptt)
        return self.current_mox

    def _set_ptt_state(self, ptt: bool) -> None:
        self.current_mox = bool(ptt)
        self.current_interlock_state = "TRANSMITTING" if ptt else "READY"
        self._last_ptt_poll = time.monotonic()

    def _run_rigctl(self, commands: list[str]) -> Optional[subprocess.CompletedProcess[str]]:
        payload = "\n".join(commands) + "\n"
        args = [
            self.config.rigctl_path,
            "-m",
            str(int(self.config.model)),
            "-r",
            str(self.config.rig_path),
        ]
        try:
            result = self._runner(
                args,
                input=payload,
                capture_output=True,
                text=True,
                timeout=float(self.config.timeout_seconds),
            )
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Hamlib rigctl command failed: %s", exc)
            return None
        if result.returncode != 0:
            self.last_error = (result.stderr or result.stdout or "").strip() or f"rigctl exited {result.returncode}"
            logger.warning("Hamlib rigctl returned %s: %s", result.returncode, self.last_error)
            return None
        self.last_error = None
        return result


def create_hamlib_rig(
    *,
    rigctl_path: str | None,
    model: int | str | None,
    rig_path: str | None,
    timeout_seconds: float = 3.0,
) -> Optional[HamlibRig]:
    resolved = resolve_rigctl_path(rigctl_path)
    if not resolved:
        logger.info("Hamlib rigctl is not available")
        return None
    path = str(rig_path or "").strip()
    if not path:
        logger.info("Hamlib rig path is empty")
        return None
    try:
        model_int = int(model or 23005)
    except (TypeError, ValueError):
        logger.warning("Invalid Hamlib model %r", model)
        return None
    return HamlibRig(
        HamlibRigConfig(
            rigctl_path=resolved,
            model=model_int,
            rig_path=path,
            timeout_seconds=timeout_seconds,
        )
    )
