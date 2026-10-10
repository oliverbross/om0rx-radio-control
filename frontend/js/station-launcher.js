// Opens the station-management workspace without adding it to the main Vue UI.
(function () {
    'use strict';

    const STATION_PAGE = '/station.html';
    const WINDOW_NAME = 'om0rxStationManagement';
    const WINDOW_FEATURES = 'popup=yes,width=1500,height=980,resizable=yes,scrollbars=yes';
    const WIDGET_PAGE = '/station-widget.html';
    const WIDGET_WINDOW_NAME = 'om0rxStationPathWidget';
    const WIDGET_ORIENTATION_KEY = 'om0rx.stationWidget.orientation';
    const WIDGET_SIZE_PREFIX = 'om0rx.stationWidget.size.';
    const WIDGET_PREFERENCES_ENDPOINT = '/api/station/widget-preferences';
    const WIDGET_SIZES = Object.freeze({
        horizontal: Object.freeze({ width: 1120, height: 250 }),
        vertical: Object.freeze({ width: 430, height: 690 }),
    });
    let cachedWidgetPreferences = null;

    async function loadWidgetPreferences(owner = window) {
        if (typeof owner.fetch !== 'function') return null;
        try {
            const response = await owner.fetch(WIDGET_PREFERENCES_ENDPOINT, { cache: 'no-store' });
            const payload = response.ok ? await response.json() : null;
            if (payload?.preferences) cachedWidgetPreferences = payload.preferences;
        } catch (_) {
            // Local storage and built-in defaults remain available offline.
        }
        return cachedWidgetPreferences;
    }

    function isStationPopup(currentWindow = window) {
        return currentWindow.name === WINDOW_NAME && Boolean(currentWindow.opener && !currentWindow.opener.closed);
    }

    function returnToOpener(currentWindow = window) {
        if (!isStationPopup(currentWindow)) return false;
        currentWindow.opener.focus?.();
        currentWindow.close?.();
        return true;
    }

    function openStationManagement(openImpl = window.open) {
        const stationWindow = openImpl.call(window, STATION_PAGE, WINDOW_NAME, WINDOW_FEATURES);
        stationWindow?.focus?.();
        return stationWindow;
    }

    function widgetOrientation(owner) {
        try {
            const saved = owner.localStorage?.getItem?.(WIDGET_ORIENTATION_KEY);
            if (saved === 'horizontal' || saved === 'vertical') return saved;
        } catch (_) {
            // Continue with the backend-cached preference.
        }
        return cachedWidgetPreferences?.orientation === 'vertical' ? 'vertical' : 'horizontal';
    }

    function widgetSize(owner, orientation = widgetOrientation(owner)) {
        try {
            const rawSize = owner.localStorage?.getItem?.(`${WIDGET_SIZE_PREFIX}${orientation}`);
            if (rawSize) {
                const parsed = JSON.parse(rawSize);
                const width = Math.round(Number(parsed?.width));
                const height = Math.round(Number(parsed?.height));
                if (width >= 300 && width <= 1800 && height >= 180 && height <= 1100) {
                    return { width, height };
                }
            }
        } catch (_) {
            // Storage can be unavailable in hardened browser profiles.
        }
        const savedSize = cachedWidgetPreferences?.sizes?.[orientation];
        const width = Math.round(Number(savedSize?.width));
        const height = Math.round(Number(savedSize?.height));
        if (width >= 300 && width <= 1800 && height >= 180 && height <= 1100) return { width, height };
        return WIDGET_SIZES[orientation];
    }

    async function openNativeStationWidget(owner, orientation, size) {
        const nativeApi = owner.pywebview?.api;
        if (!nativeApi || typeof nativeApi.open_station_widget !== 'function') return null;
        try {
            const result = await nativeApi.open_station_widget(orientation, size.width, size.height);
            return result?.success ? result : null;
        } catch (_) {
            return null;
        }
    }

    function openBrowserStationWidget(owner, openImpl, size) {
        const openWindow = openImpl || owner.open;
        const widgetWindow = openWindow.call(
            owner,
            WIDGET_PAGE,
            WIDGET_WINDOW_NAME,
            `popup=yes,width=${size.width},height=${size.height},resizable=yes,scrollbars=yes`,
        );
        try {
            if (widgetWindow) widgetWindow.opener = null;
        } catch (_) {
            // Some managed browsers expose opener as read-only; the Radio
            // Control ownership above still keeps it independent of management.
        }
        widgetWindow?.focus?.();
        return widgetWindow;
    }

    function openStationWidget(openImpl = null, currentWindow = window) {
        // The desktop bridge creates a native WebView window with no browser
        // URL bar and ordinary Windows z-order. Browser sessions retain the
        // normal named-popup fallback; document PiP is intentionally avoided
        // because its windows are always-on-top by design.
        const owner = isStationPopup(currentWindow) ? currentWindow.opener : currentWindow;
        const initialOrientation = widgetOrientation(owner);
        const initialSize = widgetSize(owner, initialOrientation);
        const hasNativeLauncher = !openImpl
            && typeof owner.pywebview?.api?.open_station_widget === 'function';
        if (hasNativeLauncher) {
            return openNativeStationWidget(owner, initialOrientation, initialSize)
                .then(nativeResult => nativeResult || openBrowserStationWidget(owner, owner.open, initialSize));
        }
        // Browser popups must be created synchronously inside the click event.
        // Awaiting even an immediately-resolved native check first can make
        // Chromium classify the popup as unsolicited and block it.
        return openBrowserStationWidget(owner, openImpl, initialSize);
    }

    function handleClick(event) {
        if (event.target.closest?.('#station-widget-launcher')) {
            void openStationWidget();
            return;
        }
        if (!event.target.closest?.('#station-management-launcher')) return;
        if (!returnToOpener()) openStationManagement();
    }

    function labelLauncherForContext(root = document) {
        if (!isStationPopup()) return;
        const launcher = root.querySelector?.('#station-management-launcher');
        if (!launcher) return;
        launcher.textContent = 'Close & return';
        launcher.title = 'Focus the original Radio Control window and close this popup';
    }

    window.StationManagementLauncher = Object.freeze({
        STATION_PAGE,
        WINDOW_NAME,
        WIDGET_PAGE,
        WIDGET_WINDOW_NAME,
        WIDGET_ORIENTATION_KEY,
        WIDGET_PREFERENCES_ENDPOINT,
        WIDGET_SIZE_PREFIX,
        WIDGET_SIZES,
        isStationPopup,
        labelLauncherForContext,
        loadWidgetPreferences,
        openBrowserStationWidget,
        openStationManagement,
        openNativeStationWidget,
        openStationWidget,
        returnToOpener,
        widgetOrientation,
        widgetSize,
    });

    // Vue rebuilds the template nodes when it mounts, so keep this listener on
    // the stable document rather than binding directly to the transient button.
    document.addEventListener('click', handleClick);
    void loadWidgetPreferences();
    document.addEventListener('templates-loaded', () => labelLauncherForContext());
    document.addEventListener('vue-mounted', () => labelLauncherForContext());
    if (document.readyState !== 'loading') labelLauncherForContext();
}());
