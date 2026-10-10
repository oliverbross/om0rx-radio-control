// Guarded ATU planning and training. Plan construction never starts execution;
// the RF-producing job requires a separate action and explicit confirmations.
(function () {
    'use strict';

    const ENDPOINT = '/api/station/training/preview';
    const JOBS_ENDPOINT = '/api/station/training/jobs';
    const ACTIVE_JOB_ENDPOINT = `${JOBS_ENDPOINT}/active`;
    const TUNES_ENDPOINT = '/api/station/tunes';
    const DIGITAL_STOP_ENDPOINT = '/api/digital/stop';
    const DEFAULT_FETCH_OPTIONS = Object.freeze({ method: 'GET', cache: 'no-store' });
    const SVG_NS = 'http://www.w3.org/2000/svg';
    const TARGET_SWR = 1.5;
    const ABORT_SWR = 3;
    const BAND_FREQUENCIES = Object.freeze({
        '160m': Object.freeze({ cw: 1.830, data: 1.840, ssb: 1.900 }),
        '80m': Object.freeze({ cw: 3.520, data: 3.573, ssb: 3.700 }),
        '60m': Object.freeze({ cw: 5.3515, data: 5.357, ssb: 5.3665 }),
        '40m': Object.freeze({ cw: 7.030, data: 7.074, ssb: 7.150 }),
        '30m': Object.freeze({ cw: 10.120, data: 10.136, ssb: 10.140 }),
        '20m': Object.freeze({ cw: 14.030, data: 14.074, ssb: 14.200 }),
        '17m': Object.freeze({ cw: 18.080, data: 18.100, ssb: 18.130 }),
        '15m': Object.freeze({ cw: 21.030, data: 21.074, ssb: 21.250 }),
        '12m': Object.freeze({ cw: 24.910, data: 24.915, ssb: 24.950 }),
        '10m': Object.freeze({ cw: 28.030, data: 28.074, ssb: 28.400 }),
        '6m': Object.freeze({ cw: 50.090, data: 50.313, ssb: 50.150 }),
    });
    const TERMINAL_JOB_STATES = Object.freeze(['completed', 'succeeded', 'completed_with_failures', 'failed', 'error', 'cancelled', 'canceled', 'aborted']);
    let previewController = null;
    let pollTimer = null;
    let preflightTimer = null;
    let preflightBusy = false;
    let lastRequest = null;
    let lastView = null;
    let activeJob = null;
    let pendingOperation = null;
    let currentResultPoints = [];
    let historyProfiles = [];

    function formatDuration(seconds) {
        const value = Number(seconds);
        if (!Number.isFinite(value) || value < 0) return '—';
        if (value < 60) return `${Math.round(value)} s`;
        return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
    }

    function numericOrNull(value) {
        if (value === null || value === undefined || value === '') return null;
        const number = Number(value);
        return Number.isFinite(number) && number > 0 ? number : null;
    }

    function formatSWR(value) {
        const number = numericOrNull(value);
        return number === null ? '—' : number.toFixed(2);
    }

    function normalizePoint(point, index) {
        const eligible = point.eligible === true
            || (point.eligible == null && !(point.blocked_reasons || []).length);
        const apiStatus = String(point.status || '').trim();
        const frequencyMhz = numericOrNull(point.frequency_mhz)
            ?? (numericOrNull(point.memory_bin_khz) === null ? null : Number(point.memory_bin_khz) / 1000)
            ?? (numericOrNull(point.kat_memory_bin?.bin_start_khz) === null
                ? null
                : Number(point.kat_memory_bin.bin_start_khz) / 1000);
        const portions = Array.isArray(point.portions) ? point.portions : [];
        const pointError = typeof point.error === 'object'
            ? String(point.error?.message || point.error?.code || '')
            : String(point.error || '');
        const statusText = apiStatus && pointError
            ? `${apiStatus.replaceAll('_', ' ')} — ${pointError}`
            : apiStatus;
        return {
            sequence: Number(point.sequence) || index + 1,
            band: String(point.band || '—'),
            portion: String(point.portion || portions.join('/') || '').toLowerCase(),
            frequencyMhz,
            frequency: frequencyMhz === null ? '—' : `${frequencyMhz.toFixed(3)} MHz`,
            flex: String(point.flex_tx_ant || '—'),
            kat: point.kat_antenna ? `ANT${point.kat_antenna} · ${point.antenna_name || 'unnamed'}` : '—',
            eligible,
            swrBefore: numericOrNull(point.swr_before),
            swrAfter: numericOrNull(point.swr_after),
            resultStatus: apiStatus,
            status: statusText || (eligible ? 'Eligible preview' : (point.blocked_reasons || []).join('; ') || 'Blocked'),
        };
    }

    function normalize(payload) {
        const source = payload?.training_preview;
        if (!source || source.preview_only !== true || !Array.isArray(source.points)) {
            return { state: 'unavailable', message: 'ATU plan preview is unavailable. No hardware action was attempted.', points: [] };
        }
        const points = source.points.map(normalizePoint);
        const rawPlotPoints = Array.isArray(source.plot)
            ? source.plot
            : (Array.isArray(source.plot?.points) ? source.plot.points : source.points);
        const plotPoints = rawPlotPoints.map(normalizePoint);
        const errors = Array.isArray(source.validation_errors) ? source.validation_errors : [];
        const execution = source.execution || source.preflight || source.job_preflight || source.capabilities || {};
        const executionAvailable = source.execution_available === true || execution.execution_available === true || execution.available === true;
        const rawBlockers = source.execution_blockers || execution.execution_blockers || execution.blockers || [];
        const executionBlockerDetails = (Array.isArray(rawBlockers) ? rawBlockers : [rawBlockers])
            .map(blocker => typeof blocker === 'string'
                ? { code: '', message: blocker }
                : { code: String(blocker?.code || ''), message: String(blocker?.message || blocker?.code || '') })
            .filter(blocker => blocker.message);
        if (!executionAvailable && !executionBlockerDetails.length) {
            executionBlockerDetails.push({ code: 'training-execution-unavailable', message: 'The backend has not enabled RF execution for this plan.' });
        }
        const requiredConfirmation = String(source.required_confirmation || execution.required_confirmation || '').trim();
        const executionBlockers = executionBlockerDetails.map(blocker => blocker.message);
        return {
            state: errors.length ? 'invalid' : 'ready',
            pointCount: Number.isFinite(Number(source.point_count)) ? Number(source.point_count) : points.length,
            eligible: Number(source.eligible_count) || 0,
            blocked: Number(source.blocked_count) || 0,
            duration: formatDuration(source.total_worst_case_seconds),
            power: Number.isFinite(Number(source.tune_power_w)) ? `${Number(source.tune_power_w)} W` : '—',
            points,
            plotPoints,
            executionAvailable: executionAvailable && errors.length === 0 && executionBlockers.length === 0,
            executionBlockers,
            executionBlockerCodes: executionBlockerDetails.map(blocker => blocker.code).filter(Boolean),
            requiredConfirmation,
            message: errors.length
                ? errors.map(error => error.message || error.code).join('; ')
                : (Number(source.blocked_count) > 0
                    ? `Plan ready — ${Number(source.eligible_count) || 0} runnable point(s); ${Number(source.blocked_count)} policy-blocked point(s) will be skipped.`
                    : `Plan ready — ${points.length} point${points.length === 1 ? '' : 's'}. Inspect every route and frequency before training.`),
        };
    }

    function unwrapJob(payload) {
        if (!payload || typeof payload !== 'object') return null;
        return payload.training_job || payload.active_job || payload.job || payload;
    }

    function normalizeJob(payload) {
        const source = unwrapJob(payload);
        if (!source || (!source.id && !source.job_id && !source.training_job_id && !source.status && !source.state && !source.phase)) return null;
        const status = String(source.status || source.state || source.phase || 'unknown').toLowerCase();
        const rawResults = source.results || source.result_points || source.points || source.measurements || [];
        const results = (Array.isArray(rawResults) ? rawResults : []).map(normalizePoint);
        const total = Number(source.total_points ?? source.point_count ?? source.progress?.total ?? results.length) || 0;
        const completed = Number(source.completed_points ?? source.completed_count ?? source.progress?.completed ?? results.length) || 0;
        const rawBlockers = source.execution_blockers || source.blockers || source.errors || [];
        const blockers = (Array.isArray(rawBlockers) ? rawBlockers : [rawBlockers])
            .map(blocker => typeof blocker === 'string' ? blocker : (blocker?.message || blocker?.detail || blocker?.code || ''))
            .filter(Boolean);
        const rawError = source.error;
        const error = rawError && typeof rawError === 'object'
            ? {
                code: String(rawError.code || 'training-error'),
                message: String(rawError.message || rawError.detail || 'Training operation failed'),
            }
            : (rawError ? { code: 'training-error', message: String(rawError) } : null);
        const message = String(source.message || source.detail || error?.message || '').trim();
        const events = (Array.isArray(source.events) ? source.events : []).map(event => ({
            sequence: Number(event?.sequence) || 0,
            occurredAt: String(event?.occurred_at || ''),
            event: String(event?.event || 'unknown'),
            step: String(event?.step || ''),
            pointSequence: Number(event?.point_sequence) || null,
            frequencyMhz: numericOrNull(event?.frequency_mhz),
            attempt: Number(event?.attempt) || null,
            durationMs: Number.isFinite(Number(event?.duration_ms)) ? Number(event.duration_ms) : null,
            error: event?.error && typeof event.error === 'object'
                ? String(event.error.message || event.error.code || '')
                : '',
        }));
        return {
            id: String(source.id || source.job_id || source.training_job_id || ''),
            operation: String(source.operation || 'train').toLowerCase() === 'survey' ? 'survey' : 'train',
            status,
            total,
            requestedTotal: Number(source.requested_point_count ?? total) || total,
            skipped: Number(source.skipped_point_count) || 0,
            completed,
            processed: Number(source.processed_count ?? completed ?? results.length) || 0,
            failedPoints: Number(source.failed_point_count) || 0,
            currentFrequencyMhz: numericOrNull(source.current_frequency_mhz || source.progress?.frequency_mhz),
            results,
            blockers,
            message,
            error,
            events,
            terminal: TERMINAL_JOB_STATES.includes(status),
            raw: source,
        };
    }

    function buildStartPayload(request, confirmations) {
        return {
            ...(request || {}),
            operation: confirmations?.operation === 'survey' ? 'survey' : 'train',
            operator_confirmed: confirmations?.operatorConfirmed === true,
            approved_load_confirmed: confirmations?.approvedLoadConfirmed === true,
            digital_engine_inhibit_confirmed: confirmations?.digitalEngineInhibitConfirmed === true,
            legal_operation_confirmed: confirmations?.legalOperationConfirmed === true,
            vendor_backup_confirmed: confirmations?.vendorBackupConfirmed === true,
        };
    }

    function buildRequest(bands, portions, options = {}) {
        const selectedBands = [...new Set((bands || []).filter(band => BAND_FREQUENCIES[band]))];
        const selectedPortions = [...new Set((portions || []).filter(portion => ['cw', 'data', 'ssb'].includes(portion)))];
        const requestedCoverage = String(options.coverage || 'representative').toLowerCase();
        return {
            bands: selectedBands,
            portions: selectedPortions,
            coverage: requestedCoverage === 'full_bins' ? 'full_bins' : 'representative',
            erase_selected_memories: options.eraseSelectedMemories === true,
            // Keep the legacy field in the API contract while leaving point
            // generation to the backend's authoritative KAT-bin planner.
            frequency_points_mhz: {},
        };
    }

    function buildPlotSeries(points) {
        return (points || []).flatMap((point, index) => {
            const result = [];
            if (numericOrNull(point.swrBefore) !== null) result.push({ kind: 'before', index, swr: Number(point.swrBefore), band: point.band });
            if (numericOrNull(point.swrAfter) !== null) result.push({ kind: 'after', index, swr: Number(point.swrAfter), band: point.band });
            return result;
        });
    }

    function setText(root, selector, value) {
        const node = root.querySelector(selector);
        if (node) node.textContent = value;
    }

    function svgElement(name, attributes) {
        const node = document.createElementNS(SVG_NS, name);
        Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
        return node;
    }

    function renderPlot(root, points) {
        const svg = root.querySelector('[data-training-role="swr-plot"]');
        const layer = root.querySelector('[data-training-role="plot-points"]');
        const empty = root.querySelector('[data-training-role="plot-empty"]');
        if (!svg || !layer || !empty) return;
        const series = buildPlotSeries(points);
        const slots = Math.max(1, points.length - 1);
        const xFor = index => points.length === 1 ? 396 : 66 + (index / slots) * 660;
        const yFor = swr => 182 - ((Math.min(4, Math.max(1, swr)) - 1) / 3) * 162;
        const children = [];
        (points || []).forEach((point, index) => {
            const group = svgElement('g', { class: 'station-training-plot-point planned' });
            const tick = svgElement('circle', { cx: xFor(index), cy: 190, r: 3, tabindex: '0' });
            const title = svgElement('title', {});
            title.textContent = `${point.band} ${point.frequency}: planned, awaiting measurement`;
            tick.appendChild(title);
            group.appendChild(tick);
            children.push(group);
        });
        ['before', 'after'].forEach(kind => {
            const values = series.filter(value => value.kind === kind);
            if (values.length > 1) {
                children.push(svgElement('polyline', {
                    class: `station-training-series ${kind}`,
                    points: values.map(value => `${xFor(value.index)},${yFor(value.swr)}`).join(' '),
                }));
            }
            values.forEach(value => {
                const group = svgElement('g', { class: `station-training-plot-point ${kind}` });
                const dot = svgElement('circle', { cx: xFor(value.index), cy: yFor(value.swr), r: 5, tabindex: '0' });
                const title = svgElement('title', {});
                title.textContent = `${value.band} ${kind} tuning: SWR ${value.swr.toFixed(2)}`;
                dot.appendChild(title);
                group.appendChild(dot);
                children.push(group);
            });
        });
        layer.replaceChildren(...children);
        empty.hidden = series.length > 0;
        if (!series.length && points.length) {
            empty.textContent = `Plan ready — ${points.length} point${points.length === 1 ? '' : 's'} awaiting measurements`;
        } else if (!series.length) {
            empty.textContent = 'Build a plan to show planned tuning points';
        } else {
            empty.textContent = 'SWR results will be drawn here';
        }
        svg.setAttribute('aria-label', series.length
            ? `SWR plot with ${series.length} returned measurement${series.length === 1 ? '' : 's'} and ${points.length} planned frequency markers. Target ${TARGET_SWR}; abort threshold ${ABORT_SWR}.`
            : points.length
                ? `Plan ready with ${points.length} planned frequency marker${points.length === 1 ? '' : 's'}; no SWR measurements yet.`
                : 'SWR preview plot. No planned or measured points available.');
    }

    function statusClass(point) {
        const status = point.resultStatus.toLowerCase();
        if (status.includes('abort') || status.includes('fail') || !point.eligible) return 'station-training-point-blocked';
        if (status.includes('complete') || status.includes('success') || point.swrAfter !== null) return 'station-training-point-complete';
        return 'station-training-point-ready';
    }

    function render(view, options = {}) {
        const root = document.getElementById('station-training-preview');
        if (!root) return;
        if (options.jobResults !== true) lastView = view;
        root.dataset.state = view.state;
        root.dataset.erasePreview = options.erasePreview ? 'true' : 'false';
        setText(root, '[data-training-role="point-count"]', view.pointCount ?? view.points.length ?? '—');
        setText(root, '[data-training-role="eligible"]', view.eligible ?? '—');
        setText(root, '[data-training-role="blocked"]', view.blocked ?? '—');
        setText(root, '[data-training-role="duration"]', view.duration ?? '—');
        setText(root, '[data-training-role="power"]', view.power ?? '—');
        const warning = options.erasePreview
            ? ' Erase simulation selected: existing memories are shown as replaceable, but this preview cannot erase them.'
            : '';
        setText(root, '[data-training-role="message"]', `${view.message}${warning}`);
        const body = root.querySelector('[data-training-role="points"]');
        if (body) {
            body.replaceChildren(...view.points.map(point => {
                const row = document.createElement('tr');
                const values = [point.band, point.frequency, point.flex, point.kat, formatSWR(point.swrBefore), formatSWR(point.swrAfter), point.status];
                values.forEach((value, index) => {
                    const cell = document.createElement('td');
                    cell.textContent = value;
                    if (index === 6) cell.className = statusClass(point);
                    row.appendChild(cell);
                });
                return row;
            }));
        }
        renderPlot(root, view.plotPoints || view.points);
        renderExecutionAvailability(root, view);
    }

    function selection(root, name) {
        return [...root.querySelectorAll(`input[name="${name}"]:checked`)].map(input => input.value);
    }

    function setFormError(root, message) {
        const node = root.querySelector('[data-training-role="form-error"]');
        if (!node) return;
        node.textContent = message;
        node.hidden = !message;
    }

    function setExecutionMessage(root, message, tone = 'info') {
        const node = root.querySelector('[data-training-role="execution-message"]');
        if (!node) return;
        node.textContent = message;
        node.dataset.tone = tone;
    }

    function confirmationState(root) {
        return {
            approvedLoadConfirmed: root.querySelector('[data-training-role="approved-load"]')?.checked === true,
            digitalEngineInhibitConfirmed: root.querySelector('[data-training-role="digital-inhibit"]')?.checked === true,
            legalOperationConfirmed: root.querySelector('[data-training-role="legal-operation"]')?.checked === true,
            vendorBackupConfirmed: root.querySelector('[data-training-role="vendor-backup"]')?.checked === true,
        };
    }

    function confirmationsComplete(root) {
        const confirmations = confirmationState(root);
        const eraseRequested = lastRequest?.erase_selected_memories === true;
        return confirmations.approvedLoadConfirmed
            && confirmations.digitalEngineInhibitConfirmed
            && confirmations.legalOperationConfirmed
            && (!eraseRequested || confirmations.vendorBackupConfirmed);
    }

    function updateStartEnabled(root) {
        const start = root.querySelector('[data-training-role="start"]');
        const survey = root.querySelector('[data-training-role="survey"]');
        if (!start && !survey) return;
        const running = Boolean(activeJob && !activeJob.terminal);
        const terminal = Boolean(activeJob?.terminal);
        const planReady = Boolean(lastRequest && lastView?.state === 'ready' && lastView.executionAvailable);
        const commonDisabled = running || terminal || !planReady || !confirmationsComplete(root);
        if (start) start.disabled = commonDisabled;
        if (survey) survey.disabled = commonDisabled || lastRequest?.erase_selected_memories === true;
        const title = running
            ? 'A station job is already running.'
            : terminal
                ? 'Build a new plan before another run.'
                : !lastRequest
                    ? 'Build a plan first.'
                    : !lastView?.executionAvailable
                        ? 'Execution preflight is blocked; see the prerequisite list.'
                        : !confirmationsComplete(root)
                            ? 'Complete every safety confirmation.'
                            : 'A final Yes/No RF confirmation will be shown.';
        if (start) start.title = title;
        if (survey) {
            survey.title = lastRequest?.erase_selected_memories
                ? 'SWR survey cannot be combined with memory erase.'
                : title;
        }

        if (!running && !terminal && planReady) {
            const confirmations = confirmationState(root);
            const eraseRequested = lastRequest?.erase_selected_memories === true;
            const boxesComplete = confirmations.approvedLoadConfirmed
                && confirmations.digitalEngineInhibitConfirmed
                && confirmations.legalOperationConfirmed
                && (!eraseRequested || confirmations.vendorBackupConfirmed);
            if (!boxesComplete) {
                setExecutionMessage(root, 'Complete every required safety confirmation. No RF will start until all are checked.', 'warning');
            } else setExecutionMessage(root, 'Ready. Choose SWR survey or training; a final Yes/No RF confirmation will appear.', 'warning');
        }
    }

    function hasDigitalBlocker(view) {
        const codes = view?.executionBlockerCodes || [];
        return codes.includes('digital-engine-owns-radio') || codes.includes('digital-tx-armed');
    }

    function schedulePreflightRefresh() {
        clearTimeout(preflightTimer);
        const hidden = typeof document.visibilityState === 'string' && document.visibilityState === 'hidden';
        if (hidden || preflightBusy || !lastRequest || activeJob || lastView?.executionAvailable) return;
        preflightTimer = setTimeout(() => refreshSafetyStatus(false), 4000);
    }

    function renderExecutionAvailability(root, view) {
        const blockers = root.querySelector('[data-training-role="blockers"]');
        const backupRow = root.querySelector('[data-training-role="backup-row"]');
        const stopDigital = root.querySelector('[data-training-role="stop-digital"]');
        const eraseRequested = lastRequest?.erase_selected_memories === true;
        if (backupRow) backupRow.hidden = !eraseRequested;
        if (stopDigital) stopDigital.hidden = !hasDigitalBlocker(view);
        const reasons = view.executionAvailable
            ? [view.blocked > 0
                ? `Backend preflight passed for ${view.eligible} eligible point(s); ${view.blocked} policy-blocked point(s) will remain visible and be skipped.`
                : 'Plan valid and backend execution preflight passed. Complete all confirmations below.']
            : (view.executionBlockers?.length ? view.executionBlockers : ['RF execution is unavailable for this plan.']);
        if (blockers) {
            blockers.replaceChildren(...reasons.map(reason => {
                const item = document.createElement('li');
                item.textContent = reason;
                return item;
            }));
            blockers.parentElement?.setAttribute('data-ready', view.executionAvailable ? 'true' : 'false');
        }
        if (!activeJob) {
            setExecutionMessage(root, view.executionAvailable
                ? 'Training is ready only after every confirmation is complete. Starting will produce RF.'
                : `Training blocked: ${reasons.join('; ')}`, view.executionAvailable ? 'warning' : 'error');
        }
        updateStartEnabled(root);
        schedulePreflightRefresh();
    }

    function resetConfirmations(root) {
        ['approved-load', 'digital-inhibit', 'legal-operation', 'vendor-backup'].forEach(role => {
            const input = root.querySelector(`[data-training-role="${role}"]`);
            if (input) input.checked = false;
        });
    }

    function markPlanStale(root) {
        if (!lastRequest || activeJob) return;
        lastRequest = null;
        clearTimeout(preflightTimer);
        resetConfirmations(root);
        const reasons = ['Selections changed. Build the plan again before training.'];
        renderExecutionAvailability(root, {
            ...lastView,
            executionAvailable: false,
            executionBlockers: reasons,
            requiredConfirmation: '',
        });
        setExecutionMessage(root, `Training blocked: ${reasons[0]}`, 'error');
    }

    async function refreshSafetyStatus(announce = true) {
        const root = document.getElementById('station-training-preview');
        if (!root || !lastRequest || preflightBusy || activeJob) return null;
        preflightBusy = true;
        const button = root.querySelector('[data-training-role="recheck"]');
        if (button) button.disabled = true;
        try {
            const view = await requestPreview('POST', lastRequest, {
                erasePreview: lastRequest.erase_selected_memories === true,
            });
            if (announce && view) {
                setExecutionMessage(root, view.executionAvailable
                    ? 'Safety status refreshed. Complete the safety confirmations, then choose survey or training.'
                    : `Safety status refreshed; still blocked: ${view.executionBlockers.join('; ')}`, view.executionAvailable ? 'warning' : 'error');
                updateStartEnabled(root);
            }
            return view;
        } finally {
            preflightBusy = false;
            if (button) button.disabled = false;
            schedulePreflightRefresh();
        }
    }

    async function stopDigitalEngine() {
        const root = document.getElementById('station-training-preview');
        if (!root || preflightBusy) return null;
        const button = root.querySelector('[data-training-role="stop-digital"]');
        if (button) button.disabled = true;
        setExecutionMessage(root, 'Stopping the selected digital engine and verifying FLEX receive…', 'warning');
        try {
            const response = await fetch(DIGITAL_STOP_ENDPOINT, {
                method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: '{}',
            });
            const result = await responseJson(response);
            if (result?.success !== true || result?.recovery_tx_off_required === true) {
                throw new Error('Digital engine stop did not return a confirmed safe state');
            }
            const view = await refreshSafetyStatus(false);
            if (!view) throw new Error('Safety status could not be refreshed');
            if (hasDigitalBlocker(view)) throw new Error('Digital engine still owns radio control');
            setExecutionMessage(root, 'Digital engine stopped and radio control released. Complete the safety confirmations, then choose survey or training.', 'success');
            updateStartEnabled(root);
            return result;
        } catch (error) {
            setExecutionMessage(root, `Digital engine was not safely released: ${error?.message || 'unknown error'}. No training was started.`, 'error');
            return null;
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function responseJson(response) {
        let body = null;
        try { body = await response.json(); } catch (_) { /* HTTP status remains useful. */ }
        if (!response.ok) {
            const detail = body?.detail || body?.message || body?.error;
            const blockerDetails = Array.isArray(detail?.execution_blockers)
                ? detail.execution_blockers
                    .map(item => item?.message || item?.code || '')
                    .filter(Boolean)
                    .join('; ')
                : '';
            const description = Array.isArray(detail)
                ? detail.map(item => item?.msg || item?.message || String(item)).join('; ')
                : (typeof detail === 'object'
                    ? [detail?.message, blockerDetails].filter(Boolean).join(': ') || JSON.stringify(detail)
                    : detail);
            throw new Error(description || `HTTP ${response.status}`);
        }
        return body;
    }

    async function requestPreview(method = 'GET', payload = null, options = {}) {
        const root = document.getElementById('station-training-preview');
        if (!root) return null;
        if (previewController) previewController.abort();
        previewController = new AbortController();
        root.dataset.state = 'loading';
        const fetchOptions = { ...DEFAULT_FETCH_OPTIONS, method, signal: previewController.signal };
        if (payload) {
            fetchOptions.headers = { 'Content-Type': 'application/json' };
            fetchOptions.body = JSON.stringify(payload);
        }
        try {
            const response = await fetch(ENDPOINT, fetchOptions);
            const view = normalize(await responseJson(response));
            render(view, options);
            return view;
        } catch (error) {
            if (error?.name !== 'AbortError') {
                const unavailable = normalize(null);
                unavailable.message = `ATU plan request failed: ${error?.message || 'unknown error'}. No RF action was attempted.`;
                unavailable.executionBlockers = [unavailable.message];
                render(unavailable, options);
                setFormError(root, unavailable.message);
            }
            return null;
        }
    }

    async function buildPlan(event) {
        event?.preventDefault();
        const root = document.getElementById('station-training-preview');
        if (!root) return null;
        const bands = selection(root, 'training-band');
        const portions = selection(root, 'training-portion');
        if (!bands.length || !portions.length) {
            setFormError(root, !bands.length ? 'Select at least one band.' : 'Select at least one band portion.');
            return null;
        }
        setFormError(root, '');
        activeJob = null;
        currentResultPoints = [];
        pendingOperation = null;
        clearTimeout(pollTimer);
        const diagnostics = root.querySelector('[data-training-role="diagnostics"]');
        if (diagnostics) diagnostics.hidden = true;
        const recommendation = root.querySelector('[data-training-role="survey-recommendation"]');
        if (recommendation) recommendation.hidden = true;
        const button = root.querySelector('[data-training-role="build"]');
        if (button) button.disabled = true;
        try {
            const eraseSelectedMemories = root.querySelector('[data-training-role="erase"]')?.checked === true;
            const coverage = root.querySelector('[data-training-role="coverage"]')?.value || 'representative';
            const request = buildRequest(bands, portions, {
                coverage,
                eraseSelectedMemories,
            });
            lastRequest = request;
            resetConfirmations(root);
            const view = await requestPreview('POST', request, {
                erasePreview: eraseSelectedMemories,
            });
            if (!view) lastRequest = null;
            return view;
        } finally {
            if (button) button.disabled = false;
        }
    }

    function mergedResultPoints(results) {
        const returned = results || [];
        const planned = lastView?.points || [];
        if (!planned.length) return returned;
        return planned.map(planPoint => {
            const result = returned.find(candidate =>
                candidate.sequence === planPoint.sequence
                || (planPoint.frequencyMhz !== null && candidate.frequencyMhz !== null
                    && Math.abs(planPoint.frequencyMhz - candidate.frequencyMhz) < 0.0005));
            if (!result) {
                if (!planPoint.eligible) return planPoint;
                return {
                    ...planPoint,
                    resultStatus: 'not-attempted',
                    status: activeJob?.terminal ? 'Not attempted — run stopped earlier' : 'Pending',
                };
            }
            return {
                ...planPoint,
                ...result,
                band: result.band === '—' ? planPoint.band : result.band,
                flex: result.flex === '—' ? planPoint.flex : result.flex,
                kat: result.kat === '—' ? planPoint.kat : result.kat,
                frequency: result.frequency === '—' ? planPoint.frequency : result.frequency,
                frequencyMhz: result.frequencyMhz ?? planPoint.frequencyMhz,
            };
        });
    }

    function normalizeHistoryProfiles(payload) {
        const records = Array.isArray(payload?.records) ? payload.records : [];
        const normalized = records.map((record, index) => {
            const details = record?.details && typeof record.details === 'object' ? record.details : {};
            const completedAt = Date.parse(record?.completed_at || details.finished_at || '');
            const frequencyMhz = numericOrNull(record?.frequency_hz) === null
                ? numericOrNull(details?.route?.frequency_mhz)
                : Number(record.frequency_hz) / 1_000_000;
            const routeId = String(record?.route_id || details.route_id || '');
            const band = String(details?.route?.band || routeId.split('-flex-')[0] || '—');
            const operation = String(details.operation || details.kind || '').includes('survey') ? 'survey' : 'train';
            return {
                index,
                jobId: String(details.training_job_id || ''),
                completedAt: Number.isFinite(completedAt) ? completedAt : 0,
                operation,
                point: normalizePoint({
                    sequence: index + 1,
                    band,
                    frequency_mhz: frequencyMhz,
                    swr_before: record?.swr_before,
                    swr_after: record?.swr_after,
                    status: operation === 'survey' ? 'survey history' : String(record?.outcome || 'history'),
                    eligible: true,
                }, index),
            };
        }).filter(item => item.completedAt > 0 && item.point.frequencyMhz !== null);
        normalized.sort((a, b) => a.completedAt - b.completedAt);

        const profiles = [];
        normalized.forEach(item => {
            let profile = item.jobId
                ? profiles.find(candidate => candidate.key === `job:${item.jobId}`)
                : null;
            if (!profile && !item.jobId) {
                const previous = profiles.at(-1);
                if (previous?.legacy && previous.operation === item.operation
                    && item.completedAt - previous.completedAt <= 10 * 60 * 1000) profile = previous;
            }
            if (!profile) {
                profile = {
                    key: item.jobId ? `job:${item.jobId}` : `legacy:${item.completedAt}`,
                    jobId: item.jobId,
                    legacy: !item.jobId,
                    operation: item.operation,
                    completedAt: item.completedAt,
                    points: [],
                };
                profiles.push(profile);
            }
            profile.completedAt = Math.max(profile.completedAt, item.completedAt);
            profile.points.push(item.point);
        });
        return profiles.sort((a, b) => b.completedAt - a.completedAt).map(profile => {
            const bands = [...new Set(profile.points.map(point => point.band))].join(', ');
            const timestamp = new Date(profile.completedAt).toLocaleString();
            return {
                ...profile,
                label: `${timestamp} · ${profile.operation === 'survey' ? 'SWR survey' : 'Training'} · ${bands}`,
            };
        });
    }

    function populateHistorySelect(root) {
        const select = root.querySelector('[data-training-role="history-profile"]');
        if (!select) return;
        const selected = select.value || 'live';
        const live = document.createElement('option');
        live.value = 'live';
        live.textContent = 'Current plan / latest run';
        select.replaceChildren(live, ...historyProfiles.map(profile => {
            const option = document.createElement('option');
            option.value = profile.key;
            option.textContent = profile.label;
            return option;
        }));
        select.value = historyProfiles.some(profile => profile.key === selected) ? selected : 'live';
    }

    function renderSelectedHistory(root) {
        const select = root.querySelector('[data-training-role="history-profile"]');
        const profile = historyProfiles.find(item => item.key === select?.value);
        if (!profile) {
            renderPlot(root, currentResultPoints.length ? currentResultPoints : (lastView?.plotPoints || lastView?.points || []));
            return;
        }
        renderPlot(root, profile.points);
        setText(root, '[data-training-role="message"]', `Historical ${profile.operation === 'survey' ? 'SWR survey' : 'training'} profile: ${profile.label}.`);
    }

    async function loadProfileHistory() {
        const root = document.getElementById('station-training-preview');
        if (!root) return [];
        const refresh = root.querySelector('[data-training-role="history-refresh"]');
        if (refresh) refresh.disabled = true;
        try {
            const start = new Date(Date.now() - 31 * 24 * 60 * 60 * 1000).toISOString();
            const response = await fetch(`${TUNES_ENDPOINT}?start=${encodeURIComponent(start)}&limit=1000`, DEFAULT_FETCH_OPTIONS);
            const payload = await responseJson(response);
            historyProfiles = normalizeHistoryProfiles(payload);
            populateHistorySelect(root);
            return historyProfiles;
        } catch (error) {
            historyProfiles = [];
            populateHistorySelect(root);
            return [];
        } finally {
            if (refresh) refresh.disabled = false;
        }
    }

    function surveyThreshold(root) {
        const value = Number(root.querySelector('[data-training-role="survey-threshold"]')?.value);
        return Number.isFinite(value) ? Math.max(1.1, Math.min(2.9, value)) : 1.5;
    }

    function renderSurveyRecommendation(root, job) {
        const panel = root.querySelector('[data-training-role="survey-recommendation"]');
        const text = root.querySelector('[data-training-role="survey-recommendation-text"]');
        const button = root.querySelector('[data-training-role="train-recommended"]');
        const visible = Boolean(job?.terminal && job.operation === 'survey' && job.status === 'succeeded');
        if (!panel) return;
        panel.hidden = !visible;
        if (!visible) return;
        const threshold = surveyThreshold(root);
        const candidates = job.results.filter(point => point.swrBefore !== null && point.swrBefore > threshold);
        if (text) text.textContent = candidates.length
            ? `${candidates.length} of ${job.results.length} measured point(s) are above ${threshold.toFixed(2)} SWR.`
            : `All ${job.results.length} measured point(s) are at or below ${threshold.toFixed(2)} SWR.`;
        if (button) button.disabled = candidates.length === 0;
    }

    async function buildRecommendedTrainingPlan() {
        const root = document.getElementById('station-training-preview');
        if (!root || activeJob?.operation !== 'survey' || !activeJob.terminal) return null;
        const threshold = surveyThreshold(root);
        const candidates = activeJob.results.filter(point => point.swrBefore !== null && point.swrBefore > threshold);
        if (!candidates.length) return null;
        const frequencyPoints = {};
        candidates.forEach(point => {
            if (!frequencyPoints[point.band]) frequencyPoints[point.band] = [];
            frequencyPoints[point.band].push(point.frequencyMhz);
        });
        activeJob = null;
        currentResultPoints = [];
        clearTimeout(pollTimer);
        const recommendation = root.querySelector('[data-training-role="survey-recommendation"]');
        if (recommendation) recommendation.hidden = true;
        const historySelect = root.querySelector('[data-training-role="history-profile"]');
        if (historySelect) historySelect.value = 'live';
        lastRequest = {
            bands: Object.keys(frequencyPoints),
            portions: [],
            coverage: 'representative',
            erase_selected_memories: false,
            frequency_points_mhz: frequencyPoints,
        };
        resetConfirmations(root);
        const view = await requestPreview('POST', lastRequest);
        if (view) setExecutionMessage(root, `Follow-up plan contains only ${candidates.length} point(s) above ${threshold.toFixed(2)} SWR. Review and confirm before training.`, 'warning');
        return view;
    }

    function renderDiagnostics(root, job) {
        const details = root.querySelector('[data-training-role="diagnostics"]');
        const summary = root.querySelector('[data-training-role="diagnostics-summary"]');
        const body = root.querySelector('[data-training-role="diagnostics-body"]');
        if (!details || !summary || !body) return;
        if (!job) {
            details.hidden = true;
            body.textContent = '';
            return;
        }
        const lines = [
            `Job ${job.id || 'unknown'} · ${job.status}`,
            ...job.events.map(event => {
                const point = event.pointSequence ? ` point=${event.pointSequence}` : '';
                const frequency = event.frequencyMhz ? ` frequency=${event.frequencyMhz.toFixed(3)}MHz` : '';
                const attempt = event.attempt ? ` attempt=${event.attempt}` : '';
                const duration = event.durationMs !== null ? ` duration=${event.durationMs}ms` : '';
                const error = event.error ? ` error=${event.error}` : '';
                return `${event.sequence}. ${event.event}${point}${frequency}${attempt}${duration}${error}`;
            }),
        ];
        if (job.error) lines.push(`Failure ${job.error.code}: ${job.error.message}`);
        summary.textContent = `${job.operation === 'survey' ? 'Survey' : 'Training'} diagnostics · ${job.events.length} event${job.events.length === 1 ? '' : 's'} · job ${job.id.slice(0, 8)}`;
        body.textContent = lines.join('\n');
        details.hidden = false;
    }

    function renderJob(root, job) {
        activeJob = job;
        if (job && !job.terminal) clearTimeout(preflightTimer);
        const state = root.querySelector('[data-training-role="job-state"]');
        const badge = root.querySelector('[data-training-role="mode-badge"]');
        const cancel = root.querySelector('[data-training-role="cancel"]');
        const progressWrap = root.querySelector('[data-training-role="progress-wrap"]');
        const progress = root.querySelector('[data-training-role="progress"]');
        const count = root.querySelector('[data-training-role="progress-count"]');
        const label = root.querySelector('[data-training-role="progress-label"]');
        const running = job && !job.terminal;
        const operationLabel = job?.operation === 'survey' ? 'SWR survey' : 'Training';
        if (state) state.textContent = job ? job.status.replaceAll('_', ' ') : 'Not running';
        if (badge) badge.textContent = running
            ? `${operationLabel} active`
            : (job?.terminal ? `${operationLabel} ${job.status}` : 'Plan first');
        if (cancel) cancel.hidden = !running;
        if (progressWrap) progressWrap.hidden = !job;
        if (progress && job) {
            progress.max = Math.max(1, job.total);
            progress.value = Math.min(job.processed, progress.max);
        }
        if (count && job) {
            const outcome = job.failedPoints ? ` · ${job.failedPoints} failed` : '';
            count.textContent = `${job.processed} / ${job.total || '—'}${outcome}`;
        }
        if (label && job) {
            label.textContent = job.currentFrequencyMhz
                ? `${job.status.replaceAll('_', ' ')} · ${job.currentFrequencyMhz.toFixed(3)} MHz`
                : job.status.replaceAll('_', ' ');
        }
        if (job) {
            const points = mergedResultPoints(job.results);
            currentResultPoints = points;
            render({
                ...(lastView || {}),
                state: ['failed', 'error', 'aborted'].includes(job.status) ? 'invalid' : 'ready',
                points,
                plotPoints: points,
                pointCount: lastView?.pointCount ?? job.requestedTotal ?? points.length,
                eligible: lastView?.eligible ?? job.total ?? points.filter(point => point.eligible).length,
                blocked: lastView?.blocked || 0,
                message: job.message || `${operationLabel} ${job.status}: ${job.processed} of ${job.total || points.length} point(s) processed.`,
                executionAvailable: lastView?.executionAvailable === true,
                executionBlockers: lastView?.executionBlockers || [],
                requiredConfirmation: lastView?.requiredConfirmation || '',
            }, { erasePreview: lastRequest?.erase_selected_memories === true, jobResults: true });
        }
        renderDiagnostics(root, job);
        renderSurveyRecommendation(root, job);
        const failure = job?.error
            ? `${job.error.code}: ${job.error.message}`
            : (job?.blockers.length ? job.blockers.join('; ') : job?.message);
        if (!job) setExecutionMessage(root, 'No active station job.', 'info');
        else if (job.status === 'completed' || job.status === 'succeeded') {
            setExecutionMessage(root, job.message || `${operationLabel} completed. Review every returned SWR result.`, 'success');
            loadProfileHistory();
        } else if (job.status === 'completed_with_failures') {
            setExecutionMessage(root, job.message || `${operationLabel} finished with ${job.failedPoints} failed point(s); all later safe points were still attempted.`, 'warning');
            loadProfileHistory();
        } else if (job.status === 'cancelled' || job.status === 'canceled') setExecutionMessage(root, job.message || `${operationLabel} was cancelled. The radio should be unkeyed; verify station state.`, 'warning');
        else if (job.status === 'failed' || job.status === 'error' || job.status === 'aborted') setExecutionMessage(root, `${operationLabel} ${job.status}: ${failure || 'the backend did not provide a reason.'}`, 'error');
        else setExecutionMessage(root, job.message || `${operationLabel} is active and producing RF. Monitor the station; use Cancel to stop.`, 'warning');
        updateStartEnabled(root);
    }

    function schedulePoll(jobId) {
        clearTimeout(pollTimer);
        if (!jobId || activeJob?.terminal) return;
        pollTimer = setTimeout(() => pollJob(jobId), 1000);
    }

    async function pollJob(jobId) {
        const root = document.getElementById('station-training-preview');
        if (!root || !jobId) return null;
        try {
            const response = await fetch(`${JOBS_ENDPOINT}/${encodeURIComponent(jobId)}`, DEFAULT_FETCH_OPTIONS);
            const job = normalizeJob(await responseJson(response));
            if (!job) throw new Error('backend returned no training job');
            renderJob(root, job);
            schedulePoll(job.id);
            return job;
        } catch (error) {
            setExecutionMessage(root, `Training status update failed: ${error?.message || 'unknown error'}. Treat station state as unknown and verify hardware before continuing.`, 'error');
            clearTimeout(pollTimer);
            return null;
        }
    }

    async function loadActiveJob() {
        const root = document.getElementById('station-training-preview');
        if (!root) return null;
        try {
            const response = await fetch(ACTIVE_JOB_ENDPOINT, DEFAULT_FETCH_OPTIONS);
            const payload = await responseJson(response);
            const source = payload?.training_job ?? payload?.active_job ?? payload?.job ?? (payload?.active === false ? null : payload);
            const job = normalizeJob(source);
            if (job) {
                renderJob(root, job);
                schedulePoll(job.id);
            } else if (!activeJob) {
                const state = root.querySelector('[data-training-role="job-state"]');
                if (state) state.textContent = 'Not running';
            }
            return job;
        } catch (error) {
            setExecutionMessage(root, `Could not check for an active training job: ${error?.message || 'unknown error'}.`, 'error');
            return null;
        }
    }

    async function startStationJob(operation = 'train') {
        const root = document.getElementById('station-training-preview');
        if (!root) return null;
        const normalizedOperation = operation === 'survey' ? 'survey' : 'train';
        const operationLabel = normalizedOperation === 'survey' ? 'SWR survey' : 'Training';
        if (!lastRequest || !lastView?.executionAvailable) {
            setExecutionMessage(root, `${operationLabel} blocked: build an executable plan and resolve every prerequisite first.`, 'error');
            updateStartEnabled(root);
            return null;
        }
        if (!confirmationsComplete(root)) {
            setExecutionMessage(root, `${operationLabel} blocked: complete every safety checkbox.`, 'error');
            updateStartEnabled(root);
            return null;
        }
        if (normalizedOperation === 'survey' && lastRequest.erase_selected_memories === true) {
            setExecutionMessage(root, 'SWR survey blocked: memory erase is not allowed during a measurement-only run.', 'error');
            return null;
        }
        const action = root.querySelector(`[data-training-role="${normalizedOperation === 'survey' ? 'survey' : 'start'}"]`);
        if (action) action.disabled = true;
        setExecutionMessage(root, `Requesting the guarded ${operationLabel.toLowerCase()} job… no job is assumed active until the backend confirms it.`, 'warning');
        try {
            const confirmations = {
                ...confirmationState(root),
                operation: normalizedOperation,
                operatorConfirmed: true,
            };
            const response = await fetch(JOBS_ENDPOINT, {
                method: 'POST',
                cache: 'no-store',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(buildStartPayload(lastRequest, confirmations)),
            });
            const job = normalizeJob(await responseJson(response));
            if (!job || !job.id) throw new Error('backend did not return a station job id');
            renderJob(root, job);
            schedulePoll(job.id);
            return job;
        } catch (error) {
            setExecutionMessage(root, `${operationLabel} did not start: ${error?.message || 'unknown error'}. No execution is assumed; verify station state before retrying.`, 'error');
            updateStartEnabled(root);
            return null;
        }
    }

    function closeRfConfirmation(accepted) {
        const root = document.getElementById('station-training-preview');
        const dialog = root?.querySelector('[data-training-role="rf-confirm-dialog"]');
        const operation = pendingOperation;
        pendingOperation = null;
        if (dialog?.open) dialog.close();
        if (accepted && operation) return startStationJob(operation);
        return null;
    }

    function openRfConfirmation(operation = 'train') {
        const root = document.getElementById('station-training-preview');
        if (!root) return null;
        const normalizedOperation = operation === 'survey' ? 'survey' : 'train';
        if (!lastRequest || !lastView?.executionAvailable || !confirmationsComplete(root)) {
            updateStartEnabled(root);
            setExecutionMessage(root, 'RF action blocked: build an executable plan and complete every safety confirmation first.', 'error');
            return null;
        }
        const dialog = root.querySelector('[data-training-role="rf-confirm-dialog"]');
        const bands = (lastRequest.bands || []).join(', ');
        const verb = normalizedOperation === 'survey'
            ? 'measure SWR without tuning or storing KAT500 memory'
            : 'tune and store KAT500 memory';
        setText(root, '[data-training-role="rf-confirm-title"]', normalizedOperation === 'survey' ? 'Start SWR survey?' : 'Start ATU training?');
        const skipped = Number(lastView.blocked) || 0;
        const skippedNote = skipped ? ` ${skipped} policy-blocked point(s) will be skipped.` : '';
        setText(root, '[data-training-role="rf-confirm-summary"]', `This will produce low-power RF at ${lastView.eligible} eligible point(s) on ${bands}, using ${lastView.power}, to ${verb}.${skippedNote} Are you sure?`);
        pendingOperation = normalizedOperation;
        if (dialog && typeof dialog.showModal === 'function') {
            dialog.showModal();
            return null;
        }
        if (typeof window.confirm === 'function' && window.confirm('This action produces RF. Are you sure?')) {
            return closeRfConfirmation(true);
        }
        pendingOperation = null;
        return null;
    }

    function startTraining() {
        return openRfConfirmation('train');
    }

    async function cancelTraining() {
        const root = document.getElementById('station-training-preview');
        const jobId = activeJob?.id;
        if (!root || !jobId || activeJob.terminal) {
            if (root) setExecutionMessage(root, 'No active station job is available to cancel.', 'error');
            return null;
        }
        const cancel = root.querySelector('[data-training-role="cancel"]');
        if (cancel) cancel.disabled = true;
        setExecutionMessage(root, 'Cancellation requested. Continue monitoring until the backend confirms a terminal state.', 'warning');
        try {
            const response = await fetch(`${JOBS_ENDPOINT}/${encodeURIComponent(jobId)}/cancel`, {
                method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: '{}',
            });
            const job = normalizeJob(await responseJson(response));
            if (job) renderJob(root, job);
            if (job && !job.terminal) schedulePoll(job.id);
            return job;
        } catch (error) {
            setExecutionMessage(root, `Cancel request failed: ${error?.message || 'unknown error'}. Station job state is unknown; use the station emergency stop if RF continues.`, 'error');
            schedulePoll(jobId);
            return null;
        } finally {
            if (cancel) cancel.disabled = false;
        }
    }

    function bind(root) {
        if (!root || root.dataset.controlsBound === 'true') return;
        root.dataset.controlsBound = 'true';
        root.querySelector('[data-training-role="form"]')?.addEventListener('submit', buildPlan);
        root.querySelector('[data-training-role="start"]')?.addEventListener('click', startTraining);
        root.querySelector('[data-training-role="survey"]')?.addEventListener('click', () => openRfConfirmation('survey'));
        root.querySelector('[data-training-role="cancel"]')?.addEventListener('click', cancelTraining);
        root.querySelector('[data-training-role="rf-confirm-yes"]')?.addEventListener('click', () => closeRfConfirmation(true));
        root.querySelector('[data-training-role="rf-confirm-no"]')?.addEventListener('click', () => closeRfConfirmation(false));
        root.querySelector('[data-training-role="rf-confirm-dialog"]')?.addEventListener('cancel', () => { pendingOperation = null; });
        root.querySelector('[data-training-role="stop-digital"]')?.addEventListener('click', stopDigitalEngine);
        root.querySelector('[data-training-role="recheck"]')?.addEventListener('click', () => refreshSafetyStatus(true));
        ['approved-load', 'digital-inhibit', 'legal-operation', 'vendor-backup'].forEach(role => {
            const input = root.querySelector(`[data-training-role="${role}"]`);
            input?.addEventListener('input', () => updateStartEnabled(root));
            input?.addEventListener('change', () => updateStartEnabled(root));
        });
        root.querySelector('[data-training-role="erase"]')?.addEventListener('change', event => {
            root.dataset.erasePreview = event.currentTarget.checked ? 'true' : 'false';
            markPlanStale(root);
        });
        root.querySelectorAll('input[name="training-band"], input[name="training-portion"], [data-training-role="coverage"]')
            .forEach(input => input.addEventListener('change', () => markPlanStale(root)));
        root.querySelector('[data-training-role="history-profile"]')?.addEventListener('change', () => renderSelectedHistory(root));
        root.querySelector('[data-training-role="history-refresh"]')?.addEventListener('click', async () => {
            await loadProfileHistory();
            renderSelectedHistory(root);
        });
        root.querySelector('[data-training-role="survey-threshold"]')?.addEventListener('input', () => renderSurveyRecommendation(root, activeJob));
        root.querySelector('[data-training-role="train-recommended"]')?.addEventListener('click', buildRecommendedTrainingPlan);
        root.querySelector('[data-training-role="bands-all"]')?.addEventListener('click', () => {
            root.querySelectorAll('input[name="training-band"]').forEach(input => { input.checked = true; });
            markPlanStale(root);
        });
        root.querySelector('[data-training-role="bands-none"]')?.addEventListener('click', () => {
            root.querySelectorAll('input[name="training-band"]').forEach(input => { input.checked = false; });
            markPlanStale(root);
        });
        if (typeof window.addEventListener === 'function') {
            window.addEventListener('focus', () => refreshSafetyStatus(false));
        }
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') refreshSafetyStatus(false);
        });
    }

    async function refresh() {
        const root = document.getElementById('station-training-preview');
        if (!root) return null;
        bind(root);
        const bands = selection(root, 'training-band');
        const portions = selection(root, 'training-portion');
        const coverage = root.querySelector('[data-training-role="coverage"]')?.value || 'representative';
        lastRequest = buildRequest(bands, portions, { coverage });
        const view = await requestPreview('POST', lastRequest);
        await Promise.all([loadActiveJob(), loadProfileHistory()]);
        return view;
    }

    window.StationTrainingPreview = Object.freeze({
        ENDPOINT,
        JOBS_ENDPOINT,
        ACTIVE_JOB_ENDPOINT,
        TUNES_ENDPOINT,
        DIGITAL_STOP_ENDPOINT,
        BAND_FREQUENCIES,
        TARGET_SWR,
        ABORT_SWR,
        formatDuration,
        formatSWR,
        normalize,
        normalizeJob,
        buildRequest,
        buildStartPayload,
        buildPlotSeries,
        normalizeHistoryProfiles,
        render,
        buildPlan,
        startTraining,
        startStationJob,
        openRfConfirmation,
        cancelTraining,
        refreshSafetyStatus,
        stopDigitalEngine,
        loadActiveJob,
        refresh,
    });
    document.addEventListener('templates-loaded', refresh);
}());
