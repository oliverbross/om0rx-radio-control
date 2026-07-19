namespace Om0rxAgent;

public enum ComponentStatus
{
    Unknown,
    Ok,
    Busy,
    Warning,
    Error,
    Off,
}

public sealed record ComponentProbe(
    string Id,
    string Name,
    ComponentStatus Status,
    string Value,
    string Detail);

public sealed record AgentSnapshot(
    DateTimeOffset Timestamp,
    IReadOnlyList<ComponentProbe> Components,
    bool ManagedRuntimeRunning,
    bool AutoRestartEnabled,
    bool RepairInProgress,
    string Summary)
{
    public ComponentStatus OverallStatus
    {
        get
        {
            if (Components.Any(c => c.Status == ComponentStatus.Error)) return ComponentStatus.Error;
            if (Components.Any(c => c.Status == ComponentStatus.Warning)) return ComponentStatus.Warning;
            if (Components.Any(c => c.Status == ComponentStatus.Busy)) return ComponentStatus.Busy;
            if (Components.Count > 0 && Components.All(c => c.Status is ComponentStatus.Off or ComponentStatus.Unknown)) return ComponentStatus.Off;
            return ComponentStatus.Ok;
        }
    }
}
