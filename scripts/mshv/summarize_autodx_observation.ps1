param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$records = Get-Content -LiteralPath $InputPath | ForEach-Object { $_ | ConvertFrom-Json }
$samples = @($records | Where-Object record_type -eq 'sample' | Sort-Object { [DateTime]$_.utc })
if ($samples.Count -eq 0) {
    throw "No observation samples found in $InputPath"
}

function Complete-Run {
    param(
        [System.Collections.ArrayList]$Destination,
        [pscustomobject]$Run,
        [pscustomobject]$Last
    )
    if ($null -eq $Run -or $null -eq $Last) { return }
    $Run.end_utc = $Last.utc
    $Run.duration_seconds = [Math]::Round((([DateTime]$Last.utc) - ([DateTime]$Run.start_utc)).TotalSeconds)
    [void]$Destination.Add($Run)
}

$attempts = [System.Collections.ArrayList]::new()
$bandVisits = [System.Collections.ArrayList]::new()
$verificationVisits = [System.Collections.ArrayList]::new()
$guardViolations = [System.Collections.ArrayList]::new()
$currentAttempt = $null
$currentBandVisit = $null
$currentVerification = $null
$previous = $null

foreach ($sample in $samples) {
    if ($null -eq $currentBandVisit -or $sample.band -ne $currentBandVisit.band) {
        Complete-Run -Destination $bandVisits -Run $currentBandVisit -Last $previous
        if ($null -ne $previous -and $previous.post_qso_guard_active) {
            [void]$guardViolations.Add([pscustomobject]@{
                utc = $sample.utc
                from_band = $previous.band
                to_band = $sample.band
                guard_call = $previous.post_qso_guard_call
                guard_remaining_seconds = $previous.post_qso_guard_remaining_seconds
            })
        }
        $currentBandVisit = [pscustomobject]@{
            band = $sample.band
            mode = $sample.mode
            start_utc = $sample.utc
            end_utc = $null
            duration_seconds = 0
            verification = [bool]$sample.verification_active
            verification_call = $sample.verification_call
        }
    }

    $attemptChanged = $null -ne $currentAttempt -and $sample.target_call -ne $currentAttempt.call
    if ($attemptChanged) {
        Complete-Run -Destination $attempts -Run $currentAttempt -Last $previous
        $currentAttempt = $null
    }
    if ($sample.target_call -and $null -eq $currentAttempt) {
        $currentAttempt = [pscustomobject]@{
            call = $sample.target_call
            dxcc = $sample.target_dxcc
            band = $sample.band
            mode = $sample.mode
            start_utc = $sample.utc
            end_utc = $null
            duration_seconds = 0
            selection_class = $sample.selection_class
            selection_reason = $sample.selection_reason
            selection_score = $sample.selection_score
            new_dxcc = [bool]$sample.target_new_dxcc
            new_band_slot = [bool]$sample.target_new_band_slot
            dxpedition = [bool]$sample.target_dxpedition
            directed_caller = [bool]$sample.target_directed_caller
            engaged = $false
            progress = $false
            logged = $false
            start_logged_count = [int]$sample.logged_count
            end_logged_count = [int]$sample.logged_count
            max_budget_total_seconds = [int]$sample.budget_total_seconds
        }
    }
    if ($null -ne $currentAttempt) {
        $currentAttempt.engaged = $currentAttempt.engaged -or $sample.qso_state -eq 'in_qso' -or $sample.audit_event -eq 'target-engaged'
        $currentAttempt.progress = $currentAttempt.progress -or $sample.audit_event -eq 'target-progress'
        $currentAttempt.end_logged_count = [Math]::Max($currentAttempt.end_logged_count, [int]$sample.logged_count)
        $currentAttempt.logged = $currentAttempt.end_logged_count -gt $currentAttempt.start_logged_count
        $currentAttempt.max_budget_total_seconds = [Math]::Max($currentAttempt.max_budget_total_seconds, [int]$sample.budget_total_seconds)
    }

    if ($sample.verification_active -and $null -eq $currentVerification) {
        $currentVerification = [pscustomobject]@{
            call = $sample.verification_call
            band = $sample.verification_band
            source = $sample.verification_source
            reason = $sample.verification_reason
            start_utc = $sample.utc
            end_utc = $null
            duration_seconds = 0
            target_selected = $false
        }
    }
    if ($null -ne $currentVerification) {
        $currentVerification.target_selected = $currentVerification.target_selected -or $sample.target_call -eq $currentVerification.call
        if (-not $sample.verification_active) {
            Complete-Run -Destination $verificationVisits -Run $currentVerification -Last $previous
            $currentVerification = $null
        }
    }
    $previous = $sample
}

