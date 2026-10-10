param([string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path)
$ErrorActionPreference = 'Stop'
$lock = Get-Content (Join-Path $PSScriptRoot 'upstream-lock.json') -Raw | ConvertFrom-Json
$work = Join-Path $ProjectRoot 'data\build\mshv-auto-dx'
$source = Join-Path $work 'src'
$patches = @(
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-integration.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-phase1.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-wavelog-history-phase2.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-quiet-qsy-fix.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-native-policy.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-persistence.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-layout-persistence.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-performance-decode-dxpedition.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-recent-qso-cooldown.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-permanent-slot-dedupe.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-compact-status-combinations.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-us-states-chase.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-cluster-chase-scheduler.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-us-state-dxcc-guard.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-composable-award-hunting.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-priority-patrol-ft4.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-repeat-final-exchange.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-band-markers-country-exclusions.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-exchange-only-reply-guard.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-qso-lifecycle-ui.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-station-rf-panel.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-target-lock.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-late-reply-qsy-guard.patch'),
    (Join-Path $ProjectRoot 'docs\mshv\om0rx-adaptive-retry-ignore.patch')
)
New-Item -ItemType Directory -Force -Path $work | Out-Null
if (-not (Test-Path (Join-Path $source '.git'))) {
    git clone $lock.repository $source
    if ($LASTEXITCODE -ne 0) { throw 'MSHV source clone failed' }
    git -C $source checkout --detach $lock.commit
    if ($LASTEXITCODE -ne 0) { throw 'Pinned MSHV checkout failed' }
}
$actual = (git -C $source rev-parse HEAD).Trim()
if ($actual -ne $lock.commit) { throw "Source identity mismatch: $actual" }
try {
    & (Join-Path $PSScriptRoot 'assert_source.ps1') -ProjectRoot $ProjectRoot
    Write-Host 'OM0RX maintained patch stack is already applied'
    exit 0
} catch { }
$dirty = @(git -C $source status --porcelain --untracked-files=no)
if ($dirty.Count) { throw 'MSHV source has other tracked changes; preserve them before preparing' }
foreach ($patch in $patches) {
    git -C $source apply --check $patch
    if ($LASTEXITCODE -ne 0) { throw "OM0RX patch does not match preceding pinned source state: $patch" }
    git -C $source apply $patch
    if ($LASTEXITCODE -ne 0) { throw "OM0RX patch application failed: $patch" }
}
& (Join-Path $PSScriptRoot 'assert_source.ps1') -ProjectRoot $ProjectRoot
Write-Host "Prepared MSHV $actual with the maintained OM0RX patch stack at $source"
