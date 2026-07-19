namespace Om0rxAgent;

public sealed class StatusForm : Form
{
    private readonly AgentSettings _settings;
    private readonly AgentSupervisor _supervisor;
    private readonly Label _summary = new();
    private readonly DataGridView _grid = new();
    private readonly TextBox _events = new();

    public StatusForm(AgentSettings settings, AgentSupervisor supervisor)
    {
        _settings = settings;
        _supervisor = supervisor;

        Text = "OM0RX Radio Control Agent";
        MinimumSize = new Size(820, 560);
        Size = new Size(980, 680);
        StartPosition = FormStartPosition.CenterScreen;

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 4,
            Padding = new Padding(12),
        };
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 58));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 42));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        Controls.Add(root);

        _summary.AutoSize = true;
        _summary.Font = new Font("Segoe UI", 11, FontStyle.Bold);
        root.Controls.Add(_summary, 0, 0);

        ConfigureGrid();
        root.Controls.Add(_grid, 0, 1);

        _events.Multiline = true;
        _events.ReadOnly = true;
        _events.ScrollBars = ScrollBars.Vertical;
        _events.Font = new Font("Consolas", 9);
        root.Controls.Add(_events, 0, 2);

        var buttons = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            AutoSize = true,
            WrapContents = true,
        };
        root.Controls.Add(buttons, 0, 3);

        AddButton(buttons, "Start All", async () => await _supervisor.StartAllAsync());
        AddButton(buttons, "Restart All", async () => await _supervisor.RestartAllAsync());
        AddButton(buttons, "Repair", async () => await _supervisor.RepairAsync());
        AddButton(buttons, "Stop All", async () => await _supervisor.StopAllAsync());
        AddButton(buttons, "Open UI", () => _supervisor.OpenWebUi());
        AddButton(buttons, "Logs", () => _supervisor.OpenLogFolder());
        AddButton(buttons, "Settings", ShowSettings);
        AddButton(buttons, "Refresh", () => ApplySnapshot(_supervisor.CurrentSnapshot));
    }

    public void ApplySnapshot(AgentSnapshot snapshot)
    {
        if (IsDisposed) return;

        _summary.Text = $"{snapshot.OverallStatus} | {snapshot.Summary} | Last check {snapshot.Timestamp:HH:mm:ss} | Auto restart {(snapshot.AutoRestartEnabled ? "on" : "off")}";
        _grid.SuspendLayout();
        _grid.Rows.Clear();
        foreach (var component in snapshot.Components.OrderBy(c => c.Name))
        {
            var index = _grid.Rows.Add(component.Name, component.Status.ToString(), component.Value, component.Detail);
            _grid.Rows[index].Cells[1].Style.ForeColor = StatusColor(component.Status);
        }

        _grid.ResumeLayout();
    }

    public void AppendEvent(string line)
    {
        if (IsDisposed) return;
        _events.AppendText(line + Environment.NewLine);
    }

    private void ConfigureGrid()
    {
        _grid.Dock = DockStyle.Fill;
        _grid.AllowUserToAddRows = false;
        _grid.AllowUserToDeleteRows = false;
        _grid.AllowUserToResizeRows = false;
        _grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
        _grid.BackgroundColor = SystemColors.Window;
        _grid.BorderStyle = BorderStyle.FixedSingle;
        _grid.ReadOnly = true;
        _grid.RowHeadersVisible = false;
        _grid.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
        _grid.Columns.Add("component", "Component");
        _grid.Columns.Add("status", "Status");
        _grid.Columns.Add("value", "Value");
        _grid.Columns.Add("detail", "Detail");
        _grid.Columns[0].FillWeight = 22;
        _grid.Columns[1].FillWeight = 12;
        _grid.Columns[2].FillWeight = 20;
        _grid.Columns[3].FillWeight = 46;
    }

    private static void AddButton(FlowLayoutPanel panel, string text, Func<Task> action)
    {
        var button = MakeButton(text);
        button.Click += async (_, _) =>
        {
            button.Enabled = false;
            try
            {
                await action();
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "OM0RX Agent", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                button.Enabled = true;
            }
        };
        panel.Controls.Add(button);
    }

    private static void AddButton(FlowLayoutPanel panel, string text, Action action)
    {
        var button = MakeButton(text);
        button.Click += (_, _) =>
        {
            try
            {
                action();
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "OM0RX Agent", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        };
        panel.Controls.Add(button);
    }

    private void ShowSettings()
    {
        using var form = new SettingsForm(_settings);
        if (form.ShowDialog(this) == DialogResult.OK)
        {
            _supervisor.SaveSettings();
        }
    }

    private static Button MakeButton(string text) => new()
    {
        Text = text,
        AutoSize = true,
        MinimumSize = new Size(92, 32),
        Margin = new Padding(0, 8, 8, 0),
    };

    private static Color StatusColor(ComponentStatus status) => status switch
    {
        ComponentStatus.Ok => Color.FromArgb(22, 130, 65),
        ComponentStatus.Busy => Color.FromArgb(35, 104, 178),
        ComponentStatus.Warning => Color.FromArgb(180, 100, 18),
        ComponentStatus.Error => Color.FromArgb(190, 45, 45),
        ComponentStatus.Off => Color.FromArgb(90, 94, 100),
        _ => Color.FromArgb(90, 94, 100),
    };
}
