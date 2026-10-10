param([Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference = 'Stop'
$source = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src'
$lock = Get-Content (Join-Path $PSScriptRoot 'upstream-lock.json') -Raw | ConvertFrom-Json
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
if ((git -C $source rev-parse HEAD).Trim() -ne $lock.commit) { throw 'MSHV source commit mismatch' }
foreach ($patch in $patches) { if (-not (Test-Path $patch)) { throw "Maintained patch missing: $patch" } }

# Generate the expected aggregate diff from a clean local worktree. Comparing
# Git's own binary diff output catches extra hunks even when they share a file
# with one of the maintained patches.
$verificationRoot = Join-Path $ProjectRoot ('data\build\mshv-auto-dx\verification\assert-' + [Guid]::NewGuid().ToString('N'))
$expected = Join-Path $verificationRoot 'expected.patch'
$actual = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\source-attestation.patch'
New-Item -ItemType Directory -Force -Path (Split-Path $verificationRoot) | Out-Null
try {
    git -C $source worktree add --detach $verificationRoot $lock.commit | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create clean source attestation worktree' }
    foreach ($patch in $patches) {
        git -C $verificationRoot apply $patch
        if ($LASTEXITCODE -ne 0) { throw "Maintained patch does not cleanly replay: $patch" }
    }
    foreach ($tree in @($verificationRoot,$source)) {
        git -C $tree add -N MSHV_2762/src/om0rxstationgate.h MSHV_2762/src/om0rxtxwatchdogedge.h MSHV_2762/src/HvTxW/om0rxstationpanel.h MSHV_2762/src/HvAutoDxer/targeteligibility.h MSHV_2762/src/HvAutoDxer/autodxruntimeconfig.h MSHV_2762/src/HvAutoDxer/autodxstatusownership.h MSHV_2762/src/HvAutoDxer/autodxstatusprovenance.h MSHV_2762/src/HvAutoDxer/autodxselectionpolicy.h MSHV_2762/src/HvAutoDxer/autodxmessageparser.h MSHV_2762/src/HvAutoDxer/autodxhistoryconditional.h MSHV_2762/src/HvAutoDxer/awardhuntingpolicy.h MSHV_2762/src/HvAutoDxer/awardadifpolicy.h
        if ($LASTEXITCODE -ne 0) { throw 'Unable to attest patch-added source' }
    }
    git -C $verificationRoot diff HEAD --binary "--output=$expected"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to generate expected MSHV source diff' }
    git -C $source diff HEAD --binary "--output=$actual"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to attest MSHV source' }
    if ((Get-FileHash $expected -Algorithm SHA256).Hash -ne (Get-FileHash $actual -Algorithm SHA256).Hash) {
        throw 'MSHV source differs from the maintained patch stack; refusing build/package'
    }
} finally {
    git -C $source worktree remove --force $verificationRoot 2>$null
}
$untracked = @(git -C $source ls-files --others --exclude-standard -- MSHV_2762/src)
if ($untracked.Count) { throw 'Unrecorded source files present; refusing build/package' }
