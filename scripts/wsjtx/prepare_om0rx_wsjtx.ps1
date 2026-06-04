param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$sourceArchive = Join-Path $ProjectRoot "data\research\wsjtx-improved-3.1.0\src\wsjtx.tgz"
$patchPath = Join-Path $ProjectRoot "docs\wsjtx\om0rx-start-target-qso.patch"
$workRoot = Join-Path $ProjectRoot "data\build\wsjtx-improved-om0rx"
$sourceRoot = Join-Path $workRoot "src"

if (-not (Test-Path -LiteralPath $sourceArchive)) {
    throw "WSJT-X Improved source archive not found: $sourceArchive"
}
if (-not (Test-Path -LiteralPath $patchPath)) {
    throw "OM0RX WSJT patch not found: $patchPath"
}

$resolvedProject = (Resolve-Path $ProjectRoot).Path
$resolvedWorkParent = Split-Path -Parent $workRoot
if (-not (Test-Path -LiteralPath $resolvedWorkParent)) {
    New-Item -ItemType Directory -Path $resolvedWorkParent | Out-Null
}
$resolvedWorkParent = (Resolve-Path $resolvedWorkParent).Path
if (-not $resolvedWorkParent.StartsWith((Join-Path $resolvedProject "data"), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to prepare outside project data directory: $resolvedWorkParent"
}

if ((Test-Path -LiteralPath $workRoot) -and -not $Force) {
    Write-Host "Source already prepared: $sourceRoot"
    Write-Host "Pass -Force to recreate it."
    exit 0
}

Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $sourceRoot | Out-Null

tar -xzf $sourceArchive -C $sourceRoot --strip-components=1

$relativeSource = "data/build/wsjtx-improved-om0rx/src"
git -C $ProjectRoot apply --check --directory=$relativeSource $patchPath
git -C $ProjectRoot apply --directory=$relativeSource $patchPath

Write-Host "Prepared patched WSJT-X Improved source:"
Write-Host "  $sourceRoot"
