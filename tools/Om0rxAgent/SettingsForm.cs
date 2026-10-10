namespace Om0rxAgent;

public sealed class SettingsForm : Form
{
    private readonly AgentSettings _settings;
    private readonly TextBox _projectRoot = new();
    private readonly TextBox _host = new();
    private readonly NumericUpDown _port = new();
    private readonly ComboBox _appEnv = new();
    private readonly CheckBox _startServices = new();
    private readonly CheckBox _autoRestart = new();
    private readonly CheckBox _startLauncher = new();
    private readonly CheckBox _manageDocker = new();
    private readonly CheckBox _rememberWindowLayout = new();
    private readonly ComboBox _digitalEngine = new();
    private readonly CheckBox _startWsjtz = new();
    private readonly CheckBox _enableAutoCall = new();
    private readonly NumericUpDown _autoCallLimit = new();
    private readonly NumericUpDown _interval = new();
    private readonly NumericUpDown _threshold = new();
    private readonly NumericUpDown _cooldown = new();
    private readonly TextBox _composeFile = new();
    private readonly TextBox _watchedProcesses = new();

    public SettingsForm(AgentSettings settings)
    {
        _settings = settings;
        Text = "OM0RX Agent Settings";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterParent;
        Size = new Size(680, 660);

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 3,
            RowCount = 18,
            Padding = new Padding(12),
        };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 160));
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        Controls.Add(root);

        AddTextRow(root, 0, "Project root", _projectRoot, BrowseProjectRoot);
        AddTextRow(root, 1, "Backend host", _host);
        AddNumberRow(root, 2, "Backend port", _port, 1, 65535);
        AddComboRow(root, 3, "App environment", _appEnv, new[] { "local", "development" });
        AddCheckRow(root, 4, _startServices, "Start services when agent starts");
        AddCheckRow(root, 5, _autoRestart, "Auto restart failed services");
        AddCheckRow(root, 6, _startLauncher, "Start desktop/browser launcher");
        AddCheckRow(root, 7, _manageDocker, "Manage Docker/Postgres compose");
        AddCheckRow(root, 8, _rememberWindowLayout, "Remember app window positions");
        AddComboRow(root, 9, "Digital engine", _digitalEngine, new[] { "none", "wsjtz", "mshv_auto_dx" });
        AddCheckRow(root, 10, _startWsjtz, "Start selected digital engine with agent");
        AddCheckRow(root, 11, _enableAutoCall, "Enable WSJT-Z Auto Call after startup");
        AddNumberRow(root, 12, "Auto Call limit", _autoCallLimit, 0, 99);
        AddNumberRow(root, 13, "Check interval sec", _interval, 2, 300);
        AddNumberRow(root, 14, "Failures before restart", _threshold, 1, 20);
        AddNumberRow(root, 15, "Restart cooldown sec", _cooldown, 10, 600);
        AddTextRow(root, 16, "Compose file", _composeFile);
        AddTextRow(root, 17, "Watched processes", _watchedProcesses);

        var buttons = new FlowLayoutPanel
        {
            Dock = DockStyle.Bottom,
            FlowDirection = FlowDirection.RightToLeft,
            Padding = new Padding(12),
            AutoSize = true,
        };
        Controls.Add(buttons);

        var ok = new Button { Text = "Save", DialogResult = DialogResult.OK, AutoSize = true, MinimumSize = new Size(88, 32) };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, AutoSize = true, MinimumSize = new Size(88, 32) };
        buttons.Controls.Add(ok);
        buttons.Controls.Add(cancel);
        AcceptButton = ok;
        CancelButton = cancel;

        ok.Click += (_, _) => SaveToSettings();
        LoadFromSettings();
    }

    private void LoadFromSettings()
    {
        _projectRoot.Text = _settings.ProjectRoot;
        _host.Text = _settings.BackendHost;
        _port.Value = Clamp(_settings.BackendPort, _port.Minimum, _port.Maximum);
        _appEnv.SelectedItem = _settings.AppEnv;
        if (_appEnv.SelectedIndex < 0) _appEnv.SelectedIndex = 0;
        _startServices.Checked = _settings.StartServicesWithAgent;
        _autoRestart.Checked = _settings.AutoRestart;
        _startLauncher.Checked = _settings.StartLauncher;
        _manageDocker.Checked = _settings.ManageDocker;
        _rememberWindowLayout.Checked = _settings.RememberWindowLayout;
        _digitalEngine.SelectedItem = _settings.DigitalEngineProvider;
        if (_digitalEngine.SelectedIndex < 0) _digitalEngine.SelectedItem = "none";
        _startWsjtz.Checked = _settings.StartWsjtzWithAgent;
        _enableAutoCall.Checked = _settings.EnableAutoCallOnStartup;
        _autoCallLimit.Value = Clamp(_settings.AutoCallLimit, _autoCallLimit.Minimum, _autoCallLimit.Maximum);
        _interval.Value = Clamp(_settings.CheckIntervalSeconds, _interval.Minimum, _interval.Maximum);
        _threshold.Value = Clamp(_settings.FailureRestartThreshold, _threshold.Minimum, _threshold.Maximum);
        _cooldown.Value = Clamp(_settings.RestartCooldownSeconds, _cooldown.Minimum, _cooldown.Maximum);
        _composeFile.Text = _settings.DockerComposeFile;
        _watchedProcesses.Text = string.Join(", ", _settings.WatchedProcessNames);
    }

    private void SaveToSettings()
    {
        _settings.ProjectRoot = Path.GetFullPath(_projectRoot.Text.Trim());
        _settings.BackendHost = _host.Text.Trim();
        _settings.BackendPort = (int)_port.Value;
        _settings.AppEnv = _appEnv.SelectedItem?.ToString() ?? "local";
        _settings.StartServicesWithAgent = _startServices.Checked;
        _settings.AutoRestart = _autoRestart.Checked;
        _settings.StartLauncher = _startLauncher.Checked;
        _settings.ManageDocker = _manageDocker.Checked;
        _settings.RememberWindowLayout = _rememberWindowLayout.Checked;
        _settings.DigitalEngineProvider = AgentSettings.NormalizeDigitalProvider(_digitalEngine.SelectedItem?.ToString(), false);
        _settings.StartWsjtzWithAgent = _digitalEngine.SelectedItem?.ToString() != "none" && _startWsjtz.Checked;
        _settings.EnableAutoCallOnStartup = _digitalEngine.SelectedItem?.ToString() == "wsjtz" && _enableAutoCall.Checked;
        _settings.AutoCallLimit = (int)_autoCallLimit.Value;
        _settings.CheckIntervalSeconds = (int)_interval.Value;
        _settings.FailureRestartThreshold = (int)_threshold.Value;
        _settings.RestartCooldownSeconds = (int)_cooldown.Value;
        _settings.DockerComposeFile = _composeFile.Text.Trim();
        _settings.WatchedProcessNames = _watchedProcesses.Text
            .Split(new[] { ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
        _settings.Save();
    }

    private void BrowseProjectRoot()
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "Select the om0rx-radio-control project folder",
            SelectedPath = Directory.Exists(_projectRoot.Text) ? _projectRoot.Text : _settings.ProjectRoot,
            UseDescriptionForTitle = true,
        };

        if (dialog.ShowDialog(this) == DialogResult.OK)
        {
            _projectRoot.Text = dialog.SelectedPath;
        }
    }

    private static void AddTextRow(TableLayoutPanel root, int row, string label, TextBox box, Action? browse = null)
    {
        AddLabel(root, row, label);
        box.Dock = DockStyle.Fill;
        root.Controls.Add(box, 1, row);
        if (browse != null)
        {
            var button = new Button { Text = "...", Width = 34 };
            button.Click += (_, _) => browse();
            root.Controls.Add(button, 2, row);
        }
    }

    private static void AddNumberRow(TableLayoutPanel root, int row, string label, NumericUpDown number, decimal min, decimal max)
    {
        AddLabel(root, row, label);
        number.Minimum = min;
        number.Maximum = max;
        number.Dock = DockStyle.Left;
        number.Width = 120;
        root.Controls.Add(number, 1, row);
    }

    private static void AddComboRow(TableLayoutPanel root, int row, string label, ComboBox combo, IEnumerable<string> values)
    {
        AddLabel(root, row, label);
        combo.DropDownStyle = ComboBoxStyle.DropDownList;
        combo.Items.AddRange(values.Cast<object>().ToArray());
        combo.Dock = DockStyle.Left;
        combo.Width = 180;
        root.Controls.Add(combo, 1, row);
    }

    private static void AddCheckRow(TableLayoutPanel root, int row, CheckBox checkBox, string text)
    {
        checkBox.Text = text;
        checkBox.AutoSize = true;
        root.Controls.Add(new Label(), 0, row);
        root.Controls.Add(checkBox, 1, row);
    }

    private static void AddLabel(TableLayoutPanel root, int row, string text)
    {
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
        var label = new Label
        {
            Text = text,
            AutoSize = true,
            Anchor = AnchorStyles.Left,
            TextAlign = ContentAlignment.MiddleLeft,
        };
        root.Controls.Add(label, 0, row);
    }

    private static decimal Clamp(decimal value, decimal min, decimal max) => Math.Min(max, Math.Max(min, value));
}
