from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import _bootstrap  # noqa: F401
import pytest

from remote_station import __main__ as remote_main
from remote_station.config import default_config_document
from remote_station.controller_ownership import (
    CONFLICT_EXIT_CODE,
    MUTEX_NAME,
    ControllerOwnershipConflict,
    StationControllerOwnership,
    read_owner_metadata,
)

ROOT = Path(__file__).resolve().parents[2]
PROBE_PROJECT = ROOT / "tools" / "Om0rxControllerOwnershipProbe" / "Om0rxControllerOwnershipProbe.csproj"


def _contract(tmp_path: Path) -> tuple[str, Path]:
    unique = uuid4().hex
    prefix = "Global" if os.name == "nt" else "om0rx-test"
    return f"{prefix}\\OM0RX.StationController.Test.{unique}", tmp_path / "owner.json"


def _python_owner(
    family: str,
    mutex_name: str,
    owner_path: Path,
    hold_seconds: float,
    *,
    crash: bool = False,
) -> subprocess.Popen[str]:
    source = """
import os
import sys
import time
from pathlib import Path
from remote_station.controller_ownership import StationControllerOwnership
owner = StationControllerOwnership(sys.argv[1], "test", mutex_name=sys.argv[2], owner_path=Path(sys.argv[3]))
owner.acquire()
print("ACQUIRED", flush=True)
time.sleep(float(sys.argv[4]))
if sys.argv[5] == "crash":
    os._exit(0)
owner.release()
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            source,
            family,
            mutex_name,
            str(owner_path),
            str(hold_seconds),
            "crash" if crash else "clean",
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "ACQUIRED"
    return process


@pytest.fixture(scope="session")
def dotnet_probe() -> Path:
    subprocess.run(
        ["dotnet", "build", str(PROBE_PROJECT), "-c", "Release", "--nologo"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    probe = PROBE_PROJECT.parent / "bin" / "Release" / "net8.0" / "Om0rxControllerOwnershipProbe.dll"
    assert probe.exists()
    return probe


def _dotnet_owner(
    probe: Path,
    family: str,
    mutex_name: str,
    owner_path: Path,
    hold_ms: int,
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            "dotnet",
            str(probe),
            family,
            "test",
            str(hold_ms),
            mutex_name,
            str(owner_path),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process


def test_contract_uses_one_stable_windows_global_mutex():
    assert MUTEX_NAME == r"Global\OM0RX.StationController"
    source = (ROOT / "tools" / "Om0rxAgent" / "StationControllerOwnership.cs").read_text(
        encoding="utf-8"
    )
    assert '@"Global\\OM0RX.StationController"' in source


def test_both_production_entrypoints_acquire_before_station_runtime():
    python_source = (ROOT / "remote_station" / "__main__.py").read_text(encoding="utf-8")
    legacy_source = (ROOT / "tools" / "Om0rxAgent" / "Program.cs").read_text(
        encoding="utf-8"
    )
    assert python_source.index("ownership.acquire()") < python_source.index("uvicorn.run(")
    assert legacy_source.index("StationControllerOwnership.TryAcquire(") < legacy_source.index(
        "new AgentSupervisor(settings)"
    )
    assert 'argument.Equals("--non-interactive"' in legacy_source


def test_remote_entrypoint_returns_distinct_conflict_code_before_creating_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "agent.json"
    config_path.write_text(
        json.dumps(default_config_document(control_token="x" * 40)), encoding="utf-8"
    )

    class RefusingOwnership:
        def __init__(self, *_args, **_kwargs):
            pass

        def acquire(self):
            raise ControllerOwnershipConflict("python-remote-station-agent", None)

    monkeypatch.setattr(remote_main, "StationControllerOwnership", RefusingOwnership)
    monkeypatch.setattr(
        remote_main,
        "create_app",
        lambda *_args, **_kwargs: pytest.fail("app/runtime must not be created on conflict"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["remote_station", "run", "--config", str(config_path), "--log-level", "error"],
    )
    assert remote_main.main() == CONFLICT_EXIT_CODE


def test_legacy_controller_first_blocks_python_before_resources(
    tmp_path: Path, dotnet_probe: Path
):
    mutex_name, owner_path = _contract(tmp_path)
    legacy = _dotnet_owner(
        dotnet_probe, "legacy-radio-control-agent", mutex_name, owner_path, 1200
    )
    assert legacy.stdout is not None
    assert legacy.stdout.readline().startswith("ACQUIRED ")
    with pytest.raises(ControllerOwnershipConflict, match="did not open station resources"):
        StationControllerOwnership(
            "python-remote-station-agent",
            "test",
            mutex_name=mutex_name,
            owner_path=owner_path,
        ).acquire()
    assert legacy.wait(timeout=5) == 0


def test_python_controller_first_blocks_legacy_before_supervisor(
    tmp_path: Path, dotnet_probe: Path
):
    mutex_name, owner_path = _contract(tmp_path)
    remote = _python_owner("python-remote-station-agent", mutex_name, owner_path, 1.2)
    legacy = _dotnet_owner(dotnet_probe, "legacy-radio-control-agent", mutex_name, owner_path, 0)
    stdout, stderr = legacy.communicate(timeout=5)
    assert legacy.returncode == CONFLICT_EXIT_CODE
    assert stdout == ""
    assert "did not open station resources" in stderr
    assert remote.wait(timeout=5) == 0


@pytest.mark.parametrize(
    "family", ["python-remote-station-agent", "legacy-radio-control-agent"]
)
def test_second_copy_of_each_controller_family_refuses_cleanly(tmp_path: Path, family: str):
    mutex_name, owner_path = _contract(tmp_path)
    holder = _python_owner(family, mutex_name, owner_path, 1.0)
    with pytest.raises(ControllerOwnershipConflict):
        StationControllerOwnership(
            family, "second-copy", mutex_name=mutex_name, owner_path=owner_path
        ).acquire()
    assert holder.wait(timeout=5) == 0


def test_normal_shutdown_releases_ownership_for_other_controller(tmp_path: Path):
    mutex_name, owner_path = _contract(tmp_path)
    first = StationControllerOwnership(
        "python-remote-station-agent", "test", mutex_name=mutex_name, owner_path=owner_path
    ).acquire()
    first.release()
    second = StationControllerOwnership(
        "legacy-radio-control-agent", "test", mutex_name=mutex_name, owner_path=owner_path
    ).acquire()
    second.release()
    assert not owner_path.exists()


def test_stale_owner_metadata_does_not_block_startup(tmp_path: Path):
    mutex_name, owner_path = _contract(tmp_path)
    owner_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "mutex_name": mutex_name,
                "controller_family": "stale-controller",
                "pid": 999999,
                "executable_path": "C:/stale/controller.exe",
                "started_utc": "2026-01-01T00:00:00+00:00",
                "launch_source": "stale",
            }
        ),
        encoding="utf-8",
    )
    owner = StationControllerOwnership(
        "python-remote-station-agent", "test", mutex_name=mutex_name, owner_path=owner_path
    ).acquire()
    assert owner.owner_info is not None
    assert owner.owner_info.controller_family == "python-remote-station-agent"
    owner.release()


def test_concurrent_launch_race_has_exactly_one_owner(tmp_path: Path):
    mutex_name, owner_path = _contract(tmp_path)
    barrier = tmp_path / "go"
    source = """
