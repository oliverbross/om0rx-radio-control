using Om0rxAgent;

if (args.Length != 5
    || !int.TryParse(args[2], out var holdMilliseconds)
    || holdMilliseconds < 0)
{
    Console.Error.WriteLine(
        "Usage: probe <controller-family> <launch-source> <hold-ms> <mutex-name> <owner-path>");
    return 64;
}

StationControllerOwnership? ownership;
try
{
    ownership = StationControllerOwnership.TryAcquire(
        args[0],
        args[1],
        out var failure,
        args[3],
        args[4]);
    if (ownership is null)
    {
        Console.Error.WriteLine(failure);
        return StationControllerOwnership.ConflictExitCode;
    }
}
catch (Exception ex)
{
    Console.Error.WriteLine($"Station controller ownership could not be established: {ex.Message}");
    return StationControllerOwnership.ConflictExitCode + 1;
}

using (ownership)
{
    Console.WriteLine($"ACQUIRED {Environment.ProcessId}");
    if (holdMilliseconds > 0) Thread.Sleep(holdMilliseconds);
}
return 0;
