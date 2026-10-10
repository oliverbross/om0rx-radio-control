"""Exact local supervisor/backend/bridge ownership attestation.

The lifecycle scripts write this manifest atomically after all three processes
are known.  A managed backend treats a missing, stale, or replaced owner as an
authorization failure; an HTTP health response alone never proves ownership.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import socket
from typing import Any, Callable

from radio_control.persistence import read_json_object


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_OWNER_ENV = "OM0RX_RUNTIME_OWNER_ID"
RUNTIME_OWNER_PATH_ENV = "OM0RX_RUNTIME_OWNER_PATH"
SUPERVISOR_ENV = "APP_LIFECYCLE_SUPERVISOR"
DEFAULT_RUNTIME_OWNER_PATH = ROOT / "logs" / "runtime_owner.json"


class _MibTcpRowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("state", wintypes.DWORD),
        ("local_address", wintypes.DWORD),
        ("local_port", wintypes.DWORD),
        ("remote_address", wintypes.DWORD),
        ("remote_port", wintypes.DWORD),
        ("owning_pid", wintypes.DWORD),
    ]


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _normal_path(value: str) -> str:
    return os.path.normcase(os.path.realpath(str(value or "")))


def query_process_identity(pid: int) -> dict[str, Any] | None:
    """Return the non-reusable Windows process identity used by the manifest."""
    if os.name != "nt" or int(pid) <= 0:
        return None

    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]

    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        creation_time = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        return {
            "pid": int(pid),
            "executable_path": _normal_path(buffer.value),
            "creation_time_filetime": creation_time,
        }
    finally:
        kernel32.CloseHandle(handle)


def query_tcp_listener_pids(port: int) -> set[int] | None:
    """Return exact IPv4 listener owners without starting PowerShell/CIM.

    The station authorization path calls this helper, so it deliberately uses
    the in-process Windows IP Helper API instead of a slow subprocess.  A
    failed query returns ``None`` and is treated as an ownership failure.
    """
    if os.name != "nt" or not (0 < int(port) <= 65535):
        return None

    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = iphlpapi.GetExtendedTcpTable
    get_table.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
    ]
    get_table.restype = wintypes.DWORD

    af_inet = 2
    tcp_table_owner_pid_listener = 3
    error_insufficient_buffer = 122
    size = wintypes.DWORD(0)
    result = get_table(
        None,
        ctypes.byref(size),
        False,
        af_inet,
        tcp_table_owner_pid_listener,
        0,
    )
    if result != error_insufficient_buffer or size.value < ctypes.sizeof(wintypes.DWORD):
        return None

    buffer = ctypes.create_string_buffer(size.value)
    result = get_table(
        buffer,
        ctypes.byref(size),
        False,
        af_inet,
        tcp_table_owner_pid_listener,
        0,
    )
    if result != 0:
        return None

    count = wintypes.DWORD.from_buffer_copy(buffer.raw[: ctypes.sizeof(wintypes.DWORD)]).value
    row_size = ctypes.sizeof(_MibTcpRowOwnerPid)
    offset = ctypes.sizeof(wintypes.DWORD)
    owners: set[int] = set()
    for index in range(int(count)):
        start = offset + index * row_size
        end = start + row_size
        if end > len(buffer):
            return None
        row = _MibTcpRowOwnerPid.from_buffer_copy(buffer.raw[start:end])
        if socket.ntohs(int(row.local_port) & 0xFFFF) == int(port):
            owners.add(int(row.owning_pid))
    return owners


def runtime_owner_path() -> Path:
    value = os.environ.get(RUNTIME_OWNER_PATH_ENV, "").strip()
    return Path(value).resolve() if value else DEFAULT_RUNTIME_OWNER_PATH


def runtime_owner_status(
    *,
    path: Path | None = None,
    expected_owner_id: str | None = None,
    expected_backend_pid: int | None = None,
    process_identity: Callable[[int], dict[str, Any] | None] = query_process_identity,
    listener_owners: Callable[[int], set[int] | None] = query_tcp_listener_pids,
) -> dict[str, Any]:
    """Validate exact managed-runtime ownership without mutating process state."""
    if not _env_flag(SUPERVISOR_ENV):
        return {"success": True, "managed": False, "reason": "unmanaged-runtime"}

    expected_owner_id = (
        os.environ.get(RUNTIME_OWNER_ENV, "").strip()
        if expected_owner_id is None
        else str(expected_owner_id).strip()
    )
    if not expected_owner_id:
        return {"success": False, "managed": True, "reason": "owner-id-missing"}

    manifest_path = path or runtime_owner_path()
    manifest = read_json_object(manifest_path)
    if not manifest:
        return {"success": False, "managed": True, "reason": "owner-manifest-missing"}
    if manifest.get("schema") != 1 or manifest.get("state") != "active":
        return {"success": False, "managed": True, "reason": "owner-manifest-inactive"}
    if str(manifest.get("owner_id") or "") != expected_owner_id:
        return {"success": False, "managed": True, "reason": "owner-id-mismatch"}

    ports = manifest.get("ports") if isinstance(manifest.get("ports"), dict) else {}
    expected_ports = {
        "backend": int(os.environ.get("BACKEND_PORT", "8080")),
        "bridge_ws": 8091,
        "bridge_command": 8092,
    }
    if any(int(ports.get(name, -1)) != value for name, value in expected_ports.items()):
        return {"success": False, "managed": True, "reason": "owner-port-contract-mismatch"}

    expected_backend_pid = os.getpid() if expected_backend_pid is None else int(expected_backend_pid)
    declared_pids: dict[str, int] = {}
    for role in ("supervisor", "backend", "bridge"):
        declared = manifest.get(role)
        if not isinstance(declared, dict):
            return {"success": False, "managed": True, "reason": f"{role}-identity-missing"}
        try:
            declared_pid = int(declared.get("pid"))
            declared_created = int(declared.get("creation_time_filetime"))
        except (TypeError, ValueError):
            return {"success": False, "managed": True, "reason": f"{role}-identity-invalid"}
        if role == "backend" and declared_pid != expected_backend_pid:
            return {"success": False, "managed": True, "reason": "backend-pid-mismatch"}
        declared_pids[role] = declared_pid
        actual = process_identity(declared_pid)
        if not actual:
            return {"success": False, "managed": True, "reason": f"{role}-process-missing"}
        if (
            int(actual.get("pid", -1)) != declared_pid
            or int(actual.get("creation_time_filetime", -1)) != declared_created
            or _normal_path(str(actual.get("executable_path") or ""))
            != _normal_path(str(declared.get("executable_path") or ""))
        ):
            return {"success": False, "managed": True, "reason": f"{role}-identity-mismatch"}

    listener_contract = {
        int(expected_ports["backend"]): declared_pids["backend"],
        int(expected_ports["bridge_ws"]): declared_pids["bridge"],
        int(expected_ports["bridge_command"]): declared_pids["bridge"],
    }
    for port, expected_pid in listener_contract.items():
        owners = listener_owners(port)
        if owners is None:
            return {"success": False, "managed": True, "reason": f"listener-query-failed:{port}"}
        if owners != {expected_pid}:
            return {"success": False, "managed": True, "reason": f"listener-owner-mismatch:{port}"}

    return {
        "success": True,
        "managed": True,
        "reason": "owner-verified",
        "owner_id": expected_owner_id,
        "path": str(manifest_path),
        "ports": expected_ports,
    }
