// DX Spots Module
// FlexRadio Web Control v2.0 - DX Spots Management

console.log('✅ Loading dx-spots.js module...');

const dxSpotsData = {
    // DX Spots
    dxSpots: [],
    clusterConnected: false, // Track cluster connection status
    maxSpots: 100, // Maximum number of spots to display
    availableSpotCounts: [10, 25, 50, 100, 200],
    hoveredSpotId: null, // Track which spot is being hovered
    workedCallsigns: {}, // Store worked QSOs: { callsign: { qso_date, time_on } }
    spotsFilter: {
        callsign: '',
        bands: [],
        modes: [],
        continents: [],
        cqs: [],
        callStatuses: [],
        dxccStatuses: [],
        specials: [],
        spotSources: ['cluster'],
        rblModes: [],
        rblMinSnr: '',
        rblDedupeMinutes: 0,
        sortBy: 'time',
        workedB4Include: false,
        workedB4Exclude: false,
    },
    rblControl: {
        enabled: false,
        busy: false,
        lastCommand: '',
        lastCommands: [],
        lastCommandResults: [],
        lastResponse: '',
        lastResponseAt: null,
        lastProfile: '',
        lastProfileLabel: '',
    },
    rblProfiles: [],
    rblProfile: 'dxspider',
    spotSourceStats: null,
    spotSourceStatsLoading: false,
    spotSourceStatsTimer: null,
    spotSourceMuted: {
        cluster: false,
        rbl: false,
    },
    rblAlertRules: {
        enabled: true,
        newDxcc: true,
        newBand: true,
        newCall: false,
        localHeard: true,
        minScore: 55,
        minSnr: 8,
        modes: [],
        bands: [],
        cooldownMinutes: 10,
        sound: false,
        toast: true,
    },
    rblAlertSettingsOpen: false,
    rblAlerts: [],
    rblAlertSeen: {},
    
    // Filtered search from database
    filteredSearchResults: [],
    isSearchingSpots: false,
    lastSearchFilter: null,
    filteredSearchWarning: '',
    filteredSearchRetryAfter: 0,
    selectedSpot: null,
    selectedSpotExplain: null,
    spotExplainLoading: false,
    spotExplainError: '',
    visualSpotWindowMinutes: 60,
    visualSpotWindows: [5, 15, 30, 60],
    visualSpotLatestOnly: true,
    visualMapMode: 'globe',
    visualOverlayMode: 'dxcc',
    visualPathColorBy: 'band',
    visualTopoFeatures: [],
    visualTopoLoading: false,
    visualTopoError: '',
    visualTopoCountryIndex: {},
    visualZoneOverlayData: null,
    visualZoneOverlayLoading: false,
    visualZoneOverlayError: '',
    visualZoneOverlayReady: false,
    visualGlobeZoom: 1.1,
    visualGlobeRotation: { lon: -15, lat: 25 },
    visualGlobeDragging: false,
    visualGlobeDragStart: null,
    visualGlobeDrawPending: false,
    visualGlobeRefreshTimer: null,
    visualGlobeVisibleMarkers: [],
    visualGlobeVisiblePaths: [],
    visualGlobeHover: null,
    visualOverlayPalette: [
        'rgba(121, 201, 176, 0.58)',
        'rgba(245, 184, 100, 0.56)',
        'rgba(132, 190, 236, 0.56)',
        'rgba(228, 136, 170, 0.54)',
        'rgba(168, 203, 103, 0.56)',
        'rgba(195, 157, 225, 0.55)',
        'rgba(239, 155, 117, 0.54)',
        'rgba(116, 205, 211, 0.54)',
        'rgba(221, 203, 112, 0.56)',
        'rgba(151, 183, 239, 0.55)',
    ],
    visualCtyEntries: [],
    visualCtyLoading: false,
    visualCtyReady: false,
    visualCtyError: '',
    visualCtyLookupCache: {},
    visualCtyCountryIndex: {},
    visualSpotQuickFilter: 'all',
    visualQuickFilters: [
        { id: 'all', label: 'All' },
        { id: 'needed', label: 'Needed' },
        { id: 'hot', label: 'Hot' },
        { id: 'cluster', label: 'Cluster' },
        { id: 'rbl', label: 'RBL' },
        { id: 'mapped', label: 'Mapped' },
        { id: 'heard', label: 'Heard' },
    ],
    
    // 🆕 Queue for real-time spots arriving during filtered search
    // These are shown after the search completes, preventing filter interruption
    queuedRealtimeSpots: [],
    
    // Filter options
    availableBands: ['160m', '80m', '40m', '30m', '20m', '17m', '15m', '12m', '10m', '6m'],
    availableModes: ['CW', 'SSB', 'FT8', 'FT4', 'FT2', 'RTTY', 'PSK', 'DIGI', 'AM', 'FM', 'JT65', 'SSTV'],
    availableContinents: [
        {id: 'EU', name: 'Europe'},
        {id: 'NA', name: 'N. America'},
        {id: 'AS', name: 'Asia'},
        {id: 'AF', name: 'Africa'},
        {id: 'SA', name: 'S. America'},
        {id: 'OC', name: 'Oceania'}
    ],
    availableCQs: Array.from({length: 75}, (_, i) => (i + 1)),
    availableCallStatuses: ['New Call', 'New Band', 'New Mode', 'New Band+Mode', 'Worked', 'Confirmed'],
    availableDxccStatuses: ['ATNO', 'C/New Band', 'C/New Mode', 'C/New Band+Mode', 'W/New Band', 'W/New Mode', 'W/New Band+Mode', 'Worked', 'Confirmed', 'Unknown'],
    availableSpecials: ['POTA', 'SOTA', 'IOTA', 'WWFF', 'CASTLE', 'LIGHTHOUSE', 'CONTEST', 'IARU'],
    availableSpotSources: [
        { id: 'cluster', name: 'Cluster' },
        { id: 'rbl', name: 'RBL' },
    ],
    availableRblModes: ['CW', 'SSB', 'DIGI'],
    availableSpotSorts: [
        { id: 'time', name: 'Newest' },
        { id: 'score', name: 'Best' },
    ],
    availableSpotPresets: [
        { id: 'dx', name: 'DX hunt' },
        { id: 'rbl-cw', name: 'RBL CW' },
        { id: 'digital', name: 'Digital' },
        { id: 'new-dxcc', name: 'New DXCC' },
        { id: 'worked', name: 'Worked' },
    ],
    
    // Dropdown visibility
    openDropdown: null,
    
    // Spots popup window
    spotsWindow: null,
    spotsDetached: false,
    spotsChannel: null, // BroadcastChannel for window sync
};

