"""One station-owned digital engine, with legacy WSJT services as adapters.

Selection never enables transmission. Switching requires a confirmed idle radio
and stops the previous process before changing UDP ownership.
"""
from __future__ import annotations

import asyncio
import csv
import json
import hashlib
import fnmatch
import logging
import os
from pathlib import Path
import platform
import secrets
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from radio_control.persistence import atomic_write_json, atomic_write_text, read_json_object
from radio_control.runtime_owner import runtime_owner_status

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "settings" / "digital_engine.json"
PROVIDERS = {
    "none": {"label": "None (digital engines disabled)", "planner_owner": "none", "modes": []},
    "wsjtz": {"label": "OM0RX WSJT-Z", "planner_owner": "om0rx", "modes": ["FT8", "FT4", "FT2"]},
    "mshv_auto_dx": {"label": "MSHV Auto DX Chaser", "planner_owner": "mshv", "modes": ["FT8", "FT4"]},
}
PROVIDER_CLIENT_IDS = {
    "none": set(),
    "wsjtz": {"WSJT-X", "WSJT-X - OM0RX-WSJT-Z", "WSJT-Z", "WSJT-Z - OM0RX-WSJT-Z"},
    "mshv_auto_dx": {"MSHV-OM0RX-AUTO-DX"},
}
STARTUP_CONFIRM_TIMEOUT_SECONDS = 45.0
STARTUP_CONFIRM_INTERVAL_SECONDS = 0.2
PROCESS_SCAN_CACHE_SECONDS = 2.0
PROCESS_SCAN_FALLBACK_CACHE_SECONDS = 2.0
STATION_PREPARE_TTL_SECONDS = 90.0
STATION_PTT_PERMIT_TTL_SECONDS = 45.0
STATION_PTT_CONSUME_TIMEOUT_SECONDS = 1.25
STATION_ACCESSORY_CACHE_MAX_AGE_SECONDS = 5.0
# MSHV guarantees a 15-second WSJT-X heartbeat.  Allow one scheduling margin,
# but keep station authorization much stricter than the public bridge's
# operator-facing stale display window.
STATION_CLIENT_FRESH_MAX_AGE_MS = 20_000.0
STATION_AUDIT_PATH = ROOT / "logs" / "digital_station_authorization.jsonl"
MSHV_MUTABLE_PATHS = {
    ".history-import.lock", "history-import.json", "history-backups/**", "log/**", "logs/**",
    "settings/autodx.ini", "settings/ms_*", "settings/*.txt", "settings/azel.dat",
    "settings/database/worked.db", "settings/database/worked.db-*",
    "settings/database/wavelog_delta_state.json",
    "settings/database/award_hunting.json",
    "settings/database/dxpedition_watch.json",
    "settings/database/autodx_ignore.json",
    "settings/database/autodx_status_owner.json",
    "settings/database/lotw-users.txt", "settings/database/confirmed-dxcc.txt",
    "settings/database/us-states.txt",
    "settings/database/status-colors.ini",
    "settings/database/msloc_db*", "settings/database/msbcn_db*",
    "settings/database/mstn_db*", "settings/database/sat.dat",
}


def _stage_mshv_display_indexes(runtime: Path) -> dict[str, Any]:
    """Publish Wavelog status facts and the shared Spots palette for MSHV.

    This runs immediately before process launch, so native decode rows and the
    web Spots table use one classification source without network calls in the
    decode hot path.
    """
    from radio_control import config
    from radio_control.qso_status_store import DuckDBQSOStatusStore

    database = runtime / "settings" / "database"
    database.mkdir(parents=True, exist_ok=True)
    store = DuckDBQSOStatusStore()
    facts = store.mshv_confirmation_index()
    if facts is not None:
        atomic_write_text(database / "confirmed-dxcc.txt", "\n".join(facts) + "\n")
    state_facts = store.mshv_us_state_index()
    if state_facts is not None:
        atomic_write_text(database / "us-states.txt", "\n".join(state_facts) + "\n")
    lotw_members = store.mshv_lotw_members()
    if lotw_members is not None:
        atomic_write_text(
            database / "lotw-users.txt",
            "# OM0RX QRZ LoTW membership cache v1\n" + "\n".join(lotw_members) + "\n",
        )

    palette_keys = (
        "New Call", "New Band", "New Mode", "New Band+Mode", "Worked",
        "Confirmed", "ATNO", "C/New Band", "C/New Mode", "C/New Band+Mode",
        "W/New Band", "W/New Mode", "W/New Band+Mode", "Unknown",
    )
    palette = getattr(config, "COLORS", {})
    color_lines = ["[StatusColors]"]
    for key in palette_keys:
        raw = str(palette.get(key, "") or "")
        if len(raw) == 9 and raw.startswith("#"):
            raw = "#" + raw[3:]
        if len(raw) == 7 and raw.startswith("#"):
            color_lines.append(f"{key.replace('/', '_')}={raw}")
    atomic_write_text(database / "status-colors.ini", "\n".join(color_lines) + "\n")
    return {
        "confirmation_index_refreshed": facts is not None,
        "confirmation_fact_count": len(facts or ()),
        "us_state_index_refreshed": state_facts is not None,
        "us_state_fact_count": len(state_facts or ()),
        "lotw_membership_count": len(lotw_members or ()),
        "status_palette_count": len(color_lines) - 1,
    }


def normalize_provider(value: Any) -> str:
    value = str(value or "none").strip().lower()
    value = {"disabled": "none", "off": "none", "wsjt-z": "wsjtz", "mshv": "mshv_auto_dx"}.get(value, value)
    # A missing/corrupt persisted choice must fail safe.  The tray performs
    # the only intentional migration of its legacy WSJT-Z startup preference.
    return value if value in PROVIDERS else "none"


def selected_provider() -> str:
    # Read on demand so separate workers and the tray see the committed choice.
    return normalize_provider(read_json_object(STATE_PATH).get("provider", "none"))


def require_om0rx_planner() -> None:
    provider = selected_provider()
    if provider != "wsjtz":
        owner = "MSHV" if provider == "mshv_auto_dx" else "No digital engine"
        raise HTTPException(409, f"{owner} owns digital target selection; OM0RX planner is disabled")


def backend_radio_control_allowed(*, force_refresh: bool = True) -> bool:
    """The CAT engine owns dial, modulation and transmit while it is running."""
    if selected_provider() != "mshv_auto_dx":
        return True
    try:
        service = get_digital_engine_service()
        return not service.processes(force_refresh=force_refresh)["mshv_auto_dx"] and not any(row["provider"] == "mshv_auto_dx" for row in service.unmanaged_processes)
    except HTTPException:
        return False


