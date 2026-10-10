// Station-level workflow UI. Mutations are exclusively coordinator-authorized.
(function () {
    'use strict';

    const POLL_MS = 3000;
    const MISSING_ENDPOINT_POLL_MS = 30000;
    const ACTIONS = Object.freeze(['prepare-route', 'standby', 'operate', 'tune', 'cancel']);
    const MAINTENANCE_ACTIONS = Object.freeze(['enter', 'exit']);
    const DEESCALATION_ACTIONS = new Set(['standby', 'cancel']);
    const ACTION_LABELS = Object.freeze({
        'prepare-route': 'Prepare Route',
        standby: 'Amplifier Standby',
        operate: 'Amplifier Operate',
        tune: 'Tune',
        cancel: 'Cancel',
    });
    const TERMINAL_TRANSACTION_STATES = new Set(['idle', 'complete', 'completed', 'done', 'succeeded', 'cancelled', 'canceled', 'failed', 'error']);

    let timer = null;
    let started = false;
    let requestInFlight = false;
    let actionInFlight = null;
    let endpointAvailable = false;
    let latestState = null;
    let latestError = null;

    function textValue(value, fallback = '') {
        if (value === undefined || value === null || value === '') return fallback;
        return String(value);
    }

    function issueText(issue) {
        if (typeof issue === 'string') return issue;
        return issue?.message || issue?.detail || issue?.reason || issue?.code || '';
    }

    function routeLabel(route) {
        if (typeof route === 'string') return route;
        return route?.route_label || route?.label || route?.name || route?.id || 'No route selected';
    }

    function normalizeProgress(transaction) {
        const explicitPercent = Number(transaction?.progress_percent ?? transaction?.percent);
        if (Number.isFinite(explicitPercent)) return Math.max(0, Math.min(100, Math.round(explicitPercent)));
        const candidate = transaction?.progress;
        const numeric = Number(candidate);
        if (!Number.isFinite(numeric)) return 0;
        const percent = numeric > 0 && numeric <= 1 ? numeric * 100 : numeric;
        return Math.max(0, Math.min(100, Math.round(percent)));
    }

    function normalizeState(payload) {
        const source = payload?.station_state
            || payload?.station
            || payload?.data
            || (payload?.state && typeof payload.state === 'object' ? payload.state : null)
            || payload
            || {};
        const transaction = source.active_transaction || source.transaction || source.tune_transaction || null;
        const rawIssues = [
            ...(Array.isArray(source.issues) ? source.issues : []),
            ...(Array.isArray(source.warnings) ? source.warnings : []),
        ];
        const issues = [...new Set(rawIssues.map(issueText).filter(Boolean))];
        const alarms = source?.alarms && Array.isArray(source.alarms.items)
            ? source.alarms.items.filter(alarm => alarm?.active !== false && alarm?.status !== 'cleared')
            : [];
        const allowedActions = Array.isArray(source.allowed_actions)
            ? source.allowed_actions.filter(action => typeof action === 'string')
            : [];
        return {
            commissioned: source.commissioned === true,
            maintenance: source.maintenance === true,
            maintenanceEnterAvailable: source.maintenance_enter_available === true,
            allowedActions,
            coordinatorState: textValue(
                source.coordinator_state || (typeof source.state === 'string' ? source.state : null) || source.status,
                'unknown',
            ).toLowerCase(),
            selectedRoute: source.selected_route || source.route || source.route_profile || null,
            selectedRouteLabel: routeLabel(source.selected_route || source.route || source.route_profile),
            issues,
            alarms,
            alarmCount: Number(source?.alarms?.active_count ?? alarms.length) || 0,
            transaction: transaction ? {
                id: transaction.id || transaction.transaction_id || null,
                action: textValue(transaction.action || transaction.type || transaction.kind, 'Transaction'),
                state: textValue(transaction.state || transaction.status, 'unknown').toLowerCase(),
                detail: textValue(transaction.detail || transaction.message || transaction.step, 'Transaction is in progress.'),
                progress: normalizeProgress(transaction),
            } : null,
            updatedAt: source.updated_at || null,
        };
    }

    function actionAllowed(state, action) {
        return ACTIONS.includes(action)
            && Array.isArray(state.allowedActions)
            && state.allowedActions.includes(action)
            && (state?.commissioned === true || DEESCALATION_ACTIONS.has(action));
    }

    function displayState(state, available) {
        if (!available) return 'unavailable';
        if (state?.maintenance === true) return 'maintenance';
        if (state?.commissioned !== true) return 'locked';
        const value = String(state.coordinatorState || '').toLowerCase();
        if (['ready', 'idle', 'receive', 'prepared'].includes(value)) return 'ready';
        if (['preparing', 'switching', 'tuning', 'cancelling', 'canceling', 'active', 'busy'].includes(value)) return 'active';
        if (['warning', 'fault', 'error', 'unsafe', 'blocked'].includes(value)) return 'warning';
        return 'locked';
    }

    function buildViewModel(state, options = {}) {
        const available = options.endpointAvailable === true;
        const busy = Boolean(options.actionInFlight);
        const display = displayState(state, available);
        const transaction = state?.transaction;
        const transactionActive = Boolean(transaction && !TERMINAL_TRANSACTION_STATES.has(transaction.state));
        const issues = [
            ...(state?.issues || []),
            ...((state?.alarms || []).map(alarm => issueText(alarm)).filter(Boolean)),
            ...(options.error ? [options.error] : []),
        ];
        if (!available && !issues.length) issues.push('Coordinator endpoint is unavailable; monitoring remains read-only.');
        return {
            state: display,
            stateLabel: display === 'unavailable' ? 'Unavailable' : display === 'locked' ? 'Locked' : display === 'active' ? 'In progress' : display === 'warning' ? 'Attention' : 'Ready',
            coordinatorLabel: available ? textValue(state?.coordinatorState, 'Unknown') : 'Unavailable',
            routeLabel: available ? textValue(state?.selectedRouteLabel, 'No route selected') : 'No coordinator state',
            authorizationLabel: state?.commissioned === true ? 'Commissioned' : 'Locked',
            commissioned: state?.commissioned === true,
            lockText: state?.commissioned === true
                ? (state?.maintenance === true
                    ? 'Maintenance Mode active. Elecraft serial ports are released; all transmit and route controls are locked.'
                    : 'Coordinator commissioned. Actions still require explicit backend authorization.')
                : 'Commissioning lock active. Only backend-authorized Standby or Cancel safety actions can run.',
            issues,
            alarmCount: state?.alarmCount || 0,
            actionEnabled: Object.fromEntries(ACTIONS.map(action => [
                action,
                available && !busy && actionAllowed(state, action),
            ])),
            actionTitles: Object.fromEntries(ACTIONS.map(action => {
                let title = `${ACTION_LABELS[action]} is authorized by the station coordinator`;
                if (!available) title = 'Coordinator endpoint is unavailable';
                else if (state?.commissioned !== true && !DEESCALATION_ACTIONS.has(action)) title = 'Commissioning lock is active';
                else if (!state.allowedActions.includes(action)) title = 'Backend has not allowed this action';
                else if (busy) title = `Waiting for ${ACTION_LABELS[options.actionInFlight] || options.actionInFlight}`;
                return [action, title];
            })),
            maintenanceActionEnabled: {
                enter: available && !busy && state?.maintenance !== true && state?.maintenanceEnterAvailable === true,
                exit: available && !busy && state?.maintenance === true,
            },
            transaction: transactionActive ? {
                label: `${ACTION_LABELS[transaction.action] || transaction.action}${transaction.id ? ` · ${transaction.id}` : ''}`,
                state: transaction.state,
                detail: transaction.detail,
                progress: transaction.progress,
            } : {
                label: transaction ? `${ACTION_LABELS[transaction.action] || transaction.action}${transaction.id ? ` · ${transaction.id}` : ''}` : 'No active transaction',
                state: transaction?.state || 'idle',
                detail: transaction?.detail || 'Coordinator progress will appear here.',
                progress: transaction?.progress || 0,
            },
        };
    }

    async function responsePayload(response) {
        try {
            return await response.json();
        } catch (_) {
            return {};
        }
    }

    async function postAction(action, state, fetchImpl = fetch) {
        if (!ACTIONS.includes(action)) throw new Error(`Unknown station action: ${action}`);
        if (!actionAllowed(state, action)) {
            return { sent: false, reason: state?.commissioned === true ? 'action-not-allowed' : 'commissioning-lock' };
        }
        const response = await fetchImpl(`/api/station/actions/${action}`, {
            method: 'POST',
            headers: { Accept: 'application/json' },
        });
        const payload = await responsePayload(response);
        if (!response.ok) throw new Error(payload.detail || payload.message || `Station action failed with HTTP ${response.status}`);
        return { sent: true, payload };
    }

    async function postMaintenance(action, state, fetchImpl = fetch) {
        if (!MAINTENANCE_ACTIONS.includes(action)) throw new Error(`Unknown maintenance action: ${action}`);
        const allowed = action === 'enter'
            ? state?.maintenance !== true && state?.maintenanceEnterAvailable === true
            : state?.maintenance === true;
        if (!allowed) return { sent: false, reason: 'maintenance-action-not-allowed' };
        const response = await fetchImpl(`/api/station/maintenance/${action}`, {
            method: 'POST',
            headers: { Accept: 'application/json' },
        });
        const payload = await responsePayload(response);
        if (!response.ok) throw new Error(payload.detail || payload.message || `Maintenance action failed with HTTP ${response.status}`);
        return { sent: true, payload };
    }

    function setText(root, selector, value) {
        const element = root.querySelector(selector);
        if (element) element.textContent = value;
    }

    function renderIssues(root, issues) {
        const list = root.querySelector('[data-workflow-role="issues"]');
        if (!list) return;
        list.replaceChildren();
        (issues.length ? issues : ['No coordinator issues reported.']).forEach(issue => {
            const item = document.createElement('li');
            item.textContent = issue;
            list.appendChild(item);
        });
    }

    function render() {
        const root = document.getElementById('station-workflow-panel');
        if (!root) return;
        const view = buildViewModel(latestState, { endpointAvailable, actionInFlight, error: latestError });
        root.dataset.state = view.state;
        root.dataset.commissioned = String(view.commissioned);
        const badge = root.querySelector('[data-workflow-role="state"]');
        if (badge) {
            badge.textContent = view.stateLabel;
            badge.className = `station-workflow-state state-${view.state}`;
        }
        setText(root, '[data-workflow-role="route"]', view.routeLabel);
        setText(root, '[data-workflow-role="coordinator"]', view.coordinatorLabel);
        setText(root, '[data-workflow-role="authorization"]', view.authorizationLabel);
        setText(root, '[data-workflow-role="alarm-count"]', String(view.alarmCount));
        setText(root, '[data-workflow-role="lock"]', view.lockText);
        setText(root, '[data-workflow-role="transaction-label"]', view.transaction.label);
        setText(root, '[data-workflow-role="transaction-state"]', view.transaction.state);
        setText(root, '[data-workflow-role="transaction-detail"]', view.transaction.detail);
        const progress = root.querySelector('[data-workflow-role="transaction-progress"]');
        if (progress) {
            progress.value = view.transaction.progress;
            progress.textContent = `${view.transaction.progress}%`;
        }
        ACTIONS.forEach(action => {
            const button = root.querySelector(`[data-station-action="${action}"]`);
            if (!button) return;
            button.disabled = !view.actionEnabled[action];
            button.title = view.actionTitles[action];
            button.setAttribute('aria-disabled', String(button.disabled));
        });
        MAINTENANCE_ACTIONS.forEach(action => {
            const button = root.querySelector(`[data-station-maintenance="${action}"]`);
            if (!button) return;
            button.disabled = !view.maintenanceActionEnabled[action];
            button.setAttribute('aria-disabled', String(button.disabled));
        });
        renderIssues(root, view.issues);
    }

    async function fetchState() {
        if (requestInFlight) return;
        requestInFlight = true;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 4000);
        try {
            const response = await fetch('/api/station/state', { cache: 'no-store', signal: controller.signal });
            if (response.status === 404 || response.status === 405 || response.status === 501) {
                endpointAvailable = false;
                latestState = null;
                latestError = 'Coordinator endpoint is not available; controls remain read-only.';
                return;
            }
            const payload = await responsePayload(response);
            if (!response.ok) throw new Error(payload.detail || payload.message || `Coordinator state HTTP ${response.status}`);
            latestState = normalizeState(payload);
            endpointAvailable = true;
            latestError = null;
        } catch (error) {
            endpointAvailable = false;
            latestError = error?.name === 'AbortError' ? 'Coordinator state request timed out; controls remain locked.' : (error?.message || 'Coordinator state is unavailable.');
        } finally {
            clearTimeout(timeout);
            requestInFlight = false;
            render();
        }
    }

    async function handleAction(action) {
        if (actionInFlight || !actionAllowed(latestState, action)) return;
        actionInFlight = action;
        latestError = null;
        render();
        try {
            const result = await postAction(action, latestState);
            if (result.sent) {
                const responseState = normalizeState(result.payload);
                if (responseState.coordinatorState !== 'unknown' || responseState.transaction) latestState = responseState;
            }
        } catch (error) {
            latestError = error?.message || `${ACTION_LABELS[action]} failed`;
        } finally {
            actionInFlight = null;
            render();
            await fetchState();
        }
    }

    async function handleMaintenance(action) {
        if (actionInFlight) return;
        if (action === 'enter' && !window.confirm(
            'Enter Maintenance Mode? OM0RX will prove FLEX receive and KPA500 standby, then release COM ports for the official Elecraft utilities. All station transmit and route controls will remain locked.',
        )) return;
        actionInFlight = `maintenance-${action}`;
        latestError = null;
        render();
        try {
            const result = await postMaintenance(action, latestState);
            if (result.sent) latestState = normalizeState(result.payload);
        } catch (error) {
            latestError = error?.message || `Maintenance ${action} failed`;
        } finally {
            actionInFlight = null;
            render();
            await fetchState();
        }
    }

    function bindActions() {
        const root = document.getElementById('station-workflow-panel');
        if (!root || root.dataset.actionsBound === 'true') return;
        root.dataset.actionsBound = 'true';
        root.addEventListener('click', event => {
            const button = event.target.closest('[data-station-action]');
            if (button && !button.disabled) {
                handleAction(button.dataset.stationAction);
                return;
            }
            const maintenanceButton = event.target.closest('[data-station-maintenance]');
            if (maintenanceButton && !maintenanceButton.disabled) {
                handleMaintenance(maintenanceButton.dataset.stationMaintenance);
            }
        });
    }

    function start() {
        if (started) return;
        started = true;
        bindActions();
        render();
        fetchState().finally(scheduleNextFetch);
    }

    function scheduleNextFetch() {
        if (!started) return;
        clearTimeout(timer);
        const delay = endpointAvailable ? POLL_MS : MISSING_ENDPOINT_POLL_MS;
        timer = setTimeout(async () => {
            timer = null;
            await fetchState();
            scheduleNextFetch();
        }, delay);
    }

    function stop() {
        started = false;
        clearTimeout(timer);
        timer = null;
    }

    window.StationWorkflow = {
        ACTIONS,
        actionAllowed,
        buildViewModel,
        normalizeProgress,
        normalizeState,
        postAction,
        postMaintenance,
        start,
        stop,
    };

    if (typeof document !== 'undefined') {
        document.addEventListener('vue-mounted', start, { once: true });
        window.addEventListener('beforeunload', stop, { once: true });
    }
}());
