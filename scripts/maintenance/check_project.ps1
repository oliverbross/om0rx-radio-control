param(
    [switch]$IncludeNpmAudit,
    [switch]$IncludeLive,
    [switch]$UsePytest
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$startedAt = Get-Date
$failures = New-Object System.Collections.Generic.List[string]

function Invoke-CheckStep {
    param(
        [string]$Name,
        [scriptblock]$ScriptBlock
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    $stepStartedAt = Get-Date

    try {
        & $ScriptBlock
        $elapsed = [int]((Get-Date) - $stepStartedAt).TotalSeconds
        Write-Host "PASS $Name ($elapsed s)" -ForegroundColor Green
    }
    catch {
        $failures.Add($Name)
        Write-Host "FAIL $Name" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
}

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exited with code $LASTEXITCODE"
    }
}

function Test-CommandAvailable {
    param([string]$CommandName)
    return $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

Push-Location $ProjectRoot
try {
    $maintenanceSettingsDir = Join-Path ([System.IO.Path]::GetTempPath()) "om0rx-radio-control-maintenance"
    New-Item -ItemType Directory -Force -Path $maintenanceSettingsDir | Out-Null
    $maintenanceAppSettings = Join-Path $maintenanceSettingsDir "local_settings.json"
    $maintenanceLocalSecrets = Join-Path $maintenanceSettingsDir "local_secrets.json"
    Set-Content -LiteralPath $maintenanceAppSettings -Value "{}" -Encoding UTF8
    if (Test-Path -LiteralPath (Join-Path $ProjectRoot "settings\local_secrets.json")) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot "settings\local_secrets.json") -Destination $maintenanceLocalSecrets -Force
    }
    $env:OM0RX_APP_SETTINGS_PATH = $maintenanceAppSettings
    $env:OM0RX_LOCAL_SECRETS_PATH = $maintenanceLocalSecrets

    Invoke-CheckStep "Python syntax compile" {
        @'
import compileall
import pathlib
import sys

roots = [
    pathlib.Path("backend"),
    pathlib.Path("services"),
    pathlib.Path("radio_control"),
    pathlib.Path("scripts"),
    pathlib.Path("tests"),
]

ok = True
for root in roots:
    if root.exists():
        ok = compileall.compile_dir(str(root), quiet=1) and ok

sys.exit(0 if ok else 1)
'@ | python -
        if ($LASTEXITCODE -ne 0) {
            throw "Python compile failed"
        }
    }

    Invoke-CheckStep "Backend import" {
        Invoke-NativeCommand python @("-c", "import backend.main; print('backend import OK')")
    }

    Invoke-CheckStep "Ruff correctness" {
        Invoke-NativeCommand python @("-m", "ruff", "check", "backend", "services", "radio_control", "activity_intelligence", "--select", "F,E9")
    }

    Invoke-CheckStep "FastAPI duplicate route scan" {
        @'
from collections import Counter
import backend.main

routes = []
for route in backend.main.app.routes:
    methods = tuple(sorted(getattr(route, "methods", []) or []))
    path = getattr(route, "path", None)
    if path:
        routes.append((methods, path))

counts = Counter(routes)
duplicates = [(methods, path, count) for (methods, path), count in counts.items() if count > 1]

if duplicates:
    for methods, path, count in duplicates:
        print(f"duplicate route {methods} {path}: {count}")
    raise SystemExit(1)

print("no duplicate routes")
'@ | python -
        if ($LASTEXITCODE -ne 0) {
            throw "Duplicate route scan failed"
        }
    }

    Invoke-CheckStep "PowerShell parser check" {
        $parseFailed = $false
        git ls-files "*.ps1" |
            ForEach-Object { Get-Item -LiteralPath (Join-Path $ProjectRoot $_) } |
            ForEach-Object {
                $tokens = $null
                $errors = $null
                [System.Management.Automation.Language.Parser]::ParseFile(
                    $_.FullName,
                    [ref]$tokens,
                    [ref]$errors
                ) | Out-Null

                if ($errors.Count -gt 0) {
                    $parseFailed = $true
                    Write-Host "PowerShell parse failed: $($_.FullName)" -ForegroundColor Red
                    $errors | ForEach-Object {
                        Write-Host "  $($_.Message)" -ForegroundColor Red
                    }
                }
            }

        if ($parseFailed) {
            throw "PowerShell parser check failed"
        }
    }

    Invoke-CheckStep "JavaScript syntax check" {
        $jsFiles = @()
        $jsFiles += Get-ChildItem -Path "bridge" -Filter *.js -File
        $jsFiles += Get-ChildItem -Path "frontend\js" -Filter *.js -File
        $jsFiles += Get-ChildItem -Path "tests\smoke" -Filter *.js -File
        $jsFiles += Get-ChildItem -Path "tests\live" -Filter *.js -File

        foreach ($file in $jsFiles) {
            Invoke-NativeCommand node @("--check", $file.FullName)
        }
    }

    Invoke-CheckStep "Bash syntax check" {
        if (-not (Test-CommandAvailable "bash")) {
            Write-Host "SKIP bash is not available on this machine" -ForegroundColor Yellow
            return
        }

        try {
            & bash -lc "exit 0" *> $null
            $bashExitCode = $LASTEXITCODE
        }
        catch {
            Write-Host "SKIP bash command is present but cannot execute" -ForegroundColor Yellow
            return
        }

        if ($bashExitCode -ne 0) {
            Write-Host "SKIP bash command is present but cannot execute" -ForegroundColor Yellow
            return
        }

        Invoke-NativeCommand bash @("-n", "scripts/start/start_webapp.sh")
    }

    Invoke-CheckStep "Safe smoke checks" {
        Invoke-NativeCommand python @("-m", "pytest", "tests\smoke", "-q")
    }

    if ($UsePytest) {
        Invoke-CheckStep "Pytest safe smoke subset" {
            Invoke-NativeCommand python @("-m", "pytest", "tests\smoke", "-q")
        }
    }

    Invoke-CheckStep "Old project reference scan" {
        if (-not (Test-CommandAvailable "rg")) {
            Write-Host "SKIP ripgrep is not available on this machine" -ForegroundColor Yellow
            return
        }

        & rg -n "(?i)Wave-Flex-Spots|waave-flex-spots|wave-flex-spots|wave-flex|waave-flex|waveflex|c:\\Projects\\wave|documentation\\FEATURE_NAME|/documentation" . -g "*.*" -g "!data/**" -g "!logs/**" -g "!docs/archive/**" -g "!vendor/**" -g "!node_modules/**" -g "!om0rx_radio_control.egg-info/**" -g "!__pycache__/**" -g "!**/__pycache__/**" -g "!.pytest_cache/**" -g "!.git/**" -g "!scripts/maintenance/check_project.ps1"
        if ($LASTEXITCODE -eq 0) {
            throw "Old project references were found"
        }
        if ($LASTEXITCODE -gt 1) {
            throw "ripgrep failed with code $LASTEXITCODE"
        }
    }

    Invoke-CheckStep "Git whitespace check" {
        if (-not (Test-CommandAvailable "git")) {
            Write-Host "SKIP git is not available on this machine" -ForegroundColor Yellow
            return
        }

        Invoke-NativeCommand git @("diff", "--check")
    }

    if ($IncludeNpmAudit) {
        Invoke-CheckStep "npm audit" {
            Invoke-NativeCommand npm @("audit", "--omit=dev")
        }
    }

    if ($IncludeLive) {
        Invoke-CheckStep "Live/local integration checks" {
            $liveChecks = @(
                "tests\live\test_qth_data.py",
                "tests\live\test_wsjtx_adif.py",
                "tests\live\test_ft8_status.py"
            )

            foreach ($testPath in $liveChecks) {
                Invoke-NativeCommand python @($testPath)
            }
        }
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "============================================================"

if ($failures.Count -gt 0) {
    Write-Host "Project check failed:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

$totalSeconds = [int]((Get-Date) - $startedAt).TotalSeconds
Write-Host "Project check passed in $totalSeconds seconds" -ForegroundColor Green
exit 0
