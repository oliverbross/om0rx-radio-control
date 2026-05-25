// Core Vue App Configuration and Data
// FlexRadio Web Control v2.0 - Core Module

console.log('✅ Loading core.js module...');

// Determine page mode from query parameter or window variable
const getPageMode = () => {
    if (window.PAGE_MODE) return window.PAGE_MODE;
    const params = new URLSearchParams(window.location.search);
    return params.get('pageMode') || 'main';
};

// Core Vue app data and configuration
const coreData = {
    // Page mode configuration
    pageMode: getPageMode(),
    
    // WebSocket
    ws: null,
    connected: false,
    reconnectTimer: null,
    
    // Radio status
    radioStatus: {
        frequency: 14.074000,
        mode: 'USB',
        filter_lo: 100,
        filter_hi: 2900,
        volume: 50,
        drive: 31,
        tune_power: 18,
        mic_level: 32,
        monitor: 0,
        vox_enabled: false,
        agc_mode: 'med',
        nb_enabled: false,
        nr_enabled: false,
        anf_enabled: false,
        apf_enabled: false,
        rx2_enabled: false,
        split_enabled: false,
    },
    
    // TX state
    txState: {
        mox: false,
        tune: false,
        vox: false,
        breakin: false,
    },
    
    // Sub VFO (for RX2 or SPLIT)
    subVfoFreq: 14.080000,
    
    // Bands
    bands: ['160M', '80M', '60M', '40M', '30M', '20M', '17M', '15M', '12M', '10M', '6M'],
    
    // Modes
    modes: ['AM', 'LSB', 'USB', 'CW', 'NFM', 'DIGL', 'DIGU', 'FM', 'SAM', 'DFM', 'RTTY'],
    
    // Mode-specific filter presets
    filtersByMode: {
        'USB': [
            { label: '1.8K', lo: 100, hi: 1900 },
            { label: '2.1K', lo: 100, hi: 2200 },
            { label: '2.4K', lo: 100, hi: 2500 },
            { label: '2.7K', lo: 100, hi: 2800 },
            { label: '2.9K', lo: 100, hi: 3000 },
            { label: '3.3K', lo: 100, hi: 3400 },
            { label: '4.0K', lo: 100, hi: 4100 },
            { label: '6K', lo: 100, hi: 6100 },
        ],
        'LSB': [
            { label: '1.8K', lo: -1900, hi: -100 },
            { label: '2.1K', lo: -2200, hi: -100 },
            { label: '2.4K', lo: -2500, hi: -100 },
            { label: '2.7K', lo: -2800, hi: -100 },
            { label: '2.9K', lo: -3000, hi: -100 },
            { label: '3.3K', lo: -3400, hi: -100 },
            { label: '4.0K', lo: -4100, hi: -100 },
            { label: '6K', lo: -6100, hi: -100 },
        ],
        'CW': [
            { label: '50', lo: -25, hi: 25 },
            { label: '100', lo: -50, hi: 50 },
            { label: '250', lo: -125, hi: 125 },
            { label: '400', lo: -200, hi: 200 },
            { label: '500', lo: -250, hi: 250 },
            { label: '800', lo: -400, hi: 400 },
            { label: '1.0K', lo: -500, hi: 500 },
            { label: '3.0K', lo: -1500, hi: 1500 },
        ],
        'AM': [
            { label: '5.6K', lo: -2800, hi: 2800 },
            { label: '6.0K', lo: -3000, hi: 3000 },
            { label: '8.0K', lo: -4000, hi: 4000 },
            { label: '10K', lo: -5000, hi: 5000 },
            { label: '12K', lo: -6000, hi: 6000 },
            { label: '14K', lo: -7000, hi: 7000 },
            { label: '16K', lo: -8000, hi: 8000 },
            { label: '20K', lo: -10000, hi: 10000 },
        ],
        'DIGL': [
            { label: '100', lo: -100, hi: 0 },
            { label: '300', lo: -300, hi: 0 },
            { label: '600', lo: -600, hi: 0 },
            { label: '1.0K', lo: -1000, hi: 0 },
            { label: '1.5K', lo: -1500, hi: 0 },
            { label: '2.0K', lo: -2000, hi: 0 },
            { label: '3.0K', lo: -3000, hi: 0 },
            { label: '6.0K', lo: -6000, hi: 0 },
        ],
        'DIGU': [
            { label: '100', lo: 0, hi: 100 },
            { label: '300', lo: 0, hi: 300 },
            { label: '600', lo: 0, hi: 600 },
            { label: '1.0K', lo: 0, hi: 1000 },
            { label: '1.5K', lo: 0, hi: 1500 },
            { label: '2.0K', lo: 0, hi: 2000 },
            { label: '3.0K', lo: 0, hi: 3000 },
            { label: '6.0K', lo: 0, hi: 6000 },
        ],
        'SAM': [
            { label: '5.6K', lo: -2800, hi: 2800 },
            { label: '6.0K', lo: -3000, hi: 3000 },
            { label: '8.0K', lo: -4000, hi: 4000 },
            { label: '10K', lo: -5000, hi: 5000 },
            { label: '12K', lo: -6000, hi: 6000 },
            { label: '14K', lo: -7000, hi: 7000 },
            { label: '16K', lo: -8000, hi: 8000 },
            { label: '20K', lo: -10000, hi: 10000 },
        ],
        'DFM': [
            { label: '6.0K', lo: -3000, hi: 3000 },
            { label: '8.0K', lo: -4000, hi: 4000 },
            { label: '10K', lo: -5000, hi: 5000 },
            { label: '12K', lo: -6000, hi: 6000 },
            { label: '14K', lo: -7000, hi: 7000 },
            { label: '16K', lo: -8000, hi: 8000 },
            { label: '18K', lo: -9000, hi: 9000 },
            { label: '20K', lo: -10000, hi: 10000 },
        ],
        'RTTY': [
            { label: '250', lo: -125, hi: 125 },
            { label: '300', lo: -150, hi: 150 },
            { label: '350', lo: -175, hi: 175 },
            { label: '400', lo: -200, hi: 200 },
            { label: '500', lo: -250, hi: 250 },
            { label: '1.0K', lo: -500, hi: 500 },
            { label: '1.5K', lo: -750, hi: 750 },
            { label: '3.0K', lo: -1500, hi: 1500 },
        ],
        'FM': [],
        'NFM': [],
    },
    
    // Band frequency map
    bandFrequencies: {
        '160M': 1.840,
        '80M': 3.650,
        '60M': 5.357,
        '40M': 7.074,
        '30M': 10.120,
        '20M': 14.074,
        '17M': 18.100,
        '15M': 21.074,
        '12M': 24.915,
        '10M': 28.074,
        '6M': 50.313,
    },
    
    // Control values (for sliders)
    controls: {
        volume: 50,
        drive: 31,
        tunePower: 18,
        mic: 32,
        monitor: 0,
        agcThreshold: 65, // AGC Threshold (rxagc_threshold in SmartSDR)
    },
    
    // RIT/XIT
    ritValue: 0,
    xitValue: 0,
    ritEnabled: false,
    xitEnabled: false,
    
    // DSP Levels (0-100)
    dspLevels: {
        nb: 50,
        nr: 50,
        anf: 50,
        apf: 50,
    },
    
    // DSP level slider visibility
    showDSPSlider: {
        nb: false,
        nr: false,
        anf: false,
        apf: false,
    },
    
    // Tuning step
    currentStepIndex: 1, // Default to 10 Hz
    stepsByMode: {
        'USB': ['1 Hz', '10 Hz', '50 Hz', '100 Hz', '500 Hz', '1 kHz', '2 kHz', '3 kHz'],
        'LSB': ['1 Hz', '10 Hz', '50 Hz', '100 Hz', '500 Hz', '1 kHz', '2 kHz', '3 kHz'],
        'CW': ['1 Hz', '5 Hz', '10 Hz', '50 Hz', '100 Hz', '200 Hz', '400 Hz'],
        'DIGU': ['1 Hz', '10 Hz', '50 Hz', '100 Hz', '500 Hz', '1 kHz', '2 kHz', '3 kHz'],
        'DIGL': ['1 Hz', '10 Hz', '50 Hz', '100 Hz', '500 Hz', '1 kHz', '2 kHz', '3 kHz'],
        'AM': ['10 Hz', '100 Hz', '1 kHz', '5 kHz', '9 kHz', '10 kHz'],
        'FM': ['100 Hz', '1 kHz', '5 kHz', '10 kHz', '12.5 kHz', '25 kHz'],
        'NFM': ['100 Hz', '1 kHz', '2.5 kHz', '5 kHz', '12.5 kHz'],
        'SAM': ['10 Hz', '100 Hz', '1 kHz', '5 kHz', '9 kHz', '10 kHz'],
        'DFM': ['10 Hz', '100 Hz', '1 kHz', '5 kHz', '9 kHz', '10 kHz'],
        'RTTY': ['1 Hz', '10 Hz', '50 Hz', '100 Hz', '500 Hz', '1 kHz'],
    },
    
    // UI State
    configDialogVisible: false,
    showSyncModal: false,
    
    // Sync status
    syncStatus: {
        syncing: false,
        last_sync: null,
        total_records: 0,
        new_records_this_sync: 0,
        records_skipped: 0,
        next_sync_in: 0,
        adif_file_path: null,
        adif_file_size: 0,
        adif_file_modified: null,
        adif_qso_count: 0,
    },
    syncCountdownTimer: 0,
    
    // WinKeyer UI state
    winkeyer: {
        enabled: false,
        isConnected: false,
        status: '🔴 Disconnected',
        currentWpm: 20,
        connectionTime: null,
        lastError: null,
        config: {
            port: 'COM3',
            baudRate: 1200,
            defaultWpm: 20,
        },
        memories: {
            M1: 'CQ DE OM0RX',
            M2: 'UR RST 599',
            M3: 'QSL TU DE OM0RX',
            M4: 'MNI TU'
        },
        showWpmSlider: false,
    },
    
    // Power control
    showPowerMenu: false,
    serverOffline: false,
    
    // Cluster status
    clusterStatus: {
        connected: false,
        activeName: '',  // e.g., "localhost (Primary)"
        host: '',
        port: '',
    },
};

