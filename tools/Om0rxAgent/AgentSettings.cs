using System.Text.Json;
using System.Text.Json.Serialization;

namespace Om0rxAgent;

public sealed class AgentSettings
{
    public string ProjectRoot { get; set; } = "";
    public string BackendHost { get; set; } = "127.0.0.1";
    public int BackendPort { get; set; } = 8080;
    public string AppEnv { get; set; } = "local";
    public bool StartServicesWithAgent { get; set; } = true;
    public bool AutoRestart { get; set; } = true;
    public bool StartLauncher { get; set; } = true;
    public bool ManageDocker { get; set; } = true;
    public bool RememberWindowLayout { get; set; } = true;
    public string DigitalEngineProvider { get; set; } = "";
    // Legacy startup toggle retained for migration and as the generic
    // "start selected engine" preference in existing settings files.
    public bool StartWsjtzWithAgent { get; set; } = false;
    public bool EnableAutoCallOnStartup { get; set; } = false;
    public int AutoCallLimit { get; set; } = 5;
    public int CheckIntervalSeconds { get; set; } = 5;
    public int FailureRestartThreshold { get; set; } = 3;
    public int RestartCooldownSeconds { get; set; } = 30;
    public string DockerComposeFile { get; set; } = "docker-compose.postgres.yml";
    public List<string> WatchedProcessNames { get; set; } = new() { "wsjtx", "wsjt-x", "wsjtz", "mshv", "sdc" };

    [JsonIgnore]
    public string BackendUrl => $"http://{BackendHost}:{BackendPort}";

    [JsonIgnore]
    public string SettingsPath => GetSettingsPath();

    [JsonIgnore]
    public bool StartServicesThisSession { get; private set; } = true;

    [JsonIgnore]
    public string? LoadWarning { get; private set; }

    public static string GetSettingsPath()
    {
        var dir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "OM0RX Radio Control",
            "Agent");
        Directory.CreateDirectory(dir);
        return Path.Combine(dir, "agent-settings.json");
    }

    public static AgentSettings Load(string[] args)
    {
        var path = GetSettingsPath();
        AgentSettings settings;
        if (File.Exists(path))
        {
            try
            {
                var json = File.ReadAllText(path);
                settings = JsonSerializer.Deserialize<AgentSettings>(json, JsonOptions()) ?? new AgentSettings();
            }
            catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
            {
                var quarantine = path + ".corrupt-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss");
                try { File.Move(path, quarantine, overwrite: false); } catch { quarantine = path; }
                settings = new AgentSettings
                {
                    LoadWarning = $"Agent settings were unreadable and defaults were restored. Backup: {quarantine}",
                };
            }
        }
        else
        {
            settings = new AgentSettings();
        }

        settings.StartServicesThisSession = settings.StartServicesWithAgent;
        settings.DigitalEngineProvider = NormalizeDigitalProvider(
            settings.DigitalEngineProvider,
            settings.StartWsjtzWithAgent);
        if (settings.DigitalEngineProvider == "none")
        {
            settings.StartWsjtzWithAgent = false;
            settings.EnableAutoCallOnStartup = false;
        }
        settings.ProjectRoot = NormalizeProjectRoot(settings.ProjectRoot, args);
        settings.ApplyArgs(args);
        settings.Save();
        return settings;
    }

    public void Save()
    {
        ProjectRoot = NormalizeProjectRoot(ProjectRoot, Array.Empty<string>());
        var json = JsonSerializer.Serialize(this, JsonOptions());
        var tempPath = SettingsPath + ".tmp-" + Environment.ProcessId;
        File.WriteAllText(tempPath, json);
        File.Move(tempPath, SettingsPath, overwrite: true);
    }

    private void ApplyArgs(string[] args)
    {
        for (var i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            string? Next() => i + 1 < args.Length ? args[++i] : null;

            if (arg.Equals("--project-root", StringComparison.OrdinalIgnoreCase))
            {
                ProjectRoot = NormalizeProjectRoot(Next() ?? ProjectRoot, Array.Empty<string>());
            }
            else if (arg.Equals("--port", StringComparison.OrdinalIgnoreCase) && int.TryParse(Next(), out var port))
            {
                BackendPort = port;
            }
            else if (arg.Equals("--host", StringComparison.OrdinalIgnoreCase))
            {
                BackendHost = Next() ?? BackendHost;
            }
            else if (arg.Equals("--no-autostart", StringComparison.OrdinalIgnoreCase))
            {
                StartServicesThisSession = false;
            }
        }
    }

    private static JsonSerializerOptions JsonOptions() => new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
    };

    public static string NormalizeDigitalProvider(string? value, bool legacyStartWsjtz)
    {
        var normalized = (value ?? "").Trim().ToLowerInvariant();
        if (normalized is "wsjt-z") normalized = "wsjtz";
        if (normalized is "mshv") normalized = "mshv_auto_dx";
        if (normalized is "none" or "wsjtz" or "mshv_auto_dx") return normalized;
        return legacyStartWsjtz ? "wsjtz" : "none";
    }

    private static string NormalizeProjectRoot(string configuredRoot, string[] args)
    {
        var argRoot = GetArgValue(args, "--project-root");
        foreach (var candidate in CandidateRoots(argRoot, configuredRoot))
        {
            if (string.IsNullOrWhiteSpace(candidate)) continue;
            try
            {
                var full = Path.GetFullPath(Environment.ExpandEnvironmentVariables(candidate));
                if (File.Exists(Path.Combine(full, "start_all.ps1")))
                {
                    return full;
                }
            }
            catch
            {
                // Try the next candidate.
            }
        }

        return Directory.GetCurrentDirectory();
    }

    private static string? GetArgValue(string[] args, string name)
    {
        for (var i = 0; i + 1 < args.Length; i++)
        {
            if (args[i].Equals(name, StringComparison.OrdinalIgnoreCase))
            {
                return args[i + 1];
            }
        }

        return null;
    }

    private static IEnumerable<string?> CandidateRoots(string? argRoot, string configuredRoot)
    {
        yield return argRoot;
        yield return configuredRoot;
        yield return Directory.GetCurrentDirectory();

        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null)
        {
            yield return dir.FullName;
            dir = dir.Parent;
        }

        yield return @"C:\Projects\om0rx-radio-control";
    }
}
