$ErrorActionPreference = "Stop"

if (-not (Get-Command tailscale.exe -ErrorAction SilentlyContinue)) {
    throw "Tailscale is not installed or tailscale.exe is not on PATH"
}

& tailscale.exe serve --bg --https=443 http://127.0.0.1:8840
if ($LASTEXITCODE -ne 0) { throw "Tailscale Serve configuration failed" }
& tailscale.exe serve status
if ($LASTEXITCODE -ne 0) { throw "Could not read Tailscale Serve status" }