Complete-Run -Destination $attempts -Run $currentAttempt -Last $previous
Complete-Run -Destination $bandVisits -Run $currentBandVisit -Last $previous
Complete-Run -Destination $verificationVisits -Run $currentVerification -Last $previous

$repeatIntervals = [System.Collections.ArrayList]::new()
foreach ($callGroup in ($attempts | Group-Object call)) {
    $ordered = @($callGroup.Group | Sort-Object { [DateTime]$_.start_utc })
    for ($index = 1; $index -lt $ordered.Count; $index++) {
        [void]$repeatIntervals.Add([pscustomobject]@{
            call = $callGroup.Name
            previous_start_utc = $ordered[$index - 1].start_utc
            next_start_utc = $ordered[$index].start_utc
            interval_seconds = [Math]::Round((([DateTime]$ordered[$index].start_utc) - ([DateTime]$ordered[$index - 1].start_utc)).TotalSeconds)
            band = $ordered[$index].band
        })
    }
}

$durationSeconds = [Math]::Round((([DateTime]$samples[-1].utc) - ([DateTime]$samples[0].utc)).TotalSeconds)
$summary = [ordered]@{
    input = (Resolve-Path $InputPath).Path
    started_utc = $samples[0].utc
    ended_utc = $samples[-1].utc
    duration_seconds = $durationSeconds
    samples = $samples.Count
    error_records = @($records | Where-Object record_type -eq 'error').Count
    process_conflict_samples = @($samples | Where-Object conflict).Count
    stale_engine_samples = @($samples | Where-Object { -not $_.engine_fresh }).Count
    modes_observed = @($samples.mode | Where-Object { $_ } | Select-Object -Unique)
    full_hunting_observed = @($samples.full_hunting_enabled | Select-Object -Unique)
    logged_qso_delta = ([int]$samples[-1].logged_count - [int]$samples[0].logged_count)
    attempts_total = $attempts.Count
    attempts_logged = @($attempts | Where-Object logged).Count
    attempts_engaged = @($attempts | Where-Object engaged).Count
    dxpedition_attempts = @($attempts | Where-Object dxpedition).Count
    band_visits = @($bandVisits)
    attempts = @($attempts)
    verification_visits = @($verificationVisits)
    post_qso_guard_qsy_violations = @($guardViolations)
    repeat_intervals = @($repeatIntervals)
}

if (-not $OutputPath) {
    $OutputPath = [IO.Path]::ChangeExtension($InputPath, '.summary.json')
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8

[pscustomobject]@{
    DurationMinutes = [Math]::Round($durationSeconds / 60, 1)
    Samples = $samples.Count
    Errors = $summary.error_records
    Modes = $summary.modes_observed -join ','
    FullHunting = $summary.full_hunting_observed -join ','
    Attempts = $summary.attempts_total
    Engaged = $summary.attempts_engaged
    Logged = $summary.attempts_logged
    LoggedDelta = $summary.logged_qso_delta
    DxpeditionAttempts = $summary.dxpedition_attempts
    VerificationVisits = $verificationVisits.Count
    GuardQsyViolations = $guardViolations.Count
    Output = $OutputPath
} | Format-List
