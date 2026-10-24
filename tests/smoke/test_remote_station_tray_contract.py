from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRAY = (ROOT / "scripts" / "remote_agent" / "run_remote_agent_tray.ps1").read_text(
    encoding="utf-8"
)
INSTALLER = (
    ROOT / "scripts" / "remote_agent" / "install_remote_agent_tray_startup.ps1"
).read_text(encoding="utf-8")
UNINSTALLER = (
    ROOT / "scripts" / "remote_agent" / "uninstall_remote_agent_tray_startup.ps1"
).read_text(encoding="utf-8")
SETTINGS = (
    ROOT / "scripts" / "remote_agent" / "remote_agent_settings.ps1"
).read_text(encoding="utf-8")
WIDGET = (
    ROOT / "scripts" / "remote_agent" / "remote_agent_widget.ps1"
).read_text(encoding="utf-8")
STARTUP_INSTALLER = (
    ROOT / "scripts" / "remote_agent" / "install_remote_agent_startup.ps1"
).read_text(encoding="utf-8")


def test_tray_exposes_requested_process_controls_and_status_window():
    for label in (
        "Show details",
        "Show station widget",
        "Settings...",
        "Start agent",
        "Stop agent...",
        "Restart agent...",
        "Quit tray",
    ):
        assert label in TRAY
    assert "OM0RX Remote Station Agent" in TRAY
    assert "Application]::ExitThread()" in TRAY
    assert "Show-StationWidget" in TRAY


def test_tray_launches_settings_and_widget_without_a_visible_powershell_console():
    assert TRAY.count('"-WindowStyle", "Hidden"') >= 2
    assert TRAY.count("-WindowStyle Hidden") >= 2
    assert 'Start-Process -FilePath "powershell.exe"' in TRAY


def test_tray_status_is_read_only_and_station_actions_use_the_command_endpoint():
    assert "/api/v1/state" in TRAY
    assert "-Method Get" in TRAY
    assert "/api/v1/commands" in TRAY
    assert "-Method Post" in TRAY
    for command in (
        "station_standby",
        "station_operate",
        "station_tune",
        "station_cancel",
    ):
        assert command in TRAY


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


def test_tray_tolerates_partial_radio_state_without_optional_slice_objects():
    assert "function Get-PropertyValue" in TRAY
    assert 'Get-PropertyValue $radio "active_receive"' in TRAY
    assert 'Get-PropertyValue $radio "transmit"' in TRAY
    assert "$radio.active_receive.index_letter" not in TRAY
    assert "$radio.transmit.index_letter" not in TRAY


def test_tray_surfaces_shared_controller_owner_without_acquiring_the_mutex():
    assert "station-controller-owner.json" in TRAY
    assert "Get-ControllerOwnerInfo" in TRAY
    assert "Active station controller:" in TRAY
    assert "Global\\OM0RX.StationController" not in TRAY


def test_tray_installer_registers_an_interactive_login_task():
    assert '"OM0RX Remote Station Tray"' in INSTALLER
    assert "New-ScheduledTaskTrigger -AtLogOn" in INSTALLER
    assert "-LogonType Interactive" in INSTALLER
    assert "-STA -WindowStyle Hidden" in INSTALLER
    assert '-Python `"$Python`"' in INSTALLER


def test_tray_installer_adds_a_start_menu_entry_that_opens_existing_details():
    assert '[Environment]::GetFolderPath("Programs")' in INSTALLER
    assert '"OM0RX Remote Station Agent.lnk"' in INSTALLER
    assert "$shortcut.Save()" in INSTALLER
    assert '-ShowDetails -EnsureAgentStarted"' in INSTALLER
    assert '"Local\\OM0RXRemoteStationTrayShow"' in TRAY
    assert "if ($ShowDetails)" in TRAY
    assert "$showEvent.Set()" in TRAY
    assert '"OM0RX Remote Station Agent.lnk"' in UNINSTALLER


def test_start_menu_launcher_starts_only_the_existing_agent_task_when_needed():
    assert "[switch]$EnsureAgentStarted" in TRAY
    assert "if ($EnsureAgentStarted)" in TRAY
    assert 'if ($agentTask.State -ne "Running")' in TRAY
    assert "Start-ScheduledTask -TaskName $AgentTaskName" in TRAY
    assert "AddSeconds(10)" in TRAY
    assert "New-ScheduledTaskAction" not in TRAY


