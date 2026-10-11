using System.Text.Json;
using System.Text.Json.Serialization;

namespace Om0rxAgent;

public sealed class StationControllerOwnership : IDisposable
{
    public const string MutexName = @"Global\OM0RX.StationController";
    public const int ConflictExitCode = 73;
    private const int OwnerSchema = 1;

    private readonly Mutex _mutex;
    private readonly string _ownerPath;
    private bool _ownsMutex;

    public ControllerOwnerInfo OwnerInfo { get; }
    public ControllerOwnerInfo? PreviousOwner { get; }
    public bool RecoveredAbandonedMutex { get; }

    private StationControllerOwnership(
        Mutex mutex,
        string ownerPath,
        ControllerOwnerInfo ownerInfo,
        ControllerOwnerInfo? previousOwner,
        bool recoveredAbandonedMutex)
    {
        _mutex = mutex;
        _ownerPath = ownerPath;
        OwnerInfo = ownerInfo;
        PreviousOwner = previousOwner;
        RecoveredAbandonedMutex = recoveredAbandonedMutex;
        _ownsMutex = true;
    }

    public static StationControllerOwnership? TryAcquire(
        string controllerFamily,
        string launchSource,
        out string failure,
        string? mutexName = null,
        string? ownerPath = null)
    {
        var resolvedMutexName = mutexName ?? MutexName;
        var resolvedOwnerPath = ownerPath ?? DefaultOwnerPath();
        var mutex = new Mutex(initiallyOwned: false, resolvedMutexName);
        var acquired = false;
        var abandoned = false;
        try
        {
            try
            {
                acquired = mutex.WaitOne(0);
            }
            catch (AbandonedMutexException)
            {
                acquired = true;
                abandoned = true;
            }

            if (!acquired)
            {
                var active = ReadOwner(resolvedOwnerPath);
                var ownerLabel = active is null
                    ? "an unidentified OM0RX controller"
                    : $"{active.ControllerFamily} (PID {active.Pid})";
                failure =
                    $"Another OM0RX station controller is active: {ownerLabel}; " +
                    $"{controllerFamily} did not open station resources. Inspect the " +
                    "'OM0RX Remote Station Agent' scheduled task and the HKCU Run value " +
                    "'OM0RX Radio Control Agent', then stop only the controller you intend to replace.";
                mutex.Dispose();
                return null;
            }

            var previousOwner = abandoned ? ReadOwner(resolvedOwnerPath) : null;
            var owner = new ControllerOwnerInfo(
                OwnerSchema,
                resolvedMutexName,
                SafeLabel(controllerFamily, "unknown-controller"),
                Environment.ProcessId,
                Environment.ProcessPath ?? AppContext.BaseDirectory,
                DateTimeOffset.UtcNow.ToString("O"),
                SafeLabel(launchSource, "unknown"));
            WriteOwner(resolvedOwnerPath, owner);
            failure = "";
            return new StationControllerOwnership(
                mutex,
                resolvedOwnerPath,
                owner,
                previousOwner,
                abandoned);
        }
        catch
        {
            if (acquired)
            {
                try { mutex.ReleaseMutex(); } catch { }
            }
            mutex.Dispose();
            throw;
        }
    }

    public static string DefaultOwnerPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "OM0RX",
        "station-controller-owner.json");

    public static ControllerOwnerInfo? ReadOwner(string? path = null)
    {
        try
        {
            var target = path ?? DefaultOwnerPath();
            if (!File.Exists(target)) return null;
            var owner = JsonSerializer.Deserialize<ControllerOwnerInfo>(File.ReadAllText(target));
            return owner is { Schema: OwnerSchema, Pid: > 0 } ? owner : null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            return null;
        }
    }

    private static void WriteOwner(string path, ControllerOwnerInfo owner)
    {
        var directory = Path.GetDirectoryName(path)
            ?? throw new InvalidOperationException("Controller owner path has no parent directory.");
        Directory.CreateDirectory(directory);
        var temporary = $"{path}.tmp-{Environment.ProcessId}-{Guid.NewGuid():N}";
        try
        {
            File.WriteAllText(
                temporary,
                JsonSerializer.Serialize(owner, new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine);
            File.Move(temporary, path, overwrite: true);
        }
        finally
        {
            try { File.Delete(temporary); } catch { }
        }
    }

    private static string SafeLabel(string? value, string fallback)
    {
        var candidate = (value ?? "").Trim();
        return candidate.Length is >= 1 and <= 64
            && candidate.All(character => char.IsAsciiLetterOrDigit(character) || character is '.' or '_' or '-')
            ? candidate
            : fallback;
    }

    public void Dispose()
    {
        if (!_ownsMutex) return;
        try
        {
            var current = ReadOwner(_ownerPath);
            if (current?.Pid == OwnerInfo.Pid
                && current.ControllerFamily.Equals(OwnerInfo.ControllerFamily, StringComparison.Ordinal))
            {
                try { File.Delete(_ownerPath); } catch { }
            }
            _mutex.ReleaseMutex();
        }
        finally
        {
            _ownsMutex = false;
            _mutex.Dispose();
        }
    }
}

public sealed record ControllerOwnerInfo(
    [property: JsonPropertyName("schema")] int Schema,
    [property: JsonPropertyName("mutex_name")] string MutexName,
    [property: JsonPropertyName("controller_family")] string ControllerFamily,
    [property: JsonPropertyName("pid")] int Pid,
    [property: JsonPropertyName("executable_path")] string ExecutablePath,
    [property: JsonPropertyName("started_utc")] string StartedUtc,
    [property: JsonPropertyName("launch_source")] string LaunchSource);
