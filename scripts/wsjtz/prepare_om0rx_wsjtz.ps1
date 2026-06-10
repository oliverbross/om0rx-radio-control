param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$UpstreamUrl = "https://github.com/sq9fve/wsjt-z.git",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$patchPath = Join-Path $ProjectRoot "docs\wsjtx\om0rx-wsjtz-enrichment.patch"
$researchRoot = Join-Path $ProjectRoot "data\research\wsjt-z"
$workRoot = Join-Path $ProjectRoot "data\build\wsjt-z-om0rx"
$sourceRoot = Join-Path $workRoot "src"

if (-not (Test-Path -LiteralPath $patchPath)) {
    throw "OM0RX WSJT-Z enrichment patch not found: $patchPath"
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

if ((Test-Path -LiteralPath $sourceRoot) -and -not $Force) {
    Write-Host "Source already prepared: $sourceRoot"
    Write-Host "Pass -Force to recreate it from upstream."
    exit 0
}

if (-not (Test-Path -LiteralPath $researchRoot)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $researchRoot) | Out-Null
    git clone $UpstreamUrl $researchRoot
} else {
    git -C $researchRoot fetch --tags --prune origin
}

$latestRef = "origin/master"

Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
git clone $researchRoot $sourceRoot
git -C $sourceRoot checkout master
git -C $sourceRoot reset --hard $latestRef
git -C $sourceRoot apply --check $patchPath
git -C $sourceRoot apply $patchPath

Write-Host "Prepared OM0RX WSJT-Z source:"
Write-Host "  $sourceRoot"
Write-Host "Upstream:"
git -C $sourceRoot log -1 --oneline --decorate
