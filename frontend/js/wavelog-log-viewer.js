/**
 * Wavelog Log Viewer Module
 * Direct database access for fast log viewing with advanced features
 */

(function() {
    'use strict';

    // Default column configuration
    const DEFAULT_COLUMNS = [
        { id: 'time_on', label: 'Date/Time', visible: true, width: 160 },
        { id: 'callsign', label: 'Callsign', visible: true, width: 100 },
        { id: 'mode', label: 'Mode', visible: true, width: 80 },
        { id: 'rst_sent', label: 'RST(S)', visible: true, width: 70 },
        { id: 'rst_rcvd', label: 'RST(R)', visible: true, width: 70 },
        { id: 'band', label: 'Band', visible: true, width: 70 },
        { id: 'frequency', label: 'Frequency', visible: true, width: 100 },
        { id: 'name', label: 'Name', visible: true, width: 120 },
        { id: 'qth', label: 'QTH', visible: true, width: 120 },
        { id: 'gridsquare', label: 'Gridsquare', visible: true, width: 100 },
        { id: 'country', label: 'Country', visible: true, width: 150 },
        { id: 'cqz', label: 'CQ', visible: true, width: 60 },
        { id: 'ituz', label: 'ITU', visible: true, width: 60 },
        { id: 'dxcc', label: 'DXCC', visible: true, width: 70 },
        { id: 'state', label: 'State', visible: false, width: 80 },
        { id: 'iota', label: 'IOTA', visible: false, width: 80 },
        { id: 'pota_ref', label: 'POTA', visible: false, width: 100 },
        { id: 'sota_ref', label: 'SOTA', visible: false, width: 100 },
        { id: 'wwff_ref', label: 'WWFF', visible: false, width: 100 },
        { id: 'lotw', label: 'LoTW', visible: true, width: 80 },
        { id: 'qsl', label: 'QSL', visible: true, width: 80 },
        { id: 'eqsl', label: 'eQSL', visible: false, width: 80 },
        { id: 'comment', label: 'Comment', visible: false, width: 200 }
    ];

    // Wait for Vue app to be ready
    document.addEventListener('vue-mounted', () => {
        if (!window.vueInstance) {
            console.error('❌ Vue instance not found for Wavelog Log Viewer');
            return;
        }

        console.log('📋 Initializing Wavelog Log Viewer...');

        // Load saved column configuration from localStorage
        const savedColumns = localStorage.getItem('wavelog-log-columns');
        const columns = savedColumns ? JSON.parse(savedColumns) : JSON.parse(JSON.stringify(DEFAULT_COLUMNS));

        // Populate the logColumns array (already defined in app-main.js data)
        // This preserves user's column preferences (visibility, width)
        window.vueInstance.logColumns = columns;

        console.log('✅ Wavelog Log Viewer initialized with', columns.length, 'columns');
    });
})();