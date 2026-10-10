// Compact, read-only history view for persisted station telemetry.
(function () {
    'use strict';

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const POLL_MS = 30000;
    const METRICS = Object.freeze({
        'kpa.output_power_w': { label: 'KPA output', unit: 'W', digits: 0, color: '#38bdf8', floor: 0 },
        'kpa.swr': { label: 'KPA SWR', unit: '', digits: 2, color: '#22c55e', floor: 1 },
        'kpa.temperature_c': { label: 'KPA temperature', unit: '°C', digits: 0, color: '#fb923c', floor: 0 },
        'kat.swr': { label: 'KAT SWR', unit: '', digits: 2, color: '#a78bfa', floor: 1 },
    });
    const WINDOWS = Object.freeze({
        900: { label: '15 min', bucket: 5 },
        3600: { label: '1 hour', bucket: 15 },
        21600: { label: '6 hours', bucket: 60 },
        86400: { label: '24 hours', bucket: 300 },
    });
    const CHART = Object.freeze({ width: 760, height: 160, left: 42, right: 12, top: 10, bottom: 28 });

    let timer = null;
    let controller = null;
    let selectedMetric = 'kpa.output_power_w';
    let selectedWindow = 3600;

    function finite(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }

    function timestamp(value) {
        const parsed = Date.parse(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function buildUrls(metric, windowSeconds, now = Date.now()) {
        const duration = WINDOWS[windowSeconds] ? Number(windowSeconds) : 3600;
        const end = new Date(now).toISOString();
        const start = new Date(now - duration * 1000).toISOString();
        const common = new URLSearchParams({ start, end, limit: '1000' });
        const telemetry = new URLSearchParams(common);
        telemetry.set('metric', METRICS[metric] ? metric : 'kpa.output_power_w');
        telemetry.set('bucket_seconds', String(WINDOWS[duration].bucket));
        return {
            start: now - duration * 1000,
            end: now,
            telemetry: `/api/station/telemetry?${telemetry}`,
            events: `/api/station/events?${common}`,
            tunes: `/api/station/tunes?${common}`,
        };
    }

    function normalizePoints(records) {
        return (Array.isArray(records) ? records : [])
            .map(record => ({
                at: timestamp(record.observed_at),
                value: finite(record.avg ?? record.value),
                min: finite(record.min ?? record.value),
                max: finite(record.max ?? record.value),
                quality: record.quality || null,
                unit: record.unit || null,
            }))
            .filter(point => point.at !== null && point.value !== null)
            .sort((a, b) => a.at - b.at);
    }

    function eventTime(record) {
        return timestamp(record.occurred_at ?? record.completed_at);
    }

    function normalizeMarkers(records, kind, start, end) {
        return (Array.isArray(records) ? records : [])
            .map(record => ({ at: eventTime(record), kind, record }))
            .filter(marker => marker.at !== null && marker.at >= start && marker.at <= end)
            .sort((a, b) => a.at - b.at);
    }

    function buildChartModel({ metric, telemetry, events, tunes, start, end }) {
        const config = METRICS[metric] || METRICS['kpa.output_power_w'];
        const points = normalizePoints(telemetry);
        const values = points.flatMap(point => [point.min, point.max]).filter(value => value !== null);
        let minimum = values.length ? Math.min(...values) : config.floor;
        let maximum = values.length ? Math.max(...values) : config.floor + 1;
        minimum = Math.min(minimum, config.floor);
        if (maximum <= minimum) maximum = minimum + 1;
        const padding = Math.max((maximum - minimum) * 0.12, config.digits === 0 ? 1 : 0.05);
        const yMin = Math.max(config.floor, minimum - padding);
        const yMax = maximum + padding;
        const plotWidth = CHART.width - CHART.left - CHART.right;
        const plotHeight = CHART.height - CHART.top - CHART.bottom;
        const range = Math.max(1, end - start);
        const x = at => CHART.left + ((at - start) / range) * plotWidth;
        const y = value => CHART.top + ((yMax - value) / (yMax - yMin)) * plotHeight;
        const coordinates = points.map(point => ({ ...point, x: x(point.at), y: y(point.value) }));
        const path = coordinates.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
        const baseline = CHART.top + plotHeight;
        const area = path ? `${path} L${coordinates.at(-1).x.toFixed(1)},${baseline} L${coordinates[0].x.toFixed(1)},${baseline} Z` : '';
        return {
            config,
            points: coordinates,
            path,
            area,
            yMin,
            yMax,
            start,
            end,
            markers: [
                ...normalizeMarkers(events, 'event', start, end),
                ...normalizeMarkers(tunes, 'tune', start, end),
            ].map(marker => ({ ...marker, x: x(marker.at) })),
        };
    }

    function availabilityState(payloads, pointCount) {
        const unavailable = payloads.filter(payload => payload?.available === false || payload?.error);
        if (payloads[0]?.available === false || payloads[0]?.error) return 'unavailable';
        if (unavailable.length) return 'degraded';
        return pointCount ? 'ready' : 'empty';
    }

    function detailText(value) {
        if (!value || typeof value !== 'object') return '';
        return value.message || value.detail || value.reason || value.step || '';
    }

    function recentItems(events, tunes) {
        const eventItems = (Array.isArray(events) ? events : []).map(record => ({
            at: eventTime(record),
            kind: 'event',
            label: String(record.event_type || 'event').replaceAll('_', ' '),
            detail: detailText(record.details) || record.source || '',
            severity: record.severity || '',
        }));
        const tuneItems = (Array.isArray(tunes) ? tunes : []).map(record => ({
            at: eventTime(record),
            kind: 'tune',
            label: `Tune ${record.outcome || 'unknown'}`,
            detail: [record.route_id, finite(record.swr_after) === null ? null : `SWR ${Number(record.swr_after).toFixed(2)}`].filter(Boolean).join(' · '),
            severity: record.outcome || '',
        }));
        return [...eventItems, ...tuneItems]
            .filter(item => item.at !== null)
            .sort((a, b) => b.at - a.at)
            .slice(0, 5);
    }

    function svgElement(name, attributes = {}) {
        const element = document.createElementNS(SVG_NS, name);
        Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
        return element;
    }

    function addSvgText(svg, text, x, y, anchor = 'start') {
        const element = svgElement('text', { x, y, 'text-anchor': anchor, class: 'station-history-axis-label' });
        element.textContent = text;
        svg.appendChild(element);
    }

    function formatMetric(value, config) {
        return `${value.toFixed(config.digits)}${config.unit ? ` ${config.unit}` : ''}`;
    }

    function formatClock(at) {
        return new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function renderChart(svg, model) {
        svg.replaceChildren();
        svg.style.setProperty('--history-series-color', model.config.color);
        const baseline = CHART.height - CHART.bottom;
        for (let index = 0; index <= 3; index += 1) {
            const ratio = index / 3;
            const y = CHART.top + ratio * (baseline - CHART.top);
            const value = model.yMax - ratio * (model.yMax - model.yMin);
            svg.appendChild(svgElement('line', { x1: CHART.left, y1: y, x2: CHART.width - CHART.right, y2: y, class: 'station-history-grid' }));
            addSvgText(svg, formatMetric(value, model.config), CHART.left - 5, y + 3, 'end');
        }
        addSvgText(svg, formatClock(model.start), CHART.left, CHART.height - 8);
        addSvgText(svg, formatClock(model.end), CHART.width - CHART.right, CHART.height - 8, 'end');

        model.markers.forEach(marker => {
            const markerClass = marker.kind === 'tune' ? 'station-history-tune' : 'station-history-event';
            svg.appendChild(svgElement('line', { x1: marker.x, y1: CHART.top, x2: marker.x, y2: baseline, class: `${markerClass}-line` }));
            svg.appendChild(svgElement('circle', { cx: marker.x, cy: CHART.top + 5, r: 3, class: `${markerClass}-dot` }));
        });
        if (model.area) svg.appendChild(svgElement('path', { d: model.area, class: 'station-history-area' }));
        if (model.path) svg.appendChild(svgElement('path', { d: model.path, class: 'station-history-line' }));
        if (model.points.length <= 60) {
            model.points.forEach(point => {
                const dot = svgElement('circle', { cx: point.x, cy: point.y, r: 2.4, class: 'station-history-point' });
                const title = svgElement('title');
                title.textContent = `${formatClock(point.at)} · ${formatMetric(point.value, model.config)}`;
                dot.appendChild(title);
                svg.appendChild(dot);
            });
        }
    }

    function renderRecent(root, items, sourcesAvailable) {
        root.replaceChildren();
        if (!sourcesAvailable) {
            const item = document.createElement('li');
            item.className = 'station-history-placeholder';
            item.textContent = 'Activity history is unavailable.';
            root.appendChild(item);
            return;
        }
        if (!items.length) {
            const item = document.createElement('li');
            item.className = 'station-history-placeholder';
            item.textContent = 'No events or tunes in this window.';
            root.appendChild(item);
            return;
        }
        items.forEach(entry => {
            const item = document.createElement('li');
            const time = document.createElement('time');
            time.dateTime = new Date(entry.at).toISOString();
            time.textContent = formatClock(entry.at);
            const kind = document.createElement('span');
            kind.className = `station-history-kind kind-${entry.kind}`;
            kind.textContent = entry.kind;
            const detail = document.createElement('span');
            detail.className = 'station-history-detail';
            detail.textContent = [entry.label, entry.detail].filter(Boolean).join(' · ');
            detail.title = detail.textContent;
            item.append(time, kind, detail);
            root.appendChild(item);
        });
    }

    async function fetchJson(url, signal, fetcher = fetch) {
        try {
            const response = await fetcher(url, { cache: 'no-store', signal });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            if (error?.name === 'AbortError') throw error;
            return { success: false, available: false, records: [], error: error?.message || 'Request failed' };
        }
    }

    function sourceReason(name, payload) {
        if (payload?.available !== false && !payload?.error) return null;
        return `${name}: ${payload?.reason || payload?.error || 'unavailable'}`;
    }

    async function load(fetcher = fetch, now = Date.now()) {
        const root = document.getElementById('station-history-panel');
        if (!root) return null;
        if (controller) controller.abort();
        controller = new AbortController();
        const urls = buildUrls(selectedMetric, selectedWindow, now);
        root.dataset.state = 'loading';
        const stateBadge = root.querySelector('[data-history-role="state"]');
        stateBadge.textContent = 'Loading';
        stateBadge.className = 'station-history-state state-loading';
        let payloads;
        try {
            payloads = await Promise.all([
                fetchJson(urls.telemetry, controller.signal, fetcher),
                fetchJson(urls.events, controller.signal, fetcher),
                fetchJson(urls.tunes, controller.signal, fetcher),
            ]);
        } catch (error) {
            if (error?.name === 'AbortError') return null;
            throw error;
        }
        const [telemetry, events, tunes] = payloads;
        const model = buildChartModel({
            metric: selectedMetric,
            telemetry: telemetry.records,
            events: events.records,
            tunes: tunes.records,
            start: urls.start,
            end: urls.end,
        });
        const state = availabilityState(payloads, model.points.length);
        root.dataset.state = state;
        root.style.setProperty('--history-series-color', model.config.color);
        stateBadge.textContent = state === 'empty' ? 'No data' : state;
        stateBadge.className = `station-history-state state-${state}`;
        root.querySelector('[data-history-role="series-label"]').textContent = model.config.label;
        const chart = root.querySelector('[data-history-role="chart"]');
        chart.setAttribute('aria-label', `${model.config.label} over ${WINDOWS[selectedWindow].label}; ${model.points.length} samples`);
        renderChart(chart, model);
        const emptyMessage = root.querySelector('[data-history-role="empty"]');
        emptyMessage.textContent = state === 'unavailable'
            ? 'Telemetry history is unavailable.'
            : 'No samples in this time window.';
        emptyMessage.hidden = model.points.length > 0;
        const activityAvailable = events.available !== false || tunes.available !== false;
        renderRecent(root.querySelector('[data-history-role="recent"]'), recentItems(events.records, tunes.records), activityAvailable);
        root.querySelector('[data-history-role="updated"]').textContent = `Updated ${formatClock(now)}`;
        const reasons = [sourceReason('Telemetry', telemetry), sourceReason('Events', events), sourceReason('Tunes', tunes)].filter(Boolean);
        root.querySelector('[data-history-role="message"]').textContent = reasons.length
            ? reasons.join(' · ')
            : `${model.points.length} samples · ${(events.records || []).length} events · ${(tunes.records || []).length} tunes`;
        return { state, model, payloads };
    }

    function start() {
        if (timer) return;
        const root = document.getElementById('station-history-panel');
        if (!root) return;
        const metricSelect = root.querySelector('[data-history-role="metric"]');
        const windowSelect = root.querySelector('[data-history-role="window"]');
        metricSelect.addEventListener('change', () => {
            selectedMetric = METRICS[metricSelect.value] ? metricSelect.value : 'kpa.output_power_w';
            load();
        });
        windowSelect.addEventListener('change', () => {
            selectedWindow = WINDOWS[windowSelect.value] ? Number(windowSelect.value) : 3600;
            load();
        });
        load();
        timer = setInterval(load, POLL_MS);
    }

    function stop() {
        clearInterval(timer);
        timer = null;
        if (controller) controller.abort();
        controller = null;
    }

    window.StationHistory = {
        METRICS,
        WINDOWS,
        availabilityState,
        buildChartModel,
        buildUrls,
        load,
        normalizePoints,
        recentItems,
        start,
        stop,
    };

    if (typeof document !== 'undefined') {
        document.addEventListener('vue-mounted', start, { once: true });
        window.addEventListener('beforeunload', stop, { once: true });
    }
}());
