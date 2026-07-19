namespace Om0rxAgent;

public sealed class AgentApplicationContext : ApplicationContext
{
    private readonly AgentSettings _settings;
    private readonly AgentSupervisor _supervisor;
    private readonly NotifyIcon _notifyIcon;
    private readonly SynchronizationContext _uiContext;
    private StatusForm? _statusForm;
    private Icon? _currentIcon;
    private ToolStripMenuItem? _statusItem;
    private ToolStripMenuItem? _autoRestartItem;
    private ToolStripMenuItem? _startupItem;
    private readonly List<ToolStripItem> _actionItems = new();
    private bool _actionInProgress;

    public AgentApplicationContext(AgentSettings settings, AgentSupervisor supervisor)
    {
        _settings = settings;
        _supervisor = supervisor;
        _uiContext = SynchronizationContext.Current ?? new WindowsFormsSynchronizationContext();

        _notifyIcon = new NotifyIcon
        {
            Text = "OM0RX Agent starting",
            Visible = true,
            ContextMenuStrip = BuildMenu(),
        };
        SetTrayIcon(ComponentStatus.Unknown);
        _notifyIcon.DoubleClick += (_, _) => ShowStatusWindow();
        if (!string.IsNullOrWhiteSpace(_settings.LoadWarning))
        {
            _notifyIcon.ShowBalloonTip(8000, "OM0RX settings recovered", _settings.LoadWarning, ToolTipIcon.Warning);
        }

        _supervisor.SnapshotChanged += (_, snapshot) => _uiContext.Post(_ => ApplySnapshot(snapshot), null);
        _supervisor.EventLogged += (_, line) => _uiContext.Post(_ => _statusForm?.AppendEvent(line), null);
        _supervisor.Start();
    }

    private ContextMenuStrip BuildMenu()
    {
        var menu = new ContextMenuStrip();
        _statusItem = new ToolStripMenuItem("Starting...") { Enabled = false };
        menu.Items.Add(_statusItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Status...", null, (_, _) => ShowStatusWindow());
        menu.Items.Add("Open Web UI", null, (_, _) => Safe(_supervisor.OpenWebUi));
        menu.Items.Add("Open Logs", null, (_, _) => Safe(_supervisor.OpenLogFolder));
        menu.Items.Add(new ToolStripSeparator());
        AddActionItem(menu, "Start All", "Starting all OM0RX services...", _supervisor.StartAllAsync);
        AddActionItem(menu, "Restart All", "Restarting all OM0RX services and windows...", _supervisor.RestartAllAsync);
        AddActionItem(menu, "Repair", "Repairing the OM0RX runtime...", _supervisor.RepairAsync);
        AddActionItem(menu, "Stop All", "Stopping all OM0RX services...", _supervisor.StopAllAsync);
        menu.Items.Add(new ToolStripSeparator());

        _autoRestartItem = new ToolStripMenuItem("Auto Restart")
        {
            Checked = _settings.AutoRestart,
            CheckOnClick = true,
        };
        _autoRestartItem.CheckedChanged += (_, _) =>
        {
            _settings.AutoRestart = _autoRestartItem.Checked;
            _supervisor.SaveSettings();
        };
        menu.Items.Add(_autoRestartItem);

        _startupItem = new ToolStripMenuItem("Start with Windows")
        {
            Checked = StartupRegistration.IsEnabled(),
            CheckOnClick = true,
        };
        _startupItem.CheckedChanged += (_, _) =>
        {
            StartupRegistration.SetEnabled(_startupItem.Checked, _settings);
        };
        menu.Items.Add(_startupItem);
        menu.Items.Add("Settings...", null, (_, _) => ShowSettings());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Exit Agent", null, async (_, _) => await ExitAgentAsync());
        return menu;
    }

    private void ApplySnapshot(AgentSnapshot snapshot)
    {
        SetTrayIcon(snapshot.OverallStatus);
        var text = $"OM0RX Agent: {snapshot.Summary}";
        _notifyIcon.Text = text.Length > 63 ? text[..63] : text;
        if (_statusItem != null)
        {
            _statusItem.Text = $"{snapshot.OverallStatus}: {snapshot.Summary}";
        }

        if (_autoRestartItem != null)
        {
            _autoRestartItem.Checked = _settings.AutoRestart;
        }

        _statusForm?.ApplySnapshot(snapshot);
    }

    private void SetTrayIcon(ComponentStatus status)
    {
        var next = TrayIconFactory.Create(status);
        var old = _currentIcon;
        _currentIcon = next;
        _notifyIcon.Icon = next;
        old?.Dispose();
    }

    private void ShowStatusWindow()
    {
        if (_statusForm is { IsDisposed: false })
        {
            _statusForm.Show();
            _statusForm.Activate();
            return;
        }

        _statusForm = new StatusForm(_settings, _supervisor);
        _statusForm.ApplySnapshot(_supervisor.CurrentSnapshot);
        foreach (var line in _supervisor.RecentEvents)
        {
            _statusForm.AppendEvent(line);
        }

        _statusForm.Show();
    }

    private void ShowSettings()
    {
        using var form = new SettingsForm(_settings);
        if (form.ShowDialog() == DialogResult.OK)
        {
            _supervisor.SaveSettings();
            if (_startupItem?.Checked == true)
            {
                StartupRegistration.SetEnabled(true, _settings);
            }
        }
    }

    private static void Safe(Action action)
    {
        try
        {
            action();
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "OM0RX Agent", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void AddActionItem(ContextMenuStrip menu, string label, string progressText, Func<Task> action)
    {
        var item = new ToolStripMenuItem(label);
        item.Click += async (_, _) => await RunActionAsync(label, progressText, action);
        _actionItems.Add(item);
        menu.Items.Add(item);
    }

    private async Task RunActionAsync(string label, string progressText, Func<Task> action)
    {
        if (_actionInProgress)
        {
            _notifyIcon.ShowBalloonTip(2500, "OM0RX Agent busy", "Another action is already in progress.", ToolTipIcon.Info);
            return;
        }

        _actionInProgress = true;
        foreach (var item in _actionItems) item.Enabled = false;
        if (_statusItem != null) _statusItem.Text = progressText;
        _notifyIcon.ShowBalloonTip(2500, "OM0RX Agent", progressText, ToolTipIcon.Info);

        try
        {
            await action();
            _notifyIcon.ShowBalloonTip(3000, "OM0RX Agent", $"{label} completed.", ToolTipIcon.Info);
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "OM0RX Agent", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            _actionInProgress = false;
            foreach (var item in _actionItems) item.Enabled = true;
            ApplySnapshot(_supervisor.CurrentSnapshot);
        }
    }

    private async Task ExitAgentAsync()
    {
        var result = MessageBox.Show(
            "Exit the tray agent?\n\nChoose Yes to stop only the tray agent. Managed services may keep running.",
            "OM0RX Agent",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Question);
        if (result != DialogResult.Yes) return;

        await Task.Yield();
        _notifyIcon.Visible = false;
        _notifyIcon.Dispose();
        _currentIcon?.Dispose();
        _supervisor.Dispose();
        ExitThread();
    }
}
