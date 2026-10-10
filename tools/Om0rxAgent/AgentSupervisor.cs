using System.Diagnostics;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

namespace Om0rxAgent;

public sealed class AgentSupervisor : IDisposable
{
    private readonly AgentSettings _settings;
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(10) };
    // MSHV loads the canonical history before its first exact heartbeat. Keep
    // this above the backend's bounded 45-second startup confirmation window.
    private readonly HttpClient _actionHttp = new() { Timeout = TimeSpan.FromSeconds(120) };
    private readonly CancellationTokenSource _stop = new();
    private readonly SemaphoreSlim _actionLock = new(1, 1);
    private readonly object _sync = new();
    private readonly List<string> _events = new();
    private Task? _monitorTask;
    private Process? _runtimeProcess;
    private TaskCompletionSource<bool>? _launcherStartedSignal;
    private int _consecutiveFailures;
    private DateTimeOffset _lastRestartAttempt = DateTimeOffset.MinValue;
    private DateTimeOffset _runtimeStartedAt = DateTimeOffset.MinValue;
    private bool _repairInProgress;
    private bool _desiredRunning;
    private bool _startupOptionsApplied;
    private DateTimeOffset _nextStartupOptionAttempt = DateTimeOffset.MinValue;
    private DateTimeOffset _lastWsjtzRestartAttempt = DateTimeOffset.MinValue;
    private int _wsjtxStaleFailures;
    private int _autoCallStallFailures;
    private int _wsjtzUiHungFailures;
    private string _lastWsjtxQsoState = "";
    private DateTimeOffset _lastWsjtxQsoStateChangedAt = DateTimeOffset.Now;
    private string _lastAutoCallProgressKey = "";
    private int _lastAutoCallRemaining = -1;
    private DateTimeOffset _lastAutoCallProgressAt = DateTimeOffset.Now;
    private bool _wsjtzNativeAutomationPending;
    private int _wsjtzNativeAutomationAttempts;
    private DateTimeOffset _nextWsjtzNativeAutomationAttempt = DateTimeOffset.MinValue;
    private string _selectedDigitalEngine = "none";
    private int _mshvHealthFailures;

    public event EventHandler<AgentSnapshot>? SnapshotChanged;
    public event EventHandler<string>? EventLogged;

    public AgentSnapshot CurrentSnapshot { get; private set; } = new(
        DateTimeOffset.Now,
        Array.Empty<ComponentProbe>(),
        false,
        true,
        false,
        "Starting");

    public IReadOnlyList<string> RecentEvents
    {
        get
        {
            lock (_sync) return _events.ToList();
        }
    }

    public AgentSupervisor(AgentSettings settings)
    {
        _settings = settings;
        _desiredRunning = settings.StartServicesThisSession;
    }

    public void Start()
    {
        _monitorTask ??= Task.Run(MonitorLoopAsync);
    }

    public async Task StartAllAsync()
    {
        if (!await TryBeginActionAsync("Start All")) return;
        try
        {
            _desiredRunning = true;
            _startupOptionsApplied = false;
            _nextStartupOptionAttempt = DateTimeOffset.MinValue;
            if (await IsRuntimeLikelyRunningAsync())
            {
                _runtimeStartedAt = DateTimeOffset.Now;
                Log("Start skipped: managed runtime is already running.");
                return;
            }

            await StartAllWithoutLockAsync();
            if (!await WaitForBackendReadyAsync(TimeSpan.FromSeconds(120)))
            {
                throw new InvalidOperationException("Start All timed out waiting for the backend to become ready. Check om0rx-agent.log and start_all backend logs.");
            }

            await WaitForLauncherReadyAsync();
            Log("Start All completed: backend and desktop UI are ready.");
        }
        finally
        {
            _actionLock.Release();
        }
    }

    public async Task StopAllAsync()
    {
        if (!await TryBeginActionAsync("Stop All")) return;
        try
        {
            _desiredRunning = false;
            _startupOptionsApplied = false;
            Log("Stopping OM0RX runtime.");
            await HaltDigitalTxAsync();
            if (!await StopDigitalEngineProcessesAsync()) throw new InvalidOperationException("Digital engine stop was not confirmed; runtime shutdown blocked.");
            await TryPostAsync("/api/shutdown");
            await Task.Delay(2500);

            await StopManagedRuntimeAsync("stop");

            await StopProjectProcessesAsync();
            _runtimeProcess = null;
            _consecutiveFailures = 0;
        }
        finally
        {
            _actionLock.Release();
        }
    }

    public async Task RestartAllAsync()
    {
        if (!await TryBeginActionAsync("Restart All")) return;
        try
        {
            _desiredRunning = true;
            _startupOptionsApplied = false;
            _nextStartupOptionAttempt = DateTimeOffset.MinValue;
            _lastRestartAttempt = DateTimeOffset.Now;
            _repairInProgress = true;
            Log("Restarting all OM0RX runtime processes and windows.");

            await HaltDigitalTxAsync();
            if (!await StopDigitalEngineProcessesAsync()) throw new InvalidOperationException("Digital engine stop was not confirmed; runtime restart blocked.");
            var gracefulShutdown = await TryPostAsync("/api/shutdown");
            Log(gracefulShutdown
                ? "Backend accepted the shutdown request."
                : "Backend did not accept the shutdown request; continuing with process cleanup.");
            await Task.Delay(2500);
            await StopManagedRuntimeAsync("restart");

            await StopProjectProcessesAsync();
            _runtimeProcess = null;
            await Task.Delay(1500);
            await StartAllWithoutLockAsync();
            if (!await WaitForBackendReadyAsync(TimeSpan.FromSeconds(120)))
            {
                throw new InvalidOperationException("Restart timed out waiting for the backend to become ready. Check om0rx-agent.log and start_all backend logs.");
            }

            await EnsureRestartWindowsAsync();

            Log("Restart All completed: backend, desktop UI, and WSJT-Z are ready.");
            _consecutiveFailures = 0;
        }
        finally
        {
            _repairInProgress = false;
            _actionLock.Release();
        }
    }

    public async Task RepairAsync()
    {
        if (!await TryBeginActionAsync("Repair")) return;
        try
        {
            _desiredRunning = true;
            _startupOptionsApplied = false;
            _nextStartupOptionAttempt = DateTimeOffset.MinValue;
            _repairInProgress = true;
            Log("Repair requested: clearing managed processes and starting fresh.");
            await HaltDigitalTxAsync();
            if (!await StopDigitalEngineProcessesAsync()) throw new InvalidOperationException("Digital engine stop was not confirmed; runtime repair blocked.");
            await TryPostAsync("/api/shutdown");
            await Task.Delay(1500);
            await StopManagedRuntimeAsync("repair");
            await StopProjectProcessesAsync();
            _runtimeProcess = null;
            await StartAllWithoutLockAsync();
            if (!await WaitForBackendReadyAsync(TimeSpan.FromSeconds(120)))
            {
                throw new InvalidOperationException("Repair timed out waiting for the backend to become ready.");
            }

            await EnsureRestartWindowsAsync();

            Log("Repair completed: backend, desktop UI, and WSJT-Z are ready.");
            _consecutiveFailures = 0;
        }
        finally
        {
            _repairInProgress = false;
            _actionLock.Release();
        }
    }

    public void OpenWebUi()
    {
        Process.Start(new ProcessStartInfo(_settings.BackendUrl) { UseShellExecute = true });
    }

    public void OpenLogFolder()
    {
        var logs = Path.Combine(_settings.ProjectRoot, "logs");
        Directory.CreateDirectory(logs);
        Process.Start(new ProcessStartInfo(logs) { UseShellExecute = true });
    }

    public void SaveSettings()
    {
        _settings.Save();
        Log("Agent settings saved.");
    }

    private async Task MonitorLoopAsync()
    {
        Log("OM0RX Agent monitor started.");

        if (_settings.StartServicesThisSession)
        {
            try
            {
                await StartAllAsync();
            }
            catch (Exception ex)
            {
                // A failed startup must not terminate the monitor task. Keep
                // probing so the status UI and Repair action remain usable.
                Log($"Initial startup failed: {ex.Message}");
            }
        }

        while (!_stop.IsCancellationRequested)
        {
            try
            {
                var snapshot = await ProbeAsync();
                CurrentSnapshot = snapshot;
                SnapshotChanged?.Invoke(this, snapshot);
                await RefreshDigitalEngineAsync();
                await MaybeWsjtzWatchdogAsync(snapshot);
                await MaybeApplyStartupOptionsAsync(snapshot);
                await MaybeApplyPendingWsjtzNativeAutomationAsync();
                await MaybeAutoRepairAsync(snapshot);
            }
            catch (Exception ex)
            {
                Log($"Monitor error: {ex.Message}");
            }

            try
            {
                await Task.Delay(TimeSpan.FromSeconds(Math.Max(2, _settings.CheckIntervalSeconds)), _stop.Token);
            }
            catch (TaskCanceledException)
            {
                break;
            }
        }
    }

    private async Task<AgentSnapshot> ProbeAsync()
    {
        // These probes are independent. Running them serially made the Agent
        // status window wait on Docker before it could publish backend/port
        // health, even though all work already happens off the WinForms UI
        // thread.
        var ownerTask = ProbeRuntimeOwnerAsync();
        var backendTask = ProbeBackendAsync();
        var bridgeWsTask = ProbeRequiredPortAsync("bridge-ws", "Bridge WebSocket", _settings.BackendHost, 8091);
        var bridgeCommandTask = ProbeRequiredPortAsync("bridge-command", "Bridge Command", _settings.BackendHost, 8092);
        var sdcTask = ProbeOptionalDependencyPortAsync("sdc-tcp", "SDC TCP", _settings.BackendHost, 12166);
        var dockerTask = ProbeDockerAsync();
        var serviceHealthTask = ProbeBackendServiceHealthAsync();

        await Task.WhenAll(
            ownerTask,
            backendTask,
            bridgeWsTask,
            bridgeCommandTask,
            sdcTask,
            dockerTask,
            serviceHealthTask);

        var ownerProbe = await ownerTask;
        var runtimeRunning = ownerProbe.Status == ComponentStatus.Ok;
        var components = new List<ComponentProbe>
        {
            ownerProbe,
            await backendTask,
            await bridgeWsTask,
            await bridgeCommandTask,
            await sdcTask,
            await dockerTask,
        };
        components.AddRange(await serviceHealthTask);
        components.AddRange(ProbeWatchedProcesses());

        var errors = components.Count(c => c.Status == ComponentStatus.Error);
        var warnings = components.Count(c => c.Status == ComponentStatus.Warning);
        var ok = components.Count(c => c.Status == ComponentStatus.Ok);
        var summary = errors > 0
            ? $"{errors} error(s), {warnings} warning(s)"
            : warnings > 0
                ? $"{warnings} warning(s), {ok} OK"
                : $"{ok} OK";

        return new AgentSnapshot(
            DateTimeOffset.Now,
            components,
            runtimeRunning,
            _settings.AutoRestart,
            _repairInProgress,
            summary);
    }

    private async Task<ComponentProbe> ProbeRuntimeOwnerAsync()
    {
        var path = Path.Combine(_settings.ProjectRoot, "logs", "runtime_owner.json");
        try
        {
            if (!File.Exists(path))
            {
                return new ComponentProbe("runtime", "Runtime Owner", ComponentStatus.Error, "missing", "Atomic runtime owner manifest is absent");
            }

            using var doc = JsonDocument.Parse(await File.ReadAllTextAsync(path, _stop.Token));
            var root = doc.RootElement;
            if (GetJsonInt32(root, "schema") != 1 || GetJsonString(root, "state", "") != "active")
            {
                return new ComponentProbe("runtime", "Runtime Owner", ComponentStatus.Error, "inactive", "Runtime owner manifest is not active schema 1");
            }
            if (!root.TryGetProperty("ports", out var ports)
                || GetJsonInt32(ports, "backend") != _settings.BackendPort
                || GetJsonInt32(ports, "bridge_ws") != 8091
                || GetJsonInt32(ports, "bridge_command") != 8092)
            {
                return new ComponentProbe("runtime", "Runtime Owner", ComponentStatus.Error, "port mismatch", "Runtime owner port contract does not match backend/8091/8092");
            }

            foreach (var role in new[] { "supervisor", "backend", "bridge" })
            {
                if (!root.TryGetProperty(role, out var identity) || !RuntimeProcessIdentityMatches(identity))
                {
                    return new ComponentProbe("runtime", "Runtime Owner", ComponentStatus.Error, $"{role} mismatch", $"The {role} PID/path/creation identity is missing or stale");
                }
            }
            if (!await RuntimePortsMatchOwnerAsync(root))
            {
                return new ComponentProbe("runtime", "Runtime Owner", ComponentStatus.Error, "listener mismatch", "Backend/8091/8092 listeners do not belong to the declared child identities");
            }

            var ownerId = GetJsonString(root, "owner_id", "");
            if (string.IsNullOrWhiteSpace(ownerId))
            {
                return new ComponentProbe("runtime", "Runtime Owner", ComponentStatus.Error, "owner missing", "Runtime owner ID is empty");
            }
            return new ComponentProbe("runtime", "Runtime Owner", ComponentStatus.Ok, "owned", $"Owner {ownerId[..Math.Min(12, ownerId.Length)]}; backend + bridge identities match");
        }
        catch (Exception ex)
        {
            return new ComponentProbe("runtime", "Runtime Owner", ComponentStatus.Error, "invalid", ex.Message);
        }
    }

    private static bool RuntimeProcessIdentityMatches(JsonElement identity)
    {
        var pid = GetJsonInt32(identity, "pid");
        var declaredCreated = GetJsonInt64(identity, "creation_time_filetime");
        var declaredPath = GetJsonString(identity, "executable_path", "");
        if (pid is null || declaredCreated is null || string.IsNullOrWhiteSpace(declaredPath)) return false;
        try
        {
            using var process = Process.GetProcessById(pid.Value);
            var actualCreated = process.StartTime.ToUniversalTime().ToFileTimeUtc();
            var actualPath = process.MainModule?.FileName;
            return actualCreated == declaredCreated.Value
                && !string.IsNullOrWhiteSpace(actualPath)
                && string.Equals(Path.GetFullPath(actualPath), Path.GetFullPath(declaredPath), StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    private Task<bool> RuntimePortsMatchOwnerAsync(JsonElement root)
    {
        if (!root.TryGetProperty("backend", out var backend) || !root.TryGetProperty("bridge", out var bridge)) return Task.FromResult(false);
        var backendPid = GetJsonInt32(backend, "pid");
        var bridgePid = GetJsonInt32(bridge, "pid");
        if (backendPid is null || bridgePid is null) return Task.FromResult(false);

        var expected = new Dictionary<int, int>
        {
            [_settings.BackendPort] = backendPid.Value,
            [8091] = bridgePid.Value,
            [8092] = bridgePid.Value,
        };
        var owners = GetTcp4ListenerOwners(expected.Keys);
        if (owners is null) return Task.FromResult(false);

        return Task.FromResult(expected.All(entry =>
            owners.TryGetValue(entry.Key, out var actual) &&
            actual.Count == 1 &&
            actual.Contains(entry.Value)));
    }

    private static Dictionary<int, HashSet<int>>? GetTcp4ListenerOwners(IEnumerable<int> requestedPorts)
    {
        var requested = requestedPorts.ToHashSet();
        var owners = requested.ToDictionary(port => port, _ => new HashSet<int>());
        if (!OperatingSystem.IsWindows()) return null;

        uint size = 0;
        var result = GetExtendedTcpTable(IntPtr.Zero, ref size, false, 2, 3, 0);
        if (result != 122 || size < sizeof(uint)) return null;

        var buffer = Marshal.AllocHGlobal(checked((int)size));
        try
        {
            result = GetExtendedTcpTable(buffer, ref size, false, 2, 3, 0);
            if (result != 0) return null;

            var count = Marshal.ReadInt32(buffer);
            var rowSize = Marshal.SizeOf<MibTcpRowOwnerPid>();
            for (var index = 0; index < count; index++)
            {
                var rowPointer = IntPtr.Add(buffer, sizeof(uint) + index * rowSize);
                var row = Marshal.PtrToStructure<MibTcpRowOwnerPid>(rowPointer);
                var port = (int)(((row.LocalPort & 0xff) << 8) | ((row.LocalPort & 0xff00) >> 8));
                if (owners.TryGetValue(port, out var portOwners))
                {
                    portOwners.Add(checked((int)row.OwningPid));
                }
            }

            return owners;
        }
        catch
        {
            return null;
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MibTcpRowOwnerPid
    {
        public uint State;
        public uint LocalAddress;
        public uint LocalPort;
        public uint RemoteAddress;
        public uint RemotePort;
        public uint OwningPid;
    }

    [DllImport("iphlpapi.dll")]
    private static extern uint GetExtendedTcpTable(
        IntPtr tcpTable,
        ref uint size,
        [MarshalAs(UnmanagedType.Bool)] bool order,
        int ipVersion,
        int tableClass,
        uint reserved);

    private async Task<ComponentProbe> ProbeBackendAsync()
    {
        try
        {
            using var response = await _http.GetAsync($"{_settings.BackendUrl}/api/health", _stop.Token);
            if (!response.IsSuccessStatusCode)
            {
                return new ComponentProbe("backend", "Backend", ComponentStatus.Error, ((int)response.StatusCode).ToString(), response.ReasonPhrase ?? "HTTP error");
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(_stop.Token), cancellationToken: _stop.Token);
            var status = doc.RootElement.TryGetProperty("status", out var s) ? s.GetString() ?? "ok" : "ok";
            var connected = doc.RootElement.TryGetProperty("connected", out var c) && c.GetBoolean();
            var value = connected ? "radio connected" : status;
            var componentStatus = status.Equals("ok", StringComparison.OrdinalIgnoreCase)
                ? ComponentStatus.Ok
                : ComponentStatus.Warning;
            return new ComponentProbe("backend", "Backend", componentStatus, value, $"{_settings.BackendUrl}/api/health");
        }
        catch (Exception ex)
        {
            return new ComponentProbe("backend", "Backend", ComponentStatus.Error, "down", ex.Message);
        }
    }

    private async Task<IReadOnlyList<ComponentProbe>> ProbeBackendServiceHealthAsync()
    {
        try
        {
            using var response = await _http.GetAsync($"{_settings.BackendUrl}/api/service-health", _stop.Token);
            if (!response.IsSuccessStatusCode) return Array.Empty<ComponentProbe>();

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(_stop.Token), cancellationToken: _stop.Token);
            if (!doc.RootElement.TryGetProperty("services", out var services) || services.ValueKind != JsonValueKind.Array)
            {
                return Array.Empty<ComponentProbe>();
            }

            var probes = new List<ComponentProbe>();
            foreach (var service in services.EnumerateArray())
            {
                var id = GetJsonString(service, "id", "service");
                var label = GetJsonString(service, "label", id);
                var status = MapBackendStatus(GetJsonString(service, "status", "unknown"));
                var value = GetJsonString(service, "value", "");
                var detail = GetJsonString(service, "detail", "");
                probes.Add(new ComponentProbe($"backend-{id}", label, status, value, detail));
            }

            return probes;
        }
        catch
        {
            return Array.Empty<ComponentProbe>();
        }
    }

    private async Task<ComponentProbe> ProbeRequiredPortAsync(string id, string label, string host, int port)
    {
        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            cts.CancelAfter(TimeSpan.FromSeconds(1));
            using var client = new TcpClient();
            await client.ConnectAsync(host, port, cts.Token);
            return new ComponentProbe(id, label, ComponentStatus.Ok, $":{port}", "TCP port accepts connections");
        }
        catch (Exception ex)
        {
            return new ComponentProbe(id, label, ComponentStatus.Error, $":{port} down", ex.Message);
        }
    }

    private async Task<ComponentProbe> ProbeOptionalDependencyPortAsync(string id, string label, string host, int port)
    {
        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            cts.CancelAfter(TimeSpan.FromSeconds(1));
            using var client = new TcpClient();
            await client.ConnectAsync(host, port, cts.Token);
            return new ComponentProbe(id, label, ComponentStatus.Ok, $":{port}", "External dependency accepts connections");
        }
        catch (Exception ex)
        {
            return new ComponentProbe(id, label, ComponentStatus.Off, "not connected", $"External dependency is not reachable on {host}:{port}: {ex.Message}");
        }
    }

    private async Task<ComponentProbe> ProbeDockerAsync()
    {
        if (!_settings.ManageDocker)
        {
            return new ComponentProbe("docker", "Docker", ComponentStatus.Off, "disabled", "Docker management is disabled in agent settings");
        }

        // `docker info` enumerates every installed CLI plugin on Windows. A
        // misbehaving plugin can inherit the redirected output pipe and keep an
        // agent action open after docker.exe itself has exited. `version` gives
        // us the daemon readiness signal without that plugin scan.
        var docker = await RunProcessAsync("docker", new[] { "version", "--format", "{{.Server.Version}}" }, _settings.ProjectRoot, 4000);
        if (docker.ExitCode != 0)
        {
            return new ComponentProbe("docker", "Docker", ComponentStatus.Warning, "unavailable", FirstLine(docker.Error, docker.Output, "Docker daemon is not reachable"));
        }

        var composePath = Path.Combine(_settings.ProjectRoot, _settings.DockerComposeFile);
        if (!File.Exists(composePath))
        {
            return new ComponentProbe("docker", "Docker", ComponentStatus.Ok, docker.Output.Trim(), "Docker is running; no compose file found");
        }

        var compose = await RunProcessAsync("docker", new[] { "compose", "-f", composePath, "ps" }, _settings.ProjectRoot, 5000);
        var hasRunning = compose.Output.Contains("running", StringComparison.OrdinalIgnoreCase) ||
                         compose.Output.Contains("Up", StringComparison.OrdinalIgnoreCase);
        return new ComponentProbe(
            "docker",
            "Docker/Postgres",
            hasRunning ? ComponentStatus.Ok : ComponentStatus.Warning,
            hasRunning ? "compose up" : "compose idle",
            FirstLine(compose.Output, compose.Error, "Docker daemon is running"));
    }

    private IReadOnlyList<ComponentProbe> ProbeWatchedProcesses()
    {
        var processes = Process.GetProcesses();
        var probes = new List<ComponentProbe>();
        foreach (var processName in _settings.WatchedProcessNames.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            var matches = processes.Where(p =>
            {
                try
                {
                    return p.ProcessName.Contains(processName, StringComparison.OrdinalIgnoreCase);
                }
                catch
                {
                    return false;
                }
            }).ToList();

            var label = processName.Equals("sdc", StringComparison.OrdinalIgnoreCase)
                ? "SDC"
                : processName.ToUpperInvariant();
            probes.Add(new ComponentProbe(
                $"process-{processName}",
                label,
                matches.Count > 0 ? ComponentStatus.Ok : ComponentStatus.Off,
                matches.Count > 0 ? $"{matches.Count} process(es)" : "not running",
                matches.Count > 0 ? string.Join(", ", matches.Select(p => $"{p.ProcessName}:{p.Id}")) : "External program is not detected"));
        }

        return probes;
    }

    private async Task MaybeAutoRepairAsync(AgentSnapshot snapshot)
    {
        // A manual restart/repair already owns the action lock. Starting another
        // repair cannot help and only produces repeated ignored actions while
        // the first operation is still settling.
        if (_repairInProgress)
        {
            return;
        }

        var backend = snapshot.Components.FirstOrDefault(c => c.Id == "backend");
        var bridge = snapshot.Components.FirstOrDefault(c => c.Id == "bridge-ws");
        var runtime = snapshot.Components.FirstOrDefault(c => c.Id == "runtime");
        var criticalFailure =
            _desiredRunning &&
            (backend?.Status == ComponentStatus.Error ||
             bridge?.Status == ComponentStatus.Error ||
             runtime?.Status == ComponentStatus.Error);

        if (!criticalFailure)
        {
            _consecutiveFailures = 0;
            return;
        }

        var startupGrace = TimeSpan.FromSeconds(120);
        if (_runtimeStartedAt != DateTimeOffset.MinValue && DateTimeOffset.Now - _runtimeStartedAt < startupGrace)
        {
            return;
        }

        _consecutiveFailures++;
        if (!_settings.AutoRestart)
        {
            return;
        }

        if (_consecutiveFailures < Math.Max(1, _settings.FailureRestartThreshold))
        {
            return;
        }

        var cooldown = TimeSpan.FromSeconds(Math.Max(10, _settings.RestartCooldownSeconds));
        if (DateTimeOffset.Now - _lastRestartAttempt < cooldown)
        {
            return;
        }

        var unsafeReason = await FullAutoRepairUnsafeReasonAsync();
        if (unsafeReason is not null)
        {
            _lastRestartAttempt = DateTimeOffset.Now;
            _consecutiveFailures = 0;
            Log($"Auto-repair suppressed: {unsafeReason}");
            return;
        }

        Log($"Auto-repair triggered after {_consecutiveFailures} failed probe(s).");
        await RestartAllAsync();
    }

    private async Task MaybeWsjtzWatchdogAsync(AgentSnapshot snapshot)
    {
        if (_selectedDigitalEngine == "none")
        {
            _wsjtxStaleFailures = 0;
            _autoCallStallFailures = 0;
            _wsjtzUiHungFailures = 0;
            _mshvHealthFailures = 0;
            return;
        }
        if (_selectedDigitalEngine != "wsjtz")
        {
            await MaybeMshvWatchdogAsync();
            return;
        }
        if (!_desiredRunning || !_settings.StartWsjtzWithAgent || _repairInProgress)
        {
            return;
        }

        // Once startup has completed, an absent WSJT-Z process is treated as
        // an intentional operator stop. The watchdog repairs a running but
        // stale or hung process; it must not relaunch an application the
        // operator deliberately closed.
        if (_startupOptionsApplied && !IsWsjtzProcessRunning())
        {
            _wsjtxStaleFailures = 0;
            _autoCallStallFailures = 0;
            _wsjtzUiHungFailures = 0;
            return;
        }

        var backendOk = snapshot.Components.Any(c => c.Id == "backend" && c.Status is ComponentStatus.Ok or ComponentStatus.Warning);
        var bridgeOk = snapshot.Components.Any(c => c.Id == "bridge-ws" && c.Status == ComponentStatus.Ok);
        if (!backendOk || !bridgeOk)
        {
            return;
        }

        var cooldown = TimeSpan.FromSeconds(Math.Max(60, _settings.RestartCooldownSeconds * 4));
        if (DateTimeOffset.Now - _lastWsjtzRestartAttempt < cooldown)
        {
            return;
        }

        var bridge = await ReadWsjtxBridgeStatusAsync();
        if (bridge is null)
        {
            return;
        }

        var ft8 = await ReadFt8WatchStatusAsync();
        var staleReason = WsjtxStaleReason(bridge);
        _wsjtxStaleFailures = staleReason is null ? 0 : _wsjtxStaleFailures + 1;

        var stallReason = AutoCallStallReason(bridge, ft8);
        _autoCallStallFailures = stallReason is null ? 0 : _autoCallStallFailures + 1;

        var uiHungReason = WsjtzUiHungReason();
        _wsjtzUiHungFailures = uiHungReason is null ? 0 : _wsjtzUiHungFailures + 1;
        if (uiHungReason is not null)
        {
            Log($"WSJT-Z UI watchdog observed failure {_wsjtzUiHungFailures}: {uiHungReason}");
        }

        var unsafeReason = WsjtzRestartUnsafeReason(bridge, ft8, ignoreNonIdleQso: uiHungReason is not null);
        if (unsafeReason is not null)
        {
            if (_wsjtxStaleFailures > 0 || _autoCallStallFailures > 0 || _wsjtzUiHungFailures > 0)
            {
                Log($"WSJT-Z watchdog suppressed: {unsafeReason}");
            }
            _wsjtxStaleFailures = 0;
            _autoCallStallFailures = 0;
            _wsjtzUiHungFailures = 0;
            return;
        }

        var threshold = Math.Max(2, _settings.FailureRestartThreshold);
        if (_wsjtzUiHungFailures >= threshold)
        {
            Log($"WSJT-Z watchdog restart: {uiHungReason}");
            await RestartWsjtzOnlyAsync();
            return;
        }

        if (_wsjtxStaleFailures >= threshold)
        {
            Log($"WSJT-Z watchdog restart: {staleReason}");
            await RestartWsjtzOnlyAsync();
            return;
        }

        if (_autoCallStallFailures >= threshold)
        {
            Log($"WSJT-Z Auto Call watchdog restart: {stallReason}");
            await RestartWsjtzOnlyAsync();
        }
    }

    private async Task RestartWsjtzOnlyAsync()
    {
        await _actionLock.WaitAsync();
        try
        {
            _lastWsjtzRestartAttempt = DateTimeOffset.Now;
            _wsjtxStaleFailures = 0;
            _autoCallStallFailures = 0;
            _wsjtzUiHungFailures = 0;
            _startupOptionsApplied = false;
            _nextStartupOptionAttempt = DateTimeOffset.MinValue;

            Log("Restarting WSJT-Z only.");
            if (!await StopDigitalEngineProcessesAsync()) return;
            await Task.Delay(1500, _stop.Token);

            var launched = await LaunchWsjtzAsync();
            if (_settings.EnableAutoCallOnStartup && launched)
            {
                await EnableAutoCallAsync();
            }

            _startupOptionsApplied = launched;
        }
        finally
        {
            _actionLock.Release();
        }
    }

    private async Task<WsjtxBridgeWatch?> ReadWsjtxBridgeStatusAsync()
    {
        try
        {
            using var response = await _actionHttp.GetAsync($"http://{_settings.BackendHost}:8092/wsjtx/status", _stop.Token);
            if (!response.IsSuccessStatusCode)
            {
                return null;
            }

            await using var stream = await response.Content.ReadAsStreamAsync(_stop.Token);
            using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: _stop.Token);
            var root = doc.RootElement;
            var stats = root.TryGetProperty("stats", out var statsElement) ? statsElement : default;
            var lastStatus = stats.ValueKind == JsonValueKind.Object && stats.TryGetProperty("lastStatus", out var statusElement)
                ? statusElement
                : default;
            var lastDecode = stats.ValueKind == JsonValueKind.Object && stats.TryGetProperty("lastDecode", out var decodeElement)
                ? decodeElement
                : default;

            return new WsjtxBridgeWatch(
                ClientId: root.TryGetProperty("client", out var client) && client.ValueKind == JsonValueKind.Object
                    ? GetJsonString(client, "id", "")
                    : "",
                LastSeenMs: root.TryGetProperty("client", out client) && client.ValueKind == JsonValueKind.Object
                    ? GetJsonInt64(client, "lastSeenMs")
                    : null,
                LastStatusAgeMs: stats.ValueKind == JsonValueKind.Object ? GetJsonInt64(stats, "lastStatusAgeMs") : null,
                LastDecodeAgeMs: stats.ValueKind == JsonValueKind.Object ? GetJsonInt64(stats, "lastDecodeAgeMs") : null,
                QsoState: lastStatus.ValueKind == JsonValueKind.Object
                    ? GetJsonString(lastStatus, "qsoState", GetJsonString(lastStatus, "qso_state", ""))
                    : "",
                Decoding: lastStatus.ValueKind == JsonValueKind.Object &&
                          lastStatus.TryGetProperty("decoding", out var decoding) &&
                          decoding.ValueKind == JsonValueKind.True,
                Transmitting: lastStatus.ValueKind == JsonValueKind.Object &&
                              lastStatus.TryGetProperty("transmitting", out var transmitting) &&
                              transmitting.ValueKind == JsonValueKind.True,
                LastDecodeMessage: lastDecode.ValueKind == JsonValueKind.Object ? GetJsonString(lastDecode, "message", "") : "");
        }
        catch
        {
            return null;
        }
    }

    private async Task<Ft8Watch?> ReadFt8WatchStatusAsync()
    {
        try
        {
            using var response = await _actionHttp.GetAsync($"{_settings.BackendUrl}/api/ft8/status", _stop.Token);
            if (!response.IsSuccessStatusCode)
            {
                return null;
            }

            await using var stream = await response.Content.ReadAsStreamAsync(_stop.Token);
            using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: _stop.Token);
            var root = doc.RootElement;
            var controller = root.TryGetProperty("automation_controller", out var controllerElement) ? controllerElement : default;
            var activeTarget = controller.ValueKind == JsonValueKind.Object && controller.TryGetProperty("active_target", out var activeTargetElement)
                ? activeTargetElement
                : default;

            var activeKey = activeTarget.ValueKind == JsonValueKind.Object
                ? GetJsonString(activeTarget, "key", GetJsonString(activeTarget, "call", ""))
                : "";

            return new Ft8Watch(
                AutoCallEnabled: root.TryGetProperty("auto_call_enabled", out var autoCall) && autoCall.ValueKind == JsonValueKind.True,
                AutoCallRemaining: GetJsonInt32(root, "auto_call_remaining") ?? -1,
                ActiveAttemptId: GetJsonString(root, "active_attempt_id", ""),
                ActiveTargetKey: activeKey,
                AutomationStatus: GetJsonString(root, "automation_status", ""),
                DigitalState: GetJsonString(root, "digital_state", ""),
                QueueLength: GetJsonInt32(root, "tx_queue_length") ?? 0);
        }
        catch
        {
            return null;
        }
    }

    private string? WsjtxStaleReason(WsjtxBridgeWatch bridge)
    {
        if (string.IsNullOrWhiteSpace(bridge.ClientId))
        {
            return "no WSJT-Z client attached to bridge";
        }

        if (bridge.LastSeenMs is > 45000)
        {
            return $"heartbeat stale ({bridge.LastSeenMs.Value / 1000}s)";
        }

        if (bridge.LastStatusAgeMs is > 60000)
        {
            return $"status stale ({bridge.LastStatusAgeMs.Value / 1000}s)";
        }

        if (bridge.Decoding && bridge.LastDecodeAgeMs is > 240000)
        {
            return $"decode stream stale while decoding ({bridge.LastDecodeAgeMs.Value / 1000}s)";
        }

        return null;
    }

    private string? AutoCallStallReason(WsjtxBridgeWatch bridge, Ft8Watch? ft8)
    {
        var now = DateTimeOffset.Now;
        var qsoState = string.IsNullOrWhiteSpace(bridge.QsoState) ? "unknown" : bridge.QsoState;
        if (!string.Equals(qsoState, _lastWsjtxQsoState, StringComparison.OrdinalIgnoreCase))
        {
            _lastWsjtxQsoState = qsoState;
            _lastWsjtxQsoStateChangedAt = now;
        }

        if (ft8 is null || !ft8.AutoCallEnabled)
        {
            _lastAutoCallProgressKey = "";
            _lastAutoCallRemaining = -1;
            _lastAutoCallProgressAt = now;
            return null;
        }

        var progressKey = $"{ft8.ActiveAttemptId}|{ft8.ActiveTargetKey}|{ft8.QueueLength}|{bridge.QsoState}|{bridge.LastDecodeMessage}";
        if (!string.Equals(progressKey, _lastAutoCallProgressKey, StringComparison.Ordinal) ||
            ft8.AutoCallRemaining != _lastAutoCallRemaining)
        {
            _lastAutoCallProgressKey = progressKey;
            _lastAutoCallRemaining = ft8.AutoCallRemaining;
            _lastAutoCallProgressAt = now;
        }

        var nonIdleQso = !string.IsNullOrWhiteSpace(qsoState) &&
                         !qsoState.Equals("idle", StringComparison.OrdinalIgnoreCase) &&
                         !qsoState.Equals("unknown", StringComparison.OrdinalIgnoreCase);

        var hasActiveAutoCallWork = !string.IsNullOrWhiteSpace(ft8.ActiveAttemptId) ||
                                    !string.IsNullOrWhiteSpace(ft8.ActiveTargetKey) ||
                                    ft8.QueueLength > 0 ||
                                    nonIdleQso;
        if (hasActiveAutoCallWork && now - _lastAutoCallProgressAt > TimeSpan.FromMinutes(8))
        {
            return $"Auto Call progress stalled; state={qsoState}, automation={ft8.AutomationStatus}, digital={ft8.DigitalState}";
        }

        return null;
    }

    private string? WsjtzRestartUnsafeReason(WsjtxBridgeWatch bridge, Ft8Watch? ft8, bool ignoreNonIdleQso = false)
    {
        var qsoState = string.IsNullOrWhiteSpace(bridge.QsoState) ? "unknown" : bridge.QsoState;
        var nonIdleQso = !qsoState.Equals("idle", StringComparison.OrdinalIgnoreCase) &&
                         !qsoState.Equals("unknown", StringComparison.OrdinalIgnoreCase);
        if (nonIdleQso && !ignoreNonIdleQso)
        {
            return $"active WSJT-Z QSO state is {qsoState}";
        }

        if (bridge.Transmitting)
        {
            return "WSJT-Z is transmitting";
        }

        if (ft8 is null)
        {
            return null;
        }

        if (!string.IsNullOrWhiteSpace(ft8.ActiveAttemptId) ||
            !string.IsNullOrWhiteSpace(ft8.ActiveTargetKey) ||
            ft8.QueueLength > 0)
        {
            return $"backend digital work is active (attempt={ft8.ActiveAttemptId}, target={ft8.ActiveTargetKey}, queue={ft8.QueueLength})";
        }

        return null;
    }

    private static string? WsjtzUiHungReason()
    {
        foreach (var process in Process.GetProcesses())
        {
            try
            {
                var name = process.ProcessName;
                if (!name.Contains("wsjt", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                try
                {
                    if (DateTime.Now - process.StartTime < TimeSpan.FromMinutes(2))
                    {
                        continue;
                    }
                }
                catch
                {
                    // Some processes may deny StartTime access.
                }

                if (process.MainWindowHandle != IntPtr.Zero && !process.Responding)
                {
                    return $"{process.ProcessName}:{process.Id} Windows UI is not responding";
                }
            }
            catch
            {
                // Process may exit while enumerating.
            }
        }

        return null;
    }

    private async Task<string?> FullAutoRepairUnsafeReasonAsync()
    {
        var bridge = await ReadWsjtxBridgeStatusAsync();
        var ft8 = await ReadFt8WatchStatusAsync();

        if (bridge is not null)
        {
            var reason = WsjtzRestartUnsafeReason(bridge, ft8);
            if (reason is not null)
            {
                return reason;
            }
        }

        if (ft8 is not null)
        {
            var automationBusy = !string.IsNullOrWhiteSpace(ft8.AutomationStatus) &&
                                 !ft8.AutomationStatus.Equals("idle", StringComparison.OrdinalIgnoreCase);
            var digitalBusy = !string.IsNullOrWhiteSpace(ft8.DigitalState) &&
                              !ft8.DigitalState.Equals("idle", StringComparison.OrdinalIgnoreCase);
            if (automationBusy || digitalBusy)
            {
                return $"backend FT8 state is active (automation={ft8.AutomationStatus}, digital={ft8.DigitalState})";
            }
        }

        if ((bridge is null || string.IsNullOrWhiteSpace(bridge.ClientId)) && IsDigitalEngineProcessRunning())
        {
            return "WSJT-Z is running but bridge state is unknown";
        }

        return null;
    }

    private static bool IsDigitalEngineProcessRunning()
    {
        foreach (var process in Process.GetProcesses())
        {
            try
            {
                var name = process.ProcessName;
                if (name.Contains("wsjt", StringComparison.OrdinalIgnoreCase) ||
                    name.StartsWith("mshv", StringComparison.OrdinalIgnoreCase) ||
                    name.Contains("jt9", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            catch
            {
                // Process may exit while enumerating.
            }
        }

        return false;
    }

    private static bool IsWsjtzProcessRunning()
    {
        foreach (var process in Process.GetProcesses())
        {
            try
            {
                if (process.ProcessName.Contains("wsjt", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            catch
            {
                // Process may exit while enumerating.
            }
        }

        return false;
    }

    private async Task MaybeApplyStartupOptionsAsync(AgentSnapshot snapshot)
    {
        if (_startupOptionsApplied || !_desiredRunning)
        {
            return;
        }

        if (DateTimeOffset.Now < _nextStartupOptionAttempt)
        {
            return;
        }

        if (_selectedDigitalEngine == "none")
        {
            _settings.EnableAutoCallOnStartup = false;
            _startupOptionsApplied = true;
            return;
        }

        if (!_settings.StartWsjtzWithAgent && !_settings.EnableAutoCallOnStartup)
        {
            _startupOptionsApplied = true;
            return;
        }

        var backendOk = snapshot.Components.Any(c => c.Id == "backend" && c.Status is ComponentStatus.Ok or ComponentStatus.Warning);
        var bridgeOk = snapshot.Components.Any(c => c.Id == "bridge-ws" && c.Status == ComponentStatus.Ok);
        if (!backendOk || !bridgeOk)
        {
            return;
        }

        _nextStartupOptionAttempt = DateTimeOffset.Now.AddSeconds(20);
        var success = true;
        if (_settings.StartWsjtzWithAgent)
        {
            success &= await LaunchWsjtzAsync();
        }

        if (_selectedDigitalEngine == "wsjtz" && _settings.EnableAutoCallOnStartup)
        {
            success &= await EnableAutoCallAsync();
        }

        _startupOptionsApplied = success;
        if (!success)
        {
            Log("Startup options will retry after services settle.");
        }
    }

    private async Task<bool> LaunchWsjtzAsync()
    {
        await RefreshDigitalEngineAsync();
        if (_selectedDigitalEngine == "none")
        {
            Log("Digital engine startup skipped: provider is none.");
            return true;
        }
        var start = await PostJsonAsync("/api/digital/start", JsonSerializer.Serialize(new { engine = _selectedDigitalEngine }));
        Log($"{_selectedDigitalEngine} startup: {start.Detail}");
        return start.Success;
    }

    private async Task RefreshDigitalEngineAsync()
    {
        try
        {
            using var response = await _http.GetAsync($"{_settings.BackendUrl}/api/digital/status", _stop.Token);
            if (!response.IsSuccessStatusCode) return;
            using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(_stop.Token));
            var selected = GetJsonString(doc.RootElement, "selected_engine", "");
            if (selected is "none" or "wsjtz" or "mshv_auto_dx")
            {
                _selectedDigitalEngine = selected;
                if (_settings.DigitalEngineProvider != selected)
                {
                    _settings.DigitalEngineProvider = selected;
                    if (selected == "none")
                    {
                        _settings.StartWsjtzWithAgent = false;
                        _settings.EnableAutoCallOnStartup = false;
                    }
                    _settings.Save();
                }
            }
        }
        catch (Exception ex) when (ex is HttpRequestException or JsonException or TaskCanceledException)
        {
            // Preserve the last known selection through temporary outages.
        }
    }

    private async Task MaybeMshvWatchdogAsync()
    {
        if (_selectedDigitalEngine == "none" || !_desiredRunning || !_settings.StartWsjtzWithAgent || _repairInProgress) return;
        try
        {
            using var response = await _http.GetAsync($"{_settings.BackendUrl}/api/digital/status", _stop.Token);
            if (!response.IsSuccessStatusCode) return;
            using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(_stop.Token));
            var root = doc.RootElement;
            // An operator stop is intentional. A running provider with degraded
            // health can be restarted by the backend's safe lifecycle service.
            var running = root.TryGetProperty("running", out var value) && value.ValueKind == JsonValueKind.True;
            var health = root.TryGetProperty("health", out var healthValue) ? healthValue : default;
            var state = GetJsonString(health, "status", "");
            var bridge = await ReadWsjtxBridgeStatusAsync();
            var stale = bridge is not null && WsjtxStaleReason(bridge) is not null;
            _mshvHealthFailures = running && (state is "error" or "stale" || stale) ? _mshvHealthFailures + 1 : 0;
            if (_mshvHealthFailures < Math.Max(2, _settings.FailureRestartThreshold) ||
                DateTimeOffset.Now - _lastWsjtzRestartAttempt < TimeSpan.FromSeconds(Math.Max(60, _settings.RestartCooldownSeconds * 4))) return;
            if (!await _actionLock.WaitAsync(0)) return;
            try
            {
                _lastWsjtzRestartAttempt = DateTimeOffset.Now;
                var result = await PostJsonAsync("/api/digital/restart", "{\"engine\":\"mshv_auto_dx\"}");
                Log($"MSHV watchdog restart: {result.Detail}");
                _mshvHealthFailures = 0;
            }
            finally { _actionLock.Release(); }
        }
        catch (Exception ex) when (ex is HttpRequestException or JsonException or TaskCanceledException)
        {
            // Backend health recovery is handled by the runtime watchdog.
        }
    }

    // Legacy startup remains for older backends; new startup always routes through
    // the provider service, which owns engine exclusion and TX release checks.
    private async Task<bool> LaunchLegacyWsjtzAsync()
    {
        var existing = await ReadWsjtxBridgeStatusAsync();
        if (existing is not null &&
            !string.IsNullOrWhiteSpace(existing.ClientId) &&
            existing.LastSeenMs is not null and < 60000 &&
            IsWsjtzProcessRunning())
        {
            Log("WSJT-Z startup skipped: bridge client is already attached.");
            return true;
        }

        var payload = """
        {
          "rigName": "OM0RX-WSJT-Z",
          "configName": "OM0RX-WSJT-Z"
        }
        """;
        var result = await PostJsonAsync("/api/wsjtx/launch-wsjtz-engine", payload);
        if (result.Success)
        {
            Log("WSJT-Z startup requested; waiting for bridge client.");
            var attached = await WaitForWsjtxClientAsync();
            if (attached)
            {
                Log("WSJT-Z bridge client attached.");
                return true;
            }

            Log("WSJT-Z startup did not attach a bridge client yet.");
            return false;
        }

        Log($"WSJT-Z startup failed: {result.Detail}");
        return false;
    }

    private async Task<bool> WaitForWsjtxClientAsync()
    {
        for (var attempt = 0; attempt < 12; attempt++)
        {
            if (attempt > 0)
            {
                await Task.Delay(TimeSpan.FromSeconds(5), _stop.Token);
            }

            try
            {
                using var response = await _actionHttp.GetAsync($"{_settings.BackendUrl}/api/service-health", _stop.Token);
                if (!response.IsSuccessStatusCode)
                {
                    continue;
                }

                await using var stream = await response.Content.ReadAsStreamAsync(_stop.Token);
                using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: _stop.Token);
                if (!doc.RootElement.TryGetProperty("services", out var services) || services.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                foreach (var service in services.EnumerateArray())
                {
                    var id = service.TryGetProperty("id", out var idProp) ? idProp.GetString() : "";
                    if (!string.Equals(id, "wsjtx", StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    var status = service.TryGetProperty("status", out var statusProp) ? statusProp.GetString() : "";
                    if (string.Equals(status, "ok", StringComparison.OrdinalIgnoreCase))
                    {
                        return true;
                    }
                }
            }
            catch (OperationCanceledException) when (_stop.IsCancellationRequested)
            {
                return false;
            }
            catch
            {
                // Service health is still settling; retry until the launch window expires.
            }
        }

        return false;
    }

    private async Task<bool> EnableAutoCallAsync()
    {
        await RefreshDigitalEngineAsync();
        if (_selectedDigitalEngine != "wsjtz")
        {
            _wsjtzNativeAutomationPending = false;
            Log("Selected provider does not use OM0RX Auto Call; setup skipped.");
            return true;
        }
        var limit = Math.Max(0, Math.Min(99, _settings.AutoCallLimit));
        var payload = $$"""
        {
          "tx_audio_frequency": 1500,
          "tx_even_first": true,
          "watchdog_ft8": 2,
          "watchdog_ft4": 2,
          "watchdog_enabled": true,
          "auto_cq": false,
          "auto_call": true,
          "cq_only": true,
          "auto_call_limit": {{limit}},
          "immediate": false
        }
        """;
        var result = await PostJsonAsync("/api/ft8/tx/enable", payload);
        if (result.Success)
        {
            Log($"Auto Call enabled with limit {limit}.");
            var uiApplied = await ApplyWsjtzNativeAutomationAsync();
            if (!uiApplied)
            {
                ScheduleWsjtzNativeAutomationRetry("native controls were not confirmed");
            }

            return true;
        }

        Log($"Auto Call enable failed: {result.Detail}");
        return false;
    }

    private async Task MaybeApplyPendingWsjtzNativeAutomationAsync()
    {
        if (_selectedDigitalEngine != "wsjtz")
        {
            _wsjtzNativeAutomationPending = false;
            return;
        }
        if (!_wsjtzNativeAutomationPending ||
            !_desiredRunning ||
            !_settings.EnableAutoCallOnStartup ||
            _repairInProgress ||
            DateTimeOffset.Now < _nextWsjtzNativeAutomationAttempt)
        {
            return;
        }

        if (!IsWsjtzProcessRunning())
        {
            _nextWsjtzNativeAutomationAttempt = DateTimeOffset.Now.AddSeconds(10);
            return;
        }

        var hungReason = WsjtzUiHungReason();
        if (hungReason is not null)
        {
            _nextWsjtzNativeAutomationAttempt = DateTimeOffset.Now.AddSeconds(15);
            return;
        }

        _wsjtzNativeAutomationAttempts++;
        _nextWsjtzNativeAutomationAttempt = DateTimeOffset.Now.AddSeconds(20);
        Log($"Retrying WSJT-Z native Auto Call controls (attempt {_wsjtzNativeAutomationAttempts}).");

        if (await ApplyWsjtzNativeAutomationAsync())
        {
            _wsjtzNativeAutomationPending = false;
            _wsjtzNativeAutomationAttempts = 0;
            _nextWsjtzNativeAutomationAttempt = DateTimeOffset.MinValue;
        }
    }

    private void ScheduleWsjtzNativeAutomationRetry(string reason)
    {
        _wsjtzNativeAutomationPending = true;
        _nextWsjtzNativeAutomationAttempt = DateTimeOffset.Now.AddSeconds(10);
        Log($"WSJT-Z native Auto Call controls pending: {reason}; will retry.");
    }

    private async Task<bool> ApplyWsjtzNativeAutomationAsync()
    {
        var script = WsjtzNativeAutomationScript();
        var result = await RunProcessAsync(
            "powershell.exe",
            new[] { "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script },
            _settings.ProjectRoot,
            8000);

        if (result.ExitCode == 0)
        {
            Log("WSJT-Z native Auto Call and CQ only controls enabled.");
            return true;
        }

        Log($"WSJT-Z native automation controls failed: {FirstLine(result.Error, result.Output, "unknown error")}");
        return false;
    }

    private async Task<PostResult> PostJsonAsync(string path, string json)
    {
        try
        {
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            using var response = await _actionHttp.PostAsync($"{_settings.BackendUrl}{path}", content, _stop.Token);
            var body = await response.Content.ReadAsStringAsync(_stop.Token);
            return new PostResult(response.IsSuccessStatusCode, FirstLine(body, response.ReasonPhrase ?? ""));
        }
        catch (Exception ex)
        {
            return new PostResult(false, ex.Message);
        }
    }

    private async Task StartAllWithoutLockAsync()
    {
        if (_settings.ManageDocker)
        {
            await StartDockerAsync();
        }

        var script = Path.Combine(_settings.ProjectRoot, "start_all.ps1");
        if (!File.Exists(script))
        {
            Log($"Cannot start: {script} was not found.");
            return;
        }

        var args = new List<string> { "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
            "-AppEnv", _settings.AppEnv, "-BackendHost", _settings.BackendHost, "-Port", _settings.BackendPort.ToString() };
        if (!_settings.StartLauncher) args.Add("-NoLauncher");
        var launcherStartedSignal = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        _launcherStartedSignal = launcherStartedSignal;
        var info = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            WorkingDirectory = _settings.ProjectRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var arg in args) info.ArgumentList.Add(arg);
        info.Environment["OM0RX_REMEMBER_WINDOW_LAYOUT"] = _settings.RememberWindowLayout ? "1" : "0";
        _runtimeProcess = new Process { StartInfo = info, EnableRaisingEvents = true };
        _runtimeProcess.Exited += (_, _) => Log("Managed runtime process exited.");
        _runtimeProcess.OutputDataReceived += (_, eventArgs) =>
        {
            if (!string.IsNullOrWhiteSpace(eventArgs.Data))
            {
                Log($"Runtime: {eventArgs.Data}");
                if (eventArgs.Data.Contains("Launcher UI ready", StringComparison.OrdinalIgnoreCase))
                {
                    launcherStartedSignal.TrySetResult(true);
                }
            }
        };
        _runtimeProcess.ErrorDataReceived += (_, eventArgs) =>
        {
            if (!string.IsNullOrWhiteSpace(eventArgs.Data)) Log($"Runtime error: {eventArgs.Data}");
        };
        if (!_runtimeProcess.Start())
        {
            _runtimeProcess.Dispose();
            _runtimeProcess = null;
            throw new InvalidOperationException("Windows did not start the OM0RX runtime process.");
        }
        _runtimeProcess.BeginOutputReadLine();
        _runtimeProcess.BeginErrorReadLine();
        _runtimeStartedAt = DateTimeOffset.Now;
        Log($"Started OM0RX runtime with PID {_runtimeProcess.Id}.");
    }

    private async Task StopManagedRuntimeAsync(string operation)
    {
        var process = _runtimeProcess;
        _runtimeProcess = null;
        _launcherStartedSignal = null;
        if (process is null)
        {
            return;
        }

        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }

            // Do not await Process.WaitForExitAsync here. Descendants of the
            // PowerShell supervisor can inherit its redirected pipe handles,
            // which may keep that task incomplete after the process has exited.
            var deadline = DateTimeOffset.UtcNow.AddSeconds(8);
            while (!process.HasExited && DateTimeOffset.UtcNow < deadline)
            {
                await Task.Delay(100);
            }

            if (!process.HasExited)
            {
                Log($"Managed runtime did not report exit within 8 seconds during {operation}; continuing forced cleanup.");
            }
        }
        catch (Exception ex)
        {
            Log($"Could not terminate managed runtime during {operation}: {ex.Message}");
        }
        finally
        {
            try { process.CancelOutputRead(); } catch { }
            try { process.CancelErrorRead(); } catch { }
            process.Dispose();
        }
    }

    private async Task EnsureRestartWindowsAsync()
    {
        await WaitForLauncherReadyAsync();

        var startupSuccess = true;
        await RefreshDigitalEngineAsync();
        if (_selectedDigitalEngine != "none" && _settings.StartWsjtzWithAgent)
        {
            startupSuccess &= await LaunchWsjtzAsync();
        }
        if (_selectedDigitalEngine == "wsjtz" && _settings.EnableAutoCallOnStartup)
        {
            startupSuccess &= await EnableAutoCallAsync();
        }

        _startupOptionsApplied = startupSuccess;
        if (!startupSuccess)
        {
            throw new InvalidOperationException("Restart brought up the services, but WSJT-Z startup or Auto Call setup did not complete.");
        }
    }

    private async Task<bool> TryBeginActionAsync(string actionName)
    {
        if (await _actionLock.WaitAsync(0))
        {
            return true;
        }

        Log($"{actionName} ignored because another agent action is already in progress.");
        return false;
    }

    private async Task<bool> WaitForBackendReadyAsync(TimeSpan timeout)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        while (!_stop.IsCancellationRequested && DateTimeOffset.UtcNow < deadline)
        {
            try
            {
                using var response = await _http.GetAsync($"{_settings.BackendUrl}/api/health", _stop.Token);
                if (response.IsSuccessStatusCode)
                {
                    return true;
                }
            }
            catch (OperationCanceledException) when (_stop.IsCancellationRequested)
            {
                return false;
            }
            catch
            {
                // The backend is expected to refuse connections while restarting.
            }

            await Task.Delay(1000, _stop.Token);
        }

        return false;
    }

    private async Task StartDockerAsync()
    {
        if (!_settings.ManageDocker) return;
        var composePath = Path.Combine(_settings.ProjectRoot, _settings.DockerComposeFile);
        if (!File.Exists(composePath)) return;

        if (!await EnsureDockerDaemonAsync())
        {
            Log("Docker compose start skipped because Docker Desktop did not become ready.");
            return;
        }

        var result = await RunProcessAsync("docker", new[] { "compose", "-f", composePath, "up", "-d" }, _settings.ProjectRoot, 30000);
        if (result.ExitCode == 0)
        {
            Log("Docker compose is up.");
        }
        else
        {
            Log($"Docker compose start failed: {FirstLine(result.Error, result.Output, "unknown error")}");
        }
    }

    private async Task WaitForLauncherReadyAsync()
    {
        if (!_settings.StartLauncher)
        {
            return;
        }

        var signal = _launcherStartedSignal;
        if (signal is null)
        {
            throw new InvalidOperationException("Desktop launcher tracking was not initialized.");
        }

        Log("Backend is ready; waiting for a visible desktop UI.");
        try
        {
            await signal.Task.WaitAsync(TimeSpan.FromSeconds(60), _stop.Token);
        }
        catch (TimeoutException)
        {
            throw new InvalidOperationException("Timed out waiting for a visible desktop UI. Check start_all-launcher logs.");
        }
        Log("Desktop UI is visible.");
    }

    private async Task<bool> EnsureDockerDaemonAsync()
    {
        var version = await RunProcessAsync("docker", new[] { "version", "--format", "{{.Server.Version}}" }, _settings.ProjectRoot, 5000);
        if (version.ExitCode == 0) return true;

        var desktopPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            "Docker",
            "Docker",
            "Docker Desktop.exe");
        if (!File.Exists(desktopPath))
        {
            Log("Docker daemon is unavailable and Docker Desktop is not installed in the standard location.");
            return false;
        }

        try
        {
            if (Process.GetProcessesByName("Docker Desktop").Length == 0)
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = desktopPath,
                    UseShellExecute = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                });
                Log("Docker daemon was unavailable; Docker Desktop launch requested.");
            }
        }
        catch (Exception ex)
        {
            Log($"Could not launch Docker Desktop: {ex.Message}");
            return false;
        }

        var deadline = DateTimeOffset.UtcNow + TimeSpan.FromSeconds(60);
        while (!_stop.IsCancellationRequested && DateTimeOffset.UtcNow < deadline)
        {
            await Task.Delay(2000, _stop.Token);
            version = await RunProcessAsync("docker", new[] { "version", "--format", "{{.Server.Version}}" }, _settings.ProjectRoot, 5000);
            if (version.ExitCode == 0)
            {
                Log($"Docker Desktop is ready ({version.Output.Trim()}).");
                return true;
            }
        }

        return false;
    }

    private async Task<bool> TryPostAsync(string path)
    {
        try
        {
            using var response = await _http.PostAsync($"{_settings.BackendUrl}{path}", null, _stop.Token);
            if (!response.IsSuccessStatusCode) return false;
            var body = await response.Content.ReadAsStringAsync(_stop.Token);
            if (string.IsNullOrWhiteSpace(body)) return true;
            using var doc = JsonDocument.Parse(body);
            return !doc.RootElement.TryGetProperty("success", out var success) || success.ValueKind != JsonValueKind.False;
        }
        catch
        {
            return false;
        }
    }

    private async Task HaltDigitalTxAsync()
    {
        var wsjtzHalted = await TryPostAsync("/api/digital/halt-tx");
        var builtinHalted = await TryPostAsync("/api/ft8/tx/halt");
        Log($"Pre-stop TX halt requested (WSJT-Z: {wsjtzHalted}, built-in digital: {builtinHalted}).");
        await Task.Delay(750);
    }

    private async Task<bool> IsRuntimeLikelyRunningAsync()
    {
        if (_runtimeProcess is { HasExited: false }) return true;

        // Never start a competing supervisor while a live atomic owner
        // manifest exists. Exact listener verification is intentionally left
        // to the monitor: Get-NetTCPConnection can take several seconds during
        // Windows login and a timeout must not trigger destructive cleanup of
        // an otherwise healthy runtime.
        var path = Path.Combine(_settings.ProjectRoot, "logs", "runtime_owner.json");
        try
        {
            if (!File.Exists(path)) return false;
            using var doc = JsonDocument.Parse(await File.ReadAllTextAsync(path, _stop.Token));
            var root = doc.RootElement;
            if (GetJsonInt32(root, "schema") != 1 || GetJsonString(root, "state", "") != "active") return false;
            if (!root.TryGetProperty("ports", out var ports)
                || GetJsonInt32(ports, "backend") != _settings.BackendPort
                || GetJsonInt32(ports, "bridge_ws") != 8091
                || GetJsonInt32(ports, "bridge_command") != 8092)
            {
                return false;
            }

            foreach (var role in new[] { "supervisor", "backend", "bridge" })
            {
                if (!root.TryGetProperty(role, out var identity) || !RuntimeProcessIdentityMatches(identity)) return false;
            }

            return !string.IsNullOrWhiteSpace(GetJsonString(root, "owner_id", ""));
        }
        catch
        {
            return false;
        }
    }

    private async Task<IReadOnlyList<int>> GetProjectProcessIdsAsync()
    {
        var script = ProjectProcessQueryScript(stop: false);
        var result = await RunProcessAsync("powershell.exe", new[] { "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script }, _settings.ProjectRoot, 5000);
        return result.Output
            .Split(new[] { '\r', '\n', ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(s => int.TryParse(s, out var pid) ? pid : 0)
            .Where(pid => pid > 0 && pid != Environment.ProcessId)
            .Distinct()
            .ToList();
    }

    private async Task StopProjectProcessesAsync()
    {
        var script = ProjectProcessQueryScript(stop: true);
        var result = await RunProcessAsync("powershell.exe", new[] { "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script }, _settings.ProjectRoot, 15000);
        if (result.ExitCode != 0)
        {
            Log($"Project process cleanup warning: {FirstLine(result.Error, result.Output, "unknown error")}");
        }
    }

    private async Task<bool> StopDigitalEngineProcessesAsync()
    {
        // A successful provider stop includes TX-off verification. Never bypass
        // a provider refusal by force-killing its process.
        if (await TryPostAsync("/api/digital/stop")) return true;

        // During a complete backend/runtime crash there is no API left to
        // acknowledge the stop.  That must not deadlock automatic recovery
        // when Windows independently proves that no digital engine process is
        // alive.  Fail closed if enumeration itself fails or finds an engine.
        var engineProcessIds = await TryGetDigitalEngineProcessIdsAsync();
        if (engineProcessIds is { Count: 0 })
        {
            Log("Digital stop API unavailable, but no MSHV/WSJT engine process exists; recovery may continue.");
            return true;
        }

        var detail = engineProcessIds is null
            ? "process enumeration failed"
            : $"engine process IDs still present: {string.Join(',', engineProcessIds)}";
        Log($"Digital engine stop not confirmed ({detail}); process cleanup skipped.");
        return false;
    }

    private async Task<IReadOnlyList<int>?> TryGetDigitalEngineProcessIdsAsync()
    {
        var script = DigitalEngineProcessScript(stop: false);
        var result = await RunProcessAsync(
            "powershell.exe",
            new[] { "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script },
            _settings.ProjectRoot,
            10000);
        if (result.ExitCode != 0)
        {
            Log($"Digital engine process enumeration warning: {FirstLine(result.Error, result.Output, "unknown error")}");
            return null;
        }

        return result.Output
            .Split(new[] { '\r', '\n', ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(value => int.TryParse(value, out var pid) ? pid : 0)
            .Where(pid => pid > 0 && pid != Environment.ProcessId)
            .Distinct()
            .ToList();
    }

    private async Task StopLegacyDigitalEngineProcessesAsync()
    {
        var script = DigitalEngineStopScript();
        var result = await RunProcessAsync("powershell.exe", new[] { "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script }, _settings.ProjectRoot, 15000);
        if (result.ExitCode != 0)
        {
            Log($"Digital engine cleanup warning: {FirstLine(result.Error, result.Output, "unknown error")}");
        }
        var stopped = FirstLine(result.Output);
        if (!string.IsNullOrWhiteSpace(stopped))
        {
            Log($"Stopped digital engine process IDs: {stopped}");
        }
    }

    private string ProjectProcessQueryScript(bool stop)
    {
        var root = PsQuote(_settings.ProjectRoot);
        var action = stop
            ? "function Stop-Tree([int]$id) { @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object ParentProcessId -eq $id) | ForEach-Object { Stop-Tree ([int]$_.ProcessId) }; Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }; foreach ($p in $matches) { Stop-Tree ([int]$p.ProcessId) }"
            : "$matches | Select-Object -ExpandProperty ProcessId";

        return "$rootPath = " + root + "; " +
               "$patterns = @('start_all.ps1','start_services_only.ps1','backend.main:app','sdc-bridge-server.js','launch_windows.py'); " +
               "$matches = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $cmd = $_.CommandLine; $cmd -and $_.ProcessId -ne $PID -and $cmd -like \"*$rootPath*\" -and ($patterns | Where-Object { $cmd -like \"*$_*\" }) }); " +
               action;
    }

    private string DigitalEngineStopScript()
    {
        return DigitalEngineProcessScript(stop: true);
    }

    private string DigitalEngineProcessScript(bool stop)
    {
        var root = PsQuote(_settings.ProjectRoot);
        var action = stop
            ? "foreach ($id in $ids) { Stop-Tree ([int]$id) }; $ids -join ','"
            : "$ids -join ','";
        // The legacy decode-status helper cannot key the radio. It may survive
        // a backend crash, so include it in explicit cleanup but never let it
        // masquerade as a live transmitter during the fail-closed recovery
        // check.
        var helperPattern = stop ? "'scripts\\wsjtz\\om0rx_decode_status_server.py'," : "";
        return "$rootPath = " + root + "; " +
               "$patterns = @(" + helperPattern + "'data\\build\\wsjt-z-om0rx','data\\build\\wsjtx-improved-om0rx','data\\build\\mshv-auto-dx\\runtime\\MSHV_OM0RX.exe','--rig-name OM0RX-WSJT-Z','--rig-name OM0RX-AUTO','WSJT-X - OM0RX-WSJT-Z','WSJT-X - OM0RX-AUTO'); " +
               "$matches = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $cmd = $_.CommandLine; $cmd -and $_.ProcessId -ne $PID -and (($cmd -like \"*$rootPath*\") -or ($cmd -like '*OM0RX*')) -and ($patterns | Where-Object { $cmd -like \"*$_*\" }) }); " +
               "$ids = @($matches | Select-Object -ExpandProperty ProcessId -Unique); " +
               "function Stop-Tree([int]$processId) { @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object ParentProcessId -eq $processId) | ForEach-Object { Stop-Tree ([int]$_.ProcessId) }; Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue }; " +
               action;
    }

    private static string WsjtzNativeAutomationScript()
    {
        return """
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
function Find-WsjtzWindow {
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
  for ($i = 0; $i -lt $windows.Count; $i++) {
    $window = $windows.Item($i)
    if ($window.Current.Name -like '*OM0RX-WSJT-Z*') {
      return $window
    }
  }
  return $null
}
function Set-Checkbox {
  param(
    [Parameter(Mandatory=$true)] $Window,
    [Parameter(Mandatory=$true)] [string] $Name,
    [Parameter(Mandatory=$true)] [bool] $Checked,
    [bool] $Required = $true
  )
  $condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Name)
  $element = $Window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
  if (-not $element) {
    if ($Required) {
      throw "Control not found: $Name"
    }
    return $false
  }
  $pattern = $element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
  $isOn = $pattern.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On
  if ($isOn -ne $Checked) {
    $pattern.Toggle()
    Start-Sleep -Milliseconds 300
  }
  return $true
}
$window = Find-WsjtzWindow
if (-not $window) {
  throw 'WSJT-Z OM0RX window not found'
}
# Some WSJT-Z layouts do not expose Auto CQ in the UI Automation tree. It is
# already forced off in the profile and backend, so its absence must not abort
# before the required Auto Call and CQ-only controls are enabled.
Set-Checkbox -Window $window -Name 'Auto CQ' -Checked $false -Required $false | Out-Null
Set-Checkbox -Window $window -Name 'Auto Call' -Checked $true
Set-Checkbox -Window $window -Name 'CQ only' -Checked $true
'WSJT-Z native automation controls applied'
""";
    }

    private static async Task<ProcessResult> RunProcessAsync(string fileName, IReadOnlyList<string> arguments, string workingDirectory, int timeoutMs)
    {
        try
        {
            using var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = fileName,
                    WorkingDirectory = workingDirectory,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                }
            };

            foreach (var argument in arguments) process.StartInfo.ArgumentList.Add(argument);
            process.Start();
            var outputTask = process.StandardOutput.ReadToEndAsync();
            var errorTask = process.StandardError.ReadToEndAsync();
            var waitTask = process.WaitForExitAsync();
            // Bound both process exit and redirected stream drainage. Docker CLI
            // plugins can inherit stdout/stderr on Windows; in that case
            // docker.exe exits but ReadToEndAsync never completes, which used to
            // hold the supervisor action lock indefinitely.
            var completionTask = Task.WhenAll(waitTask, outputTask, errorTask);
            var completed = await Task.WhenAny(completionTask, Task.Delay(timeoutMs));
            if (completed != completionTask)
            {
                try
                {
                    if (!process.HasExited)
                    {
                        process.Kill(entireProcessTree: true);
                    }
                }
                catch { }
                await Task.WhenAny(waitTask, Task.Delay(2000));
                var output = outputTask.IsCompletedSuccessfully ? outputTask.Result : "";
                var error = errorTask.IsCompletedSuccessfully ? errorTask.Result : "";
                return new ProcessResult(-1, output, FirstLine(error, "Timed out"));
            }

            await completionTask;
            return new ProcessResult(process.ExitCode, await outputTask, await errorTask);
        }
        catch (Exception ex)
        {
            return new ProcessResult(-1, "", ex.Message);
        }
    }

    private static string GetJsonString(JsonElement element, string property, string fallback)
    {
        return element.ValueKind == JsonValueKind.Object && element.TryGetProperty(property, out var value) && value.ValueKind != JsonValueKind.Null
            ? value.ToString()
            : fallback;
    }

    private static int? GetJsonInt32(JsonElement element, string property)
    {
        if (!element.TryGetProperty(property, out var value))
        {
            return null;
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var number))
        {
            return number;
        }

        return int.TryParse(value.ToString(), out number) ? number : null;
    }

    private static long? GetJsonInt64(JsonElement element, string property)
    {
        if (!element.TryGetProperty(property, out var value))
        {
            return null;
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number))
        {
            return number;
        }

        return long.TryParse(value.ToString(), out number) ? number : null;
    }

    private static ComponentStatus MapBackendStatus(string status) => status.ToLowerInvariant() switch
    {
        "ok" => ComponentStatus.Ok,
        "busy" => ComponentStatus.Busy,
        "warn" => ComponentStatus.Warning,
        "warning" => ComponentStatus.Warning,
        "off" => ComponentStatus.Off,
        "error" => ComponentStatus.Error,
        _ => ComponentStatus.Unknown,
    };

    private static string FirstLine(params string[] values)
    {
        foreach (var value in values)
        {
            var line = value.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries).FirstOrDefault();
            if (!string.IsNullOrWhiteSpace(line)) return line.Trim();
        }

        return "";
    }

    private static string PsQuote(string value) => "'" + value.Replace("'", "''") + "'";

    private void Log(string message)
    {
        var line = $"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss} {message}";
        lock (_sync)
        {
            _events.Add(line);
            if (_events.Count > 250) _events.RemoveRange(0, _events.Count - 250);
        }

        try
        {
            var logDir = Path.Combine(_settings.ProjectRoot, "logs");
            Directory.CreateDirectory(logDir);
            File.AppendAllText(Path.Combine(logDir, "om0rx-agent.log"), line + Environment.NewLine, Encoding.UTF8);
        }
        catch
        {
            // Best-effort runtime logging.
        }

        EventLogged?.Invoke(this, line);
    }

    public void Dispose()
    {
        _stop.Cancel();
        _http.Dispose();
        _actionHttp.Dispose();
        _actionLock.Dispose();
        _stop.Dispose();
    }

    private sealed record ProcessResult(int ExitCode, string Output, string Error);

    private sealed record PostResult(bool Success, string Detail);

    private sealed record WsjtxBridgeWatch(
        string ClientId,
        long? LastSeenMs,
        long? LastStatusAgeMs,
        long? LastDecodeAgeMs,
        string QsoState,
        bool Decoding,
        bool Transmitting,
        string LastDecodeMessage);

    private sealed record Ft8Watch(
        bool AutoCallEnabled,
        int AutoCallRemaining,
        string ActiveAttemptId,
        string ActiveTargetKey,
        string AutomationStatus,
        string DigitalState,
        int QueueLength);
}
