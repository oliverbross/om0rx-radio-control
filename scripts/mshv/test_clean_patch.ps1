param([string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path)
$ErrorActionPreference = 'Stop'
$lock = Get-Content (Join-Path $PSScriptRoot 'upstream-lock.json') -Raw | ConvertFrom-Json
$verificationRoot = Join-Path $ProjectRoot ('data\build\mshv-auto-dx\verification\' + [Guid]::NewGuid().ToString('N'))
$source = Join-Path $verificationRoot 'data\build\mshv-auto-dx\src'
New-Item -ItemType Directory -Force -Path (Split-Path $source),(Join-Path $verificationRoot 'docs\mshv') | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-integration.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-phase1.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-wavelog-history-phase2.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-quiet-qsy-fix.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-native-policy.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-persistence.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-layout-persistence.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-performance-decode-dxpedition.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-recent-qso-cooldown.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-permanent-slot-dedupe.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-compact-status-combinations.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-us-states-chase.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-cluster-chase-scheduler.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-us-state-dxcc-guard.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-composable-award-hunting.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-priority-patrol-ft4.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-repeat-final-exchange.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-band-markers-country-exclusions.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-exchange-only-reply-guard.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-qso-lifecycle-ui.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-station-rf-panel.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-target-lock.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-late-reply-qsy-guard.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'docs\mshv\om0rx-adaptive-retry-ignore.patch') -Destination (Join-Path $verificationRoot 'docs\mshv')
git clone --no-checkout $lock.repository $source
if ($LASTEXITCODE -ne 0) { throw 'Clean patch clone failed' }
git -C $source checkout --detach $lock.commit
if ($LASTEXITCODE -ne 0) { throw 'Clean patch checkout failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-integration.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-phase1.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean AutoDX Phase 1 patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-wavelog-history-phase2.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean Wavelog history Phase 2 patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-quiet-qsy-fix.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean AutoDX quiet-band QSY fix patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-autodx-native-policy.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean native AutoDX policy patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-persistence.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean native UI persistence patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-ui-layout-persistence.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean native UI layout persistence patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-performance-decode-dxpedition.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean performance/decode/DXpedition patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-recent-qso-cooldown.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean recent-QSO cooldown patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-permanent-slot-dedupe.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean permanent slot-dedupe patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-compact-status-combinations.patch')
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-us-states-chase.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean compact status-combinations patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-cluster-chase-scheduler.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean cluster chase scheduler patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-us-state-dxcc-guard.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean US-state DXCC guard patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-composable-award-hunting.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean composable award-hunting patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-priority-patrol-ft4.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean priority-patrol/FT4 patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-repeat-final-exchange.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean final-exchange repeat patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-band-markers-country-exclusions.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean band-marker/country-exclusion patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-exchange-only-reply-guard.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean exchange-only reply guard patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-qso-lifecycle-ui.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean manual-QSO lifecycle UI patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-station-rf-panel.patch')
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-manual-target-lock.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean station RF panel patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-late-reply-qsy-guard.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean late-reply QSY guard patch application failed' }
git -C $source apply (Join-Path $ProjectRoot 'docs\mshv\om0rx-adaptive-retry-ignore.patch')
if ($LASTEXITCODE -ne 0) { throw 'Clean adaptive-retry/ignore patch application failed' }
& (Join-Path $PSScriptRoot 'assert_source.ps1') -ProjectRoot $verificationRoot
$network = Get-Content (Join-Path $source 'MSHV_2762\src\HvTxW\HvRadioNetW\radionetw.cpp') -Raw
if (-not $network.Contains('new MessageClient {"MSHV-OM0RX-AUTO-DX",VER_MS,"127.0.0.1",2237')) { throw 'Clean patch lost protocol identity/loopback integration' }
$gate = Get-Content (Join-Path $source 'MSHV_2762\src\om0rxstationgate.h') -Raw
foreach ($contract in @(
    'body["phase"] = phase',
    'body["prepare_nonce"] = nonce',
    'result.value("phase").toString() == phase',
    'result.value("transmit_ready")',
    'result.value("permit_nonce")',
    'requestTimeoutMs() { return 75000; }',
    'consumeTimeoutMs() { return 1500; }',
    'station-permit/consume',
    'consumePermitBlocking'
)) {
    if (-not $gate.Contains($contract)) { throw "Clean patch lost two-phase station contract: $contract" }
}
$scorer = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\targetscorer.cpp') -Raw
foreach ($contract in @('m_weightCallingMe','AutoDxMessageParser::parse','parsedMessage.destination','m_weightSNRPerDb','awardDimensionScores','m_awardConfig.stackScores')) {
    if (-not $scorer.Contains($contract)) { throw "Clean patch lost configurable target-priority contract: $contract" }
}
$awardPolicy = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\awardhuntingpolicy.h') -Raw
foreach ($contract in @('applyCampaignProfile','std::sort(rows.begin()','OutcomeLearningIndex','m_scores.size() >= 5000','void prune')) {
    if (-not $awardPolicy.Contains($contract)) { throw "Clean patch lost composable award policy: $contract" }
}
$awardAdifPolicy = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\awardadifpolicy.h') -Raw
foreach ($contract in @('struct AwardReferenceMatch','match.program + "_REF"','SIG_INFO','fromProgramColumns')) {
    if (-not $awardAdifPolicy.Contains($contract)) { throw "Clean patch lost structured award ADIF policy: $contract" }
}
$logWindow = Get-Content (Join-Path $source 'MSHV_2762\src\HvTxW\HvLogW\hvlogw.cpp') -Raw
foreach ($contract in @('SetAutoDxAwardReferences','AwardAdifPolicy::adifFields','model.item(j, 25)','model.item(j, 27)')) {
    if (-not $logWindow.Contains($contract)) { throw "Clean patch lost award references at MSHV log boundary: $contract" }
}
$messageParser = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\autodxmessageparser.h') -Raw
foreach ($contract in @('parts.first() == "CQ"','parsed.destination = resolvedCall(parts.at(0))','parsed.transmitter = resolvedCall(parts.at(1))','if (!parsed.senderResolved) parsed.transmitter.clear()')) {
    if (-not $messageParser.Contains($contract)) { throw "Clean patch lost fail-closed FT8 sender contract: $contract" }
}
$eligibility = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\targeteligibility.h') -Raw
foreach ($contract in @('newDxcc || newBandSlot || newGrid || callingMe','newGrid ? gridWeight','callingMe ? callingWeight')) {
    if (-not $eligibility.Contains($contract)) { throw "Clean patch lost independent eligibility contract: $contract" }
}
$panel = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\autodxerpanel.cpp') -Raw
$core = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\autodxercore.cpp') -Raw
$runtimeConfig = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\autodxruntimeconfig.h') -Raw
foreach ($contract in @('AutoDxRuntimeConfig::load(settingsPath)','runtimeConfigStatus','if (!m_bandSwitchingEnabled && !m_fullHuntingEnabled')) {
    if (-not $core.Contains($contract)) { throw "Clean patch lost active AutoDX core contract: $contract" }
}
foreach ($contract in @('static const int delays[] = { 180, 600, 1800, 3600 }',
                         'database/autodx_ignore.json',
                         'new_dxcc_30_minute_lease_active',
                         'isStationIgnored')) {
    if (-not $core.Contains($contract)) { throw "Clean patch lost adaptive-retry/ignore contract: $contract" }
}
if (-not $panel.Contains('m_tabWidget->addTab(ignoreTab, "Ignore")')) {
    throw 'Clean patch lost Ignore tab'
}
foreach ($contract in @('ordinaryNewCallFallbackAllowed',
                         'new-call-fallback-deferred',
                         'eligible-priority-opportunity-pending',
                         'priority_cycle_complete')) {
    if (-not $core.Contains($contract)) { throw "Clean patch lost priority-patrol contract: $contract" }
}
foreach ($contract in @('auditEvent("award-index-hot-reloaded"',
                         'sourceConfigurationChanged && wasEffective',
                         'if (!localRowFound) continue',
                         'pruneAttemptHistory(attemptUtc)')) {
    if (-not $core.Contains($contract)) { throw "Clean patch lost safe composable runtime behavior: $contract" }
}
foreach ($contract in @(
    'evaluateTargets();',
    'void AutoDxerCore::beginBandChange',
    'void AutoDxerCore::onBandChangeFailed',
    'if (!m_quietBandTimer.isValid()) m_quietBandTimer.start();'
)) {
    if (-not $core.Contains($contract)) { throw "Clean patch lost quiet-band retry contract: $contract" }
}
foreach ($contract in @('BandSwitching/Enabled','AutoDx/Modes','SpotSources/RbnEnabled','effectiveEnabled')) {
    if (-not $runtimeConfig.Contains($contract)) { throw "Clean patch lost active AutoDX runtime configuration: $contract" }
}
foreach ($contract in @('TargetPriority/NewDxcc','TargetPriority/NewBandSlot','TargetPriority/NewGrid','TargetPriority/CallingMe','TargetPriority/Cq','TargetPriority/SnrPerDb')) {
    if (-not $runtimeConfig.Contains($contract)) { throw "Clean patch lost authoritative target-priority settings binding: $contract" }
    if ($panel.Contains($contract)) { throw "Panel reintroduced duplicate target-priority settings binding: $contract" }
}
foreach ($contract in @('QSignalBlocker','m_core->desiredEnabled()','bandManager()->getEnabledBands()','targetScorer()->minSNR()')) {
    if (-not $panel.Contains($contract)) { throw "Clean patch lost authoritative panel rendering: $contract" }
}
$aggregator = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\spotaggregator.cpp') -Raw
if ($aggregator.Split('if (!m_cleanupTimer->isActive()) return;').Count -lt 4 -or
    $aggregator -notmatch 'm_pskrEnabled\s*&&\s*m_cleanupTimer->isActive') {
    throw 'Clean patch lost pre-start network-source inhibition'
}
$main = Get-Content (Join-Path $source 'MSHV_2762\src\main_ms.cpp') -Raw
$autoDxCore = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\autodxercore.cpp') -Raw
$targetScorer = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\targetscorer.cpp') -Raw
foreach ($contract in @(
    'considerCallingMePreemption(localDecode);',
    'm_suspendedTargetElapsedMs = currentTargetAttemptElapsedMs();',
    'm_targetAttemptElapsedOffsetMs = elapsedMs;',
    'CALLING-ME-PREEMPT:',
    'CALLING-ME-RESUME:',
    'persistentAndFresh'
)) {
    if (-not $autoDxCore.Contains($contract)) {
        throw "Clean patch lost full-duration/calling-me state-machine contract: $contract"
    }
}
$decodeComplete = ($autoDxCore -split [regex]::Escape('void AutoDxerCore::onDecodeComplete'), 2)[1]
$decodeComplete = ($decodeComplete -split [regex]::Escape('void AutoDxerCore::processListeningState'), 2)[0]
if ($decodeComplete.Contains('not heard locally for')) {
    throw 'Clean patch lets post-selection freshness truncate an accepted target'
}
foreach ($contract in @(
    'isPendingWavelogCall(decode.callsign)',
    'if (!facts.bandCall)',
    'Call already worked on this band/mode',
    '!target.isCallingMe && decode.snr < m_selectionConfig.minSignal'
)) {
    if (-not $targetScorer.Contains($contract)) {
        throw "Clean patch lost permanent slot eligibility contract: $contract"
    }
}
$selectionPolicy = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\autodxselectionpolicy.h') -Raw
foreach ($contract in @('allowBandDxccOutsideContinent', 'continent-filter-override', 'bandDxccContinentOverride')) {
    if (-not $selectionPolicy.Contains($contract)) {
        throw "Clean patch lost all-band DXCC continent-override contract: $contract"
    }
}
foreach ($contract in @('state["desired_enabled"]','state["autodx_config"]','setCurrentMode(ModeStr(s_mod_ident))')) {
    if (-not $main.Contains($contract)) { throw "Clean patch lost AutoDX effective-state telemetry: $contract" }
}
foreach ($contract in @(
    'm_autoDxerBandChangePending',
    'activeBandChangeRequestId',
    'onBandChangeFailedForRequest(',
    'ListBands.at(bandIndex)->setChecked(true);',
    'StopTxGlobalWithReason("stop-tx-global")',
    'StopTxGlobalWithReason("udp-stop")',
    'StopTxGlobalWithReason("escape-stop")',
    'StopTxGlobalWithReason("process-teardown")',
    'requestAuthorizationInvalidation'
)) {
    if (-not $main.Contains($contract)) { throw "Clean patch lost native band-change handshake: $contract" }
}
$nativeBandQsy = ($main -split [regex]::Escape('void Main_Ms::SetBandFromAutoDxer(int bandIndex)'), 2)[1]
$nativeBandQsy = ($nativeBandQsy -split [regex]::Escape('void Main_Ms::SetDialFreqFromAutoDxer(int dialFreqHz)'), 2)[0]
foreach ($forbidden in @('gate->prepare', 'finalGate->confirm')) {
    if ($nativeBandQsy.Contains($forbidden)) {
        throw "Clean patch reintroduced synchronous station veto in native band QSY: $forbidden"
    }
}
if (-not $nativeBandQsy.Contains('onBandChangeCompleteForRequest')) {
    throw 'Clean patch lost CAT-confirmed native band-QSY completion'
}
$nativeDialQsy = ($main -split [regex]::Escape('void Main_Ms::SetDialFreqFromAutoDxer(int dialFreqHz)'), 2)[1]
$nativeDialQsy = ($nativeDialQsy -split [regex]::Escape('void Main_Ms::SetModeGlobalFromRigCat(QString mode)'), 2)[0]
foreach ($forbidden in @('gate->prepare', 'finalGate->confirm', '/api/digital/station-ready')) {
    if ($nativeDialQsy.Contains($forbidden)) {
        throw "Clean patch reintroduced synchronous station veto in native dial QSY: $forbidden"
    }
}
if (-not $nativeDialQsy.Contains('THvRigControl, "SetFreq"')) {
    throw 'Clean patch lost direct native dial-QSY CAT command'
}
if ([regex]::Matches(
        $main,
        [regex]::Escape('invalidateAndNotify(this, "autodx-band-qsy")')
    ).Count -ne 1) {
    throw 'Clean patch must retain exactly one explicit native band-QSY authorization invalidation'
}
$nativePtt = ($main -split [regex]::Escape('void Main_Ms::SetRigTxRx(bool f)'), 2)[1]
$nativePtt = ($nativePtt -split [regex]::Escape('QDateTime Main_Ms::getDateTime()'), 2)[0]
if (-not $nativePtt.Contains('THvRigControl->SetPtt(f,0)')) {
    throw 'Clean patch lost direct native Main_Ms PTT edge'
}
foreach ($forbidden in @('hasPermit', 'consumePermitBlocking', 'prefetch', 'auditRejected')) {
    if ($nativePtt.Contains($forbidden)) {
        throw "Clean patch reintroduced station permit gating in Main_Ms PTT path: $forbidden"
    }
}
$rigControl = Get-Content (Join-Path $source 'MSHV_2762\src\HvRigControl\hvrigcontrol.cpp') -Raw
$lowestPtt = ($rigControl -split [regex]::Escape('void HvRigControl::SetPtt_p(bool flag,int id)'), 2)[1]
$lowestPtt = ($lowestPtt -split [regex]::Escape('void HvRigControl::SetQSOProgress(int i)'), 2)[0]
if (-not $lowestPtt.Contains('THvRigCat->set_ptt(flag,false)')) {
    throw 'Clean patch lost direct native rig PTT output'
}
foreach ($forbidden in @('hasPermit', 'consumePermitBlocking', 'prefetch', 'notePttRequest')) {
    if ($lowestPtt.Contains($forbidden)) {
        throw "Clean patch reintroduced station permit gating in lowest native PTT edge: $forbidden"
    }
}
$txWindow = Get-Content (Join-Path $source 'MSHV_2762\src\HvTxW\hvtxw.cpp') -Raw
$stopAuto = ($txWindow -split [regex]::Escape('void HvTxW::StopAuto()'), 2)[1]
$stopAuto = ($stopAuto -split [regex]::Escape('void HvTxW::auto_on()'), 2)[0]
if (-not $stopAuto.Contains('noteInternalAutoStopped') -or $stopAuto.Contains('invalidate')) {
    throw 'Clean patch must keep ordinary/empty-queue StopAuto generation-neutral'
}
if (-not $stopAuto.Contains('emit EmitAutoModeChanged(false)')) {
    throw 'Clean patch lost the generation-neutral AUTO-off feedback edge'
}
$autoDxerCore = Get-Content (Join-Path $source 'MSHV_2762\src\HvAutoDxer\autodxercore.cpp') -Raw
foreach ($contract in @('AUTO_OFF_RECONCILE_MS', 'AUTO-OFF-PENDING',
                         'AUTO-OFF-TERMINAL', 'reconcileSustainedAutoOff')) {
    if (-not $autoDxerCore.Contains($contract)) {
        throw "Clean patch lost sustained AUTO-off ownership reconciliation: $contract"
    }
}
$autoOn = ($txWindow -split [regex]::Escape('void HvTxW::auto_on()'), 2)[1]
$autoOn = ($autoOn -split [regex]::Escape('void HvTxW::StartAuto()'), 2)[0]
$startAuto = ($txWindow -split [regex]::Escape('void HvTxW::StartAuto()'), 2)[1]
$startAuto = ($startAuto -split [regex]::Escape('void HvTxW::SetAutoModeFromConfig(bool enabled)'), 2)[0]
foreach ($entry in @(@('auto_on', $autoOn), @('StartAuto', $startAuto))) {
    if ($entry[1].Contains('prefetch')) {
        throw "Clean patch reintroduced station-ready prefetch in native $($entry[0]) path"
    }
}
if ($main.Contains('Om0rxStationGate::prefetch(this);')) {
    throw 'Clean patch reintroduced station-ready prefetch in Main_Ms heartbeat/start path'
}
$txEdge = ($txWindow -split [regex]::Escape('void HvTxW::SetTxRxCountAutoSeq(bool f)'), 2)[1]
$txEdge = ($txEdge -split [regex]::Escape('void HvTxW::CountTx73_p(bool f)'), 2)[0]
foreach ($contract in @('if (f && f_no_time_count_txwatchdog != 0', 'QTimer::singleShot', 'shouldTrip(', 'emit EmitTxWatchdogStop()')) {
    if (-not $txEdge.Contains($contract)) { throw "Clean patch lost continuous-TX watchdog contract: $contract" }
}
foreach ($forbidden in @('invalidateAndNotify', 'StopAuto()')) {
    if ($txEdge.Contains($forbidden)) {
        throw "Clean patch lets a normal TX release stop/invalidate AutoDX: $forbidden"
    }
}
if (-not $main.Contains('StopTxGlobalWithReason("tx-watchdog-stop")')) {
    throw 'Clean patch lost explicit emergency stop for a genuinely stuck TX edge'
}
Write-Host "Clean pinned-source patch replay and exact diff attestation passed: $source"
