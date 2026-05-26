// Main Application Entry Point
// FlexRadio Web Control v2.0 - Main Vue App

console.log('✅ Loading app-main.js module...');

const { createApp } = Vue;

// ⚡ CRITICAL FIX: Prevent double mounting
let templatesReady = false;
let vueMounted = false;

// Listen for templates to finish loading before mounting Vue
document.addEventListener('templates-loaded', () => {
    console.log('📋 Templates loaded - ready to mount Vue app');
    templatesReady = true;
    if (!vueMounted) {
        mountVueApp();
    }
});

// ⚡ CRITICAL FIX: Increased timeout to 10 seconds and prevent double mounting
setTimeout(() => {
    if (!templatesReady && !vueMounted) {
        console.warn('⚠️ Templates took too long to load (10s timeout), mounting Vue anyway...');
        mountVueApp();
    } else if (vueMounted) {
        console.log('✅ Vue already mounted, skipping fallback mount');
    }
}, 10000);

// Wrap Vue app creation in a function to be called after templates load
function mountVueApp() {
    // Verify all required modules are loaded
    console.log('🔍 Checking module dependencies...');
    console.log('FlexRadioCore:', window.FlexRadioCore ? '✅' : '❌');
    console.log('FlexRadioWebSocket:', window.FlexRadioWebSocket ? '✅' : '❌');
    console.log('FlexRadioControls:', window.FlexRadioControls ? '✅' : '❌');
    console.log('FlexRadioUtils:', window.FlexRadioUtils ? '✅' : '❌');
    console.log('FlexRadioSpots:', window.FlexRadioSpots ? '✅' : '❌');
    console.log('SDCTicker:', window.SDCTicker ? '✅' : '❌');
    console.log('RadioControlConfig:', window.RadioControlConfig ? '✅' : '❌');
    console.log('RadioControlSolar:', window.RadioControlSolar ? '✅' : '❌');
    console.log('RadioControlWavelogStats:', window.RadioControlWavelogStats ? '✅' : '❌');

    // Check if all required modules are available
    if (!window.FlexRadioCore || !window.FlexRadioWebSocket || !window.FlexRadioControls || 
        !window.FlexRadioUtils || !window.FlexRadioSpots || !window.SDCTicker ||
        !window.RadioControlConfig || !window.RadioControlSolar || !window.RadioControlWavelogStats) {
        console.error('❌ Missing required modules! Cannot create Vue app.');
        console.error('Make sure all JavaScript files are loaded in the correct order.');
        throw new Error('Missing required modules');
    }

    // Create the main Vue application
    createApp({
    data() {
        return {
            // Merge all module data
            ...window.FlexRadioCore.data,
            ...window.FlexRadioSpots.data,
            ...window.SDCTicker.data,
            ...window.RadioControlConfig.data,
            ...window.RadioControlSolar.data,
            ...window.RadioControlWavelogStats.data,
            ...(window.ft8ModalMixin ? window.ft8ModalMixin.data() : {}),
            
            // Additional data properties that weren't in core
            sliderDebounceTimers: {},
            statusMessage: null,
            currentTime: '00:00:00',
            spotsFilterDebounceTimer: null,  // Debounce timer for spots filter changes
            
            // Additional Information modal
            showAdditionalInfoModal: false,
            
            // Rotator Control (data properties for UI state)
            rotorAzimuth: 0,
            rotorPreset: '',
            rotorStatus: null,
            rotorConnected: false,
            rotorInputFocused: false,
            
            // Rotator AUTO Control
            rotorAutoEnabled: false,
            rotorAutoTimer: null,
            rotorAutoPending: null,  // Callsign/info of pending AUTO action
            rotorHomeGrid: 'JN88TQ',
            rotorHomeLat: 48.17,
            rotorHomeLon: 17.08,
            rotorBands: {
                "160m": false, "80m": false, "60m": false, "40m": false, "30m": false,
                "20m": true, "17m": true, "15m": true, "12m": true, "10m": true,
                "6m": false, "2m": false
            },
            
            // Beaming display (SP/LP bearing info)
            currentBeamingCallsign: null,
            shortPathBearing: null,
            longPathBearing: null,
            lastBeamingTime: null,
            
            // WinKeyer Data
            winkeyer: {
                enabled: false,
                isConnected: false,
                currentWpm: 20,
                showWpmSlider: false,
                memories: {
                    M1: 'CQ DE OM0RX',
                    M2: 'UR RST 599',
                    M3: 'QSL TU DE OM0RX',
                    M4: 'MNI TU'
                },
                status: 'Disconnected',
                logs: [],
                lastError: null,
                connectionTime: null,
                config: {
                    port: 'COM3',
                    baudRate: 1200,
                    defaultWpm: 20
                }
            },
            
            // === Logging Form Data ===
            loggingForm: {
                // Station Tab
                callsign: '',
                date: new Date().toISOString().split('T')[0],
                time_off: (() => {
                    const now = new Date();
                    const h = String(now.getUTCHours()).padStart(2, '0');
                    const m = String(now.getUTCMinutes()).padStart(2, '0');
                    const s = String(now.getUTCSeconds()).padStart(2, '0');
                    return `${h}:${m}:${s}`;
                })(),
                frequency: null,  // Will track current radioStatus.frequency
                band: '',         // CRITICAL: Needed for "Worked b4" matching (CALL-BAND-MODE key)
                mode: 'SSB',      // Default mode, will track current radioStatus.mode
                rst_sent: 599,    // Default RST
                rst_received: 599, // Default RST
                name: '',
                qth: '',
                gridsquare: '',
                pota: '',
                sota: '',
                wwff: '',
                iota: '',
                notes: '',
                
                // General Tab
                continent: '',
                cq_zone: '',
                itu_zone: '',
                region: '',
                country: '',
                state: '',
                us_county: '',
                tx_pwr: '',
                ant: '',
                
                // QSL Tab
                qsl_rcvd: 'N',
                qsl_sent: 'N',
                lotw_member: false,
                qsl_manager: '',
                email: '',
                
                // SAT Tab
                prop_mode: '',
                ant_path: '',
                sat_name: '',
                sat_mode: '',
                freq_rx: '',
                mode_rx: '',
            },
            activeLogTab: 'station',
            loggingStatus: null,
            loggingPanelSectionCollapsed: false,
            
            // Interface Layout Mode
            interfaceLayout: localStorage.getItem('interfaceLayout') || 'full', // 'full' or 'compact'
            
            // Modal Visibility Flags
            showQRZProfileModal: false,
            showDXCCWavelogModal: false,
            
            // QRZ Profile Data
            qrzProfile: {},
            qrzHistory: [],
            qrzLoading: false,
            
            // DXCC Status Data
            dxccStatus: {},
            dxccBands: {},
            dxccLoading: false,
            dxccLookupTimer: null,  // Debounce timer for callsign lookup
            
            // Previous QSOs Data
            previousQSOs: [],
            previousQSOsLoading: false,
            allPreviousQSOs: [],
            showPrevQSOsDropdown: false,
            closeDropdownTimeout: null,
            currentPrevQSOsPage: 1,
            prevQSOsPerPage: 5,
            prevQSOsActiveTab: 'wavelog',
            allLocalLogQSOs: [],
            currentLocalLogPage: 1,
            localLogPerPage: 5,
            
            // QRZ Profile Data
            qrzProfile: { success: false },
            qrzLoading: false,
            qrzHistory: [],
            
            // DXCC Status Data
            dxccStatus: { success: false },
            dxccLoading: false,
            dxccBands: {},
            dxccLookupTimer: null,
            
            bandList: ['160m', '80m', '60m', '40m', '30m', '20m', '17m', '15m', '12m', '10m'],
            
            // Additional properties that might be missing
            openDropdown: null,
            clusterConnected: false,
            agcSlider: 2, // Default to 'med' (index 2 in ['off', 'slow', 'med', 'fast'])
            
            // Wavelog Log Viewer Data
            viewMode: 'spots',  // 'spots' or 'log'
            logEntries: [],
            logLoading: false,
            logError: null,
            logLimit: 100,
            logStats: null,
            availableLogLimits: [50, 100, 250, 500],
            logColumns: [],  // Will be populated by wavelog-log-viewer.js
            showColumnConfig: false,
            logFilters: {
                callsign: '',
                mode: '',
                band: '',
                country: '',
                name: '',
                gridsquare: '',
                cqz: '',
                ituz: '',
                dxcc: '',
                state: '',
                pota_ref: '',
                sota_ref: '',
                wwff_ref: '',
                iota: '',
                comment: ''
            },
            resizingColumn: null,
            resizeStartX: 0,
            resizeStartWidth: 0,
            
            // Callsign Search Modal Data
            showCallsignSearchModal: false,
            callsignSearchQuery: '',
            callsignSearchResults: null,
            callsignSearchLoading: false,
            callsignSearchError: null,
            matrixBands: ['160m', '80m', '60m', '40m', '30m', '20m', '17m', '15m', '12m', '10m'],
            matrixModes: ['CW', 'FT8', 'RTTY', 'SSB', 'LSB', 'USB'],
            
            // Prev QSOs Modal Data (duplicate of callsign search for independent use)
            showPrevQsosModal: false,
            prevQsosCallsign: '',
            prevQsosResults: null,
            prevQsosLoading: false,
            prevQsosError: null,
            prevQsosSortColumn: null,
            prevQsosSortDirection: 'asc',
        };
    },
    
    computed: {
        // Merge all computed properties
        ...window.FlexRadioCore.computed,
        ...window.FlexRadioSpots.computed,
        ...window.RadioControlConfig.computed,
        
        // Wavelog Log Viewer - Filter Options
        uniqueModes() {
            if (!this.logEntries || this.logEntries.length === 0) return [];
            const modes = [...new Set(this.logEntries.map(e => e.mode).filter(Boolean))];
            return modes.sort();
        },
        
        uniqueBands() {
            if (!this.logEntries || this.logEntries.length === 0) return [];
            const bands = [...new Set(this.logEntries.map(e => e.band).filter(Boolean))];
            return bands.sort((a, b) => {
                // Sort bands numerically (160m, 80m, 40m, etc.)
                const aNum = parseInt(a);
                const bNum = parseInt(b);
                if (!isNaN(aNum) && !isNaN(bNum)) return bNum - aNum;
                return a.localeCompare(b);
            });
        },
        
        uniqueCqZones() {
            if (!this.logEntries || this.logEntries.length === 0) return [];
            const zones = [...new Set(this.logEntries.map(e => e.cqz).filter(Boolean))];
            return zones.sort((a, b) => parseInt(a) - parseInt(b));
        },
        
        ...window.RadioControlSolar.computed,
        ...window.RadioControlWavelogStats.computed,
        
        // Pagination for Previous QSOs
        prevQSOsPageCount() {
            return Math.ceil(this.allPreviousQSOs.length / this.prevQSOsPerPage);
        },
        
        paginatedPreviousQSOs() {
            const start = (this.currentPrevQSOsPage - 1) * this.prevQSOsPerPage;
            const end = start + this.prevQSOsPerPage;
            return this.allPreviousQSOs.slice(start, end);
        },
        
        isPrevQSOsFirstPage() {
            return this.currentPrevQSOsPage === 1;
        },
        
        isPrevQSOsLastPage() {
            return this.currentPrevQSOsPage === this.prevQSOsPageCount;
        },
        
        // Sorted Prev QSOs for modal
        sortedPrevQsos() {
            if (!this.prevQsosResults || !this.prevQsosResults.qsos) return [];
            
            const qsos = [...this.prevQsosResults.qsos];
            
            if (!this.prevQsosSortColumn) return qsos;
            
            return qsos.sort((a, b) => {
                let aValue, bValue;
                
                if (this.prevQsosSortColumn === 'mode') {
                    aValue = a.mode || '';
                    bValue = b.mode || '';
                    const comparison = aValue.localeCompare(bValue);
                    return this.prevQsosSortDirection === 'asc' ? comparison : -comparison;
                }
                
                if (this.prevQsosSortColumn === 'band') {
                    aValue = a.band || '';
                    bValue = b.band || '';
                    
                    // Extract numeric part for proper band sorting (160m, 80m, 40m, etc.)
                    const aNum = parseInt(aValue);
                    const bNum = parseInt(bValue);
                    
                    let comparison;
                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        // Numeric comparison for bands
                        comparison = aNum - bNum;
                    } else {
                        // Alphabetic comparison for non-standard bands
                        comparison = aValue.localeCompare(bValue);
                    }
                    
                    return this.prevQsosSortDirection === 'asc' ? comparison : -comparison;
                }
                
                return 0;
            });
        },
        
        // Pagination for Local Log QSOs (in Prev QSOs modal)
        localLogPageCount() {
            return Math.ceil(this.allLocalLogQSOs.length / this.localLogPerPage);
        },
        
        paginatedLocalLogQSOs() {
            const start = (this.currentLocalLogPage - 1) * this.localLogPerPage;
            const end = start + this.localLogPerPage;
            return this.allLocalLogQSOs.slice(start, end);
        },
        
        isLocalLogFirstPage() {
            return this.currentLocalLogPage === 1;
        },
        
        isLocalLogLastPage() {
            return this.currentLocalLogPage === this.localLogPageCount;
        },
        
        // Format main frequency display with full precision
        formattedFrequency() {
            return this.formatFrequencyForDisplay(this.radioStatus.frequency);
        },
        
        // Format sub VFO frequency display
        formattedSubFreq() {
            return this.formatFrequencyForDisplay(this.subVfoFreq);
        },
    },
    
    watch: {
        // Watch for callsign changes to trigger lookups
        'loggingForm.callsign'(newCallsign, oldCallsign) {
            if (newCallsign && newCallsign.trim()) {
                // Update beaming display to show new callsign
                this.currentBeamingCallsign = newCallsign;
                // Reset bearings when new callsign is entered (will be recalculated if needed)
                this.shortPathBearing = null;
                this.longPathBearing = null;
                
                if (newCallsign !== oldCallsign && newCallsign.length >= 3) {
                    // Debounce the lookup
                    if (this.dxccLookupTimer) {
                        clearTimeout(this.dxccLookupTimer);
                    }
                    this.dxccLookupTimer = setTimeout(() => {
                        this.loadQRZProfile();
                        this.loadDXCCStatus();
                        this.loadPreviousQSOs();
                    }, 500);
                }
            } else {
                // Clear beaming display when callsign is cleared
                this.currentBeamingCallsign = null;
                this.shortPathBearing = null;
                this.longPathBearing = null;
            }
        },
        
        // Watch for mode changes to update filter presets
        'radioStatus.mode'(newMode) {
            // Sync mode to logging form when radio mode changes
            const convertedMode = newMode === 'USB' || newMode === 'LSB' ? 'SSB' : newMode;
            this.loggingForm.mode = convertedMode;
            
            // Update current step index when mode changes
            if (this.stepsByMode[newMode]) {
                this.currentStepIndex = Math.min(this.currentStepIndex, this.stepsByMode[newMode].length - 1);
            }
        },
        
        // Clear SDC buffer when frequency changes (tuning to new frequency)
        'radioStatus.frequency'(newFrequency) {
            // Update the logging form frequency immediately when radio frequency changes
            this.loggingForm.frequency = newFrequency;
            
            // Also update the band when frequency changes
            if (newFrequency && typeof newFrequency === 'number') {
                this.loggingForm.band = this.getBandFromFrequency(newFrequency);
            }
            
            // Clear SDC buffer when frequency changes (tuning to new frequency)
            this.clearSDCBuffer();
        },
        
        // Watch for DX spots filter changes to trigger database search
        spotsFilter: {
            async handler(newFilter) {
                console.log('🔔 Spots filter changed, triggering search...');
                // Call the filtered search method with a small debounce to avoid rapid consecutive calls
                if (this.spotsFilterDebounceTimer) {
                    clearTimeout(this.spotsFilterDebounceTimer);
                }
                this.spotsFilterDebounceTimer = setTimeout(() => {
                    this.performFilteredSearch();
                }, 300);
            },
            deep: true  // Watch nested properties in the filter object
        },
        
        // Watch for maxSpots changes to refetch with new limit if filters are active
        maxSpots() {
            if (this.hasActiveFilters() && this.filteredSearchResults.length > 0) {
                console.log(`🔄 maxSpots changed to ${this.maxSpots}, refetching...`);
                this.performFilteredSearch();
            }
        },

        // Watch for spots changes (removed solar overlays)
        filteredSpots: {
            handler(newSpots) {
                // Spots updated
            },
            immediate: false
        },
    },
    
    methods: {
        // Merge all methods from modules
        ...window.FlexRadioWebSocket,
        ...window.FlexRadioControls,
        ...window.FlexRadioUtils,
        ...window.FlexRadioSpots.methods,
        ...window.SDCTicker.methods,
        ...window.RadioControlConfig.methods,
        ...window.RadioControlSolar.methods,
        ...window.RadioControlWavelogStats.methods,
        ...PowerControl,
        ...(window.ft8ModalMixin ? window.ft8ModalMixin.methods : {}),
        
        // === Wavelog Log Viewer Methods ===
        switchViewMode(mode) {
            console.log(`📋 Switching view mode to: ${mode}`);
            this.viewMode = mode;
            if (mode === 'log') {
                this.loadLogEntries();
            }
        },
        
        async loadLogEntries() {
            console.log(`📋 Loading log entries (limit: ${this.logLimit})...`);
            this.logLoading = true;
            this.logError = null;
            try {
                const response = await fetch(`/api/wavelog-log/entries?limit=${this.logLimit}`);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                const data = await response.json();
                if (data.success) {
                    this.logEntries = data.entries;
                    console.log(`✅ Loaded ${data.count} log entries`);
                } else {
                    throw new Error('Failed to load log entries');
                }
            } catch (error) {
                console.error('❌ Error loading log entries:', error);
                this.logError = error.message;
            } finally {
                this.logLoading = false;
            }
        },
        
        setLogLimit(limit) {
            console.log(`📋 Setting log limit to: ${limit}`);
            this.logLimit = limit;
            this.loadLogEntries();
        },
        
        refreshLogEntries() {
            console.log('🔄 Refreshing log entries...');
            this.loadLogEntries();
        },
        
        getFilteredLogEntries() {
            if (!this.logEntries || this.logEntries.length === 0) {
                return [];
            }
            return this.logEntries.filter(entry => {
                for (const [key, value] of Object.entries(this.logFilters)) {
                    if (value && value.trim() !== '') {
                        const entryValue = entry[key] || '';
                        const filterValue = value.toLowerCase();
                        const entryValueLower = String(entryValue).toLowerCase();
                        if (!entryValueLower.includes(filterValue)) {
                            return false;
                        }
                    }
                }
                return true;
            });
        },
        
        clearLogFilters() {
            for (const key in this.logFilters) {
                this.logFilters[key] = '';
            }
            console.log('🗑️ Cleared all log filters');
        },
        
        hasActiveLogFilters() {
            return Object.values(this.logFilters).some(v => v && v.trim() !== '');
        },
        
        openColumnConfig() {
            this.showColumnConfig = true;
        },
        
        closeColumnConfig() {
            this.showColumnConfig = false;
        },
        
        // === Callsign Search Methods ===
        openCallsignSearchModal() {
            this.showCallsignSearchModal = true;
            this.callsignSearchQuery = '';
            this.callsignSearchResults = null;
            this.callsignSearchError = null;
        },
        
        closeCallsignSearchModal() {
            this.showCallsignSearchModal = false;
            this.callsignSearchQuery = '';
            this.callsignSearchResults = null;
            this.callsignSearchError = null;
        },
        
        async searchCallsignHistory() {
            if (!this.callsignSearchQuery.trim()) {
                this.callsignSearchError = 'Please enter a callsign';
                return;
            }
            
            this.callsignSearchLoading = true;
            this.callsignSearchError = null;
            this.callsignSearchResults = null;
            
            try {
                const callsign = this.callsignSearchQuery.trim().toUpperCase();
                console.log(`🔍 Searching for callsign: ${callsign}`);
                
                // URL encode the callsign to handle slashes (e.g., OH2NBC/P, OH2NBC/MM)
                const encodedCallsign = encodeURIComponent(callsign);
                const response = await fetch(`/api/wavelog-log/search/${encodedCallsign}`);
                if (!response.ok) {
                    throw new Error(`Failed to search: ${response.statusText}`);
                }
                
                const data = await response.json();
                if (data.success) {
                    this.callsignSearchResults = {
                        qsos: data.qsos,
                        summary: data.summary,
                        matrix: data.matrix
                    };
                    console.log(`✅ Found ${data.count} QSOs for ${callsign}`);
                } else {
                    throw new Error('Search failed');
                }
            } catch (error) {
                console.error('❌ Error searching callsign:', error);
                this.callsignSearchError = error.message;
            } finally {
                this.callsignSearchLoading = false;
            }
        },
        
        formatSearchDate(dateStr) {
            if (!dateStr) return '-';
            try {
                const date = new Date(dateStr);
                return date.toLocaleString('en-US', {
                    year: '2-digit',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false
                });
            } catch (e) {
                return dateStr;
            }
        },
        
        formatLoTWStatus(sent, rcvd) {
            // Up arrow = Uploaded/Sent to LoTW (green if Y, red otherwise)
            const sentColor = sent === 'Y' ? '#10b981' : '#dc2626';
            const sentArrow = `<span style="color: ${sentColor}; font-weight: bold;">▲</span>`;
            
            // Down arrow = Downloaded/Confirmed from LoTW (green if Y, red otherwise)
            const rcvdColor = rcvd === 'Y' ? '#10b981' : '#dc2626';
            const rcvdArrow = `<span style="color: ${rcvdColor}; font-weight: bold;">▼</span>`;
            
            return sentArrow + rcvdArrow;
        },
        
        viewQSODetails(qso) {
            // Placeholder for future detailed QSO view
            console.log('📋 QSO Details:', qso);
            alert(`QSO Details:\n\nCallsign: ${qso.callsign}\nDate: ${qso.time_on}\nBand: ${qso.band}\nMode: ${qso.mode}\nRST Sent: ${qso.rst_sent}\nRST Rcvd: ${qso.rst_rcvd}`);
        },
        
        refreshSummaryField(field) {
            console.log(`🔄 Refreshing ${field} field...`);
            // Placeholder for future field refresh functionality
            alert(`Refresh ${field} - Feature coming soon!`);
        },
        
        // === Prev QSOs Modal Methods (duplicate of callsign search for independent use) ===
        async openPrevQsosModal() {
            const callsign = this.loggingForm.callsign.trim().toUpperCase();
            if (!callsign) {
                alert('Please enter a callsign first');
                return;
            }
            
            this.showPrevQsosModal = true;
            this.prevQsosCallsign = callsign;
            this.prevQsosResults = null;
            this.prevQsosError = null;
            this.prevQsosLoading = true;
            
            // Auto-search immediately
            try {
                console.log(`🔍 Searching Prev QSOs for callsign: ${callsign}`);
                
                // URL encode the callsign to handle slashes (e.g., OH2NBC/P, OH2NBC/MM)
                const encodedCallsign = encodeURIComponent(callsign);
                const response = await fetch(`/api/wavelog-log/search/${encodedCallsign}`);
                if (!response.ok) {
                    throw new Error(`Failed to search: ${response.statusText}`);
                }
                
                const data = await response.json();
                if (data.success) {
                    this.prevQsosResults = {
                        qsos: data.qsos,
                        summary: data.summary,
                        matrix: data.matrix
                    };
                    console.log(`✅ Found ${data.count} QSOs for ${callsign}`);
                } else {
                    throw new Error('Search failed');
                }
            } catch (error) {
                console.error('❌ Error searching Prev QSOs:', error);
                this.prevQsosError = error.message;
            } finally {
                this.prevQsosLoading = false;
            }
        },
        
        closePrevQsosModal() {
            this.showPrevQsosModal = false;
            this.prevQsosCallsign = '';
            this.prevQsosResults = null;
            this.prevQsosError = null;
            this.prevQsosSortColumn = null;
            this.prevQsosSortDirection = 'asc';
        },
        
        refreshPrevQsosSummaryField(fieldName) {
            console.log(`🔄 Refresh Prev QSOs summary field: ${fieldName}`);
            alert(`Refresh ${fieldName} - Feature coming soon!`);
        },
        
        sortPrevQsos(column) {
            if (this.prevQsosSortColumn === column) {
                // Toggle direction if clicking same column
                this.prevQsosSortDirection = this.prevQsosSortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                // New column, default to ascending
                this.prevQsosSortColumn = column;
                this.prevQsosSortDirection = 'asc';
            }
            console.log(`📊 Sorting Prev QSOs by ${column} (${this.prevQsosSortDirection})`);
        },
        
        getMatrixCellValue(mode, band) {
            // Check both callsign search and prev QSOs results
            const results = this.callsignSearchResults || this.prevQsosResults;
            if (!results || !results.matrix) return '-';
            
            const modeData = results.matrix[mode];
            if (!modeData || !modeData[band]) return '-';
            
            return modeData[band].confirmed ? 'C' : (modeData[band].worked ? 'W' : '-');
        },
        
        getMatrixCellClass(mode, band) {
            // Check both callsign search and prev QSOs results
            const results = this.callsignSearchResults || this.prevQsosResults;
            if (!results || !results.matrix) return 'matrix-cell-empty';
            
            const modeData = results.matrix[mode];
            if (!modeData || !modeData[band]) return 'matrix-cell-empty';
            
            if (modeData[band].confirmed) return 'matrix-cell-confirmed';
            if (modeData[band].worked) return 'matrix-cell-worked';
            return 'matrix-cell-empty';
        },
        
        getMatrixCellTitle(mode, band) {
            // Check both callsign search and prev QSOs results
            const results = this.callsignSearchResults || this.prevQsosResults;
            if (!results || !results.matrix) return '';
            
            const modeData = results.matrix[mode];
            if (!modeData || !modeData[band]) return 'Not worked';
            
            if (modeData[band].confirmed) return `${mode} on ${band} - LoTW Confirmed`;
            if (modeData[band].worked) return `${mode} on ${band} - Worked (not confirmed)`;
            return 'Not worked';
        },
        
        toggleColumnVisibility(columnId) {
            const column = this.logColumns.find(c => c.id === columnId);
            if (column) {
                column.visible = !column.visible;
                this.saveColumnConfig();
            }
        },
        
        resetColumnConfig() {
            // Load default columns from localStorage or use hardcoded defaults
            const DEFAULT_COLUMNS = [
                { id: 'time_on', label: 'Date/Time', visible: true, width: 160 },
                { id: 'callsign', label: 'Callsign', visible: true, width: 100 },
                { id: 'mode', label: 'Mode', visible: true, width: 80 },
                { id: 'rst_sent', label: 'RST(S)', visible: true, width: 70 },
                { id: 'rst_rcvd', label: 'RST(R)', visible: true, width: 70 },
                { id: 'band', label: 'Band', visible: true, width: 70 },
                { id: 'frequency', label: 'Frequency', visible: true, width: 100 },
                { id: 'country', label: 'Country', visible: true, width: 150 },
                { id: 'name', label: 'Name', visible: true, width: 120 },
                { id: 'qth', label: 'QTH', visible: true, width: 120 },
                { id: 'gridsquare', label: 'Gridsquare', visible: true, width: 100 },
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
            this.logColumns = JSON.parse(JSON.stringify(DEFAULT_COLUMNS));
            this.saveColumnConfig();
            console.log('🔄 Reset column configuration to default');
        },
        
        saveColumnConfig() {
            localStorage.setItem('wavelog-log-columns', JSON.stringify(this.logColumns));
            console.log('💾 Saved column configuration');
        },
        
        showAllColumns() {
            this.logColumns.forEach(col => col.visible = true);
            this.saveColumnConfig();
        },
        
        hideAllColumns() {
            this.logColumns.forEach(col => col.visible = false);
            this.saveColumnConfig();
        },
        
        startColumnResize(columnId, event) {
            event.preventDefault();
            const column = this.logColumns.find(c => c.id === columnId);
            if (!column) return;
            
            this.resizingColumn = column;
            this.resizeStartX = event.clientX;
            this.resizeStartWidth = column.width;
            
            // Add event listeners for resize - bind to this instance
            const handleResize = (e) => this.handleColumnResize(e);
            const stopResize = (e) => this.stopColumnResize(e);
            
            // Store bound handlers so we can remove them later
            this._handleColumnResizeBound = handleResize;
            this._stopColumnResizeBound = stopResize;
            
            document.addEventListener('mousemove', handleResize);
            document.addEventListener('mouseup', stopResize);
            
            event.target.classList.add('resizing');
        },
        
        handleColumnResize(event) {
            if (!this.resizingColumn) return;
            const deltaX = event.clientX - this.resizeStartX;
            const newWidth = Math.max(50, this.resizeStartWidth + deltaX);
            
            // Find the column in the array and update it to trigger Vue reactivity
            const columnIndex = this.logColumns.findIndex(c => c.id === this.resizingColumn.id);
            if (columnIndex !== -1) {
                this.logColumns[columnIndex] = { ...this.logColumns[columnIndex], width: newWidth };
                this.resizingColumn = this.logColumns[columnIndex]; // Update reference
            }
        },
        
        stopColumnResize(event) {
            if (this.resizingColumn) {
                this.saveColumnConfig();
                this.resizingColumn = null;
                document.querySelectorAll('.column-resizer').forEach(el => {
                    el.classList.remove('resizing');
                });
            }
            
            // Remove event listeners using bound handlers
            if (this._handleColumnResizeBound) {
                document.removeEventListener('mousemove', this._handleColumnResizeBound);
                this._handleColumnResizeBound = null;
            }
            if (this._stopColumnResizeBound) {
                document.removeEventListener('mouseup', this._stopColumnResizeBound);
                this._stopColumnResizeBound = null;
            }
        },
        
        getVisibleColumns() {
            return this.logColumns.filter(col => col.visible);
        },
        
        getColumnById(id) {
            return this.logColumns.find(col => col.id === id);
        },
        
        getColumnWidth(id) {
            const column = this.getColumnById(id);
            return column ? `${column.width}px` : 'auto';
        },
        
        isColumnVisible(id) {
            const column = this.getColumnById(id);
            return column ? column.visible : false;
        },
        
        formatLogDateTime(dateTimeStr) {
            if (!dateTimeStr) return '-';
            try {
                const date = new Date(dateTimeStr);
                return date.toLocaleString('en-US', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                });
            } catch (e) {
                return dateTimeStr;
            }
        },
        
        formatLogFrequency(freqMhz) {
            if (!freqMhz) return '-';
            return parseFloat(freqMhz).toFixed(3);
        },
        
        formatQslStatus(status) {
            if (!status || status === '') return '-';
            const statusMap = {
                'Y': '✅',
                'N': '❌',
                'R': '📬',
                'Q': '📤',
                'I': '⏳'
            };
            return statusMap[status] || status;
        },
        
        getLogRowClass(entry) {
            if (entry.lotw_rcvd === 'Y') {
                return 'log-row-lotw-confirmed';
            }
            if (entry.qsl_rcvd === 'Y' || entry.eqsl_rcvd === 'Y') {
                return 'log-row-qsl-confirmed';
            }
            return '';
        },
        
        getLogModeDisplay(entry) {
            if (entry.submode && entry.submode !== entry.mode) {
                return `${entry.mode}/${entry.submode}`;
            }
            return entry.mode || '-';
        },
        
        getEntryValue(entry, columnId) {
            if (columnId === 'mode') {
                return this.getLogModeDisplay(entry);
            } else if (columnId === 'frequency') {
                return this.formatLogFrequency(entry.frequency);
            } else if (columnId === 'time_on') {
                return this.formatLogDateTime(entry.time_on);
            } else if (columnId === 'lotw') {
                return `${this.formatQslStatus(entry.lotw_sent)}/${this.formatQslStatus(entry.lotw_rcvd)}`;
            } else if (columnId === 'qsl') {
                return `${this.formatQslStatus(entry.qsl_sent)}/${this.formatQslStatus(entry.qsl_rcvd)}`;
            } else if (columnId === 'eqsl') {
                return `${this.formatQslStatus(entry.eqsl_sent)}/${this.formatQslStatus(entry.eqsl_rcvd)}`;
            }
            return entry[columnId] || '-';
        },
        
        getCellStyle(columnId) {
            const styles = {
                callsign: 'font-weight: bold; color: #10b981;',
                frequency: 'font-family: monospace; color: #4a9eff;',
                gridsquare: 'font-family: monospace;',
                pota_ref: 'color: #fbbf24;',
                sota_ref: 'color: #fbbf24;',
                wwff_ref: 'color: #fbbf24;',
                country: 'color: #ccc;',
                name: 'color: #ccc;',
                qth: 'color: #ccc;',
                comment: 'color: #aaa; max-width: 200px;'
            };
            return styles[columnId] || '';
        },
        
        // === Interface Layout Methods ===
        setInterfaceLayout(layout) {
            this.interfaceLayout = layout;
            localStorage.setItem('interfaceLayout', layout);
            console.log(`✅ Interface layout set to: ${layout}`);
        },
        
        toggleInterfaceLayout() {
            const newLayout = this.interfaceLayout === 'full' ? 'compact' : 'full';
            this.setInterfaceLayout(newLayout);
        },
        
        showQRZModal() {
            if (!this.loggingForm.callsign.trim()) {
                alert('Please enter a callsign first');
                return;
            }
            this.showQRZProfileModal = true;
            // Load the QRZ profile for the current callsign
            this.loadQRZProfile();
        },
        
        closeQRZModal() {
            this.showQRZProfileModal = false;
        },
        
        showDXCCModal() {
            this.showDXCCWavelogModal = true;
        },
        
        closeDXCCModal() {
            this.showDXCCWavelogModal = false;
        },
        
        // Additional methods that need to be in main app
        async initializeApp() {
            console.log('🚀 FlexRadio Web Control v2.0 starting...');
            
            // Load configuration first
            await this.loadConfig();
            
            // Initialize Country Modal
            if (window.CountryModal) {
                window.CountryModal.init();
            }
            
            // Initialize Local Log Modal
            if (window.LocalLogModal) {
                window.LocalLogModal.init();
            }
            
            // Initialize Solar Overlay
            if (window.SolarOverlay) {
                await window.SolarOverlay.init();
                console.log('✅ Solar Overlay initialized');
            }
            
            // Initialize Solar Data for QRZ Profile Panel
            await this.loadSolarData();
            this.setupSolarDataRefresh();
            console.log('✅ Solar data initialized for QRZ Profile panel');
            
            // Initialize Wavelog Statistics for DXCC Panel
            await this.loadWavelogStatistics();
            console.log('✅ Wavelog statistics initialized for DXCC panel');
            
            // Connect WebSocket
            this.connectWebSocket();
            
            // Fetch initial status
            await this.fetchInitialStatus();
            
            // Load worked callsigns from ADIF log
            await this.loadWorkedCallsigns();
            
            // Load rotor status if enabled
            if (this.rotorEnabled) {
                console.log('✅ Rotor is enabled, loading rotor configuration...');
                await this.loadRotorStatus();
                await this.loadRotorAutoConfig();
                console.log(`✅ Rotor AUTO is ${this.rotorAutoEnabled ? 'ENABLED' : 'DISABLED'}`);
            } else {
                console.log('⚠️ Rotor is not enabled in configuration');
            }
            
            // Initialize Winkeyer if enabled
            if (window.winKeyerUI) {
                await window.winKeyerUI.init(this.configData);
                console.log(`✅ WinKeyer is ${this.configData.WINKEYER_ENABLED ? 'ENABLED' : 'DISABLED'}`);
                
                // Register error callback for Winkeyer errors
                window.winKeyerUI.onError((error) => {
                    console.warn('🔑 WinKeyer Error:', error);
                    // You could show error dialog here if needed
                    // For now, errors are visible in widget status
                });
            }
            
            // Start clock
            this.updateClock();
            setInterval(this.updateClock, 1000);
            
            // Poll rotor status every 5 seconds if enabled
            setInterval(() => {
                if (this.rotorEnabled) {
                    this.checkRotorStatus();
                }
            }, 5000);
            
            // Poll sync status every 5 seconds
            this.pollSyncStatus();  // Initial poll
            
            // Countdown timer that updates every 1 second
            setInterval(() => {
                if (this.syncCountdownTimer > 0) {
                    this.syncCountdownTimer--;
                    this.syncStatus.next_sync_in = this.syncCountdownTimer;
                }
            }, 1000);
            
            // Re-poll sync status every 5 seconds
            setInterval(() => {
                this.pollSyncStatus();
            }, 5000);
            
            // Close dropdowns when clicking outside
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.filter-dropdown')) {
                    this.openDropdown = null;
                }
            });
            
            // Initialize SDC Ticker for CW mode
            console.log('🔌 Initializing SDC Ticker...');
            this.initSDCTicker();
            
            console.log('✅ FlexRadio Web Control v2.0 initialized');
        },
        
        // Auto-populate RST based on mode
        autoPopulateRST() {
            // Auto-populate RST values based on current mode
            const mode = this.loggingForm.mode || this.radioStatus.mode || '';
            
            // Voice modes get 2-digit RST (59)
            const voiceModes = ['SSB', 'USB', 'LSB', 'AM', 'FM', 'NFM', 'SAM', 'DFM'];
            
            // Digital modes get 3-digit RST (599)
            const digitalModes = ['CW', 'RTTY', 'DIGL', 'DIGU', 'PSK', 'FT8', 'FT4', 'JT65', 'DIGI'];
            
            if (voiceModes.includes(mode.toUpperCase())) {
                this.loggingForm.rst_sent = 59;
                this.loggingForm.rst_received = 59;
            } else if (digitalModes.includes(mode.toUpperCase()) || mode.toUpperCase() === 'CW') {
                this.loggingForm.rst_sent = 599;
                this.loggingForm.rst_received = 599;
            } else {
                // Default to 599 for unknown modes
                this.loggingForm.rst_sent = 599;
                this.loggingForm.rst_received = 599;
            }
        },
        
        // QRZ and DXCC API methods (imported from utils)
        loadQRZProfile: window.FlexRadioUtils.loadQRZProfile,
        loadWavelogProfile: window.FlexRadioUtils.loadWavelogProfile,
        loadDXCCStatus: window.FlexRadioUtils.loadDXCCStatus,
        loadPreviousQSOs: window.FlexRadioUtils.loadPreviousQSOs,
        parseDXCCData: window.FlexRadioUtils.parseDXCCData,
        autoPopulateForm: window.FlexRadioUtils.autoPopulateForm,
        getCallStatusStyle: window.FlexRadioUtils.getCallStatusStyle,
        getDxccStatusStyle: window.FlexRadioUtils.getDxccStatusStyle,
        freqToBand: window.FlexRadioUtils.freqToBand,
        
        // Initial status fetch
        async fetchInitialStatus() {
            try {
                const response = await fetch('/api/status');
                if (response.ok) {
                    const status = await response.json();
                    this.updateRadioStatus(status);
                }
            } catch (error) {
                console.warn('Could not fetch initial status:', error);
            }
        },
        
        // Clock update
        updateClock() {
            const now = new Date();
            const h = String(now.getUTCHours()).padStart(2, '0');
            const m = String(now.getUTCMinutes()).padStart(2, '0');
            const s = String(now.getUTCSeconds()).padStart(2, '0');
            this.currentTime = `${h}:${m}:${s}`;
        },
        
        // Status message display
        showStatus(message, type = 'info') {
            this.statusMessage = { text: message, type: type };
            setTimeout(() => {
                this.statusMessage = null;
            }, 3000);
        },
        
        // Rotor status loading
        async loadRotorStatus() {
            try {
                const response = await fetch('/api/rotor/status');
                if (response.ok) {
                    const data = await response.json();
                    console.log('🌐 Rotor status:', data);
                    if (data.enabled) {
                        this.rotorConnected = data.azimuth !== null;
                        if (data.azimuth !== null) {
                            this.rotorAzimuth = data.azimuth;
                        }
                        console.log('✅ Rotator connected');
                    } else {
                        this.rotorConnected = false;
                    }
                }
            } catch (error) {
                console.error('Failed to fetch rotor status:', error);
                this.rotorConnected = false;
            }
        },
        
        // === Frequency Control Handlers ===
        
        handleFrequencyKeydown(event) {
            // Handle arrow keys for frequency adjustment
            if (event.key === 'ArrowUp' || event.key === 'ArrowRight') {
                event.preventDefault();
                this.adjustFrequency(1);
            } else if (event.key === 'ArrowDown' || event.key === 'ArrowLeft') {
                event.preventDefault();
                this.adjustFrequency(-1);
            }
        },
        
        handleFrequencyWheel(event) {
            // Handle mouse wheel for frequency adjustment
            // Note: Using .passive modifier in template, so don't call preventDefault()
            // This allows better page scrolling performance
            const direction = event.deltaY < 0 ? 1 : -1;
            this.adjustFrequency(direction);
        },
        
        // === Spot Time Formatting ===
        
        formatSpotTime(timestamp) {
            if (!timestamp) return '';
            // Backend sends Unix timestamp in SECONDS, JS Date needs MILLISECONDS
            // So multiply by 1000 to convert
            const date = new Date(timestamp * 1000);
            // Format: DD/MM/YYYY HH:MM:SS
            const day = String(date.getUTCDate()).padStart(2, '0');
            const month = String(date.getUTCMonth() + 1).padStart(2, '0');
            const year = date.getUTCFullYear();
            const time = date.toISOString().substr(11, 8);
            return `${day}/${month}/${year} ${time}`;
        },
        
        // === QSO Date Formatting ===
        
        formatQSODate(dateStr) {
            if (!dateStr) return '';
            // Format YYYYMMDD to MM/DD/YY
            const year = dateStr.substring(0, 4);
            const month = dateStr.substring(4, 6);
            const day = dateStr.substring(6, 8);
            return `${month}/${day}/${year.substring(2)}`;
        },
        
        // === Band Derivation (CRITICAL for "Worked b4" feature) ===
        
        getBandFromFrequency(freqMhz) {
            // Derive band from frequency in MHz
            // Must match backend's band_from_khz() function for consistency
            if (!freqMhz) return '';
            
            const freq = parseFloat(freqMhz);
            if (freq >= 1.8 && freq < 2.0) return '160m';
            if (freq >= 3.5 && freq < 4.0) return '80m';
            if (freq >= 5.25 && freq < 5.45) return '60m';
            if (freq >= 7.0 && freq < 7.3) return '40m';
            if (freq >= 10.1 && freq < 10.15) return '30m';
            if (freq >= 14.0 && freq < 14.35) return '20m';
            if (freq >= 18.068 && freq < 18.168) return '17m';
            if (freq >= 21.0 && freq < 21.45) return '15m';
            if (freq >= 24.89 && freq < 24.99) return '12m';
            if (freq >= 28.0 && freq < 29.7) return '10m';
            if (freq >= 50.0 && freq < 54.0) return '6m';
            if (freq >= 144.0 && freq < 148.0) return '2m';
            if (freq >= 430.0 && freq < 450.0) return '70cm';
            
            return '';
        },
        
        // === Filter Management ===
        
        clearAllFilters() {
            this.spotsFilter = {
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
            };
        },
        
        // === Logging Form Methods ===
        
        autoPopulateForm() {
            // Auto-populate form when callsign field loses focus or Enter is pressed
            const callsign = this.loggingForm.callsign.trim().toUpperCase();
            if (callsign && callsign.length >= 3) {
                // Look for matching DX spot first
                const spot = this.dxSpots.find(s => s.callsign === callsign);
                if (spot) {
                    // Found matching spot - use spot frequency
                    this.loggingForm.frequency = spot.frequency_mhz || parseFloat(spot.frequency) / 1000;
                    this.loggingForm.mode = spot.mode || '';
                    // Extract awards from spot comments if available
                    if (spot.comment) {
                        this.loggingForm.notes = spot.comment;
                    }
                } else {
                    // No matching spot - use current radio status
                    this.loggingForm.frequency = this.radioStatus.frequency;
                    this.loggingForm.mode = this.radioStatus.mode === 'USB' || this.radioStatus.mode === 'LSB' ? 'SSB' : this.radioStatus.mode;
                }
                
                // CRITICAL: Derive band from frequency for "Worked b4" matching
                if (this.loggingForm.frequency) {
                    this.loggingForm.band = this.freqToBand(this.loggingForm.frequency);
                }
                
                // Auto-populate RST based on mode
                this.autoPopulateRST();
                
                // Update time
                const now = new Date();
                const h = String(now.getUTCHours()).padStart(2, '0');
                const m = String(now.getUTCMinutes()).padStart(2, '0');
                const s = String(now.getUTCSeconds()).padStart(2, '0');
                this.loggingForm.time_off = `${h}:${m}:${s}`;
                
                // Load QRZ profile and DXCC status - IMPORTANT for populating all details
                this.loadQRZProfile();
                this.loadDXCCStatus();
            }
        },
        
        onCallsignChange() {
            // Handle callsign input changes for real-time lookup
            const callsign = this.loggingForm.callsign.trim().toUpperCase();
            this.loggingForm.callsign = callsign;
            
            // Trigger full lookup (QRZ, DXCC, Previous QSOs) if callsign is valid
            if (callsign.length >= 3) {
                // Clear existing timer
                if (this.dxccLookupTimer) {
                    clearTimeout(this.dxccLookupTimer);
                }
                
                // Set new timer for debounced lookup - same as watch behavior
                this.dxccLookupTimer = setTimeout(() => {
                    this.loadQRZProfile();      // Load QRZ profile with Wavelog lookup
                    this.loadDXCCStatus();      // Load DXCC status (which calls loadPreviousQSOs)
                }, 500);
            }
        },
        
        async submitQSO() {
            // Ensure RST values are populated based on mode
            this.autoPopulateRST();
            
            // Validate required fields
            if (!this.loggingForm.callsign.trim()) {
                this.showLoggingStatus('error', '❌ Callsign is required');
                return;
            }
            
            if (!this.loggingForm.frequency || this.loggingForm.frequency <= 0) {
                this.showLoggingStatus('error', '❌ Valid frequency is required');
                return;
            }
            
            if (!this.loggingForm.mode) {
                this.showLoggingStatus('error', '❌ Mode is required');
                return;
            }
            
            // Ensure RST values are valid (keep as strings for backend)
            const rstSent = (this.loggingForm.rst_sent || '599').toString().trim();
            const rstRcvd = (this.loggingForm.rst_received || '599').toString().trim();
            
            // Validate as numbers
            const rstSentNum = parseInt(rstSent);
            const rstRcvdNum = parseInt(rstRcvd);
            
            if (isNaN(rstSentNum) || rstSentNum < 1 || rstSentNum > 999) {
                this.showLoggingStatus('error', '❌ RST Sent must be 1-999');
                return;
            }
            
            if (isNaN(rstRcvdNum) || rstRcvdNum < 1 || rstRcvdNum > 999) {
                this.showLoggingStatus('error', '❌ RST Received must be 1-999');
                return;
            }
            
            this.loggingStatus = { type: 'loading', message: '⏳ Logging QSO...' };
            
            try {
                // Prepare QSO data with uppercase callsign and proper frequency format (MHz)
                const frequency = parseFloat(this.loggingForm.frequency);
                const qsoData = {
                    ...this.loggingForm,
                    callsign: this.loggingForm.callsign.trim().toUpperCase(),
                    frequency: parseFloat(frequency),  // Keep full precision in MHz
                    rst_sent: rstSent,  // Keep as string for backend
                    rst_received: rstRcvd  // Keep as string for backend
                };
                
                // Remove empty strings and null values to avoid issues with Wavelog API
                for (const key in qsoData) {
                    if (qsoData[key] === '' || qsoData[key] === null) {
                        delete qsoData[key];
                    }
                }
                
                console.log('📤 Sending QSO data to backend:', JSON.stringify(qsoData, null, 2));
                
                const response = await fetch('/api/qso/log', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(qsoData)
                });
                
                // Handle response - check status first
                let data;
                const contentType = response.headers.get('content-type');
                let responseBody;
                
                if (!response.ok) {
                    // Read response body once, try to parse as JSON
                    try {
                        responseBody = await response.text();
                        try {
                            data = JSON.parse(responseBody);
                            const errorMsg = data.detail || data.message || `Server error (${response.status})`;
                            console.error('📍 Backend error details:', data);
                            this.showLoggingStatus('error', `❌ ${errorMsg}`);
                        } catch (jsonError) {
                            // Not JSON, use as plain text
                            console.error('📍 Server error response:', responseBody);
                            
                            // Extract useful message from error text if possible
                            let errorMsg = `Server error: ${response.status}`;
                            if (responseBody.length < 200) {
                                errorMsg = `${response.status}: ${responseBody}`;
                            }
                            this.showLoggingStatus('error', `❌ ${errorMsg}`);
                        }
                    } catch (readError) {
                        console.error('📍 Could not read error response:', readError);
                        this.showLoggingStatus('error', `❌ Server error ${response.status} - Check console for details`);
                    }
                    return;
                }
                
                // Parse successful response
                if (contentType && contentType.includes('application/json')) {
                    data = await response.json();
                } else {
                    const text = await response.text();
                    console.error('Unexpected response format:', text);
                    this.showLoggingStatus('error', `❌ Invalid server response format`);
                    return;
                }
                
                if (data.success || data.wavelog?.success) {
                    this.showLoggingStatus('success', `✅ QSO logged: ${qsoData.callsign}`);
                    
                    // === TRIGGER ROTOR AUTO IF ENABLED (for manually logged QSO) ===
                    if (this.rotorAutoEnabled && this.rotorEnabled) {
                        const frequencyKhz = qsoData.frequency * 1000;
                        const gridsquare = qsoData.gridsquare || null;
                        const latitude = qsoData.latitude || null;
                        const longitude = qsoData.longitude || null;
                        console.log(`🤖 AUTO rotor triggered for manual QSO: ${qsoData.callsign} on ${qsoData.frequency} MHz`);
                        this.rotorAutoGoto(qsoData.callsign, frequencyKhz, gridsquare, latitude, longitude);
                    }
                    
                    // Clear form after successful submission
                    setTimeout(() => this.clearLoggingForm(), 2000);
                } else {
                    const errorMsg = data.message || data.wavelog?.message || 'Failed to log QSO';
                    this.showLoggingStatus('error', `❌ ${errorMsg}`);
                }
            } catch (error) {
                console.error('QSO submission error:', error);
                this.showLoggingStatus('error', `❌ Error: ${error.message}`);
            }
        },
        
        showLoggingStatus(type, message) {
            this.loggingStatus = { type, message };
            
            // Auto-clear after 5 seconds
            if (type !== 'loading') {
                setTimeout(() => {
                    if (this.loggingStatus?.type === type) {
                        this.loggingStatus = null;
                    }
                }, 5000);
            }
        },
        
        clearLoggingForm() {
            // Get current UTC time
            const now = new Date();
            const utcHours = String(now.getUTCHours()).padStart(2, '0');
            const utcMinutes = String(now.getUTCMinutes()).padStart(2, '0');
            const utcSeconds = String(now.getUTCSeconds()).padStart(2, '0');
            const currentUtcTime = `${utcHours}:${utcMinutes}:${utcSeconds}`;
            
            // COMPLETE FORM RESET - ALL FIELDS FROM ALL TABS
            this.loggingForm = {
                // === STATION TAB ===
                callsign: '',
                date: new Date().toISOString().split('T')[0],
                time_off: currentUtcTime,
                frequency: this.radioStatus.frequency || null,
                band: (this.radioStatus.frequency && typeof this.radioStatus.frequency === 'number') ? this.getBandFromFrequency(this.radioStatus.frequency) : '',  // CRITICAL: For "Worked b4" matching
                mode: this.radioStatus.mode || 'SSB',
                rst_sent: 599,
                rst_received: 599,
                name: '',
                qth: '',
                gridsquare: '',
                notes: '',
                
                // === AWARDS TAB ===
                pota: '',
                sota: '',
                wwff: '',
                iota: '',
                
                // === GENERAL TAB ===
                continent: '',
                cq_zone: '',
                itu_zone: '',
                region: '',
                country: '',
                state: '',
                us_county: '',
                tx_pwr: '',
                ant: '',
                
                // === QSL TAB ===
                qsl_rcvd: 'N',
                qsl_sent: 'N',
                lotw_member: false,
                qsl_manager: '',
                email: '',
                
                // === SAT TAB ===
                prop_mode: '',
                ant_path: '',
                sat_name: '',
                sat_mode: '',
                freq_rx: '',
                mode_rx: '',
            };
            
            // Clear associated data
            this.qrzProfile = {};
            this.dxccStatus = {};
            this.previousQSOs = [];
            this.allPreviousQSOs = [];
            this.allLocalLogQSOs = [];
            this.qrzHistory = [];
            this.activeLogTab = 'station';
            this.prevQSOsActiveTab = 'wavelog';
            
            console.log('🗑️ Logging form completely cleared - all tabs reset');
        },
        
        // === Rotor Preset Handling ===
        
        handleDirectorToggle() {
            // Handle rotor preset dropdown changes
            if (this.rotorPreset) {
                console.log('Rotor preset selected:', this.rotorPreset);
                // You can add specific logic here for different presets
                // For now, just log the selection
            }
        },
        
        // === Previous QSOs Hover Dropdown ===
        
        formatQSODate(dateStr) {
            // Convert YYYYMMDD format to MM/DD/YY
            if (!dateStr || dateStr.length < 8) return dateStr;
            const year = dateStr.substring(0, 4);
            const month = dateStr.substring(4, 6);
            const day = dateStr.substring(6, 8);
            const shortYear = year.substring(2);
            return `${month}/${day}/${shortYear}`;
        },
        
        async loadAllPreviousQSOs(event) {
            const callsign = this.loggingForm.callsign.trim().toUpperCase();
            if (!callsign) {
                this.allPreviousQSOs = [];
                return;
            }
            
            try {
                console.log(`[All Previous QSOs] 🔍 Loading all QSOs for callsign: ${callsign}`);
                
                const response = await fetch('/api/wavelog/recent_qsos', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        callsign: callsign,
                        limit: 0  // 0 means fetch ALL previous QSOs
                    })
                });
                
                const result = await response.json();
                console.log(`[All Previous QSOs] 📡 Response:`, result);
                
                if (result.success && result.data) {
                    const qsos = Array.isArray(result.data) ? result.data : [];
                    console.log(`[All Previous QSOs] ✅ Received ${qsos.length} QSOs`);
                    this.allPreviousQSOs = qsos;
                    this.currentPrevQSOsPage = 1; // Reset to first page
                    this.showPrevQSOsDropdown = true;
                } else {
                    this.allPreviousQSOs = [];
                    this.showPrevQSOsDropdown = false;
                }
            } catch (error) {
                console.error('[All Previous QSOs] ❌ Error loading QSOs:', error);
                this.allPreviousQSOs = [];
                this.showPrevQSOsDropdown = false;
            }
        },
        
        nextPrevQSOsPage() {
            if (this.currentPrevQSOsPage < this.prevQSOsPageCount) {
                this.currentPrevQSOsPage++;
            }
        },
        
        prevPrevQSOsPage() {
            if (this.currentPrevQSOsPage > 1) {
                this.currentPrevQSOsPage--;
            }
        },
        
        closePrevQSOsDropdown() {
            // Close the modal when X button is clicked or backdrop is clicked
            this.showPrevQSOsDropdown = false;
            this.currentPrevQSOsPage = 1; // Reset pagination when closing
            this.currentLocalLogPage = 1; // Reset local log pagination
        },
        
        /**
         * Load local log QSO data for the Prev QSOs modal
         * Filters for the callsign currently in the logging form
         * Uses DuckDB for fast queries - 10.7x faster than ADIF parsing!
         */
        async loadLocalLogDataForModal() {
            const callsign = this.loggingForm.callsign.trim().toUpperCase();
            if (!callsign) {
                this.allLocalLogQSOs = [];
                return;
            }
            
            try {
                console.log(`[Local Log Modal] 🔍 Loading QSOs for callsign: ${callsign}`);
                
                // Try new DuckDB endpoint first (FAST - ~100ms for filtered results)
                const startTime = performance.now();
                const response = await fetch(`/api/qsos/duckdb/by-call?call=${encodeURIComponent(callsign)}`, {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                const result = await response.json();
                const elapsedTime = performance.now() - startTime;
                
                if (result.success && result.data) {
                    const qsos = Array.isArray(result.data) ? result.data : [];
                    console.log(`✅ Loaded ${qsos.length} QSOs for ${callsign} from duckdb in ${elapsedTime.toFixed(2)}ms (backend: ${result.query_time_ms}ms)`);
                    this.allLocalLogQSOs = qsos;
                    this.currentLocalLogPage = 1; // Reset to first page
                } else {
                    // Fallback to ADIF if DuckDB fails (for robustness)
                    console.warn(`[Local Log Modal] ⚠️ DuckDB endpoint failed, falling back to ADIF parsing...`);
                    await this.loadLocalLogDataFromADIF(callsign);
                }
            } catch (error) {
                console.error('[Local Log Modal] ❌ Error loading from DuckDB, falling back to ADIF:', error);
                // Graceful fallback to ADIF
                await this.loadLocalLogDataFromADIF(callsign);
            }
        },
        
        /**
         * Fallback method: Load local log data from ADIF file
         * Used if DuckDB is unavailable
         */
        async loadLocalLogDataFromADIF(callsign) {
            try {
                console.log(`[Local Log Modal] 📋 Loading from ADIF as fallback for: ${callsign}`);
                
                const startTime = performance.now();
                const response = await fetch('/api/adif/all', {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                const result = await response.json();
                const elapsedTime = performance.now() - startTime;
                
                if (result.success && result.data) {
                    const allQSOs = Array.isArray(result.data) ? result.data : [];
                    // Filter for matching callsign
                    const filteredQSOs = allQSOs.filter(qso => 
                        qso.call && qso.call.toUpperCase() === callsign
                    );
                    console.log(`⚠️ Loaded ${filteredQSOs.length} QSOs for ${callsign} from ADIF in ${elapsedTime.toFixed(2)}ms (slower fallback)`);
                    this.allLocalLogQSOs = filteredQSOs;
                    this.currentLocalLogPage = 1; // Reset to first page
                } else {
                    this.allLocalLogQSOs = [];
                }
            } catch (error) {
                console.error('[Local Log Modal] ❌ Error loading from ADIF fallback:', error);
                this.allLocalLogQSOs = [];
            }
        },
        
        /**
         * Switch to Local Log tab in Prev QSOs modal
         * This ensures the data is loaded when the tab is clicked
         */
        async switchToLocalLogTab() {
            console.log('📁 Switching to Local Log tab');
            this.prevQSOsActiveTab = 'local';
            await this.loadLocalLogDataForModal();
        },
        
        /**
         * Pagination: Go to next page in local log modal
         */
        nextLocalLogPage() {
            if (this.currentLocalLogPage < this.localLogPageCount) {
                this.currentLocalLogPage++;
            }
        },
        
        /**
         * Pagination: Go to previous page in local log modal
         */
        prevLocalLogPage() {
            if (this.currentLocalLogPage > 1) {
                this.currentLocalLogPage--;
            }
        },
        
        /**
         * Show local QSO log modal
         */
        showLocalLog() {
            if (window.LocalLogModal) {
                window.LocalLogModal.showModal();
            } else {
                console.error('LocalLogModal module not loaded');
            }
        },
        
        /**
         * Show local QSO log modal with fresh data
         */
        showLocalLog() {
            if (window.LocalLogModal) {
                window.LocalLogModal.showModal();
            } else {
                console.error('LocalLogModal module not loaded');
            }
        },
        
        /**
         * Hide local QSO log modal
         */
        hideLocalLog() {
            if (window.LocalLogModal) {
                window.LocalLogModal.hideModal();
            } else {
                console.error('LocalLogModal module not loaded');
            }
        },
        
        /**
         * Pagination: Go to previous page in local log
         */
        localLogPrevPage() {
            if (window.LocalLogModal && window.LocalLogModal.goToPage) {
                window.LocalLogModal.goToPage(window.LocalLogModal.currentPage - 1);
            }
        },
        
        /**
         * Pagination: Go to next page in local log
         */
        localLogNextPage() {
            if (window.LocalLogModal && window.LocalLogModal.goToPage) {
                window.LocalLogModal.goToPage(window.LocalLogModal.currentPage + 1);
            }
        },
        
        /**
         * Pagination: Set items per page in local log
         */
        setLocalLogItemsPerPage(count) {
            if (window.LocalLogModal && window.LocalLogModal.setItemsPerPage) {
                window.LocalLogModal.setItemsPerPage(count);
            }
        },
        
        /**
         * Export local log as CSV
         */
        exportLocalLogAsCSV() {
            if (window.LocalLogModal && window.LocalLogModal.exportAsCSV) {
                window.LocalLogModal.exportAsCSV();
            }
        },
        
        /**
         * Show Wavelog QSO log modal
         */
        showWavelogLog() {
            if (window.WavelogLogModal) {
                window.WavelogLogModal.showModal();
            } else {
                console.error('WavelogLogModal module not loaded');
            }
        },
        
        /**
         * Hide Wavelog QSO log modal
         */
        hideWavelogLog() {
            if (window.WavelogLogModal) {
                window.WavelogLogModal.hideModal();
            } else {
                console.error('WavelogLogModal module not loaded');
            }
        },
        
        /**
         * Pagination: Go to previous page in Wavelog log
         */
        wavelogLogPrevPage() {
            if (window.WavelogLogModal && window.WavelogLogModal.goToPage) {
                window.WavelogLogModal.goToPage(window.WavelogLogModal.currentPage - 1);
            }
        },
        
        /**
         * Pagination: Go to next page in Wavelog log
         */
        wavelogLogNextPage() {
            if (window.WavelogLogModal && window.WavelogLogModal.goToPage) {
                window.WavelogLogModal.goToPage(window.WavelogLogModal.currentPage + 1);
            }
        },
        
        /**
         * Pagination: Set items per page in Wavelog log
         */
        setWavelogLogItemsPerPage(count) {
            if (window.WavelogLogModal && window.WavelogLogModal.setItemsPerPage) {
                window.WavelogLogModal.setItemsPerPage(count);
            }
        },
        
        /**
         * Export Wavelog log as CSV
         */
        exportWavelogLogAsCSV() {
            if (window.WavelogLogModal && window.WavelogLogModal.exportAsCSV) {
                window.WavelogLogModal.exportAsCSV();
            }
        },
        
        /**
         * Refresh Wavelog log (manual refresh triggered by user)
         */
        refreshWavelogLog() {
            if (window.WavelogLogModal && window.WavelogLogModal.refresh) {
                window.WavelogLogModal.refresh();
            }
        },
        
        /**
         * Show country information modal with map
         */
        async showCountryModal() {
            if (!this.dxccStatus || !this.dxccStatus.data) {
                console.warn('No DXCC data available');
                return;
            }
            
            const data = this.dxccStatus.data;
            
            // Debug: Log available fields
            console.log('📊 DXCC data available keys:', Object.keys(data));
            
            // Extract country name - backend provides 'dxcc_entity' after enrichment
            const countryName = data.dxcc_entity 
                || data.country 
                || data.country_entity 
                || 'Unknown';
            
            if (!countryName || countryName === 'Unknown') {
                console.warn('⚠️ Could not determine country name from DXCC data');
                alert('Country information not found for this callsign');
                return;
            }
            
            // Extract continent - backend provides 'continent' after enrichment
            const continent = data.continent 
                || data.cont 
                || '—';
            
            // Extract CQ Zone - backend provides 'cq' after enrichment
            const cqZone = data.cq 
                || data.cqz 
                || data.cq_zone 
                || data.dxcc_cqz 
                || '—';
            
            // Extract DXCC ID - backend provides 'dxcc' after enrichment
            const dxccId = data.dxcc 
                || data.dxcc_id 
                || '—';
            
            // Extract latitude - backend provides 'latitude' after enrichment
            let lat = null;
            if (data.latitude) lat = parseFloat(data.latitude);
            else if (data.lat) lat = parseFloat(data.lat);
            else if (data.dxcc_lat) lat = parseFloat(data.dxcc_lat);
            
            // Extract longitude - backend provides 'longitude' after enrichment
            let lon = null;
            if (data.longitude) lon = parseFloat(data.longitude);
            else if (data.lon) lon = parseFloat(data.lon);
            else if (data.dxcc_long) lon = parseFloat(data.dxcc_long);
            
            // Extract grid square
            const grid = data.grid 
                || data.gridsquare 
                || data.grid_square 
                || '';
            
            // Extract bearing - get from rotor control if available
            let bearing = null;
            if (this.shortPathBearing !== null && this.shortPathBearing !== undefined) {
                bearing = this.shortPathBearing;
            }
            
            console.log('🌍 Showing country modal for:', { countryName, continent, cqZone, dxccId, lat, lon, grid, bearing });
            
            // Show the modal
            if (window.CountryModal) {
                await window.CountryModal.showModal(countryName, continent, cqZone, dxccId, lat, lon, grid, bearing);
            } else {
                console.error('CountryModal module not loaded');
            }
        },
        
        // Sync Status Methods
        async pollSyncStatus() {
            try {
                const response = await fetch('/api/sync-status');
                if (response.ok) {
                    this.syncStatus = await response.json();
                    // Set countdown timer from the response
                    this.syncCountdownTimer = this.syncStatus.next_sync_in || 0;
                }
            } catch (error) {
                console.error('Error fetching sync status:', error);
            }
        },
        
        formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
        },

        // === Winkeyer Methods ===
        async winKeyerConnect() {
            if (window.winKeyerUI) {
                await window.winKeyerUI.connect();
            } else {
                console.error('WinKeyer UI not initialized');
            }
        },

        async winKeyerDisconnect() {
            if (window.winKeyerUI) {
                await window.winKeyerUI.disconnect();
            } else {
                console.error('WinKeyer UI not initialized');
            }
        },

        async winKeyerSetWpm() {
            if (window.winKeyerUI) {
                await window.winKeyerUI.setWpm(this.winkeyer.currentWpm);
            }
        },

        winKeyerToggleWpmSlider() {
            if (window.winKeyerUI) {
                window.winKeyerUI.toggleWpmSlider();
            }
        },

        async winKeyerSendMacro(memory) {
            if (window.winKeyerUI) {
                await window.winKeyerUI.sendMacro(memory);
            } else {
                console.error('WinKeyer UI not initialized');
            }
        },

    },
    
    async mounted() {
        // Expose Vue instance to window first (needed by WinKeyer and other modules)
        window.vueInstance = this;
        console.log('✅ Vue instance exposed globally for WSJT-X integration');
        
        // Trigger WinKeyer initialization BEFORE initializeApp so WinKeyerUI is created first
        document.dispatchEvent(new CustomEvent('vue-mounted'));
        console.log('✅ Vue-mounted event triggered for WinKeyer initialization');
        
        // Small delay to allow WinKeyer UI to be created
        await new Promise(resolve => setTimeout(resolve, 50));
        
        // Now initialize the app (which will call init() on WinKeyerUI if it exists)
        await this.initializeApp();
        
        // Initialize WSJT-X handler to listen for station clicks from bridge
        if (typeof initWsjtxHandler === 'function') {
            initWsjtxHandler();
            console.log('✅ WSJT-X Handler initialized');
        } else {
            console.warn('⚠️  WSJT-X handler function not available');
        }
    },
    
    beforeUnmount() {
        this.cleanupSolarDataRefresh();
        // Clean up SDC ticker WebSocket connection
        this.cleanupSDCTicker();
    }
    }).mount('#app');

    // ⚡ CRITICAL FIX: Mark Vue as mounted to prevent double mounting
    vueMounted = true;
    console.log('✅ Vue app mounted successfully');
    console.log('✅ Vue instance exposed to window for inter-window communication');
}

// If templates already loaded (shouldn't happen, but safety check), mount now
if (document.readyState === 'loading' && templatesReady) {
    mountVueApp();
}