import sys
import time
from pathlib import Path
from remote_station.controller_ownership import ControllerOwnershipConflict, StationControllerOwnership
while not Path(sys.argv[1]).exists():
    time.sleep(0.01)
try:
    owner = StationControllerOwnership(sys.argv[2], "race", mutex_name=sys.argv[3], owner_path=Path(sys.argv[4])).acquire()
except ControllerOwnershipConflict:
    raise SystemExit(73)
time.sleep(0.5)
owner.release()
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    contenders = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                source,
                str(barrier),
                family,
                mutex_name,
                str(owner_path),
            ],
            cwd=ROOT,
            env=environment,
        )
        for family in ("python-remote-station-agent", "legacy-radio-control-agent")
    ]
    barrier.touch()
    results = sorted(process.wait(timeout=5) for process in contenders)
    assert results == [0, CONFLICT_EXIT_CODE]


@pytest.mark.skipif(os.name != "nt", reason="Windows abandoned-mutex semantics")
def test_abandoned_mutex_is_recovered_and_reported(tmp_path: Path):
    from remote_station.controller_ownership import _WindowsMutex

    mutex_name, owner_path = _contract(tmp_path)
    keeper = _WindowsMutex(mutex_name)
    crashed = _python_owner(
        "python-remote-station-agent", mutex_name, owner_path, 0.05, crash=True
    )
    assert crashed.wait(timeout=5) == 0
    owner = StationControllerOwnership(
        "legacy-radio-control-agent", "recovery", mutex_name=mutex_name, owner_path=owner_path
    ).acquire()
    try:
        assert owner.abandoned is True
        assert owner.previous_owner is not None
        assert owner.previous_owner.controller_family == "python-remote-station-agent"
    finally:
        owner.release()
        keeper.close()


