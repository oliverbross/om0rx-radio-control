param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$BaselineRef = "v2.0.14",
    [string]$UpstreamUrl = "https://github.com/sq9fve/wsjt-z.git",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$projectRootResolved = (Resolve-Path -LiteralPath $ProjectRoot).Path
$dataBuildRoot = Join-Path $projectRootResolved "data\build"
$researchRoot = Join-Path $projectRootResolved "data\research\wsjt-z"
$workRoot = Join-Path $dataBuildRoot "wsjt-z-clean"
$sourceRoot = Join-Path $workRoot "src"

New-Item -ItemType Directory -Force -Path $dataBuildRoot | Out-Null
$dataBuildResolved = (Resolve-Path -LiteralPath $dataBuildRoot).Path

function Assert-SafeWorkRoot {
    param([string]$Path)

    $candidate = [IO.Path]::GetFullPath($Path)
    $expected = [IO.Path]::GetFullPath((Join-Path $dataBuildResolved "wsjt-z-clean"))
    if (-not $candidate.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify unexpected work root: $candidate"
    }
}

Assert-SafeWorkRoot -Path $workRoot

if (-not (Test-Path -LiteralPath $researchRoot)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $researchRoot) | Out-Null
    git clone $UpstreamUrl $researchRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to clone the WSJT-Z research source."
    }
}

$baselineCommit = (git -C $researchRoot rev-parse "$BaselineRef^{commit}" 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or -not $baselineCommit) {
    git -C $researchRoot fetch --tags --prune origin
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to fetch WSJT-Z tags."
    }
    $baselineCommit = (git -C $researchRoot rev-parse "$BaselineRef^{commit}").Trim()
}
$baselineTree = (git -C $researchRoot rev-parse "$baselineCommit^{tree}").Trim()

if (Test-Path -LiteralPath $sourceRoot) {
    $currentCommit = (git -C $sourceRoot rev-parse HEAD 2>$null).Trim()
    $dirty = @(git -C $sourceRoot status --porcelain)
    if (-not $Force) {
        if ($currentCommit -ne $baselineCommit) {
            throw "Existing clean workspace is at $currentCommit, expected $baselineCommit. Re-run with -Force."
        }
        if ($dirty.Count -gt 0) {
            throw "Existing clean workspace has local changes. Preserve them or re-run with -Force."
        }
        Write-Host "Clean WSJT-Z source is already prepared: $sourceRoot"
        Write-Host "Commit: $baselineCommit"
        Write-Host "Tree:   $baselineTree"
        exit 0
    }
}

if ($Force -and (Test-Path -LiteralPath $workRoot)) {
    Assert-SafeWorkRoot -Path $workRoot
    Remove-Item -LiteralPath $workRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
git clone --no-hardlinks --no-checkout $researchRoot $sourceRoot
if ($LASTEXITCODE -ne 0) {
    throw "Unable to materialize the clean WSJT-Z source."
}
git -C $sourceRoot config core.autocrlf true
git -C $sourceRoot checkout --detach $baselineCommit
if ($LASTEXITCODE -ne 0) {
    throw "Unable to check out WSJT-Z baseline $baselineCommit."
}

$materializedCommit = (git -C $sourceRoot rev-parse HEAD).Trim()
$materializedTree = (git -C $sourceRoot rev-parse "HEAD^{tree}").Trim()
$materializedDirty = @(git -C $sourceRoot status --porcelain)
if ($materializedCommit -ne $baselineCommit -or $materializedTree -ne $baselineTree -or $materializedDirty.Count -gt 0) {
    throw "Materialized WSJT-Z source failed the identity/cleanliness check."
}

$identity = @(
    "ref=$BaselineRef"
    "commit=$materializedCommit"
    "tree=$materializedTree"
    "source=$UpstreamUrl"
)
Set-Content -LiteralPath (Join-Path $workRoot "BASELINE.txt") -Value $identity -Encoding ASCII

Write-Host "Prepared pristine WSJT-Z source:"
Write-Host "  $sourceRoot"
Write-Host "Ref:    $BaselineRef"
Write-Host "Commit: $materializedCommit"
Write-Host "Tree:   $materializedTree"
