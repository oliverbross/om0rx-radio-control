namespace Om0rxAgent;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        using var mutex = new Mutex(true, "OM0RX.RadioControl.Agent", out var created);
        if (!created)
        {
            MessageBox.Show(
                "OM0RX Radio Control Agent is already running.",
                "OM0RX Agent",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
            return;
        }

        ApplicationConfiguration.Initialize();
        var settings = AgentSettings.Load(args);
        using var supervisor = new AgentSupervisor(settings);
        Application.Run(new AgentApplicationContext(settings, supervisor));
    }
}
