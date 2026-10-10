// Operator evidence preview for commissioning readiness. This module cannot apply or transmit.
(function () {
    'use strict';

    const ENDPOINT = '/api/station/commissioning/readiness';
    const MAX_ITEMS = 50;
    const MAX_TEXT = 240;
    const EVIDENCE_KEYS = Object.freeze([
        'physical_key_interrupt_verified',
        'antenna_routes_names_verified',
        'vendor_backups_captured',
        'dummy_load_or_approved_antenna_connected',
        'digital_engine_inhibit_verified',
    ]);

    function boundedText(value, fallback) {
        const candidate = typeof value === 'string'
            ? value
            : (typeof value?.message === 'string' ? value.message
                : (typeof value?.label === 'string' ? value.label
                    : (typeof value?.name === 'string' ? value.name : fallback)));
        return String(candidate || fallback).replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, MAX_TEXT);
    }

    function normalizeItems(value, fallback) {
        if (!Array.isArray(value)) return [];
        return value.slice(0, MAX_ITEMS).map(item => boundedText(item, fallback));
    }

    function normalizeReadiness(payload) {
        const source = payload?.readiness && typeof payload.readiness === 'object'
            ? payload.readiness
            : (payload && typeof payload === 'object' ? payload : {});
        const readyForReceiveOnly = source.ready_for_receive_only === true;
        const readyForLowPowerTest = source.ready_for_low_power_test === true;
        return {
            ready: readyForLowPowerTest || source.ready === true || source.readiness === true,
            readyForReceiveOnly,
            readyForLowPowerTest,
            commissioningEnabled: source.commissioning_enabled === true,
            disposition: boundedText(source.disposition, 'blocked'),
            previewOnly: source.read_only === true || source.preview_only !== false,
            blockers: normalizeItems(source.blockers, 'Unspecified blocker'),
            warnings: normalizeItems(source.warnings, 'Unspecified warning'),
            checks: normalizeItems(source.checks, 'Unspecified check'),
        };
    }

    function normalizeEvidence(source) {
        const input = source && typeof source === 'object' ? source : {};
        return Object.fromEntries(EVIDENCE_KEYS.map(key => [key, input[key] === true]));
    }

    async function responsePayload(response) {
        try {
            return await response.json();
        } catch (_) {
            return {};
        }
    }

    async function requestReadiness(fetchImpl = fetch) {
        const response = await fetchImpl(ENDPOINT, {
            method: 'GET',
            cache: 'no-store',
            headers: { Accept: 'application/json' },
        });
        const payload = await responsePayload(response);
        if (!response.ok) throw new Error(boundedText(payload.detail, `Readiness request failed with HTTP ${response.status}`));
        return normalizeReadiness(payload);
    }

    async function evaluateEvidence(evidence, fetchImpl = fetch) {
        const response = await fetchImpl(ENDPOINT, {
            method: 'POST',
            headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify(normalizeEvidence(evidence)),
        });
        const payload = await responsePayload(response);
        if (!response.ok) throw new Error(boundedText(payload.detail, `Evidence evaluation failed with HTTP ${response.status}`));
        return normalizeReadiness(payload);
    }

    function renderList(root, category, items) {
        const list = root.querySelector(`[data-station-commissioning-list="${category}"]`);
        const count = root.querySelector(`[data-station-commissioning-count="${category}"]`);
        if (count) count.textContent = String(items.length);
        if (!list) return;
        list.replaceChildren();
        (items.length ? items : ['None reported.']).forEach(text => {
            const item = document.createElement('li');
            item.textContent = text;
            list.appendChild(item);
        });
    }

    function render(root, report) {
        const normalized = normalizeReadiness(report);
        renderList(root, 'blockers', normalized.blockers);
        renderList(root, 'warnings', normalized.warnings);
        renderList(root, 'checks', normalized.checks);
        const status = root.querySelector('[data-station-commissioning="status"]');
        if (!status) return;
        status.dataset.state = normalized.commissioningEnabled
            ? 'error'
            : (normalized.readyForLowPowerTest ? 'clear' : (normalized.readyForReceiveOnly ? 'review' : 'blocked'));
        if (normalized.commissioningEnabled) {
            status.textContent = 'Invalid readiness response: evaluation must never enable commissioning. Controls remain locked.';
        } else if (normalized.readyForLowPowerTest) {
            status.textContent = 'Ready for operator review of a supervised low-power test. Commissioning remains disabled; nothing was applied or transmitted.';
        } else if (normalized.readyForReceiveOnly) {
            status.textContent = 'Cached automated checks support receive-only validation; low-power blockers or evidence remain. Commissioning remains disabled.';
        } else {
            status.textContent = `${normalized.blockers.length} blocker(s) prevent receive-only readiness. Evaluation only—no commissioning, apply, or transmit occurred.`;
        }
    }

    function renderError(root, error) {
        const status = root.querySelector('[data-station-commissioning="status"]');
        if (!status) return;
        status.dataset.state = 'error';
        status.textContent = `${boundedText(error?.message, 'Readiness evaluation failed.')} No commissioning, apply, or transmit occurred.`;
    }

    function evidenceFrom(root) {
        const values = {};
        EVIDENCE_KEYS.forEach(key => {
            values[key] = root.querySelector(`[data-evidence-key="${key}"]`)?.checked === true;
        });
        return normalizeEvidence(values);
    }

    function setBusy(root, busy) {
        const button = root.querySelector('[data-station-commissioning="evaluate"]');
        if (button) button.disabled = busy;
        root.setAttribute('aria-busy', String(busy));
    }

    async function refresh(root) {
        setBusy(root, true);
        try {
            render(root, await requestReadiness());
        } catch (error) {
            renderError(root, error);
        } finally {
            setBusy(root, false);
        }
    }

    async function submit(root) {
        setBusy(root, true);
        try {
            render(root, await evaluateEvidence(evidenceFrom(root)));
        } catch (error) {
            renderError(root, error);
        } finally {
            setBusy(root, false);
        }
    }

    function start() {
        const root = document.getElementById('station-commissioning-panel');
        if (!root || root.dataset.bound === 'true') return;
        root.dataset.bound = 'true';
        root.querySelector('[data-station-commissioning="form"]')?.addEventListener('submit', event => {
            event.preventDefault();
            submit(root);
        });
        refresh(root);
    }

    window.StationCommissioning = {
        ENDPOINT,
        EVIDENCE_KEYS,
        evaluateEvidence,
        normalizeEvidence,
        normalizeReadiness,
        requestReadiness,
        start,
    };

    if (typeof document !== 'undefined') document.addEventListener('vue-mounted', start, { once: true });
}());
