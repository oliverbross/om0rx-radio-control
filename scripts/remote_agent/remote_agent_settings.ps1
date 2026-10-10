param(
    [string]$Config = "",
    [string]$Python = "python.exe",
    [string]$AgentTaskName = "OM0RX Remote Station Agent",
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$configPath = if ($Config) {
    [System.IO.Path]::GetFullPath($Config)
}
else {
    Join-Path $env:APPDATA "OM0RX Remote Station\agent.json"
}
$bands = @("160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m")

function Get-BooleanProperty([object]$Object, [string]$Name, [bool]$Default) {
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $Default }
    return [bool]$property.Value
}

function Get-StringProperty([object]$Object, [string]$Name, [string]$Default) {
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $Default }
    return [string]$property.Value
}

function New-Label([string]$Text, [int]$Left, [int]$Top, [int]$Width = 145) {
    $control = New-Object System.Windows.Forms.Label
    $control.Text = $Text
    $control.Left = $Left
    $control.Top = $Top
    $control.Width = $Width
    $control.Height = 24
    $control.TextAlign = "MiddleLeft"
    return $control
}

function New-TextBox([string]$Text, [int]$Left, [int]$Top, [int]$Width = 240) {
    $control = New-Object System.Windows.Forms.TextBox
    $control.Text = $Text
    $control.Left = $Left
    $control.Top = $Top
    $control.Width = $Width
    return $control
}

function New-Numeric([decimal]$Value, [decimal]$Minimum, [decimal]$Maximum, [int]$Left, [int]$Top, [int]$Decimals = 0) {
    $control = New-Object System.Windows.Forms.NumericUpDown
    $control.Minimum = $Minimum
    $control.Maximum = $Maximum
    $control.DecimalPlaces = $Decimals
    if ($Decimals -gt 0) { $control.Increment = [decimal]0.1 }
    $control.Value = [Math]::Min($Maximum, [Math]::Max($Minimum, $Value))
    $control.Left = $Left
    $control.Top = $Top
    $control.Width = 110
    return $control
}

function New-CheckBox([string]$Text, [bool]$Checked, [int]$Left, [int]$Top, [int]$Width = 250) {
    $control = New-Object System.Windows.Forms.CheckBox
    $control.Text = $Text
    $control.Checked = $Checked
    $control.Left = $Left
    $control.Top = $Top
    $control.Width = $Width
    $control.Height = 24
    return $control
}