const dxSpotsMethods = {
    // === DX Spots ===
    
    async tuneToSpot(spot) {
        console.log('🎯 tuneToSpot called with spot:', spot);
        
        // Expand panel section when a spot is clicked
        this.loggingPanelSectionCollapsed = false;
        
        // Backend stores frequency_mhz (float MHz) and frequency (string kHz from cluster)
        // Use frequency_mhz for calculations (it's the float MHz version)
        const freqMhz = spot.frequency_mhz || parseFloat(spot.frequency) / 1000;
        if (!freqMhz || isNaN(freqMhz)) {
            console.error('Invalid spot frequency:', spot);
            this.showStatus('Invalid spot frequency', 'error');
            return;
        }
        
        try {
            // Map cluster mode to radio mode
            // For SSB: determine USB (20m and up) or LSB (160-40m bands)
            let radioMode = spot.mode;
            if (spot.mode === 'SSB' || spot.mode === 'ssb') {
                // LSB for 160m, 80m, 60m, 40m (freq < 14 MHz)
                // USB for 20m and higher (freq >= 14 MHz)
                radioMode = freqMhz < 14 ? 'LSB' : 'USB';
            }
            
            console.log('Tuning to spot:', freqMhz, 'Mode:', spot.mode, '→', radioMode);
            this.showStatus(`🎯 Tuning to ${spot.callsign} on ${this.formatFrequencyForDisplay(freqMhz)} MHz (${radioMode})...`, 'info');

            // === CLEAR OLD FORM DATA FIRST ===
            // Make sure all fields from all tabs are cleared before populating with new spot
            this.suppressCallsignLookup = true;
            if (this.dxccLookupTimer) {
                clearTimeout(this.dxccLookupTimer);
                this.dxccLookupTimer = null;
            }
            this.clearLoggingForm();
            
            // === POPULATE LOGGING FORM ===
            // Fill in logging form fields with spot data
            this.loggingForm.callsign = spot.callsign || '';
            // Use MHz for the frequency field with full precision
            this.loggingForm.frequency = freqMhz;
            // CRITICAL: Set band from spot for "Worked b4" matching (CALL-BAND-MODE key)
            this.loggingForm.band = spot.band || '';
            
            // Set current UTC time
            const now = new Date();
            const utcHours = String(now.getUTCHours()).padStart(2, '0');
            const utcMinutes = String(now.getUTCMinutes()).padStart(2, '0');
            const utcSeconds = String(now.getUTCSeconds()).padStart(2, '0');
            this.loggingForm.time_off = `${utcHours}:${utcMinutes}:${utcSeconds}`;
            
            // When clicking a spot, use spot mode (not radio mode)
            // This avoids mismatch between spot "SSB" vs radio "USB", or spot "FT8" vs radio "DIGU"
            this.loggingForm.mode = spot.mode || '';
            
            // Auto-populate RST based on mode
            this.autoPopulateRST();
            
            // Extract POTA/SOTA/IOTA/WWFF from comments
            if (spot.comment) {
                const comment = spot.comment.toLowerCase();
                
                // Try to extract POTA reference
                const potaMatch = comment.match(/k-\d{4}|us-\d{4}|[a-z]{1,2}-\d{4}/i);
                if (potaMatch) this.loggingForm.pota = potaMatch[0].toUpperCase();
                
                // Try to extract SOTA reference
                const sotaMatch = comment.match(/[a-z]{1,2}\/[a-z]{2}-\d{3}/i);
                if (sotaMatch) this.loggingForm.sota = sotaMatch[0].toUpperCase();
                
                // Try to extract IOTA reference
                const iotaMatch = comment.match(/af-\d{3}|an-\d{3}|as-\d{3}|eu-\d{3}|na-\d{3}|oc-\d{3}|sa-\d{3}/i);
                if (iotaMatch) this.loggingForm.iota = iotaMatch[0].toUpperCase();
                
                // Try to extract WWFF reference
                const wwffMatch = comment.match(/[a-z]{2}ff-\d{4}/i);
                if (wwffMatch) this.loggingForm.wwff = wwffMatch[0].toUpperCase();
                
            // Store full comment in notes
            this.loggingForm.notes = spot.comment;
            }

            if (!spot._skipDigitalBroadcast) {
                this.broadcastDigitalSpotSelection(spot, freqMhz);
            }

            await this.$nextTick();
            this.suppressCallsignLookup = false;

            // === TRIGGER ROTOR AUTO IF ENABLED ===
            // Convert frequency to kHz for rotor AUTO
            const frequencyKhz = freqMhz * 1000;
            const gridsquare = spot.gridsquare || null;
            const latitude = spot.latitude ?? null;
            const longitude = spot.longitude ?? null;
            const hasCoords = latitude !== null && latitude !== undefined && longitude !== null && longitude !== undefined;
            const rotorOptions = {
                location_source: spot.location_source || (gridsquare || hasCoords ? 'cty_prefix' : null),
                grid_source: spot.location_source || null,
                cty_latitude: latitude,
                cty_longitude: longitude
            };
            
            console.log(`🔍 Rotor status: rotorEnabled=${this.rotorEnabled}, rotorAutoEnabled=${this.rotorAutoEnabled}, spotGrid=${!!gridsquare}, hasCoords=${hasCoords}`);
            
            if (this.rotorAutoEnabled && this.rotorEnabled) {
                console.log(`🤖 AUTO rotor triggered for ${spot.callsign} on ${freqMhz} MHz`);
                this.rotorAutoGoto(spot.callsign, frequencyKhz, gridsquare, latitude, longitude, rotorOptions);
            } else if (this.rotorEnabled && (gridsquare || hasCoords)) {
                // Even if AUTO is disabled, calculate and display SP/LP bearings
                // This allows manual rotor control via SP/LP GO buttons
                console.log(`📡 Calculating bearing (AUTO disabled): ${spot.callsign} with grid=${gridsquare}`);
                try {
                    const data = await this.resolveRotorTarget(spot.callsign, frequencyKhz, gridsquare, latitude, longitude, rotorOptions);
                    console.log(`📡 Bearing API response:`, data);
                    if (data.ok) {
                        console.log(`✅ Bearing calculated for ${spot.callsign}: SP ${this.shortPathBearing}° / LP ${this.longPathBearing}° (${data.source})`);
                    } else {
                        console.warn(`⚠️  Could not calculate bearing: ${data.error || 'unknown error'}`);
                        this.showStatus(`⚠️ Could not calculate bearing: ${data.error || data.message}`, 'warning');
                    }
                } catch (e) {
                    console.error('Could not calculate bearing:', e);
                }
            } else {
                console.log(`ℹ️ Rotor data insufficient: rotorEnabled=${this.rotorEnabled}, hasGrid=${!!gridsquare}, hasCoords=${hasCoords}`);
            }

            // Load QRZ/Wavelog/DXCC enrichment after the immediate click path.
            Promise.allSettled([
                this.loadQRZProfile({ triggerRotor: true, includeHistory: false }),
                this.loadDXCCStatus()
            ]).then(results => {
                const rejected = results.find(result => result.status === 'rejected');
                if (rejected) {
                    console.warn('Spot enrichment completed with an error:', rejected.reason);
                }
            });

            // Tune radio with full precision
            await this.sendCommand('spots/tune', { frequency: freqMhz, mode: radioMode });

            // Add spot to SmartSDR panadapter display
            try {
                const response = await fetch('/api/spots/add-to-radio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        callsign: spot.callsign,
                        frequency: freqMhz,
                        mode: radioMode,  // Use converted radioMode (USB/LSB for SSB), not original spot.mode
                        spotter: spot.spotter || 'Cluster',
                        comment: spot.comment || '',
                        tag: spot.tag
                    })
                });

                if (response.ok) {
                    const result = await response.json();
                    console.log('✨ Spot added to panadapter:', result.message);
                }
            } catch (e) {
                console.warn('Could not add spot to panadapter:', e);
            }

            this.showStatus(`✅ Tuned to ${spot.callsign} on ${this.formatFrequencyForDisplay(freqMhz)} MHz`, 'success');
            
        } catch (e) {
            this.suppressCallsignLookup = false;
            console.error('Tune to spot failed:', e);
            this.showStatus(`❌ Failed to tune to spot: ${e.message}`, 'error');
        }
    },

    isDigitalSpotMode(spot) {
        return ['FT8', 'FT4', 'FT2'].includes(String(spot?.mode || '').toUpperCase());
    },

    broadcastDigitalSpotSelection(spot, freqMhz) {
        if (!this.isDigitalSpotMode(spot)) {
            return;
        }
        const payload = {
            callsign: String(spot.callsign || '').toUpperCase(),
            frequency_mhz: Number(freqMhz || spot.frequency_mhz || (parseFloat(spot.frequency) / 1000) || 0),
            band: spot.band || '',
            mode: String(spot.mode || '').toUpperCase(),
            comment: spot.comment || '',
            gridsquare: spot.gridsquare || '',
            latitude: spot.latitude ?? null,
            longitude: spot.longitude ?? null,
            country: spot.country || spot.dxcc_name || '',
            call_status: spot.call_status || '',
            dxcc_status: spot.dxcc_status || '',
            audio_offset: spot.audio_offset || null
        };
        const event = {
            type: 'spot-selected',
            payload,
            source: 'main-window',
            timestamp: new Date().toISOString()
        };
        try {
            if (this.digitalModeChannel) {
                this.digitalModeChannel.postMessage(event);
            } else if (typeof BroadcastChannel !== 'undefined') {
                const channel = new BroadcastChannel('om0rx-digital-mode');
                channel.postMessage(event);
                channel.close();
            }
            localStorage.setItem('om0rx.digital.lastEvent', JSON.stringify(event));
        } catch (error) {
            console.warn('Unable to broadcast digital spot selection:', error);
        }
    },
    
    formatSpotFreq(freqMhz) {
        // Format frequency in MHz with full precision display
        if (!freqMhz) return '----.------';
        return this.formatFrequencyForDisplay(freqMhz);
    },
    
    // Get color for spot based on DXCC status
    getSpotRowClass(spot) {
        const tag = spot.tag || spot.dxcc_status;
        const classMap = {
            'ATNO': 'spot-atno',
            'New band': 'spot-new-band',
            'New mode': 'spot-new-mode',
            'New band+mode': 'spot-new-bandmode',
            'Need LoTW': 'spot-need-lotw',
            'Worked': 'spot-worked',
            'Confirmed': 'spot-confirmed'
        };
        return classMap[tag] || '';
    },
    
    // === Filter Management ===
    
    // Set maximum number of spots to display
    setMaxSpots(count) {
        this.maxSpots = count;
    },

    getDefaultSpotFilter() {
        return {
            callsign: '',
            bands: [],
            modes: [],
            continents: [],
            cqs: [],
            callStatuses: [],
            dxccStatuses: [],
            specials: [],
            spotSources: ['cluster'],
            rblModes: [],
            rblMinSnr: '',
            rblDedupeMinutes: 0,
            sortBy: 'time',
            workedB4Include: false,
            workedB4Exclude: false,
        };
    },
    
    // Dropdown management
    toggleDropdown(name) {
        this.openDropdown = this.openDropdown === name ? null : name;
    },
    
    // Toggle filter selection
    toggleFilterItem(filterArray, value) {
        const index = filterArray.indexOf(value);
        if (index === -1) {
            filterArray.push(value);
        } else {
            filterArray.splice(index, 1);
        }
    },
    
    // Select all items in a filter
    selectAllInFilter(filterArray, allItems) {
        filterArray.splice(0, filterArray.length, ...allItems);
    },
    
    // Clear specific filter
    clearFilter(filterArray) {
        filterArray.splice(0, filterArray.length);
    },
    
    // Clear all filters
    clearAllFilters() {
        Object.assign(this.spotsFilter, this.getDefaultSpotFilter());
        this.filteredSearchResults = [];
        this.lastSearchFilter = null;
        this.filteredSearchWarning = '';
        this.filteredSearchRetryAfter = 0;
    },

    resetSpotSearchCache() {
        this.filteredSearchResults = [];
        this.lastSearchFilter = null;
        this.filteredSearchWarning = '';
        this.filteredSearchRetryAfter = 0;
    },

    applySpotPreset(presetId) {
        const next = this.getDefaultSpotFilter();
        switch (presetId) {
            case 'dx':
                next.dxccStatuses = ['ATNO', 'C/New Band', 'C/New Mode', 'C/New Band+Mode', 'W/New Band', 'W/New Mode', 'W/New Band+Mode'];
                next.sortBy = 'score';
                break;
            case 'rbl-cw':
                next.spotSources = ['rbl'];
                next.rblModes = ['CW'];
                next.rblMinSnr = 8;
                next.rblDedupeMinutes = 5;
                next.sortBy = 'score';
                break;
            case 'digital':
                next.modes = ['FT8', 'FT4', 'FT2'];
                next.sortBy = 'score';
                break;
            case 'new-dxcc':
                next.dxccStatuses = ['ATNO'];
                next.sortBy = 'score';
                break;
            case 'worked':
                next.workedB4Include = true;
                break;
            default:
                return;
        }
        Object.assign(this.spotsFilter, next);
        this.resetSpotSearchCache();
        this.openDropdown = null;
    },
    
    // === Filtered Search (Database Query) ===
    
    async performFilteredSearch() {
        /**
         * Query spots from DuckDB database when filters are applied
         * This allows access to all historical spots, not just the cached recent ones
         */
        try {
            // Check if any filter is active
            const hasFilters = this.hasActiveFilters();
            
            if (!hasFilters) {
                console.log('ℹ️ No filters active, using cache');
                this.filteredSearchResults = [];
                return;
            }
            
            const rblSourceSelected = this.rblSourceSelected();

            // Build filter criteria for API
            const filterCriteria = {
                limit: this.maxSpots,
                callsign: this.spotsFilter.callsign || null,
                bands: this.spotsFilter.bands.length > 0 ? this.spotsFilter.bands : null,
                modes: this.spotsFilter.modes.length > 0 ? this.spotsFilter.modes : null,
                zones_cq: this.spotsFilter.cqs.length > 0 ? this.spotsFilter.cqs : null,
                continents: this.spotsFilter.continents.length > 0 ? this.spotsFilter.continents : null,
                special_tags: this.spotsFilter.specials.length > 0 ? this.spotsFilter.specials : null,
                spot_sources: this.spotsFilter.spotSources.length > 0 ? this.spotsFilter.spotSources : null,
                rbl_modes: rblSourceSelected && this.spotsFilter.rblModes.length > 0 ? this.spotsFilter.rblModes : null,
                rbl_min_snr: rblSourceSelected && this.spotsFilter.rblMinSnr !== '' ? Number(this.spotsFilter.rblMinSnr) : null,
                rbl_dedupe_minutes: rblSourceSelected && Number(this.spotsFilter.rblDedupeMinutes) > 0 ? Number(this.spotsFilter.rblDedupeMinutes) : null,
                sort_by: this.spotsFilter.sortBy || 'time',
            };
            
            // Check if filter criteria changed
            if (JSON.stringify(filterCriteria) === JSON.stringify(this.lastSearchFilter)) {
                console.log('ℹ️ Filter criteria unchanged, skipping search');
                return;
            }
            
            this.isSearchingSpots = true;
            this.filteredSearchWarning = '';
            console.log('🔍 Searching database for spots...', filterCriteria);
            
            const response = await fetch('/api/spots/filtered-search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(filterCriteria)
            });
            
            if (!response.ok) {
                throw new Error(`API error: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            if (result.ok) {
                this.filteredSearchResults = result.spots || [];
                this.lastSearchFilter = filterCriteria;
                console.log(`✅ Found ${this.filteredSearchResults.length} matching spots`);
            } else {
                this.filteredSearchWarning = result.warning || result.error || 'Spots database search is temporarily unavailable';
                this.filteredSearchRetryAfter = Date.now() + 30000;
                this.lastSearchFilter = filterCriteria;
                console.warn('⚠️ Search degraded:', this.filteredSearchWarning);
                this.filteredSearchResults = [];
            }
        } catch (e) {
            console.error('❌ Error performing filtered search:', e);
            this.filteredSearchWarning = e.message || 'Spots database search failed';
            this.filteredSearchRetryAfter = Date.now() + 30000;
            this.filteredSearchResults = [];
        } finally {
            this.isSearchingSpots = false;
            
            // 🆕 After search completes, flush any queued real-time spots
            // These are spots that arrived via WebSocket while search was in progress
            if (this.queuedRealtimeSpots.length > 0) {
                console.log(`📥 Flushing ${this.queuedRealtimeSpots.length} queued real-time spots`);
                // Add queued spots to the beginning of dxSpots cache
                this.dxSpots = this.queuedRealtimeSpots.concat(this.dxSpots);
                this.queuedRealtimeSpots = [];
            }
        }
    },
    
    hasActiveFilters() {
        /**Check if any filter is currently active*/
        const sourceFilterActive = this.isSpotSourceFilterActive();
        const rblFilterActive = this.rblSourceSelected() && (
            this.spotsFilter.rblModes.length > 0 ||
            this.spotsFilter.rblMinSnr !== '' ||
            Number(this.spotsFilter.rblDedupeMinutes) > 0
        );
        return !!(
            this.spotsFilter.callsign ||
            this.spotsFilter.bands.length > 0 ||
            this.spotsFilter.modes.length > 0 ||
            this.spotsFilter.continents.length > 0 ||
            this.spotsFilter.cqs.length > 0 ||
            this.spotsFilter.callStatuses.length > 0 ||
            this.spotsFilter.dxccStatuses.length > 0 ||
            this.spotsFilter.specials.length > 0 ||
            sourceFilterActive ||
            rblFilterActive ||
            this.spotsFilter.workedB4Include ||
            this.spotsFilter.workedB4Exclude
        );
    },
    
    matchesCurrentFilters(spot) {
        /**Check if a spot matches all currently active filters (for real-time spots)*/
        
        // Callsign filter
        if (this.spotsFilter.callsign) {
            const searchTerm = this.spotsFilter.callsign.toLowerCase();
            if (!spot.callsign.toLowerCase().includes(searchTerm)) {
                return false;
            }
        }
        
        // Band filter
        if (this.spotsFilter.bands.length > 0) {
            if (!this.spotsFilter.bands.includes(spot.band)) {
                return false;
            }
        }
        
        // Mode filter
        if (this.spotsFilter.modes.length > 0) {
            if (!this.spotsFilter.modes.includes(spot.mode)) {
                return false;
            }
        }
        
        // Continent filter - spotter_continent is the correct field from backend
        if (this.spotsFilter.continents.length > 0) {
            if (!this.spotsFilter.continents.includes(spot.spotter_continent)) {
                return false;
            }
        }
        
        // CQ Zone filter - backend sends 'cq' as string, need to convert filter values to strings
        if (this.spotsFilter.cqs.length > 0) {
            const cqStrings = this.spotsFilter.cqs.map(cq => String(cq));
            if (!cqStrings.includes(String(spot.cq))) {
                return false;
            }
        }
        
        // Special tags filter (POTA, SOTA, IOTA, WWFF, etc)
        if (this.spotsFilter.specials.length > 0) {
            const hasSpecial = this.spotsFilter.specials.some(special => 
                (spot.special_tags || spot.special || '').includes(special)
            );
            if (!hasSpecial) {
                return false;
            }
        }

        // Spot source filter
        if (this.spotsFilter.spotSources.length === 0) {
            return false;
        }

        const source = spot.spot_source || 'cluster';
        if (!this.spotsFilter.spotSources.includes(source)) {
            return false;
        }

        // RBL broad-mode filter
        if (this.rblSourceSelected() && this.spotsFilter.rblModes.length > 0) {
            if (source === 'rbl' && !this.spotsFilter.rblModes.includes(spot.rbl_mode_group || 'OTHER')) {
                return false;
            }
        }
        
        // Call Status filter (requires local QSO data)
        if (this.spotsFilter.callStatuses.length > 0) {
            const callStatus = spot.call_status || this.getCallStatus(spot.callsign, spot.band, spot.mode);
            if (!this.spotsFilter.callStatuses.includes(callStatus)) {
                return false;
            }
        }
        
        // DXCC Status filter (requires local QSO data)
        if (this.spotsFilter.dxccStatuses.length > 0) {
            const dxccStatus = spot.tag || spot.dxcc_status || this.getDXCCStatus(spot.callsign, spot.band, spot.mode);
            if (!this.spotsFilter.dxccStatuses.includes(dxccStatus)) {
                return false;
            }
        }
        
        // Worked b4 filter (requires local QSO data)
        if (this.spotsFilter.workedB4Include || this.spotsFilter.workedB4Exclude) {
            const isWorked = !!this.getWorkedDate(spot.callsign, spot.band, spot.mode);
            
            if (this.spotsFilter.workedB4Include && this.spotsFilter.workedB4Exclude) {
                // Both selected = show all
            } else if (this.spotsFilter.workedB4Include) {
                // Only include worked
                if (!isWorked) return false;
            } else if (this.spotsFilter.workedB4Exclude) {
                // Only exclude worked
                if (isWorked) return false;
            }
        }
        
        // All filters matched
        return true;
    },
    
    // === Spots Window Management ===
    
    detachSpots() {
        if (this.spotsDetached) return;
        
        const windowFeatures = 'width=1200,height=800,scrollbars=yes,resizable=yes';
        this.spotsWindow = window.open('/spots.html', 'spotsWindow', windowFeatures);
        
        if (this.spotsWindow) {
            this.spotsDetached = true;
            
            // Set up communication channel
            this.spotsChannel = new BroadcastChannel('spots-sync');
            
            // Send initial data when window loads
            this.spotsWindow.addEventListener('load', () => {
                this.syncSpotsToWindow();
            });
            
            // Handle window close
            this.spotsWindow.addEventListener('beforeunload', () => {
                this.spotsDetached = false;
                this.spotsWindow = null;
                if (this.spotsChannel) {
                    this.spotsChannel.close();
                    this.spotsChannel = null;
                }
            });
        }
    },
    
    syncSpotsToWindow() {
        if (this.spotsDetached && this.spotsChannel) {
            this.spotsChannel.postMessage({
                type: 'spots-update',
                spots: this.dxSpots,
                filters: this.spotsFilter,
                maxSpots: this.maxSpots
            });
        }
    },
    
    reattachSpots() {
        if (this.spotsWindow) {
            this.spotsWindow.close();
        }
        this.spotsDetached = false;
        this.spotsWindow = null;
        if (this.spotsChannel) {
            this.spotsChannel.close();
            this.spotsChannel = null;
        }
    },
    
    // === Filter Status ===
    
    isFilterActive(filterType) {
        switch (filterType) {
            case 'bands':
                return this.spotsFilter.bands.length > 0;
            case 'modes':
                return this.spotsFilter.modes.length > 0;
            case 'continents':
                return this.spotsFilter.continents.length > 0;
            case 'zones':
                return this.spotsFilter.cqs.length > 0;
            case 'callStatus':
                return this.spotsFilter.callStatuses.length > 0;
            case 'dxccStatus':
                return this.spotsFilter.dxccStatuses.length > 0;
            case 'special':
                return this.spotsFilter.specials.length > 0;
            case 'rbl':
                return (
                    this.rblControl.enabled ||
                    this.isSpotSourceFilterActive() ||
                    (
                        this.rblSourceSelected() &&
                        (
                            this.spotsFilter.rblModes.length > 0 ||
                            this.spotsFilter.rblMinSnr !== '' ||
                            Number(this.spotsFilter.rblDedupeMinutes) > 0
                        )
                    )
                );
            case 'sort':
                return this.spotsFilter.sortBy && this.spotsFilter.sortBy !== 'time';
            case 'workedB4':
                return this.spotsFilter.workedB4Include || this.spotsFilter.workedB4Exclude;
            default:
                return false;
        }
    },

    isSpotSourceFilterActive() {
        const sources = [...new Set(this.spotsFilter.spotSources || [])].sort();
        return !(sources.length === 1 && sources[0] === 'cluster');
    },

    rblSourceSelected() {
        return (this.spotsFilter.spotSources || []).includes('rbl');
    },

    clearRblSpotFilters() {
        this.spotsFilter.rblModes = [];
        this.spotsFilter.rblMinSnr = '';
        this.spotsFilter.rblDedupeMinutes = 0;
    },

    toggleSpotSource(sourceId) {
        this.toggleFilterItem(this.spotsFilter.spotSources, sourceId);
        if (!this.rblSourceSelected()) {
            this.clearRblSpotFilters();
        }
        this.resetSpotSearchCache();
    },

    applySourceAndRblFilters(spots) {
        let filtered = spots || [];

        if (this.spotsFilter.spotSources.length === 0) {
            return [];
        }

        filtered = filtered.filter(spot =>
            this.spotsFilter.spotSources.includes(spot.spot_source || 'cluster')
        );

        filtered = filtered.filter(spot => {
            const source = spot.spot_source || 'cluster';
            return !this.spotSourceMuted[source];
        });

        if (this.rblSourceSelected() && this.spotsFilter.rblModes.length > 0) {
            filtered = filtered.filter(spot =>
                (spot.spot_source || 'cluster') !== 'rbl' ||
                this.spotsFilter.rblModes.includes(spot.rbl_mode_group || 'OTHER')
            );
        }

        return filtered;
    },

    toggleSpotSourceMute(sourceId) {
        if (!Object.prototype.hasOwnProperty.call(this.spotSourceMuted, sourceId)) return;
        this.spotSourceMuted[sourceId] = !this.spotSourceMuted[sourceId];
        this.saveSpotSourceMuteState();
    },

    loadSpotSourceMuteState() {
        try {
            const raw = localStorage.getItem('om0rx.spots.sourceMuted');
            if (!raw) return;
            const parsed = JSON.parse(raw);
            this.spotSourceMuted = {
                cluster: parsed.cluster === true,
                rbl: parsed.rbl === true,
            };
        } catch (error) {
            console.warn('Could not load source mute state:', error);
        }
    },

    saveSpotSourceMuteState() {
        try {
            localStorage.setItem('om0rx.spots.sourceMuted', JSON.stringify(this.spotSourceMuted));
        } catch (error) {
            console.warn('Could not save source mute state:', error);
        }
    },

    getSourceStateSummaryItems() {
        const sources = this.spotsFilter.spotSources || [];
        const items = [];

        if (sources.length === 0) {
            items.push({ label: 'No sources selected', state: 'warning' });
        } else if (sources.includes('cluster') && sources.includes('rbl')) {
            items.push({ label: 'All sources', state: 'normal' });
        } else if (sources.includes('cluster')) {
            items.push({ label: 'Cluster only', state: 'normal' });
        } else if (sources.includes('rbl')) {
            items.push({ label: 'RBL only', state: 'rbl' });
        }

        if (!sources.includes('cluster')) {
            items.push({ label: 'Cluster hidden', state: 'muted' });
        }
        if (!sources.includes('rbl')) {
            items.push({ label: 'RBL hidden', state: 'muted' });
        }
        if (this.spotSourceMuted.cluster) {
            items.push({ label: 'Cluster muted', state: 'warning' });
        }
        if (this.spotSourceMuted.rbl) {
            items.push({ label: 'RBL muted', state: 'warning' });
        }

        return items;
    },

    getActiveSpotFilterChips() {
        const chips = [];
        const pushArray = (type, values, label) => {
            values.forEach(value => chips.push({ type, value, label: `${label}: ${value}` }));
        };

        if (this.spotsFilter.callsign) {
            chips.push({ type: 'callsign', value: this.spotsFilter.callsign, label: `Call: ${this.spotsFilter.callsign}` });
        }
        pushArray('band', this.spotsFilter.bands, 'Band');
        pushArray('mode', this.spotsFilter.modes, 'Mode');
        pushArray('continent', this.spotsFilter.continents, 'Continent');
        pushArray('cq', this.spotsFilter.cqs, 'CQ');
        pushArray('callStatus', this.spotsFilter.callStatuses, 'Call');
        pushArray('dxccStatus', this.spotsFilter.dxccStatuses, 'DXCC');
        pushArray('special', this.spotsFilter.specials, 'Special');
        if (this.isSpotSourceFilterActive()) {
            pushArray('source', this.spotsFilter.spotSources, 'Source');
        }
        if (this.rblSourceSelected()) {
            pushArray('rblMode', this.spotsFilter.rblModes, 'RBL');
            if (this.spotsFilter.rblMinSnr !== '') {
                chips.push({ type: 'rblMinSnr', value: this.spotsFilter.rblMinSnr, label: `RBL ≥ ${this.spotsFilter.rblMinSnr} dB` });
            }
            if (Number(this.spotsFilter.rblDedupeMinutes) > 0) {
                chips.push({ type: 'rblDedupeMinutes', value: this.spotsFilter.rblDedupeMinutes, label: `Dedupe ${this.spotsFilter.rblDedupeMinutes}m` });
            }
        }
        if (this.spotsFilter.sortBy === 'score') {
            chips.push({ type: 'sortBy', value: 'score', label: 'Sort: Best' });
        }
        if (this.spotsFilter.workedB4Include) {
            chips.push({ type: 'workedB4Include', value: true, label: 'Worked only' });
        }
        if (this.spotsFilter.workedB4Exclude) {
            chips.push({ type: 'workedB4Exclude', value: true, label: 'Not worked' });
        }
        return chips;
    },

    removeSpotFilterChip(chip) {
        const removeFrom = (array, value) => {
            const index = array.indexOf(value);
            if (index !== -1) array.splice(index, 1);
        };

        switch (chip.type) {
            case 'callsign':
                this.spotsFilter.callsign = '';
                break;
            case 'band':
                removeFrom(this.spotsFilter.bands, chip.value);
                break;
            case 'mode':
                removeFrom(this.spotsFilter.modes, chip.value);
                break;
            case 'continent':
                removeFrom(this.spotsFilter.continents, chip.value);
                break;
            case 'cq':
                removeFrom(this.spotsFilter.cqs, chip.value);
                break;
            case 'callStatus':
                removeFrom(this.spotsFilter.callStatuses, chip.value);
                break;
            case 'dxccStatus':
                removeFrom(this.spotsFilter.dxccStatuses, chip.value);
                break;
            case 'special':
                removeFrom(this.spotsFilter.specials, chip.value);
                break;
            case 'source':
                removeFrom(this.spotsFilter.spotSources, chip.value);
                if (!this.rblSourceSelected()) {
                    this.clearRblSpotFilters();
                }
                break;
            case 'rblMode':
                removeFrom(this.spotsFilter.rblModes, chip.value);
                break;
            case 'rblMinSnr':
                this.spotsFilter.rblMinSnr = '';
                break;
            case 'rblDedupeMinutes':
                this.spotsFilter.rblDedupeMinutes = 0;
                break;
            case 'sortBy':
                this.spotsFilter.sortBy = 'time';
                break;
            case 'workedB4Include':
                this.spotsFilter.workedB4Include = false;
                break;
            case 'workedB4Exclude':
                this.spotsFilter.workedB4Exclude = false;
                break;
        }
    },

    getBandActivityItems() {
        const counts = new Map();
        const source = this.filteredSpots || [];
        source.forEach(spot => {
            const band = spot.band || 'Unknown';
            if (!counts.has(band)) {
                counts.set(band, { band, total: 0, rbl: 0, cluster: 0, hot: 0, topScore: 0 });
            }
            const item = counts.get(band);
            const score = this.getSpotScore(spot);
            item.total += 1;
            item.topScore = Math.max(item.topScore, score);
            if (score >= 55) item.hot += 1;
            if ((spot.spot_source || 'cluster') === 'rbl') item.rbl += 1;
            else item.cluster += 1;
        });

        return this.availableBands
            .map(band => counts.get(band) || { band, total: 0, rbl: 0, cluster: 0, hot: 0, topScore: 0 })
            .filter(item => item.total > 0);
    },

    buildSpotSourceStats(spots) {
        const stats = {
            total: 0,
            cluster: 0,
            rbl: 0,
            other: 0,
            lastCluster: 0,
            lastRbl: 0,
            lastAny: 0,
            modes: {},
        };

        (spots || []).forEach(spot => {
            const source = spot.spot_source || 'cluster';
            const timestamp = this.getSpotTimestamp(spot);
            stats.total += 1;
            stats.lastAny = Math.max(stats.lastAny, timestamp);
            if (source === 'rbl') {
                stats.rbl += 1;
                stats.lastRbl = Math.max(stats.lastRbl, timestamp);
                const group = String(spot.rbl_mode_group || 'OTHER').toUpperCase();
                stats.modes[group] = (stats.modes[group] || 0) + 1;
            } else if (source === 'cluster') {
                stats.cluster += 1;
                stats.lastCluster = Math.max(stats.lastCluster, timestamp);
            } else {
                stats.other += 1;
            }
        });

        return stats;
    },

    formatSourceAge(timestamp) {
        const numeric = Number(timestamp || 0);
        if (!numeric) return 'none';
        const ageSeconds = Math.max(0, Math.floor(Date.now() / 1000 - numeric));
        if (ageSeconds < 60) return `${ageSeconds}s ago`;
        if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)}m ago`;
        return `${Math.floor(ageSeconds / 3600)}h ago`;
    },

    getSpotSourceDiagnostics() {
        const cache = this.buildSpotSourceStats(this.dxSpots || []);
        const visible = this.buildSpotSourceStats(this.filteredSpots || []);
        const serverStats = this.spotSourceStats || null;
        const live = serverStats && serverStats.live ? serverStats.live : cache;
        const windows = serverStats && Array.isArray(serverStats.windows) ? serverStats.windows : [];
        const selectedSources = this.spotsFilter.spotSources || [];
        const rblSelected = selectedSources.includes('rbl');
        const clusterSelected = selectedSources.includes('cluster');
        const muted = this.spotSourceMuted || {};
        const hiddenRbl = Math.max(0, cache.rbl - visible.rbl);
        const hiddenCluster = Math.max(0, cache.cluster - visible.cluster);

        let hint = 'Showing selected sources';
        if (!clusterSelected && !rblSelected) {
            hint = 'No source selected';
        } else if (muted.cluster && muted.rbl) {
            hint = 'All sources muted';
        } else if (muted.rbl) {
            hint = 'RBL muted';
        } else if (muted.cluster) {
            hint = 'Cluster muted';
        } else if (cache.rbl > 0 && !rblSelected) {
            hint = `${cache.rbl} RBL ${cache.rbl === 1 ? 'spot is' : 'spots are'} hidden`;
        } else if (cache.cluster > 0 && !clusterSelected) {
            hint = `${cache.cluster} cluster ${cache.cluster === 1 ? 'spot is' : 'spots are'} hidden`;
        } else if (visible.total === 0 && cache.total > 0) {
            hint = 'Current filters hide all cached spots';
        }

        return {
            cache,
            visible,
            live,
            windows,
            selectedSources,
            hiddenRbl,
            hiddenCluster,
            muted,
            hint,
            lastClusterLabel: this.formatSourceAge(live.last_cluster || live.lastCluster || cache.lastCluster),
            lastRblLabel: this.formatSourceAge(live.last_rbl || live.lastRbl || cache.lastRbl),
            lastAnyLabel: this.formatSourceAge(live.last_any || live.lastAny || cache.lastAny),
        };
    },

    getSourceWindowStats() {
        const diagnostics = this.getSpotSourceDiagnostics();
        return diagnostics.windows || [];
    },

    hasSpotSourceDiagnostics() {
        const diagnostics = this.getSpotSourceDiagnostics();
        return (
            diagnostics.cache.total > 0 ||
            diagnostics.live.total > 0 ||
            (diagnostics.windows || []).some(windowStats => windowStats.total > 0)
        );
    },

    getSourceWindowLabel(windowStats) {
        if (!windowStats) return '';
        return `${windowStats.label || windowStats.minutes + 'm'} ${windowStats.cluster || 0}C/${windowStats.rbl || 0}R`;
    },

    getSourceTrendItems() {
        const maxTotal = Math.max(1, ...this.getSourceWindowStats().map(item => Number(item.total || 0)));
        return this.getSourceWindowStats().map(item => ({
            ...item,
            clusterPercent: Math.round(((item.cluster || 0) / maxTotal) * 100),
            rblPercent: Math.round(((item.rbl || 0) / maxTotal) * 100),
        }));
    },

    getClusterHealth() {
        const diagnostics = this.getSpotSourceDiagnostics();
        const lastCluster = diagnostics.live.last_cluster || diagnostics.live.lastCluster || diagnostics.cache.lastCluster || 0;
        const oneHour = diagnostics.windows.find(item => Number(item.minutes) === 60);
        const ageSeconds = lastCluster ? Math.max(0, Math.floor(Date.now() / 1000 - lastCluster)) : null;
        let status = 'off';
        let label = 'Cluster none';
        if (ageSeconds !== null) {
            if (ageSeconds <= 300) {
                status = 'ok';
            } else if (ageSeconds <= 1800) {
                status = 'warn';
            } else {
                status = 'stale';
            }
            label = `Cluster ${this.formatSourceAge(lastCluster)}`;
        } else if (oneHour && oneHour.cluster > 0) {
            status = 'stale';
            label = `Cluster ${oneHour.cluster}/1h`;
        }
        return {
            status,
            label,
            lastCluster,
            lastClusterLabel: this.formatSourceAge(lastCluster),
            hourCount: oneHour ? oneHour.cluster || 0 : 0,
        };
    },

    getSpotSourceCounterText() {
        const diagnostics = this.getSpotSourceDiagnostics();
        const visible = diagnostics.visible;
        const cache = diagnostics.cache;
        const live = diagnostics.live;
        if (visible.total === 0) {
            if (cache.total === 0 && live.total > 0) {
                return `0 shown · live ${live.cluster || 0} cluster / ${live.rbl || 0} RBL`;
            }
            if (cache.total === 0) return '0 spots';
            return `0 shown · cache ${cache.cluster} cluster / ${cache.rbl} RBL`;
        }
        const shownParts = [];
        if (visible.cluster > 0) shownParts.push(`${visible.cluster} cluster`);
        if (visible.rbl > 0) shownParts.push(`${visible.rbl} RBL`);
        if (visible.other > 0) shownParts.push(`${visible.other} other`);
        const shownText = shownParts.join(' / ');
        if (cache.total === visible.total) {
            return `${visible.total} spots (${shownText})`;
        }
        return `${visible.total} shown (${shownText}) · cache ${cache.cluster} cluster / ${cache.rbl} RBL`;
    },

    async loadSpotSourceStats() {
        if (this.spotSourceStatsLoading) return;
        this.spotSourceStatsLoading = true;
        try {
            const response = await fetch('/api/spots/source-stats');
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || data.error || `HTTP ${response.status}`);
            }
            this.spotSourceStats = data;
        } catch (error) {
            console.warn('Could not load spot source stats:', error);
        } finally {
            this.spotSourceStatsLoading = false;
        }
    },

    setupSpotSourceStatsRefresh() {
        this.cleanupSpotSourceStatsRefresh();
        this.spotSourceStatsTimer = setInterval(() => {
            this.loadSpotSourceStats();
        }, 30000);
    },

    cleanupSpotSourceStatsRefresh() {
        if (this.spotSourceStatsTimer) {
            clearInterval(this.spotSourceStatsTimer);
            this.spotSourceStatsTimer = null;
        }
    },

    getRblCommandStatusText() {
        if (this.rblControl.busy) return 'Sending command...';
        if (this.rblControl.lastCommand) return this.rblControl.lastCommand;
        return 'No RBL command sent in this session';
    },

    getSelectedRblProfile() {
        return (this.rblProfiles || []).find(profile => profile.id === this.rblProfile) || null;
    },

    getRblProfileCommandPreview() {
        const profile = this.getSelectedRblProfile();
        if (!profile) {
            return {
                name: this.rblProfile || 'RBL',
                enable: '',
                disable: '',
                modes: [],
                selected: [],
            };
        }

        const modes = profile.modes || {};
        const selectedModes = this.spotsFilter.rblModes.length > 0 ? this.spotsFilter.rblModes : this.availableRblModes;
        const selected = selectedModes
            .map(mode => ({ mode, command: modes[mode] || modes[String(mode).toLowerCase()] || '' }))
            .filter(item => item.command);

        return {
            name: profile.name || profile.id,
            enable: profile.enable || '',
            disable: profile.disable || '',
            modes: Object.entries(modes).map(([mode, command]) => ({ mode: String(mode).toUpperCase(), command })),
            selected,
            modeNote: profile.mode_note || '',
            supportsModeCommands: Boolean(profile.supports_mode_commands || selected.length > 0),
        };
    },

    applyRblCommandTelemetry(data) {
        if (!data) return;
        if (typeof data.enabled === 'boolean') {
            this.rblControl.enabled = data.enabled;
        }
        this.rblControl.lastProfile = data.profile || this.rblControl.lastProfile || '';
        this.rblControl.lastProfileLabel = data.profile_label || this.rblControl.lastProfileLabel || '';
        this.rblControl.lastCommands = data.commands || this.rblControl.lastCommands || [];
        this.rblControl.lastCommand = this.rblControl.lastCommands.join(', ');
        this.rblControl.lastCommandResults = data.command_results || this.rblControl.lastCommandResults || [];

        const telemetry = data.telemetry || {};
        this.rblControl.lastResponse = telemetry.last_response || telemetry.last_line || this.rblControl.lastResponse || '';
        this.rblControl.lastResponseAt = telemetry.last_line_at || this.rblControl.lastResponseAt || null;
    },

    applyBandActivityFilter(band) {
        this.spotsFilter.bands = [band];
    },

    async setRblEnabled(enabled) {
        if (this.rblControl.busy) return;
        this.rblControl.busy = true;
        try {
            const response = await fetch('/api/cluster/rbl', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled,
                    modes: this.spotsFilter.rblModes.length > 0 ? this.spotsFilter.rblModes : null,
                    profile: this.rblProfile || null,
                }),
            });
            const data = await response.json();
            this.applyRblCommandTelemetry(data);
            if (data.success) {
                this.rblControl.enabled = enabled;
                this.showStatus(enabled ? 'RBL spots enabled' : 'RBL spots disabled', 'success');
            } else {
                this.showStatus(`RBL command failed: ${data.message}`, 'error');
            }
        } catch (error) {
            this.showStatus(`RBL command failed: ${error.message}`, 'error');
        } finally {
            this.rblControl.busy = false;
        }
    },

    async loadRblCommandStatus() {
        try {
            const response = await fetch('/api/cluster/rbl/status');
            const data = await response.json();
            if (!response.ok || !data.ok) {
                return;
            }
            this.applyRblCommandTelemetry(data);
        } catch (error) {
            console.warn('Could not load RBL command status:', error);
        }
    },

    async loadRblProfiles() {
        try {
            const response = await fetch('/api/cluster/rbl/profiles');
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.detail || data.error || 'Could not load RBL profiles');
            }
            this.rblProfiles = data.profiles || [];
            this.rblProfile = data.default_profile || this.rblProfile || 'dxspider';
        } catch (error) {
            console.warn('Could not load RBL profiles:', error);
            this.rblProfiles = [];
        }
    },

    showOnlyRblSpots() {
        this.spotsFilter.spotSources = ['rbl'];
        this.resetSpotSearchCache();
    },

    showOnlyClusterSpots() {
        this.spotsFilter.spotSources = ['cluster'];
        this.clearRblSpotFilters();
        this.resetSpotSearchCache();
    },

    showAllSpotSources() {
        this.spotsFilter.spotSources = ['cluster', 'rbl'];
        this.clearRblSpotFilters();
        this.resetSpotSearchCache();
    },

    getDefaultRblAlertRules() {
        return {
            enabled: true,
            newDxcc: true,
            newBand: true,
            newCall: false,
            localHeard: true,
            minScore: 55,
            minSnr: 8,
            modes: [],
            bands: [],
            cooldownMinutes: 10,
            sound: false,
            toast: true,
        };
    },

    loadRblAlertRules() {
        try {
            const serverRules = this.configData && this.configData.RBL_ALERT_RULES;
            if (serverRules && typeof serverRules === 'object') {
                this.rblAlertRules = { ...this.getDefaultRblAlertRules(), ...serverRules };
                return;
            }

            const raw = localStorage.getItem('om0rx.spots.rblAlertRules');
            if (!raw) return;
            const parsed = JSON.parse(raw);
            this.rblAlertRules = { ...this.getDefaultRblAlertRules(), ...parsed };
        } catch (error) {
            console.warn('Could not load RBL alert rules:', error);
            this.rblAlertRules = this.getDefaultRblAlertRules();
        }
    },

    async saveRblAlertRules() {
        try {
            localStorage.setItem('om0rx.spots.rblAlertRules', JSON.stringify(this.rblAlertRules));
            if (this.configData) {
                this.configData.RBL_ALERT_RULES = { ...this.rblAlertRules };
            }
            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config: { RBL_ALERT_RULES: this.rblAlertRules } }),
            }).then(async response => {
                if (!response.ok) {
                    const text = await response.text();
                    throw new Error(text || `HTTP ${response.status}`);
                }
                return response.json();
            }).then(data => {
                if (data && data.success === false) {
                    throw new Error(data.error || 'RBL alert settings were rejected');
                }
            }).catch(error => {
                console.warn('Could not save RBL alert rules to backend:', error);
            });
        } catch (error) {
            console.warn('Could not save RBL alert rules:', error);
        }
    },

    resetRblAlertRules() {
        this.rblAlertRules = this.getDefaultRblAlertRules();
        this.saveRblAlertRules();
    },

    toggleRblAlertsEnabled() {
        this.rblAlertRules.enabled = !this.rblAlertRules.enabled;
        this.saveRblAlertRules();
        this.evaluateRblAlertsForVisibleSpots();
    },

    toggleRblAlertSettings() {
        this.rblAlertSettingsOpen = !this.rblAlertSettingsOpen;
    },

    toggleRblAlertRuleArray(field, value) {
        if (!Array.isArray(this.rblAlertRules[field])) {
            this.rblAlertRules[field] = [];
        }
        const index = this.rblAlertRules[field].indexOf(value);
        if (index === -1) this.rblAlertRules[field].push(value);
        else this.rblAlertRules[field].splice(index, 1);
        this.saveRblAlertRules();
    },

    rblAlertStatusText() {
        if (!this.rblAlertRules.enabled) return 'Alerts off';
        const parts = [];
        if (this.rblAlertRules.newDxcc) parts.push('DXCC');
        if (this.rblAlertRules.newBand) parts.push('band');
        if (this.rblAlertRules.newCall) parts.push('call');
        if (this.rblAlertRules.localHeard) parts.push('heard');
        if (Number(this.rblAlertRules.minScore) > 0) parts.push(`score ${this.rblAlertRules.minScore}+`);
        if (this.rblAlertRules.minSnr !== '' && this.rblAlertRules.minSnr !== null) parts.push(`${this.rblAlertRules.minSnr}+ dB`);
        return parts.length ? parts.join(' / ') : 'All RBL';
    },

    getRblAlertReasons(spot) {
        if (!spot || (spot.spot_source || 'cluster') !== 'rbl') return [];
        const rules = this.rblAlertRules || this.getDefaultRblAlertRules();
        if (!rules.enabled) return [];

        const mode = String(spot.rbl_mode_group || 'OTHER').toUpperCase();
        if (Array.isArray(rules.modes) && rules.modes.length > 0 && !rules.modes.includes(mode)) {
            return [];
        }

        const band = spot.band || '';
        if (Array.isArray(rules.bands) && rules.bands.length > 0 && !rules.bands.includes(band)) {
            return [];
        }

        const reasons = [];
        const dxccStatus = String(spot.dxcc_status || spot.tag || '').toUpperCase();
        const callStatus = String(spot.call_status || '').toUpperCase();
        const score = this.getSpotScore(spot);
        const snr = this.getRblSnr(spot);

        if (rules.newDxcc && (dxccStatus.includes('ATNO') || dxccStatus.includes('NEW'))) {
            reasons.push(spot.dxcc_status || spot.tag || 'New DXCC');
        }
        if (rules.newBand && callStatus.includes('NEW BAND')) {
            reasons.push('New band');
        }
        if (rules.newCall && callStatus.includes('NEW CALL')) {
            reasons.push('New call');
        }
        if (rules.localHeard && spot.local_heard) {
            reasons.push('Decoded locally');
        }
        if (Number(rules.minScore) > 0 && score >= Number(rules.minScore)) {
            reasons.push(`Score ${score}`);
        }
        if (rules.minSnr !== '' && rules.minSnr !== null && snr !== null && !Number.isNaN(snr) && snr >= Number(rules.minSnr)) {
            reasons.push(`${snr} dB`);
        }

        return [...new Set(reasons)];
    },

    isRblAlertSpot(spot) {
        return !!(spot && (spot._rbl_alert || this.getRblAlertReasons(spot).length > 0));
    },

    getRblAlertKey(spot) {
        return [
            String(spot.callsign || '').toUpperCase(),
            spot.band || '',
            spot.rbl_mode_group || spot.mode || '',
        ].join('|');
    },

    evaluateRblSpotAlert(spot) {
        const reasons = this.getRblAlertReasons(spot);
        if (reasons.length === 0) {
            if (spot) {
                spot._rbl_alert = false;
                spot._rbl_alert_reasons = [];
            }
            return false;
        }

        spot._rbl_alert = true;
        spot._rbl_alert_reasons = reasons;

        const key = this.getRblAlertKey(spot);
        const now = Date.now();
        const cooldownMs = Math.max(1, Number(this.rblAlertRules.cooldownMinutes || 10)) * 60 * 1000;
        if (this.rblAlertSeen[key] && now - this.rblAlertSeen[key] < cooldownMs) {
            return true;
        }

        this.rblAlertSeen[key] = now;
        const alert = {
            id: `${key}|${now}`,
            timestamp: Math.floor(now / 1000),
            callsign: spot.callsign || '',
            band: spot.band || '',
            mode: spot.rbl_mode_group || spot.mode || '',
            frequency: spot.frequency_mhz || parseFloat(spot.frequency || 0) / 1000,
            country: spot.country || '',
            score: this.getSpotScore(spot),
            snr: this.getRblSnr(spot),
            reasons,
            spot,
        };
        this.rblAlerts.unshift(alert);
        this.rblAlerts = this.rblAlerts.slice(0, 30);

        if (this.rblAlertRules.toast) {
            this.showStatus(`RBL alert: ${alert.callsign} ${alert.band} ${reasons.join(', ')}`, 'warning');
        }
        if (this.rblAlertRules.sound) {
            this.playRblAlertSound();
        }
        return true;
    },

    evaluateRblAlertsForVisibleSpots() {
        (this.dxSpots || []).forEach(spot => {
            if ((spot.spot_source || 'cluster') === 'rbl') {
                const reasons = this.getRblAlertReasons(spot);
                spot._rbl_alert = reasons.length > 0;
                spot._rbl_alert_reasons = reasons;
            }
        });
    },

    playRblAlertSound() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            const context = new AudioContext();
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(880, context.currentTime);
            oscillator.frequency.setValueAtTime(1320, context.currentTime + 0.08);
            gain.gain.setValueAtTime(0.0001, context.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.22);
            oscillator.connect(gain);
            gain.connect(context.destination);
            oscillator.start();
            oscillator.stop(context.currentTime + 0.24);
            setTimeout(() => context.close(), 400);
        } catch (error) {
            console.warn('RBL alert sound failed:', error);
        }
    },

    clearRblAlerts() {
        this.rblAlerts = [];
    },

    focusRblAlert(alert) {
        if (!alert) return;
        this.spotsFilter.spotSources = ['rbl'];
        this.spotsFilter.callsign = alert.callsign || '';
        this.spotsFilter.bands = alert.band ? [alert.band] : [];
        this.spotsFilter.sortBy = 'score';
        if (alert.spot) {
            this.showSpotDetails(alert.spot);
        }
    },

    getSpotTimestamp(spot) {
        return Number(spot.aggregate_last_timestamp || spot.timestamp || 0);
    },

    getRblLiveSpots() {
        return (this.dxSpots || []).filter(spot => (spot.spot_source || 'cluster') === 'rbl');
    },

    getRblMonitorStats() {
        const spots = this.getRblLiveSpots();
        const stats = {
            total: spots.length,
            cw: 0,
            ssb: 0,
            digi: 0,
            other: 0,
            hot: 0,
            bestSnr: null,
            topScore: 0,
            lastTimestamp: 0,
            stale: true,
            lastLabel: 'no RBL',
        };

        spots.forEach(spot => {
            const group = String(spot.rbl_mode_group || 'OTHER').toUpperCase();
            if (group === 'CW') stats.cw += 1;
            else if (group === 'SSB') stats.ssb += 1;
            else if (group === 'DIGI') stats.digi += 1;
            else stats.other += 1;

            const snr = this.getRblSnr(spot);
            if (snr !== null && !Number.isNaN(snr)) {
                stats.bestSnr = stats.bestSnr === null ? snr : Math.max(stats.bestSnr, snr);
            }

            const score = this.getSpotScore(spot);
            stats.topScore = Math.max(stats.topScore, score);
            if (score >= 55) stats.hot += 1;
            stats.lastTimestamp = Math.max(stats.lastTimestamp, this.getSpotTimestamp(spot));
        });

        if (stats.lastTimestamp) {
            const ageSeconds = Math.max(0, Math.floor(Date.now() / 1000 - stats.lastTimestamp));
            stats.stale = ageSeconds > 300;
            stats.lastLabel = this.formatRblAge(ageSeconds);
        }

        return stats;
    },

    getRblMonitorBandItems() {
        const counts = new Map();
        this.getRblLiveSpots().forEach(spot => {
            const band = spot.band || 'Unknown';
            if (!counts.has(band)) {
                counts.set(band, { band, total: 0, cw: 0, ssb: 0, digi: 0, bestSnr: null, topScore: 0 });
            }
            const item = counts.get(band);
            const group = String(spot.rbl_mode_group || 'OTHER').toUpperCase();
            item.total += 1;
            if (group === 'CW') item.cw += 1;
            else if (group === 'SSB') item.ssb += 1;
            else if (group === 'DIGI') item.digi += 1;
            const snr = this.getRblSnr(spot);
            if (snr !== null && !Number.isNaN(snr)) {
                item.bestSnr = item.bestSnr === null ? snr : Math.max(item.bestSnr, snr);
            }
            item.topScore = Math.max(item.topScore, this.getSpotScore(spot));
        });

        return this.availableBands
            .map(band => counts.get(band))
            .filter(Boolean)
            .sort((a, b) => b.total - a.total || b.topScore - a.topScore);
    },

    formatRblAge(ageSeconds) {
        if (ageSeconds < 60) return `${ageSeconds}s`;
        if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)}m`;
        return `${Math.floor(ageSeconds / 3600)}h`;
    },

    focusRblMode(mode) {
        this.spotsFilter.spotSources = ['rbl'];
        this.spotsFilter.rblModes = [mode];
        this.spotsFilter.sortBy = 'score';
        this.openDropdown = null;
    },

    focusRblBand(band) {
        this.spotsFilter.spotSources = ['rbl'];
        this.spotsFilter.bands = [band];
        this.spotsFilter.sortBy = 'score';
    },

    showHighConfidenceRblSpots() {
        this.spotsFilter.spotSources = ['rbl'];
        this.spotsFilter.rblMinSnr = 8;
        this.spotsFilter.rblDedupeMinutes = 5;
        this.spotsFilter.sortBy = 'score';
    },

    getRblSnr(spot) {
        if (spot.rbl_snr !== null && spot.rbl_snr !== undefined && spot.rbl_snr !== '') {
            return Number(spot.rbl_snr);
        }
        const match = String(spot.comment || '').match(/(^|[^A-Z0-9])([+-]?\d{1,2}(?:\.\d+)?)\s*dB\b/i);
        return match ? Number(match[2]) : null;
    },

    getSpotIdentityKey(spot) {
        if (spot.aggregate_key) return spot.aggregate_key;
        const source = spot.spot_source || 'cluster';
        const callsign = String(spot.callsign || '').toUpperCase();
        const band = String(spot.band || '').toUpperCase();
        const mode = String(spot.mode || '').toUpperCase();
        if (source === 'rbl') {
            return `rbl:${callsign}:${band}:${mode}`;
        }
        const freqMhz = spot.frequency_mhz || parseFloat(spot.frequency || 0) / 1000;
        return `cluster:${callsign}:${Number(freqMhz || 0).toFixed(3)}`;
    },

    findExistingSpotIndex(spot, spots) {
        const key = this.getSpotIdentityKey(spot);
        return (spots || []).findIndex(existing => this.getSpotIdentityKey(existing) === key);
    },

    mergeSpotAggregate(existingSpot, incomingSpot) {
        const currentCount = Number(existingSpot.aggregate_count || 1);
        const incomingCount = Number(incomingSpot.aggregate_count || 1);
        const existingSpotters = Array.isArray(existingSpot.aggregate_spotters)
            ? existingSpot.aggregate_spotters
            : [existingSpot.spotter].filter(Boolean);
        const incomingSpotters = Array.isArray(incomingSpot.aggregate_spotters)
            ? incomingSpot.aggregate_spotters
            : [incomingSpot.spotter].filter(Boolean);
        const spotters = [...new Set([...existingSpotters, ...incomingSpotters])];
        const bestSnrValues = [
            existingSpot.aggregate_best_snr,
            incomingSpot.aggregate_best_snr,
            this.getRblSnr(existingSpot),
            this.getRblSnr(incomingSpot),
        ].filter(value => value !== null && value !== undefined && value !== '');

        return {
            ...existingSpot,
            ...incomingSpot,
            aggregate_key: incomingSpot.aggregate_key || existingSpot.aggregate_key || this.getSpotIdentityKey(incomingSpot),
            aggregate_count: Math.max(currentCount + 1, incomingCount),
            aggregate_spotters: spotters,
            aggregate_spotter_count: spotters.length,
            aggregate_first_timestamp: Math.min(
                Number(existingSpot.aggregate_first_timestamp || existingSpot.timestamp || 0),
                Number(incomingSpot.aggregate_first_timestamp || incomingSpot.timestamp || 0)
            ),
            aggregate_last_timestamp: Math.max(
                Number(existingSpot.aggregate_last_timestamp || existingSpot.timestamp || 0),
                Number(incomingSpot.aggregate_last_timestamp || incomingSpot.timestamp || 0)
            ),
            aggregate_best_snr: bestSnrValues.length > 0 ? Math.max(...bestSnrValues.map(Number)) : null,
        };
    },

    getSpotSeenLabel(spot) {
        const count = Number(spot.aggregate_count || 1);
        return count > 1 ? `seen x${count}` : '';
    },

    getSpotterSummary(spot) {
        const count = Number(spot.aggregate_spotter_count || 0);
        if (count > 1) return `${count} spotters`;
        return spot.spotter || '-';
    },

    getBestSnrLabel(spot) {
        const best = spot.aggregate_best_snr;
        if (best === null || best === undefined || best === '') return '';
        return `best ${Number(best).toFixed(0)} dB`;
    },

    getLastSeenLabel(spot) {
        const timestamp = this.getSpotTimestamp(spot);
        if (!timestamp) return '';
        const ageSeconds = Math.max(0, Math.floor(Date.now() / 1000 - timestamp));
        if (ageSeconds < 60) return `${ageSeconds}s ago`;
        if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)}m ago`;
        return `${Math.floor(ageSeconds / 3600)}h ago`;
    },

    filterRblNoise(spots) {
        let filtered = spots || [];
        if (!this.rblSourceSelected()) {
            return filtered;
        }

        const minSnr = this.spotsFilter.rblMinSnr !== '' ? Number(this.spotsFilter.rblMinSnr) : null;
        if (minSnr !== null && !Number.isNaN(minSnr)) {
            filtered = filtered.filter(spot => {
                if ((spot.spot_source || 'cluster') !== 'rbl') return true;
                const snr = this.getRblSnr(spot);
                return snr !== null && snr >= minSnr;
            });
        }

        const dedupeMinutes = Number(this.spotsFilter.rblDedupeMinutes);
        if (dedupeMinutes > 0) {
            const seen = new Map();
            const windowSeconds = dedupeMinutes * 60;
            filtered = filtered.filter(spot => {
                if ((spot.spot_source || 'cluster') !== 'rbl') return true;
                const key = `${spot.callsign || ''}|${spot.band || ''}|${spot.mode || ''}`;
                const timestamp = Number(spot.timestamp || 0);
                const previous = seen.get(key);
                if (previous !== undefined && Math.abs(previous - timestamp) <= windowSeconds) {
                    return false;
                }
                seen.set(key, timestamp);
                return true;
            });
        }

        return filtered;
    },

    sortVisibleSpots(spots) {
        const sorted = [...(spots || [])];
        if (this.spotsFilter.sortBy === 'score') {
            sorted.sort((a, b) =>
                (Number(b.spot_score || 0) - Number(a.spot_score || 0)) ||
                (Number(b.timestamp || 0) - Number(a.timestamp || 0))
            );
        }
        return sorted;
    },

    getSpotScore(spot) {
        return Number(spot.spot_score || 0);
    },

    getSpotScoreLabel(spot) {
        const score = this.getSpotScore(spot);
        if (score >= 80) return 'Hot';
        if (score >= 55) return 'Good';
        if (score >= 30) return 'Watch';
        return 'Low';
    },

    getSpotScoreStyle(spot) {
        const score = this.getSpotScore(spot);
        if (score >= 80) return 'background: #7f1d1d; color: #fecaca;';
        if (score >= 55) return 'background: #854d0e; color: #fde68a;';
        if (score >= 30) return 'background: #064e3b; color: #a7f3d0;';
        return 'background: #374151; color: #d1d5db;';
    },

    getSpotScoreReasons(spot) {
        if (Array.isArray(spot.spot_score_reasons)) return spot.spot_score_reasons;
        if (typeof spot.spot_score_reasons === 'string') {
            return spot.spot_score_reasons.split(',').map(item => item.trim()).filter(Boolean);
        }
        return [];
    },

    async showSpotDetails(spot, event) {
        if (event) event.stopPropagation();
        this.selectedSpot = spot;
        this.selectedSpotExplain = null;
        this.spotExplainError = '';
        this.spotExplainLoading = true;

        try {
            const frequencyKhz = spot.frequency_mhz
                ? Number(spot.frequency_mhz) * 1000
                : Number(spot.frequency || 0);
            const params = new URLSearchParams({
                band: spot.band || '',
                mode: spot.mode || '',
                comment: spot.comment || '',
            });
            if (frequencyKhz > 0) params.set('frequency_khz', String(frequencyKhz));
            const response = await fetch(`/api/spots/explain/${encodeURIComponent(spot.callsign || '')}?${params.toString()}`);
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.detail || data.error || 'Spot explanation failed');
            }
            this.selectedSpotExplain = data;
        } catch (error) {
            console.error('Spot explanation failed:', error);
            this.spotExplainError = error.message || 'Spot explanation failed';
        } finally {
            this.spotExplainLoading = false;
        }
    },

    closeSpotDetails() {
        this.selectedSpot = null;
        this.selectedSpotExplain = null;
        this.spotExplainError = '';
        this.spotExplainLoading = false;
    },
    
    // === Worked QSO Lookup (matches by CALL + BAND + MODE) ===
    
    async loadWorkedCallsigns() {
        try {
            const response = await fetch('/api/wavelog-log/entries?limit=5000');
            if (!response.ok) {
                console.warn('Failed to load worked callsigns');
                return;
            }
            
            const result = await response.json();
            if (result.success && Array.isArray(result.entries)) {
                this.workedCallsigns = window.WavelogQsoNormalizer.buildWorkedMap(result.entries);
                console.log(`✅ Loaded ${Object.keys(this.workedCallsigns).length} worked band/mode combinations from ${result.entries.length} Wavelog QSOs`);
                
                // Log sample for debugging
                const keys = Object.keys(this.workedCallsigns);
                if (keys.length > 0) {
                    console.log(`📝 Sample keys: ${keys.slice(0, 5).join(', ')}`);
                }
            } else {
                console.warn('API response missing success or entries:', result);
            }
        } catch (e) {
            console.error('Error loading worked callsigns:', e);
        }
    },
    
    getWorkedDate(callsign, band, mode) {
        if (!callsign || !band || !mode) return '';
        // Create composite key matching the spot: CALL-BAND-MODE
        const call = callsign.toUpperCase();
        const bandUpper = band.toUpperCase();
        const modeUpper = mode.toUpperCase();
        const key = `${call}-${bandUpper}-${modeUpper}`;
        
        const qso = this.workedCallsigns[key];
        if (qso && qso.qso_date) {
            // Format date from YYYYMMDD to DD/MM/YYYY
            const date = qso.qso_date;
            if (date.length === 8) {
                const year = date.substring(0, 4);
                const month = date.substring(4, 6);
                const day = date.substring(6, 8);
                return `✓ ${day}/${month}/${year}`;
            }
        }
        return '';
    },
    
    isWorkedToday(callsign, band, mode) {
        /**
         * Check if a callsign/band/mode combination was worked today
         * Returns true if the QSO date matches today's date
         */
        if (!callsign || !band || !mode) return false;
        
        // Create composite key matching the spot: CALL-BAND-MODE
        const call = callsign.toUpperCase();
        const bandUpper = band.toUpperCase();
        const modeUpper = mode.toUpperCase();
        const key = `${call}-${bandUpper}-${modeUpper}`;
        
        const qso = this.workedCallsigns[key];
        if (qso && qso.qso_date) {
            // Get today's date in YYYYMMDD format
            const today = new Date();
            const todayStr = 
                today.getFullYear() +
                String(today.getMonth() + 1).padStart(2, '0') +
                String(today.getDate()).padStart(2, '0');
            
            // Compare with QSO date
            return qso.qso_date === todayStr;
        }
        return false;
    },
    
    setVisualSpotWindow(minutes) {
        this.visualSpotWindowMinutes = Number(minutes) || 60;
        this.queueVisualGlobeDraw();
    },

    setVisualMapMode(mode) {
        this.visualMapMode = mode === 'polar' ? 'polar' : 'globe';
        this.queueVisualGlobeDraw();
    },

    setupVisualGlobeRefresh() {
        this.cleanupVisualGlobeRefresh();
        this.ensureVisualCtyData();
        this.visualGlobeRefreshTimer = setInterval(() => {
            if (this.viewMode === 'visual' && this.visualMapMode === 'globe') {
                this.queueVisualGlobeDraw();
            }
        }, 2000);
    },

    cleanupVisualGlobeRefresh() {
        if (this.visualGlobeRefreshTimer) {
            clearInterval(this.visualGlobeRefreshTimer);
            this.visualGlobeRefreshTimer = null;
        }
    },

    queueVisualGlobeDraw() {
        if (this.visualGlobeDrawPending) return;
        this.visualGlobeDrawPending = true;
        setTimeout(() => {
            this.visualGlobeDrawPending = false;
            if (this.viewMode === 'visual' && this.visualMapMode === 'globe') {
                this.drawVisualGlobe();
            }
        }, 0);
    },

    async ensureVisualCtyData() {
        if (this.visualCtyReady || this.visualCtyLoading) return;
        this.visualCtyLoading = true;
        this.visualCtyError = '';
        try {
            const response = await fetch('/api/spots/cty-prefixes');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const text = await response.text();
            this.visualCtyEntries = this.parseVisualCtyContent(text);
            this.visualCtyCountryIndex = this.buildVisualCtyCountryIndex(this.visualCtyEntries);
            this.visualCtyLookupCache = {};
            this.visualCtyReady = this.visualCtyEntries.length > 0;
        } catch (error) {
            console.warn('Could not load visual CTY prefix data:', error);
            this.visualCtyError = 'CTY prefix locations unavailable';
            this.visualCtyEntries = [];
            this.visualCtyCountryIndex = {};
            this.visualCtyReady = false;
        } finally {
            this.visualCtyLoading = false;
            this.queueVisualGlobeDraw();
        }
    },

    splitVisualCsvLine(line) {
        const parts = [];
        let part = '';
        let inQuotes = false;
        for (let i = 0; i < line.length; i += 1) {
            const char = line[i];
            if (char === '"') {
                inQuotes = !inQuotes;
            } else if (char === ',' && !inQuotes) {
                parts.push(part.trim());
                part = '';
            } else {
                part += char;
            }
        }
        if (part.endsWith(';')) part = part.slice(0, -1);
        parts.push(part.trim());
        return parts;
    },

    cleanVisualCtyToken(token) {
        const raw = String(token || '').trim();
        if (!raw || raw === ';') return null;
        const exact = raw.startsWith('=');
        let value = exact ? raw.slice(1) : raw;
        value = value
            .replace(/;$/, '')
            .replace(/[({<\[].*$/, '')
            .replace(/[^A-Za-z0-9/]/g, '')
            .toUpperCase();
        if (!value) return null;
        return { value, exact };
    },

    normalizeVisualCtyLongitude(value) {
        const longitude = Number(value);
        if (!Number.isFinite(longitude) || Math.abs(longitude) > 180) return null;
        return -longitude;
    },

    parseVisualCtyContent(content) {
        const entries = [];
        const addToken = (country, token) => {
            const cleaned = this.cleanVisualCtyToken(token);
            if (!cleaned) return;
            entries.push({
                ...country,
                prefix: cleaned.value,
                exact: cleaned.exact,
            });
        };

        let currentCountry = null;
        String(content || '').split(/\r?\n/).forEach(line => {
            const trimmed = line.trim();
            if (!trimmed) return;
            const parts = this.splitVisualCsvLine(trimmed);
            if (parts.length < 9) {
                if (currentCountry) {
                    trimmed.split(',').forEach(alias => addToken(currentCountry, alias));
                }
                return;
            }
            const latitude = Number(parts[6]);
            const longitude = this.normalizeVisualCtyLongitude(parts[7]);
            if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
            currentCountry = {
                country: parts[1],
                dxcc: Number(parts[2]) || null,
                continent: parts[3],
                cq: Number(parts[4]) || null,
                itu: Number(parts[5]) || null,
                latitude,
                longitude,
            };
            addToken(currentCountry, parts[0]);
            String(parts[9] || '').split(/\s+/).forEach(alias => addToken(currentCountry, alias));
        });

        return entries.sort((a, b) => b.prefix.length - a.prefix.length || Number(b.exact) - Number(a.exact));
    },

    buildVisualCtyCountryIndex(entries) {
        const index = {};
        (entries || []).forEach(entry => {
            const key = this.normalizeVisualCountryName(entry.country);
            if (!key || index[key]) return;
            index[key] = entry;
        });
        return index;
    },

    getVisualCountryLookupName(country) {
        return String(country || '')
            .replace(/^RBL\s+/i, '')
            .trim();
    },

    getVisualCtyInfo(callsign) {
        const call = String(callsign || '').toUpperCase().trim();
        if (!call || !this.visualCtyReady) return null;
        if (Object.prototype.hasOwnProperty.call(this.visualCtyLookupCache, call)) {
            return this.visualCtyLookupCache[call];
        }
        const match = this.visualCtyEntries.find(entry => (
            entry.exact ? call === entry.prefix : call.startsWith(entry.prefix)
        )) || null;
        this.visualCtyLookupCache[call] = match;
        return match;
    },

    getVisualCtyCountryInfo(country) {
        if (!country || !this.visualCtyReady) return null;
        const key = this.normalizeVisualCountryName(this.getVisualCountryLookupName(country));
        return this.visualCtyCountryIndex[key] || null;
    },

    hasVisualCoordinates(spot) {
        if (!spot) return false;
        const lat = Number(spot.latitude ?? spot.lat ?? spot.dxcc_lat);
        const lon = Number(spot.longitude ?? spot.lon ?? spot.lng ?? spot.dxcc_long);
        return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
    },

    enrichVisualSpotFromCty(spot) {
        if (!spot || spot._visualCtyEnriched) return spot;
        const info = this.getVisualCtyInfo(spot.callsign) ||
            this.getVisualCtyCountryInfo(spot.country || spot.dxcc_entity || spot.entity) ||
            this.getVisualTopoCountryInfo(spot.country || spot.dxcc_entity || spot.entity);
        if (!info) return spot;

        if (!spot.country || spot.country === 'UNKNOWN') spot.country = info.country;
        if (!spot.dxcc) spot.dxcc = info.dxcc;
        if (!spot.continent) spot.continent = info.continent;
        if (!spot.cq && !spot.cq_zone && info.cq) spot.cq = info.cq;
        if (!spot.itu && !spot.itu_zone && info.itu) spot.itu = info.itu;
        if (!this.hasVisualCoordinates(spot)) {
            spot.latitude = info.latitude;
            spot.longitude = info.longitude;
            spot.location_source = info.location_source || 'cty_prefix';
        }
        spot._visualCtyEnriched = true;
        return spot;
    },

    async ensureVisualTopoFeatures() {
        if (this.visualTopoFeatures.length > 0 || this.visualTopoLoading) return;
        this.visualTopoLoading = true;
        this.visualTopoError = '';
        try {
            let topo = window.CountryModal && window.CountryModal.topoData ? window.CountryModal.topoData : null;
            if (!topo) {
                const response = await fetch('/api/country/data');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                topo = await response.json();
            }

            if (topo && topo.objects && window.topojson && window.topojson.feature) {
                const object = topo.objects.countries || Object.values(topo.objects)[0];
                const collection = window.topojson.feature(topo, object);
                this.visualTopoFeatures = collection && collection.features ? collection.features : [];
            } else if (topo && Array.isArray(topo.features)) {
                this.visualTopoFeatures = topo.features;
            } else {
                this.visualTopoFeatures = [];
            }
            this.visualTopoCountryIndex = this.buildVisualTopoCountryIndex(this.visualTopoFeatures);
        } catch (error) {
            console.warn('Could not load visual globe country topology:', error);
            this.visualTopoError = 'Country outlines unavailable';
            this.visualTopoFeatures = [];
            this.visualTopoCountryIndex = {};
        } finally {
            this.visualTopoLoading = false;
        }
    },

    async ensureVisualZoneOverlays() {
        if (this.visualZoneOverlayReady || this.visualZoneOverlayLoading) return;
        this.visualZoneOverlayLoading = true;
        this.visualZoneOverlayError = '';
        try {
            const response = await fetch('/api/zone-overlays');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const payload = await response.json();
            this.visualZoneOverlayData = payload && payload.overlays ? payload.overlays : {};
            this.visualZoneOverlayReady = true;
        } catch (error) {
            console.warn('Could not load visual zone overlays:', error);
            this.visualZoneOverlayError = 'Zone overlays unavailable';
            this.visualZoneOverlayData = {};
            this.visualZoneOverlayReady = false;
        } finally {
            this.visualZoneOverlayLoading = false;
        }
    },

    getVisualActiveZoneOverlay() {
        if (this.visualOverlayMode !== 'cq' && this.visualOverlayMode !== 'itu') return null;
        return this.visualZoneOverlayData && this.visualZoneOverlayData[this.visualOverlayMode]
            ? this.visualZoneOverlayData[this.visualOverlayMode]
            : null;
    },

    normalizeVisualCountryName(name) {
        const raw = String(name || '')
            .toUpperCase()
            .replace(/[^A-Z0-9]/g, '');
        const aliases = {
            USA: 'UNITEDSTATES',
            US: 'UNITEDSTATES',
            UNITEDSTATESOFAMERICA: 'UNITEDSTATES',
            UNITEDSTATES: 'UNITEDSTATES',
            ENGLAND: 'UNITEDKINGDOM',
            SCOTLAND: 'UNITEDKINGDOM',
            WALES: 'UNITEDKINGDOM',
            NORTHERNIRELAND: 'UNITEDKINGDOM',
            RUSSIANFEDERATION: 'RUSSIA',
            ASIATICRUSSIA: 'RUSSIA',
            EUROPEANRUSSIA: 'RUSSIA',
            ASIATICTURKEY: 'TURKEY',
            EUROPEANTURKEY: 'TURKEY',
            CZECHREPUBLIC: 'CZECHIA',
            FEDREPOFGERMANY: 'GERMANY',
            FEDERALREPUBLICOFGERMANY: 'GERMANY',
            MADEIRAISLANDS: 'PORTUGAL',
            SOUTHAFRICA: 'SOUTHAFRICA',
        };
        return aliases[raw] || raw;
    },

    getVisualGeometryCentroid(geometry) {
        if (!geometry || !geometry.coordinates) return null;
        const points = [];
        const collectRing = ring => {
            (ring || []).forEach(coord => {
                const lon = Number(coord && coord[0]);
                const lat = Number(coord && coord[1]);
                if (Number.isFinite(lat) && Number.isFinite(lon)) {
                    points.push({ lat, lon });
                }
            });
        };
        if (geometry.type === 'Polygon') {
            geometry.coordinates.forEach(collectRing);
        } else if (geometry.type === 'MultiPolygon') {
            geometry.coordinates.forEach(polygon => polygon.forEach(collectRing));
        }
        if (points.length === 0) return null;
        const totals = points.reduce((acc, point) => ({
            lat: acc.lat + point.lat,
            lon: acc.lon + point.lon,
        }), { lat: 0, lon: 0 });
        return {
            latitude: totals.lat / points.length,
            longitude: totals.lon / points.length,
            location_source: 'country_centroid',
        };
    },

    buildVisualTopoCountryIndex(features) {
        const index = {};
        (features || []).forEach(feature => {
            const name = this.getVisualFeatureName(feature);
            const key = this.normalizeVisualCountryName(name);
            if (!key || index[key]) return;
            const centroid = this.getVisualGeometryCentroid(feature.geometry);
            if (!centroid) return;
            index[key] = {
                country: name,
                ...centroid,
            };
        });
        return index;
    },

    getVisualTopoCountryInfo(country) {
        if (!country) return null;
        const key = this.normalizeVisualCountryName(this.getVisualCountryLookupName(country));
        return this.visualTopoCountryIndex[key] || null;
    },

    cleanVisualCallsign(callsign) {
        let value = String(callsign || '').toUpperCase().trim();
        if (!value) return '';
        value = value.split(/\s+/)[0].split('#')[0].split('-')[0];
        return value.replace(/[^A-Z0-9/]/g, '');
    },

    hashVisualString(value) {
        return String(value || '').split('').reduce((hash, char) => (
            ((hash << 5) - hash + char.charCodeAt(0)) | 0
        ), 0);
    },

    getVisualModeGroup(spot) {
        const mode = String((spot && spot.mode) || '').toUpperCase();
        const rblMode = String((spot && spot.rbl_mode_group) || '').toUpperCase();
        if (mode.includes('CW') || rblMode === 'CW') return 'CW';
        if (mode.includes('SSB') || mode === 'USB' || mode === 'LSB' || rblMode === 'SSB') return 'SSB';
        if (mode.includes('FT') || mode.includes('DIG') || mode.includes('RTTY') || mode.includes('PSK') || rblMode === 'DIGI') return 'DIGI';
        return 'OTHER';
    },

    getVisualModeColor(spot) {
        const colors = {
            CW: '#f6c85f',
            SSB: '#6bb6ff',
            DIGI: '#7dd3c7',
            OTHER: '#c4b5fd',
        };
        return colors[this.getVisualModeGroup(spot)] || colors.OTHER;
    },

    getVisualPathColor(spot) {
        if (this.visualPathColorBy === 'mode') {
            return this.getVisualModeColor(spot);
        }
        return this.getVisualBandColor(spot && spot.band);
    },

    getVisualCountryPaletteColor(countryKey, stat, featureName = '') {
        const palette = this.visualOverlayPalette || [];
        if (palette.length === 0) return 'rgba(121, 201, 176, 0.58)';
        const dxccSeed = Number(stat && stat.dxcc) || 0;
        const cqSeed = stat && stat.cqZones && stat.cqZones.size ? Number([...stat.cqZones][0]) : 0;
        const centroid = this.getVisualTopoCountryInfo(featureName || countryKey);
        const latBin = centroid ? Math.round(Number(centroid.latitude) / 8) : 0;
        const lonBin = centroid ? Math.round(Number(centroid.longitude) / 12) : 0;
        const hash = Math.abs(this.hashVisualString(`${countryKey}:${dxccSeed}:${cqSeed}:${latBin}:${lonBin}`) + latBin * 7 + lonBin * 11);
        return palette[hash % palette.length];
    },

    getVisualFeatureName(feature) {
        const properties = feature && feature.properties ? feature.properties : {};
        return properties.name || properties.NAME || properties.admin || properties.ADMIN || properties.sovereignt || properties.SOVEREIGNT || '';
    },

    getVisualZone(spot, type) {
        if (!spot) return '';
        if (type === 'cq') return String(spot.cq || spot.cq_zone || spot.cqz || '').trim();
        if (type === 'itu') return String(spot.itu || spot.itu_zone || spot.ituz || spot.dxcc_itu || '').trim();
        return '';
    },

    buildVisualZoneActivity(type = this.visualOverlayMode) {
        const activity = new Map();
        this.getVisualSourceSpots().forEach(spot => {
            const zone = this.getVisualZone(spot, type);
            if (!zone) return;
            if (!activity.has(zone)) {
                activity.set(zone, {
                    zone,
                    count: 0,
                    rbl: 0,
                    cluster: 0,
                    needed: 0,
                    topScore: 0,
                });
            }
            const item = activity.get(zone);
            item.count += 1;
            item.topScore = Math.max(item.topScore, this.getSpotScore(spot));
            if ((spot.spot_source || 'cluster') === 'rbl') item.rbl += 1;
            else item.cluster += 1;
            if (this.isVisualNeededSpot(spot)) item.needed += 1;
        });
        return activity;
    },

    buildVisualOverlayStats() {
        const stats = new Map();
        this.getVisualSourceSpots().forEach(spot => {
            const countryKey = this.normalizeVisualCountryName(spot.country || spot.dxcc_entity || spot.entity || '');
            if (!countryKey) return;
            if (!stats.has(countryKey)) {
                stats.set(countryKey, {
                    count: 0,
                    topScore: 0,
                    dxccStatuses: new Set(),
                    callStatuses: new Set(),
                    cqZones: new Set(),
                    ituZones: new Set(),
                    rbl: 0,
                    cluster: 0,
                    dxcc: spot.dxcc || null,
                });
            }
            const item = stats.get(countryKey);
            item.count += 1;
            item.topScore = Math.max(item.topScore, this.getSpotScore(spot));
            if (!item.dxcc && spot.dxcc) item.dxcc = spot.dxcc;
            if (spot.dxcc_status) item.dxccStatuses.add(spot.dxcc_status);
            if (spot.call_status) item.callStatuses.add(spot.call_status);
            const cq = this.getVisualZone(spot, 'cq');
            const itu = this.getVisualZone(spot, 'itu');
            if (cq) item.cqZones.add(cq);
            if (itu) item.ituZones.add(itu);
            if ((spot.spot_source || 'cluster') === 'rbl') item.rbl += 1;
            else item.cluster += 1;
        });
        return stats;
    },

    getVisualOverlaySummary() {
        const stats = this.getVisualSpotStats();
        const overlay = this.buildVisualOverlayStats();
        if (this.visualOverlayMode === 'cq') {
            const zones = new Set();
            overlay.forEach(item => item.cqZones.forEach(zone => zones.add(zone)));
            return `${zones.size} CQ zones`;
        }
        if (this.visualOverlayMode === 'itu') {
            const zones = new Set();
            overlay.forEach(item => item.ituZones.forEach(zone => zones.add(zone)));
            return `${zones.size} ITU zones`;
        }
        return `${overlay.size} DXCC/countries · ${stats.cluster} cluster / ${stats.rbl} RBL`;
    },

    getVisualOverlayBreakdown() {
        const groups = new Map();
        this.getVisualSourceSpots().forEach(spot => {
            let key = '';
            let label = '';
            if (this.visualOverlayMode === 'cq') {
                key = this.getVisualZone(spot, 'cq');
                label = key ? `CQ ${key}` : '';
            } else if (this.visualOverlayMode === 'itu') {
                key = this.getVisualZone(spot, 'itu');
                label = key ? `ITU ${key}` : '';
            } else {
                key = this.normalizeVisualCountryName(spot.country || spot.dxcc_entity || spot.entity || '');
                label = spot.country || spot.dxcc_entity || spot.entity || '';
            }
            if (!key || !label) return;
            if (!groups.has(key)) {
                groups.set(key, {
                    key,
                    label,
                    count: 0,
                    rbl: 0,
                    cluster: 0,
                    needed: 0,
                    topScore: 0,
                });
            }
            const item = groups.get(key);
            item.count += 1;
            item.topScore = Math.max(item.topScore, this.getSpotScore(spot));
            if ((spot.spot_source || 'cluster') === 'rbl') item.rbl += 1;
            else item.cluster += 1;
            if (this.isVisualNeededSpot(spot)) item.needed += 1;
        });
        return [...groups.values()]
            .sort((a, b) => b.needed - a.needed || b.topScore - a.topScore || b.count - a.count || a.label.localeCompare(b.label))
            .slice(0, 10);
    },

    getVisualOverlayColor(stat, featureName = '') {
        if (!stat) return 'rgba(28, 39, 51, 0.62)';
        if (this.visualOverlayMode === 'cq') {
            const first = Number([...stat.cqZones][0] || 0);
            return this.getVisualZoneColor(first || stat.topScore, 40, 0.50);
        }
        if (this.visualOverlayMode === 'itu') {
            const first = Number([...stat.ituZones][0] || 0);
            return this.getVisualZoneColor(first || stat.topScore, 90, 0.50);
        }
        const countryKey = this.normalizeVisualCountryName(featureName);
        return this.getVisualCountryPaletteColor(countryKey, stat, featureName);
    },

    getVisualZoneColor(value, maxValue, alpha = 0.48) {
        const zone = Math.max(1, Number(value || 1));
        const hue = Math.round((zone * 47) % 360);
        return `hsla(${hue}, 72%, 66%, ${alpha})`;
    },

    projectVisualGlobe(lon, lat, width, height) {
        const rotationLon = Number(this.visualGlobeRotation.lon || 0);
        const rotationLat = Number(this.visualGlobeRotation.lat || 0);
        const lambda = this.toRadians(Number(lon) - rotationLon);
        const phi = this.toRadians(Number(lat));
        const phi0 = this.toRadians(rotationLat);
        const cosc = Math.sin(phi0) * Math.sin(phi) + Math.cos(phi0) * Math.cos(phi) * Math.cos(lambda);
        if (cosc < -0.02) return null;
        const scale = Math.min(width, height) * 0.46 * Number(this.visualGlobeZoom || 1);
        return {
            x: width / 2 + scale * Math.cos(phi) * Math.sin(lambda),
            y: height / 2 - scale * (Math.cos(phi0) * Math.sin(phi) - Math.sin(phi0) * Math.cos(phi) * Math.cos(lambda)),
            visible: cosc >= 0,
            cosc,
        };
    },

    interpolateVisualGreatCircle(from, to, steps = 28) {
        const lat1 = this.toRadians(from.lat);
        const lon1 = this.toRadians(from.lon);
        const lat2 = this.toRadians(to.lat);
        const lon2 = this.toRadians(to.lon);
        const delta = 2 * Math.asin(Math.sqrt(
            Math.sin((lat2 - lat1) / 2) ** 2 +
            Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2,
        ));
        if (!Number.isFinite(delta) || delta < 0.00001) return [from, to];

        const points = [];
        for (let i = 0; i <= steps; i += 1) {
            const fraction = i / steps;
            const a = Math.sin((1 - fraction) * delta) / Math.sin(delta);
            const b = Math.sin(fraction * delta) / Math.sin(delta);
            const x = a * Math.cos(lat1) * Math.cos(lon1) + b * Math.cos(lat2) * Math.cos(lon2);
            const y = a * Math.cos(lat1) * Math.sin(lon1) + b * Math.cos(lat2) * Math.sin(lon2);
            const z = a * Math.sin(lat1) + b * Math.sin(lat2);
            const lat = Math.atan2(z, Math.sqrt(x * x + y * y)) * 180 / Math.PI;
            const lon = Math.atan2(y, x) * 180 / Math.PI;
            points.push({ lat, lon });
        }
        return points;
    },

    drawVisualGreatCircle(ctx, path, width, height) {
        const points = this.interpolateVisualGreatCircle(path.from, path.to, 34)
            .map(point => this.projectVisualGlobe(point.lon, point.lat, width, height));
        let drawing = false;
        const screenPoints = [];
        ctx.beginPath();
        points.forEach(point => {
            if (!point || !point.visible || point.cosc < 0.04) {
                drawing = false;
                return;
            }
            screenPoints.push({ x: point.x, y: point.y });
            if (!drawing) {
                ctx.moveTo(point.x, point.y);
                drawing = true;
            } else {
                ctx.lineTo(point.x, point.y);
            }
        });
        ctx.stroke();
        return screenPoints;
    },

    drawVisualGeometryPath(ctx, geometry, width, height) {
        const drawRing = ring => {
            let drawing = false;
            ring.forEach(coord => {
                const projected = this.projectVisualGlobe(coord[0], coord[1], width, height);
                if (!projected || !projected.visible) {
                    drawing = false;
                    return;
                }
                if (!drawing) {
                    ctx.moveTo(projected.x, projected.y);
                    drawing = true;
                } else {
                    ctx.lineTo(projected.x, projected.y);
                }
            });
        };

        if (!geometry) return;
        if (geometry.type === 'Polygon') {
            geometry.coordinates.forEach(drawRing);
        } else if (geometry.type === 'MultiPolygon') {
            geometry.coordinates.forEach(polygon => polygon.forEach(drawRing));
        }
    },

    drawVisualGraticule(ctx, width, height) {
        ctx.save();
        ctx.strokeStyle = 'rgba(116, 142, 168, 0.22)';
        ctx.lineWidth = 1;
        for (let lat = -60; lat <= 60; lat += 30) {
            ctx.beginPath();
            let started = false;
            for (let lon = -180; lon <= 180; lon += 4) {
                const point = this.projectVisualGlobe(lon, lat, width, height);
                if (!point || !point.visible) {
                    started = false;
                    continue;
                }
                if (!started) {
                    ctx.moveTo(point.x, point.y);
                    started = true;
                } else {
                    ctx.lineTo(point.x, point.y);
                }
            }
            ctx.stroke();
        }
        for (let lon = -180; lon <= 180; lon += 30) {
            ctx.beginPath();
            let started = false;
            for (let lat = -90; lat <= 90; lat += 3) {
                const point = this.projectVisualGlobe(lon, lat, width, height);
                if (!point || !point.visible) {
                    started = false;
                    continue;
                }
                if (!started) {
                    ctx.moveTo(point.x, point.y);
                    started = true;
                } else {
                    ctx.lineTo(point.x, point.y);
                }
            }
            ctx.stroke();
        }
        ctx.restore();
    },

    drawVisualZoneLine(ctx, points, width, height) {
        let drawing = false;
        (points || []).forEach(coord => {
            const projected = this.projectVisualGlobe(coord[0], coord[1], width, height);
            if (!projected || !projected.visible || projected.cosc < 0.02) {
                drawing = false;
                return;
            }
            if (!drawing) {
                ctx.moveTo(projected.x, projected.y);
                drawing = true;
            } else {
                ctx.lineTo(projected.x, projected.y);
            }
        });
    },

    drawVisualZoneOverlay(ctx, width, height) {
        const overlay = this.getVisualActiveZoneOverlay();
        if (!overlay) return;

        const isCq = this.visualOverlayMode === 'cq';
        const activity = this.buildVisualZoneActivity(this.visualOverlayMode);
        const lineColor = isCq ? 'rgba(251, 191, 36, 0.72)' : 'rgba(56, 189, 248, 0.72)';
        const activeFill = isCq ? 'rgba(120, 75, 0, 0.82)' : 'rgba(8, 80, 112, 0.82)';
        const activeStroke = isCq ? '#fbbf24' : '#38bdf8';
        const passiveText = isCq ? 'rgba(253, 230, 138, 0.58)' : 'rgba(186, 230, 253, 0.58)';

        ctx.save();
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = Math.max(0.75, Math.min(1.35, Number(this.visualGlobeZoom || 1)));
        ctx.setLineDash([6, 4]);
        (overlay.lines || []).forEach(line => {
            ctx.beginPath();
            this.drawVisualZoneLine(ctx, line.points, width, height);
            ctx.stroke();
        });
        ctx.restore();

        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '800 10px system-ui, sans-serif';
        const showPassiveLabels = Number(this.visualGlobeZoom || 1) >= 1.2;
        (overlay.labels || []).forEach(label => {
            const zone = String(label.zone);
            const zoneActivity = activity.get(zone);
            if (!zoneActivity && !showPassiveLabels) return;
            const point = this.projectVisualGlobe(label.lon, label.lat, width, height);
            if (!point || !point.visible || point.cosc < 0.08) return;
            const text = this.visualOverlayMode === 'cq' ? `CQ ${label.zone}` : `ITU ${label.zone}`;
            const widthPx = ctx.measureText(text).width + 10;
            if (zoneActivity) {
                ctx.fillStyle = activeFill;
                ctx.strokeStyle = activeStroke;
                ctx.lineWidth = 1;
                ctx.beginPath();
                if (typeof ctx.roundRect === 'function') {
                    ctx.roundRect(point.x - widthPx / 2, point.y - 9, widthPx, 18, 4);
                } else {
                    ctx.rect(point.x - widthPx / 2, point.y - 9, widthPx, 18);
                }
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle = '#f8fafc';
            } else {
                ctx.fillStyle = passiveText;
            }
            ctx.fillText(text, point.x, point.y);
        });
        ctx.restore();
    },

    async drawVisualGlobe() {
        const markerCanvas = this.$refs ? this.$refs.visualGlobeCanvas : null;
        const baseCanvas = this.$refs ? this.$refs.visualGlobeBaseCanvas : null;
        const pathCanvas = this.$refs ? this.$refs.visualGlobePathCanvas : null;
        if (!markerCanvas) return;
        await this.ensureVisualTopoFeatures();
        if (this.visualOverlayMode === 'cq' || this.visualOverlayMode === 'itu') {
            await this.ensureVisualZoneOverlays();
        }

        const rect = markerCanvas.getBoundingClientRect();
        const ratio = window.devicePixelRatio || 1;
        const width = Math.max(320, Math.floor(rect.width || 900));
        const height = Math.max(320, Math.floor(rect.height || 520));
        const canvases = [baseCanvas, pathCanvas, markerCanvas].filter(Boolean);
        canvases.forEach(canvas => {
            if (canvas.width !== Math.floor(width * ratio) || canvas.height !== Math.floor(height * ratio)) {
                canvas.width = Math.floor(width * ratio);
                canvas.height = Math.floor(height * ratio);
            }
        });

        const baseCtx = (baseCanvas || markerCanvas).getContext('2d');
        const pathCtx = (pathCanvas || markerCanvas).getContext('2d');
        const markerCtx = markerCanvas.getContext('2d');
        [baseCtx, pathCtx, markerCtx].forEach(ctx => {
            ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
            ctx.clearRect(0, 0, width, height);
        });

        const centerX = width / 2;
        const centerY = height / 2;
        const radius = Math.min(width, height) * 0.46 * Number(this.visualGlobeZoom || 1);
        const overlayStats = this.buildVisualOverlayStats();

        baseCtx.save();
        baseCtx.beginPath();
        baseCtx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        baseCtx.clip();
        const gradient = baseCtx.createRadialGradient(centerX - radius * 0.28, centerY - radius * 0.30, radius * 0.05, centerX, centerY, radius);
        gradient.addColorStop(0, '#20384a');
        gradient.addColorStop(1, '#071018');
        baseCtx.fillStyle = gradient;
        baseCtx.fillRect(0, 0, width, height);
        this.drawVisualGraticule(baseCtx, width, height);

        this.visualTopoFeatures.forEach(feature => {
            const name = this.getVisualFeatureName(feature);
            const stat = overlayStats.get(this.normalizeVisualCountryName(name));
            baseCtx.beginPath();
            this.drawVisualGeometryPath(baseCtx, feature.geometry, width, height);
            baseCtx.fillStyle = this.getVisualOverlayColor(stat, name);
            baseCtx.strokeStyle = stat ? 'rgba(241, 245, 249, 0.52)' : 'rgba(113, 128, 150, 0.34)';
            baseCtx.lineWidth = stat ? 0.9 : 0.55;
            baseCtx.fill();
            baseCtx.stroke();
        });
        this.drawVisualZoneOverlay(baseCtx, width, height);
        baseCtx.restore();

        pathCtx.save();
        pathCtx.beginPath();
        pathCtx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        pathCtx.clip();
        const visiblePaths = [];
        this.getVisualSpotPathItems().forEach(path => {
            pathCtx.save();
            pathCtx.strokeStyle = path.color;
            pathCtx.globalAlpha = Math.min(0.82, 0.24 + Math.max(0, path.score) / 140);
            pathCtx.lineWidth = path.score >= 80 ? 2.1 : path.score >= 55 ? 1.65 : 1.15;
            if ((path.spot.spot_source || 'cluster') === 'rbl') {
                pathCtx.setLineDash([5, 4]);
            } else {
                pathCtx.setLineDash([]);
            }
            const screenPoints = this.drawVisualGreatCircle(pathCtx, path, width, height);
            pathCtx.restore();
            if (screenPoints.length > 1) {
                visiblePaths.push({ ...path, points: screenPoints });
            }

            const fromPoint = this.projectVisualGlobe(path.from.lon, path.from.lat, width, height);
            if (fromPoint && fromPoint.visible) {
                pathCtx.save();
                pathCtx.globalAlpha = 0.86;
                pathCtx.beginPath();
                pathCtx.arc(fromPoint.x, fromPoint.y, 2.6, 0, Math.PI * 2);
                pathCtx.fillStyle = path.color;
                pathCtx.strokeStyle = '#071018';
                pathCtx.lineWidth = 1;
                pathCtx.fill();
                pathCtx.stroke();
                pathCtx.restore();
            }
        });
        this.visualGlobeVisiblePaths = visiblePaths;
        pathCtx.restore();

        const visibleMarkers = [];
        this.getVisualRawSpotItems().slice(0, 180).forEach(item => {
            const point = this.projectVisualGlobe(item.location.lon, item.location.lat, width, height);
            if (!point || !point.visible) return;
            visibleMarkers.push({ ...item, point });
        });

        markerCtx.save();
        markerCtx.beginPath();
        markerCtx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        markerCtx.clip();
        visibleMarkers.forEach(item => {
            const spot = item.spot;
            const score = this.getSpotScore(spot);
            const markerRadius = score >= 80 ? 6 : score >= 55 ? 5 : 4;
            markerCtx.beginPath();
            markerCtx.arc(item.point.x, item.point.y, markerRadius, 0, Math.PI * 2);
            markerCtx.fillStyle = this.getVisualBandColor(spot.band);
            markerCtx.strokeStyle = (spot.spot_source || 'cluster') === 'rbl' ? '#fbbf24' : '#f8fafc';
            markerCtx.lineWidth = this.isVisualSpotSelected(spot) ? 3 : 1.6;
            markerCtx.fill();
            markerCtx.stroke();

            const zone = this.getVisualZone(spot, this.visualOverlayMode);
            if (score >= 80 || spot.local_heard || zone) {
                markerCtx.font = '700 10px system-ui, sans-serif';
                markerCtx.fillStyle = '#f8fafc';
                markerCtx.strokeStyle = '#071018';
                markerCtx.lineWidth = 3;
                const label = zone && this.visualOverlayMode !== 'dxcc' ? `${spot.callsign} z${zone}` : spot.callsign;
                markerCtx.strokeText(label, item.point.x + 7, item.point.y - 7);
                markerCtx.fillText(label, item.point.x + 7, item.point.y - 7);
            }
        });
        this.visualGlobeVisibleMarkers = visibleMarkers;
        markerCtx.restore();

        markerCtx.save();
        markerCtx.beginPath();
        markerCtx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        markerCtx.strokeStyle = 'rgba(191, 219, 254, 0.45)';
        markerCtx.lineWidth = 1.5;
        markerCtx.stroke();
        markerCtx.fillStyle = '#bbf7d0';
        markerCtx.font = '800 11px system-ui, sans-serif';
        markerCtx.textAlign = 'center';
        markerCtx.fillText(`Globe · ${this.visualOverlayMode.toUpperCase()} · drag to rotate · wheel to zoom`, centerX, height - 12);
        markerCtx.restore();
    },

    zoomVisualGlobe(factor) {
        this.visualGlobeZoom = Math.max(0.55, Math.min(5.5, Number(this.visualGlobeZoom || 1) * Number(factor || 1)));
        this.queueVisualGlobeDraw();
    },

    resetVisualGlobeView() {
        this.visualGlobeZoom = 1.1;
        this.centerVisualGlobeOnHome();
    },

    centerVisualGlobeOnHome() {
        const home = this.getVisualHomeLocation();
        this.visualGlobeRotation = {
            lon: Number(home.lon || 0),
            lat: Math.max(-65, Math.min(65, Number(home.lat || 0))),
        };
        this.queueVisualGlobeDraw();
    },

    onVisualGlobeWheel(event) {
        this.zoomVisualGlobe(event.deltaY < 0 ? 1.18 : 0.85);
    },

    startVisualGlobeDrag(event) {
        this.visualGlobeDragging = true;
        this.visualGlobeDragStart = {
            x: event.clientX,
            y: event.clientY,
            lon: Number(this.visualGlobeRotation.lon || 0),
            lat: Number(this.visualGlobeRotation.lat || 0),
        };
    },

    moveVisualGlobeDrag(event) {
        if (!this.visualGlobeDragging || !this.visualGlobeDragStart) return;
        const dx = event.clientX - this.visualGlobeDragStart.x;
        const dy = event.clientY - this.visualGlobeDragStart.y;
        const zoom = Math.max(0.75, Number(this.visualGlobeZoom || 1));
        this.visualGlobeRotation = {
            lon: this.visualGlobeDragStart.lon - (dx * 0.35) / zoom,
            lat: Math.max(-75, Math.min(75, this.visualGlobeDragStart.lat + (dy * 0.25) / zoom)),
        };
        this.queueVisualGlobeDraw();
    },

    onVisualGlobeMouseMove(event) {
        if (this.visualGlobeDragging) {
            this.moveVisualGlobeDrag(event);
            return;
        }
        this.updateVisualGlobeHover(event);
    },

    endVisualGlobeDrag() {
        this.visualGlobeDragging = false;
        this.visualGlobeDragStart = null;
        this.visualGlobeHover = null;
    },

    distanceToVisualSegment(point, a, b) {
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        if (dx === 0 && dy === 0) return Math.hypot(point.x - a.x, point.y - a.y);
        const t = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy)));
        return Math.hypot(point.x - (a.x + t * dx), point.y - (a.y + t * dy));
    },

    getNearestVisualPath(point) {
        return (this.visualGlobeVisiblePaths || [])
            .map(path => {
                let distance = Infinity;
                for (let i = 1; i < path.points.length; i += 1) {
                    distance = Math.min(distance, this.distanceToVisualSegment(point, path.points[i - 1], path.points[i]));
                }
                return { path, distance };
            })
            .sort((a, b) => a.distance - b.distance)[0];
    },

    getVisualEventPoint(event) {
        const canvas = this.$refs ? this.$refs.visualGlobeCanvas : null;
        if (!canvas) return null;
        const rect = canvas.getBoundingClientRect();
        return {
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
        };
    },

    updateVisualGlobeHover(event) {
        const point = this.getVisualEventPoint(event);
        if (!point) return;
        const nearestMarker = (this.visualGlobeVisibleMarkers || [])
            .map(item => ({
                item,
                distance: Math.hypot(item.point.x - point.x, item.point.y - point.y),
            }))
            .sort((a, b) => a.distance - b.distance)[0];
        if (nearestMarker && nearestMarker.distance <= 14) {
            const spot = nearestMarker.item.spot || {};
            const source = (spot.spot_source || 'cluster') === 'rbl' ? 'RBL' : 'Cluster';
            this.visualGlobeHover = {
                x: point.x,
                y: point.y,
                title: `${spot.callsign || '-'} ${spot.band || ''} ${spot.mode || ''}`.trim(),
                lines: [
                    `${source} · score ${this.getSpotScore(spot)}`,
                    `${spot.country || '-'} · CQ ${this.getVisualZone(spot, 'cq') || '-'} · ITU ${this.getVisualZone(spot, 'itu') || '-'}`,
                    `${Math.round(nearestMarker.item.distanceKm).toLocaleString()} km · ${Math.round(nearestMarker.item.bearing)} deg`,
                ],
            };
            return;
        }

        const nearestPath = this.getNearestVisualPath(point);
        if (nearestPath && nearestPath.distance <= 9) {
            const path = nearestPath.path;
            const spot = path.spot || {};
            this.visualGlobeHover = {
                x: point.x,
                y: point.y,
                title: `${path.spotter.callsign} hears ${spot.callsign || '-'}`,
                lines: [
                    `${spot.band || ''} ${spot.mode || ''} · ${path.modeGroup}`,
                    `${Math.round(path.distanceKm).toLocaleString()} km path`,
                    `${path.spotter.country || '-'} to ${spot.country || '-'}`,
                ],
            };
            return;
        }

        this.visualGlobeHover = null;
    },

    focusVisualGlobeClick(event) {
        const point = this.getVisualEventPoint(event);
        if (!point) return;
        const x = point.x;
        const y = point.y;
        const nearest = this.visualGlobeVisibleMarkers
            .map(item => ({
                item,
                distance: Math.hypot(item.point.x - x, item.point.y - y),
            }))
            .sort((a, b) => a.distance - b.distance)[0];
        if (nearest && nearest.distance <= 14) {
            this.focusVisualSpot(nearest.item.spot);
            return;
        }
        const nearestPath = this.getNearestVisualPath(point);
        if (nearestPath && nearestPath.distance <= 9) {
            this.focusVisualSpot(nearestPath.path.spot);
        }
    },

    getVisualHomeGrid() {
        const configured = (
            this.rotorHomeGrid ||
            (this.configData && (this.configData.ROTOR_HOME_GRID || this.configData.FT8_MYGRID)) ||
            (this.ft8 && (this.ft8.mygrid || (this.ft8.config && this.ft8.config.mygrid))) ||
            'JN88'
        );
        return String(configured || 'JN88').toUpperCase().trim();
    },

    gridToLatLon(grid) {
        const value = String(grid || '').toUpperCase().trim();
        if (!/^([A-R]{2}[0-9]{2}|[A-R]{2}[0-9]{2}[A-X]{2}|[A-R]{2}[0-9]{2}[A-X]{2}[0-9]{2})$/.test(value)) {
            return null;
        }

        let lon = (value.charCodeAt(0) - 65) * 20 - 180;
        let lat = (value.charCodeAt(1) - 65) * 10 - 90;
        lon += Number(value[2]) * 2;
        lat += Number(value[3]) * 1;

        let lonSize = 2;
        let latSize = 1;
        if (value.length >= 6) {
            lon += (value.charCodeAt(4) - 65) * (5 / 60);
            lat += (value.charCodeAt(5) - 65) * (2.5 / 60);
            lonSize = 5 / 60;
            latSize = 2.5 / 60;
        }
        if (value.length >= 8 && /^[0-9]{2}$/.test(value.slice(6, 8))) {
            lon += Number(value[6]) * (5 / 600);
            lat += Number(value[7]) * (2.5 / 600);
            lonSize = 5 / 600;
            latSize = 2.5 / 600;
        }

        return {
            lat: lat + latSize / 2,
            lon: lon + lonSize / 2,
        };
    },

    getVisualHomeLocation() {
        return this.gridToLatLon(this.getVisualHomeGrid()) || { lat: 48.2, lon: 17.1 };
    },

    getSpotLocation(spot) {
        if (!spot) return null;
        this.enrichVisualSpotFromCty(spot);
        const latValue = spot.latitude ?? spot.lat ?? spot.dxcc_lat;
        const lonValue = spot.longitude ?? spot.lon ?? spot.lng ?? spot.dxcc_long;
        const lat = Number(latValue);
        const lon = Number(lonValue);
        if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
            return { lat, lon };
        }

        const grid = spot.gridsquare || spot.grid || spot.grid_square || spot.locator || spot.dx_grid;
        return this.gridToLatLon(grid);
    },

    getVisualSpotterLocationFromPayload(payload) {
        if (!payload) return null;
        const lat = Number(payload.latitude ?? payload.lat);
        const lon = Number(payload.longitude ?? payload.lon ?? payload.lng);
        if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
            return null;
        }
        return {
            callsign: payload.callsign || payload.spotter || '',
            country: payload.country || '',
            location: { lat, lon },
            source: payload.location_source || 'cty_prefix',
        };
    },

    getVisualSpotterLocations(spot) {
        if (!spot) return [];
        const locations = [];
        const seen = new Set();
        const addLocation = candidate => {
            if (!candidate || !candidate.callsign) return;
            const key = this.cleanVisualCallsign(candidate.callsign);
            if (!key || seen.has(key)) return;
            seen.add(key);
            locations.push({ ...candidate, callsign: key });
        };

        if (Array.isArray(spot.spotter_locations)) {
            spot.spotter_locations.forEach(payload => addLocation(this.getVisualSpotterLocationFromPayload(payload)));
        }

        const directPayload = this.getVisualSpotterLocationFromPayload({
            callsign: spot.spotter_callsign || spot.spotter,
            country: spot.spotter_country,
            latitude: spot.spotter_latitude,
            longitude: spot.spotter_longitude,
            location_source: 'cty_prefix',
        });
        addLocation(directPayload);

        const rawSpotters = [];
        if (Array.isArray(spot.aggregate_spotters)) rawSpotters.push(...spot.aggregate_spotters.slice(0, 8));
        ['spotter', 'dx_de', 'dxde', 'spotter_call'].forEach(key => {
            if (spot[key]) rawSpotters.push(spot[key]);
        });

        rawSpotters.forEach(raw => {
            const callsign = this.cleanVisualCallsign(raw);
            if (!callsign || seen.has(callsign)) return;
            const info = this.getVisualCtyInfo(callsign);
            if (!info) return;
            addLocation({
                callsign,
                country: info.country,
                location: { lat: Number(info.latitude), lon: Number(info.longitude) },
                source: 'cty_prefix',
            });
        });

        return locations;
    },

    getVisualSpotPathItems() {
        return this.getVisualRawSpotItems()
            .flatMap(item => {
                const spotters = this.getVisualSpotterLocations(item.spot).slice(0, 4);
                return spotters.map(spotter => {
                    const pathDistanceKm = this.calculateDistanceKm(
                        spotter.location.lat,
                        spotter.location.lon,
                        item.location.lat,
                        item.location.lon,
                    );
                    return {
                        key: `${item.key}:${spotter.callsign}`,
                        spot: item.spot,
                        spotter,
                        dx: item,
                        from: spotter.location,
                        to: item.location,
                        distanceKm: pathDistanceKm,
                        modeGroup: this.getVisualModeGroup(item.spot),
                        color: this.getVisualPathColor(item.spot),
                        colorKey: this.visualPathColorBy === 'mode' ? this.getVisualModeGroup(item.spot) : (item.spot.band || 'Unknown'),
                        score: this.getSpotScore(item.spot),
                    };
                });
            })
            .sort((a, b) => b.score - a.score || b.distanceKm - a.distanceKm)
            .slice(0, 280);
    },

    isVisualNeededSpot(spot) {
        const callStatus = String(spot.call_status || '');
        const dxccStatus = String(spot.dxcc_status || '');
        return dxccStatus === 'ATNO' ||
            callStatus.includes('New') ||
            dxccStatus.includes('New') ||
            dxccStatus.startsWith('C/') ||
            dxccStatus.startsWith('W/');
    },

    isVisualHotSpot(spot) {
        return this.getSpotScore(spot) >= 55;
    },

    getVisualQuickFilterPredicate(filterId) {
        const id = filterId || 'all';
        if (id === 'cluster') {
            return spot => (spot.spot_source || 'cluster') !== 'rbl';
        }
        if (id === 'rbl') {
            return spot => (spot.spot_source || 'cluster') === 'rbl';
        }
        if (id === 'needed') {
            return spot => this.isVisualNeededSpot(spot);
        }
        if (id === 'hot') {
            return spot => this.isVisualHotSpot(spot);
        }
        if (id === 'mapped') {
            return spot => Boolean(this.getSpotLocation(spot));
        }
        if (id === 'heard') {
            return spot => Boolean(spot.local_heard);
        }
        return () => true;
    },

    getActiveVisualQuickFilterId() {
        if (this.visualSpotQuickFilter && this.visualSpotQuickFilter !== 'all') {
            return this.visualSpotQuickFilter;
        }
        const sources = this.spotsFilter.spotSources || [];
        if (sources.length === 1 && sources[0] === 'cluster') return 'cluster';
        if (sources.length === 1 && sources[0] === 'rbl') return 'rbl';
        return 'all';
    },

    setVisualQuickFilter(filterId) {
        const id = filterId || 'all';
        if (id === 'all') {
            this.visualSpotQuickFilter = 'all';
            this.showAllSpotSources();
        } else if (id === 'cluster') {
            this.visualSpotQuickFilter = 'all';
            this.showOnlyClusterSpots();
        } else if (id === 'rbl') {
            this.visualSpotQuickFilter = 'all';
            this.showOnlyRblSpots();
        } else {
            this.visualSpotQuickFilter = id;
        }
        this.queueVisualGlobeDraw();
    },

    getVisualQuickFilterItems() {
        const base = this.getVisualBaseSpots();
        const active = this.getActiveVisualQuickFilterId();
        return this.visualQuickFilters.map(filter => ({
            ...filter,
            count: base.filter(this.getVisualQuickFilterPredicate(filter.id)).length,
            active: active === filter.id,
        }));
    },

    applyVisualQuickFilter(spots) {
        const active = this.visualSpotQuickFilter || 'all';
        if (active === 'all') return spots;
        return spots.filter(this.getVisualQuickFilterPredicate(active));
    },

    toRadians(value) {
        return (Number(value) * Math.PI) / 180;
    },

    calculateDistanceKm(fromLat, fromLon, toLat, toLon) {
        const radiusKm = 6371;
        const dLat = this.toRadians(toLat - fromLat);
        const dLon = this.toRadians(toLon - fromLon);
        const lat1 = this.toRadians(fromLat);
        const lat2 = this.toRadians(toLat);
        const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
        return radiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    },

    calculateBearing(fromLat, fromLon, toLat, toLon) {
        const lat1 = this.toRadians(fromLat);
        const lat2 = this.toRadians(toLat);
        const dLon = this.toRadians(toLon - fromLon);
        const y = Math.sin(dLon) * Math.cos(lat2);
        const x = Math.cos(lat1) * Math.sin(lat2) -
            Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
        return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
    },

    getVisualBaseSpots() {
        const nowSeconds = Math.floor(Date.now() / 1000);
        const windowSeconds = Number(this.visualSpotWindowMinutes || 60) * 60;
        let spots = (this.filteredSpots || []).filter(spot => {
            const timestamp = this.getSpotTimestamp(spot);
            if (!timestamp) return true;
            return nowSeconds - timestamp <= windowSeconds;
        });

        if (this.visualSpotLatestOnly) {
            const latestByCall = new Map();
            spots.forEach(spot => {
                const key = String(spot.callsign || '').toUpperCase();
                const current = latestByCall.get(key);
                if (!current || this.getSpotTimestamp(spot) > this.getSpotTimestamp(current)) {
                    latestByCall.set(key, spot);
                }
            });
            spots = [...latestByCall.values()];
        }

        return spots.map(spot => this.enrichVisualSpotFromCty(spot));
    },

    getVisualSourceSpots() {
        return this.applyVisualQuickFilter(this.getVisualBaseSpots());
    },

    getVisualRawSpotItems() {
        const home = this.getVisualHomeLocation();
        return this.getVisualSourceSpots()
            .map(spot => {
                const location = this.getSpotLocation(spot);
                if (!location) return null;
                const distanceKm = this.calculateDistanceKm(home.lat, home.lon, location.lat, location.lon);
                const bearing = this.calculateBearing(home.lat, home.lon, location.lat, location.lon);
                return {
                    key: this.getSpotIdentityKey(spot),
                    spot,
                    location,
                    distanceKm,
                    bearing,
                };
            })
            .filter(Boolean)
            .sort((a, b) => this.getSpotScore(b.spot) - this.getSpotScore(a.spot) || b.distanceKm - a.distanceKm);
    },

    getVisualMapRadiusKm() {
        const maxDistance = Math.max(0, ...this.getVisualRawSpotItems().map(item => item.distanceKm));
        const targets = [1000, 2000, 3500, 5000, 7500, 10000, 15000, 20000];
        return targets.find(radius => radius >= maxDistance) || 20000;
    },

    getVisualSpotItems() {
        const radiusKm = this.getVisualMapRadiusKm();
        const center = 260;
        const maxRadius = 240;
        return this.getVisualRawSpotItems().slice(0, 160).map(item => {
            const angle = this.toRadians(item.bearing);
            const radius = Math.min(maxRadius, Math.max(10, (item.distanceKm / radiusKm) * maxRadius));
            const score = this.getSpotScore(item.spot);
            return {
                ...item,
                x: center + Math.sin(angle) * radius,
                y: center - Math.cos(angle) * radius,
                labelX: center + Math.sin(angle) * (radius + 11),
                labelY: center - Math.cos(angle) * (radius + 11),
                radius: score >= 80 ? 6.5 : score >= 55 ? 5.4 : 4.2,
                lineOpacity: score >= 55 ? 0.48 : 0.22,
            };
        });
    },

    getVisualSpotLabelItems() {
        return this.getVisualSpotItems()
            .filter(item => this.isVisualSpotSelected(item.spot) || this.getSpotScore(item.spot) >= 80 || item.spot.local_heard)
            .slice(0, 18);
    },

    getVisualSpotStats() {
        const source = this.getVisualSourceSpots();
        const plotted = this.getVisualRawSpotItems();
        const rbl = plotted.filter(item => (item.spot.spot_source || 'cluster') === 'rbl').length;
        const cluster = plotted.length - rbl;
        return {
            total: source.length,
            plotted: plotted.length,
            hidden: Math.max(0, source.length - plotted.length),
            rbl,
            cluster,
            paths: this.getVisualSpotPathItems().length,
        };
    },

    getVisualBandColor(band) {
        const colors = {
            '160m': '#8b5cf6',
            '80m': '#38bdf8',
            '60m': '#22c55e',
            '40m': '#84cc16',
            '30m': '#eab308',
            '20m': '#ef4444',
            '17m': '#f97316',
            '15m': '#ec4899',
            '12m': '#14b8a6',
            '10m': '#f59e0b',
            '6m': '#a855f7',
        };
        return colors[band] || '#cbd5e1';
    },

    getVisualLegendBands() {
        return [...new Set(this.getVisualSpotItems().map(item => item.spot.band || 'Unknown'))]
            .sort((a, b) => this.availableBands.indexOf(a) - this.availableBands.indexOf(b));
    },

    getVisualPathLegendItems() {
        const paths = this.getVisualSpotPathItems();
        if (this.visualPathColorBy === 'mode') {
            const groups = new Set(paths.map(path => path.modeGroup));
            const order = ['CW', 'SSB', 'DIGI', 'OTHER'];
            return order
                .filter(group => groups.has(group))
                .map(group => ({
                    label: `${group} paths`,
                    color: this.getVisualModeColor({ mode: group === 'DIGI' ? 'FT8' : group }),
                }));
        }
        const bands = [...new Set(paths.map(path => path.spot.band || 'Unknown'))]
            .sort((a, b) => this.availableBands.indexOf(a) - this.availableBands.indexOf(b));
        return bands.map(band => ({
            label: `${band} paths`,
            color: this.getVisualBandColor(band),
        }));
    },

    getVisualSpotClass(spot) {
        const classes = [];
        if ((spot.spot_source || 'cluster') === 'rbl') classes.push('rbl');
        if (spot.local_heard) classes.push('heard');
        if (this.getSpotScore(spot) >= 80) classes.push('hot');
        if (this.getSpotScore(spot) >= 55) classes.push('good');
        if (spot.dxcc_status === 'Confirmed' || spot.call_status === 'Confirmed') classes.push('confirmed');
        return classes.join(' ');
    },

    getVisualSpotTitle(item) {
        if (!item) return '';
        const spot = item.spot || {};
        const source = (spot.spot_source || 'cluster') === 'rbl' ? 'RBL' : 'Cluster';
        return `${spot.callsign || '-'} ${spot.band || ''} ${spot.mode || ''} · ${Math.round(item.distanceKm).toLocaleString()} km · ${Math.round(item.bearing)}° · ${source}`;
    },

    focusVisualSpot(spot) {
        this.showSpotDetails(spot);
    },

    isVisualSpotSelected(spot) {
        return Boolean(this.selectedSpot && spot && this.getSpotIdentityKey(this.selectedSpot) === this.getSpotIdentityKey(spot));
    },

    // Get band from frequency
    getBandFromFrequency(freqMhz) {
        // Ensure frequency is a number (handle object/string cases)
        if (freqMhz === null || freqMhz === undefined) return '';
        
        const freq = typeof freqMhz === 'number' ? freqMhz : parseFloat(freqMhz);
        
        // If conversion failed or result is NaN, return empty string
        if (isNaN(freq)) return '';
        
        if (freq >= 1.8 && freq <= 2.0) return '160m';
        if (freq >= 3.5 && freq <= 4.0) return '80m';
        if (freq >= 5.3 && freq <= 5.4) return '60m';
        if (freq >= 7.0 && freq <= 7.3) return '40m';
        if (freq >= 10.1 && freq <= 10.15) return '30m';
        if (freq >= 14.0 && freq <= 14.35) return '20m';
        if (freq >= 18.068 && freq <= 18.168) return '17m';
        if (freq >= 21.0 && freq <= 21.45) return '15m';
        if (freq >= 24.89 && freq <= 24.99) return '12m';
        if (freq >= 28.0 && freq <= 29.7) return '10m';
        if (freq >= 50.0 && freq <= 54.0) return '6m';
        return 'Unknown';
    }
};