@contextmanager
def lifecycle_lock():
    """Serialize selectors across FastAPI workers as well as browser requests."""
    lock_path = STATE_PATH.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise HTTPException(409, "Another digital engine lifecycle operation is active") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class DigitalEngineService:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.engine_state: dict[str, Any] = {}
        self.engine_state_at = 0.0
        self.watchdog_task = None
        self.process_identities: dict[int, tuple[str, str, str]] = {}
        self.unmanaged_processes: list[dict[str, Any]] = []
        self._hash_cache: dict[str, tuple[int, int, str]] = {}
        self._process_scan_lock = threading.Lock()
        self._process_scan_condition = threading.Condition(self._process_scan_lock)
        self._process_scan_rows: list[dict[str, Any]] = []
        self._process_scan_at = 0.0
        self._process_scan_backend = "none"
        self._process_scan_refreshing = False
        self.station_preparations: dict[str, dict[str, Any]] = {}
        self.station_permits: dict[str, dict[str, Any]] = {}
        self.station_authorization_epoch = 0
        self.station_client_generation = -1
        self.station_audit_lock = threading.Lock()
        self.station_control_lease_token: str | None = None
        self.station_control_inhibit_reason: str | None = None

    def _legacy(self):
        from services.wsjtx import get_wsjtx_service
        return get_wsjtx_service()

    def _station_audit(self, event: str, **details: Any) -> None:
        record = {
            "timestamp": time.time(),
            "event": str(event),
            **details,
        }
        with self.station_audit_lock:
            STATION_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with STATION_AUDIT_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    def clear_station_authorizations(self, reason: str) -> None:
        with self.lock:
            self.station_authorization_epoch += 1
            epoch = self.station_authorization_epoch
            prepare_count = len(self.station_preparations)
            permit_count = len(self.station_permits)
            self.station_preparations.clear()
            for permit in self.station_permits.values():
                permit["revoked"] = True
        self._station_audit(
            "authorization-cleared",
            reason=reason,
            authorization_epoch=epoch,
            prepare_count=prepare_count,
            permit_count=permit_count,
        )

    def acquire_station_control_lease(self, reason: str) -> str:
        """Inhibit new native authorizations and revoke every outstanding one."""
        token = secrets.token_urlsafe(24)
        clean_reason = str(reason or "station-control").strip() or "station-control"
        with self.lock:
            if self.station_control_lease_token is not None:
                raise RuntimeError("another station-control lease is active")
            self.station_control_lease_token = token
            self.station_control_inhibit_reason = clean_reason
            self.station_authorization_epoch += 1
            epoch = self.station_authorization_epoch
            prepare_count = len(self.station_preparations)
            permit_count = len(self.station_permits)
            self.station_preparations.clear()
            for permit in self.station_permits.values():
                permit["revoked"] = True
        self._station_audit(
            "station-control-lease-acquired",
            reason=clean_reason,
            authorization_epoch=epoch,
            prepare_count=prepare_count,
            permit_count=permit_count,
        )
        return token

    def release_station_control_lease(self, token: str) -> bool:
        """Release only the exact lease acquired by the station coordinator."""
        with self.lock:
            if not token or token != self.station_control_lease_token:
                return False
            reason = self.station_control_inhibit_reason
            self.station_control_lease_token = None
            self.station_control_inhibit_reason = None
        self._station_audit("station-control-lease-released", reason=reason)
        return True

    def station_control_inhibit(self) -> str | None:
        with self.lock:
            return self.station_control_inhibit_reason

    def reset_station_client_generation(self, reason: str) -> None:
        """Start a fresh native generation namespace for a new MSHV process.

        Native authorization generations are process-local and restart at one.
        Keeping the previous process' high-water mark across a supervised stop
        would reject the first prepare from the newly attested process as stale.
        Callers must already have retired all server authorizations and must use
        this only after the old process is gone or immediately before launching
        a replacement.
        """
        with self.lock:
            previous = self.station_client_generation
            self.station_client_generation = -1
        self._station_audit(
            "native-generation-reset",
            reason=reason,
            previous_native_generation=previous,
        )

    def begin_station_preparation(
        self, native_generation: int,
    ) -> tuple[bool, str, int]:
        """Atomically retire prior permits before a new slow prepare begins.

        Native invalidation notification is asynchronous.  The generation lets
        a prepare overtake its matching notification safely: once this method
        has accepted generation N, a delayed invalidation for N is idempotent
        and cannot revoke the preparation that follows.  An invalidation for a
        later generation still wins and changes the server authorization epoch.
        """
        with self.lock:
            if self.station_control_lease_token is not None:
                return False, "station-control-inhibited", self.station_authorization_epoch
            if native_generation < 0:
                return False, "native-generation-invalid", self.station_authorization_epoch
            if native_generation < self.station_client_generation:
                return False, "native-generation-stale", self.station_authorization_epoch
            self.station_client_generation = native_generation
            self.station_authorization_epoch += 1
            epoch = self.station_authorization_epoch
            prepare_count = len(self.station_preparations)
            permit_count = len(self.station_permits)
            self.station_preparations.clear()
            for permit in self.station_permits.values():
                permit["revoked"] = True
        self._station_audit(
            "prepare-authorization-begun",
            native_generation=native_generation,
            authorization_epoch=epoch,
            prepare_count=prepare_count,
            permit_count=permit_count,
        )
        return True, "prepare-authorization-begun", epoch

    def apply_native_invalidation(
        self, reason: str, native_generation: int,
    ) -> tuple[bool, str]:
        """Apply only a newer native invalidation generation."""
        with self.lock:
            if native_generation < 0:
                apply = True
                result = "native-generation-missing"
            elif native_generation <= self.station_client_generation:
                apply = False
                result = "native-invalidation-already-observed"
            else:
                apply = True
                result = "native-invalidation-applied"
                self.station_client_generation = native_generation
            if apply:
                self.station_authorization_epoch += 1
                epoch = self.station_authorization_epoch
                prepare_count = len(self.station_preparations)
                permit_count = len(self.station_permits)
                self.station_preparations.clear()
                for permit in self.station_permits.values():
                    permit["revoked"] = True
            else:
                epoch = self.station_authorization_epoch
                prepare_count = 0
                permit_count = 0
        self._station_audit(
            result,
            reason=reason,
            native_generation=native_generation,
            authorization_epoch=epoch,
            prepare_count=prepare_count,
            permit_count=permit_count,
        )
        return apply, result

    def station_process_binding(self, *, force_refresh: bool = True) -> dict[str, Any]:
        processes = self.processes(force_refresh=force_refresh)
        pids = list(processes.get("mshv_auto_dx") or [])
        if len(pids) != 1 or self.unmanaged_processes:
            raise HTTPException(409, "exact managed MSHV process identity is unavailable")
        pid = int(pids[0])
        identity = self.process_identities.get(pid)
        if not identity:
            raise HTTPException(409, "managed MSHV process identity is unavailable")
        bridge = self._legacy().get_bridge_status()
        client = bridge.get("client") if isinstance(bridge.get("client"), dict) else {}
        client_id = str(client.get("id") or "")
        if not self.station_bridge_identity_fresh(bridge):
            raise HTTPException(409, "fresh exact MSHV bridge identity is unavailable")
        return {
            "provider": "mshv_auto_dx",
            "pid": pid,
            "process_identity": list(identity),
            "bridge_client_id": client_id,
            "bridge_address": str(client.get("address") or ""),
            "bridge_port": int(client.get("port") or 0),
        }

    @staticmethod
    def station_bridge_identity_fresh(bridge: dict[str, Any]) -> bool:
        client = bridge.get("client") if isinstance(bridge.get("client"), dict) else {}
        try:
            client_age_ms = float(client.get("lastSeenMs"))
        except (TypeError, ValueError):
            return False
        return (
            bridge.get("success") is True
            and bridge.get("provider") == "mshv_auto_dx"
            and bridge.get("conflict") is not True
            and str(client.get("id") or "") in PROVIDER_CLIENT_IDS["mshv_auto_dx"]
            and 0 <= client_age_ms < STATION_CLIENT_FRESH_MAX_AGE_MS
        )

    def create_station_preparation(
        self,
        binding: dict[str, Any],
        *,
        expected_epoch: int | None = None,
        native_generation: int | None = None,
    ) -> tuple[str, int]:
        now = time.monotonic()
        nonce = secrets.token_urlsafe(32)
        expires_at = now + STATION_PREPARE_TTL_SECONDS
        with self.lock:
            if self.station_control_lease_token is not None:
                raise RuntimeError("station control is inhibited")
            if expected_epoch is not None and expected_epoch != self.station_authorization_epoch:
                raise RuntimeError("station authorization changed during prepare")
            if native_generation is not None and native_generation != self.station_client_generation:
                raise RuntimeError("native generation changed during prepare")
            epoch = self.station_authorization_epoch
            self.station_preparations = {
                key: value for key, value in self.station_preparations.items()
                if float(value.get("expires_at", 0)) > now
            }
            self.station_preparations[nonce] = {
                **binding, "authorization_epoch": epoch, "expires_at": expires_at,
            }
        self._station_audit("prepare-issued", nonce=nonce, authorization_epoch=epoch, **binding)
        return nonce, int(STATION_PREPARE_TTL_SECONDS * 1000)

    def consume_station_preparation(
        self, nonce: str, binding: dict[str, Any],
    ) -> tuple[bool, str, int | None, int | None]:
        now = time.monotonic()
        with self.lock:
            prepared = self.station_preparations.pop(str(nonce or ""), None)
            if not prepared:
                reason = "prepare-nonce-missing-or-replayed"
            elif float(prepared.get("expires_at", 0)) <= now:
                reason = "prepare-nonce-expired"
            elif int(prepared.get("authorization_epoch", -1)) != self.station_authorization_epoch:
                reason = "prepare-nonce-revoked"
            elif {key: prepared.get(key) for key in binding} != binding:
                reason = "prepare-nonce-binding-mismatch"
            else:
                epoch = int(prepared["authorization_epoch"])
                native_generation = int(prepared.get("native_generation", -1))
                reason = "station-prepared"
        if reason == "prepare-nonce-missing-or-replayed":
            self._station_audit("prepare-rejected", reason="missing-or-replayed", nonce=str(nonce or ""))
            return False, reason, None, None
        if reason == "prepare-nonce-expired":
            self._station_audit("prepare-rejected", reason="expired", nonce=nonce)
            return False, reason, None, None
        if reason == "prepare-nonce-revoked":
            self._station_audit("prepare-rejected", reason="revoked", nonce=nonce)
            return False, reason, None, None
        if reason == "prepare-nonce-binding-mismatch":
            self._station_audit("prepare-rejected", reason="binding-mismatch", nonce=nonce)
            return False, reason, None, None
        self._station_audit(
            "prepare-consumed", nonce=nonce, authorization_epoch=epoch,
            **binding,
        )
        return True, reason, epoch, native_generation

    def create_station_permit(
        self,
        binding: dict[str, Any],
        *,
        expected_epoch: int,
        native_generation: int,
    ) -> tuple[str, int]:
        now = time.monotonic()
        nonce = secrets.token_urlsafe(32)
        expires_at = now + STATION_PTT_PERMIT_TTL_SECONDS
        # Process/CIM and bridge refresh can be comparatively slow.  Never
        # hold the authorization lock while doing that I/O: Halt/Stop must be
        # able to advance the epoch immediately.  The locked checks below
        # make any lifecycle change during this refresh authoritative.
        current_process = self.station_process_binding(force_refresh=True)
        with self.lock:
            if self.station_control_lease_token is not None:
                raise RuntimeError("station control is inhibited")
            if expected_epoch != self.station_authorization_epoch:
                raise RuntimeError("station authorization changed during final readiness")
            if native_generation != self.station_client_generation:
                raise RuntimeError("native generation changed during final readiness")
            if int(binding.get("native_generation", -1)) != native_generation:
                raise RuntimeError("native generation binding changed during final readiness")
            if selected_provider() != "mshv_auto_dx":
                raise RuntimeError("digital provider changed during final readiness")
            # A final permit can never adopt whatever identity is current
            # after a halt/provider/process/client race.  Lifecycle mutations
            # advance the epoch under this lock; spontaneous identity drift
            # fails the exact refreshed binding comparison and is rechecked
            # again by the authoritative edge-consume endpoint.
            process_keys = (
                "provider", "pid", "process_identity", "bridge_client_id",
                "bridge_address", "bridge_port",
            )
            if any(binding.get(key) != current_process.get(key) for key in process_keys):
                raise RuntimeError("managed process or bridge client changed during final readiness")
            epoch = self.station_authorization_epoch
            self.station_permits = {
                key: value for key, value in self.station_permits.items()
                if float(value.get("expires_at", 0)) > now
                and not value.get("consumed")
                and not value.get("revoked")
            }
            self.station_permits[nonce] = {
                **binding,
                "authorization_epoch": epoch,
                "expires_at": expires_at,
                "consumed": False,
            }
        self._station_audit("permit-issued", nonce=nonce, authorization_epoch=epoch, **binding)
        return nonce, int(STATION_PTT_PERMIT_TTL_SECONDS * 1000)

    def consume_station_permit(self, nonce: str, binding: dict[str, Any]) -> tuple[bool, str]:
        """Atomically consume a server permit after live route validation.

        The caller must build *binding* from current process/client/config and
        fresh radio/accessory evidence.  The epoch makes Halt/Stop/QSY and
        provider changes authoritative even if a native client retained a
        previously issued nonce.
        """
        now = time.monotonic()
        with self.lock:
            permit = self.station_permits.get(str(nonce or ""))
            if self.station_control_lease_token is not None:
                reason = "station-control-inhibited"
            elif not permit:
                reason = "permit-missing"
            elif permit.get("consumed"):
                reason = "permit-replayed"
            elif permit.get("revoked"):
                reason = "permit-revoked"
            elif int(permit.get("authorization_epoch", -1)) != self.station_authorization_epoch:
                reason = "permit-revoked"
            elif float(permit.get("expires_at", 0)) <= now:
                reason = "permit-expired"
            elif {key: permit.get(key) for key in binding} != binding:
                reason = "permit-binding-mismatch"
            else:
                permit["consumed"] = True
                reason = "permit-consumed"
            epoch = self.station_authorization_epoch
        self._station_audit(
            reason,
            nonce=str(nonce or ""),
            authorization_epoch=epoch,
            **binding,
        )
        return reason == "permit-consumed", reason

    def _file_sha256(self, path: Path) -> str:
        stat = path.stat()
        key = os.path.normcase(str(path.resolve()))
        cached = self._hash_cache.get(key)
        # Package promotion replaces the complete runtime directory atomically.
        # PE/source artifacts can legitimately retain the same size and copied
        # mtime across that swap, so creation/change time is also part of the
        # cache identity.  Otherwise preflight can reuse a digest from the
        # previous bundle even though the path now names a different file.
        signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if cached and cached[:3] == signature:
            return cached[3]
        digest = hashlib.sha256(path.read_bytes()).hexdigest().lower()
        self._hash_cache[key] = (*signature, digest)
        return digest

    @staticmethod
    def _parse_wmic_process_rows(output: str) -> list[dict[str, str]]:
        lines = [line.strip("\ufeff\r\n") for line in output.splitlines() if line.strip("\ufeff\r\n")]
        if not lines:
            return []
        return [dict(row) for row in csv.DictReader(lines)]

    def _perform_windows_process_scan(self) -> tuple[list[dict[str, Any]], str]:
        condition = "(Name like 'wsjt-z%' or Name like 'wsjtx%' or Name like 'mshv%')"
        try:
            scan = subprocess.run(
                [
                    "wmic.exe", "process", "where", condition, "get",
                    "Name,ProcessId,ExecutablePath,CommandLine,CreationDate", "/format:csv",
                ],
                capture_output=True, text=True, timeout=5, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return self._parse_wmic_process_rows(scan.stdout), "wmic"
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, UnicodeError):
            command = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(wsjt-z.*|wsjtx|mshv.*)\\.exe$' } | Select-Object Name,ProcessId,ExecutablePath,CommandLine,CreationDate | ConvertTo-Json -Compress"
            scan = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=8, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            value = json.loads(scan.stdout or "[]")
            return (value if isinstance(value, list) else [value]), "powershell-cim"

    def _refresh_process_scan_background(self) -> None:
        # Never hold the cache lock while invoking WMIC/CIM. Ordinary status
        # callers must be able to keep using the last complete snapshot while
        # a slow compatibility scan is in flight. A force scan that completes
        # after this refresh started wins, preventing stale overwrite.
        started_at = time.monotonic()
        try:
            rows, backend = self._perform_windows_process_scan()
            with self._process_scan_condition:
                if self._process_scan_at <= started_at:
                    self._process_scan_rows = [dict(row) for row in rows]
                    self._process_scan_at = time.monotonic()
                    self._process_scan_backend = backend
        finally:
            with self._process_scan_condition:
                self._process_scan_refreshing = False
                self._process_scan_condition.notify_all()

    def _invalidate_process_scan(self) -> None:
        with self._process_scan_lock:
            self._process_scan_at = 0.0

    def _scan_windows_process_rows(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        # Ordinary polling uses a single-flight stale-while-refresh snapshot;
        # lifecycle actions force a fresh exact scan. This keeps the slower CIM
        # compatibility fallback off the browser/Agent request path.
        requested_at = time.monotonic()
        while True:
            with self._process_scan_condition:
                if force_refresh and self._process_scan_at >= requested_at:
                    return [dict(row) for row in self._process_scan_rows]
                cache_seconds = (
                    PROCESS_SCAN_FALLBACK_CACHE_SECONDS
                    if self._process_scan_backend == "powershell-cim"
                    else PROCESS_SCAN_CACHE_SECONDS
                )
                if (
                    not force_refresh
                    and self._process_scan_at
                    and time.monotonic() - self._process_scan_at < cache_seconds
                ):
                    return [dict(row) for row in self._process_scan_rows]
                if not force_refresh and self._process_scan_at:
                    if not self._process_scan_refreshing:
                        self._process_scan_refreshing = True
                        threading.Thread(
                            target=self._refresh_process_scan_background,
                            name="digital-process-scan", daemon=True,
                        ).start()
                    return [dict(row) for row in self._process_scan_rows]
                if self._process_scan_refreshing:
                    # A force caller may wait for and share another exact scan;
                    # ordinary callers with a usable snapshot never reach here.
                    self._process_scan_condition.wait(timeout=15)
                    if self._process_scan_refreshing:
                        raise TimeoutError("digital process scan did not complete")
                    continue
                self._process_scan_refreshing = True

            try:
                rows, backend = self._perform_windows_process_scan()
            except Exception:
                # Always release coalesced callers on failure so lifecycle
                # operations fail closed instead of hanging.
                with self._process_scan_condition:
                    self._process_scan_refreshing = False
                    self._process_scan_condition.notify_all()
                raise
            with self._process_scan_condition:
                self._process_scan_rows = [dict(row) for row in rows]
                self._process_scan_at = time.monotonic()
                self._process_scan_backend = backend
                self._process_scan_refreshing = False
                self._process_scan_condition.notify_all()
                return [dict(row) for row in rows]

    def processes(self, *, force_refresh: bool = False) -> dict[str, list[int]]:
        result = {key: [] for key in PROVIDERS}
        if platform.system().lower() != "windows":
            return result
        try:
            rows = self._scan_windows_process_rows(force_refresh=force_refresh)
            runtime = Path(os.environ.get("OM0RX_MSHV_RUNTIME", ROOT / "data/build/mshv-auto-dx/runtime"))
            try:
                manifest = json.loads((runtime / "om0rx-build.json").read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                manifest = {}
            mshv_exe = runtime / str(manifest.get("executable") or "MSHV_OM0RX.exe")
            expected = {"wsjtz": {os.path.normcase(str((ROOT / "data/build/wsjt-z-clean/build-msys/wsjt-z-clean.exe").resolve())), os.path.normcase(str((ROOT / "data/build/wsjtx-improved-om0rx/build-msys/wsjtx.exe").resolve()))}, "mshv_auto_dx": {os.path.normcase(str(mshv_exe.resolve()))}}
            identities = {}
            unmanaged = []
            for row in rows:
                key = "mshv_auto_dx" if str(row["Name"]).lower().startswith("mshv") else "wsjtz"
                path = os.path.normcase(str(Path(row.get("ExecutablePath") or "missing").resolve()))
                hash_mismatch = False
                if key == "mshv_auto_dx" and path in expected[key]:
                    expected_hash = str(manifest.get("executable_sha256") or "").lower()
                    try:
                        hash_mismatch = not expected_hash or self._file_sha256(Path(path)) != expected_hash
                    except OSError:
                        hash_mismatch = True
                if path not in expected[key] or hash_mismatch or (key == "wsjtz" and "--rig-name OM0RX" not in str(row.get("CommandLine") or "")):
                    unmanaged.append({"provider": key, "pid": int(row["ProcessId"]), "path": row.get("ExecutablePath")})
                    continue
                pid = int(row["ProcessId"])
                result[key].append(pid)
                identities[pid] = (path, str(row.get("CommandLine") or ""), str(row.get("CreationDate") or ""))
            self.process_identities = identities
            self.unmanaged_processes = unmanaged
        except Exception as exc:
            raise HTTPException(503, f"Cannot establish digital-engine process ownership: {exc}") from exc
        return result

    def preflight(self, provider: str) -> dict[str, Any]:
        provider = normalize_provider(provider)
        if provider == "none":
            prerequisites = {"exe_exists": False, "qualified": True, "disabled": True, "version": None}
        elif provider == "wsjtz":
            prerequisites = self._legacy().get_wsjtz_engine_status()
        else:
            runtime = Path(os.environ.get("OM0RX_MSHV_RUNTIME", ROOT / "data" / "build" / "mshv-auto-dx" / "runtime"))
            try:
                manifest = json.loads((runtime / "om0rx-build.json").read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                manifest = {}
            exe = runtime / str(manifest.get("executable") or "MSHV_OM0RX.exe")
            lock = read_json_object(ROOT / "scripts/mshv/upstream-lock.json")
            files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
            declared_mutable = set(manifest.get("mutable_paths") or [])
            checks = {
                "manifest_schema": manifest.get("schema") == 1 and manifest.get("provider") == "mshv_auto_dx" and manifest.get("udp_client_id") == "MSHV-OM0RX-AUTO-DX" and manifest.get("station_interlock") is True,
                "station_ready_v2": "station_ready_v2" in set(manifest.get("capabilities") or []),
                "station_permit_v1": "station_permit_v1" in set(manifest.get("capabilities") or []),
                "target_priority_v1": "target_priority_v1" in set(manifest.get("capabilities") or []),
                "autodx_runtime_config_v1": "autodx_runtime_config_v1" in set(manifest.get("capabilities") or []),
                "wavelog_history_authority_v1": "wavelog_history_authority_v1" in set(manifest.get("capabilities") or []),
                "wavelog_history_delta_v2": "wavelog_history_delta_v2" in set(manifest.get("capabilities") or []),
                "source_attestation": bool(manifest.get("source_diff_sha256")),
                "commit": bool(manifest.get("commit") and manifest.get("commit") == lock.get("commit")),
                "import_unlocked": not (runtime / ".history-import.lock").exists(),
                "inventory_policy": manifest.get("inventory_excludes") == ["om0rx-build.json"] and declared_mutable == MSHV_MUTABLE_PATHS,
                "inventory_counts": len(files) == int(manifest.get("file_count", -1)) and int(manifest.get("staged_file_count", -1)) == len(files) + int(manifest.get("mutable_file_count", -1)),
            }
            for name, path in (("executable", exe), ("cty", runtime / "settings/database/cty.dat"), ("dxcc", runtime / "settings/database/dxcc_numbers.dat"), ("patch", runtime / "om0rx-integration.patch")):
                checks[name] = path.is_file() and self._file_sha256(path) == str(manifest.get(name + "_sha256") or "").lower()
            phase_patch = runtime / "om0rx-autodx-phase1.patch"
            phase2_patch = runtime / "om0rx-wavelog-history-phase2.patch"
            source_attestation = runtime / "source-attestation.patch"
            checks["autodx_phase1_patch"] = phase_patch.is_file() and self._file_sha256(phase_patch) == str(manifest.get("autodx_phase1_patch_sha256") or "").lower()
            checks["wavelog_history_phase2_patch"] = phase2_patch.is_file() and self._file_sha256(phase2_patch) == str(manifest.get("wavelog_history_phase2_patch_sha256") or "").lower()
            checks["source_attestation"] = checks["source_attestation"] and source_attestation.is_file() and self._file_sha256(source_attestation) == str(manifest.get("source_diff_sha256") or "").lower()
            immutable_actual = set()
            mutable_actual = set()
            if runtime.is_dir() and checks["inventory_policy"]:
                for path in runtime.rglob("*"):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(runtime).as_posix()
                    if relative == "om0rx-build.json":
                        continue
                    if any(fnmatch.fnmatch(relative, pattern) for pattern in declared_mutable):
                        mutable_actual.add(relative)
                    else:
                        immutable_actual.add(relative)
            checks["immutable_inventory_set"] = immutable_actual == set(files)
            checks["immutable_inventory_hashes"] = checks["immutable_inventory_set"] and all(
                self._file_sha256(runtime / relative) == str(digest).lower()
                for relative, digest in files.items()
            )
            # mutable_file_count describes the package-time snapshot only.
            # Atomic installation refreshes mutable operator state from the
            # stopped runtime, where transient status/lock files may already
            # have appeared or disappeared.  Qualification must therefore
            # validate the recorded count, but must not compare it with the
            # current mutable set.  Immutable paths and hashes remain exact.
            checks["mutable_inventory_count"] = int(manifest.get("mutable_file_count", -1)) >= 0
            checks["sqlite_driver"] = (runtime / "sqldrivers/qsqlite.dll").is_file()
            prerequisites = {"exe": str(exe), "exe_exists": exe.is_file(), "runtime": str(runtime), "version": manifest.get("version"), "manifest": manifest, "checks": checks, "qualified": all(checks.values())}
        success = provider == "none" or (bool(prerequisites.get("exe_exists")) and prerequisites.get("qualified", True))
        return {"success": success, "provider": provider, "prerequisites": prerequisites}

    def mshv_settings(self) -> dict[str, Any]:
        from services.mshv_configuration import read_mshv_auto_dx_settings
        processes = self.processes()
        running = any(processes[key] for key in processes if key != "none") or bool(self.unmanaged_processes)
        native_state = self.engine_state if processes.get("mshv_auto_dx") else None
        return read_mshv_auto_dx_settings(engine_running=running, engine_state=native_state)

    def update_mshv_settings(self, request: dict[str, Any]) -> dict[str, Any]:
        from services.mshv_configuration import update_mshv_auto_dx_settings
        with self.lock, lifecycle_lock():
            processes = self.processes(force_refresh=True)
            running = any(processes[key] for key in processes if key != "none") or bool(self.unmanaged_processes)
            return update_mshv_auto_dx_settings(request, engine_running=running)

    def reconcile_mshv_history(self) -> dict[str, Any]:
        """Apply source-backed staging recovery only under the lifecycle lock."""
        from services.mshv_history import reconcile_source_backed_pending
        with self.lock, lifecycle_lock():
            processes = self.processes(force_refresh=True)
            if any(processes.get(key) for key in processes if key != "none") or self.unmanaged_processes:
                raise HTTPException(409, "Stop all digital engines before reconciling MSHV history staging")
            return reconcile_source_backed_pending(apply=True)

    def status(self) -> dict[str, Any]:
        from radio_control import config
        from radio_control.flex_radio import FlexCtl
        from radio_control.station_policy import resolve_amplifier_policy
        provider = selected_provider()
        processes = self.processes()
        try:
            bridge = self._legacy().get_bridge_status()
        except Exception as exc:
            bridge = {"success": False, "error": str(exc)}
        if provider == "none":
            health = {"success": True, "status": "disabled", "provider": "none", "planner_owner": "none"}
        else:
            health = bridge
        any_process = any(bool(group) for key, group in processes.items() if key != "none")
        preflight = self.preflight(provider)
        try:
            frequency_hz = int(self.engine_state.get("frequency_hz") or 0)
        except (TypeError, ValueError):
            frequency_hz = 0
        band = FlexCtl.band_for_frequency(frequency_hz / 1_000_000) if frequency_hz else None
        station_policy = resolve_amplifier_policy(
            config,
            band,
            self.engine_state.get("mode") or "DIGU",
        ).as_dict()
        station_policy["control_inhibit"] = self.station_control_inhibit()
        engine_state_fresh = provider == "mshv_auto_dx" and time.monotonic() - self.engine_state_at < 6
        from services.mshv_observability import normalize_status
        autodx_status = normalize_status(self.engine_state.get("autodx_status"), fresh=engine_state_fresh)
        return {"success": True, "provider": provider, "selected_engine": provider, **PROVIDERS[provider], "version": preflight["prerequisites"].get("version"), "running": False if provider == "none" else bool(processes[provider]), "running_pids": processes, "unmanaged_processes": self.unmanaged_processes, "conflict": (provider == "none" and any_process) or sum(bool(group) for key, group in processes.items() if key != "none") > 1 or bool(self.unmanaged_processes) or bool(bridge.get("conflict")), "health": health, "bridge": bridge, "engine_state": self.engine_state, "engine_state_fresh": engine_state_fresh, "autodx_status": autodx_status, "station_identity_fresh": provider == "mshv_auto_dx" and self.station_bridge_identity_fresh(bridge), "station_identity_max_age_ms": int(STATION_CLIENT_FRESH_MAX_AGE_MS), "station_policy": station_policy, "capabilities": {"halt_tx": True, "target_control": provider == "wsjtz", "cross_band": provider == "wsjtz" or (provider == "mshv_auto_dx" and bool(preflight["prerequisites"].get("manifest", {}).get("station_interlock"))), "modes": PROVIDERS[provider]["modes"]}, "providers": PROVIDERS}

    def halt(self) -> dict[str, Any]:
        self.clear_station_authorizations("halt-tx")
        bridge_result: dict[str, Any]
        try:
            bridge_result = self._legacy().send_bridge_command("halt_tx", {})
        except Exception as exc:
            bridge_result = {"success": False, "error": str(exc)}
        from services.radio import get_radio_instance, run_radio_io_sync
        flex = get_radio_instance()
        try:
            radio_off = bool(flex is not None and run_radio_io_sync(lambda: flex.set_mox(False)))
        except Exception:
            radio_off = False
        command_accepted = bool(radio_off or bridge_result.get("success"))
        idle_confirmed = False
        confirmation_error = None
        try:
            self._confirm_idle()
            idle_confirmed = True
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            confirmation_error = str(detail if detail is not None else exc)
        result = {
            "success": command_accepted or idle_confirmed,
            "command_accepted": command_accepted,
            "idle_confirmed": idle_confirmed,
            "bridge_command_accepted": bridge_result.get("success") is True,
            "radio_command_accepted": radio_off,
            "bridge": bridge_result,
            "confirmation_error": confirmation_error,
        }
        if not result["success"]:
            raise HTTPException(503, {"reason": "No transmit-off command was accepted and RF idle could not be freshly confirmed", **result})
        return result

    def _confirm_idle(self) -> None:
        from services.radio import get_radio_instance, run_radio_io_sync
        flex = get_radio_instance()
        if flex is None:
            raise HTTPException(409, "Radio transmit state must be confirmed idle before switching")
        deadline = time.monotonic() + 6
        stable = 0
        while time.monotonic() < deadline:
            levels = run_radio_io_sync(lambda: flex.get_fresh_tx_state(timeout=1.25))
            if (
                levels.get("confirmed") is True
                and levels.get("mox") is False
                and levels.get("interlock_state") in {"READY", "RECEIVE"}
            ):
                stable += 1
                if stable >= 1:
                    break
            else:
                stable = 0
            time.sleep(.2)
        if stable < 1:
            raise HTTPException(409, "Radio transmit state must be confirmed idle before switching")
        bridge = self._legacy().get_bridge_status()
        stats = bridge.get("stats") or {}
        status = stats.get("lastStatus") or {}
        if status.get("transmitting"):
            raise HTTPException(409, "Digital engine is still transmitting")

    def _stop_processes(self, pids: list[int]) -> None:
        identities = dict(self.process_identities)
        for pid in pids:
            self.processes(force_refresh=True)
            if pid not in self.process_identities:
                continue
            if pid not in identities or self.process_identities.get(pid) != identities[pid]:
                raise HTTPException(409, "Digital process identity changed; refusing to stop it")
            result = subprocess.run(
                ["taskkill.exe", "/PID", str(int(pid)), "/T"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            logger.info(
                "Graceful digital process stop pid=%s rc=%s stdout=%r stderr=%r",
                pid,
                result.returncode,
                (result.stdout or "").strip(),
                (result.stderr or "").strip(),
            )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            remaining = {pid for group in self.processes(force_refresh=True).values() for pid in group}
            if not remaining.intersection(pids):
                return
            time.sleep(.25)

        # A responsive Windows GUI can ignore WM_CLOSE (for example while a
        # modal prompt is open).  Escalate only for the exact managed process
        # identities captured above, and only after both the engine heartbeat
        # and the physical radio have just proved RX-idle.  This is deliberately
        # not a name-based kill and cannot run on an active QSO/TX edge.
        current = self.processes(force_refresh=True)
        remaining = {
            pid for group in current.values() for pid in group
            if pid in pids
        }
        for pid in remaining:
            if pid not in identities or self.process_identities.get(pid) != identities[pid]:
                raise HTTPException(409, "Digital process identity changed; refusing forced stop")
        bridge = self._legacy().get_bridge_status()
        status = (bridge.get("stats") or {}).get("lastStatus") or {}
        qso_state = str(status.get("qsoState") or status.get("qso_state") or "").strip().lower()
        if (
            qso_state != "idle"
            or bool(status.get("txEnabled"))
            or bool(status.get("transmitting"))
        ):
            raise HTTPException(409, "Digital engine is not idle; refusing forced stop")
        self._confirm_idle()

        for pid in sorted(remaining):
            # Re-resolve the full path/command/start identity immediately before
            # every forced termination so PID reuse fails closed.
            self.processes(force_refresh=True)
            if self.process_identities.get(pid) != identities.get(pid):
                raise HTTPException(409, "Digital process identity changed; refusing forced stop")
            result = subprocess.run(
                ["taskkill.exe", "/PID", str(int(pid)), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            logger.warning(
                "Forced exact managed digital process stop pid=%s rc=%s stdout=%r stderr=%r",
                pid,
                result.returncode,
                (result.stdout or "").strip(),
                (result.stderr or "").strip(),
            )

        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            still_running = {
                pid for group in self.processes(force_refresh=True).values() for pid in group
            }
            if not still_running.intersection(remaining):
                return
            time.sleep(.25)
        raise HTTPException(409, "Previous digital engine did not exit after exact forced stop; selection unchanged")

    def disarm_planner(self, reason: str = "backend-startup-disarmed") -> dict[str, Any]:
        """Make planner/TX state inert until an explicit operator re-arm.

        Persisted candidates must never resume transmission merely because the
        backend restarted or a provider was selected.  The normal automation
        settings endpoint remains the explicit re-arm path.
        """
        from services.ft8_service import get_ft8_service
        service = get_ft8_service()
        service.set_tx_options(auto_call=False, auto_cq=False)
        controller = service.automation_controller
        controller.settings.enabled = False
        for target in list(controller.targets.values()):
            target.sync_state("skipped")
            target.reason = reason
            controller._persist_target(target)
        controller.targets.clear()
        controller.active_target_key = controller.listen_target_key = None
        controller.pending_return_command = None
        controller.active_qso_state = "idle"
        return {
            "enabled": False,
            "auto_call": bool(service.auto_call_enabled),
            "auto_cq": bool(service.auto_cq_enabled),
            "targets": len(controller.targets),
            "reason": reason,
        }

    def _disable_planner(self) -> None:
        self.disarm_planner("mshv-provider-selected")

    def _startup_readiness(self, provider: str, *, selected_at: float, force_refresh: bool = False) -> dict[str, Any]:
        processes = self.processes(force_refresh=force_refresh)
        try:
            bridge = self._legacy().get_bridge_status()
        except Exception as exc:
            bridge = {"success": False, "error": str(exc)}
        client = bridge.get("client") if isinstance(bridge.get("client"), dict) else {}
        client_id = str(client.get("id") or "")
        try:
            client_age_ms = float(client.get("lastSeenMs"))
        except (TypeError, ValueError):
            client_age_ms = float("inf")
        bridge_healthy = (
            bridge.get("success") is True
            and bridge.get("provider") == provider
            and bridge.get("conflict") is not True
            and client_id in PROVIDER_CLIENT_IDS[provider]
            and 0 <= client_age_ms < 6000
        )
        managed_conflict = any(
            bool(group) for key, group in processes.items()
            if key not in {"none", provider}
        )
        bridge_conflict = bridge.get("conflict") is True
        heartbeat_fresh = True
        if provider == "mshv_auto_dx":
            heartbeat_fresh = (
                self.engine_state_at >= selected_at
                and time.monotonic() - self.engine_state_at < 6
                and self.engine_state.get("provider") == provider
            )
        return {
            "ready": bool(processes[provider]) and not managed_conflict and not self.unmanaged_processes and bridge_healthy and heartbeat_fresh,
            "process_running": bool(processes[provider]),
            "running_pids": processes[provider],
            "bridge_healthy": bridge_healthy,
            "bridge_provider": bridge.get("provider"),
            "client_id": client_id or None,
            "client_last_seen_ms": None if client_age_ms == float("inf") else client_age_ms,
            "heartbeat_fresh": heartbeat_fresh,
            "managed_conflict": managed_conflict,
            "unmanaged_conflict": bool(self.unmanaged_processes),
            "bridge_conflict": bridge_conflict,
        }

    def _wait_for_startup(self, provider: str, *, selected_at: float) -> dict[str, Any]:
        deadline = time.monotonic() + STARTUP_CONFIRM_TIMEOUT_SECONDS
        readiness: dict[str, Any] = {}
        while time.monotonic() < deadline:
            readiness = self._startup_readiness(provider, selected_at=selected_at)
            if readiness["ready"]:
                return readiness
            time.sleep(STARTUP_CONFIRM_INTERVAL_SECONDS)
        # A slow first-run UI/history load may delay UDP and engine-state
        # telemetry even though the exact attested process is still alive.
        # Report that as accepted/starting; it is not TX-ready and does not
        # weaken any station-readiness gate. A dead, conflicting or unowned
        # process remains a hard startup failure.
        readiness = self._startup_readiness(provider, selected_at=selected_at, force_refresh=True)
        if (
            readiness.get("process_running")
            and not readiness.get("managed_conflict")
            and not readiness.get("unmanaged_conflict")
            and not readiness.get("bridge_conflict")
        ):
            return {
                **readiness,
                "accepted": True,
                "starting": True,
                "ready": False,
                "reason": "Owned process is running; bridge/heartbeat confirmation is still pending",
            }
        raise HTTPException(503, {
            "reason": "Digital engine startup was not confirmed before timeout",
            "provider": provider,
            "startup": readiness,
        })

    def select(self, request: dict[str, Any], *, launch: bool = False) -> dict[str, Any]:
        provider = normalize_provider(request.get("provider") or request.get("engine") or selected_provider())
        startup_safety = None
        with self.lock, lifecycle_lock():
            self.clear_station_authorizations("provider-selection")
            preflight = self.preflight(provider)
            if request.get("dryRun"):
                return {**preflight, "dry_run": True, "planner_owner": PROVIDERS[provider]["planner_owner"]}
            if launch and not preflight["success"]:
                raise HTTPException(404, preflight)
            processes = self.processes(force_refresh=True)
            if self.unmanaged_processes:
                raise HTTPException(409, "An unmanaged digital engine is running; close it before selecting an engine")
            if launch and provider != "none":
                if read_json_object(STATE_PATH).get("recovery_tx_off_required"):
                    self.halt()
                self._confirm_idle()
            conflicting_pids = [pid for key, group in processes.items() if key != provider and key != "none" for pid in group]
            if conflicting_pids:
                self.halt()
                self._confirm_idle()
                self._stop_processes(conflicting_pids)
                self.halt()
                self._confirm_idle()
            bridge_result = self._legacy().send_bridge_command("select_provider", {"provider": provider})
            if bridge_result.get("success") is not True:
                raise HTTPException(503, "Bridge did not acknowledge provider selection")
            atomic_write_json(STATE_PATH, {"provider": provider})
            selected_at = time.monotonic()
            if provider == "mshv_auto_dx":
                self._disable_planner()
            elif provider == "wsjtz":
                # Selecting a provider is not an operator re-arm.  A backend
                # restart or an engine switch must leave the planner inert.
                self.disarm_planner("wsjtz-provider-selected-disarmed")
            else:
                self.disarm_planner("digital-engine-disabled")
                self.engine_state = {"provider": "none", "state": "disabled", "enabled": False}
                self.engine_state_at = time.monotonic()
                try:
                    self._legacy().send_bridge_command("reset_client", {})
                except HTTPException:
                    pass
            if launch and provider == "none":
                return {**self.status(), "success": False, "disabled": True, "message": "Digital engines are disabled; select WSJT-Z or MSHV before starting"}
            if launch and not self.processes(force_refresh=True)[provider]:
                if provider == "wsjtz":
                    self._legacy().launch_wsjtz_engine({**request, "_provider_managed": True})
                elif provider == "mshv_auto_dx":
                    # MSHV's generation counter is local to this process and
                    # begins again at one on every launch.  Reset only after
                    # the forced scan proved there is no existing instance.
                    self.reset_station_client_generation("mshv-process-launch")
                    from services.mshv_configuration import stage_mshv_safe_startup
                    startup_safety = stage_mshv_safe_startup()
                    exe = Path(preflight["prerequisites"]["exe"])
                    startup_safety["display_indexes"] = _stage_mshv_display_indexes(exe.parent)
                    from radio_control import config
                    env = os.environ.copy()
                    env["OM0RX_CONTROL_TOKEN"] = str(getattr(config, "CONTROL_TOKEN", "") or "")
                    env["OM0RX_API_BASE"] = f"http://127.0.0.1:{getattr(config, 'BACKEND_PORT', 8080)}"
                    env["OM0RX_UDP_PORT"] = str(getattr(config, "WSJTX_UDP_PORT", 2237))
                    subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    # The pre-launch force scan intentionally observed no
                    # process. Invalidate that snapshot so readiness sees the
                    # newly created PID immediately, including on CIM fallback.
                    self._invalidate_process_scan()
            startup = self._wait_for_startup(provider, selected_at=selected_at) if launch and provider != "none" else None
            response = self.status()
            if startup is not None:
                response["startup"] = startup
            if startup_safety is not None:
                response["startup_safety"] = startup_safety
            return response

    def stop(self) -> dict[str, Any]:
        with self.lock, lifecycle_lock():
            self.clear_station_authorizations("engine-stop")
            pids = [pid for group in self.processes(force_refresh=True).values() for pid in group]
            idle_confirmed = False
            try:
                self.halt()
                self._confirm_idle()
                idle_confirmed = True
            except HTTPException:
                if pids:
                    raise HTTPException(409, "Engine remains running: transmit-off could not be freshly confirmed; verify radio RX before stopping")
            self._stop_processes(pids)
            self.reset_station_client_generation("engine-process-stopped")
            try:
                self.halt()
                self._confirm_idle()
                idle_confirmed = True
            except HTTPException:
                idle_confirmed = False
            atomic_write_json(STATE_PATH, {"provider": selected_provider(), "recovery_tx_off_required": not idle_confirmed})
            try:
                self._legacy().send_bridge_command("reset_client", {})
            except HTTPException:
                if pids:
                    raise
            return {**self.status(), "success": idle_confirmed or not pids, "recovery_tx_off_required": not idle_confirmed}


_service = DigitalEngineService()


def get_digital_engine_service() -> DigitalEngineService:
    return _service


def verify_station_readback(
    levels,
    desired,
    devices=None,
    *,
    frequency_mhz=None,
    mode=None,
    rfpower_w=None,
    verify_tx_state=True,
):
    if verify_tx_state and (levels.get("mox") is not False or levels.get("interlock_state") not in {"READY", "RECEIVE"}):
        return "radio-readback-not-idle"
    if desired and (levels.get("rx_ant") != desired["rx"] or levels.get("tx_ant") != desired["tx"]):
        return "radio-antenna-readback-mismatch"
    if frequency_mhz is not None:
        try:
            if abs(float(levels.get("freq")) - float(frequency_mhz)) > .000010:
                return "radio-frequency-readback-mismatch"
        except (TypeError, ValueError):
            return "radio-frequency-readback-missing"
    if mode and str(levels.get("mode") or "").upper() != str(mode).upper():
        return "radio-mode-readback-mismatch"
    if rfpower_w is not None:
        try:
            if int(levels.get("rfpower")) != int(rfpower_w):
                return "radio-rfpower-readback-mismatch"
        except (TypeError, ValueError):
            return "radio-rfpower-readback-missing"
    devices = devices or {}
    for name, expected in devices.items():
        status = expected["status"]
        if (
            status.get("connected") is not True
            or status.get("responsive") is not True
            or status.get("error")
            or status.get("missing_fields")
            or status.get("band") != expected["band"]
            or status.get("power") is not True
        ):
            return f"{name}-readback-not-ready"
        if name == "kpa500":
            required = {"operate", "fault", "output_power_w", "current"}
            if not required.issubset(status):
                return "kpa500-readback-incomplete"
            fault = str(status.get("fault") or "").strip().upper()
            try:
                output_power = float(status["output_power_w"])
                current = float(status["current"])
            except (TypeError, ValueError):
                return "kpa500-fault-or-transmit-readback"
            if fault not in {"0", "00", "000", "NONE", "OK"} or status.get("operate") is not expected.get("operate", True) or output_power != 0 or current != 0:
                return "kpa500-fault-or-transmit-readback"
        if name == "kat500":
            required = {"mode", "antenna", "frequency_khz", "tuning", "fault"}
            if not required.issubset(status):
                return "kat500-readback-incomplete"
            try:
                frequency_khz = round(float(status["frequency_khz"]))
            except (TypeError, ValueError):
                return "kat500-readback-incomplete"
            if (
                status.get("tuning") is not False
                or status.get("mode") not in {"auto", "manual"}
                or str(status.get("fault") or "").strip() != "0"
                or status.get("antenna") != expected["antenna"]
                or frequency_khz != round(float(expected["frequency_khz"]))
            ):
                return "kat500-frequency-antenna-or-tuning-readback"
    return None


def register_digital_endpoints(app) -> None:
    async def watch_engine_state():
        while True:
            await asyncio.sleep(2)
            provider = selected_provider()
            conflict = False
            owner = runtime_owner_status()
            owner_lost = owner.get("success") is not True
            try:
                processes = await asyncio.to_thread(_service.processes)
                if provider == "none":
                    conflict = any(bool(group) for key, group in processes.items() if key != "none") or bool(_service.unmanaged_processes)
                else:
                    conflict = any(bool(group) for key, group in processes.items() if key not in {provider, "none"}) or bool(_service.unmanaged_processes)
            except Exception:
                conflict = True
            if conflict or owner_lost:
                fault = "runtime-owner-lost" if owner_lost else "engine-conflict"
                _service.engine_state = {**_service.engine_state, "enabled": False, "state": fault}
                _service.clear_station_authorizations(fault)
                try:
                    await asyncio.to_thread(_service.halt)
                except Exception:
                    pass  # State remains faulted; a fresh readiness check is needed.

    def ensure_watchdog():
        if _service.watchdog_task is None or _service.watchdog_task.done():
            _service.watchdog_task = asyncio.create_task(watch_engine_state())

    _service.ensure_watchdog = ensure_watchdog
    app.router.add_event_handler("startup", ensure_watchdog)

    @app.get("/api/digital/logging/provisional")
    async def provisional_status():
        from services.digital_logging import provisional_health
        return {"success": True, **await asyncio.to_thread(provisional_health)}

    @app.post("/api/digital/logging/reconcile")
    async def reconcile_pending():
        from services.digital_logging import reconcile_provisional
        return await reconcile_provisional(_service._legacy())

    @app.post("/api/digital/engine-state")
    async def engine_state(request: dict[str, Any]):
        owner = runtime_owner_status()
        if owner.get("success") is not True:
            _service.clear_station_authorizations(f"runtime-owner-invalid:{owner.get('reason')}")
            raise HTTPException(409, "Managed runtime owner is not verified")
        if request.get("provider") != "mshv_auto_dx" or selected_provider() != "mshv_auto_dx":
            raise HTTPException(409, "Engine telemetry does not match selected provider")
        _service.engine_state = {
            key: request.get(key)
            for key in (
                "provider", "state", "enabled", "desired_enabled", "target_call",
                "frequency_hz", "timestamp", "autodx_config", "autodx_status",
            )
        }
        from services.mshv_observability import record_selection
        await asyncio.to_thread(record_selection, _service.engine_state.get("autodx_status") or {})
        _service.engine_state_at = time.monotonic()
        if _service.watchdog_task is None or _service.watchdog_task.done():
            _service.watchdog_task = asyncio.create_task(watch_engine_state())
        return {"success": True}

    @app.get("/api/digital/status")
    @app.get("/api/digital/config")
    async def status():
        return await asyncio.to_thread(_service.status)

    @app.get("/api/digital/preflight")
    async def preflight(provider: str = "wsjtz", engine: str | None = None):
        return await asyncio.to_thread(_service.preflight, engine or provider)

    @app.get("/api/digital/mshv-settings")
    async def mshv_settings():
        return await asyncio.to_thread(_service.mshv_settings)

    @app.get("/api/digital/mshv-history")
    async def mshv_history(request: Request):
        from services.mshv_history import history_status, history_status_etag
        payload = await asyncio.to_thread(history_status)
        etag = history_status_etag(payload)
        headers = {
            "Cache-Control": "no-store, max-age=0",
            "ETag": etag,
            "X-OM0RX-History-Generated-At": str(payload.get("generated_at") or ""),
            "X-OM0RX-History-Max-Age": str(payload.get("max_age_seconds") or 0),
        }
        if request.headers.get("if-none-match", "").strip() == etag:
            return Response(status_code=304, headers=headers)
        return JSONResponse(content=payload, headers=headers)

    @app.get("/api/digital/mshv-history/reconcile-preview")
    async def mshv_history_reconcile_preview():
        from services.mshv_history import reconcile_source_backed_pending
        payload = await asyncio.to_thread(reconcile_source_backed_pending, apply=False)
        return JSONResponse(content=payload, headers={"Cache-Control": "no-store, max-age=0"})

    @app.post("/api/digital/mshv-history/reconcile")
    async def mshv_history_reconcile(request: dict[str, Any]):
        if request.get("confirm_source_backed") is not True:
            raise HTTPException(422, "confirm_source_backed=true is required")
        payload = await asyncio.to_thread(_service.reconcile_mshv_history)
        return JSONResponse(content=payload, headers={"Cache-Control": "no-store, max-age=0"})

    @app.get("/api/digital/mshv-daily-summaries")
    async def mshv_daily_summaries(limit: int = 31):
        from services.mshv_observability import daily_summaries
        payload = await asyncio.to_thread(daily_summaries, limit=limit)
        return JSONResponse(content=payload, headers={"Cache-Control": "no-store, max-age=0"})

    @app.post("/api/digital/mshv-settings")
    async def save_mshv_settings(request: dict[str, Any]):
        return await asyncio.to_thread(_service.update_mshv_settings, request)

    @app.post("/api/digital/select")
    async def select(request: dict[str, Any]):
        ensure_watchdog()
        return await asyncio.to_thread(_service.select, request)

    @app.post("/api/digital/start")
    async def start(request: dict[str, Any] = {}):
        ensure_watchdog()
        result = await asyncio.to_thread(_service.select, request, launch=True)
        startup = result.get("startup") if isinstance(result, dict) else None
        if isinstance(startup, dict) and startup.get("starting") is True:
            return JSONResponse(status_code=202, content=result)
        return result

    @app.post("/api/digital/stop")
    async def stop():
        return await asyncio.to_thread(_service.stop)

    @app.post("/api/digital/restart")
    async def restart(request: dict[str, Any] = {}):
        ensure_watchdog()
        await asyncio.to_thread(_service.stop)
        result = await asyncio.to_thread(_service.select, request, launch=True)
        startup = result.get("startup") if isinstance(result, dict) else None
        if isinstance(startup, dict) and startup.get("starting") is True:
            return JSONResponse(status_code=202, content=result)
        return result

    @app.post("/api/digital/halt")
    @app.post("/api/digital/halt-tx")
    async def halt():
        return await asyncio.to_thread(_service.halt)

    @app.post("/api/digital/station-ready")
    async def station_ready(request: dict[str, Any]):
        from services.radio import get_radio_command_lock, get_radio_instance, run_radio_io
        from radio_control.flex_radio import FlexCtl
        request_id = str(request.get("request_id") or "")
        phase = str(request.get("phase") or "").lower()
        result = {
            "ready": False, "prepared": False, "transmit_ready": False,
            "request_id": request_id, "phase": phase,
        }
        failure_stage = "validate-request"
        try:
            owner = runtime_owner_status()
            if owner.get("success") is not True:
                _service.clear_station_authorizations(f"runtime-owner-invalid:{owner.get('reason')}")
                return {**result, "reason": "runtime-owner-invalid"}
            if request.get("provider") != "mshv_auto_dx" or selected_provider() != "mshv_auto_dx" or not request_id or phase not in {"prepare", "final"}:
                return {**result, "reason": "provider-or-request-invalid"}
            mhz = float(request.get("frequency_hz", 0)) / 1_000_000
            band = FlexCtl.band_for_frequency(mhz)
            if not band or str(request.get("band")) != band:
                return {**result, "reason": "frequency-band-policy-rejected"}
            mode = str(request.get("mode") or "DIGU").strip().upper()
            if mode != "DIGU":
                return {**result, "reason": "mode-policy-rejected"}
            try:
                native_generation = int(request.get("authorization_generation"))
            except (TypeError, ValueError):
                return {**result, "reason": "native-generation-invalid"}
            prepare_epoch = None
            if phase == "prepare":
                failure_stage = "begin-authorization"
                begun, begin_reason, prepare_epoch = _service.begin_station_preparation(
                    native_generation,
                )
                if not begun:
                    return {**result, "reason": begin_reason}
            flex = get_radio_instance()
            if flex is None or getattr(flex, "current_mox", None) is not False or not getattr(flex, "sock", None):
                return {**result, "reason": "radio-not-confirmed-idle"}
            failure_stage = "confirm-idle"
            await asyncio.wait_for(asyncio.to_thread(_service._confirm_idle), timeout=3)
            failure_stage = "scan-processes"
            processes = await asyncio.to_thread(_service.processes)
            if processes["wsjtz"] or _service.unmanaged_processes:
                return {**result, "reason": "conflicting-digital-engine"}
            expected = flex.desired_antennas_for_current_config(mhz)
            from radio_control import config
            from radio_control.station_policy import resolve_amplifier_policy
            amplifier_policy = resolve_amplifier_policy(config, band, mode)
            if str(getattr(config, "DIGITAL_KPA_POLICY", "operate") or "").strip().lower() not in {"operate", "standby"}:
                return {**result, "reason": "invalid-kpa-operation-policy"}
            effective_kpa_policy = amplifier_policy.effective_mode
            failure_stage = "bind-process-client"
            process_binding = await asyncio.to_thread(_service.station_process_binding)
            binding = {
                **process_binding,
                "frequency_hz": int(round(mhz * 1_000_000)),
                "band": band,
                "mode": mode,
                "rx_ant": str(expected.get("rx") or ""),
                "tx_ant": str(expected.get("tx") or ""),
                "kpa_policy": effective_kpa_policy,
                "rf_drive_w": amplifier_policy.active_drive_w,
                "kat_antenna": int((getattr(config, "KAT500_ANTENNA_POLICY", {}) or {}).get(band, 0) or 0),
                "native_generation": native_generation,
            }
            final_epoch = None
            final_native_generation = None
            if phase == "final":
                failure_stage = "consume-preparation"
                nonce_ok, nonce_reason, final_epoch, final_native_generation = _service.consume_station_preparation(
                    str(request.get("prepare_nonce") or ""), binding,
                )
                if not nonce_ok:
                    return {**result, "reason": nonce_reason}
            radio_lock = get_radio_command_lock()

            async def confirm_receive_before_route_change() -> dict[str, Any] | None:
                fresh = await asyncio.wait_for(
                    run_radio_io(lambda: flex.get_fresh_tx_state(timeout=1.5)),
                    timeout=3,
                )
                interlock = str(fresh.get("interlock_state") or "").upper()
                if (
                    fresh.get("confirmed") is not True
                    or fresh.get("mox") is not False
                    or interlock not in {"READY", "RECEIVE"}
                ):
                    return None
                return fresh

            if phase == "prepare":
                # Hold target-band routing across old-frequency background
                # polls until MSHV completes CAT QSY and asks for final proof.
                failure_stage = "prepare-flex-route"
                async with radio_lock:
                    if await confirm_receive_before_route_change() is None:
                        return {**result, "reason": "radio-fresh-tx-state-unavailable"}
                    flex.pending_external_frequency = mhz
                    flex.pending_external_frequency_until = time.time() + 20
                    ready = await asyncio.wait_for(
                        run_radio_io(
                            lambda: flex.enforce_antenna_policy(
                                mhz,
                                reason="mshv-interlock-prepare",
                            )
                        ),
                        timeout=2,
                    )
                if ready is not True:
                    flex.pending_external_frequency_until = 0
                    return {**result, "reason": "antenna-preparation-failed"}
            else:
                # First prove CAT has reached the requested frequency.  This
                # read is deliberately non-mutating and cannot approve stale
                # old-band state or silently fix the evidence being checked.
                failure_stage = "verify-final-flex-route"
                async with radio_lock:
                    observed = await asyncio.wait_for(
                        run_radio_io(
                            lambda: flex.get_current_levels(
                                timeout=.5,
                                apply_antenna_policy=False,
                            )
                        ),
                        timeout=1,
                    )
                    observed_reason = verify_station_readback(
                        observed,
                        None,
                        frequency_mhz=mhz,
                        mode="DIGU",
                        verify_tx_state=False,
                    )
                    if observed_reason:
                        return {**result, "reason": observed_reason}
                    if await confirm_receive_before_route_change() is None:
                        return {**result, "reason": "radio-fresh-tx-state-unavailable"}
                    ready = await asyncio.wait_for(
                        run_radio_io(
                            lambda: flex.enforce_antenna_policy(
                                mhz,
                                reason="mshv-interlock-final",
                            )
                        ),
                        timeout=2,
                    )
                if ready is not True:
                    return {**result, "reason": "antenna-preparation-failed"}
            devices = {}
            if getattr(config, "KPA500_ENABLED", False) or getattr(config, "KAT500_ENABLED", False):
                from backend.core import context
                from radio_control.elecraft import get_elecraft_manager

                manager = get_elecraft_manager()
                coordinator = getattr(context, "station_coordinator", None)
                if coordinator is None:
                    return {**result, "reason": "station-coordinator-unavailable"}
                policy = effective_kpa_policy
                if phase == "prepare":
                    failure_stage = "accessories-standby"
                    await asyncio.wait_for(
                        coordinator.ensure_external_digital_standby(), timeout=12
                    )
                else:
                    failure_stage = "prepare-accessory-route"
                    await asyncio.wait_for(
                        coordinator.prepare_external_digital_route(
                            mhz,
                            amplifier_operate=policy == "operate",
                        ),
                        timeout=30,
                    )
                    failure_stage = "refresh-accessory-readback"
                    status = await asyncio.wait_for(manager.refresh_status(), timeout=8)
                    if time.time() - float(status.get("updated_at", 0)) > 3:
                        return {**result, "reason": "accessory-readback-stale"}
                    for name, enabled in (
                        ("kpa500", "KPA500_ENABLED"),
                        ("kat500", "KAT500_ENABLED"),
                    ):
                        if getattr(config, enabled, False):
                            devices[name] = {
                                "status": status.get(name, {}),
                                "band": band,
                                "frequency_khz": mhz * 1000,
                                "antenna": int(manager.antenna_policy.get(band, 1)),
                                "operate": policy == "operate",
                            }
            elif phase == "final":
                failure_stage = "set-barefoot-drive"
                async with radio_lock:
                    if await confirm_receive_before_route_change() is None:
                        return {**result, "reason": "radio-not-confirmed-idle"}
                    drive_set = await asyncio.wait_for(
                        run_radio_io(
                            lambda: flex.set_rf_power(amplifier_policy.active_drive_w)
                        ),
                        timeout=3,
                    )
                if drive_set is not True:
                    return {**result, "reason": "radio-rfpower-command-rejected"}
            reason = None
            if phase == "final":
                # Final is the sole transmit-authorizing proof.  Keep its exact
                # combined FLEX/KPA/KAT readback, but do not repeat the same
                # radio-lock proof during the RX-only prepare phase after
                # enforce_antenna_policy and exact KPA standby already passed.
                failure_stage = "verify-combined-readback"
                async with radio_lock:
                    levels = await asyncio.wait_for(
                        run_radio_io(
                            lambda: flex.get_current_levels(
                                timeout=.5,
                                apply_antenna_policy=False,
                            )
                        ),
                        timeout=1,
                    )
                    fresh_tx = await asyncio.wait_for(
                        run_radio_io(lambda: flex.get_fresh_tx_state(timeout=1.5)),
                        timeout=3,
                    )
                if not fresh_tx.get("confirmed"):
                    return {**result, "reason": "radio-fresh-tx-state-unavailable"}
                # The long-lived station socket remains authoritative for
                # frequency, mode, antennas and levels.  SmartSDR does not
                # always replay TX state when that socket re-subscribes.
                levels = {
                    **levels,
                    "mox": fresh_tx.get("mox"),
                    "interlock_state": fresh_tx.get("interlock_state"),
                }
                reason = verify_station_readback(
                    levels,
                    expected,
                    devices,
                    frequency_mhz=mhz,
                    mode="DIGU",
                    rfpower_w=amplifier_policy.active_drive_w,
                )
            if reason is None and phase == "final":
                flex.pending_external_frequency = None
                flex.pending_external_frequency_until = 0
            response = {
                **result,
                "ready": reason is None,
                "prepared": reason is None,
                "transmit_ready": reason is None and phase == "final",
                "station_policy": amplifier_policy.as_dict(),
                "reason": reason or ("station-ready" if phase == "final" else "station-prepared"),
            }
            owner = runtime_owner_status()
            if owner.get("success") is not True:
                _service.clear_station_authorizations(f"runtime-owner-invalid:{owner.get('reason')}")
                return {**result, "reason": "runtime-owner-invalid"}
            if reason is None and phase == "prepare":
                failure_stage = "issue-preparation"
                prepare_nonce, ttl_ms = _service.create_station_preparation(
                    binding,
                    expected_epoch=prepare_epoch,
                    native_generation=native_generation,
                )
                response.update({"prepare_nonce": prepare_nonce, "prepare_expires_in_ms": ttl_ms})
            elif reason is None and phase == "final":
                failure_stage = "issue-permit"
                permit_nonce, ttl_ms = _service.create_station_permit(
                    binding,
                    expected_epoch=int(final_epoch),
                    native_generation=int(final_native_generation),
                )
                response.update({"permit_nonce": permit_nonce, "permit_expires_in_ms": ttl_ms})
            return response
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            _service._station_audit(
                "station-ready-failed",
                request_id=request_id,
                phase=phase,
                failure_stage=failure_stage,
                exception_type=type(exc).__name__,
                detail=str(detail if detail is not None else exc),
            )
            timeout_reason = (
                f"{failure_stage}-timeout" if isinstance(exc, TimeoutError)
                else "station-preparation-failed"
            )
            return {
                **result,
                "reason": timeout_reason,
                "failure_stage": failure_stage,
            }

    @app.post("/api/digital/station-permit/consume")
    async def consume_station_permit(request: dict[str, Any]):
        """Authoritatively validate and consume a permit before a PTT edge.

        This path is deliberately bounded and non-mutating.  Slow station
        preparation remains in the RX-period prepare/final workflow; the PTT
        edge only accepts fresh process/client, Flex and cached accessory
        evidence that still matches the issued permit.
        """
        from services.radio import get_radio_command_lock, get_radio_instance, run_radio_io
        from radio_control.flex_radio import FlexCtl
        from radio_control import config

        started = time.monotonic()
        result = {"success": False, "reason": "permit-consume-failed"}
        nonce = str(request.get("permit_nonce") or "")
        def rejected(reason: str) -> dict[str, Any]:
            _service.clear_station_authorizations(f"permit-consume-rejected:{reason}")
            _service._station_audit(
                "permit-consume-rejected",
                nonce=nonce,
                reason=reason,
                path=str(request.get("path") or ""),
                frequency_hz=int(request.get("frequency_hz") or 0),
                latency_ms=round((time.monotonic() - started) * 1000, 1),
            )
            return {**result, "reason": reason}
        try:
            async with asyncio.timeout(STATION_PTT_CONSUME_TIMEOUT_SECONDS):
                owner = runtime_owner_status()
                if owner.get("success") is not True:
                    return rejected("runtime-owner-invalid")
                if request.get("provider") != "mshv_auto_dx" or selected_provider() != "mshv_auto_dx":
                    return rejected("provider-invalid")
                frequency_hz = int(request.get("frequency_hz") or 0)
                mhz = frequency_hz / 1_000_000
                band = FlexCtl.band_for_frequency(mhz)
                mode = str(request.get("mode") or "").strip().upper()
                try:
                    native_generation = int(request.get("authorization_generation"))
                except (TypeError, ValueError):
                    return rejected("native-generation-invalid")
                if not band or mode != "DIGU":
                    return rejected("route-invalid")
                if (
                    _service.engine_state.get("provider") != "mshv_auto_dx"
                    or time.monotonic() - _service.engine_state_at >= 6
                ):
                    return rejected("engine-heartbeat-stale")

                process_binding = await asyncio.to_thread(
                    _service.station_process_binding,
                    force_refresh=False,
                )
                flex = get_radio_instance()
                if flex is None or not getattr(flex, "sock", None):
                    return rejected("radio-unavailable")
                expected = flex.desired_antennas_for_current_config(mhz)
                from radio_control.station_policy import resolve_amplifier_policy
                amplifier_policy = resolve_amplifier_policy(config, band, mode)
                binding = {
                    **process_binding,
                    "frequency_hz": frequency_hz,
                    "band": band,
                    "mode": mode,
                    "rx_ant": str(expected.get("rx") or ""),
                    "tx_ant": str(expected.get("tx") or ""),
                    "kpa_policy": amplifier_policy.effective_mode,
                    "rf_drive_w": amplifier_policy.active_drive_w,
                    "kat_antenna": int(
                        (getattr(config, "KAT500_ANTENNA_POLICY", {}) or {}).get(band, 0) or 0
                    ),
                    "native_generation": native_generation,
                }
                radio_lock = get_radio_command_lock()
                async with radio_lock:
                    levels = await asyncio.wait_for(
                        run_radio_io(
                            lambda: flex.get_current_levels(
                                timeout=.25,
                                apply_antenna_policy=False,
                            )
                        ),
                        timeout=.5,
                    )
                    fresh_tx = await asyncio.wait_for(
                        run_radio_io(lambda: flex.get_fresh_tx_state(timeout=.35)),
                        timeout=.65,
                    )
                if fresh_tx.get("confirmed") is not True:
                    return rejected("radio-fresh-tx-state-unavailable")
                levels = {
                    **levels,
                    "mox": fresh_tx.get("mox"),
                    "interlock_state": fresh_tx.get("interlock_state"),
                }

                devices = {}
                if getattr(config, "KPA500_ENABLED", False) or getattr(config, "KAT500_ENABLED", False):
                    from radio_control.elecraft import get_elecraft_manager

                    manager = get_elecraft_manager()
                    status = manager.snapshot()
                    try:
                        age = time.time() - float(status.get("updated_at", 0))
                    except (TypeError, ValueError):
                        age = float("inf")
                    if not 0 <= age <= STATION_ACCESSORY_CACHE_MAX_AGE_SECONDS:
                        return rejected("accessory-readback-stale")
                    if getattr(config, "KPA500_ENABLED", False):
                        devices["kpa500"] = {
                            "status": status.get("kpa500", {}),
                            "band": band,
                            "operate": binding["kpa_policy"] == "operate",
                        }
                    if getattr(config, "KAT500_ENABLED", False):
                        devices["kat500"] = {
                            "status": status.get("kat500", {}),
                            "band": band,
                            "frequency_khz": mhz * 1000,
                            "antenna": binding["kat_antenna"],
                        }
                reason = verify_station_readback(
                    levels,
                    expected,
                    devices,
                    frequency_mhz=mhz,
                    mode=mode,
                    rfpower_w=amplifier_policy.active_drive_w,
                )
                if reason:
                    return rejected(reason)
                owner = runtime_owner_status()
                if owner.get("success") is not True:
                    return rejected("runtime-owner-invalid")
                consumed, reason = _service.consume_station_permit(
                    nonce,
                    binding,
                )
                if not consumed:
                    return rejected(reason)
                _service._station_audit(
                    "ptt-edge-authorized",
                    nonce=nonce,
                    path=str(request.get("path") or ""),
                    frequency_hz=frequency_hz,
                    authorization_epoch=_service.station_authorization_epoch,
                )
                return {
                    "success": True,
                    "reason": reason,
                    "authorization_epoch": _service.station_authorization_epoch,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                }
        except TimeoutError:
            _service.clear_station_authorizations("permit-consume-timeout")
            _service._station_audit(
                "permit-consume-timeout",
                nonce=nonce,
                latency_ms=round((time.monotonic() - started) * 1000, 1),
            )
            return {**result, "reason": "permit-consume-timeout"}
        except HTTPException as exc:
            return rejected(str(exc.detail))
        except Exception as exc:
            _service.clear_station_authorizations("permit-consume-error")
            _service._station_audit(
                "permit-consume-error",
                nonce=nonce,
                error=type(exc).__name__,
            )
            return result

    @app.post("/api/digital/station-audit")
    async def station_audit(request: dict[str, Any]):
        event = str(request.get("event") or "").strip().lower()
        if request.get("provider") != "mshv_auto_dx" or selected_provider() != "mshv_auto_dx":
            return {"success": False, "reason": "provider-invalid"}
        if event == "authorization-invalidated":
            try:
                native_generation = int(request.get("authorization_generation"))
            except (TypeError, ValueError):
                native_generation = -1
            _, invalidation_result = _service.apply_native_invalidation(
                str(request.get("reason") or "native-invalidation"),
                native_generation,
            )
        else:
            invalidation_result = "not-an-invalidation"
        _service._station_audit(
            "native-event",
            native_event=event or "unspecified",
            request_id=str(request.get("request_id") or ""),
            reason=str(request.get("reason") or ""),
            frequency_hz=int(request.get("frequency_hz") or 0),
            path=str(request.get("path") or ""),
            authorization_generation=request.get("authorization_generation"),
        )
        return {"success": True, "reason": invalidation_result}
