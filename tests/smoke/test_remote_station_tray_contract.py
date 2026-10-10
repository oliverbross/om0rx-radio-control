from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRAY = (ROOT / "scripts" / "remote_agent" / "run_remote_agent_tray.ps1").read_text(
    encoding="utf-8"
)
INSTALLER = (
    ROOT / "scripts" / "remote_agent" / "install_remote_agent_tray_startup.ps1"
).read_text(encoding="utf-8")


def test_tray_exposes_requested_process_controls_and_status_window():
    for label in (
        "Show details",
        "Start agent",
        "Stop agent...",
        "Restart agent...",
        "Quit tray",
    ):
        assert label in TRAY
    assert "OM0RX Remote Station Agent" in TRAY
    assert "Application]::ExitThread()" in TRAY


def test_tray_status_is_read_only_and_never_uses_the_command_endpoint():
    assert "/api/v1/state" in TRAY
    assert "-Method Get" in TRAY
    assert "/api/v1/commands" not in TRAY
    assert "-Method Post" not in TRAY
    assert "radio, PTT, tune, antenna, or station-control commands" in TRAY


def test_tray_shows_sanitized_station_evidence_without_rendering_the_token():
    assert "Commissioned:" in TRAY
    assert "Maestro bound:" in TRAY
    assert "MOX:" in TRAY
    assert "KPA500" in TRAY
    assert "KAT500" in TRAY
    assert "Alarms:" in TRAY
    assert "$token" not in "\n".join(
        line for line in TRAY.splitlines() if "$lines.Add" in line or "$notify.Text" in line
    )


def test_tray_installer_registers_an_interactive_login_task():
    assert '"OM0RX Remote Station Tray"' in INSTALLER
    assert "New-ScheduledTaskTrigger -AtLogOn" in INSTALLER
    assert "-LogonType Interactive" in INSTALLER
    assert "-STA -WindowStyle Hidden" in INSTALLER
