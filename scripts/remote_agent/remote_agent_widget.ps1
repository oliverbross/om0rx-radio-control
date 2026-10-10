param(
    [string]$Config = "",
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

$configPath = if ($Config) {
    [System.IO.Path]::GetFullPath($Config)
}
else {
    Join-Path $env:APPDATA "OM0RX Remote Station\agent.json"
}
$widgetStatePath = Join-Path (Split-Path -Parent $configPath) "widget.json"
$instanceSuffix = if ($SmokeTest) { "SmokeTest" } else { "Live" }
$mutexName = "Local\OM0RXRemoteStationWidget$instanceSuffix"
$showEventName = "Local\OM0RXRemoteStationWidgetShow$instanceSuffix"
$createdNew = $false
$mutex = [System.Threading.Mutex]::new($true, $mutexName, [ref]$createdNew)
if (-not $createdNew) {
    try {
        $existingEvent = [System.Threading.EventWaitHandle]::OpenExisting($showEventName)
        $existingEvent.Set() | Out-Null
        $existingEvent.Dispose()
    }
    catch { }
    $mutex.Dispose()
    exit 0
}
$showEvent = [System.Threading.EventWaitHandle]::new(
    $false,
    [System.Threading.EventResetMode]::AutoReset,
    $showEventName
)

function Get-PropertyValue([object]$Object, [string]$Name, [object]$Default = $null) {
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $Default }
    return $property.Value
}

function Format-BoolState([object]$Value, [string]$TrueText, [string]$FalseText) {
    if ($null -eq $Value) { return "UNKNOWN" }
    if ([bool]$Value) { return $TrueText }
    return $FalseText
}

function Format-Frequency([object]$MHz) {
    if ($null -eq $MHz) { return "--.------ MHz" }
    try { return "{0:F6} MHz" -f [double]$MHz }
    catch { return "--.------ MHz" }
}

function Format-Number([object]$Value, [string]$Format, [string]$Suffix = "") {
    if ($null -eq $Value) { return "--" }
    try { return (("{0:$Format}" -f [double]$Value) + $Suffix) }
    catch { return "--" }
}

