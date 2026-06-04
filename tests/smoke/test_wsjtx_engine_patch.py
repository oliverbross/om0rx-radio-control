"""Checks for the OM0RX WSJT-X Improved engine patch artifact."""

import subprocess
import tarfile
from pathlib import Path

import _bootstrap  # noqa: F401

from services.wsjtx import PROJECT_ROOT as WSJTX_PROJECT_ROOT
from services.wsjtx import WSJTXService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PATCH_PATH = PROJECT_ROOT / "docs" / "wsjtx" / "om0rx-start-target-qso.patch"
SOURCE_ARCHIVE = PROJECT_ROOT / "data" / "research" / "wsjtx-improved-3.1.0" / "src" / "wsjtx.tgz"


def test_wsjtx_engine_patch_contains_target_qso_extension():
    text = PATCH_PATH.read_text(encoding="utf-8")

    assert "OM0RXStartTargetQSO" in text
    assert "start_target_qso" in text
    assert "remote_start_target_qso" in text
    assert "QJsonDocument" in text
    assert "ui->autoButton->click" in text
    assert "OM0RX_BUILD_WITH_OMNIRIG" in text
    assert "TransceiverFactory.cpp" in text


def test_wsjtx_engine_patch_applies_to_downloaded_source(tmp_path):
    if not SOURCE_ARCHIVE.exists():
        return

    source_root = tmp_path / "wsjtx-src"
    source_root.mkdir()
    with tarfile.open(SOURCE_ARCHIVE, "r:gz") as archive:
      members = archive.getmembers()
      root_prefix = members[0].name.split("/")[0] + "/"
      for member in members:
          if not member.name.startswith(root_prefix):
              continue
          member.name = member.name[len(root_prefix):]
          if member.name:
              archive.extract(member, source_root)

    subprocess.run(
        ["git", "-C", str(source_root), "apply", "--check", str(PATCH_PATH)],
        check=True,
        text=True,
        capture_output=True,
    )


def test_wsjtx_engine_build_scripts_are_present():
    script_root = PROJECT_ROOT / "scripts" / "wsjtx"

    prepare = (script_root / "prepare_om0rx_wsjtx.ps1").read_text(encoding="utf-8")
    build = (script_root / "build_om0rx_wsjtx.ps1").read_text(encoding="utf-8")
    run = (script_root / "run_om0rx_wsjtx.ps1").read_text(encoding="utf-8")

    assert "om0rx-start-target-qso.patch" in prepare
    assert "OM0RX_BUILD_WITH_OMNIRIG=OFF" in build
    assert "--target wsjtx jt9" in build
    assert "jt9.exe" in build
    assert "--rig-name" in run
    assert "--config" in run
    assert "jt9.exe" in run
    assert "$appName.lock" in run
    assert "already running" in run
    assert "RedirectStandardOutput" in run


def test_wsjtx_launch_logs_tail_stdout_and_missing_stderr():
    service = WSJTXService()
    rig_name = "PYTEST-LOG"
    log_root = WSJTX_PROJECT_ROOT / "logs"
    stdout_log = log_root / "wsjt-x-pytest-log.out.log"
    stderr_log = log_root / "wsjt-x-pytest-log.err.log"
    log_root.mkdir(parents=True, exist_ok=True)

    try:
        stdout_log.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
        if stderr_log.exists():
            stderr_log.unlink()

        result = service.get_launch_logs(rig_name=rig_name, lines=2)

        assert result["success"] is True
        assert result["rig_name"] == rig_name
        assert result["lines"] == 2
        assert result["logs"]["stdout"]["exists"] is True
        assert result["logs"]["stdout"]["lines"] == ["line 2", "line 3"]
        assert result["logs"]["stderr"]["exists"] is False
        assert result["logs"]["stderr"]["lines"] == []
    finally:
        if stdout_log.exists():
            stdout_log.unlink()
        if stderr_log.exists():
            stderr_log.unlink()
