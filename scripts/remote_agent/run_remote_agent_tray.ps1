param(
    [string]$Config = "",
    [string]$Python = "python.exe",
    [string]$AgentTaskName = "OM0RX Remote Station Agent",
    [switch]$ShowDetails
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

$showEvent = [System.Threading.EventWaitHandle]::new(
    $false,
    [System.Threading.EventResetMode]::AutoReset,
    "Local\OM0RXRemoteStationTrayShow"
)
$mutex = [System.Threading.Mutex]::new($false, "Local\OM0RXRemoteStationTray")
if (-not $mutex.WaitOne(0, $false)) {
    if ($ShowDetails) {
        $showEvent.Set() | Out-Null
    }
    $showEvent.Dispose()
    $mutex.Dispose()
    exit 0
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$configPath = if ($Config) {
    [System.IO.Path]::GetFullPath($Config)
}
else {
    Join-Path $env:APPDATA "OM0RX Remote Station\agent.json"
}
$logPath = Join-Path (Split-Path -Parent $configPath) "agent.log"
$controllerOwnerPath = Join-Path $env:LOCALAPPDATA "OM0RX\station-controller-owner.json"
$settingsScript = Join-Path $PSScriptRoot "remote_agent_settings.ps1"
$widgetScript = Join-Path $PSScriptRoot "remote_agent_widget.ps1"

$script:lastSnapshot = $null
$script:closing = $false

function Get-TaskState {
    try {
        return (Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop).State.ToString()
    }
    catch {
        return "Not installed"
    }
}

function Get-AgentSnapshot {
    $taskState = Get-TaskState
    try {
        $document = Get-Content -LiteralPath $configPath -Raw -ErrorAction Stop | ConvertFrom-Json
        $token = [string]$document.server.control_token
        if ([string]::IsNullOrWhiteSpace($token)) {
            throw "The local agent configuration has no bearer token."
        }
        $bindPort = [int]$document.server.bind_port
        $localStateUrl = "http://127.0.0.1:$bindPort/api/v1/state"
        $headers = @{ Authorization = "Bearer $token" }
        $response = Invoke-RestMethod -Uri $localStateUrl -Headers $headers -Method Get -TimeoutSec 3
        if (-not $response.success -or -not $response.state) {
            throw "The local agent returned an invalid state response."
        }
        return [pscustomobject]@{
            TaskState = $taskState
            State = $response.state
            Error = $null
            ControllerOwner = Get-ControllerOwnerInfo
        }
    }
    catch {
        return [pscustomobject]@{
            TaskState = $taskState
            State = $null
            Error = $_.Exception.Message
            ControllerOwner = Get-ControllerOwnerInfo
        }
    }
}

function Get-ControllerOwnerInfo {
    try {
        $owner = Get-Content -LiteralPath $controllerOwnerPath -Raw -ErrorAction Stop | ConvertFrom-Json
        if ([int]$owner.schema -ne 1 -or [int]$owner.pid -le 0) { return $null }
        return [pscustomobject]@{
            Family = ([string]$owner.controller_family -replace '[^A-Za-z0-9._-]', '')
            Pid = [int]$owner.pid
            LaunchSource = ([string]$owner.launch_source -replace '[^A-Za-z0-9._-]', '')
        }
    }
    catch {
        return $null
    }
}

function Format-Boolean([object]$Value, [string]$TrueText, [string]$FalseText) {
    if ($null -eq $Value) { return "unknown" }
    if ([bool]$Value) { return $TrueText }
    return $FalseText
}

function Format-AgentDetails([object]$Snapshot) {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("OM0RX Remote Station Agent")
    $lines.Add("Updated UTC: $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss'))")
    $lines.Add("Scheduled task: $($Snapshot.TaskState)")

    if ($null -eq $Snapshot.State) {
        $lines.Add("")
        $lines.Add("Local API: unavailable")
        $lines.Add("Reason: $($Snapshot.Error)")
        if ($Snapshot.ControllerOwner) {
            $lines.Add(
                "Active station controller: $($Snapshot.ControllerOwner.Family) " +
                "(PID $($Snapshot.ControllerOwner.Pid), $($Snapshot.ControllerOwner.LaunchSource))"
            )
        }
        else {
            $lines.Add("Active station controller: unknown; inspect both controller startup entries.")
        }
        return $lines -join [Environment]::NewLine
    }

    $state = $Snapshot.State
    $radio = $state.radio
    $station = $state.station
    $kpa = $state.elecraft.kpa500
    $kat = $state.elecraft.kat500
    $alarms = $station.alarms
    $alarmCodes = @($alarms.items | ForEach-Object { $_.code }) -join ", "
    if (-not $alarmCodes) { $alarmCodes = "none" }
    $routeMismatches = @($station.path.mismatches | ForEach-Object { $_.code }) -join ", "
    if (-not $routeMismatches) { $routeMismatches = "none" }
    $uptime = [TimeSpan]::FromSeconds([double]$state.agent.uptime_seconds)

    $lines.Add("Local API: authenticated and available")
    $lines.Add("Protocol: v$($state.protocol_version)   Uptime: $([math]::Floor($uptime.TotalHours))h $($uptime.Minutes)m")
    $lines.Add("Commissioned: $($station.commissioned)   Transmit authorization: $($station.path.transmit_authorized)")
    $lines.Add("")
    $lines.Add("FLEX-8400")
    $lines.Add("  Connected: $($radio.connected)   Fresh: $(-not [bool]$radio.stale)   Maestro bound: $($radio.station_bound)")
    $lines.Add("  Frequency: $($radio.frequency) MHz   Mode: $($radio.mode)")
    $lines.Add("  RX antenna: $($radio.rx_ant)   TX antenna: $($radio.tx_ant)")
    $lines.Add("  Active slice: $($radio.active_receive.index_letter)   TX slice: $($radio.transmit.index_letter)")
    $lines.Add("  MOX: $($radio.mox)   Interlock: $($radio.interlock_state)")
    $lines.Add("")
    $lines.Add("KPA500")
    $lines.Add("  Connected: $($kpa.connected)   Band: $($kpa.band)   State: $(Format-Boolean $kpa.operate 'OPERATE' 'STBY')")
    $lines.Add("KAT500")
    $lines.Add("  Connected: $($kat.connected)   Band: $($kat.band)   Antenna: ANT$($kat.antenna)")
    $lines.Add("")
    $lines.Add("Route: $($station.path.alignment)   Mismatches: $routeMismatches")
    $lines.Add("Alarms: $($alarms.active_count) (critical $($alarms.counts.critical), warning $($alarms.counts.warning), info $($alarms.counts.info))")
    $lines.Add("Alarm codes: $alarmCodes")
    $allowedActions = @($station.allowed_actions) -join ", "
    if (-not $allowedActions) { $allowedActions = "none" }
    $lines.Add("Allowed station actions: $allowedActions")
    if ($state.agent.last_error) {
        $lines.Add("Last agent error: $($state.agent.last_error)")
    }
    $lines.Add("")
    $lines.Add("This tray is status and process control only. It exposes no radio, PTT, tune, antenna, or station-control commands.")
    return $lines -join [Environment]::NewLine
}

function Invoke-AgentTaskAction([ValidateSet("Start", "Stop", "Restart")][string]$Action) {
    try {
        if ($Action -eq "Stop" -or $Action -eq "Restart") {
            Stop-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
            if ($Action -eq "Restart") {
                $deadline = [DateTime]::UtcNow.AddSeconds(10)
                do {
                    [System.Windows.Forms.Application]::DoEvents()
                    Start-Sleep -Milliseconds 200
                } while ((Get-TaskState) -eq "Running" -and [DateTime]::UtcNow -lt $deadline)
            }
        }
        if ($Action -eq "Start" -or $Action -eq "Restart") {
            Start-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
        }
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "Could not $($Action.ToLowerInvariant()) the agent task.`r`n`r`n$($_.Exception.Message)",
            "OM0RX Remote Station",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
    Update-AgentStatus
}

function Open-AgentSettings {
    try {
        if (-not (Test-Path -LiteralPath $settingsScript)) {
            throw "Settings editor not found: $settingsScript"
        }
        $arguments = @(
            "-NoProfile",
            "-STA",
            "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass",
            "-File", ('"{0}"' -f $settingsScript),
            "-Config", ('"{0}"' -f $configPath),
            "-Python", ('"{0}"' -f $Python),
            "-AgentTaskName", ('"{0}"' -f $AgentTaskName)
        )
        Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WindowStyle Hidden
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "Could not open agent settings.`r`n`r`n$($_.Exception.Message)",
            "OM0RX Remote Station",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
}

function Show-StationWidget {
    try {
        if (-not (Test-Path -LiteralPath $widgetScript)) {
            throw "Station widget not found: $widgetScript"
        }
        $arguments = @(
            "-NoProfile",
            "-STA",
            "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass",
            "-File", ('"{0}"' -f $widgetScript),
            "-Config", ('"{0}"' -f $configPath),
            "-Python", ('"{0}"' -f $Python)
        )
        Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WindowStyle Hidden
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "Could not open the station widget.`r`n`r`n$($_.Exception.Message)",
            "OM0RX Remote Station",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
}

function Invoke-StationAction(
    [ValidateSet("station_standby", "station_operate", "station_tune", "station_cancel")]
    [string]$Command
) {
    $labels = @{
        station_standby = "put the station in standby"
        station_operate = "place the amplifier in OPERATE"
        station_tune = "start the guarded tuner transaction"
        station_cancel = "cancel tuning and return to receive"
    }
    if ($Command -in @("station_operate", "station_tune")) {
        $choice = [System.Windows.Forms.MessageBox]::Show(
            "Request to $($labels[$Command])?`r`n`r`nThe agent will allow this only when commissioning, route, alarms and live hardware readback all pass.",
            "Confirm station control",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        )
        if ($choice -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    }
    try {
        $document = Get-Content -LiteralPath $configPath -Raw -ErrorAction Stop | ConvertFrom-Json
        $token = [string]$document.server.control_token
        if ([string]::IsNullOrWhiteSpace($token)) { throw "The local agent configuration has no bearer token." }
        $bindPort = [int]$document.server.bind_port
        $localCommandUrl = "http://127.0.0.1:$bindPort/api/v1/commands"
        $headers = @{ Authorization = "Bearer $token" }
        $body = @{
            request_id = "windows-tray-$([Guid]::NewGuid().ToString('N'))"
            command = $Command
            arguments = @{}
        } | ConvertTo-Json -Depth 4
        $response = Invoke-RestMethod -Uri $localCommandUrl -Headers $headers -Method Post -ContentType "application/json" -Body $body -TimeoutSec 45
        if (-not $response.success) { throw "The station agent rejected the action." }
        Update-AgentStatus
    }
    catch {
        $message = $_.Exception.Message
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            try {
                $errorDocument = $_.ErrorDetails.Message | ConvertFrom-Json
                if ($errorDocument.error.message) { $message = [string]$errorDocument.error.message }
            }
            catch { }
        }
        [System.Windows.Forms.MessageBox]::Show(
            "The station action was not completed.`r`n`r`n$message",
            "OM0RX Remote Station",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "OM0RX Remote Station Agent"
$form.ClientSize = New-Object System.Drawing.Size(660, 520)
$form.MinimumSize = New-Object System.Drawing.Size(560, 420)
$form.StartPosition = "CenterScreen"
$form.ShowInTaskbar = $true

$actions = New-Object System.Windows.Forms.FlowLayoutPanel
$actions.Dock = "Bottom"
$actions.Height = 46
$actions.Padding = New-Object System.Windows.Forms.Padding(6)
$actions.WrapContents = $false
$form.Controls.Add($actions)

function Add-ActionButton([string]$Text, [int]$Width = 95) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.Width = $Width
    $button.Height = 30
    $actions.Controls.Add($button)
    return $button
}

$settingsButton = Add-ActionButton "Settings..." 100
$widgetButton = Add-ActionButton "Widget" 80
$standbyButton = Add-ActionButton "Standby" 90
$operateButton = Add-ActionButton "Operate..." 90
$tuneButton = Add-ActionButton "Tune..." 90
$cancelTuneButton = Add-ActionButton "Cancel tune" 95
$refreshButton = Add-ActionButton "Refresh" 85

$details = New-Object System.Windows.Forms.TextBox
$details.Multiline = $true
$details.ReadOnly = $true
$details.ScrollBars = "Vertical"
$details.Dock = "Fill"
$details.Font = New-Object System.Drawing.Font("Consolas", 10)
$details.BackColor = [System.Drawing.Color]::White
$form.Controls.Add($details)
$actions.BringToFront()

$notify = New-Object System.Windows.Forms.NotifyIcon
$iconPath = Join-Path $projectRoot "tools\Om0rxAgent\assets\om0rx-agent.ico"
$script:customIcon = if (Test-Path -LiteralPath $iconPath) {
    New-Object System.Drawing.Icon($iconPath)
}
else {
    $null
}
$notify.Icon = if ($script:customIcon) { $script:customIcon } else { [System.Drawing.SystemIcons]::Information }
$notify.Text = "OM0RX Remote Station Agent"
$notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$showItem = $menu.Items.Add("Show details")
$widgetItem = $menu.Items.Add("Show station widget")
$settingsItem = $menu.Items.Add("Settings...")
$refreshItem = $menu.Items.Add("Refresh")
$stationMenu = New-Object System.Windows.Forms.ToolStripMenuItem("Station control")
$standbyItem = $stationMenu.DropDownItems.Add("Standby")
$operateItem = $stationMenu.DropDownItems.Add("Operate...")
$tuneItem = $stationMenu.DropDownItems.Add("Tune...")
$cancelTuneItem = $stationMenu.DropDownItems.Add("Cancel tune")
$menu.Items.Add($stationMenu) | Out-Null
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
$startItem = $menu.Items.Add("Start agent")
$stopItem = $menu.Items.Add("Stop agent...")
$restartItem = $menu.Items.Add("Restart agent...")
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
$logItem = $menu.Items.Add("Open agent log")
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
$quitItem = $menu.Items.Add("Quit tray")
$notify.ContextMenuStrip = $menu

function Show-DetailsWindow {
    # The details form is intentionally reusable for the lifetime of the tray.
    # Ignore late launcher/event signals while the UI is shutting down instead
    # of asking WinForms to show an object that is already being disposed.
    if ($script:closing -or $form.IsDisposed -or $form.Disposing) {
        return
    }
    Update-AgentStatus
    if (-not $form.Visible) {
        $form.Show()
    }
    $form.WindowState = "Normal"
    $form.Activate()
}

function Update-AgentStatus {
    $snapshot = Get-AgentSnapshot
    $script:lastSnapshot = $snapshot
    try {
        $details.Text = Format-AgentDetails $snapshot
    }
    catch {
        $details.Text = "OM0RX Remote Station Agent`r`n`r`nStatus rendering failed: $($_.Exception.Message)"
    }
    $running = $snapshot.TaskState -eq "Running"
    $startItem.Enabled = -not $running -and $snapshot.TaskState -ne "Not installed"
    $stopItem.Enabled = $running
    $restartItem.Enabled = $running
    $apiAvailable = $null -ne $snapshot.State
    $allowedActions = if ($apiAvailable) { @($snapshot.State.station.allowed_actions) } else { @() }
    $standbyButton.Enabled = $allowedActions -contains "standby"
    $standbyItem.Enabled = $allowedActions -contains "standby"
    $cancelTuneButton.Enabled = $allowedActions -contains "cancel"
    $cancelTuneItem.Enabled = $allowedActions -contains "cancel"
    $operateButton.Enabled = $allowedActions -contains "operate"
    $operateItem.Enabled = $allowedActions -contains "operate"
    $tuneButton.Enabled = $allowedActions -contains "tune"
    $tuneItem.Enabled = $allowedActions -contains "tune"
    if ($null -eq $snapshot.State) {
        $notify.Icon = [System.Drawing.SystemIcons]::Error
        $notify.Text = "OM0RX Remote Agent: unavailable"
    }
    else {
        $alarmState = $snapshot.State.station.alarms
        $warningCount = if ($alarmState) { [int]$alarmState.counts.warning } else { 1 }
        $criticalCount = if ($alarmState) { [int]$alarmState.counts.critical } else { 0 }
        if ($criticalCount -gt 0) {
            $notify.Icon = [System.Drawing.SystemIcons]::Error
        }
        elseif ($warningCount -gt 0) {
            $notify.Icon = [System.Drawing.SystemIcons]::Warning
        }
        else {
            $notify.Icon = if ($script:customIcon) { $script:customIcon } else { [System.Drawing.SystemIcons]::Information }
        }
        $alignment = if ($snapshot.State.station.path) { $snapshot.State.station.path.alignment } else { "unknown" }
        $alarmCount = if ($alarmState) { $alarmState.active_count } else { "?" }
        $notify.Text = "OM0RX Remote Agent: $alignment, $alarmCount alarm(s)"
    }
}

$showItem.add_Click({ Show-DetailsWindow })
$widgetItem.add_Click({ Show-StationWidget })
$widgetButton.add_Click({ Show-StationWidget })
$settingsItem.add_Click({ Open-AgentSettings })
$settingsButton.add_Click({ Open-AgentSettings })
$refreshItem.add_Click({ Update-AgentStatus })
$refreshButton.add_Click({ Update-AgentStatus })
$notify.add_DoubleClick({ Show-DetailsWindow })
$standbyItem.add_Click({ Invoke-StationAction "station_standby" })
$standbyButton.add_Click({ Invoke-StationAction "station_standby" })
$operateItem.add_Click({ Invoke-StationAction "station_operate" })
$operateButton.add_Click({ Invoke-StationAction "station_operate" })
$tuneItem.add_Click({ Invoke-StationAction "station_tune" })
$tuneButton.add_Click({ Invoke-StationAction "station_tune" })
$cancelTuneItem.add_Click({ Invoke-StationAction "station_cancel" })
$cancelTuneButton.add_Click({ Invoke-StationAction "station_cancel" })
$startItem.add_Click({ Invoke-AgentTaskAction "Start" })
$stopItem.add_Click({
    $choice = [System.Windows.Forms.MessageBox]::Show(
        "Stop the remote-station agent? The tray will remain available.",
        "OM0RX Remote Station",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) { Invoke-AgentTaskAction "Stop" }
})
$restartItem.add_Click({
    $choice = [System.Windows.Forms.MessageBox]::Show(
        "Restart the remote-station agent? Startup performs its existing receive-safety recovery before reconnecting.",
        "OM0RX Remote Station",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) { Invoke-AgentTaskAction "Restart" }
})
$logItem.add_Click({
    if (Test-Path -LiteralPath $logPath) {
        Start-Process -FilePath "notepad.exe" -ArgumentList @($logPath)
    }
    else {
        [System.Windows.Forms.MessageBox]::Show("The agent log does not exist yet: $logPath") | Out-Null
    }
})
$quitItem.add_Click({
    $script:closing = $true
    $notify.Visible = $false
    [System.Windows.Forms.Application]::ExitThread()
})
$form.add_FormClosing({
    param($sender, $eventArgs)
    # Keep the modeless status form alive when anything other than the tray's
    # explicit Quit command tries to close it.  A disposed form cannot be shown
    # again from the tray icon or Start-menu launcher.
    if (-not $script:closing) {
        $eventArgs.Cancel = $true
        $sender.Hide()
    }
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000
$timer.add_Tick({ Update-AgentStatus })
$timer.Start()

$showTimer = New-Object System.Windows.Forms.Timer
$showTimer.Interval = 250
$showTimer.add_Tick({
    if (-not $script:closing -and $showEvent.WaitOne(0)) {
        Show-DetailsWindow
    }
})
$showTimer.Start()

try {
    Update-AgentStatus
    Show-StationWidget
    if ($ShowDetails) {
        Show-DetailsWindow
    }
    [System.Windows.Forms.Application]::Run()
}
finally {
    $showTimer.Stop()
    $showTimer.Dispose()
    $timer.Stop()
    $timer.Dispose()
    $notify.Visible = $false
    $notify.Dispose()
    if ($script:customIcon) { $script:customIcon.Dispose() }
    $form.Dispose()
    $showEvent.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
