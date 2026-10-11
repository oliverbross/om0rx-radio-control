using System.Diagnostics;
using Microsoft.Win32;

namespace Om0rxAgent;

public static class StartupRegistration
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ValueName = "OM0RX Radio Control Agent";

    public static bool IsEnabled()
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable: false);
        return key?.GetValue(ValueName) is string value && value.Contains(Application.ExecutablePath, StringComparison.OrdinalIgnoreCase);
    }

    public static void SetEnabled(bool enabled, AgentSettings settings)
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable: true) ??
                        Registry.CurrentUser.CreateSubKey(RunKey, writable: true);

        if (enabled)
        {
            if (RemoteControllerStartupEnabled())
            {
                throw new InvalidOperationException(
                    "The 'OM0RX Remote Station Agent' scheduled task is enabled. Disable or uninstall that controller task before enabling legacy startup. The remote tray task may remain enabled.");
            }
            var command = $"\"{Application.ExecutablePath}\" --project-root \"{settings.ProjectRoot}\" --port {settings.BackendPort} --launch-source hkcu-run";
            key.SetValue(ValueName, command, RegistryValueKind.String);
        }
        else
        {
            key.DeleteValue(ValueName, throwOnMissingValue: false);
        }
    }

    private static bool RemoteControllerStartupEnabled()
    {
        try
        {
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = "schtasks.exe",
                Arguments = "/Query /TN \"OM0RX Remote Station Agent\" /XML",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
            });
            if (process is null) return false;
            var xml = process.StandardOutput.ReadToEnd();
            process.WaitForExit(5000);
            return process.HasExited
                && process.ExitCode == 0
                && xml.Contains("<Enabled>true</Enabled>", StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }
}
