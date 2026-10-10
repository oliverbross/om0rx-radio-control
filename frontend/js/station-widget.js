// Compact, read-only FLEX -> KPA500 -> KAT500 -> antenna widget shell.
(function () {
    'use strict';

    const STORAGE_KEY = 'om0rx.stationWidget.orientation';
    const SIZE_STORAGE_PREFIX = 'om0rx.stationWidget.size.';
    const PREFERENCES_ENDPOINT = '/api/station/widget-preferences';
    const ORIENTATIONS = new Set(['horizontal', 'vertical']);
    const MANAGEMENT_PAGE = '/station.html';
    const MANAGEMENT_WINDOW = 'om0rxStationManagement';
    const TARGET_INNER_WIDTH = Object.freeze({ horizontal: 1120, vertical: 430 });
    const TARGET_INNER_HEIGHT = Object.freeze({ horizontal: 250, vertical: 690 });
    let sizeTimer = null;
    let suppressSizeMemoryUntil = 0;

    async function persistPreferences(update) {
        if (typeof window.fetch !== 'function') return false;
        try {
            const response = await window.fetch(PREFERENCES_ENDPOINT, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(update),
            });
            return response.ok;
        } catch (_) {
            return false;
        }
    }

    async function loadPreferences() {
        if (typeof window.fetch !== 'function') return null;
        try {
            const response = await window.fetch(PREFERENCES_ENDPOINT, { cache: 'no-store' });
            const payload = response.ok ? await response.json() : null;
            const orientation = payload?.preferences?.orientation;
            if (ORIENTATIONS.has(orientation)) setOrientation(orientation, { persist: false });
            return payload?.preferences || null;
        } catch (_) {
            return null;
        }
    }

    function preferenceStorage() {
        try {
            return window.__om0rxWidgetStorage || window.localStorage;
        } catch (_) {
            return null;
        }
    }

    function storedOrientation(storage = preferenceStorage()) {
        try {
            const value = storage?.getItem?.(STORAGE_KEY);
            return ORIENTATIONS.has(value) ? value : 'horizontal';
        } catch (_) {
            return 'horizontal';
        }
    }

    function fitWindowToContent(orientation) {
        const root = document.getElementById('station-path-dashboard');
        if (!root) return;
        const resolvedOrientation = ORIENTATIONS.has(orientation) ? orientation : 'horizontal';
        const hostWindow = window.top && window.top !== window ? window.top : window;
        if (typeof hostWindow.resizeTo !== 'function') return;
        try {
            suppressSizeMemoryUntil = Date.now() + 750;
            // Document Picture-in-Picture only permits resizing while the
            // orientation click still has transient user activation.
            const initialChromeWidth = Math.max(0, Number(hostWindow.outerWidth) - Number(hostWindow.innerWidth));
            hostWindow.resizeTo(
                TARGET_INNER_WIDTH[resolvedOrientation] + initialChromeWidth,
                hostWindow.outerHeight,
            );
            // Force layout after the width change so responsive toolbar wraps
            // are included before sizing the height in the same user gesture.
            const contentHeight = Math.ceil(root.getBoundingClientRect().height);
            const chromeWidth = Math.max(0, Number(hostWindow.outerWidth) - Number(hostWindow.innerWidth));
            const chromeHeight = Math.max(0, Number(hostWindow.outerHeight) - Number(hostWindow.innerHeight));
            hostWindow.resizeTo(
                TARGET_INNER_WIDTH[resolvedOrientation] + chromeWidth,
                contentHeight + chromeHeight,
            );
        } catch (_) {
            // Managed browser windows may disallow scripted resizing.
        }
    }

    function setOrientation(value, options = {}) {
        const orientation = ORIENTATIONS.has(value) ? value : 'horizontal';
        document.body.dataset.widgetOrientation = orientation;
        document.querySelectorAll('[data-widget-orientation]').forEach(button => {
            button.setAttribute('aria-pressed', String(button.dataset.widgetOrientation === orientation));
        });
        try {
            preferenceStorage()?.setItem?.(STORAGE_KEY, orientation);
        } catch (_) {
            // Storage can be disabled in hardened browser profiles.
        }
        if (options.persist !== false) {
            const update = options.resize === true
                ? { orientation, width: TARGET_INNER_WIDTH[orientation], height: TARGET_INNER_HEIGHT[orientation] }
                : { orientation };
            void persistPreferences(update);
        }
        if (options.resize === true) fitWindowToContent(orientation);
        return orientation;
    }

    function rememberSize(storage = preferenceStorage(), hostWindow = window) {
        const orientation = storedOrientation(storage);
        const width = Math.round(Number(hostWindow.innerWidth));
        const height = Math.round(Number(hostWindow.innerHeight));
        if (!Number.isFinite(width) || !Number.isFinite(height) || width < 300 || height < 180) return false;
        try { storage?.setItem?.(`${SIZE_STORAGE_PREFIX}${orientation}`, JSON.stringify({ width, height })); } catch (_) { /* optional */ }
        void persistPreferences({ orientation, width, height });
        return true;
    }

    function scheduleSizeMemory() {
        if (Date.now() < suppressSizeMemoryUntil) return;
        clearTimeout(sizeTimer);
        sizeTimer = setTimeout(() => rememberSize(), 180);
    }

    function openManagement(openImpl = window.open) {
        const management = openImpl.call(
            window,
            MANAGEMENT_PAGE,
            MANAGEMENT_WINDOW,
            'popup=yes,width=1500,height=980,resizable=yes,scrollbars=yes',
        );
        management?.focus?.();
        return management;
    }

    function updateTitle() {
        const state = document.getElementById('station-path-dashboard')?.dataset?.state || 'unknown';
        const frequency = document.querySelector('[data-path-segment="flex"] [data-path-role="primary"]')?.textContent || '';
        const nextTitle = `${state === 'ready' ? '●' : state === 'warning' ? '◆' : state === 'disconnected' ? '■' : '○'} ${frequency} · OM0RX Path`;
        if (document.title !== nextTitle) document.title = nextTitle;
    }

    function handleClick(event) {
        // The body also carries data-widget-orientation to drive the layout.
        // Match only toolbar buttons here; otherwise every click inside the
        // widget walks up to <body> and unexpectedly resizes the window.
        const orientation = event.target.closest?.('button[data-widget-orientation]')?.dataset?.widgetOrientation;
        if (orientation) {
            setOrientation(orientation, { resize: true });
            return;
        }
        if (event.target.closest?.('[data-widget-management]')) openManagement();
    }

    function start() {
        // The launcher already applies the saved per-layout size. Do not
        // overwrite a manual operator resize when this document starts.
        setOrientation(storedOrientation(), { persist: false });
        void loadPreferences();
        document.addEventListener('click', handleClick);
        document.addEventListener('station-path-updated', updateTitle);
        window.addEventListener('resize', scheduleSizeMemory);
        window.addEventListener('beforeunload', () => clearTimeout(sizeTimer), { once: true });
        updateTitle();
        // station-path.js intentionally starts after the shared startup event.
        document.dispatchEvent(new CustomEvent('vue-mounted'));
    }

    window.StationPathWidget = Object.freeze({
        MANAGEMENT_PAGE,
        PREFERENCES_ENDPOINT,
        SIZE_STORAGE_PREFIX,
        STORAGE_KEY,
        TARGET_INNER_HEIGHT,
        TARGET_INNER_WIDTH,
        fitWindowToContent,
        openManagement,
        loadPreferences,
        persistPreferences,
        preferenceStorage,
        rememberSize,
        setOrientation,
        storedOrientation,
    });

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
}());
