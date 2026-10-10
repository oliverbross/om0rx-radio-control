// Guarded station integration settings plus semantic snapshot/diff tools.
(function () {
    'use strict';

    let busy = false;
    let settingsBusy = false;
    const BANDS = Object.freeze(['160m', '80m', '60m', '40m', '30m', '20m', '17m', '15m', '12m', '10m', '6m']);

    function objectValue(value) {
        return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    }

    function numericValue(value, fallback) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function normalizeSettings(config = {}) {
        const flexPolicy = objectValue(config.FLEX_ANTENNA_POLICY);
        const flexBands = objectValue(flexPolicy.bands);
        const katPolicy = objectValue(config.KAT500_ANTENNA_POLICY);
        const antennaNames = objectValue(config.KAT500_ANTENNA_NAMES);
        const amplifierDrive = objectValue(config.STATION_AMPLIFIER_DRIVE_W);
        const barefootDrive = objectValue(config.STATION_BAREFOOT_DRIVE_W);
        const digitalDrive = objectValue(config.STATION_DIGITAL_AMPLIFIER_DRIVE_W);
        const allowedBands = new Set(Array.isArray(config.STATION_AMPLIFIER_ALLOWED_BANDS)
            ? config.STATION_AMPLIFIER_ALLOWED_BANDS.map(value => String(value).trim().toLowerCase())
            : []);
        const digitalAllowedBands = new Set(Array.isArray(config.STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS)
            ? config.STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS.map(value => String(value).trim().toLowerCase())
            : [...allowedBands]);
        return {
            KPA500_ENABLED: config.KPA500_ENABLED === true,
            KPA500_PORT: String(config.KPA500_PORT || ''),
            KPA500_BAUDRATE: numericValue(config.KPA500_BAUDRATE, 38400),
            DIGITAL_KPA_POLICY: config.DIGITAL_KPA_POLICY === 'operate' ? 'operate' : 'standby',
            KAT500_ENABLED: config.KAT500_ENABLED === true,
            KAT500_PORT: String(config.KAT500_PORT || ''),
            KAT500_BAUDRATE: numericValue(config.KAT500_BAUDRATE, 38400),
            ELECRAFT_FOLLOW_RADIO: config.ELECRAFT_FOLLOW_RADIO === true,
            KAT500_ANTENNA_NAMES: Object.fromEntries([1, 2, 3].map(number => [
                String(number),
                String(antennaNames[String(number)] || `KAT ANT${number}`),
            ])),
            KAT500_ANTENNA_POLICY: Object.fromEntries(BANDS.map(band => [
                band,
                [1, 2, 3].includes(Number(katPolicy[band])) ? Number(katPolicy[band]) : 1,
            ])),
            FLEX_ANTENNA_POLICY: {
                enabled: flexPolicy.enabled === true,
                bands: Object.fromEntries(BANDS.map(band => [
                    band,
                    String(flexBands[band] || 'ANT1').toUpperCase() === 'ANT2' ? 'ANT2' : 'ANT1',
                ])),
            },
            STATION_AMPLIFIER_ALLOWED_BANDS: BANDS.filter(band => allowedBands.has(band)),
            STATION_AMPLIFIER_DRIVE_W: Object.fromEntries(BANDS.map(band => [
                band,
                Math.max(1, Math.min(100, Math.round(numericValue(amplifierDrive[band], 25)))),
            ])),
            STATION_BAREFOOT_DRIVE_W: Object.fromEntries(BANDS.map(band => [
                band,
                Math.max(1, Math.min(100, Math.round(numericValue(barefootDrive[band], 25)))),
            ])),
            STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS: BANDS.filter(band => digitalAllowedBands.has(band)),
            STATION_DIGITAL_AMPLIFIER_DRIVE_W: Object.fromEntries(BANDS.map(band => [
                band,
                Math.max(1, Math.min(100, Math.round(numericValue(digitalDrive[band], amplifierDrive[band] ?? 25)))),
            ])),
            STATION_TUNE_POWER_W: numericValue(config.STATION_TUNE_POWER_W, 20),
            STATION_TUNE_TARGET_SWR: numericValue(config.STATION_TUNE_TARGET_SWR, 1.5),
            STATION_TUNE_ABORT_SWR: numericValue(config.STATION_TUNE_ABORT_SWR, 3),
            STATION_TUNE_TIMEOUT_SECONDS: numericValue(config.STATION_TUNE_TIMEOUT_SECONDS, 30),
        };
    }

    async function responsePayload(response) {
        try {
            return await response.json();
        } catch (_) {
            return {};
        }
    }

    async function requestSnapshot(fetchImpl = fetch) {
        const response = await fetchImpl('/api/station/configuration/snapshot', {
            method: 'GET',
            cache: 'no-store',
            headers: { Accept: 'application/json' },
        });
        const payload = await responsePayload(response);
        if (!response.ok) throw new Error(payload.detail || `Snapshot export failed with HTTP ${response.status}`);
        return payload.configuration_snapshot;
    }

    async function requestSettings(fetchImpl = fetch) {
        const response = await fetchImpl('/api/config', {
            method: 'GET',
            cache: 'no-store',
            headers: { Accept: 'application/json' },
        });
        const payload = await responsePayload(response);
        if (!response.ok || payload.success === false || !payload.config) {
            throw new Error(payload.detail || 'Station settings could not be loaded');
        }
        return normalizeSettings(payload.config);
    }

    async function requestSettingsSave(settings, fetchImpl = fetch) {
        const response = await fetchImpl('/api/config', {
            method: 'POST',
            headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: settings }),
        });
        const payload = await responsePayload(response);
        if (!response.ok || payload.success === false) {
            throw new Error(payload.detail || payload.message || `Settings save failed with HTTP ${response.status}`);
        }
        return payload;
    }

    async function requestRestorePreview(snapshot, fetchImpl = fetch) {
        const response = await fetchImpl('/api/station/configuration/restore-preview', {
            method: 'POST',
            headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify({ snapshot }),
        });
        const payload = await responsePayload(response);
        if (!response.ok) throw new Error(payload.detail || `Restore preview failed with HTTP ${response.status}`);
        return payload.restore_preview;
    }

    function normalizePreview(preview) {
        const changes = Array.isArray(preview?.changes) ? preview.changes : [];
        return {
            valid: preview?.valid === true,
            previewOnly: preview?.preview_only === true,
            applyAvailable: preview?.apply_available === true,
            changeCount: Number(preview?.change_count ?? changes.length) || 0,
            requiresMaintenance: preview?.requires_maintenance === true,
            changes: changes.map(change => ({
                key: String(change?.key || 'unknown'),
                category: String(change?.class || 'operational'),
                before: change?.before,
                after: change?.after,
            })),
        };
    }

    function safeValue(value) {
        const text = typeof value === 'string' ? value : JSON.stringify(value);
        return String(text ?? 'null').slice(0, 80);
    }

    function setBusy(root, value) {
        busy = value;
        root.querySelectorAll('[data-station-configuration="download"], [data-station-configuration="choose"]')
            .forEach(button => { button.disabled = value; });
    }

    function setSettingsBusy(root, value) {
        settingsBusy = value;
        root.querySelectorAll('[data-station-configuration="save-settings"], [data-station-configuration="reload-settings"]')
            .forEach(button => { button.disabled = value; });
    }

    function renderBandRows(root) {
        const body = root.querySelector('[data-station-configuration="band-rows"]');
        if (!body || body.children.length) return;
        BANDS.forEach(band => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <th scope="row">${band}</th>
                <td><select aria-label="${band} FLEX TX port" data-station-config-flex-band="${band}"><option value="ANT1">ANT1</option><option value="ANT2">ANT2</option></select></td>
                <td><select aria-label="${band} KAT output" data-station-config-kat-band="${band}"><option value="1">ANT1</option><option value="2">ANT2</option><option value="3">ANT3</option></select></td>
                <td><label class="station-config-check"><input type="checkbox" aria-label="${band} KPA allowed" data-station-config-amp-band="${band}">Allowed</label></td>
                <td><input type="number" min="1" max="100" step="1" aria-label="${band} FLEX drive with KPA" data-station-config-amp-drive-band="${band}"></td>
                <td><input type="number" min="1" max="100" step="1" aria-label="${band} FLEX barefoot drive" data-station-config-barefoot-drive-band="${band}"></td>
                <td><label class="station-config-check"><input type="checkbox" aria-label="${band} digital KPA allowed" data-station-config-digital-amp-band="${band}">Allowed</label></td>
                <td><input type="number" min="1" max="100" step="1" aria-label="${band} FLEX digital drive" data-station-config-digital-drive-band="${band}"></td>`;
            body.appendChild(row);
        });
    }

    function setField(root, key, value) {
        const input = root.querySelector(`[data-station-config-field="${key}"]`);
        if (!input) return;
        if (input.type === 'checkbox') input.checked = value === true;
        else input.value = String(value ?? '');
    }

    function renderSettings(root, settings) {
        [
            'KPA500_ENABLED', 'KPA500_PORT', 'KPA500_BAUDRATE', 'DIGITAL_KPA_POLICY',
            'KAT500_ENABLED', 'KAT500_PORT', 'KAT500_BAUDRATE', 'ELECRAFT_FOLLOW_RADIO',
            'STATION_TUNE_POWER_W', 'STATION_TUNE_TARGET_SWR', 'STATION_TUNE_ABORT_SWR',
            'STATION_TUNE_TIMEOUT_SECONDS',
        ].forEach(key => setField(root, key, settings[key]));
        [1, 2, 3].forEach(number => {
            const input = root.querySelector(`[data-station-config-antenna-name="${number}"]`);
            if (input) input.value = settings.KAT500_ANTENNA_NAMES[String(number)];
        });
        const flexEnabled = root.querySelector('[data-station-config-flex-enabled]');
        if (flexEnabled) flexEnabled.checked = settings.FLEX_ANTENNA_POLICY.enabled;
        BANDS.forEach(band => {
            const flex = root.querySelector(`[data-station-config-flex-band="${band}"]`);
            const kat = root.querySelector(`[data-station-config-kat-band="${band}"]`);
            const allowed = root.querySelector(`[data-station-config-amp-band="${band}"]`);
            const drive = root.querySelector(`[data-station-config-amp-drive-band="${band}"]`);
            const barefootDrive = root.querySelector(`[data-station-config-barefoot-drive-band="${band}"]`);
            const digitalAllowed = root.querySelector(`[data-station-config-digital-amp-band="${band}"]`);
            const digitalDrive = root.querySelector(`[data-station-config-digital-drive-band="${band}"]`);
            if (flex) flex.value = settings.FLEX_ANTENNA_POLICY.bands[band];
            if (kat) kat.value = String(settings.KAT500_ANTENNA_POLICY[band]);
            if (allowed) allowed.checked = settings.STATION_AMPLIFIER_ALLOWED_BANDS.includes(band);
            if (drive) drive.value = String(settings.STATION_AMPLIFIER_DRIVE_W[band]);
            if (barefootDrive) barefootDrive.value = String(settings.STATION_BAREFOOT_DRIVE_W[band]);
            if (digitalAllowed) digitalAllowed.checked = settings.STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS.includes(band);
            if (digitalDrive) digitalDrive.value = String(settings.STATION_DIGITAL_AMPLIFIER_DRIVE_W[band]);
        });
    }

    function inputValue(root, key) {
        const input = root.querySelector(`[data-station-config-field="${key}"]`);
        if (!input) throw new Error(`Missing station setting ${key}`);
        return input.type === 'checkbox' ? input.checked : input.value;
    }

    function collectSettings(root) {
        const antennaNames = Object.fromEntries([1, 2, 3].map(number => {
            const name = root.querySelector(`[data-station-config-antenna-name="${number}"]`)?.value?.trim();
            if (!name) throw new Error(`KAT ANT${number} needs a physical antenna name`);
            return [String(number), name];
        }));
        const kpaEnabled = inputValue(root, 'KPA500_ENABLED') === true;
        const katEnabled = inputValue(root, 'KAT500_ENABLED') === true;
        const kpaPort = String(inputValue(root, 'KPA500_PORT')).trim().toUpperCase();
        const katPort = String(inputValue(root, 'KAT500_PORT')).trim().toUpperCase();
        if (kpaEnabled && !kpaPort) throw new Error('KPA500 serial port is required when enabled');
        if (katEnabled && !katPort) throw new Error('KAT500 serial port is required when enabled');
        return {
            KPA500_ENABLED: kpaEnabled,
            KPA500_PORT: kpaPort,
            KPA500_BAUDRATE: Number(inputValue(root, 'KPA500_BAUDRATE')),
            DIGITAL_KPA_POLICY: String(inputValue(root, 'DIGITAL_KPA_POLICY')),
            KAT500_ENABLED: katEnabled,
            KAT500_PORT: katPort,
            KAT500_BAUDRATE: Number(inputValue(root, 'KAT500_BAUDRATE')),
            ELECRAFT_FOLLOW_RADIO: inputValue(root, 'ELECRAFT_FOLLOW_RADIO') === true,
            KAT500_ANTENNA_NAMES: antennaNames,
            KAT500_ANTENNA_POLICY: Object.fromEntries(BANDS.map(band => [
                band,
                Number(root.querySelector(`[data-station-config-kat-band="${band}"]`)?.value),
            ])),
            FLEX_ANTENNA_POLICY: {
                enabled: root.querySelector('[data-station-config-flex-enabled]')?.checked === true,
                bands: Object.fromEntries(BANDS.map(band => [
                    band,
                    String(root.querySelector(`[data-station-config-flex-band="${band}"]`)?.value || 'ANT1'),
                ])),
            },
            STATION_AMPLIFIER_ALLOWED_BANDS: BANDS.filter(band =>
                root.querySelector(`[data-station-config-amp-band="${band}"]`)?.checked === true),
            STATION_AMPLIFIER_DRIVE_W: Object.fromEntries(BANDS.map(band => [
                band,
                Number(root.querySelector(`[data-station-config-amp-drive-band="${band}"]`)?.value),
            ])),
            STATION_BAREFOOT_DRIVE_W: Object.fromEntries(BANDS.map(band => [
                band,
                Number(root.querySelector(`[data-station-config-barefoot-drive-band="${band}"]`)?.value),
            ])),
            STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS: BANDS.filter(band =>
                root.querySelector(`[data-station-config-digital-amp-band="${band}"]`)?.checked === true),
            STATION_DIGITAL_AMPLIFIER_DRIVE_W: Object.fromEntries(BANDS.map(band => [
                band,
                Number(root.querySelector(`[data-station-config-digital-drive-band="${band}"]`)?.value),
            ])),
            STATION_TUNE_POWER_W: Number(inputValue(root, 'STATION_TUNE_POWER_W')),
            STATION_TUNE_TARGET_SWR: Number(inputValue(root, 'STATION_TUNE_TARGET_SWR')),
            STATION_TUNE_ABORT_SWR: Number(inputValue(root, 'STATION_TUNE_ABORT_SWR')),
            STATION_TUNE_TIMEOUT_SECONDS: Number(inputValue(root, 'STATION_TUNE_TIMEOUT_SECONDS')),
        };
    }

    function renderSettingsResult(root, message, state = '') {
        const result = root.querySelector('[data-station-configuration="settings-result"]');
        if (!result) return;
        result.dataset.state = state;
        result.textContent = message;
    }

    async function loadSettings(root) {
        if (settingsBusy) return;
        setSettingsBusy(root, true);
        try {
            const settings = await requestSettings();
            renderSettings(root, settings);
            renderSettingsResult(
                root,
                `Active: KPA500 ${settings.KPA500_PORT || 'disabled'} · KAT500 ${settings.KAT500_PORT || 'disabled'} · ${settings.ELECRAFT_FOLLOW_RADIO ? 'following FLEX' : 'manual band tracking'}`,
                'success',
            );
        } catch (error) {
            renderSettingsResult(root, error?.message || 'Station settings could not be loaded.', 'error');
        } finally {
            setSettingsBusy(root, false);
        }
    }

    async function saveSettings(root) {
        if (settingsBusy) return;
        setSettingsBusy(root, true);
        try {
            const settings = collectSettings(root);
            const result = await requestSettingsSave(settings);
            renderSettings(root, settings);
            renderSettingsResult(
                root,
                `${result.message || 'Settings saved.'} Device connections were refreshed; commissioning remains locked.`,
                'success',
            );
        } catch (error) {
            renderSettingsResult(root, error?.message || 'Station settings could not be saved.', 'error');
        } finally {
            setSettingsBusy(root, false);
        }
    }

    function renderResult(root, preview, error = null) {
        const result = root.querySelector('[data-station-configuration="result"]');
        const list = root.querySelector('[data-station-configuration="changes"]');
        if (!result || !list) return;
        list.replaceChildren();
        if (error) {
            result.dataset.state = 'error';
            result.textContent = error;
            return;
        }
        const view = normalizePreview(preview);
        result.dataset.state = view.changeCount ? 'changes' : 'clean';
        result.textContent = view.changeCount
            ? `${view.changeCount} change(s) found${view.requiresMaintenance ? '; Maintenance Mode would be required' : ''}. Preview only—nothing was applied.`
            : 'Snapshot is valid and matches the supported running configuration. Nothing was applied.';
        view.changes.forEach(change => {
            const item = document.createElement('li');
            item.textContent = `${change.key} (${change.category}): ${safeValue(change.before)} → ${safeValue(change.after)}`;
            list.appendChild(item);
        });
    }

    function downloadJson(snapshot) {
        const blob = new Blob([`${JSON.stringify(snapshot, null, 2)}\n`], { type: 'application/json' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `om0rx-station-${snapshot.snapshot_id || 'snapshot'}.json`;
        link.click();
        URL.revokeObjectURL(link.href);
    }

    async function download(root) {
        if (busy) return;
        setBusy(root, true);
        try {
            const snapshot = await requestSnapshot();
            downloadJson(snapshot);
            const result = root.querySelector('[data-station-configuration="result"]');
            if (result) {
                result.dataset.state = 'clean';
                result.textContent = `Snapshot ${snapshot.snapshot_id || ''} downloaded. It contains no secrets or live relay state.`;
            }
        } catch (error) {
            renderResult(root, null, error?.message || 'Snapshot export failed.');
        } finally {
            setBusy(root, false);
        }
    }

    async function previewFile(root, file) {
        if (busy || !file) return;
        setBusy(root, true);
        try {
            const snapshot = JSON.parse(await file.text());
            renderResult(root, await requestRestorePreview(snapshot));
        } catch (error) {
            renderResult(root, null, error?.message || 'Snapshot preview failed.');
        } finally {
            setBusy(root, false);
        }
    }

    function start() {
        const root = document.getElementById('station-configuration-panel');
        if (!root || root.dataset.bound === 'true') return;
        root.dataset.bound = 'true';
        renderBandRows(root);
        const input = root.querySelector('[data-station-configuration="file"]');
        root.querySelector('[data-station-configuration="setup-form"]')?.addEventListener('submit', event => {
            event.preventDefault();
            saveSettings(root);
        });
        root.querySelector('[data-station-configuration="reload-settings"]')?.addEventListener('click', () => loadSettings(root));
        root.querySelector('[data-station-configuration="download"]')?.addEventListener('click', () => download(root));
        root.querySelector('[data-station-configuration="choose"]')?.addEventListener('click', () => input?.click());
        input?.addEventListener('change', () => {
            const file = input.files?.[0];
            input.value = '';
            previewFile(root, file);
        });
        loadSettings(root);
    }

    window.StationConfiguration = {
        BANDS,
        collectSettings,
        normalizeSettings,
        normalizePreview,
        requestRestorePreview,
        requestSettings,
        requestSettingsSave,
        requestSnapshot,
        renderSettings,
        start,
    };

    if (typeof document !== 'undefined') document.addEventListener('vue-mounted', start, { once: true });
}());