// Computed properties for DX spots
const dxSpotsComputed = {
    // Filtered spots based on current filters
    filteredSpots() {
        // === STRATEGY ===
        // - If filters are active and we have database results, use those  
        // - If filters are active but still searching, fall back to cache-based results (better UX than blank)
        // - Otherwise use local cache filtering
        // - Real-time spots are added to filteredSearchResults when they match filters
        
        // If database search results are available, use them
        if (this.hasActiveFilters() && this.filteredSearchResults.length > 0) {
            console.log(`📊 Using ${this.filteredSearchResults.length} spots from database search`);
            
            // Apply local-only filters: worked b4 and DXCC status
            // (Other filters like band, mode, zones, continents, callsign, special_tags are already applied by database)
            let filtered = this.filteredSearchResults;
            filtered = this.applySourceAndRblFilters(filtered);
            
            // DXCC Status filter (not available in database query)
            // Note: database results have 'tag' field if DXCC status was computed
            if (this.spotsFilter.dxccStatuses.length > 0) {
                filtered = filtered.filter(spot => {
                    const spotStatus = spot.tag || spot.dxcc_status;
                    return spotStatus && this.spotsFilter.dxccStatuses.includes(spotStatus);
                });
            }
            
            // Worked b4 filter (requires local QSO data)
            if (this.spotsFilter.workedB4Include || this.spotsFilter.workedB4Exclude) {
                filtered = filtered.filter(spot => {
                    const isWorked = !!this.getWorkedDate(spot.callsign, spot.band, spot.mode);
                    
                    if (this.spotsFilter.workedB4Include && this.spotsFilter.workedB4Exclude) {
                        return true;
                    } else if (this.spotsFilter.workedB4Include) {
                        return isWorked;
                    } else if (this.spotsFilter.workedB4Exclude) {
                        return !isWorked;
                    }
                    return true;
                });
            }
            
            filtered = this.filterRblNoise(filtered);
            filtered = this.sortVisibleSpots(filtered);
            return filtered.slice(0, this.maxSpots);
        }
        
        // Fall back to cache-based filtering when no filters active
        let filtered = this.dxSpots || [];
        
        // Callsign filter
        if (this.spotsFilter.callsign) {
            const searchTerm = this.spotsFilter.callsign.toLowerCase();
            filtered = filtered.filter(spot => 
                spot.callsign.toLowerCase().includes(searchTerm)
            );
        }
        
        // Band filter - use spot.band directly from backend
        if (this.spotsFilter.bands.length > 0) {
            filtered = filtered.filter(spot => 
                this.spotsFilter.bands.includes(spot.band)
            );
        }
        
        // Mode filter
        if (this.spotsFilter.modes.length > 0) {
            filtered = filtered.filter(spot => 
                this.spotsFilter.modes.includes(spot.mode)
            );
        }
        
        // Continent filter - spotter_continent is the correct field from backend
        if (this.spotsFilter.continents.length > 0) {
            filtered = filtered.filter(spot => 
                this.spotsFilter.continents.includes(spot.spotter_continent)
            );
        }
        
        // CQ Zone filter - backend sends 'cq' as string, need to convert filter values to strings
        if (this.spotsFilter.cqs.length > 0) {
            const cqStrings = this.spotsFilter.cqs.map(cq => String(cq));
            filtered = filtered.filter(spot => 
                cqStrings.includes(String(spot.cq))
            );
        }
        
        // Call Status filter
        if (this.spotsFilter.callStatuses.length > 0) {
            filtered = filtered.filter(spot => 
                this.spotsFilter.callStatuses.includes(spot.call_status)
            );
        }
        
        // DXCC Status filter
        if (this.spotsFilter.dxccStatuses.length > 0) {
            filtered = filtered.filter(spot => 
                this.spotsFilter.dxccStatuses.includes(spot.tag || spot.dxcc_status)
            );
        }
        
        // Special activities filter
        if (this.spotsFilter.specials.length > 0) {
            filtered = filtered.filter(spot => {
                if (!spot.special) return false;
                // spot.special contains comma-separated list of matches (e.g., "POTA, WWFF")
                return this.spotsFilter.specials.some(special => 
                    spot.special.includes(special)
                );
            });
        }

        filtered = this.applySourceAndRblFilters(filtered);
        
        // Worked b4 filter
        if (this.spotsFilter.workedB4Include || this.spotsFilter.workedB4Exclude) {
            filtered = filtered.filter(spot => {
                const isWorked = !!this.getWorkedDate(spot.callsign, spot.band, spot.mode);
                
                if (this.spotsFilter.workedB4Include && this.spotsFilter.workedB4Exclude) {
                    // Both checked: include all spots (no filter)
                    return true;
                } else if (this.spotsFilter.workedB4Include) {
                    // Only include worked spots
                    return isWorked;
                } else if (this.spotsFilter.workedB4Exclude) {
                    // Only exclude worked spots (show unworked)
                    return !isWorked;
                }
                return true;
            });
        }
        
        filtered = this.filterRblNoise(filtered);
        filtered = this.sortVisibleSpots(filtered);
        return filtered.slice(0, this.maxSpots);
    }
};

// Export for use in main app
window.FlexRadioSpots = {
    data: dxSpotsData,
    methods: dxSpotsMethods,
    computed: dxSpotsComputed
};
