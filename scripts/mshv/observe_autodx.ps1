param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [ValidateRange(1, 1440)]
    [int]$Minutes = 120,

    [ValidateRange(1, 60)]
    [int]$IntervalSeconds = 3,

    [string]$StatusUri = 'http://127.0.0.1:8080/api/digital/status'
)

$ErrorActionPreference = 'Stop'
$startedUtc = [DateTime]::UtcNow
$deadlineUtc = $startedUtc.AddMinutes($Minutes)
$outputDirectory = Split-Path -Parent $OutputPath
if ($outputDirectory) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$metadata = [ordered]@{
    record_type = 'metadata'
    started_utc = $startedUtc.ToString('o')
    deadline_utc = $deadlineUtc.ToString('o')
    minutes = $Minutes
    interval_seconds = $IntervalSeconds
    status_uri = $StatusUri
}
$metadata | ConvertTo-Json -Compress | Set-Content -LiteralPath $OutputPath -Encoding UTF8

$sampleCount = 0
$failureCount = 0
$lastHeartbeatUtc = [DateTime]::MinValue
$lastSignature = ''

while ([DateTime]::UtcNow -lt $deadlineUtc) {
    $sampleStartedUtc = [DateTime]::UtcNow
    try {
        $status = Invoke-RestMethod -Uri $StatusUri -Method Get -TimeoutSec 10
        $engine = $status.autodx_status
        $radio = $status.health.stats.lastStatus
        $decode = $status.health.stats.lastDecode
        $target = $engine.target
        $budget = $engine.budget
        $dwell = $engine.band_dwell
        $schedule = $engine.active_schedule
        $verification = $engine.pending_verification
        $guard = $engine.full_hunting.post_qso_guard

        $record = [ordered]@{
            record_type = 'sample'
            utc = $sampleStartedUtc.ToString('o')
            running = [bool]$status.running
            pid = @($status.running_pids.mshv_auto_dx)
            conflict = [bool]$status.conflict
            engine_fresh = [bool]$status.engine_state_fresh
            identity_fresh = [bool]$status.station_identity_fresh
            enabled = [bool]$status.health.enabled
            packet_age_ms = $status.health.stats.lastPacketAgeMs
            decode_age_ms = $status.health.stats.lastDecodeAgeMs
            logged_count = $status.health.stats.logged
            last_logged = $status.health.stats.lastLogged
            dial_frequency_hz = $radio.dialFrequency
            mode = $radio.mode
            dx_call = $radio.dxCall
            dx_grid = $radio.dxGrid
            tx_enabled = $radio.txEnabled
            transmitting = $radio.transmitting
            decoding = $radio.decoding
            qso_state = $radio.qsoState
            tx_rst = $radio.txRst
            rx_rst = $radio.rxRst
            last_decode_utc_ms = $decode.ts
            last_decode_message = $decode.message
            last_decode_snr = $decode.snr
            last_decode_audio_hz = $decode.deltaFrequency
            autodx_state = $engine.state
            target_call = $target.call
            target_dxcc = $target.dxcc
            target_grid = $target.grid
            target_band_index = $target.band_index
            target_audio_hz = $target.audio_frequency_hz
            target_dial_hz = $target.dial_frequency_hz
            target_new_dxcc = $target.new_dxcc
            target_new_band_slot = $target.new_band_slot
            target_dxpedition = $target.dxpedition
            target_directed_caller = $target.directed_caller
            target_award_references = @($target.award_references)
            selection_id = $engine.selection_id
            selection_reason = $engine.selection_reason
            selection_class = $engine.selection_class
            selection_score = $engine.selection_score
            attempt = $engine.attempt
            budget_elapsed_seconds = $budget.elapsed_seconds
            budget_remaining_seconds = $budget.remaining_seconds
            budget_total_seconds = $budget.total_seconds
            attempt_elapsed_seconds = $budget.attempt_elapsed_seconds
            progress_idle_seconds = $budget.progress_idle_seconds
            atno_persistence_active = $budget.atno_persistence_active
            dxpedition_lease_active = $budget.dxpedition_30_minute_lease_active
            completion_grace_active = $budget.completion_grace_active
            next_retry_call = $engine.next_retry.call
            next_retry_remaining_seconds = $engine.next_retry.remaining_seconds
            band = $schedule.band
            band_index = $schedule.band_index
            band_open = $schedule.open_now
            dwell_elapsed_seconds = $dwell.elapsed_seconds
            dwell_remaining_seconds = $dwell.remaining_seconds
            full_hunting_enabled = $engine.full_hunting.enabled
            full_hunting_mode = $engine.full_hunting.mode
            full_hunting_remaining_seconds = $engine.full_hunting.remaining_seconds
            post_qso_guard_active = $guard.active
            post_qso_guard_call = $guard.call
            post_qso_guard_remaining_seconds = $guard.remaining_seconds
            verification_active = $verification.active
            verification_call = $verification.callsign
            verification_band = $verification.band
            verification_reason = $verification.reason
            verification_source = $verification.source
            cluster_queue = @($engine.cluster_chase.queue)
            skipped_reasons = @($engine.skipped_reasons)
            audit_counter = $engine.audit.event_counter
            audit_event = $engine.audit.last_event
            station_band = $status.station_policy.band
            amplifier = $status.station_policy.kpa500
            active_drive_w = $status.station_policy.active_drive_w
        }

        $record | ConvertTo-Json -Compress -Depth 8 | Add-Content -LiteralPath $OutputPath -Encoding UTF8
        $sampleCount++

        $signatureParts = @($record.band, $record.mode, $record.target_call, $record.qso_state,
            $record.transmitting, $record.audit_counter, $record.logged_count, $record.verification_call)
        $signature = $signatureParts -join '|'
        if ($signature -ne $lastSignature) {
            $eventArguments = @($record.utc, $record.band, $record.mode, $record.target_call,
                $record.qso_state, $record.transmitting, $record.audit_event, $record.logged_count,
                $record.verification_call)
            Write-Output ('EVENT {0} band={1} mode={2} target={3} qso={4} tx={5} audit={6} logged={7} verify={8}' -f $eventArguments)
            $lastSignature = $signature
        }
    }
    catch {
        $failureCount++
        [ordered]@{
            record_type = 'error'
            utc = [DateTime]::UtcNow.ToString('o')
            message = $_.Exception.Message
        } | ConvertTo-Json -Compress | Add-Content -LiteralPath $OutputPath -Encoding UTF8
    }

    $nowUtc = [DateTime]::UtcNow
    if (($nowUtc - $lastHeartbeatUtc).TotalSeconds -ge 30) {
        $remainingMinutes = [Math]::Max(0, ($deadlineUtc - $nowUtc).TotalMinutes)
        Write-Output ('HEARTBEAT utc={0} samples={1} failures={2} remaining_minutes={3:N1}' -f
            $nowUtc.ToString('o'), $sampleCount, $failureCount, $remainingMinutes)
        $lastHeartbeatUtc = $nowUtc
    }

    $sleepMs = [Math]::Max(0, ($IntervalSeconds * 1000) - ([DateTime]::UtcNow - $sampleStartedUtc).TotalMilliseconds)
    if ($sleepMs -gt 0) {
        Start-Sleep -Milliseconds ([int]$sleepMs)
    }
}

[ordered]@{
    record_type = 'complete'
    started_utc = $startedUtc.ToString('o')
    completed_utc = [DateTime]::UtcNow.ToString('o')
    samples = $sampleCount
    failures = $failureCount
} | ConvertTo-Json -Compress | Add-Content -LiteralPath $OutputPath -Encoding UTF8

Write-Output ('COMPLETE samples={0} failures={1} output={2}' -f $sampleCount, $failureCount, $OutputPath)