// Core computed properties
const coreComputed = {
    // Current tuning steps for the active mode
    currentSteps() {
        return this.stepsByMode[this.radioStatus.mode] || this.stepsByMode['USB'];
    },
    
    // Current step value in Hz
    currentStepHz() {
        const stepStr = this.currentSteps[this.currentStepIndex] || '10 Hz';
        const match = stepStr.match(/^([\d.]+)\s*(Hz|kHz)$/);
        if (match) {
            const value = parseFloat(match[1]);
            const unit = match[2];
            return unit === 'kHz' ? value * 1000 : value;
        }
        return 10; // Default fallback
    },
    
    // Current step as string (for display)
    currentStep() {
        return this.currentSteps[this.currentStepIndex] || '10 Hz';
    },
    
    // Available filters for current mode
    availableFilters() {
        return this.filtersByMode[this.radioStatus.mode] || [];
    },
    
    // Current filters (alias for availableFilters for HTML compatibility)
    currentFilters() {
        return this.availableFilters;
    },
    
    // Connection status indicator
    connectionStatus() {
        return this.connected ? 'Connected' : 'Disconnected';
    },
    
    // TX status indicator
    txStatus() {
        if (this.txState.tune) return 'TUNE';
        if (this.txState.mox) return 'TX';
        return 'RX';
    },
};

// Export for use in main app
window.FlexRadioCore = {
    data: coreData,
    computed: coreComputed,
    getPageMode
};