def test_start_menu_launcher_requires_api_health_and_repairs_one_stuck_start():
    assert "function Wait-AgentApi" in TRAY
    assert "if (-not (Wait-AgentApi 20))" in TRAY
    assert "Stop-ScheduledTask -TaskName $AgentTaskName" in TRAY
    assert "if (-not (Wait-AgentApi 30))" in TRAY


def test_agent_startup_task_is_not_blocked_or_stopped_by_battery_state():
    assert "-AllowStartIfOnBatteries" in STARTUP_INSTALLER
    assert "-DontStopIfGoingOnBatteries" in STARTUP_INSTALLER


def test_tray_keeps_details_form_reusable_and_ignores_shutdown_show_races():
    assert "$form.IsDisposed" in TRAY
    assert "$form.Disposing" in TRAY
    assert "if (-not $form.Visible)" in TRAY
    assert "if (-not $script:closing)" in TRAY
    assert "if (-not $script:closing -and $showEvent.WaitOne(0))" in TRAY
    assert "CloseReason]::UserClosing" not in TRAY


def test_settings_gui_covers_connections_accessories_band_policy_and_commissioning():
    for label in (
        "Connections and security",
        "Band, antenna and RF policy",
        "Tuning and commissioning",
        "KPA500 enabled",
        "KAT500 enabled",
        "Automatically follow the observed radio band",
        "PA allowed",
        "PA drive W",
        "Barefoot W",
        "Digital PA",
        "Digital drive W",
        "Tune power (W)",
        "Station physically commissioned",
        "Save and restart agent...",
    ):
        assert label in SETTINGS


def test_settings_gui_masks_credentials_validates_before_atomic_save_and_requires_commissioning_confirmation():
    assert "UseSystemPasswordChar = $true" in SETTINGS
    assert "python -m remote_station" not in SETTINGS
    assert "-m remote_station check" in SETTINGS
    assert "[System.IO.File]::Replace" in SETTINGS
    assert 'confirmation -cne "COMMISSION"' in SETTINGS
    assert "does not key PTT" in SETTINGS
    assert "does not restart the agent" in SETTINGS


def test_station_widget_covers_live_flex_kpa_and_kat_telemetry():
    for value in (
        "VFO A",
        "VFO B",
        "TX POWER",
        "SWR",
        "RF DRIVE",
        "output_power_w",
        "temperature_c",
        "voltage",
        "current",
        "forward_adc",
        "reflected_adc",
        "KPA500",
        "KAT500",
    ):
        assert value in WIDGET
    assert "/api/v1/state" in WIDGET
    assert "-Method Get" in WIDGET
    assert "/api/v1/commands" in WIDGET
    assert "station_clear_faults" in WIDGET
    assert "Clear alarms" in WIDGET
    assert "This does not enable Operate or transmit RF" in WIDGET


def test_station_widget_has_configuration_access_ascii_safe_routes_and_grouped_frequency():
    assert '$settingsButton.Text = "Configure"' in WIDGET
    assert '"Open configuration..."' in WIDGET
    assert "Open-AgentSettings" in WIDGET
    assert 'Start-Process -FilePath "powershell.exe"' in WIDGET
    assert '"-WindowStyle", "Hidden"' in WIDGET
    assert "Format-RouteLabel" in WIDGET
    assert "[^\\x20-\\x7E]+" in WIDGET
    assert '"{0}.{1:000}.{2:000} MHz"' in WIDGET
    assert '"14.074.000 MHz"' in WIDGET


def test_station_widget_is_positionable_persistent_and_distinguishes_measured_from_set_power():
    assert "SizableToolWindow" in WIDGET
    assert "widget.json" in WIDGET
    assert "Always on top" in WIDGET
    assert "Reset position" in WIDGET
    assert '"{0:0} W" -f [double]$kpaOutput' in WIDGET
    assert '"~{0:0} W SET" -f [double]$drive' in WIDGET
    assert "swr_live" in WIDGET
    assert "LAST" in WIDGET
    assert "Station widget smoke test passed" in WIDGET
