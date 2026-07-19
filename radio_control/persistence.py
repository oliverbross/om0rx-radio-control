"""Crash-safe, process-local serialization helpers for station data files."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


_locks_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}


def file_lock(path: str | Path) -> threading.RLock:
    """Return the shared re-entrant lock for a resolved local path."""
    key = str(Path(path).resolve())
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


@contextmanager
def locked_file(path: str | Path) -> Iterator[None]:
    with file_lock(path):
        yield


def _fsync_directory(path: Path) -> None:
    """Best-effort directory sync (not supported by Windows file handles)."""
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_text(
    path: str | Path,
    content: str,
    *,
    backup: bool = False,
    encoding: str = "utf-8",
) -> None:
    """Flush and atomically replace a text file while holding its shared lock."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with locked_file(target):
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding=encoding,
                newline="",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_name = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if backup and target.exists():
                shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
            os.replace(temp_name, target)
            _fsync_directory(target.parent)
        finally:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)


def atomic_write_json(path: str | Path, data: Any, *, backup: bool = True) -> None:
    atomic_write_text(
        path,
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        backup=backup,
    )


def read_json_object(
    path: str | Path,
    *,
    quarantine_corrupt: bool = False,
) -> dict[str, Any]:
    target = Path(path)
    with locked_file(target):
        if not target.exists():
            return {}
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            if quarantine_corrupt:
                quarantine = target.with_suffix(target.suffix + ".corrupt")
                counter = 1
                while quarantine.exists():
                    quarantine = target.with_suffix(target.suffix + f".corrupt.{counter}")
                    counter += 1
                os.replace(target, quarantine)
            return {}
        return value if isinstance(value, dict) else {}


def durable_append_text(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    prefix_if_missing: str = "",
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with locked_file(target):
        with target.open("a", encoding=encoding, newline="") as handle:
            if handle.tell() == 0 and prefix_if_missing:
                handle.write(prefix_if_missing)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