def test_owner_metadata_contains_only_bounded_safe_diagnostics(tmp_path: Path):
    mutex_name, owner_path = _contract(tmp_path)
    owner = StationControllerOwnership(
        "python-remote-station-agent", "scheduled-task", mutex_name=mutex_name, owner_path=owner_path
    ).acquire()
    try:
        metadata = read_owner_metadata(owner_path)
        assert metadata is not None
        assert set(json.loads(owner_path.read_text(encoding="utf-8"))) == {
            "schema",
            "mutex_name",
            "controller_family",
            "pid",
            "executable_path",
            "started_utc",
            "launch_source",
        }
        assert "token" not in owner_path.read_text(encoding="utf-8").lower()
    finally:
        owner.release()


def test_startup_scripts_detect_conflicts_and_preserve_exit_code():
    remote_installer = (ROOT / "scripts" / "remote_agent" / "install_remote_agent_startup.ps1").read_text(
        encoding="utf-8"
    )
    remote_runner = (ROOT / "scripts" / "remote_agent" / "run_remote_agent.ps1").read_text(
        encoding="utf-8"
    )
    restore = (ROOT / "scripts" / "remote_agent" / "restore_legacy_agent_startup.ps1").read_text(
        encoding="utf-8"
    )
    legacy_installer = (ROOT / "scripts" / "agent" / "install_agent_startup.ps1").read_text(
        encoding="utf-8"
    )
    assert "DisableLegacyStartup" in remote_installer
    assert "StationControllerMigration" in remote_installer
    assert "OM0RX Remote Station Agent" in legacy_installer
    assert "remote tray task may remain enabled" in legacy_installer.lower()
    assert "exit $agentExitCode" in remote_runner
    assert '$agentExitCode -eq 73 -and $LaunchSource -eq "scheduled-task"' in remote_runner
    assert "Suppressing Task Scheduler retries" in remote_runner
    assert "OM0RX Remote Station Agent" in restore
    assert "OM0RX Remote Station Tray" not in restore


def test_tray_and_widget_do_not_acquire_controller_ownership():
    tray = (ROOT / "scripts" / "remote_agent" / "run_remote_agent_tray.ps1").read_text(
        encoding="utf-8"
    )
    widget = (ROOT / "scripts" / "remote_agent" / "remote_agent_widget.ps1").read_text(
        encoding="utf-8"
    )
    assert MUTEX_NAME not in tray
    assert MUTEX_NAME not in widget
