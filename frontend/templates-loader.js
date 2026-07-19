/** Required template manifest loader. Vue mounts only after a complete UI exists. */
(function () {
    'use strict';
    const templateCacheKey = '20260718-spots-workspace-4';
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
            const timer = setTimeout(() => controller.abort(), 8000);
            try {
                const response = await fetch(`${path}?v=${templateCacheKey}`, { signal: controller.signal, cache: 'no-store' });
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
        document.dispatchEvent(new CustomEvent('templates-failed', { detail: { failures } }));
    }

    async function loadManifest() {
        const results = await Promise.allSettled(templateSchedule.map(async entry => ({
            ...entry,
            html: await resolveTemplateIncludes(await fetchText(entry.file)),
        })));
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
        document.dispatchEvent(new CustomEvent('templates-loaded'));
    }

    loadManifest().catch(error => renderFatal([error.message || 'unknown template error']));
})();
