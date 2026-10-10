// End-to-end station RF path with a guarded KPA500 operate/standby control.
(function () {
    'use strict';

    const RECONCILE_MS = 30000;
    const FRESH_MS = 15000;
    const STREAM_ENDPOINT = '/api/station/stream';
    const ACTIONS = new Set(['prepare-route', 'standby', 'operate']);
    const CLEAR_FAULTS = new Set(['', '0', '00', '000', 'NONE', 'NO FAULT']);
    const DEFAULT_ANTENNA_NAMES = Object.freeze({
        1: 'KAT ANT1',
        2: 'KAT ANT2',
        3: 'KAT ANT3',
    });
    const STATE_LABELS = Object.freeze({
        ready: 'Confirmed',
        warning: 'Attention',
        unknown: 'Unknown',
        disconnected: 'Disconnected',
    });
    const BACKEND_STATE_MAP = Object.freeze({
        ready: 'ready',
        operate: 'ready',
        auto: 'ready',
        manual: 'ready',
        selected: 'ready',
        disconnected: 'disconnected',
        unknown: 'unknown',
        stale: 'unknown',
        disabled: 'unknown',
        standby: 'ready',
        off: 'warning',
        fault: 'warning',
        mismatch: 'warning',
        transmitting: 'warning',
        tuning: 'warning',
        bypass: 'warning',
    });

    let timer = null;
    let stream = null;
    let radioStream = null;
    let radioReconnectTimer = null;
    let stopped = false;
    let requestInFlight = false;
    let actionInFlight = null;
    let latestStatus = null;
    let latestCoordinatorState = null;
    let latestRadioStatus = {};
    let latestStatusError = null;
    let latestActionError = null;

    function isPresent(value) {
        return value !== undefined && value !== null && value !== '';
    }

    function numberOrNull(value) {
        if (!isPresent(value)) return null;
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function bandFromFrequency(value) {
        const mhz = numberOrNull(value);
        if (mhz === null) return null;
        const ranges = [
            [1.8, 2.0, '160m'], [3.5, 4.0, '80m'], [5.0, 5.6, '60m'],
            [7.0, 7.3, '40m'], [10.0, 10.2, '30m'], [14.0, 14.35, '20m'],
            [18.0, 18.2, '17m'], [21.0, 21.45, '15m'], [24.8, 25.0, '12m'],
            [28.0, 30.0, '10m'], [50.0, 54.0, '6m'],
        ];
        const match = ranges.find(([low, high]) => mhz >= low && mhz <= high);
        return match ? match[2] : null;
    }

    function isFresh(status, now = Date.now()) {
        const updatedAt = numberOrNull(status?.updated_at);
        return updatedAt !== null && now - (updatedAt * 1000) <= FRESH_MS;
    }

    function hasFault(value) {
        if (!isPresent(value)) return false;
        return !CLEAR_FAULTS.has(String(value).trim().toUpperCase());
    }

    function formatValue(value, suffix = '', digits = null) {
        const numeric = numberOrNull(value);
        if (numeric === null) return '—';
        const text = digits === null ? String(numeric) : numeric.toFixed(digits);
        return `${text}${suffix}`;
    }

    function formatFrequency(value) {
        const mhz = numberOrNull(value);
        if (mhz === null) return 'Frequency unknown';
        const hz = Math.max(0, Math.round(mhz * 1000000));
        return `${String(hz).replace(/\B(?=(\d{3})+(?!\d))/g, '.')} MHz`;
    }

    function formatTxPower(value) {
        const watts = numberOrNull(value);
        return watts === null ? 'TX — W' : `TX ${Math.max(0, Math.round(watts))} W`;
    }

    function expectedFlexAntenna(config, band) {
        const policy = config?.FLEX_ANTENNA_POLICY;
        if (!band || policy?.enabled === false) return null;
        const entry = policy?.bands?.[band];
        if (typeof entry === 'object') return entry.tx || entry.txAnt || entry.antenna || null;
        return entry || null;
    }

    function expectedKatAntenna(config, band) {
        const value = config?.KAT500_ANTENNA_POLICY?.[band];
        const antenna = Number(value);
        return [1, 2, 3].includes(antenna) ? antenna : null;
    }

    function antennaName(config, antenna) {
        const configured = config?.KAT500_ANTENNA_NAMES?.[antenna] || config?.KAT500_ANTENNA_NAMES?.[String(antenna)];
        return configured || DEFAULT_ANTENNA_NAMES[antenna] || 'Unknown antenna';
    }

    function classifyFlex({ connected, frequency, mode, txAntenna, expectedAntenna, interlock, transmitting }) {
        if (!connected) return { state: 'disconnected', reason: 'FLEX control link is disconnected' };
        if (!isPresent(frequency) || !isPresent(mode)) return { state: 'unknown', reason: 'FLEX frequency or mode readback is unavailable' };
        if (!isPresent(txAntenna)) {
            return { state: 'unknown', reason: expectedAntenna ? `FLEX ${expectedAntenna} is configured but not confirmed` : 'FLEX TX antenna is not confirmed' };
        }
        if (!isPresent(interlock)) return { state: 'unknown', reason: 'FLEX interlock readback is unavailable' };
        if (expectedAntenna && String(txAntenna).toUpperCase() !== String(expectedAntenna).toUpperCase()) {
            return { state: 'warning', reason: `FLEX TX path is ${txAntenna}; policy expects ${expectedAntenna}` };
        }
        if (transmitting) return { state: 'warning', reason: 'FLEX is transmitting' };
        if (isPresent(interlock) && !['READY', 'RECEIVE'].includes(String(interlock).toUpperCase())) {
            return { state: 'warning', reason: `FLEX interlock is ${interlock}` };
        }
        return { state: 'ready', reason: 'FLEX path confirmed' };
    }

    function classifyKpa(device, fresh, radioBand) {
        if (!device?.enabled) return { state: 'unknown', reason: 'KPA500 is not enabled' };
        if (device.connected === false) return { state: 'disconnected', reason: 'KPA500 is disconnected' };
        if (!fresh || device.connected !== true) return { state: 'unknown', reason: 'KPA500 readback is unavailable or stale' };
        if (device.error) return { state: 'warning', reason: `KPA500: ${device.error}` };
        if (![device.power, device.operate, device.band, device.fault].every(isPresent)) {
            return { state: 'unknown', reason: 'KPA500 critical readback is incomplete' };
        }
        if (hasFault(device.fault)) return { state: 'warning', reason: `KPA500 fault ${device.fault}` };
        if (radioBand && device.band && String(device.band).toLowerCase() !== String(radioBand).toLowerCase()) {
            return { state: 'warning', reason: `KPA500 is on ${device.band}; FLEX is on ${radioBand}` };
        }
        if (device.power !== true) return { state: 'warning', reason: 'KPA500 power is off' };
        if (device.operate !== true) return { state: 'ready', reason: 'KPA500 is safely in standby' };
        return { state: 'ready', reason: 'KPA500 ready' };
    }

    function classifyKat(device, fresh, radioBand, expectedAntenna) {
        if (!device?.enabled) return { state: 'unknown', reason: 'KAT500 is not enabled' };
        if (device.connected === false) return { state: 'disconnected', reason: 'KAT500 is disconnected' };
        if (!fresh || device.connected !== true) return { state: 'unknown', reason: 'KAT500 readback is unavailable or stale' };
        if (device.error) return { state: 'warning', reason: `KAT500: ${device.error}` };
        if (![device.power, device.mode, device.antenna, device.band, device.tuning].every(isPresent)) {
            return { state: 'unknown', reason: 'KAT500 critical readback is incomplete' };
        }
        if (radioBand && device.band && String(device.band).toLowerCase() !== String(radioBand).toLowerCase()) {
            return { state: 'warning', reason: `KAT500 is on ${device.band}; FLEX is on ${radioBand}` };
        }
        if (device.power !== true) return { state: 'warning', reason: 'KAT500 power is off' };
        if (device.tuning === true) return { state: 'warning', reason: 'KAT500 tune is in progress' };
        if (![1, 2, 3].includes(Number(device.antenna))) return { state: 'unknown', reason: 'KAT500 antenna output is not confirmed' };
        if (expectedAntenna && Number(device.antenna) !== expectedAntenna) {
            return { state: 'warning', reason: `KAT500 is on ANT${device.antenna}; route expects ANT${expectedAntenna}` };
        }
        if (!['auto', 'manual', 'bypass'].includes(String(device.mode || '').toLowerCase())) {
            return { state: 'unknown', reason: 'KAT500 mode is not confirmed' };
        }
        return { state: 'ready', reason: 'KAT500 route confirmed' };
    }

    function overallState(segments) {
        const states = segments.map(segment => segment.state);
        if (states.includes('disconnected')) return 'disconnected';
        if (states.includes('warning')) return 'warning';
        if (states.includes('unknown')) return 'unknown';
        return 'ready';
    }

    function displayState(value) {
        return BACKEND_STATE_MAP[String(value || '').toLowerCase()] || 'unknown';
    }

    function buildBackendViewModel(input, path) {
        const status = input.status || {};
        const radio = input.radioStatus || {};
        const kpa = status.kpa500 || {};
        const kat = status.kat500 || {};
        const pathStages = new Map((path.stages || []).map(stage => [stage.id, stage]));
        const backendStage = id => pathStages.get(id) || { id, state: 'unknown', detail: 'No path evidence' };
        const flexPath = backendStage('flex');
        const kpaPath = backendStage('kpa500');
        const katPath = backendStage('kat500');
        const antennaPath = backendStage('antenna');
        const katAntenna = [1, 2, 3].includes(Number(path.antenna?.observed))
            ? Number(path.antenna.observed)
            : null;
        const radioFrequency = numberOrNull(radio.frequency) ?? numberOrNull(path.frequency);
        const radioMode = radio.mode || path.mode;
        const radioBand = bandFromFrequency(radioFrequency) || path.band;
        const radioDrive = numberOrNull(radio.drive) ?? numberOrNull(path.rf_power_w);
        const transmitting = radio.mox === true
            || path.mox === true
            || String(radio.interlock_state || path.interlock_state || '').toUpperCase() === 'TRANSMITTING';
        const kpaOutput = numberOrNull(kpa.output_power_w);
        const kpaCurrent = numberOrNull(kpa.current);
        const katForward = numberOrNull(kat.forward_adc);
        const katRfDetected = kat.swr_live === true && katForward !== null && katForward > 0;
        const kpaNotKeyed = transmitting
            && kpa.operate === true
            && katRfDetected
            && kpaOutput === 0
            && (kpaCurrent === null || kpaCurrent <= 0.1);
        const kpaAmplifying = transmitting
            && kpa.operate === true
            && kpaOutput !== null
            && kpaOutput > 0;
        const ampKeyInterrupted = kat.amp_key_interrupted === true;
        const policyRoute = input.stationState?.route || {};
        const effectiveKpaMode = String(policyRoute.kpa500 || '').toLowerCase();
        const activeDrive = numberOrNull(policyRoute.active_drive_w);
        const policyText = effectiveKpaMode === 'operate'
            ? `Policy: amplified ${formatValue(activeDrive ?? policyRoute.amplifier_drive_w, ' W drive')}`
            : effectiveKpaMode === 'standby'
                ? `Policy: barefoot ${formatValue(activeDrive ?? policyRoute.barefoot_drive_w, ' W drive')}`
                : policyRoute.amplifier_allowed === true
                    ? `Policy: PA allowed ${formatValue(policyRoute.amplifier_drive_w, ' W drive')}`
                    : policyRoute.amplifier_allowed === false
                        ? `Policy: barefoot ${formatValue(policyRoute.barefoot_drive_w, ' W')}`
                        : null;
        const kpaReadbackMode = kpa.connected !== true
            ? 'UNAVAILABLE'
            : kpa.power === false
                ? 'POWER OFF'
                : kpa.power !== true
                    ? 'UNKNOWN'
                    : kpa.operate === true
                        ? 'OPERATE'
                        : kpa.operate === false
                            ? 'STANDBY'
                            : 'UNKNOWN';
        const kpaState = kpaNotKeyed || ampKeyInterrupted ? 'warning' : displayState(kpaPath.state);
        const kpaReason = ampKeyInterrupted
            ? 'KAT500 is interrupting the amplifier key line'
            : kpaNotKeyed
                ? 'RF is reaching the KAT500, but the KPA500 is not keyed and is adding no power'
                : (kpaPath.detail || 'KPA500 evidence is unavailable');
        const kpaPrimary = kpa.connected === true
            ? (kpa.power === true
                ? (kpa.operate === true ? 'OPERATE' : 'STANDBY')
                : kpa.power === false ? 'POWER OFF' : 'POWER UNKNOWN')
            : 'UNAVAILABLE';
        const segments = [
            {
                id: 'flex',
                state: displayState(flexPath.state),
                reason: flexPath.detail || 'FLEX evidence is unavailable',
                primary: radioFrequency === null
                    ? (path.frequency_label || 'Frequency unknown')
                    : formatFrequency(radioFrequency),
                secondary: [radioBand, radio.mox === true ? 'RF active' : radioMode].filter(Boolean).join(' · ') || flexPath.detail,
                values: {
                    mode: radioMode || '—',
                    'rf-power': formatValue(radioDrive, ' W'),
                    'tx-port': radio.tx_ant || radio.tx_antenna || path.tx_ant || 'Unconfirmed',
                    interlock: radio.interlock_state || path.interlock_state || '—',
                },
            },
            {
                id: 'kpa500',
                state: kpaState,
                stateLabel: kpa.connected === true && kpa.power === true
                    ? (kpaAmplifying ? 'TX ACTIVE' : kpaNotKeyed ? 'NOT KEYED' : ampKeyInterrupted ? 'KEY INHIBITED' : kpa.operate === true ? 'OPERATE MODE' : 'STANDBY MODE')
                    : null,
                reason: kpaReason,
                primary: kpaPrimary,
                amplifierState: kpaNotKeyed || ampKeyInterrupted
                    ? 'warning'
                    : kpaAmplifying
                    ? 'tx'
                    : kpa.operate === true
                        ? 'operate'
                        : kpa.power === true
                            ? 'standby'
                            : 'unknown',
                txActive: kpaAmplifying,
                secondary: [`Hardware readback: ${kpaReadbackMode}`, kpa.band || 'Band unknown', policyText, kpa.firmware ? `FW ${kpa.firmware}` : null].filter(Boolean).join(' · '),
                values: {
                    output: formatValue(kpa.output_power_w, ' W'),
                    swr: formatValue(kpa.swr, '', 2),
                    pa: numberOrNull(kpa.temperature_c) === null
                        ? '—'
                        : `${formatValue(kpa.temperature_c, '°C')} · ${formatValue(kpa.voltage, 'V', 1)} · ${formatValue(kpa.current, 'A', 1)}`,
                },
            },
            {
                id: 'kat500',
                state: displayState(katPath.state),
                reason: katPath.detail || 'KAT500 evidence is unavailable',
                primary: kat.connected === true
                    ? `${String(kat.mode || 'Unknown').toUpperCase()} · ANT${katAntenna || '—'}`
                    : 'Tuner unavailable',
                secondary: [kat.band || 'Band unknown', numberOrNull(kat.frequency_khz) === null ? null : `${kat.frequency_khz} kHz`].filter(Boolean).join(' · '),
                values: {
                    mode: kat.mode ? String(kat.mode).toUpperCase() : '—',
                    swr: formatValue(kat.swr, '', 2),
                    tune: kat.tuning === true ? 'Running' : kat.tuning === false ? 'Idle' : '—',
                },
            },
            {
                id: 'antenna',
                state: displayState(antennaPath.state),
                reason: antennaPath.detail || 'Antenna evidence is unavailable',
                primary: path.antenna?.label || 'Unknown antenna',
                secondary: katAntenna ? `KAT ANT${katAntenna}` : 'No output confirmed',
                txPower: formatTxPower(kpa.output_power_w),
                txActive: kpaOutput > 0,
                values: {
                    output: katAntenna ? `ANT${katAntenna}` : '—',
                    band: path.band || '—',
                    route: antennaPath.confirmed ? 'Confirmed' : 'Unconfirmed',
                },
            },
        ];
        const stageState = overallState(segments);
        const state = overallState([...segments, { state: displayState(path.state) }]);
        const issues = [
            ...(kpaNotKeyed || ampKeyInterrupted ? [kpaReason] : []),
            ...(path.mismatches || []).map(issue => issue.message || issue.code).filter(Boolean),
            ...(path.advisories || []).map(issue => issue.message || issue.code).filter(Boolean),
            ...(path.unknown_reasons || []).filter(Boolean),
        ];
        const ages = (path.stages || [])
            .map(stage => numberOrNull(stage.age_seconds))
            .filter(age => age !== null);
        const oldestAge = ages.length ? Math.max(...ages) : null;
        const anyStale = (path.stages || []).some(stage => stage.stale === true);
        return {
            state,
            stateLabel: STATE_LABELS[state],
            ageText: oldestAge === null
                ? 'Waiting for telemetry'
                : anyStale ? `Stale · ${Math.round(oldestAge)}s oldest` : 'Live telemetry',
            routeLabel: path.route_label || 'Station route is not yet known',
            message: issues.length
                ? `${issues.join(' · ')} · ${path.authorization_note || 'Read-only evidence only'}`
                : (path.authorization_note || 'Path readback is confirmed; this display does not authorize transmission.'),
            segments,
        };
    }

    function buildViewModel(input = {}) {
        const status = input.status || {};
        if (status.path?.schema_version === 1) {
            return buildBackendViewModel(input, status.path);
        }
        const radio = input.radioStatus || {};
        const tx = input.txState || {};
        const config = input.config || {};
        const now = input.now || Date.now();
        const frequency = numberOrNull(radio.frequency) ?? numberOrNull(status.radio_frequency);
        const mode = radio.mode || status.radio_mode || null;
        const radioBand = status.radio_band || bandFromFrequency(frequency);
        const txAntenna = radio.tx_ant || radio.tx_antenna || null;
        const configuredFlexAntenna = expectedFlexAntenna(config, radioBand);
        const configuredKatAntenna = expectedKatAntenna(config, radioBand);
        const fresh = isFresh(status, now);
        const kpa = status.kpa500 || {};
        const kat = status.kat500 || {};
        const transmitting = Boolean(tx.mox || tx.tune);
        const flexClassification = classifyFlex({
            connected: Boolean(input.connected),
            frequency,
            mode,
            txAntenna,
            expectedAntenna: configuredFlexAntenna,
            interlock: radio.interlock_state,
            transmitting,
        });
        const kpaClassification = classifyKpa(kpa, fresh, radioBand);
        const katClassification = classifyKat(kat, fresh, radioBand, configuredKatAntenna);
        const katAntenna = [1, 2, 3].includes(Number(kat.antenna)) ? Number(kat.antenna) : null;
        const antennaClassification = katClassification.state === 'disconnected'
            ? { state: 'disconnected', reason: 'Antenna output cannot be confirmed while KAT500 is disconnected' }
            : !fresh || !katAntenna
                ? { state: 'unknown', reason: 'Physical antenna route is not confirmed' }
                : configuredKatAntenna && katAntenna !== configuredKatAntenna
                    ? { state: 'warning', reason: `Selected ANT${katAntenna} does not match the ${radioBand || 'current'} route policy` }
                    : katAntenna === 3 && antennaName(config, katAntenna) === DEFAULT_ANTENNA_NAMES[3]
                        ? { state: 'warning', reason: 'KAT ANT3 has no confirmed physical antenna name' }
                        : { state: 'ready', reason: `${antennaName(config, katAntenna)} selected` };

        const segments = [
            {
                id: 'flex', ...flexClassification,
                primary: frequency === null ? '— MHz' : formatFrequency(frequency),
                secondary: radioBand ? `${radioBand} · ${transmitting ? 'RF active' : 'Receive'}` : (transmitting ? 'RF active' : 'Band unknown'),
                values: {
                    mode: mode || '—',
                    'rf-power': formatValue(radio.drive, ' W'),
                    'tx-port': txAntenna || (configuredFlexAntenna ? `${configuredFlexAntenna} policy` : '—'),
                    interlock: radio.interlock_state || (transmitting ? 'TRANSMITTING' : '—'),
                },
            },
            {
                id: 'kpa500', ...kpaClassification,
                stateLabel: kpa.connected === true && kpa.power === true
                    ? (kpa.operate === true ? 'OPERATE MODE' : 'STANDBY MODE')
                    : null,
                primary: kpa.connected === true ? (kpa.power === true ? (kpa.operate === true ? 'OPERATE' : 'STANDBY') : 'POWER OFF') : 'UNAVAILABLE',
                secondary: [`Hardware readback: ${kpa.operate === true ? 'OPERATE' : kpa.operate === false ? 'STANDBY' : 'UNKNOWN'}`, kpa.band || 'Band unknown', kpa.firmware ? `FW ${kpa.firmware}` : null].filter(Boolean).join(' · '),
                values: {
                    output: formatValue(kpa.output_power_w, ' W'),
                    swr: formatValue(kpa.swr, '', 2),
                    pa: numberOrNull(kpa.temperature_c) === null
                        ? '—'
                        : `${formatValue(kpa.temperature_c, '°C')} · ${formatValue(kpa.voltage, 'V', 1)} · ${formatValue(kpa.current, 'A', 1)}`,
                },
            },
            {
                id: 'kat500', ...katClassification,
                primary: kat.connected === true ? `${String(kat.mode || 'Unknown').toUpperCase()} · ANT${katAntenna || '—'}` : 'Tuner unavailable',
                secondary: [kat.band || 'Band unknown', numberOrNull(kat.frequency_khz) === null ? null : `${kat.frequency_khz} kHz`].filter(Boolean).join(' · '),
                values: {
                    mode: kat.mode ? String(kat.mode).toUpperCase() : '—',
                    swr: formatValue(kat.swr, '', 2),
                    tune: kat.tuning === true ? 'Running' : kat.tuning === false ? 'Idle' : '—',
                },
            },
            {
                id: 'antenna', ...antennaClassification,
                primary: katAntenna ? antennaName(config, katAntenna) : 'Unknown antenna',
                secondary: katAntenna ? `KAT ANT${katAntenna}` : 'No output selected',
                txPower: formatTxPower(kpa.output_power_w),
                txActive: numberOrNull(kpa.output_power_w) > 0,
                values: {
                    output: katAntenna ? `ANT${katAntenna}` : '—',
                    band: radioBand || '—',
                    route: antennaClassification.state === 'ready' ? 'Confirmed' : antennaClassification.state === 'warning' ? 'Check route' : 'Unconfirmed',
                },
            },
        ];
        const state = overallState(segments);
        const issues = segments.filter(segment => segment.state !== 'ready').map(segment => segment.reason);
        const updatedAt = numberOrNull(status.updated_at);
        const ageSeconds = updatedAt === null ? null : Math.max(0, Math.round((now - updatedAt * 1000) / 1000));
        return {
            state,
            stateLabel: STATE_LABELS[state],
            ageText: ageSeconds === null ? 'Waiting for telemetry' : (fresh ? 'Live telemetry' : `Stale · ${ageSeconds}s ago`),
            routeLabel: 'FLEX → KPA500 → KAT500 → antenna',
            message: issues.length ? issues.join(' · ') : 'All four route segments have fresh, matching readback.',
            segments,
        };
    }

    function setText(root, selector, value) {
        const element = root.querySelector(selector);
        const next = value === undefined || value === null ? '' : String(value);
        if (!element || element.textContent === next) return false;
        element.textContent = next;
        return true;
    }

    function setClass(element, value) {
        if (!element || element.className === value) return false;
        element.className = value;
        return true;
    }

    function normalizeCoordinatorState(payload) {
        const source = payload?.station_state || payload?.data?.station_state || payload || {};
        return {
            commissioned: source.commissioned === true,
            maintenance: source.maintenance === true,
            allowedActions: Array.isArray(source.allowed_actions)
                ? source.allowed_actions.filter(action => typeof action === 'string')
                : [],
            coordinatorState: String(source.coordinator_state || source.state || 'unknown').toLowerCase(),
            issues: Array.isArray(source.issues) ? source.issues : [],
            route: source.route && typeof source.route === 'object' ? source.route : null,
        };
    }

    function actionAllowed(action, state = latestCoordinatorState) {
        if (!ACTIONS.has(action) || state?.maintenance === true) return false;
        if (!state?.allowedActions?.includes(action)) return false;
        return action === 'standby' || state?.commissioned === true;
    }

    function kpaControlModel() {
        const kpa = latestStatus?.kpa500 || {};
        const kat = latestStatus?.kat500 || {};
        // AMPI1 means the KPA front panel may say OPERATE while its physical
        // key line is open.  Treat that as a failed operate state so one click
        // runs the backend's guarded recover-and-operate transaction instead
        // of asking the operator to toggle Standby first.
        const operating = kpa.operate === true && kat.amp_key_interrupted !== true;
        const target = operating ? 'standby' : 'operate';
        const transmitting = latestStatus?.path?.mox === true
            || String(latestStatus?.path?.interlock_state || '').toUpperCase() === 'TRANSMITTING';
        const direct = actionAllowed(target);
        const canPrepare = target === 'operate' && actionAllowed('prepare-route');
        const connected = kpa.connected === true && kpa.power === true;
        const enabled = connected && !transmitting && !actionInFlight && (direct || canPrepare);
        let title = target === 'standby'
            ? 'Place KPA500 in standby through the guarded station coordinator'
            : 'Verify the current route and place KPA500 in operate';
        if (!connected) title = 'KPA500 must be connected and powered';
        else if (transmitting) title = 'Wait for the current transmission to finish before changing amplifier state';
        else if (latestCoordinatorState?.maintenance === true) title = 'Station Maintenance Mode is active';
        else if (!direct && !canPrepare) {
            const issue = latestCoordinatorState?.issues
                ?.map(item => String(item?.message || '').trim())
                .find(Boolean);
            title = issue || (target === 'operate'
                ? 'Operate is locked until the station is commissioned and the route can be verified'
                : 'The station coordinator has not authorized standby');
        }
        if (actionInFlight) title = 'A guarded KPA500 state change is in progress';
        return {
            operating,
            target,
            transmitting,
            enabled,
            title,
            label: actionInFlight === 'prepare-route'
                ? 'Verifying…'
                : actionInFlight
                    ? 'Switching…'
                    : 'Switch',
        };
    }

    function renderKpaControl(root) {
        const button = root.querySelector('[data-kpa-toggle]');
        if (!button) return false;
        const model = kpaControlModel();
        let changed = false;
        if (button.disabled === model.enabled) {
            button.disabled = !model.enabled;
            changed = true;
        }
        if (button.dataset.targetAction !== model.target) {
            button.dataset.targetAction = model.target;
            changed = true;
        }
        const txActive = String(model.transmitting);
        if (button.dataset.txActive !== txActive) {
            button.dataset.txActive = txActive;
            changed = true;
        }
        const checked = String(model.operating);
        if (button.getAttribute('aria-checked') !== checked) {
            button.setAttribute('aria-checked', checked);
            changed = true;
        }
        const ariaLabel = model.target === 'operate'
            ? 'KPA500 is in Standby; switch to Operate'
            : 'KPA500 is in Operate; switch to Standby';
        if (button.getAttribute('aria-label') !== ariaLabel) {
            button.setAttribute('aria-label', ariaLabel);
            changed = true;
        }
        if (button.title !== model.title) {
            button.title = model.title;
            changed = true;
        }
        if (button.textContent !== model.label) {
            button.textContent = model.label;
            changed = true;
        }
        return changed;
    }

    function render(viewModel) {
        const root = document.getElementById('station-path-dashboard');
        if (!root) return;
        let changed = false;
        if (root.dataset.state !== viewModel.state) {
            root.dataset.state = viewModel.state;
            changed = true;
        }
        const badge = root.querySelector('[data-path-role="overall-state"]');
        if (badge) {
            if (badge.textContent !== viewModel.stateLabel) {
                badge.textContent = viewModel.stateLabel;
                changed = true;
            }
            changed = setClass(badge, `station-path-state state-${viewModel.state}`) || changed;
        }
        changed = setText(root, '[data-path-role="age"]', viewModel.ageText) || changed;
        changed = setText(root, '[data-path-role="route-label"]', viewModel.routeLabel) || changed;
        const message = latestActionError
            ? `KPA500 action blocked: ${latestActionError}`
            : latestStatusError && !latestStatus
                ? latestStatusError
                : viewModel.message;
        changed = setText(root, '[data-path-role="message"]', message) || changed;

        viewModel.segments.forEach(segment => {
            const node = root.querySelector(`[data-path-segment="${segment.id}"]`);
            if (!node) return;
            changed = setClass(node, `station-path-node state-${segment.state}`) || changed;
            changed = setText(node, '[data-path-role="state"]', segment.stateLabel || STATE_LABELS[segment.state]) || changed;
            changed = setText(node, '[data-path-role="primary"]', segment.primary) || changed;
            changed = setText(node, '[data-path-role="secondary"]', segment.secondary || segment.reason) || changed;
            changed = setText(node, '[data-path-role="tx-power"]', segment.txPower) || changed;
            const txActive = String(segment.txActive === true);
            if (node.dataset.txActive !== txActive) {
                node.dataset.txActive = txActive;
                changed = true;
            }
            if (segment.id === 'kpa500') {
                const amplifierState = segment.amplifierState || 'unknown';
                if (node.dataset.amplifierState !== amplifierState) {
                    node.dataset.amplifierState = amplifierState;
                    changed = true;
                }
            }
            Object.entries(segment.values).forEach(([key, value]) => {
                changed = setText(node, `[data-path-value="${key}"]`, value) || changed;
            });
            if (node.title !== segment.reason) {
                node.title = segment.reason;
                changed = true;
            }
        });
        changed = renderKpaControl(root) || changed;
        if (changed && typeof CustomEvent !== 'undefined') {
            document.dispatchEvent(new CustomEvent('station-path-updated'));
        }
    }

    function renderCurrent() {
        const app = window.vueInstance;
        const appRadioStatus = app?.radioStatus || {};
        render(buildViewModel({
            status: latestStatus,
            connected: Boolean(app?.connected ?? latestRadioStatus.connected),
            radioStatus: { ...appRadioStatus, ...latestRadioStatus },
            txState: app?.txState,
            config: app?.configData,
            stationState: latestCoordinatorState,
        }));
    }

    async function responsePayload(response) {
        try {
            return await response.json();
        } catch (_) {
            return {};
        }
    }

    async function fetchStatus(refresh = false) {
        if (requestInFlight) return;
        requestInFlight = true;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 4000);
        try {
            const [response, stationResponse] = await Promise.all([
                fetch(`/api/elecraft/status${refresh ? '?refresh=true' : ''}`, { cache: 'no-store', signal: controller.signal }),
                fetch('/api/station/state', { cache: 'no-store', signal: controller.signal }),
            ]);
            if (!response.ok) throw new Error(`Elecraft status HTTP ${response.status}`);
            const payload = await responsePayload(response);
            if (!payload?.success || !payload.status) throw new Error('Elecraft status response is incomplete');
            latestStatus = payload.status;
            if (stationResponse.ok) latestCoordinatorState = normalizeCoordinatorState(await responsePayload(stationResponse));
            latestStatusError = null;
        } catch (error) {
            latestStatusError = error?.name === 'AbortError' ? 'Elecraft status request timed out' : (error?.message || 'Elecraft status is unavailable');
        } finally {
            clearTimeout(timeout);
            requestInFlight = false;
            renderCurrent();
        }
    }

    function applyStreamPayload(payload) {
        if (payload?.status) latestStatus = payload.status;
        if (payload?.station_state) latestCoordinatorState = normalizeCoordinatorState(payload.station_state);
        latestStatusError = null;
        renderCurrent();
    }

    function connectStream() {
        if (stream || typeof EventSource !== 'function') return false;
        stream = new EventSource(STREAM_ENDPOINT);
        stream.addEventListener('station', event => {
            try {
                applyStreamPayload(JSON.parse(event.data));
            } catch (_) {
                // Ignore malformed frames; the reconciliation fetch remains authoritative.
            }
        });
        stream.onerror = () => {
            // EventSource reconnects automatically. Do not repaint or flash the
            // widget while the last confirmed snapshot remains available.
        };
        return true;
    }

    function normalizeRadioUpdate(data = {}) {
        const fieldMapping = {
            freq: 'frequency',
            rfpower: 'drive',
            tunepower: 'tune_power',
            miclevel: 'mic_level',
            vox_enable: 'vox_enabled',
        };
        return Object.fromEntries(Object.entries(data).map(([key, value]) => [fieldMapping[key] || key, value]));
    }

    function applyRadioUpdate(data) {
        if (!data || typeof data !== 'object') return false;
        latestRadioStatus = { ...latestRadioStatus, ...normalizeRadioUpdate(data) };
        renderCurrent();
        return true;
    }

    function connectRadioStream() {
        if (radioStream || typeof WebSocket !== 'function') return false;
        const protocol = window.location?.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location?.host;
        if (!host) return false;
        const socket = new WebSocket(`${protocol}//${host}/ws/radio`);
        radioStream = socket;
        socket.onmessage = event => {
            try {
                const message = JSON.parse(event.data);
                if (message.type === 'status') applyRadioUpdate(message.data);
            } catch (_) {
                // The cached station stream remains the authoritative fallback.
            }
        };
        socket.onclose = () => {
            if (radioStream === socket) radioStream = null;
            if (!stopped) {
                clearTimeout(radioReconnectTimer);
                radioReconnectTimer = setTimeout(connectRadioStream, 1500);
            }
        };
        socket.onerror = () => {
            // Closing triggers one bounded reconnect; no polling is added.
            socket.close();
        };
        return true;
    }

    async function postAction(action) {
        const response = await fetch(`/api/station/actions/${action}`, {
            method: 'POST',
            headers: { Accept: 'application/json' },
        });
        const payload = await responsePayload(response);
        const detail = payload.detail;
        const message = typeof detail === 'string'
            ? detail
            : detail?.message || payload.message || detail?.code;
        if (!response.ok) throw new Error(message || `Station action failed with HTTP ${response.status}`);
        if (payload.station_state) latestCoordinatorState = normalizeCoordinatorState(payload.station_state);
        return payload;
    }

    async function handleKpaToggle() {
        if (actionInFlight) return;
        const model = kpaControlModel();
        if (!model.enabled) return;
        latestActionError = null;
        try {
            // The backend makes OPERATE atomic: it prepares and verifies the
            // route under the same locks before switching the amplifier.  A
            // single click therefore cannot lose its proof to background
            // route following between two HTTP requests.
            actionInFlight = model.target;
            renderCurrent();
            await postAction(model.target);
            // The guarded action already performed fresh hardware readbacks
            // and updated the manager cache.  A second forced multi-device
            // serial refresh made the switch look several seconds slower.
            // Reconcile from that authoritative cache immediately; the event
            // stream and periodic poll continue normal live verification.
            await fetchStatus();
        } catch (error) {
            latestActionError = error?.message || `KPA500 ${model.target} failed`;
        } finally {
            actionInFlight = null;
            renderCurrent();
        }
    }

    function bindActions() {
        const root = document.getElementById('station-path-dashboard');
        if (!root || root.dataset.kpaActionBound === 'true') return;
        root.dataset.kpaActionBound = 'true';
        root.addEventListener('click', event => {
            const button = event.target.closest?.('[data-kpa-toggle]');
            if (button && !button.disabled) void handleKpaToggle();
        });
    }

    function start() {
        if (timer) return;
        stopped = false;
        bindActions();
        renderCurrent();
        void fetchStatus();
        connectStream();
        connectRadioStream();
        timer = setInterval(fetchStatus, RECONCILE_MS);
    }

    function stop() {
        stopped = true;
        clearInterval(timer);
        timer = null;
        clearTimeout(radioReconnectTimer);
        radioReconnectTimer = null;
        stream?.close?.();
        stream = null;
        if (radioStream) {
            radioStream.onclose = null;
            radioStream.close?.();
            radioStream = null;
        }
    }

    window.StationPathDashboard = {
        DEFAULT_ANTENNA_NAMES,
        bandFromFrequency,
        buildBackendViewModel,
        buildViewModel,
        classifyFlex,
        classifyKpa,
        classifyKat,
        actionAllowed,
        applyRadioUpdate,
        applyStreamPayload,
        formatFrequency,
        formatTxPower,
        hasFault,
        isFresh,
        normalizeCoordinatorState,
        normalizeRadioUpdate,
        postAction,
        start,
        stop,
    };

    if (typeof document !== 'undefined') {
        document.addEventListener('vue-mounted', start, { once: true });
        window.addEventListener('beforeunload', stop, { once: true });
    }
}());
