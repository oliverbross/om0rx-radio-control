// Loads the shared station partials before starting their existing modules.
(function () {
    'use strict';

    const CACHE_KEY = '20261010-fast-flex-1';
    const PARTIALS = Object.freeze([
        'templates/partials/station-path.html',
        'templates/partials/station-history.html',
        'templates/partials/station-workflow.html',
        'templates/partials/station-training-preview.html',
        'templates/partials/station-configuration.html',
        'templates/partials/station-commissioning.html',
    ]);
    const partialCache = new Map();

    async function fetchText(path, fetchImpl = fetch, attempts = 2) {
        let lastError;
        for (let attempt = 1; attempt <= attempts; attempt += 1) {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 8000);
            try {
                const response = await fetchImpl(`${path}?v=${CACHE_KEY}`, {
                    cache: 'no-store',
                    signal: controller.signal,
                });
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

    async function resolveIncludes(html, fetchImpl = fetch, depth = 0) {
        if (depth > 5) throw new Error('station partial include depth exceeded');
        const pattern = /<!--\s*@include\s+([^>]+?)\s*-->/g;
        const includes = [...html.matchAll(pattern)];
        if (!includes.length) return html;
        const resolvedPartials = await Promise.all(includes.map(async match => {
            const path = match[1].trim();
            if (!partialCache.has(path)) partialCache.set(path, fetchText(path, fetchImpl));
            return partialCache.get(path);
        }));
        let resolved = html;
        includes.forEach((match, index) => { resolved = resolved.replace(match[0], resolvedPartials[index]); });
        return resolveIncludes(resolved, fetchImpl, depth + 1);
    }

    function renderError(root, error) {
        const panel = document.createElement('section');
        panel.className = 'station-shell-error';
        panel.setAttribute('role', 'alert');
        panel.textContent = `Station Management could not load: ${error?.message || 'unknown error'}`;
        root.replaceChildren(panel);
        document.dispatchEvent(new CustomEvent('templates-failed', {
            detail: { failures: [error?.message || 'unknown station template error'] },
        }));
    }

    async function load(fetchImpl = fetch) {
        const root = document.getElementById('station-management-panels');
        if (!root) throw new Error('missing #station-management-panels');
        try {
            const panels = await Promise.all(PARTIALS.map(async path =>
                resolveIncludes(await fetchText(path, fetchImpl), fetchImpl)));
            root.innerHTML = panels.join('\n');
            document.dispatchEvent(new CustomEvent('templates-loaded'));
            document.dispatchEvent(new CustomEvent('vue-mounted'));
            return panels;
        } catch (error) {
            renderError(root, error);
            return [];
        }
    }

    window.StationManagementShell = Object.freeze({
        CACHE_KEY,
        PARTIALS,
        fetchText,
        load,
        resolveIncludes,
    });

    load();
}());