function New-ControlToken {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) }
    finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Test-And-SaveDocument([System.Collections.IDictionary]$Document) {
    $directory = Split-Path -Parent $configPath
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    $temporary = Join-Path $directory ("agent.{0}.tmp" -f [Guid]::NewGuid().ToString("N"))
    try {
        $json = $Document | ConvertTo-Json -Depth 12
        [System.IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
        $output = @(& $Python -m remote_station check --config $temporary 2>&1)
        if ($LASTEXITCODE -ne 0) {
            throw (($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
        }
        if (Test-Path -LiteralPath $configPath) {
            [System.IO.File]::Replace($temporary, $configPath, ($configPath + ".bak"), $true)
        }
        else {
            Move-Item -LiteralPath $temporary -Destination $configPath
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

try {
    $document = Get-Content -LiteralPath $configPath -Raw -ErrorAction Stop | ConvertFrom-Json
}
catch {
    [System.Windows.Forms.MessageBox]::Show(
        "The agent configuration could not be opened.`r`n`r`n$($_.Exception.Message)",
        "OM0RX Remote Station Settings",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

$originalCommissioned = Get-BooleanProperty $document.station "commissioned" $false

$form = New-Object System.Windows.Forms.Form
$form.Text = "OM0RX Remote Station Settings"
$form.ClientSize = New-Object System.Drawing.Size(980, 710)
$form.MinimumSize = New-Object System.Drawing.Size(900, 650)
$form.StartPosition = "CenterScreen"
$form.ShowInTaskbar = $true
$form.AutoScaleMode = "Dpi"

$tabs = New-Object System.Windows.Forms.TabControl
$tabs.Dock = "Fill"
$tabs.Padding = New-Object System.Drawing.Point(14, 6)
$form.Controls.Add($tabs)

$connectionsTab = New-Object System.Windows.Forms.TabPage
$connectionsTab.Text = "Connections and security"
$connectionsTab.AutoScroll = $true
$tabs.TabPages.Add($connectionsTab) | Out-Null

$serverGroup = New-Object System.Windows.Forms.GroupBox
$serverGroup.Text = "Local API (publish only through Tailscale Serve)"
$serverGroup.SetBounds(18, 18, 920, 135)
$connectionsTab.Controls.Add($serverGroup)

$serverGroup.Controls.Add((New-Label "Bind address" 18 30))
$bindHost = New-Object System.Windows.Forms.ComboBox
$bindHost.DropDownStyle = "DropDownList"
$bindHost.Items.AddRange(@("127.0.0.1", "localhost", "::1"))
$bindHost.SelectedItem = [string]$document.server.bind_host
if ($bindHost.SelectedIndex -lt 0) { $bindHost.SelectedIndex = 0 }
$bindHost.SetBounds(165, 30, 180, 24)
$serverGroup.Controls.Add($bindHost)
$serverGroup.Controls.Add((New-Label "Port" 380 30 55))
$bindPort = New-Numeric ([decimal]$document.server.bind_port) 1 65535 440 30
$serverGroup.Controls.Add($bindPort)
$serverGroup.Controls.Add((New-Label "Bearer token" 18 72))
$tokenBox = New-TextBox ([string]$document.server.control_token) 165 72 500
$tokenBox.UseSystemPasswordChar = $true
$serverGroup.Controls.Add($tokenBox)
$showToken = New-CheckBox "Show" $false 680 70 70
$showToken.add_CheckedChanged({ $tokenBox.UseSystemPasswordChar = -not $showToken.Checked })
$serverGroup.Controls.Add($showToken)
$copyToken = New-Object System.Windows.Forms.Button
$copyToken.Text = "Copy"
$copyToken.SetBounds(750, 69, 70, 28)
$copyToken.add_Click({ [System.Windows.Forms.Clipboard]::SetText($tokenBox.Text) })
$serverGroup.Controls.Add($copyToken)
$newToken = New-Object System.Windows.Forms.Button
$newToken.Text = "Regenerate..."
$newToken.SetBounds(825, 69, 85, 28)
$newToken.add_Click({
    $choice = [System.Windows.Forms.MessageBox]::Show(
        "Regenerating the token disconnects every client until its saved credential is updated. Continue?",
        "Regenerate bearer token",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    )
    if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) { $tokenBox.Text = New-ControlToken }
})
$serverGroup.Controls.Add($newToken)

$flexGroup = New-Object System.Windows.Forms.GroupBox
$flexGroup.Text = "FLEX-8400"
$flexGroup.SetBounds(18, 165, 920, 110)
$connectionsTab.Controls.Add($flexGroup)
$flexGroup.Controls.Add((New-Label "LAN address" 18 32))
$flexHost = New-TextBox ([string]$document.flex.host) 165 32 180
$flexGroup.Controls.Add($flexHost)
$flexGroup.Controls.Add((New-Label "TCP port" 380 32 70))
$flexPort = New-Numeric ([decimal]$document.flex.port) 1 65535 455 32
$flexGroup.Controls.Add($flexPort)
$flexGroup.Controls.Add((New-Label "Slice ID" 590 32 65))
$sliceId = New-Numeric ([decimal]$document.flex.slice_id) 0 7 660 32
$flexGroup.Controls.Add($sliceId)
$flexGroup.Controls.Add((New-Label "GUI station name" 18 70))
$stationName = New-TextBox ([string]$document.flex.station_name) 165 70 180
$flexGroup.Controls.Add($stationName)
$flexAntennaEnabled = New-CheckBox "Enforce per-band FLEX antenna policy" (Get-BooleanProperty $document.flex.antenna_policy "enabled" $true) 380 68 300
$flexGroup.Controls.Add($flexAntennaEnabled)

$accessoryGroup = New-Object System.Windows.Forms.GroupBox
$accessoryGroup.Text = "Elecraft accessories"
$accessoryGroup.SetBounds(18, 287, 920, 150)
$connectionsTab.Controls.Add($accessoryGroup)
$kpaEnabled = New-CheckBox "KPA500 enabled" (Get-BooleanProperty $document.kpa500 "enabled" $true) 18 30 145
$accessoryGroup.Controls.Add($kpaEnabled)
$accessoryGroup.Controls.Add((New-Label "COM port" 180 30 75))
$kpaPort = New-TextBox ([string]$document.kpa500.port) 255 30 95
$accessoryGroup.Controls.Add($kpaPort)
$accessoryGroup.Controls.Add((New-Label "Baud" 380 30 50))
$kpaBaud = New-Numeric ([decimal]$document.kpa500.baudrate) 300 1000000 435 30
$accessoryGroup.Controls.Add($kpaBaud)
$katEnabled = New-CheckBox "KAT500 enabled" (Get-BooleanProperty $document.kat500 "enabled" $true) 18 70 145
$accessoryGroup.Controls.Add($katEnabled)
$accessoryGroup.Controls.Add((New-Label "COM port" 180 70 75))
$katPort = New-TextBox ([string]$document.kat500.port) 255 70 95
$accessoryGroup.Controls.Add($katPort)
$accessoryGroup.Controls.Add((New-Label "Baud" 380 70 50))
$katBaud = New-Numeric ([decimal]$document.kat500.baudrate) 300 1000000 435 70
$accessoryGroup.Controls.Add($katBaud)
$followRadio = New-CheckBox "Automatically follow the observed radio band" (Get-BooleanProperty $document.station "follow_radio" $true) 18 108 330
$accessoryGroup.Controls.Add($followRadio)
$accessoryGroup.Controls.Add((New-Label "Digital PA default" 380 108 120))
$digitalPolicy = New-Object System.Windows.Forms.ComboBox
$digitalPolicy.DropDownStyle = "DropDownList"
$digitalPolicy.Items.AddRange(@("operate", "standby"))
$digitalPolicy.SelectedItem = Get-StringProperty $document.station "digital_kpa_policy" "operate"
if ($digitalPolicy.SelectedIndex -lt 0) { $digitalPolicy.SelectedIndex = 0 }
$digitalPolicy.SetBounds(510, 108, 120, 24)
$accessoryGroup.Controls.Add($digitalPolicy)

$connectionNote = New-Label "Changes are validated and saved locally. They take effect only after the agent is deliberately restarted." 18 454 900
$connectionNote.ForeColor = [System.Drawing.Color]::DarkBlue
$connectionsTab.Controls.Add($connectionNote)

$bandsTab = New-Object System.Windows.Forms.TabPage
$bandsTab.Text = "Band, antenna and RF policy"
$tabs.TabPages.Add($bandsTab) | Out-Null

$grid = New-Object System.Windows.Forms.DataGridView
$grid.Dock = "Fill"
$grid.AllowUserToAddRows = $false
$grid.AllowUserToDeleteRows = $false
$grid.AllowUserToOrderColumns = $false
$grid.AutoSizeColumnsMode = "Fill"
$grid.RowHeadersVisible = $false
$grid.SelectionMode = "CellSelect"
$grid.EditMode = "EditOnEnter"
$grid.Columns.Add("Band", "Band") | Out-Null
$grid.Columns[0].ReadOnly = $true
$flexColumn = New-Object System.Windows.Forms.DataGridViewComboBoxColumn
$flexColumn.Name = "FlexAntenna"
$flexColumn.HeaderText = "FLEX TX"
$flexColumn.Items.AddRange(@("ANT1", "ANT2", "XVTR"))
$grid.Columns.Add($flexColumn) | Out-Null
$katColumn = New-Object System.Windows.Forms.DataGridViewComboBoxColumn
$katColumn.Name = "KatOutput"
$katColumn.HeaderText = "KAT output"
$katColumn.Items.AddRange(@("1", "2", "3"))
$grid.Columns.Add($katColumn) | Out-Null
$paAllowedColumn = New-Object System.Windows.Forms.DataGridViewCheckBoxColumn
$paAllowedColumn.Name = "PaAllowed"
$paAllowedColumn.HeaderText = "PA allowed"
$grid.Columns.Add($paAllowedColumn) | Out-Null
$grid.Columns.Add("PaDrive", "PA drive W") | Out-Null
$grid.Columns.Add("BarefootDrive", "Barefoot W") | Out-Null
$digitalAllowedColumn = New-Object System.Windows.Forms.DataGridViewCheckBoxColumn
$digitalAllowedColumn.Name = "DigitalPaAllowed"
$digitalAllowedColumn.HeaderText = "Digital PA"
$grid.Columns.Add($digitalAllowedColumn) | Out-Null
$grid.Columns.Add("DigitalDrive", "Digital drive W") | Out-Null

$paBands = @($document.station.amplifier_allowed_bands | ForEach-Object { [string]$_ })
$digitalPaBands = @($document.station.digital_amplifier_allowed_bands | ForEach-Object { [string]$_ })
foreach ($band in $bands) {
    $index = $grid.Rows.Add()
    $row = $grid.Rows[$index]
    $row.Cells["Band"].Value = $band
    $row.Cells["FlexAntenna"].Value = [string]$document.flex.antenna_policy.bands.$band
    $row.Cells["KatOutput"].Value = [string]$document.station.kat_antenna_policy.$band
    $row.Cells["PaAllowed"].Value = $paBands -contains $band
    $row.Cells["PaDrive"].Value = [string]$document.station.amplifier_drive_w.$band
    $row.Cells["BarefootDrive"].Value = [string]$document.station.barefoot_drive_w.$band
    $row.Cells["DigitalPaAllowed"].Value = $digitalPaBands -contains $band
    $row.Cells["DigitalDrive"].Value = [string]$document.station.digital_amplifier_drive_w.$band
}

$bandsPanel = New-Object System.Windows.Forms.Panel
$bandsPanel.Dock = "Bottom"
$bandsPanel.Height = 86
$bandsPanel.Controls.Add((New-Label "KAT output 1 name" 12 10 130))
$katName1 = New-TextBox ([string]$document.station.kat_antenna_names.'1') 145 10 145
$bandsPanel.Controls.Add($katName1)
$bandsPanel.Controls.Add((New-Label "Output 2" 315 10 70))
$katName2 = New-TextBox ([string]$document.station.kat_antenna_names.'2') 385 10 145
$bandsPanel.Controls.Add($katName2)
$bandsPanel.Controls.Add((New-Label "Output 3" 555 10 70))
$katName3 = New-TextBox ([string]$document.station.kat_antenna_names.'3') 625 10 145
$bandsPanel.Controls.Add($katName3)
$bandHelp = New-Label "PA allowed is the per-band enable switch. All RF values are validated from 1 through 100 watts." 12 48 900
$bandHelp.ForeColor = [System.Drawing.Color]::DarkBlue
$bandsPanel.Controls.Add($bandHelp)
$bandsTab.Controls.Add($grid)
$bandsTab.Controls.Add($bandsPanel)

$safetyTab = New-Object System.Windows.Forms.TabPage
$safetyTab.Text = "Tuning and commissioning"
$tabs.TabPages.Add($safetyTab) | Out-Null

$tuningGroup = New-Object System.Windows.Forms.GroupBox
$tuningGroup.Text = "Guarded tuner transaction"
$tuningGroup.SetBounds(18, 18, 920, 145)
$safetyTab.Controls.Add($tuningGroup)
$tuningGroup.Controls.Add((New-Label "Tune power (W)" 18 35))
$tunePower = New-Numeric ([decimal]$document.station.tune_power_w) 1 100 175 35
$tuningGroup.Controls.Add($tunePower)
$tuningGroup.Controls.Add((New-Label "Target SWR" 330 35 100))
$targetSwr = New-Numeric ([decimal]$document.station.tune_target_swr) 0.1 20 440 35 1
$tuningGroup.Controls.Add($targetSwr)
$tuningGroup.Controls.Add((New-Label "Abort SWR" 610 35 95))
$abortSwr = New-Numeric ([decimal]$document.station.tune_abort_swr) 0.1 20 710 35 1
$tuningGroup.Controls.Add($abortSwr)
$tuningGroup.Controls.Add((New-Label "Timeout (seconds)" 18 82))
$tuneTimeout = New-Numeric ([decimal]$document.station.tune_timeout_seconds) 1 600 175 82 1
$tuningGroup.Controls.Add($tuneTimeout)

$commissionGroup = New-Object System.Windows.Forms.GroupBox
$commissionGroup.Text = "Transmit commissioning interlock"
$commissionGroup.SetBounds(18, 180, 920, 245)
$safetyTab.Controls.Add($commissionGroup)
$commissioned = New-CheckBox "Station physically commissioned — allow guarded transmit controls after restart" $originalCommissioned 18 35 650
$commissioned.Font = New-Object System.Drawing.Font($commissioned.Font, [System.Drawing.FontStyle]::Bold)
$commissionGroup.Controls.Add($commissioned)
$warning = New-Label "WARNING: Enable only after checking the physical RF route, antennas, KPA/KAT key interrupt, drive levels, emergency receive recovery, and a dummy-load transmit test." 18 78 870
$warning.Height = 58
$warning.ForeColor = [System.Drawing.Color]::DarkRed
$commissionGroup.Controls.Add($warning)
$commissionText = New-Label "Enabling this switch does not key PTT and does not restart the agent. Saving it requires typing COMMISSION. The Windows agent still performs fresh route, alarm, amplifier, tuner and radio-state checks before every transmit action." 18 140 870
$commissionText.Height = 75
$commissionGroup.Controls.Add($commissionText)

$footer = New-Object System.Windows.Forms.Panel
$footer.Dock = "Bottom"
$footer.Height = 58
$footer.Padding = New-Object System.Windows.Forms.Padding(10)
$form.Controls.Add($footer)
$footer.BringToFront()

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$cancelButton.SetBounds(850, 14, 105, 32)
$footer.Controls.Add($cancelButton)
$form.CancelButton = $cancelButton

$saveButton = New-Object System.Windows.Forms.Button
$saveButton.Text = "Save"
$saveButton.SetBounds(615, 14, 105, 32)
$footer.Controls.Add($saveButton)

$saveRestartButton = New-Object System.Windows.Forms.Button
$saveRestartButton.Text = "Save and restart agent..."
$saveRestartButton.SetBounds(725, 14, 120, 32)
$footer.Controls.Add($saveRestartButton)

$statusLabel = New-Label "Ready" 10 14 580
$footer.Controls.Add($statusLabel)

function Read-PowerCell([System.Windows.Forms.DataGridViewRow]$Row, [string]$ColumnName, [string]$Band) {
    $raw = [string]$Row.Cells[$ColumnName].Value
    $parsed = 0
    if (-not [int]::TryParse($raw, [ref]$parsed) -or $parsed -lt 1 -or $parsed -gt 100) {
        throw "$Band $ColumnName must be a whole number from 1 through 100 watts."
    }
    return $parsed
}

function Build-Document {
    if ([string]::IsNullOrWhiteSpace($flexHost.Text)) { throw "FLEX LAN address is required." }
    if ([string]::IsNullOrWhiteSpace($stationName.Text)) { throw "FLEX GUI station name is required." }
    if ([string]::IsNullOrWhiteSpace($kpaPort.Text)) { throw "KPA500 COM port is required." }
    if ([string]::IsNullOrWhiteSpace($katPort.Text)) { throw "KAT500 COM port is required." }
    if ($tokenBox.Text.Length -lt 32 -or $tokenBox.Text -match '\s') { throw "Bearer token must contain at least 32 characters and no whitespace." }
    if ($abortSwr.Value -le $targetSwr.Value) { throw "Abort SWR must be greater than target SWR." }
    if ($commissioned.Checked -and (-not $kpaEnabled.Checked -or -not $katEnabled.Checked)) {
        throw "A commissioned station requires both KPA500 and KAT500 enabled."
    }
    if ($commissioned.Checked -and (-not $followRadio.Checked -or -not $flexAntennaEnabled.Checked)) {
        throw "A commissioned station requires route following and FLEX antenna policy enforcement."
    }

    $flexBands = [ordered]@{}
    $katBands = [ordered]@{}
    $paAllowed = [System.Collections.Generic.List[string]]::new()
    $paDrive = [ordered]@{}
    $barefootDrive = [ordered]@{}
    $digitalAllowed = [System.Collections.Generic.List[string]]::new()
    $digitalDrive = [ordered]@{}
    foreach ($row in $grid.Rows) {
        $band = [string]$row.Cells["Band"].Value
        $flexBands[$band] = [string]$row.Cells["FlexAntenna"].Value
        $katOutput = 0
        if (-not [int]::TryParse([string]$row.Cells["KatOutput"].Value, [ref]$katOutput)) {
            throw "$band KAT output must be 1, 2, or 3."
        }
        $katBands[$band] = $katOutput
        if ([bool]$row.Cells["PaAllowed"].Value) { $paAllowed.Add($band) }
        $paDrive[$band] = Read-PowerCell $row "PaDrive" $band
        $barefootDrive[$band] = Read-PowerCell $row "BarefootDrive" $band
        if ([bool]$row.Cells["DigitalPaAllowed"].Value) { $digitalAllowed.Add($band) }
        $digitalDrive[$band] = Read-PowerCell $row "DigitalDrive" $band
    }
    if ([string]::IsNullOrWhiteSpace($katName1.Text) -or [string]::IsNullOrWhiteSpace($katName2.Text) -or [string]::IsNullOrWhiteSpace($katName3.Text)) {
        throw "KAT outputs 1, 2, and 3 must all have names."
    }

    return [ordered]@{
        schema_version = 1
        server = [ordered]@{
            bind_host = [string]$bindHost.SelectedItem
            bind_port = [int]$bindPort.Value
            control_token = $tokenBox.Text
        }
        flex = [ordered]@{
            model = "FLEX-8400"
            host = $flexHost.Text.Trim()
            port = [int]$flexPort.Value
            slice_id = [int]$sliceId.Value
            station_name = $stationName.Text.Trim()
            antenna_policy = [ordered]@{
                enabled = $flexAntennaEnabled.Checked
                bands = $flexBands
            }
        }
        kpa500 = [ordered]@{
            enabled = $kpaEnabled.Checked
            port = $kpaPort.Text.Trim()
            baudrate = [int]$kpaBaud.Value
        }
        kat500 = [ordered]@{
            enabled = $katEnabled.Checked
            port = $katPort.Text.Trim()
            baudrate = [int]$katBaud.Value
        }
        station = [ordered]@{
            commissioned = $commissioned.Checked
            follow_radio = $followRadio.Checked
            digital_kpa_policy = [string]$digitalPolicy.SelectedItem
            kat_antenna_policy = $katBands
            kat_antenna_names = [ordered]@{ "1" = $katName1.Text.Trim(); "2" = $katName2.Text.Trim(); "3" = $katName3.Text.Trim() }
            amplifier_allowed_bands = @($paAllowed)
            amplifier_drive_w = $paDrive
            barefoot_drive_w = $barefootDrive
            digital_amplifier_allowed_bands = @($digitalAllowed)
            digital_amplifier_drive_w = $digitalDrive
            tune_power_w = [int]$tunePower.Value
            tune_target_swr = [double]$targetSwr.Value
            tune_abort_swr = [double]$abortSwr.Value
            tune_timeout_seconds = [double]$tuneTimeout.Value
        }
    }
}

function Save-Settings([bool]$Restart) {
    try {
        $grid.EndEdit()
        if (-not $originalCommissioned -and $commissioned.Checked) {
            $confirmation = [Microsoft.VisualBasic.Interaction]::InputBox(
                "Type COMMISSION to confirm that physical commissioning and dummy-load checks are complete.",
                "Enable guarded transmit controls",
                ""
            )
            if ($confirmation -cne "COMMISSION") { throw "Commissioning was not confirmed; no settings were saved." }
        }
        $statusLabel.Text = "Validating..."
        $form.UseWaitCursor = $true
        [System.Windows.Forms.Application]::DoEvents()
        $newDocument = Build-Document
        Test-And-SaveDocument $newDocument
        $statusLabel.Text = "Saved. Restart required."
        if ($Restart) {
            $choice = [System.Windows.Forms.MessageBox]::Show(
                "Settings are valid and saved. Restart the agent now? Startup performs station safety recovery and reconnects all configured hardware.",
                "Restart OM0RX Remote Station Agent",
                [System.Windows.Forms.MessageBoxButtons]::YesNo,
                [System.Windows.Forms.MessageBoxIcon]::Warning
            )
            if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) {
                Stop-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
                $deadline = [DateTime]::UtcNow.AddSeconds(10)
                do {
                    [System.Windows.Forms.Application]::DoEvents()
                    Start-Sleep -Milliseconds 200
                    $state = (Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop).State.ToString()
                } while ($state -eq "Running" -and [DateTime]::UtcNow -lt $deadline)
                Start-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
                [System.Windows.Forms.MessageBox]::Show("Settings saved and the agent restart was requested.") | Out-Null
                $form.Close()
            }
        }
        else {
            [System.Windows.Forms.MessageBox]::Show(
                "Settings were validated and saved. They will take effect after you restart the agent from the tray.",
                "OM0RX Remote Station Settings",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Information
            ) | Out-Null
            $form.Close()
        }
    }
    catch {
        $statusLabel.Text = "Not saved"
        [System.Windows.Forms.MessageBox]::Show(
            "Settings were not saved.`r`n`r`n$($_.Exception.Message)",
            "OM0RX Remote Station Settings",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
    finally {
        $form.UseWaitCursor = $false
    }
}

$saveButton.add_Click({ Save-Settings $false })
$saveRestartButton.add_Click({ Save-Settings $true })

if ($SmokeTest) {
    try {
        $grid.EndEdit() | Out-Null
        Test-And-SaveDocument (Build-Document)
        Write-Output "Settings GUI smoke test passed"
        exit 0
    }
    catch {
        Write-Error "Settings GUI smoke test failed: $($_.Exception.Message)"
        exit 1
    }
}

[System.Windows.Forms.Application]::EnableVisualStyles()
[System.Windows.Forms.Application]::Run($form)
