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
        workedB4Include: false,
        workedB4Exclude: false,
    },
    
    // Filtered search from database
    filteredSearchResults: [],
    isSearchingSpots: false,
    lastSearchFilter: null,
    filteredSearchWarning: '',
    filteredSearchRetryAfter: 0,
    
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
        this.spotsFilter.callsign = '';
        this.spotsFilter.bands = [];
        this.spotsFilter.modes = [];
        this.spotsFilter.continents = [];
        this.spotsFilter.cqs = [];
        this.spotsFilter.callStatuses = [];
        this.spotsFilter.dxccStatuses = [];
        this.spotsFilter.specials = [];
        this.spotsFilter.workedB4Include = false;
        this.spotsFilter.workedB4Exclude = false;
        this.filteredSearchResults = [];
        this.lastSearchFilter = null;
        this.filteredSearchWarning = '';
        this.filteredSearchRetryAfter = 0;
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
            
            // Build filter criteria for API
            const filterCriteria = {
                limit: this.maxSpots,
                callsign: this.spotsFilter.callsign || null,
                bands: this.spotsFilter.bands.length > 0 ? this.spotsFilter.bands : null,
                modes: this.spotsFilter.modes.length > 0 ? this.spotsFilter.modes : null,
                zones_cq: this.spotsFilter.cqs.length > 0 ? this.spotsFilter.cqs : null,
                continents: this.spotsFilter.continents.length > 0 ? this.spotsFilter.continents : null,
                special_tags: this.spotsFilter.specials.length > 0 ? this.spotsFilter.specials : null,
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
        return !!(
            this.spotsFilter.callsign ||
            this.spotsFilter.bands.length > 0 ||
            this.spotsFilter.modes.length > 0 ||
            this.spotsFilter.continents.length > 0 ||
            this.spotsFilter.cqs.length > 0 ||
            this.spotsFilter.callStatuses.length > 0 ||
            this.spotsFilter.dxccStatuses.length > 0 ||
            this.spotsFilter.specials.length > 0 ||
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
                spot.special_tags && spot.special_tags.includes(special)
            );
            if (!hasSpecial) {
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
            case 'workedB4':
                return this.spotsFilter.workedB4Include || this.spotsFilter.workedB4Exclude;
            default:
                return false;
        }
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
        
        return filtered.slice(0, this.maxSpots);
    }
};

// Export for use in main app
window.FlexRadioSpots = {
    data: dxSpotsData,
    methods: dxSpotsMethods,
    computed: dxSpotsComputed
};
