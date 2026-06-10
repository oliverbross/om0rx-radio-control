/**
 * Template Loader - Loads all template fragments before Vue initialization
 * This allows the monolithic index.html to be split across multiple files
 * while maintaining full Vue compatibility
 * 
 * ⚡ OPTIMIZED: Load templates in PARALLEL for speed, insert in order for correctness
 */
(function() {
    console.log('🔄 Template Loader: Starting to load template fragments in parallel...');
    const templateCacheKey = '20260610-wsjtz-launch-restored-1';
    
    // Template loading schedule: which file goes into which section
    const templateSchedule = [
        // Controls - all rows go into #controls-section
        { file: 'templates/controls-row1.html', target: 'controls-section', label: 'Controls Row 1', order: 0 },
        { file: 'templates/controls-row2.html', target: 'controls-section', label: 'Controls Row 2', order: 1 },
        { file: 'templates/controls-row3.html', target: 'controls-section', label: 'Controls Row 3', order: 2 },
        { file: 'templates/controls-row4-5.html', target: 'controls-section', label: 'Controls Row 4-5', order: 3 },
        // Logging Panel
        { file: 'templates/logging-panel.html', target: 'logging-panel-section', label: 'Logging Panel', order: 4 },
        // DX Spots
        { file: 'templates/dx-spots.html', target: 'dx-spots-section', label: 'DX Spots', order: 5 },
        // Modals - all go into #modals-section
        { file: 'templates/modal-config.html', target: 'modals-section', label: 'Config Modal', order: 6 },
        { file: 'templates/modal-country.html', target: 'modals-section', label: 'Country Modal', order: 7 },
        { file: 'templates/modal-local-log.html', target: 'modals-section', label: 'Local Log Modal', order: 8 },
        { file: 'templates/modal-wavelog-log.html', target: 'modals-section', label: 'Wavelog Log Modal', order: 9 },
        { file: 'templates/modal-callsign-search.html', target: 'modals-section', label: 'Callsign Search Modal', order: 10 },
        { file: 'templates/modal-prev-qsos.html', target: 'modals-section', label: 'Prev QSOs Modal', order: 11 },
        { file: 'templates/modal-sync.html', target: 'modals-section', label: 'Sync Modal', order: 12 },
        { file: 'templates/modal-ft8.html', target: 'modals-section', label: 'FT8/FT4 Digital Modal', order: 13 }
    ];
    
    const totalToLoad = templateSchedule.length;
    const loadedTemplates = new Map(); // Store loaded content by order
    let loadedCount = 0;
    
    // ⚡ CRITICAL FIX: Load all templates in parallel
    console.log(`⚡ Loading ${totalToLoad} templates in PARALLEL...`);
    
    const partialCache = new Map();

    function resolveTemplateIncludes(html) {
        const includePattern = /<!--\s*@include\s+([^>]+?)\s*-->/g;
        const includes = [...html.matchAll(includePattern)];
        if (includes.length === 0) {
            return Promise.resolve(html);
        }

        return Promise.all(includes.map(match => {
            const partialPath = match[1].trim();
            if (partialCache.has(partialPath)) {
                return partialCache.get(partialPath);
            }
            const promise = fetch(`${partialPath}?v=${templateCacheKey}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status} loading ${partialPath}`);
                    }
                    return response.text();
                })
                .then(partialHtml => partialHtml.trim());
            partialCache.set(partialPath, promise);
            return promise;
        })).then(partials => {
            let resolved = html;
            includes.forEach((match, index) => {
                resolved = resolved.replace(match[0], partials[index]);
            });
            return resolveTemplateIncludes(resolved);
        });
    }

    templateSchedule.forEach(({ file: templatePath, target: targetId, label: templateName, order }) => {
        fetch(`${templatePath}?v=${templateCacheKey}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status} loading ${templatePath}`);
                }
                return response.text();
            })
            .then(html => resolveTemplateIncludes(html))
            .then(html => {
                loadedTemplates.set(order, { html: html.trim(), targetId, templateName, templatePath });
                loadedCount++;
                console.log(`✅ Fetched: ${templateName}`);
                
                // Check if all templates loaded
                if (loadedCount === totalToLoad) {
                    insertAllTemplates();
                }
            })
            .catch(error => {
                console.error(`❌ Template Loader: Error loading ${templatePath}:`, error);
                loadedTemplates.set(order, { html: '', targetId, templateName, templatePath, error: true });
                loadedCount++;
                
                if (loadedCount === totalToLoad) {
                    insertAllTemplates();
                }
            });
    });
    
    // ⚡ Insert templates in correct order after all are loaded
    function insertAllTemplates() {
        console.log('⚡ Inserting all loaded templates in correct order...');
        
        for (let i = 0; i < totalToLoad; i++) {
            const templateData = loadedTemplates.get(i);
            if (!templateData) continue;
            
            const { html, targetId, templateName, error } = templateData;
            if (error) continue;
            
            const targetContainer = document.getElementById(targetId);
            if (!targetContainer) {
                console.error(`❌ Target container #${targetId} not found`);
                continue;
            }
            
            targetContainer.insertAdjacentHTML('beforeend', html);
            console.log(`✅ Inserted: ${templateName} → #${targetId}`);
        }
        
        console.log('✅ Template Loader: All templates loaded and inserted successfully!');
        document.dispatchEvent(new CustomEvent('templates-loaded'));
    }
})();
