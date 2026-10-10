"""Executable ownership tests; no application services or radio are started."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import _bootstrap  # noqa: F401
from fastapi import FastAPI
from fastapi.testclient import TestClient
from radio_control.runtime_owner import query_tcp_listener_pids, runtime_owner_status


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "scripts" / "start" / "runtime_owner.ps1"


def identity(pid: int, role: str) -> dict:
    return {
        "role": role,
        "pid": pid,
        "executable_path": rf"C:\runtime\{role}.exe",
        "creation_time_filetime": pid * 1000,
    }


def write_manifest(path: Path, owner_id: str = "owner-a") -> dict:
    manifest = {
        "schema": 1,
        "owner_id": owner_id,
        "state": "active",
        "supervisor": identity(10, "supervisor"),
        "backend": identity(20, "backend"),
        "bridge": identity(30, "bridge"),
        "ports": {"backend": 8080, "bridge_ws": 8091, "bridge_command": 8092},
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def resolver(manifest: dict, missing: set[int] | None = None):
    missing = missing or set()
    values = {int(manifest[role]["pid"]): manifest[role] for role in ("supervisor", "backend", "bridge")}

    def resolve(pid: int):
        if pid in missing:
            return None
        return values.get(pid)

    return resolve


def listener_resolver(manifest: dict, overrides: dict[int, set[int] | None] | None = None):
    values = {
        8080: {int(manifest["backend"]["pid"])},
        8091: {int(manifest["bridge"]["pid"])},
        8092: {int(manifest["bridge"]["pid"])},
    }
    values.update(overrides or {})
    return lambda port: values.get(int(port), set())


def enable_managed_runtime(monkeypatch: pytest.MonkeyPatch, owner_id: str = "owner-a") -> None:
    monkeypatch.setenv("APP_LIFECYCLE_SUPERVISOR", "1")
    monkeypatch.setenv("OM0RX_RUNTIME_OWNER_ID", owner_id)
    monkeypatch.setenv("BACKEND_PORT", "8080")


def test_exact_owner_manifest_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "runtime_owner.json"
    manifest = write_manifest(path)
    enable_managed_runtime(monkeypatch)

    status = runtime_owner_status(
        path=path,
        expected_backend_pid=20,
        process_identity=resolver(manifest),
        listener_owners=listener_resolver(manifest),
    )

    assert status["success"] is True
    assert status["owner_id"] == "owner-a"


def test_wrapper_loss_revokes_backend_authorization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "runtime_owner.json"
    manifest = write_manifest(path)
    enable_managed_runtime(monkeypatch)

    status = runtime_owner_status(
        path=path,
        expected_backend_pid=20,
        process_identity=resolver(manifest, {10}),
        listener_owners=listener_resolver(manifest),
    )

    assert status == {"success": False, "managed": True, "reason": "supervisor-process-missing"}


def test_orphan_children_never_count_as_owned_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "runtime_owner.json"
    manifest = write_manifest(path)
    enable_managed_runtime(monkeypatch)

    # Backend and bridge still exist, but their supervisor has gone away.
    resolve = resolver(manifest, {10})
    assert resolve(20) and resolve(30)
    assert runtime_owner_status(
        path=path,
        expected_backend_pid=20,
        process_identity=resolve,
        listener_owners=listener_resolver(manifest),
    )["success"] is False


def test_parallel_owner_id_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "runtime_owner.json"
    manifest = write_manifest(path, owner_id="owner-a")
    enable_managed_runtime(monkeypatch, owner_id="owner-b")

    status = runtime_owner_status(
        path=path,
        expected_backend_pid=20,
        process_identity=resolver(manifest),
        listener_owners=listener_resolver(manifest),
    )

    assert status["reason"] == "owner-id-mismatch"


@pytest.mark.parametrize(
    ("port", "owners"),
    [
        (8080, {30}),
        (8091, set()),
        (8092, {30, 40}),
        (8092, None),
    ],
)
def test_listener_owner_mismatch_or_query_failure_revokes_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    port: int,
    owners: set[int] | None,
):
    path = tmp_path / "runtime_owner.json"
    manifest = write_manifest(path)
    enable_managed_runtime(monkeypatch)

    status = runtime_owner_status(
        path=path,
        expected_backend_pid=20,
        process_identity=resolver(manifest),
        listener_owners=listener_resolver(manifest, {port: owners}),
    )

    assert status["success"] is False
    expected = "listener-query-failed" if owners is None else "listener-owner-mismatch"
    assert status["reason"] == f"{expected}:{port}"


@pytest.mark.skipif(os.name != "nt", reason="Windows IP Helper listener query")
def test_native_listener_query_returns_exact_current_pid():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = int(listener.getsockname()[1])
        assert query_tcp_listener_pids(port) == {os.getpid()}
    finally:
        listener.close()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell ownership lock is Windows-specific")
def test_exclusive_owner_lock_rejects_parallel_acquire_and_recovers(tmp_path: Path):
    helper = str(HELPERS).replace("'", "''")
    lock_path = str(tmp_path / "runtime_owner.lock").replace("'", "''")
    script = (
        f". '{helper}'; $first = Enter-RuntimeOwnerLock -Path '{lock_path}'; "
        "$rejected = $false; try { $second = Enter-RuntimeOwnerLock -Path '"
        + lock_path
        + "' } catch { $rejected = $_.Exception.Message -like '*parallel supervisors are forbidden*' }; "
        "if (-not $rejected) { exit 2 }; $first.Dispose(); "
        f"$third = Enter-RuntimeOwnerLock -Path '{lock_path}'; $third.Dispose(); Write-Output 'lock-contract-ok'"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "lock-contract-ok" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="PowerShell owner manifest is Windows-specific")
def test_owner_manifest_writer_replaces_atomically_and_validates_identity(tmp_path: Path):
    helper = str(HELPERS).replace("'", "''")
    path = str(tmp_path / "runtime_owner.json").replace("'", "''")
    script = (
        f". '{helper}'; $self = Get-Process -Id $PID; "
        "$ports = @{backend=18080;bridge_ws=18091;bridge_command=18092;bridge_tcp=18166;bridge_udp=12237}; "
        f"Write-RuntimeOwnerManifest -Path '{path}' -OwnerId 'owner-test' -State 'starting' -Supervisor $self -Backend $null -Bridge $null -Ports $ports | Out-Null; "
        f"Write-RuntimeOwnerManifest -Path '{path}' -OwnerId 'owner-test' -State 'active' -Supervisor $self -Backend $self -Bridge $self -Ports $ports | Out-Null; "
        f"if (-not (Test-RuntimeOwnerManifest -Path '{path}' -OwnerId 'owner-test')) {{ exit 3 }}; Write-Output 'manifest-contract-ok'"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "manifest-contract-ok" in result.stdout
    assert not list(tmp_path.glob("*.tmp"))


def test_launchers_use_direct_children_and_complete_port_contract():
    for relative in ("start_all.ps1", "scripts/start/start_services_only.ps1"):
        text = (ROOT / relative).read_text(encoding="utf-8-sig")
        assert "Start-Process powershell" not in text
        assert "'-m', 'uvicorn'" in text
        assert "'--app-dir', $ProjectRoot" in text
        assert "WSJTX_COMMAND_PORT = '8092'" in text
        assert "Enter-RuntimeOwnerLock" in text
        assert "Write-RuntimeOwnerManifest" in text
        cleanup = text[text.rindex("finally {") :]
        assert cleanup.index("if ($RuntimeOwnerLock)") < cleanup.index("Stop-KnownRuntimePorts")
        assert "Runtime ownership was not acquired; existing OM0RX processes were left untouched." in cleanup


@pytest.mark.skipif(os.name != "nt", reason="PowerShell cleanup contract is Windows-specific")
def test_start_cleanup_leaves_real_external_sdc_listener_untouched():
    listener: socket.socket | None = None
    try:
        candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            candidate.bind(("127.0.0.1", 12166))
            candidate.listen(1)
            listener = candidate
        except OSError:
            candidate.close()  # An actual external SDC listener may already own 12166.

        helper = str(HELPERS).replace("'", "''")
        script = (
            f". '{helper}'; "
            "$before = @(Get-NetTCPConnection -LocalPort 12166 -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique | Sort-Object); "
            "$visited = [System.Collections.Generic.List[int]]::new(); "
            "Invoke-RuntimePortCleanup -BackendPort 18080 -StopPort { param($port) $visited.Add([int]$port) | Out-Null }; "
            "$after = @(Get-NetTCPConnection -LocalPort 12166 -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique | Sort-Object); "
            "[ordered]@{before=@($before);after=@($after);visited=@($visited)} | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        proof = json.loads(result.stdout.strip().splitlines()[-1])
        assert proof["before"], "test requires a real listener owner on TCP 12166"
        assert proof["after"] == proof["before"]
        assert proof["visited"] == [18080, 8080, 8091, 8092]
        assert 12166 not in proof["visited"]
        assert 2237 not in proof["visited"]
        if listener is not None:
            assert os.getpid() in proof["after"]
    finally:
        if listener is not None:
            listener.close()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell bridge revocation is Windows-specific")
def test_backend_disappearance_halts_fake_bridge_before_exact_process_stop():
    observed: dict[str, object] = {}
    fake_bridge_process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Start-Sleep -Seconds 30"],
        cwd=ROOT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            observed["path"] = self.path
            observed["token"] = self.headers.get("X-OM0RX-Control-Token")
            observed["body"] = json.loads(self.rfile.read(length))
            observed["bridge_alive_when_halted"] = fake_bridge_process.poll() is None
            response = json.dumps({"success": True, "command": "halt_tx"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def do_GET(self):  # noqa: N802
            observed["status_path"] = self.path
            observed["status_token"] = self.headers.get("X-OM0RX-Control-Token")
            observed["bridge_alive_when_status_checked"] = fake_bridge_process.poll() is None
            observed["status_requests"] = int(observed.get("status_requests", 0)) + 1
            still_transmitting = observed["status_requests"] == 1
            response = json.dumps(
                {
                    "success": True,
                    "stats": {
                        "lastStatusAgeMs": 500,
                        "lastStatus": {"transmitting": still_transmitting, "txEnabled": still_transmitting},
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        helper = str(HELPERS).replace("'", "''")
        command_uri = f"http://127.0.0.1:{server.server_port}/wsjtx/command"
        script = (
            f". '{helper}'; "
            f"$result = Invoke-DirectBridgeHalt -CommandUri '{command_uri}' -ControlToken 'test-control-token' -TimeoutSec 2; "
            "if (-not $result.direct_halt_accepted) { exit 2 }; "
            "if (-not $result.direct_idle_confirmed -or -not $result.idle_confirmed) { exit 3 }; "
            f"Stop-Process -Id {fake_bridge_process.pid} -Force; "
            "Write-Output 'halt-before-stop-ok'"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        fake_bridge_process.wait(timeout=5)
        assert result.returncode == 0, result.stderr
        assert "halt-before-stop-ok" in result.stdout
        assert observed == {
            "path": "/wsjtx/command",
            "token": "test-control-token",
            "body": {
                "command": "halt_tx",
                "payload": {"autoOnly": False, "reason": "runtime-owner-revoked"},
            },
            "bridge_alive_when_halted": True,
            "status_path": "/wsjtx/status",
            "status_token": "test-control-token",
            "bridge_alive_when_status_checked": True,
            "status_requests": 2,
        }
    finally:
        server.shutdown()
        server.server_close()
        if fake_bridge_process.poll() is None:
            fake_bridge_process.kill()
        fake_bridge_process.wait(timeout=5)


def test_launchers_halt_direct_bridge_before_every_bridge_teardown():
    for relative in ("start_all.ps1", "scripts/start/start_services_only.ps1"):
        text = (ROOT / relative).read_text(encoding="utf-8-sig")
        cleanup = text[text.index("function Stop-KnownRuntimePorts") : text.index("function Stop-ProjectProcesses")]
        revoke_start = text.index("function Revoke-RuntimeOwnership")
        revoke = text[revoke_start : text.index('Write-Host ""', revoke_start)]
        restart = text[text.index('if ($action -eq "restart")') : text.index("Clear-LifecycleRequest", text.index('if ($action -eq "restart")'))]

        assert "Invoke-RuntimePortCleanup -BackendPort $BackendPort" in cleanup
        assert "12166" not in cleanup
        assert "2237" not in cleanup
        assert revoke.index("Invoke-DirectBridgeHalt") < revoke.index("Write-RuntimeOwnerManifest")
        assert restart.index("Revoke-RuntimeOwnership") < restart.index('Stop-StartedProcess -Process $bridgeProcess')

    helper = HELPERS.read_text(encoding="utf-8-sig")
    assert "http://127.0.0.1:8092/wsjtx/command" in helper
    assert "'X-OM0RX-Control-Token'" in helper
    assert "command = 'halt_tx'" in helper
    assert "lastStatusAgeMs" in helper
    assert "direct_idle_confirmed" in helper
    assert "MaxStatusAgeMs = 6000" in helper


def test_agent_health_requires_both_bridge_ports_and_exact_owner_manifest():
    source = (ROOT / "tools" / "Om0rxAgent" / "AgentSupervisor.cs").read_text(encoding="utf-8-sig")
    assert 'ProbeRequiredPortAsync("bridge-ws", "Bridge WebSocket", _settings.BackendHost, 8091)' in source
    assert 'ProbeRequiredPortAsync("bridge-command", "Bridge Command", _settings.BackendHost, 8092)' in source
    assert "ProbeRuntimeOwnerAsync" in source
    assert "RuntimeProcessIdentityMatches" in source
    assert "RuntimePortsMatchOwnerAsync" in source
    assert 'DllImport("iphlpapi.dll")' in source
    assert "GetExtendedTcpTable" in source
    assert "Get-NetTCPConnection -LocalPort" not in source
    assert 'Path.Combine(_settings.ProjectRoot, "logs", "runtime_owner.json")' in source
    assert "runtime?.Status == ComponentStatus.Error" in source
    assert 'Contains("Launcher UI ready"' in source
    assert "Initial startup failed:" in source
    assert "await WaitForLauncherReadyAsync();" in source
    assert "waiting for a visible desktop UI" in source
    assert "Never start a competing supervisor while a live atomic owner" in source


def test_agent_recovery_accepts_absent_engine_when_backend_is_unreachable():
    source = (ROOT / "tools" / "Om0rxAgent" / "AgentSupervisor.cs").read_text(encoding="utf-8-sig")
    assert "TryGetDigitalEngineProcessIdsAsync" in source
    assert "engineProcessIds is { Count: 0 }" in source
    assert "no MSHV/WSJT engine process exists; recovery may continue" in source
    assert "process enumeration failed" in source
    assert "data\\\\build\\\\mshv-auto-dx\\\\runtime\\\\MSHV_OM0RX.exe" in source
    assert "var helperPattern = stop ?" in source
    assert "The legacy decode-status helper cannot key the radio" in source


def test_managed_owner_loss_revokes_station_authorization(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import services.digital_engine as digital

    state = tmp_path / "digital_engine.json"
    digital.atomic_write_json(state, {"provider": "mshv_auto_dx"})
    monkeypatch.setattr(digital, "STATE_PATH", state)
    monkeypatch.setattr(digital, "STATION_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(
        digital,
        "runtime_owner_status",
        lambda: {"success": False, "managed": True, "reason": "supervisor-process-missing"},
    )
    service = digital.DigitalEngineService()
    service.station_preparations["prepare"] = {"expires_at": 999999999.0}
    service.station_permits["permit"] = {"expires_at": 999999999.0}
    monkeypatch.setattr(digital, "_service", service)
    app = FastAPI()
    digital.register_digital_endpoints(app)

    with TestClient(app) as client:
        ready = client.post(
            "/api/digital/station-ready",
            json={
                "provider": "mshv_auto_dx",
                "request_id": "owner-loss",
                "phase": "prepare",
                "frequency_hz": 14074000,
                "band": "20m",
                "authorization_generation": 1,
            },
        )
        telemetry = client.post(
            "/api/digital/engine-state",
            json={"provider": "mshv_auto_dx", "enabled": True},
        )

    assert ready.json()["reason"] == "runtime-owner-invalid"
    assert telemetry.status_code == 409
    assert not service.station_preparations
    assert service.station_permits["permit"]["revoked"] is True
