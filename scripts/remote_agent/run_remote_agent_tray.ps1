param(
    [string]$Config = "",
    [string]$AgentTaskName = "OM0RX Remote Station Agent"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

$mutex = [System.Threading.Mutex]::new($false, "Local\OM0RXRemoteStationTray")
if (-not $mutex.WaitOne(0, $false)) {
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
$localStateUrl = "http://127.0.0.1:8840/api/v1/state"

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
        $headers = @{ Authorization = "Bearer $token" }
        $response = Invoke-RestMethod -Uri $localStateUrl -Headers $headers -Method Get -TimeoutSec 3
        if (-not $response.success -or -not $response.state) {
            throw "The local agent returned an invalid state response."
        }
        return [pscustomobject]@{
            TaskState = $taskState
            State = $response.state
            Error = $null
        }
    }
    catch {
        return [pscustomobject]@{
            TaskState = $taskState
            State = $null
            Error = $_.Exception.Message
        }
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

$form = New-Object System.Windows.Forms.Form
$form.Text = "OM0RX Remote Station Agent"
$form.ClientSize = New-Object System.Drawing.Size(660, 520)
$form.MinimumSize = New-Object System.Drawing.Size(560, 420)
$form.StartPosition = "CenterScreen"
$form.ShowInTaskbar = $true

$details = New-Object System.Windows.Forms.TextBox
$details.Multiline = $true
$details.ReadOnly = $true
$details.ScrollBars = "Vertical"
$details.Dock = "Fill"
$details.Font = New-Object System.Drawing.Font("Consolas", 10)
$details.BackColor = [System.Drawing.Color]::White
$form.Controls.Add($details)

$notify = New-Object System.Windows.Forms.NotifyIcon
$iconPath = Join-Path $projectRoot "tools\Om0rxAgent\assets\om0rx-agent.ico"
$notify.Icon = if (Test-Path -LiteralPath $iconPath) {
    New-Object System.Drawing.Icon($iconPath)
}
else {
    [System.Drawing.SystemIcons]::Application
}
$notify.Text = "OM0RX Remote Station Agent"
$notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$showItem = $menu.Items.Add("Show details")
$refreshItem = $menu.Items.Add("Refresh")
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
    Update-AgentStatus
    $form.Show()
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
            $notify.Icon = [System.Drawing.SystemIcons]::Information
        }
        $alignment = if ($snapshot.State.station.path) { $snapshot.State.station.path.alignment } else { "unknown" }
        $alarmCount = if ($alarmState) { $alarmState.active_count } else { "?" }
        $notify.Text = "OM0RX Remote Agent: $alignment, $alarmCount alarm(s)"
    }
}

$showItem.add_Click({ Show-DetailsWindow })
$refreshItem.add_Click({ Update-AgentStatus })
$notify.add_DoubleClick({ Show-DetailsWindow })
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
    if (-not $script:closing -and $eventArgs.CloseReason -eq [System.Windows.Forms.CloseReason]::UserClosing) {
        $eventArgs.Cancel = $true
        $sender.Hide()
    }
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000
$timer.add_Tick({ Update-AgentStatus })
$timer.Start()

try {
    Update-AgentStatus
    [System.Windows.Forms.Application]::Run()
}
finally {
    $timer.Stop()
    $timer.Dispose()
    $notify.Visible = $false
    $notify.Dispose()
    $form.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
