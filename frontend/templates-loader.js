/** Required template manifest loader. Vue mounts only after a complete UI exists. */
(function () {
    'use strict';
    const templateCacheKey = '20261010-webui-perf-1';
    const templateFetchTimeoutMs = 8000;
    const templateFetchConcurrency = 6;
    let settleReadiness;
    const readiness = {
        state: 'loading',
        result: null,
        promise: new Promise(resolve => { settleReadiness = resolve; }),
    };
    window.om0rxTemplateReady = readiness;
    const templateSchedule = [
        ['templates/controls-row1.html', 'controls-section', 'Controls Row 1'],
        ['templates/controls-row2.html', 'controls-section', 'Controls Row 2'],
        ['templates/controls-row3.html', 'controls-section', 'Controls Row 3'],
        ['templates/controls-row4-5.html', 'controls-section', 'Controls Row 4-5'],
        ['templates/logging-panel.html', 'logging-panel-section', 'Logging Panel'],
        ['templates/dx-spots.html', 'dx-spots-section', 'DX Spots'],
        ['templates/modal-config.html', 'modals-section', 'Config Modal'],
        ['templates/modal-country.html', 'modals-section', 'Country Modal'],
        ['templates/modal-local-log.html', 'modals-section', 'Local Log Modal'],
        ['templates/modal-wavelog-log.html', 'modals-section', 'Wavelog Log Modal'],
        ['templates/modal-callsign-search.html', 'modals-section', 'Callsign Search Modal'],
        ['templates/modal-prev-qsos.html', 'modals-section', 'Previous QSOs Modal'],
        ['templates/modal-sync.html', 'modals-section', 'Sync Modal'],
        ['templates/modal-ft8.html', 'modals-section', 'Digital Modal'],
    ].map(([file, target, label], order) => ({ file, target, label, order, required: true }));
    const partialCache = new Map();

    async function fetchText(path, attempts = 2) {
        let lastError;
        for (let attempt = 1; attempt <= attempts; attempt += 1) {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), templateFetchTimeoutMs);
            try {
                const response = await fetch(`${path}?v=${templateCacheKey}`, { signal: controller.signal, cache: 'default' });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const body = (await response.text()).trim();
                if (!body) throw new Error('empty response');
                return body;
            } catch (error) {
                lastError = error;
                if (attempt < attempts) await new Promise(resolve => setTimeout(resolve, 250));
            } finally {
                clearTimeout(timer);
            }
        }
        throw new Error(`${path}: ${lastError?.message || 'load failed'}`);
    }

    async function loadTemplates(entries) {
        // WebView2 limits concurrent HTTP/1.1 requests. Starting the entire
        // manifest at once also makes queued fetches consume their timeout
        // before the browser gives them a connection. Keep a small worker
        // pool so every request gets a fair chance to reach the local server.
        const results = new Array(entries.length);
        let nextIndex = 0;

        async function worker() {
            while (nextIndex < entries.length) {
                const index = nextIndex;
                nextIndex += 1;
                const entry = entries[index];
                try {
                    results[index] = {
                        status: 'fulfilled',
                        value: {
                            ...entry,
                            html: await resolveTemplateIncludes(await fetchText(entry.file)),
                        },
                    };
                } catch (reason) {
                    results[index] = { status: 'rejected', reason };
                }
            }
        }

        const workerCount = Math.min(templateFetchConcurrency, entries.length);
        await Promise.all(Array.from({ length: workerCount }, () => worker()));
        return results;
    }

    async function resolveTemplateIncludes(html, depth = 0) {
        if (depth > 5) throw new Error('template include depth exceeded');
        const pattern = /<!--\s*@include\s+([^>]+?)\s*-->/g;
        const includes = [...html.matchAll(pattern)];
        if (!includes.length) return html;
        const partials = await Promise.all(includes.map(async match => {
            const path = match[1].trim();
            if (!partialCache.has(path)) partialCache.set(path, fetchText(path));
            return partialCache.get(path);
        }));
        let resolved = html;
        includes.forEach((match, index) => { resolved = resolved.replace(match[0], partials[index]); });
        return resolveTemplateIncludes(resolved, depth + 1);
    }

    function renderFatal(failures) {
        const shell = document.getElementById('app') || document.body;
        document.getElementById('app-loading')?.remove();
        shell.removeAttribute?.('v-cloak');
        const panel = document.createElement('section');
        panel.id = 'template-load-error';
        panel.setAttribute('role', 'alert');
        const title = document.createElement('h1');
        title.textContent = 'OM0RX interface could not be loaded';
        const details = document.createElement('p');
        details.textContent = `Missing required interface asset(s): ${failures.join(', ')}`;
        const retry = document.createElement('button');
        retry.type = 'button';
        retry.textContent = 'Retry';
        retry.addEventListener('click', () => window.location.reload());
        panel.append(title, details, retry);
        shell.replaceChildren(panel);
        readiness.state = 'failed';
        readiness.result = { ok: false, failures };
        settleReadiness(readiness.result);
        document.dispatchEvent(new CustomEvent('templates-failed', { detail: { failures } }));
    }

    async function loadManifest() {
        const results = await loadTemplates(templateSchedule);
        const failures = results
            .map((result, index) => result.status === 'rejected' ? templateSchedule[index].file : null)
            .filter(Boolean);
        const missingTargets = templateSchedule
            .filter(entry => !document.getElementById(entry.target))
            .map(entry => `#${entry.target}`);
        if (failures.length || missingTargets.length) {
            renderFatal([...failures, ...missingTargets]);
            return;
        }
        results
            .map(result => result.value)
            .sort((a, b) => a.order - b.order)
            .forEach(entry => document.getElementById(entry.target).insertAdjacentHTML('beforeend', entry.html));
        readiness.state = 'loaded';
        readiness.result = { ok: true };
        settleReadiness(readiness.result);
        document.dispatchEvent(new CustomEvent('templates-loaded'));
    }

    loadManifest().catch(error => renderFatal([error.message || 'unknown template error']));
})();
