"""Windows-wide exclusive ownership for OM0RX station controllers."""

from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Self
from uuid import uuid4

MUTEX_NAME = r"Global\OM0RX.StationController"
CONFLICT_EXIT_CODE = 73
OWNER_SCHEMA = 1
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
logger = logging.getLogger(__name__)


def default_owner_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "OM0RX" / "station-controller-owner.json"
    return Path.home() / ".local" / "state" / "om0rx" / "station-controller-owner.json"


@dataclass(frozen=True)
class ControllerOwnerInfo:
    schema: int
    mutex_name: str
    controller_family: str
    pid: int
    executable_path: str
    started_utc: str
    launch_source: str


class ControllerOwnershipError(RuntimeError):
    """The ownership boundary could not be established safely."""


class ControllerOwnershipConflict(ControllerOwnershipError):
    def __init__(self, requested_family: str, active_owner: ControllerOwnerInfo | None):
        self.requested_family = requested_family
        self.active_owner = active_owner
        owner = (
            f"{active_owner.controller_family} (PID {active_owner.pid})"
            if active_owner
            else "an unidentified OM0RX controller"
        )
        super().__init__(
            f"Another OM0RX station controller is active: {owner}; "
            f"{requested_family} did not open station resources. Inspect the "
            "'OM0RX Remote Station Agent' scheduled task and the HKCU Run value "
            "'OM0RX Radio Control Agent', then stop only the controller you intend to replace."
        )


class _WindowsMutex:
    WAIT_OBJECT_0 = 0x00000000
    WAIT_ABANDONED = 0x00000080
    WAIT_TIMEOUT = 0x00000102

    def __init__(self, name: str) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
        kernel32.ReleaseMutex.restype = ctypes.c_bool
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        self._kernel32 = kernel32
        self._handle = kernel32.CreateMutexW(None, False, name)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def acquire(self) -> tuple[bool, bool]:
        result = self._kernel32.WaitForSingleObject(self._handle, 0)
        if result == self.WAIT_OBJECT_0:
            return True, False
        if result == self.WAIT_ABANDONED:
            return True, True
        if result == self.WAIT_TIMEOUT:
            return False, False
        raise ctypes.WinError(ctypes.get_last_error())

    def release(self) -> None:
        if not self._kernel32.ReleaseMutex(self._handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class _PortableMutex:
    """Test/development fallback; production Windows uses the kernel mutex above."""

    def __init__(self, name: str) -> None:
        import fcntl

        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:24]
        self._fcntl = fcntl
        self._path = Path(tempfile.gettempdir()) / f"om0rx-controller-{digest}.lock"
        self._stream: IO[bytes] = self._path.open("a+b")

    def acquire(self) -> tuple[bool, bool]:
        try:
            self._fcntl.flock(self._stream.fileno(), self._fcntl.LOCK_EX | self._fcntl.LOCK_NB)
            return True, False
        except BlockingIOError:
            return False, False

    def release(self) -> None:
        self._fcntl.flock(self._stream.fileno(), self._fcntl.LOCK_UN)

    def close(self) -> None:
        self._stream.close()


def _safe_label(value: str, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if _SAFE_LABEL.fullmatch(candidate) else fallback


def read_owner_metadata(path: Path | None = None) -> ControllerOwnerInfo | None:
    target = path or default_owner_path()
    try:
        document: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
        info = ControllerOwnerInfo(
            schema=int(document["schema"]),
            mutex_name=str(document["mutex_name"]),
            controller_family=str(document["controller_family"]),
            pid=int(document["pid"]),
            executable_path=str(document["executable_path"]),
            started_utc=str(document["started_utc"]),
            launch_source=str(document["launch_source"]),
        )
        if info.schema != OWNER_SCHEMA or info.pid <= 0:
            return None
        return info
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


class StationControllerOwnership:
    """Own the shared controller mutex and its non-authoritative diagnostics record."""

    def __init__(
        self,
        controller_family: str,
        launch_source: str,
        *,
        mutex_name: str = MUTEX_NAME,
        owner_path: Path | None = None,
    ) -> None:
        self.controller_family = _safe_label(controller_family, "unknown-controller")
        self.launch_source = _safe_label(launch_source, "unknown")
        self.mutex_name = mutex_name
        self.owner_path = owner_path or default_owner_path()
        self.owner_info: ControllerOwnerInfo | None = None
        self.previous_owner: ControllerOwnerInfo | None = None
        self.abandoned = False
        self._mutex: _WindowsMutex | _PortableMutex | None = None
        self._acquired = False

    def acquire(self) -> Self:
        if self._acquired:
            return self
        mutex: _WindowsMutex | _PortableMutex
        mutex = _WindowsMutex(self.mutex_name) if os.name == "nt" else _PortableMutex(self.mutex_name)
        acquired = False
        try:
            acquired, abandoned = mutex.acquire()
            if not acquired:
                owner = read_owner_metadata(self.owner_path)
                raise ControllerOwnershipConflict(self.controller_family, owner)
            self.previous_owner = read_owner_metadata(self.owner_path) if abandoned else None
            self.abandoned = abandoned
            info = ControllerOwnerInfo(
                schema=OWNER_SCHEMA,
                mutex_name=self.mutex_name,
                controller_family=self.controller_family,
                pid=os.getpid(),
                executable_path=str(Path(sys.executable).resolve()),
                started_utc=datetime.now(UTC).isoformat(),
                launch_source=self.launch_source,
            )
            self._write_owner(info)
            self.owner_info = info
            self._mutex = mutex
            self._acquired = True
            return self
        except (ControllerOwnershipConflict, OSError):
            if acquired and not self._acquired:
                try:
                    mutex.release()
                except OSError:
                    logger.warning("Could not release controller mutex during failed acquisition.")
            mutex.close()
            raise

    def _write_owner(self, info: ControllerOwnerInfo) -> None:
        self.owner_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.owner_path.with_name(
            f"{self.owner_path.name}.tmp-{os.getpid()}-{uuid4().hex}"
        )
        try:
            temporary.write_text(
                json.dumps(asdict(info), indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self.owner_path)
        finally:
            temporary.unlink(missing_ok=True)

    def release(self) -> None:
        if not self._acquired or self._mutex is None:
            return
        try:
            current = read_owner_metadata(self.owner_path)
            if (
                current
                and self.owner_info
                and current.pid == self.owner_info.pid
                and current.controller_family == self.owner_info.controller_family
            ):
                try:
                    self.owner_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove stale controller owner metadata.")
            self._mutex.release()
        finally:
            self._mutex.close()
            self._mutex = None
            self._acquired = False

    def __enter__(self) -> Self:
        return self.acquire()

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.release()