function New-WidgetLabel(
    [string]$Text,
    [int]$Left,
    [int]$Top,
    [int]$Width,
    [int]$Height,
    [float]$Size = 9,
    [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular,
    [System.Drawing.ContentAlignment]$Alignment = [System.Drawing.ContentAlignment]::MiddleLeft
) {
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.SetBounds($Left, $Top, $Width, $Height)
    $label.Font = New-Object System.Drawing.Font("Segoe UI", $Size, $Style)
    $label.TextAlign = $Alignment
    $label.ForeColor = [System.Drawing.Color]::FromArgb(226, 232, 240)
    return $label
}

function Get-AgentState {
    $document = Get-Content -LiteralPath $configPath -Raw -ErrorAction Stop | ConvertFrom-Json
    $token = [string]$document.server.control_token
    if ([string]::IsNullOrWhiteSpace($token)) { throw "Bearer token is unavailable" }
    $port = [int]$document.server.bind_port
    $headers = @{ Authorization = "Bearer $token" }
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/v1/state" -Headers $headers -Method Get -TimeoutSec 2
    if (-not $response.success -or -not $response.state) { throw "Agent state is unavailable" }
    return $response.state
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "OM0RX Station Monitor"
$form.ClientSize = New-Object System.Drawing.Size(548, 358)
$form.MinimumSize = New-Object System.Drawing.Size(564, 397)
$form.MaximumSize = New-Object System.Drawing.Size(760, 500)
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::SizableToolWindow
$form.MaximizeBox = $false
$form.ShowInTaskbar = $true
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(15, 23, 42)
$form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::Dpi
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen

$headerPanel = New-Object System.Windows.Forms.Panel
$headerPanel.SetBounds(0, 0, 548, 78)
$headerPanel.Anchor = "Top,Left,Right"
$headerPanel.BackColor = [System.Drawing.Color]::FromArgb(17, 24, 39)
$form.Controls.Add($headerPanel)

$frequencyLabel = New-WidgetLabel "--.------ MHz" 14 7 330 40 23 ([System.Drawing.FontStyle]::Bold)
$headerPanel.Controls.Add($frequencyLabel)
$txStateLabel = New-WidgetLabel "OFFLINE" 390 11 140 32 13 ([System.Drawing.FontStyle]::Bold) ([System.Drawing.ContentAlignment]::MiddleCenter)
$txStateLabel.BackColor = [System.Drawing.Color]::FromArgb(71, 85, 105)
$headerPanel.Controls.Add($txStateLabel)
$modeRouteLabel = New-WidgetLabel "Waiting for station telemetry" 16 47 510 24 9
$modeRouteLabel.ForeColor = [System.Drawing.Color]::FromArgb(148, 163, 184)
$headerPanel.Controls.Add($modeRouteLabel)

$vfoLabel = New-WidgetLabel "VFO A  --    |    VFO B  --" 14 82 520 32 10 ([System.Drawing.FontStyle]::Bold)
$form.Controls.Add($vfoLabel)

$txPowerCaption = New-WidgetLabel "TX POWER" 12 118 168 20 8 ([System.Drawing.FontStyle]::Bold) ([System.Drawing.ContentAlignment]::MiddleCenter)
$swrCaption = New-WidgetLabel "SWR" 190 118 168 20 8 ([System.Drawing.FontStyle]::Bold) ([System.Drawing.ContentAlignment]::MiddleCenter)
$driveCaption = New-WidgetLabel "RF DRIVE" 368 118 168 20 8 ([System.Drawing.FontStyle]::Bold) ([System.Drawing.ContentAlignment]::MiddleCenter)
$form.Controls.AddRange(@($txPowerCaption, $swrCaption, $driveCaption))

$txPowerLabel = New-WidgetLabel "0 W" 12 137 168 48 22 ([System.Drawing.FontStyle]::Bold) ([System.Drawing.ContentAlignment]::MiddleCenter)
$swrLabel = New-WidgetLabel "--" 190 137 168 48 22 ([System.Drawing.FontStyle]::Bold) ([System.Drawing.ContentAlignment]::MiddleCenter)
$driveLabel = New-WidgetLabel "-- W" 368 137 168 48 22 ([System.Drawing.FontStyle]::Bold) ([System.Drawing.ContentAlignment]::MiddleCenter)
foreach ($control in @($txPowerLabel, $swrLabel, $driveLabel)) {
    $control.BackColor = [System.Drawing.Color]::FromArgb(30, 41, 59)
    $form.Controls.Add($control)
}

$kpaLabel = New-WidgetLabel "KPA500  --" 14 190 520 48 9 ([System.Drawing.FontStyle]::Bold)
$katLabel = New-WidgetLabel "KAT500  --" 14 238 520 48 9 ([System.Drawing.FontStyle]::Bold)
$routeLabel = New-WidgetLabel "Route --" 14 287 520 32 9
$form.Controls.AddRange(@($kpaLabel, $katLabel, $routeLabel))

$footerLabel = New-WidgetLabel "Starting..." 14 324 520 24 8
$footerLabel.ForeColor = [System.Drawing.Color]::FromArgb(148, 163, 184)
$form.Controls.Add($footerLabel)

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$topMostItem = New-Object System.Windows.Forms.ToolStripMenuItem("Always on top")
$topMostItem.Checked = $true
$topMostItem.CheckOnClick = $true
$menu.Items.Add($topMostItem) | Out-Null
$resetPositionItem = $menu.Items.Add("Reset position")
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
$closeItem = $menu.Items.Add("Close widget")
$form.ContextMenuStrip = $menu

function Restore-WidgetLayout {
    if (-not (Test-Path -LiteralPath $widgetStatePath)) { return }
    try {
        $layout = Get-Content -LiteralPath $widgetStatePath -Raw | ConvertFrom-Json
        $point = New-Object System.Drawing.Point([int]$layout.left, [int]$layout.top)
        $visible = [System.Windows.Forms.Screen]::AllScreens | Where-Object {
            $_.WorkingArea.Contains($point)
        } | Select-Object -First 1
        if ($visible) {
            $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
            $form.Location = $point
        }
        if ($layout.width -and $layout.height) {
            $form.Size = New-Object System.Drawing.Size([int]$layout.width, [int]$layout.height)
        }
        if ($null -ne $layout.top_most) {
            $form.TopMost = [bool]$layout.top_most
            $topMostItem.Checked = $form.TopMost
        }
    }
    catch { }
}

function Save-WidgetLayout {
    try {
        $layout = [ordered]@{
            left = $form.Left
            top = $form.Top
            width = $form.Width
            height = $form.Height
            top_most = $form.TopMost
        } | ConvertTo-Json
        [System.IO.File]::WriteAllText(
            $widgetStatePath,
            $layout + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    catch { }
}

function Set-WidgetState([object]$State) {
    $radio = Get-PropertyValue $State "radio"
    $elecraft = Get-PropertyValue $State "elecraft"
    $station = Get-PropertyValue $State "station"
    $kpa = Get-PropertyValue $elecraft "kpa500"
    $kat = Get-PropertyValue $elecraft "kat500"
    $path = Get-PropertyValue $station "path"
    $route = Get-PropertyValue $station "route"
    $vfos = Get-PropertyValue $radio "vfos"
    $vfoA = Get-PropertyValue $vfos "A"
    $vfoB = Get-PropertyValue $vfos "B"

    $frequency = Get-PropertyValue $radio "frequency"
    $mode = [string](Get-PropertyValue $radio "mode" "--")
    $mox = [bool](Get-PropertyValue $radio "mox" $false)
    $interlock = [string](Get-PropertyValue $radio "interlock_state" "--")
    $frequencyLabel.Text = Format-Frequency $frequency
    $band = [string](Get-PropertyValue $path "band" "--")
    $alignment = [string](Get-PropertyValue $path "alignment" "unknown")
    $modeRouteLabel.Text = "$mode  |  $band  |  $alignment  |  $interlock"

    if ($mox) {
        $txStateLabel.Text = "TX"
        $txStateLabel.BackColor = [System.Drawing.Color]::FromArgb(185, 28, 28)
        $frequencyLabel.ForeColor = [System.Drawing.Color]::FromArgb(254, 202, 202)
    }
    else {
        $txStateLabel.Text = "RX"
        $txStateLabel.BackColor = [System.Drawing.Color]::FromArgb(22, 101, 52)
        $frequencyLabel.ForeColor = [System.Drawing.Color]::FromArgb(226, 232, 240)
    }

    $aText = if ($vfoA) {
        "A  $(Format-Frequency (Get-PropertyValue $vfoA 'frequency'))  $([string](Get-PropertyValue $vfoA 'mode' '--'))"
    } else { "A  --" }
    $bText = if ($vfoB) {
        "B  $(Format-Frequency (Get-PropertyValue $vfoB 'frequency'))  $([string](Get-PropertyValue $vfoB 'mode' '--'))"
    } else { "B  --" }
    $vfoLabel.Text = "VFO $aText    |    VFO $bText"

    $drive = Get-PropertyValue $radio "drive"
    $driveLabel.Text = if ($null -eq $drive) { "-- W" } else { "{0:0} W" -f [double]$drive }
    $kpaOperate = [bool](Get-PropertyValue $kpa "operate" $false)
    $kpaOutput = Get-PropertyValue $kpa "output_power_w"
    if (-not $mox) {
        $txPowerLabel.Text = "0 W"
    }
    elseif ($kpaOperate -and $null -ne $kpaOutput) {
        $txPowerLabel.Text = "{0:0} W" -f [double]$kpaOutput
    }
    elseif ($null -ne $drive) {
        $txPowerLabel.Text = "~{0:0} W SET" -f [double]$drive
    }
    else {
        $txPowerLabel.Text = "--"
    }

    $kpaSwr = Get-PropertyValue $kpa "swr"
    $katSwr = Get-PropertyValue $kat "swr_sample"
    $kpaSwrLive = [bool](Get-PropertyValue $kpa "swr_live" $false)
    $katSwrLive = [bool](Get-PropertyValue $kat "swr_live" $false)
    $katSwrValid = [bool](Get-PropertyValue $kat "swr_valid" $false)
    if ($kpaSwrLive -and $null -ne $kpaSwr) {
        $swrLabel.Text = "{0:0.00} LIVE" -f [double]$kpaSwr
    }
    elseif (($katSwrLive -or $katSwrValid) -and $null -ne $katSwr) {
        $swrLabel.Text = "{0:0.00} LIVE" -f [double]$katSwr
    }
    elseif ($null -ne $katSwr -and [double]$katSwr -gt 0) {
        $swrLabel.Text = "{0:0.00} LAST" -f [double]$katSwr
    }
    else {
        $swrLabel.Text = "--"
    }

    $kpaState = if ($kpaOperate) { "OPERATE" } else { "STBY" }
    $kpaBand = [string](Get-PropertyValue $kpa "band" "--")
    $kpaTemp = Format-Number (Get-PropertyValue $kpa "temperature_c") "0" " C"
    $kpaVoltage = Format-Number (Get-PropertyValue $kpa "voltage") "0.0" "V"
    $kpaCurrent = Format-Number (Get-PropertyValue $kpa "current") "0.0" "A"
    $kpaFault = [string](Get-PropertyValue $kpa "fault" "--")
    $kpaFirmware = [string](Get-PropertyValue $kpa "firmware" "--")
    $kpaQuality = [string](Get-PropertyValue $kpa "quality" "--")
    $kpaSwrText = if ($null -eq $kpaSwr) { "--" } else { "{0:0.00}" -f [double]$kpaSwr }
    $kpaLabel.Text = "KPA500  $kpaState  |  $kpaBand  |  OUT $(Format-Number $kpaOutput '0' 'W')  |  SWR $kpaSwrText`r`nTEMP $kpaTemp  |  $kpaVoltage / $kpaCurrent  |  FAULT $kpaFault  |  FW $kpaFirmware  |  $kpaQuality"

    $katMode = ([string](Get-PropertyValue $kat "mode" "--")).ToUpperInvariant()
    $katBand = [string](Get-PropertyValue $kat "band" "--")
    $katAntenna = Get-PropertyValue $kat "antenna"
    $katTuning = Format-BoolState (Get-PropertyValue $kat "tuning") "TUNING" "READY"
    $katForward = Format-Number (Get-PropertyValue $kat "forward_adc") "0"
    $katReflected = Format-Number (Get-PropertyValue $kat "reflected_adc") "0"
    $katFault = [string](Get-PropertyValue $kat "fault" "--")
    $katFirmware = [string](Get-PropertyValue $kat "firmware" "--")
    $katBypass = Format-BoolState (Get-PropertyValue $kat "bypass") "BYPASS" "MATCH"
    $katKey = Format-BoolState (Get-PropertyValue $kat "amp_key_interrupted") "KEY OPEN" "KEY OK"
    $katQuality = [string](Get-PropertyValue $kat "quality" "--")
    $katSwrText = if ($null -eq $katSwr) { "--" } else { "{0:0.00}" -f [double]$katSwr }
    $katLabel.Text = "KAT500  $katMode  |  $katBand  |  ANT$katAntenna  |  $katTuning  |  SWR $katSwrText`r`nFWD/REF $katForward/$katReflected  |  $katBypass  |  $katKey  |  FAULT $katFault  |  FW $katFirmware  |  $katQuality"

    $routeName = [string](Get-PropertyValue $path "route_label" "Route unavailable")
    $activeDrive = Get-PropertyValue $route "active_drive_w"
    $paAllowed = Format-BoolState (Get-PropertyValue $route "amplifier_allowed") "PA allowed" "barefoot"
    $routeLabel.Text = "$routeName  |  $paAllowed  |  policy $(Format-Number $activeDrive '0' 'W')"

    $alarms = Get-PropertyValue $station "alarms"
    $alarmCount = Get-PropertyValue $alarms "active_count" 0
    $updated = [DateTime]::Now.ToString("HH:mm:ss")
    $footerLabel.Text = "Updated $updated  |  alarms $alarmCount  |  commissioned $(Get-PropertyValue $station 'commissioned' $false)"
}

function Set-WidgetError([string]$Message) {
    $txStateLabel.Text = "OFFLINE"
    $txStateLabel.BackColor = [System.Drawing.Color]::FromArgb(127, 29, 29)
    $frequencyLabel.Text = "--.------ MHz"
    $modeRouteLabel.Text = $Message
    $footerLabel.Text = "Retrying... $([DateTime]::Now.ToString('HH:mm:ss'))"
}

function Update-Widget {
    try { Set-WidgetState (Get-AgentState) }
    catch { Set-WidgetError $_.Exception.Message }
}

$topMostItem.add_CheckedChanged({
    $form.TopMost = $topMostItem.Checked
    Save-WidgetLayout
})
$resetPositionItem.add_Click({
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        [int]($screen.Right - $form.Width - 20),
        [int]($screen.Top + 20)
    )
})
$closeItem.add_Click({ $form.Close() })
$form.add_FormClosing({ Save-WidgetLayout })

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 750
$timer.add_Tick({
    if ($showEvent.WaitOne(0)) {
        $form.Show()
        $form.WindowState = [System.Windows.Forms.FormWindowState]::Normal
        $form.Activate()
    }
    Update-Widget
})

if ($SmokeTest) {
    try {
        $fakeState = @'
{
  "radio": {"frequency":14.074,"mode":"DIGU","drive":25,"mox":true,"interlock_state":"TRANSMITTING","vfos":{"A":{"frequency":14.074,"mode":"DIGU"},"B":{"frequency":14.08,"mode":"DIGU"}}},
  "elecraft":{"kpa500":{"operate":true,"band":"20m","output_power_w":450,"swr":1.2,"swr_live":true,"temperature_c":35,"voltage":69.5,"current":18.2,"fault":"00"},"kat500":{"mode":"auto","band":"20m","antenna":1,"tuning":false,"forward_adc":110,"reflected_adc":4,"fault":"0","swr_sample":1.2,"swr_live":true,"swr_valid":true}},
  "station":{"commissioned":true,"route":{"active_drive_w":25,"amplifier_allowed":true},"path":{"band":"20m","alignment":"confirmed","route_label":"FLEX ANT1 to KPA500 to KAT500 to ANT1"},"alarms":{"active_count":0}}
}
'@ | ConvertFrom-Json
        Set-WidgetState $fakeState
        if ($txStateLabel.Text -ne "TX" -or $txPowerLabel.Text -ne "450 W" -or $swrLabel.Text -notlike "1.20*") {
            throw "Transmit telemetry did not render correctly"
        }
        Write-Output "Station widget smoke test passed"
        exit 0
    }
    catch {
        Write-Error "Station widget smoke test failed: $($_.Exception.Message)"
        exit 1
    }
    finally {
        $showEvent.Dispose()
        $mutex.ReleaseMutex()
        $mutex.Dispose()
        $form.Dispose()
    }
}

try {
    Restore-WidgetLayout
    Update-Widget
    $timer.Start()
    [System.Windows.Forms.Application]::EnableVisualStyles()
    [System.Windows.Forms.Application]::Run($form)
}
finally {
    $timer.Stop()
    $timer.Dispose()
    $showEvent.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    $form.Dispose()
}
