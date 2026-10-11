namespace Om0rxAgent;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        var settings = AgentSettings.Load(args);
        var launchSource = GetArgValue(args, "--launch-source") ?? "direct-executable";
        var nonInteractive = args.Any(
            argument => argument.Equals("--non-interactive", StringComparison.OrdinalIgnoreCase));
        StationControllerOwnership? ownership;
        try
        {
            ownership = StationControllerOwnership.TryAcquire(
                "legacy-radio-control-agent",
                launchSource,
                out var ownershipFailure);
            if (ownership is null)
            {
                WriteBootstrapLog(settings.ProjectRoot, ownershipFailure);
                if (!nonInteractive)
                {
                    MessageBox.Show(
                        ownershipFailure,
                        "OM0RX controller already active",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Warning);
                }
                return StationControllerOwnership.ConflictExitCode;
            }
        }
        catch (Exception ex)
        {
            var message = $"Station controller ownership could not be established: {ex.Message}";
            WriteBootstrapLog(settings.ProjectRoot, message);
            if (!nonInteractive)
            {
                MessageBox.Show(message, "OM0RX Agent", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            return StationControllerOwnership.ConflictExitCode + 1;
        }

        using (ownership)
        {
            if (ownership.RecoveredAbandonedMutex)
            {
                var prior = ownership.PreviousOwner is null
                    ? "unknown prior controller"
                    : $"{ownership.PreviousOwner.ControllerFamily} PID {ownership.PreviousOwner.Pid}";
                WriteBootstrapLog(
                    settings.ProjectRoot,
                    $"Recovered abandoned station-controller ownership from {prior}; normal startup validation remains required.");
            }

            using var mutex = new Mutex(true, "OM0RX.RadioControl.Agent", out var created);
            if (!created)
            {
                MessageBox.Show(
                    "OM0RX Radio Control Agent is already running.",
                    "OM0RX Agent",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return StationControllerOwnership.ConflictExitCode;
            }

            using var supervisor = new AgentSupervisor(settings);
            Application.Run(new AgentApplicationContext(settings, supervisor));
            return 0;
        }
    }

    private static string? GetArgValue(string[] args, string name)
    {
        for (var index = 0; index + 1 < args.Length; index++)
        {
            if (args[index].Equals(name, StringComparison.OrdinalIgnoreCase))
            {
                return args[index + 1];
            }
        }
        return null;
    }

    private static void WriteBootstrapLog(string projectRoot, string message)
    {
        try
        {
            var logDirectory = Path.Combine(projectRoot, "logs");
            Directory.CreateDirectory(logDirectory);
            var line = $"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss} {message}{Environment.NewLine}";
            File.AppendAllText(Path.Combine(logDirectory, "om0rx-agent.log"), line);
        }
        catch
        {
            // The interactive error remains visible if best-effort logging fails.
        }
    }
}
