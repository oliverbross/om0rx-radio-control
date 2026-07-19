/**
 * FT8/FT4 Digital Mode Modal
 * Handles FT8/FT4 decoding, encoding, and QSO management
 */

// Import FT8 engine boundary (loaded dynamically)
let ft8Engine = null;

const FT8_DEFAULT_FREQUENCY_PLAN = [
    { band: '160m', ft8: 1.840, ft4: null },
    { band: '80m', ft8: 3.573, ft4: 3.575 },
    { band: '60m', ft8: 5.357, ft4: null },
    { band: '40m', ft8: 7.074, ft4: 7.0475 },
    { band: '30m', ft8: 10.136, ft4: 10.140 },
    { band: '20m', ft8: 14.074, ft4: 14.080 },
    { band: '17m', ft8: 18.100, ft4: 18.104 },
    { band: '15m', ft8: 21.074, ft4: 21.140 },
    { band: '12m', ft8: 24.915, ft4: 24.919 },
    { band: '10m', ft8: 28.074, ft4: 28.180 },
    { band: '6m', ft8: 50.313, ft4: 50.318 }
];

const FT8_DEFAULT_BAND_PLAN = '05:20m,17m,15m,12m,10m\n20:30m,40m,80m,160m';

function cloneFT8FrequencyPlan() {
    return FT8_DEFAULT_FREQUENCY_PLAN.map(row => ({ ...row }));
}

const FT8_DEFAULT_STATUS_COLORS = {
    call: {
        'New Call': '#FF6B35',
        'New Band': '#00BFFF',
        'New Mode': '#FFC000',
        'New Band+Mode': '#E91E63',
        'Worked': '#B0B0B0',
        'Confirmed': '#10B981',
        'Unknown': '#666666',
        'Default': '#FFFFFF'
    },
    dxcc: {
        'ATNO': '#FF8C00',
        'Confirmed': '#10B981',
        'C/New Band': '#4A9EFF',
        'C/New Mode': '#FFD93D',
        'C/New Band+Mode': '#9C27B0',
        'Worked': '#B0B0B0',
        'W/New Band': '#00BCD4',
        'W/New Mode': '#FFA726',
        'W/New Band+Mode': '#FF5722',
        'Unknown': '#666666',
        'Default': '#FFFFFF'
    }
};

function cloneFT8StatusColors() {
    return {
        call: { ...FT8_DEFAULT_STATUS_COLORS.call },
        dxcc: { ...FT8_DEFAULT_STATUS_COLORS.dxcc }
    };
}

// Load FT8 engine module
async function loadFT8Engine() {
    if (!ft8Engine) {
        try {
            const module = await import('./ft8-engine.js');
            ft8Engine = module.default;
            await ft8Engine.init();
            console.log('FT8 engine module loaded');
        } catch (error) {
            console.error('Failed to load FT8 engine:', error);
        }
    }
    return ft8Engine;
}

// === Input Validation Functions ===
/**
 * Validate FT8 callsign format
 * @param {string} callsign - Callsign to validate
 * @returns {object} {valid: boolean, error: string|null}
 */
function validateCallsign(callsign) {
    if (!callsign || typeof callsign !== 'string') {
        return { valid: false, error: 'Callsign is required' };
    }

    const trimmed = callsign.trim().toUpperCase();
    if (trimmed.length < 2 || trimmed.length > 6) {
        return { valid: false, error: 'Callsign must be 2-6 characters' };
    }

    // FT8 callsign pattern: e.g., W5XYZ, M0XYZ, 9K2XYZ
    const callsignRegex = /^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}[A-Z]$/;
    if (!callsignRegex.test(trimmed)) {
        return { valid: false, error: 'Invalid callsign format' };
    }

    return { valid: true, error: null };
}

/**
 * Validate grid square format
 * @param {string} grid - Grid square to validate
 * @returns {object} {valid: boolean, error: string|null}
 */
function validateGridSquare(grid) {
    if (!grid || typeof grid !== 'string') {
        return { valid: false, error: 'Grid square is required' };
    }

    const trimmed = grid.trim().toUpperCase();

    // Grid square pattern: e.g., JN88, AA00aa
    const gridRegex = /^[A-R]{2}[0-9]{2}([A-X]{2})?$/;
    if (!gridRegex.test(trimmed)) {
        return { valid: false, error: 'Invalid grid square format (e.g., JN88 or JN88aa)' };
    }

    return { valid: true, error: null };
}

/**
 * Validate network server address
 * @param {string} server - Server address with optional port (e.g., "192.168.1.1:4992")
 * @returns {object} {valid: boolean, error: string|null}
 */
function validateNetworkServer(server) {
    if (!server || typeof server !== 'string') {
        return { valid: false, error: 'Network server is required' };
    }

    const trimmed = server.trim();

    // Split host and port
    const parts = trimmed.split(':');
    if (parts.length < 1 || parts.length > 2) {
        return { valid: false, error: 'Invalid server format. Use "host" or "host:port"' };
    }

    const host = parts[0];

    // Validate host (IP or hostname)
    const ipRegex = /^(\d{1,3}\.){3}\d{1,3}$/;
    const hostnameRegex = /^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/;

    if (!ipRegex.test(host) && !hostnameRegex.test(host)) {
        return { valid: false, error: 'Invalid host address' };
    }

    // Validate IP octets if IP format
    if (ipRegex.test(host)) {
        const octets = host.split('.').map(o => parseInt(o));
        for (const octet of octets) {
            if (octet < 0 || octet > 255) {
                return { valid: false, error: 'Invalid IP address (octets must be 0-255)' };
            }
        }
    }

    // Validate port if provided
    if (parts.length === 2) {
        const port = parseInt(parts[1]);
        if (isNaN(port) || port < 1 || port > 65535) {
            return { valid: false, error: 'Invalid port. Must be 1-65535' };
        }
    }

    return { valid: true, error: null };
}

// FT8 Modal State and Methods
const ft8ModalMixin = {
    data() {
        return {
            showFT8Modal: false,
            ft8: {
                mode: 'FT8',
                connected: false,
                mycall: 'OM0RX',
                mygrid: 'JN88',
                txEnabled: false,
                autoSequence: false,
                autoCQ: false,
                autoCall: false,
                holdTxFreq: true,
                txEvenFirst: true,
                cqOnly: false,
                filtering: true,
                pounce: false,
                menus: true,
                mini: false,
                isTxCycle: false,
                txInProgress: false,
                txPttCommandActive: false,
                txRadioMox: false,
                txRadioInterlock: '',
                txPttBackend: 'flex',
                txPttBackendError: '',
                bandwidth: 50,
                activeTab: 'operate',  // 'operate' or 'settings'
                rxPanelTab: 'messages',
                configSaved: false,
                selectedBand: '15m',
                currentFrequency: 21.074,
                radioSyncEnabled: true,
                radioSyncMessage: '',
                pendingRadioTune: null,
                cycleDuration: 15,
                cyclePosition: 0,
                cycleRemaining: 15,
                cycleProgress: 0,
                slotIsTx: false,
                activeTxMessage: '',
                activeAttemptId: '',
                digitalState: 'idle',
                pendingTxIntent: null,
                pendingMessage: '',
                txInhibitReason: '',
                automationDecisions: [],
                lastLogSyncKey: '',
                lastQsoCompleted: 0,
                watchdogLimitSeconds: 0,
                watchdogRemainingSeconds: 0,
                watchdogElapsedSeconds: 0,
                utcClock: '--:--:--',
                rxOffset: 0,
                txOffset: 1500,
                selectedTxMessage: 6,
                selectedCall: '',
                selectedGrid: '',
                reportValue: -15,
                lookupTarget: '',
                filterPrefixes: '',
                prefixFilterMode: 'off',
                stateFilterMode: 'off',
                stateFilter: '',
                ignoredStations: '',
                autoIgnore: false,
                customAlerts: '',
                alertLog: [],
                lastAlertKeys: {},
                autoCallQueued: {},
                autoCallBackoff: {},
                autoIgnoredStations: {},
                spotTargets: {},
                specialActivity: {
                    enabled: false,
                    role: 'hound',
                    submode: 'standard',
                    autoDetectFromSpot: true,
                    callOnlyAfterDecode: true,
                    returnToStandardAfterQso: true,
                    superFoxOtp: false,
                    superFoxVerified: false,
                    superFoxShowOtp: false,
                    superFoxOtpKey: '',
                    superFoxOtpUrl: 'https://www.9dx.cc',
                    superFoxLowestTone: 750,
                    houndTxMin: 1000,
                    houndTxMax: 4000,
                    superFoxTxMin: 200,
                    superFoxTxMax: 3000
                },
                filters: {
                    new: { call: false, dxcc: false, continent: false, grid: false, cqZone: false, ituZone: false },
                    onBand: { call: true, dxcc: false, continent: false, grid: true, cqZone: false, ituZone: false },
                    continents: { EU: true, AF: true, OC: true, AS: true, SA: true, NA: true, AN: true },
                    lotwOnly: false
                },
                alerts: {
                    new: { call: false, dxcc: false, continent: false, grid: false, cqZone: false, ituZone: false },
                    onBand: { call: false, dxcc: false, continent: false, grid: false, cqZone: false, ituZone: false }
                },
                statusColors: cloneFT8StatusColors(),
                callStatusColorKeys: Object.keys(FT8_DEFAULT_STATUS_COLORS.call),
                dxccStatusColorKeys: Object.keys(FT8_DEFAULT_STATUS_COLORS.dxcc),
                automation: {
                    enabled: false,
                    spotHuntEnabled: false,
                    referenceHunterEnabled: false,
                    hunterPrograms: ['POTA', 'SOTA', 'IOTA', 'WWFF', 'WWBOTA', 'ARLHS'],
                    hunterMinSpotScore: 50,
                    hunterWatchdogMinutes: 5,
                    hunterRestoreWatchdogMinutes: 2,
                    hunterSpotFilters: {},
                    bandHopping: false,
                    bandPlan: FT8_DEFAULT_BAND_PLAN,
                    allowedModes: { FT8: true, FT4: true, FT2: false },
                    modeSwitching: false,
                    autoCQCount: 5,
                    autoCallCount: 5,
                    autoCQRemaining: 5,
                    autoCallRemaining: 5,
                    spotListenSeconds: 120,
                    hopIntervalSeconds: 120,
                    minSignal: -30,
                    maxAttemptsPerTarget: 3,
                    retryBackoffMinutes: 10,
                    retryResetMinutes: 60,
                    priority: 'last',
                    treat73AsCQ: true,
                    avoidLogged: true,
                    requireHeardBeforeCall: true,
                    autoLogToWavelog: true,
                    lastHopAt: 0,
                    lastHopKey: ''
                },
                wsjtz: {
                    settingsTab: 'rx',
                    rxWindows: {
                        showDistance: true,
                        rawViewDXCC: false,
                        clearRxOnBandChange: false,
                        showState: true,
                        highlightDX: true,
                        showBearing: true,
                        colourAll: true,
                        removeExtra: true,
                        freezeBandActivity: false,
                        separatorColor: '#777777',
                        countryPadding: 42
                    },
                    misc: {
                        processTailenders: true,
                        applyFilteringToCallers: true,
                        disableWriteAll: true,
                        disableWriteFoxQso: true,
                        udpFiltering: true,
                        setRxToTxWhenFinished: true,
                        resetWatchdogAnywhere: true,
                        autoTuneAfterBandChange: false,
                        noFoxQsy: true
                    },
                    watchdog: {
                        enabled: true,
                        ft8: 2,
                        ft4: 2
                    },
                    ignoreList: {
                        permanent: '',
                        resetInterval: 0
                    },
                    freeFrequency: {
                        enabled: true,
                        range: 'wide'
                    },
                    debug: 'screen',
                    alertCommand: ''
                },
                availableBands: cloneFT8FrequencyPlan(),
                txMessages: [
                    { id: 1, label: 'Tx 1', text: '' },
                    { id: 2, label: 'Tx 2', text: '' },
                    { id: 3, label: 'Tx 3', text: '' },
                    { id: 4, label: 'Tx 4', text: '' },
                    { id: 5, label: 'Tx 5', text: '' },
                    { id: 6, label: 'Tx 6', text: 'CQ OM0RX JN88' }
                ],
                engine: {
                    engine: 'ft8_lib',
                    license: 'MIT',
                    ready: false,
                    receive: 'unavailable',
                    transmit: false,
                    messageEncode: true,
                    audioGenerate: true,
                    foxhoundHound: false,
                    foxMode: false,
                    superfoxRx: false,
                    superfoxTx: false
                },

                // Loading states for better UX
                isLoading: false,
                loadingMessage: '',
                errorMessage: '',

                // Configuration
                config: {
                    mode: 'FT8',
                    mycall: 'OM0RX',
                    mygrid: 'JN88',
                    networkServer: '192.168.0.199:4992',
                    rigBackend: 'auto',
                    hamlibRigctlPath: '',
                    hamlibModel: 23005,
                    hamlibRigPath: '',
                    hamlibTimeoutSeconds: 3,
                    pttMethod: 'CAT',
                    audioInput: 'flexradio',
                    audioOutput: 'flexradio',
                    sampleRate: 48000,
                    autoSequence: false,
                    txEnabled: false,
                    waterfallHeight: 100,
                    waterfallEnabled: true,
                    useFlexRadioAudio: true,
                    operatorSettings: {}
                },
                display: {
                    waterfall: true
                },

                // Audio devices
                audioDevices: {
                    input: [],
                    output: []
                },

                // Decoded messages
                decodedMessages: [],
                selectedMessage: null,

                // Active QSOs
                activeQSOs: [],

                // TX
                txQueue: [],
                customMessage: '',

                // Stats
                stats: {
                    decoded_count: 0,
                    transmitted_count: 0,
                    qso_completed: 0,
                    uptime: 0
                },

                // Waterfall
                waterfallData: [],
                waterfallCtx: null,
                lastDecodedFetchCount: 0,
                decodedRefreshInFlight: false,
                decodedReceiveSequence: 0,
                statusCache: {},
                statusInflight: {},
                automationController: null,
                bridgeReady: false,
                wsjtxAutomation: {
                    preparing: false,
                    lastPrepared: null,
                    lastError: ''
                }
            },

            // WebSocket
            ft8Ws: null,
            ft8StatusTimer: null,
            ft8ClockTimer: null,
            ft8RadioSyncTimer: null,
            ft8AutomationTimer: null,
            ft8EscHandler: null,
            ft8BridgeChannel: null
        };
    },

    methods: {
        // === Modal Control ===

        async openDigitalWindow() {
            if (document.body.dataset.ft8Standalone !== 'true') {
                if (window.pywebview?.api?.open_digital_window) {
                    try {
                        const result = await window.pywebview.api.open_digital_window();
                        if (result?.success !== false) {
                            return;
                        }
                        console.warn('Native Digital window request failed:', result?.error || result);
                    } catch (error) {
                        console.warn('Unable to request native Digital window:', error);
                    }
                }

                if (this.ft8) {
                    this.ft8.errorMessage = 'Digital window can only be opened from the native launcher.';
                }
                return;
            }

            await this.openFT8Modal();
        },

        async openFT8Modal() {
            if (document.body.dataset.ft8Standalone !== 'true') {
                await this.openDigitalWindow();
                return;
            }

            console.log('Opening FT8 modal');
            this.showFT8Modal = true;
            this.ft8LoadStoredOperatorSettings();
            this.ft8LoadConfiguredStatusColors();
            this.ft8SetupDigitalBridge();

            // Load FT8 engine boundary
            await loadFT8Engine();

            // Set engine mode and display capabilities
            if (ft8Engine) {
                ft8Engine.setMode(this.ft8.mode);
                this.ft8.engine = ft8Engine.getCapabilities();
            }

            // Load configuration (includes audio devices)
            await this.ft8LoadSettings();

            // Initialize waterfall canvas
            this.$nextTick(() => {
                this.initFT8Waterfall();
            });

            // Connect to FT8 WebSocket
            this.connectFT8WebSocket();
            this.startFT8Clock();
            this.startFT8RadioSync();
            this.startFT8StatusPolling();
            this.startFT8AutomationTimer();
            this.ft8InstallKeyboardShortcuts();
            await this.ft8PollRadioStatus();
            await this.ft8RefreshDecodedMessages();
        },

        closeFT8Modal() {
            console.log('Closing FT8 modal');
            this.showFT8Modal = false;

            // Cleanup engine state
            if (ft8Engine) {
                ft8Engine.clearDecodedMessages();
            }

            // Stop service if running
            if (this.ft8.connected) {
                this.ft8StopService();
            }

            // Disconnect WebSocket
            if (this.ft8Ws) {
                this.ft8Ws.close();
                this.ft8Ws = null;
            }
            this.stopFT8StatusPolling();
            this.stopFT8Clock();
            this.stopFT8RadioSync();
            this.stopFT8AutomationTimer();
            this.ft8RemoveKeyboardShortcuts();
            this.ft8CloseDigitalBridge();

            if (document.body.dataset.ft8Standalone === 'true') {
                window.close();
            }
        },

        ft8SetupDigitalBridge() {
            if (this.ft8BridgeChannel || typeof BroadcastChannel === 'undefined') {
                return;
            }
            try {
                this.ft8BridgeChannel = new BroadcastChannel('om0rx-digital-mode');
                this.ft8BridgeChannel.onmessage = event => {
                    const message = event.data || {};
                    if (message.source === 'ft8-window') {
                        return;
                    }
                    if (message.type === 'spot-selected') {
                        this.ft8ApplyExternalSpot(message.payload || {}).catch(error => {
                            console.warn('Unable to apply digital spot selection:', error);
                            this.ft8.errorMessage = `Spot tune failed: ${error.message}`;
                        });
                    }
                };
                this.ft8.bridgeReady = true;
            } catch (error) {
                console.warn('Unable to start FT8 digital bridge:', error);
            }
        },

        ft8CloseDigitalBridge() {
            if (this.ft8BridgeChannel) {
                this.ft8BridgeChannel.close();
                this.ft8BridgeChannel = null;
            }
            this.ft8.bridgeReady = false;
        },

        ft8BroadcastDigitalEvent(type, payload) {
            const event = {
                type,
                payload,
                source: 'ft8-window',
                timestamp: new Date().toISOString()
            };
            try {
                if (!this.ft8BridgeChannel && typeof BroadcastChannel !== 'undefined') {
                    this.ft8SetupDigitalBridge();
                }
                if (this.ft8BridgeChannel) {
                    this.ft8BridgeChannel.postMessage(event);
                }
                localStorage.setItem('om0rx.digital.lastEvent', JSON.stringify(event));
            } catch (error) {
                console.warn('Unable to broadcast FT8 event:', error);
            }
        },

        ft8IsDigitalMode(mode) {
            return ['FT8', 'FT4'].includes(String(mode || '').toUpperCase());
        },

        ft8AutomationAllowedModes() {
            if (this.ft8.specialActivity.enabled && this.ft8.specialActivity.submode !== 'standard') {
                return ['FT8'];
            }
            const configured = this.ft8.automation.allowedModes || {};
            const modes = ['FT8', 'FT4'].filter(mode => configured[mode] !== false);
            return modes.length ? modes : ['FT8'];
        },

        ft8AutomationModeAllowed(mode) {
            return this.ft8AutomationAllowedModes().includes(String(mode || '').toUpperCase());
        },

        ft8DetectSpotSpecialActivity(spot) {
            const raw = [
                spot.special_activity,
                spot.specialActivity,
                spot.submode,
                spot.comment,
                spot.notes,
                spot.source,
                spot.mode_detail
            ].map(value => String(value || '').toUpperCase()).join(' ');
            if (/\b(SUPER\s*FOX|SUPERFOX|SUPER\s*HOUND|SUPERHOUND|FT8_SF)\b/.test(raw)) {
                return { enabled: true, role: 'hound', submode: 'superfox', superFoxOtp: true };
            }
            if (/\b(FOX\s*\/\s*HOUND|F\/H|FOXHOUND|DXPEDITION|DXPED)\b/.test(raw)) {
                return { enabled: true, role: 'hound', submode: 'foxhound' };
            }
            return null;
        },

        ft8ApplySpecialActivity(patch = {}) {
            const current = this.ft8.specialActivity || {};
            const submode = String(patch.submode || current.submode || 'standard').toLowerCase();
            const role = String(patch.role || current.role || 'hound').toLowerCase();
            this.ft8.specialActivity = {
                ...current,
                ...patch,
                enabled: Boolean(patch.enabled ?? current.enabled),
                role: ['hound', 'fox'].includes(role) ? role : 'hound',
                submode: ['standard', 'foxhound', 'superfox'].includes(submode) ? submode : 'standard'
            };
            if (this.ft8.specialActivity.enabled) {
                this.ft8.mode = 'FT8';
                this.ft8.config.mode = 'FT8';
                this.ft8.bandwidth = 50;
                if (this.ft8.specialActivity.role === 'hound' && this.ft8.specialActivity.submode === 'foxhound') {
                    this.ft8SetTxOffset(this.ft8FindFreeTxOffset() || this.ft8.txOffset || 1500);
                }
                if (this.ft8.specialActivity.role === 'hound' && this.ft8.specialActivity.submode === 'superfox') {
                    this.ft8SetTxOffset(this.ft8FindFreeTxOffset() || this.ft8.txOffset || 1500);
                }
            } else {
                this.ft8SetTxOffset(this.ft8.txOffset || 1500);
            }
        },

        ft8ApplySpecialActivityStatus(status) {
            const mapped = {
                enabled: Boolean(status.enabled),
                role: status.role || this.ft8.specialActivity.role,
                submode: status.submode || this.ft8.specialActivity.submode,
                superFoxOtp: status.superfox_otp === undefined ? this.ft8.specialActivity.superFoxOtp : Boolean(status.superfox_otp),
                superFoxVerified: status.superfox_verified === undefined ? this.ft8.specialActivity.superFoxVerified : Boolean(status.superfox_verified),
                callOnlyAfterDecode: status.call_only_after_decode === undefined ? this.ft8.specialActivity.callOnlyAfterDecode : Boolean(status.call_only_after_decode),
                returnToStandardAfterQso: status.return_to_standard_after_qso === undefined ? this.ft8.specialActivity.returnToStandardAfterQso : Boolean(status.return_to_standard_after_qso),
                houndTxMin: Number(status.hound_tx_min || this.ft8.specialActivity.houndTxMin),
                houndTxMax: Number(status.hound_tx_max || this.ft8.specialActivity.houndTxMax),
                superFoxTxMin: Number(status.superfox_tx_min || this.ft8.specialActivity.superFoxTxMin),
                superFoxTxMax: Number(status.superfox_tx_max || this.ft8.specialActivity.superFoxTxMax)
            };
            this.ft8.specialActivity = { ...this.ft8.specialActivity, ...mapped };
        },

        ft8SpecialActivityPayload(extra = {}) {
            const activity = { ...this.ft8.specialActivity, ...extra };
            return {
                enabled: Boolean(activity.enabled),
                role: String(activity.role || 'hound').toLowerCase(),
                submode: String(activity.submode || 'standard').toLowerCase(),
                auto_detect_from_spot: Boolean(activity.autoDetectFromSpot),
                call_only_after_decode: Boolean(activity.callOnlyAfterDecode),
                return_to_standard_after_qso: Boolean(activity.returnToStandardAfterQso),
                superfox_otp: Boolean(activity.superFoxOtp),
                superfox_verified: Boolean(activity.superFoxVerified),
                superfox_show_otp: Boolean(activity.superFoxShowOtp),
                superfox_otp_key: activity.superFoxOtpKey || '',
                superfox_otp_url: activity.superFoxOtpUrl || 'https://www.9dx.cc',
                superfox_lowest_tone: Number(activity.superFoxLowestTone || 750),
                hound_tx_min: Number(activity.houndTxMin || 1000),
                hound_tx_max: Number(activity.houndTxMax || 4000),
                superfox_tx_min: Number(activity.superFoxTxMin || 200),
                superfox_tx_max: Number(activity.superFoxTxMax || 3000)
            };
        },

        async ft8ApplyExternalSpot(spot) {
            let mode = String(spot.mode || '').toUpperCase();
            if (!this.ft8IsDigitalMode(mode)) {
                return;
            }
            if (this.ft8.specialActivity.autoDetectFromSpot) {
                const special = this.ft8DetectSpotSpecialActivity(spot);
                if (special) {
                    this.ft8ApplySpecialActivity(special);
                    mode = 'FT8';
                    if (this.ft8.connected) {
                        await this.ft8SyncServiceConfig();
                    }
                }
            }
            if (!this.ft8AutomationModeAllowed(mode)) {
                this.ft8.radioSyncMessage = `${mode} spot ignored by Digital mode filter`;
                return;
            }

            const frequency = this.ft8NormalizeSpotFrequency(spot.frequency_mhz || spot.frequency || 0);
            const call = String(spot.callsign || spot.call || '').toUpperCase();
            const band = spot.band || this.ft8InferBandFromFrequency(frequency);
            const tuning = this.ft8ResolveDigitalSpotTuning(spot, frequency, band, mode);
            if (mode && this.ft8.mode !== mode) {
                this.ft8.mode = mode;
                this.ft8.config.mode = mode;
                this.ft8.bandwidth = mode === 'FT8' ? 50 : 100;
                if (ft8Engine) {
                    ft8Engine.setMode(mode);
                    this.ft8.engine = ft8Engine.getCapabilities();
                }
                if (this.ft8.connected) {
                    try {
                        await this.ft8SyncServiceConfig();
                    } catch (error) {
                        console.warn('Unable to sync digital mode after spot selection:', error);
                        this.ft8.errorMessage = `Mode sync failed: ${error.message}`;
                    }
                }
            }
            if (band) {
                this.ft8.selectedBand = band;
            }
            if (tuning.radioFrequency > 0) {
                this.ft8.currentFrequency = tuning.radioFrequency;
                this.ft8.rxOffset = tuning.audioOffset;
                this.ft8.radioSyncMessage = `Spot ${tuning.radioFrequency.toFixed(6)} MHz / ${tuning.audioOffset} Hz`;
                await this.ft8TuneRadioFrequency(tuning.radioFrequency, mode);
            }
            this.ft8.selectedCall = call;
            this.ft8.selectedGrid = String(spot.gridsquare || spot.grid || '').toUpperCase();

            const message = {
                timestamp: new Date().toISOString(),
                snr: spot.snr ?? 0,
                dt: spot.dt ?? 0,
                freq: tuning.audioOffset,
                message: `SPOT ${call} ${this.ft8.selectedGrid}`.trim(),
                callsign: call,
                grid: this.ft8.selectedGrid,
                band: band || this.ft8.selectedBand,
                mode,
                source: 'spot',
                is_spot: true,
                base_frequency: tuning.radioFrequency,
                country: spot.country || spot.dxcc_name || '',
                call_status: spot.call_status || '',
                dxcc_status: spot.dxcc_status || '',
                comment: spot.comment || ''
            };
            this.ft8.selectedMessage = message;
            const exists = this.ft8.decodedMessages.some(
                item => item.callsign === call && item.mode === mode && Math.abs(Number(item.base_frequency || 0) - frequency) < 0.0005
            );
            if (!exists) {
                this.ft8.decodedMessages.unshift(message);
                this.ft8.decodedMessages = this.ft8.decodedMessages.slice(0, 100);
            }
            this.ft8RegisterSpotTarget(message);
            this.ft8EnrichDecodedMessage(message);
        },

        ft8NormalizeSpotFrequency(value) {
            const frequency = Number(value || 0);
            if (!Number.isFinite(frequency) || frequency <= 0) {
                return 0;
            }
            return frequency > 1000 ? frequency / 1000 : frequency;
        },

        ft8ResolveDigitalSpotTuning(spot, frequency, band, mode) {
            const spotFrequency = Number(frequency || 0);
            const standardDial = this.ft8GetBandFrequency(band, mode);
            let audioOffset = Number(spot.audio_offset || spot.audioOffset || spot.freq || 0);
            let radioFrequency = spotFrequency;

            if (standardDial && spotFrequency > 0) {
                const deltaHz = Math.round((spotFrequency - standardDial) * 1000000);
                if (deltaHz >= 200 && deltaHz <= 3000) {
                    radioFrequency = standardDial;
                    audioOffset = deltaHz;
                } else if (Math.abs(deltaHz) <= 50) {
                    radioFrequency = standardDial;
                }
            }

            if (!Number.isFinite(audioOffset) || audioOffset < 200 || audioOffset > 3000) {
                audioOffset = Number(this.ft8.rxOffset || this.ft8.txOffset || 1500);
            }
            if (!Number.isFinite(audioOffset) || audioOffset < 200 || audioOffset > 3000) {
                audioOffset = 1500;
            }

            return {
                radioFrequency: Number(radioFrequency || standardDial || 0),
                audioOffset: Math.round(audioOffset)
            };
        },

        async ft8TuneRadioFrequency(frequency, mode = this.ft8.mode) {
            const target = Number(frequency || 0);
            if (!Number.isFinite(target) || target <= 0) {
                return;
            }
            this.ft8.pendingRadioTune = {
                frequency: target,
                mode,
                timestamp: Date.now()
            };
            const response = await fetch('/api/spots/tune', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    frequency: target,
                    mode: 'DIGU'
                })
            });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
            }
        },

        ft8RegisterSpotTarget(message) {
            const call = String(message?.callsign || '').toUpperCase();
            if (!call || !this.ft8.automation.spotHuntEnabled) {
                return;
            }
            const listenSeconds = Math.max(15, Math.min(900, Number(this.ft8.automation.spotListenSeconds || 120)));
            const key = `${call}|${message.band || this.ft8.selectedBand}|${message.mode || this.ft8.mode}`;
            this.ft8.spotTargets[key] = {
                call,
                band: message.band || this.ft8.selectedBand,
                mode: message.mode || this.ft8.mode,
                expiresAt: Date.now() + listenSeconds * 1000,
                frequency: message.base_frequency || this.ft8.currentFrequency,
                audioOffset: message.freq || this.ft8.rxOffset || 1500,
                specialActivity: this.ft8SpecialActivityPayload()
            };
        },

        ft8IsActiveSpotTarget(call, band, mode) {
            const key = `${String(call || '').toUpperCase()}|${band || this.ft8.selectedBand}|${mode || this.ft8.mode}`;
            const target = this.ft8.spotTargets[key];
            if (!target) {
                return false;
            }
            if (Date.now() > Number(target.expiresAt || 0)) {
                delete this.ft8.spotTargets[key];
                return false;
            }
            return true;
        },

        // === WebSocket Connection ===

        connectFT8WebSocket() {
            const wsUrl = `ws://${window.location.host}/api/ft8/ws`;
            console.log('Connecting to FT8 WebSocket:', wsUrl);

            this.ft8Ws = new WebSocket(wsUrl);

            this.ft8Ws.onopen = () => {
                console.log('FT8 WebSocket connected');
            };

            this.ft8Ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleFT8WebSocketMessage(data).catch(error => {
                        console.error('Error handling FT8 WebSocket message:', error);
                    });
                } catch (e) {
                    console.error('Error parsing FT8 WebSocket message:', e);
                }
            };

            this.ft8Ws.onerror = (error) => {
                console.error('FT8 WebSocket error:', error);
            };

            this.ft8Ws.onclose = () => {
                console.log('FT8 WebSocket closed');

                // Reconnect if modal is still open
                if (this.showFT8Modal) {
                    setTimeout(() => {
                        this.connectFT8WebSocket();
                    }, 2000);
                }
            };
        },

        startFT8StatusPolling() {
            if (this.ft8StatusTimer) {
                return;
            }
            this.ft8StatusTimer = setInterval(() => {
                this.ft8PollStatus();
            }, 750);
            this.ft8PollStatus();
        },

        stopFT8StatusPolling() {
            if (this.ft8StatusTimer) {
                clearInterval(this.ft8StatusTimer);
                this.ft8StatusTimer = null;
            }
        },

        startFT8RadioSync() {
            if (this.ft8RadioSyncTimer) {
                return;
            }
            this.ft8RadioSyncTimer = setInterval(() => {
                this.ft8PollRadioStatus();
            }, 1500);
        },

        stopFT8RadioSync() {
            if (this.ft8RadioSyncTimer) {
                clearInterval(this.ft8RadioSyncTimer);
                this.ft8RadioSyncTimer = null;
            }
        },

        startFT8AutomationTimer() {
            if (this.ft8AutomationTimer) {
                return;
            }
            this.ft8AutomationTimer = setInterval(() => {
                this.ft8RunScheduledAutomation().catch(error => {
                    console.warn('Digital automation tick failed:', error);
                    this.ft8.errorMessage = `Automation failed: ${error.message}`;
                });
            }, 30000);
            this.ft8RunScheduledAutomation().catch(error => {
                console.warn('Initial digital automation tick failed:', error);
            });
        },

        stopFT8AutomationTimer() {
            if (this.ft8AutomationTimer) {
                clearInterval(this.ft8AutomationTimer);
                this.ft8AutomationTimer = null;
            }
        },

        async ft8RunScheduledAutomation() {
            this.ft8PruneAutoIgnoreList();
            this.ft8PruneAutoCallBackoff();
            if (!this.ft8.automation.enabled || !this.ft8.automation.bandHopping) {
                return;
            }

            const intervalSeconds = Math.max(30, Math.min(3600, Number(this.ft8.automation.hopIntervalSeconds || 120)));
            const target = this.ft8NextAutomationTarget();
            if (!target) {
                return;
            }

            const now = Date.now();
            if (now - Number(this.ft8.automation.lastHopAt || 0) < intervalSeconds * 1000 && !target.urgent) {
                return;
            }

            const targetKey = `${target.band}|${target.mode}`;
            const changed = target.band !== this.ft8.selectedBand || target.mode !== this.ft8.mode;
            this.ft8.automation.lastHopAt = now;
            this.ft8.automation.lastHopKey = targetKey;

            if (target.mode !== this.ft8.mode) {
                this.ft8.mode = target.mode;
                this.ft8.config.mode = target.mode;
                this.ft8.bandwidth = target.mode === 'FT8' ? 50 : 100;
                if (ft8Engine) {
                    ft8Engine.setMode(target.mode);
                    this.ft8.engine = ft8Engine.getCapabilities();
                }
                if (this.ft8.connected) {
                    await this.ft8SyncServiceConfig();
                }
            }
            this.ft8.selectedBand = target.band;
            this.ft8SyncFrequencyFromBand();
            if (changed || Math.abs(Number(this.ft8.currentFrequency || 0) - Number(target.frequency || 0)) > 0.0005) {
                await this.ft8TuneSelectedBand();
                this.ft8MaybeUpdateFreeTxOffset('auto-hop');
                this.ft8.radioSyncMessage = `Automation ${target.band} ${target.mode} ${target.frequency.toFixed(6)} MHz (${target.reason})`;
            }
        },

        ft8NextAutomationTarget() {
            const bands = this.ft8AutomationPlanBands();
            const currentMode = String(this.ft8.mode || 'FT8').toUpperCase();
            const allowedModes = this.ft8AutomationAllowedModes();
            const modes = this.ft8.automation.modeSwitching
                ? allowedModes
                : allowedModes.includes(currentMode) ? [currentMode] : [allowedModes[0]];
            const candidates = this.ft8BuildAutomationCandidates(bands, modes);
            if (!candidates.length) {
                return null;
            }

            const lastKey = this.ft8.automation.lastHopKey || `${this.ft8.selectedBand}|${currentMode}`;
            const currentKey = `${this.ft8.selectedBand}|${currentMode}`;
            const scored = candidates.map(candidate => this.ft8ScoreAutomationCandidate(candidate));
            const current = scored.find(item => item.key === currentKey);
            const best = [...scored].sort((a, b) => b.score - a.score || b.activity - a.activity || a.order - b.order)[0];

            if (best.score > 0) {
                if (current && current.score >= best.score - 25) {
                    return { ...current, urgent: false };
                }
                return {
                    ...best,
                    urgent: best.score >= 175 && (!current || best.score >= current.score + 90)
                };
            }

            const lastIndex = scored.findIndex(item => item.key === lastKey);
            return lastIndex >= 0 ? scored[(lastIndex + 1) % scored.length] : scored[0];
        },

        ft8BuildAutomationCandidates(bands, modes) {
            const candidates = [];
            let order = 0;
            for (const band of bands) {
                for (const mode of modes) {
                    const frequency = this.ft8GetBandFrequency(band, mode);
                    if (frequency) {
                        candidates.push({ band, mode, frequency, key: `${band}|${mode}`, order });
                        order += 1;
                    }
                }
            }
            return candidates;
        },

        ft8ScoreAutomationCandidate(candidate) {
            const now = Date.now();
            const recentWindowMs = 5 * 60 * 1000;
            const messages = (this.ft8.decodedMessages || []).filter(message => {
                const timestamp = new Date(message?.timestamp || 0).getTime() || 0;
                return (message.band || this.ft8.selectedBand) === candidate.band &&
                    String(message.mode || this.ft8.mode || 'FT8').toUpperCase() === candidate.mode &&
                    (!timestamp || now - timestamp <= recentWindowMs);
            });
            const usableMessages = messages.filter(message => this.ft8PassesAutomationFilters(message, this.ft8MessageIsCallingUs(message)));
            const activeTargets = Object.values(this.ft8.spotTargets || {}).filter(target =>
                target &&
                target.expiresAt > now &&
                target.band === candidate.band &&
                String(target.mode || '').toUpperCase() === candidate.mode &&
                !this.ft8IsAutoCallBackedOff(`${target.call}|${target.band}|${String(target.mode || '').toUpperCase()}`)
            );

            let score = 0;
            let needed = 0;
            let cq = 0;
            let maxSnr = -99;
            for (const message of usableMessages) {
                const meta = this.ft8AnalyzeMessage(message);
                const goalScore = this.ft8AutomationGoalScore(meta, message);
                maxSnr = Math.max(maxSnr, meta.snr);
                if (meta.isCQ) {
                    cq += 1;
                    score += 12;
                }
                if (goalScore > 0) {
                    needed += 1;
                    score += goalScore;
                }
                score += Math.max(0, Math.min(40, meta.snr + 30));
            }

            score += activeTargets.length * 260;
            score += usableMessages.length * 8;
            score += Math.max(0, messages.length - usableMessages.length) * 2;
            if (!messages.length && !activeTargets.length) {
                score -= 35;
            }
            if (candidate.band === this.ft8.selectedBand && candidate.mode === this.ft8.mode) {
                score += 15;
            }

            let reason = 'search';
            if (activeTargets.length) {
                reason = `${activeTargets.length} spot target${activeTargets.length === 1 ? '' : 's'}`;
            } else if (needed) {
                reason = `${needed} needed decode${needed === 1 ? '' : 's'}`;
            } else if (usableMessages.length) {
                reason = `${usableMessages.length} active decode${usableMessages.length === 1 ? '' : 's'}`;
            } else if (messages.length) {
                reason = `${messages.length} weak/filtered decode${messages.length === 1 ? '' : 's'}`;
            }

            return {
                ...candidate,
                score,
                activity: activeTargets.length * 10 + usableMessages.length + messages.length,
                reason,
                needed,
                cq,
                maxSnr
            };
        },

        async ft8PollRadioStatus() {
            if (!this.ft8.radioSyncEnabled) {
                return;
            }
            try {
                const response = await fetch(`${window.location.origin}/api/status`, { cache: 'no-store' });
                if (!response.ok) {
                    this.ft8.radioSyncMessage = `Radio sync HTTP ${response.status}`;
                    return;
                }
                const status = await response.json();
                this.ft8ApplyRadioStatus(status);
            } catch (error) {
                console.warn('Unable to sync FT8 radio status:', error);
                this.ft8.radioSyncMessage = `Radio sync failed: ${error.message}`;
            }
        },

        ft8ApplyRadioStatus(status) {
            const frequency = Number(status?.frequency || 0);
            if (!Number.isFinite(frequency) || frequency <= 0) {
                return;
            }

            const pendingTune = this.ft8.pendingRadioTune;
            if (pendingTune && Date.now() - pendingTune.timestamp < 8000) {
                const target = Number(pendingTune.frequency || 0);
                if (target > 0 && Math.abs(frequency - target) <= 0.003) {
                    this.ft8.pendingRadioTune = null;
                    this.ft8.radioSyncMessage = `Radio ${frequency.toFixed(6)} MHz`;
                } else {
                    this.ft8.radioSyncMessage = `Tuning ${target.toFixed(6)} MHz`;
                    return;
                }
            } else if (pendingTune) {
                this.ft8.pendingRadioTune = null;
            }

            const previousFrequency = Number(this.ft8.currentFrequency || 0);
            this.ft8.currentFrequency = frequency;

            const inferredBand = this.ft8InferBandFromFrequency(frequency);
            if (inferredBand) {
                this.ft8.selectedBand = inferredBand;
            }

            const inferredMode = this.ft8InferDigitalModeFromFrequency(frequency);
            if (inferredMode && inferredMode !== this.ft8.mode) {
                this.ft8.mode = inferredMode;
                this.ft8.config.mode = inferredMode;
                this.ft8.bandwidth = inferredMode === 'FT8' ? 50 : 100;
                if (ft8Engine) {
                    ft8Engine.setMode(inferredMode);
                    this.ft8.engine = ft8Engine.getCapabilities();
                }
            }

            if (Math.abs(previousFrequency - frequency) > 0.0005) {
                this.ft8.radioSyncMessage = `Radio ${frequency.toFixed(6)} MHz`;
            }
        },

        startFT8Clock() {
            if (this.ft8ClockTimer) {
                return;
            }
            this.updateFT8Clock();
            this.ft8ClockTimer = setInterval(() => {
                this.updateFT8Clock();
            }, 1000);
        },

        stopFT8Clock() {
            if (this.ft8ClockTimer) {
                clearInterval(this.ft8ClockTimer);
                this.ft8ClockTimer = null;
            }
        },

        updateFT8Clock() {
            this.ft8.utcClock = this.formatFT8Time(new Date().toISOString());
        },

        async ft8PollStatus() {
            try {
                const response = await fetch('/api/ft8/status');
                if (!response.ok) {
                    return;
                }
                const status = await response.json();
                this.updateFT8Status(status);
            } catch (error) {
                console.warn('Unable to poll FT8 status:', error);
            }
        },

        async handleFT8WebSocketMessage(data) {
            const { type, data: payload } = data;

            switch (type) {
                case 'status':
                    this.updateFT8Status(payload);
                    break;

                case 'decoded':
                    this.addDecodedMessage(payload);
                    break;

                case 'audio_stream':
                    // Client-side audio is kept for waterfall display; decode runs
                    // through the backend decoder boundary.
                    if (this.ft8.display.waterfall) {
                        this.handleAudioStream(payload);
                    }
                    break;

                case 'waterfall':
                    if (!this.ft8.display.waterfall) {
                        break;
                    }
                    // Defer waterfall drawing to next frame to avoid blocking
                    requestAnimationFrame(() => {
                        this.updateWaterfall(payload);
                    });
                    break;

                case 'qsos':
                    this.ft8.activeQSOs = payload;
                    break;

                case 'qso_complete':
                    await this.handleQSOComplete(payload);
                    break;

                case 'transmitting':
                    this.handleTransmitting(payload);
                    break;

                default:
                    console.log('Unknown FT8 WebSocket message type:', type);
            }
        },

        ft8InstallKeyboardShortcuts() {
            if (this.ft8EscHandler) {
                return;
            }
            this.ft8EscHandler = async (event) => {
                if (event.key !== 'Escape') {
                    return;
                }
                event.preventDefault();
                await this.ft8StopTransmitOnly();
            };
            window.addEventListener('keydown', this.ft8EscHandler);
        },

        ft8RemoveKeyboardShortcuts() {
            if (!this.ft8EscHandler) {
                return;
            }
            window.removeEventListener('keydown', this.ft8EscHandler);
            this.ft8EscHandler = null;
        },

        async handleAudioStream(audioData) {
            try {
                // Ensure engine is loaded
                if (!ft8Engine) {
                    await loadFT8Engine();
                }

                if (ft8Engine && ft8Engine.ready) {
                    // Convert base64 to Float32Array if needed
                    let samples;
                    if (typeof audioData === 'string') {
                        // Base64 encoded audio
                        const binary = atob(audioData);
                        const bytes = new Uint8Array(binary.length);
                        for (let i = 0; i < binary.length; i++) {
                            bytes[i] = binary.charCodeAt(i);
                        }
                        samples = new Float32Array(bytes.buffer);
                        console.log(`🎵 Audio received: ${samples.length} samples from base64 (${binary.length} bytes)`);
                    } else if (audioData instanceof ArrayBuffer) {
                        samples = new Float32Array(audioData);
                        console.log(`🎵 Audio received: ${samples.length} samples from ArrayBuffer`);
                    } else if (Array.isArray(audioData)) {
                        samples = new Float32Array(audioData);
                        console.log(`🎵 Audio received: ${samples.length} samples from Array`);
                    } else {
                        console.warn('⚠️ Unknown audio format:', typeof audioData);
                        return;
                    }

                    // Log sample statistics
                    if (samples && samples.length > 0) {
                        const min = Math.min(...samples.slice(0, 1000));
                        const max = Math.max(...samples.slice(0, 1000));
                        const avg = samples.slice(0, 1000).reduce((a,b) => a + Math.abs(b), 0) / 1000;
                        console.log(`🎵 Sample preview (first 1000): min=${min.toFixed(4)}, max=${max.toFixed(4)}, avgAbs=${avg.toFixed(4)}`);
                    }

                    // Process audio through the engine boundary. This does not
                    // create decoded messages until receive decode is validated.
                    ft8Engine.processAudio(samples);

                    // Get waterfall data from engine if it provides any.
                    const waterfallData = ft8Engine.getWaterfallData();
                    if (waterfallData.length > 0) {
                        this.ft8.waterfallData = waterfallData;
                        requestAnimationFrame(() => {
                            this.drawWaterfall();
                        });
                    }

                    // Browser-side engine intentionally does not emit decodes;
                    // decoded messages arrive from the backend decoder boundary.
                    const decodedMsgs = ft8Engine.getDecodedMessages();
                    for (const msg of decodedMsgs) {
                        // Check if message is new (not already in list)
                        const exists = this.ft8.decodedMessages.some(
                            m => m.timestamp === msg.timestamp && m.message === msg.message
                        );
                        if (!exists) {
                            this.addDecodedMessage(msg);
                        }
                    }
                }
            } catch (error) {
                console.error('Error handling audio stream:', error);
            }
        },

        updateFT8Status(status) {
            const previousCompleted = Number(this.ft8.stats?.qso_completed || 0);
            this.ft8.connected = status.enabled;
            this.ft8.txEnabled = status.tx_enabled;
            this.ft8.txInProgress = Boolean(status.tx_rf_active ?? status.tx_in_progress);
            this.ft8.txPttCommandActive = Boolean(status.tx_ptt_command_active ?? status.tx_in_progress);
            this.ft8.txRadioMox = Boolean(status.tx_radio_mox);
            this.ft8.txRadioInterlock = String(status.tx_radio_interlock || '');
            this.ft8.txPttBackend = String(status.tx_ptt_backend || this.ft8.txPttBackend || 'flex');
            this.ft8.txPttBackendError = String(status.tx_ptt_backend_error || '');
            this.ft8.autoSequence = status.auto_sequence;
            this.ft8.isTxCycle = status.is_tx_cycle;
            this.ft8.slotIsTx = Boolean(status.slot_is_tx);
            this.ft8.cycleDuration = Number(status.cycle_duration || (this.ft8.mode === 'FT4' ? 7.5 : 15));
            this.ft8.cyclePosition = Number(status.cycle_position || 0);
            this.ft8.cycleRemaining = Number(status.cycle_remaining ?? Math.max(0, this.ft8.cycleDuration - this.ft8.cyclePosition));
            this.ft8.cycleProgress = this.ft8.cycleDuration > 0
                ? Math.max(0, Math.min(100, (this.ft8.cyclePosition / this.ft8.cycleDuration) * 100))
                : 0;
            this.ft8.activeTxMessage = String(status.active_tx_message || '');
            this.ft8.activeAttemptId = String(status.active_attempt_id || '');
            this.ft8.digitalState = String(status.digital_state || 'idle');
            this.ft8.pendingTxIntent = status.pending_tx_intent || null;
            this.ft8.pendingMessage = String(status.pending_message || '');
            this.ft8.txInhibitReason = String(status.tx_inhibit_reason || status.tx_inhibit || '');
            const backendTxOffset = Number(status.tx_audio_frequency || 0);
            if (Number.isFinite(backendTxOffset) && backendTxOffset > 0) {
                this.ft8SetTxOffset(backendTxOffset);
            }
            const activeAutomationTarget = status.automation_controller?.active_target || null;
            const backendRxOffset = Number(
                status.pending_tx_intent?.rx_audio_frequency ||
                activeAutomationTarget?.audio_offset ||
                0
            );
            if (
                Number.isFinite(backendRxOffset) &&
                backendRxOffset > 0 &&
                (status.active_target || status.active_tx_message || status.pending_tx_intent || activeAutomationTarget)
            ) {
                this.ft8SetRxOffset(backendRxOffset);
            }
            this.ft8.automationDecisions = Array.isArray(status.automation_decisions)
                ? status.automation_decisions.slice(-8)
                : [];
            if (this.ft8.activeTxMessage) {
                this.ft8RestoreQsoTargetFromTxMessage(this.ft8.activeTxMessage);
            }
            this.ft8SyncSelectedTxStage(status);
            this.ft8SyncActiveQsoToMainLog(status);
            this.ft8.watchdogLimitSeconds = Number(status.watchdog_limit_seconds || 0);
            this.ft8.watchdogRemainingSeconds = Number(status.watchdog_remaining_seconds || 0);
            this.ft8.watchdogElapsedSeconds = Number(status.watchdog_elapsed_seconds || 0);
            if (status.capabilities) {
                this.ft8.engine = {
                    ...this.ft8.engine,
                    engine: status.engine || this.ft8.engine.engine,
                    license: status.engine_license || this.ft8.engine.license,
                    receive: status.decoder_status || this.ft8.engine.receive,
                    transmit: Boolean(status.capabilities.tx),
                    messageEncode: Boolean(status.capabilities.message_encode),
                    waterfall: Boolean(status.capabilities.waterfall),
                    foxhoundHound: Boolean(status.capabilities.foxhound_hound),
                    foxMode: Boolean(status.capabilities.fox_mode),
                    superfoxRx: Boolean(status.capabilities.superfox_rx),
                    superfoxTx: Boolean(status.capabilities.superfox_tx)
                };
            }
            if (status.special_activity) {
                this.ft8ApplySpecialActivityStatus(status.special_activity);
            }
            if (status.automation_controller) {
                this.ft8.automationController = status.automation_controller;
            }
            this.ft8.stats = {
                decoded_count: status.decoded_count,
                transmitted_count: status.transmitted_count,
                qso_completed: status.qso_completed,
                uptime: status.uptime
            };
            const backendDecodedCount = Number(status.decoded_count || 0);
            if (
                backendDecodedCount > 0 &&
                backendDecodedCount > Number(this.ft8.lastDecodedFetchCount || 0) &&
                !this.ft8.decodedRefreshInFlight
            ) {
                this.ft8RefreshDecodedMessages(backendDecodedCount);
            }
            this.ft8.txQueue = Array(status.tx_queue_length).fill('queued');
            if (typeof status.auto_cq_remaining === 'number') {
                this.ft8.automation.autoCQRemaining = status.auto_cq_remaining;
            }
            if (typeof status.auto_call_remaining === 'number') {
                this.ft8.automation.autoCallRemaining = status.auto_call_remaining;
            }
            if (status.transmit_status && status.transmit_status !== 'idle') {
                this.ft8.radioSyncMessage = status.transmit_status;
            }
            const completedCount = Number(status.qso_completed || 0);
            const transmitStatus = String(status.transmit_status || '').toLowerCase();
            const watchdogStopped = transmitStatus.includes('watchdog halted') || transmitStatus.includes('watchdog expired');
            const attemptCleared = String(status.digital_state || '').toLowerCase() === 'aborted_cancelled' || status.last_cancel_abort_reason === 'watchdog-expired';
            if (
                (completedCount > previousCompleted || watchdogStopped || attemptCleared) &&
                Number(status.tx_queue_length || 0) === 0 &&
                Number(status.active_qsos || 0) === 0 &&
                !status.pending_tx_intent
            ) {
                this.ft8ClearQsoTarget({ haltTx: false, keepStatus: true });
            }
        },

        ft8SyncSelectedTxStage(status = {}) {
            const activeQso = status.active_qso || {};
            const pending = status.pending_tx_intent || {};
            const text = String(
                status.pending_message ||
                pending.message ||
                status.active_tx_message ||
                this.ft8.activeTxMessage ||
                ''
            ).toUpperCase().trim();
            const parts = this.ft8MessageTokens(text);
            const last = parts[parts.length - 1] || '';
            let selected = 0;
            if (parts[0] === 'CQ') {
                selected = 6;
            } else if (last === '73') {
                selected = 5;
            } else if (last === 'RR73' || last === 'RRR') {
                selected = 4;
            } else if (/^R[+-]\d{2}$/.test(last)) {
                selected = 3;
            } else if (/^[+-]\d{2}$/.test(last)) {
                selected = 2;
            } else if (last) {
                selected = 1;
            }
            if (!selected) {
                const state = String(activeQso.state || status.digital_state || '').toLowerCase();
                if (state.includes('sending_73')) selected = 5;
                else if (state.includes('sending_rrr')) selected = 4;
                else if (state.includes('sending_report')) selected = 2;
                else if (state.includes('waiting_response') || state.includes('tx_pending') || state.includes('tx_active')) selected = 1;
            }
            if (selected && selected !== this.ft8.selectedTxMessage) {
                this.ft8.selectedTxMessage = selected;
            }
        },

        addDecodedMessage(message) {
            const normalized = this.ft8NormalizeDecodedMessage(message);
            const result = this.ft8AppendDecodedMessage(normalized);
            const row = result?.row || normalized;
            if (!result?.created) {
                return;
            }
            this.ft8EvaluateAlert(row);
            this.ft8EnrichDecodedMessage(row);
            this.ft8.lastDecodedFetchCount = Math.max(
                this.ft8.lastDecodedFetchCount,
                this.ft8.stats.decoded_count || this.ft8.decodedMessages.length
            );

            // Play notification sound for CQ
            if (String(row.message || '').includes('CQ')) {
                // Could add audio notification here
            }
            this.ft8ScrollDecodePanesToBottom();
        },

        ft8AppendDecodedMessage(message) {
            const key = this.ft8DecodedMessageKey(message);
            const existing = this.ft8.decodedMessages.find(row => this.ft8DecodedMessageKey(row) === key);
            if (existing) {
                this.ft8MergeDecodedMessage(existing, message);
                return { row: existing, created: false };
            }
            message._receivedOrder = Number(message._receivedOrder || 0) || this.ft8NextDecodedOrder();
            message._displayAccepted = this.ft8PassesStableDecodeFilters(message);
            this.ft8.decodedMessages.push(message);
            if (this.ft8.decodedMessages.length > 300) {
                this.ft8.decodedMessages.shift();
            }
            return { row: message, created: true };
        },

        ft8NextDecodedOrder() {
            this.ft8.decodedReceiveSequence = Number(this.ft8.decodedReceiveSequence || 0) + 1;
            return this.ft8.decodedReceiveSequence;
        },

        ft8MergeDecodedMessage(existing, incoming) {
            if (!existing || !incoming) {
                return existing;
            }
            const preserved = {
                receivedOrder: Number(existing._receivedOrder || 0) || this.ft8NextDecodedOrder(),
                displayAccepted: existing._displayAccepted,
                statusLoading: Boolean(existing._statusLoading),
                statusPending: Boolean(existing._statusPending),
                callStatus: existing.call_status,
                dxccStatus: existing.dxcc_status,
                dxccTag: existing.dxcc_tag,
                dxcc: existing.dxcc,
                country: existing.country,
                cqZone: existing.cq_zone,
                ituZone: existing.itu_zone,
                continent: existing.continent,
                needed: existing.needed,
                neededOnBand: existing.needed_on_band
            };
            Object.assign(existing, incoming);
            existing._receivedOrder = preserved.receivedOrder;
            existing._displayAccepted = preserved.displayAccepted !== undefined
                ? preserved.displayAccepted
                : this.ft8PassesStableDecodeFilters(existing);
            existing._statusLoading = preserved.statusLoading || Boolean(incoming._statusLoading);
            existing._statusPending = preserved.statusPending || Boolean(incoming._statusPending);
            if (!incoming.call_status && preserved.callStatus) existing.call_status = preserved.callStatus;
            if (!incoming.dxcc_status && preserved.dxccStatus) existing.dxcc_status = preserved.dxccStatus;
            if (!incoming.dxcc_tag && preserved.dxccTag) existing.dxcc_tag = preserved.dxccTag;
            if (incoming.dxcc === undefined && preserved.dxcc !== undefined) existing.dxcc = preserved.dxcc;
            if (!incoming.country && preserved.country) existing.country = preserved.country;
            if (!incoming.cq_zone && preserved.cqZone) existing.cq_zone = preserved.cqZone;
            if (!incoming.itu_zone && preserved.ituZone) existing.itu_zone = preserved.ituZone;
            if (!incoming.continent && preserved.continent) existing.continent = preserved.continent;
            if (!incoming.needed && preserved.needed) existing.needed = preserved.needed;
            if (!incoming.needed_on_band && preserved.neededOnBand) existing.needed_on_band = preserved.neededOnBand;
            if (this.ft8HasResolvedStatus(existing.call_status) && this.ft8HasResolvedStatus(existing.dxcc_status)) {
                existing._statusPending = false;
            }
            return existing;
        },

        ft8DecodedMessageKey(message) {
            return [
                message?.source || '',
                message?.direction || '',
                message?.timestamp || '',
                Number(message?.freq || 0).toFixed(0),
                String(message?.message || '').trim().toUpperCase()
            ].join('|');
        },

        ft8ScrollDecodePanesToBottom() {
            this.$nextTick(() => {
                for (const refName of ['ft8BandActivityList', 'ft8RxFrequencyList']) {
                    const element = this.$refs[refName];
                    if (element) {
                        element.scrollTop = element.scrollHeight;
                    }
                }
            });
        },

        updateWaterfall(data) {
            if (!this.ft8.display.waterfall) {
                return;
            }
            if (Array.isArray(data) && data.length > 0) {
                this.ft8.waterfallData = this.ft8VisibleWaterfallRows(data);
                this.drawWaterfall();
            }
        },

        async ft8RefreshDecodedMessages(expectedCount = 0) {
            if (this.ft8.decodedRefreshInFlight) {
                return;
            }
            this.ft8.decodedRefreshInFlight = true;
            try {
                const response = await fetch('/api/ft8/decoded?limit=100');
                if (!response.ok) {
                    return;
                }
                const payload = await response.json();
                const messages = Array.isArray(payload.messages) ? payload.messages : [];
                const rowsForLookup = [];
                messages.forEach(message => {
                    const normalized = this.ft8NormalizeDecodedMessage(message);
                    const result = this.ft8AppendDecodedMessage(normalized);
                    const row = result?.row || normalized;
                    if (result?.created) {
                        this.ft8EvaluateAlert(row);
                    }
                    rowsForLookup.push(row);
                });
                rowsForLookup.slice(-20).forEach(message => {
                    this.ft8EnrichDecodedMessage(message);
                });
                this.ft8.lastDecodedFetchCount = Math.max(
                    Number(this.ft8.lastDecodedFetchCount || 0),
                    Number(expectedCount || 0),
                    Number(this.ft8.stats.decoded_count || 0),
                    messages.length
                );
                this.ft8ScrollDecodePanesToBottom();
            } catch (error) {
                console.warn('Unable to refresh FT8 decoded messages:', error);
            } finally {
                this.ft8.decodedRefreshInFlight = false;
            }
        },

        async handleQSOComplete(qso) {
            console.log('QSO complete:', qso);

            const payload = {
                ...this.ft8QsoPayload(qso),
                logged: Boolean(qso?.logged),
                log_status: qso?.log_status || 'unknown',
                log_result: qso?.log_result || null
            };
            this.ft8BroadcastDigitalEvent('qso-complete', payload);
            this.ft8.radioSyncMessage = qso?.logged
                ? `Logged ${payload.callsign} to Wavelog`
                : `QSO complete: ${payload.callsign}; backend log status ${qso?.log_status || 'unknown'}`;
            if (this.ft8.specialActivity.returnToStandardAfterQso && this.ft8.specialActivity.submode !== 'standard') {
                this.ft8ApplySpecialActivity({ enabled: false, submode: 'standard', superFoxVerified: false });
                if (this.ft8.connected) {
                    await this.ft8SyncServiceConfig();
                }
            }
            this.ft8ClearQsoTarget({ haltTx: false, keepStatus: true });
            this.ft8.radioSyncMessage = `QSO complete: ${payload.callsign}`;
        },

        handleTransmitting(data) {
            const text = String(data?.message || '').trim().toUpperCase();
            console.log('Transmitting:', text);
            if (!text) {
                return;
            }
            this.ft8RestoreQsoTargetFromTxMessage(text);
            const pending = this.ft8.decodedMessages.find(message =>
                (message?.source === 'tx_pending' || message?.direction === 'tx_pending') &&
                String(message?.message || '').trim().toUpperCase() === text
            );
            const selected = this.ft8.selectedMessage || {};
            const rowData = {
                timestamp: new Date().toISOString(),
                message: text,
                snr: null,
                dt: null,
                freq: Number(data?.result?.audio_frequency || this.ft8.txOffset || 0),
                source: 'tx',
                direction: 'tx',
                band: this.ft8.selectedBand,
                mode: this.ft8.mode,
                base_frequency: this.ft8.currentFrequency,
                call_status: 'TX',
                dxcc_status: selected.dxcc_status || selected.call_status || '-',
                country: selected.country || selected.dxcc_name || '',
                dxcc: selected.dxcc || ''
            };
            const row = pending || this.ft8NormalizeDecodedMessage(rowData);
            Object.assign(row, rowData);
            row.call_status = 'TX';
            row.dxcc_status = row.dxcc_status || selected.dxcc_status || selected.call_status || '-';
            row.direction = 'tx';
            row.source = 'tx';
            this.ft8.activeTxMessage = text;
            if (!pending) {
                this.ft8AppendDecodedMessage(row);
            }
            this.ft8ScrollDecodePanesToBottom();
        },

        // === Service Control ===

        async ft8ToggleConnection() {
            if (this.ft8.connected) {
                await this.ft8StopService();
            } else {
                await this.ft8StartService();
            }
        },

        async ft8StartService() {
            this.ft8.isLoading = true;
            this.ft8.loadingMessage = 'Starting FT8 service...';
            this.ft8.errorMessage = '';

            try {
                // Validate input before sending
                const callsignValidation = validateCallsign(this.ft8.mycall);
                if (!callsignValidation.valid) {
                    throw new Error(`Callsign validation failed: ${callsignValidation.error}`);
                }

                const gridValidation = validateGridSquare(this.ft8.mygrid);
                if (!gridValidation.valid) {
                    throw new Error(`Grid square validation failed: ${gridValidation.error}`);
                }

                const config = this.ft8.config || {};
                const serverValidation = validateNetworkServer(
                    config.networkServer || '192.168.0.199:4992'
                );
                if (!serverValidation.valid) {
                    throw new Error(`Network server validation failed: ${serverValidation.error}`);
                }

                const response = await fetch('/api/ft8/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        mode: this.ft8.mode,
                        mycall: this.ft8.mycall.toUpperCase().trim(),
                        mygrid: this.ft8.mygrid.toUpperCase().trim(),
                        auto_sequence: false,
                        tx_enabled: false,
                        audioInput: config.audioInput || 'flexradio',
                        audioOutput: config.audioOutput || 'flexradio',
                        sampleRate: Number(config.sampleRate || 48000),
                        waterfallHeight: Number(config.waterfallHeight || 100),
                        waterfallEnabled: Boolean(this.ft8.display.waterfall),
                        networkServer: config.networkServer || '192.168.0.199:4992',
                        rigBackend: config.rigBackend || 'auto',
                        hamlibRigctlPath: config.hamlibRigctlPath || '',
                        hamlibModel: Number(config.hamlibModel || 23005),
                        hamlibRigPath: config.hamlibRigPath || '',
                        hamlibTimeoutSeconds: Number(config.hamlibTimeoutSeconds || 3),
                        pttMethod: config.pttMethod || 'CAT',
                        useFlexRadioAudio: config.useFlexRadioAudio !== undefined ? config.useFlexRadioAudio : true,
                        operatorSettings: this.ft8OperatorSettingsPayload()
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                    throw new Error(errorData.detail || errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }

                console.log('✅ FT8 service started successfully');
                this.ft8.connected = true;
                this.ft8.errorMessage = '';
                await this.ft8PollStatus();
                await this.ft8RefreshDecodedMessages();

            } catch (error) {
                console.error('❌ Error starting FT8 service:', error);
                this.ft8.errorMessage = `Failed to start FT8: ${error.message}`;
                this.ft8.connected = false;

            } finally {
                this.ft8.isLoading = false;
                this.ft8.loadingMessage = '';
            }
        },

        async ft8StopService() {
            this.ft8.isLoading = true;
            this.ft8.loadingMessage = 'Stopping FT8 service...';

            try {
                const response = await fetch('/api/ft8/stop', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }

                console.log('✅ FT8 service stopped successfully');
                this.ft8.connected = false;
                this.ft8.errorMessage = '';

            } catch (error) {
                console.error('❌ Error stopping FT8 service:', error);
                this.ft8.errorMessage = `Failed to stop FT8: ${error.message}`;
                alert(this.ft8.errorMessage);

            } finally {
                this.ft8.isLoading = false;
                this.ft8.loadingMessage = '';
            }
        },

        async ft8ModeChanged() {
            console.log('FT8 mode changed to:', this.ft8.mode);
            this.ft8.mode = String(this.ft8.mode || 'FT8').toUpperCase();
            this.ft8.bandwidth = this.ft8.mode === 'FT8' ? 50 : 100;
            this.ft8.config.mode = this.ft8.mode;
            if (ft8Engine) {
                ft8Engine.setMode(this.ft8.mode);
                this.ft8.engine = ft8Engine.getCapabilities();
            }
            this.ft8SyncFrequencyFromBand();
            this.ft8.pendingRadioTune = {
                frequency: this.ft8.currentFrequency,
                mode: this.ft8.mode,
                timestamp: Date.now()
            };
            if (this.ft8.connected) {
                try {
                    await this.ft8SyncServiceConfig();
                } catch (error) {
                    console.warn('Unable to sync digital service mode:', error);
                    this.ft8.errorMessage = `Mode sync failed: ${error.message}`;
                }
            }
            await this.ft8TuneSelectedBand();
        },

        async ft8SyncServiceConfig() {
            const payload = {
                ...this.ft8.config,
                mode: this.ft8.mode,
                mycall: String(this.ft8.mycall || this.ft8.config.mycall || 'OM0RX').toUpperCase().trim(),
                mygrid: String(this.ft8.mygrid || this.ft8.config.mygrid || 'JN88').toUpperCase().trim(),
                auto_sequence: false,
                tx_enabled: false,
                waterfallEnabled: Boolean(this.ft8.display.waterfall),
                operatorSettings: this.ft8OperatorSettingsPayload()
            };
            const response = await fetch('/api/ft8/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || error.error || `HTTP ${response.status}`);
            }
        },

        ft8SyncFrequencyFromBand() {
            const frequency = this.ft8GetBandFrequency(this.ft8.selectedBand, this.ft8.mode);
            if (frequency) {
                this.ft8.currentFrequency = frequency;
            }
        },

        ft8GetBandFrequency(band, mode) {
            const row = this.ft8.availableBands.find(item => item.band === band);
            if (!row) {
                return null;
            }
            const modeKey = String(mode || this.ft8.mode || 'FT8').toLowerCase();
            const value = Number(row[modeKey] || 0);
            return Number.isFinite(value) && value > 0 ? value : null;
        },

        ft8InferDigitalModeFromFrequency(frequency) {
            const freq = Number(frequency);
            if (!Number.isFinite(freq)) {
                return null;
            }
            const toleranceMhz = 0.003;
            for (const row of this.ft8.availableBands) {
                if (row.ft4 && Math.abs(freq - row.ft4) <= toleranceMhz) {
                    return 'FT4';
                }
                if (row.ft8 && Math.abs(freq - row.ft8) <= toleranceMhz) {
                    return 'FT8';
                }
            }
            return null;
        },

        ft8InferBandFromFrequency(frequency) {
            const freq = Number(frequency);
            if (!Number.isFinite(freq)) {
                return null;
            }

            let closest = null;
            for (const row of this.ft8.availableBands) {
                for (const modeKey of ['ft8', 'ft4']) {
                    if (!row[modeKey]) {
                        continue;
                    }
                    const delta = Math.abs(freq - row[modeKey]);
                    if (!closest || delta < closest.delta) {
                        closest = { band: row.band, delta };
                    }
                }
            }
            if (closest && closest.delta <= 0.05) {
                return closest.band;
            }

            const ranges = [
                ['160m', 1.8, 2.0],
                ['80m', 3.5, 4.0],
                ['60m', 5.0, 5.5],
                ['40m', 7.0, 7.3],
                ['30m', 10.1, 10.15],
                ['20m', 14.0, 14.35],
                ['17m', 18.068, 18.168],
                ['15m', 21.0, 21.45],
                ['12m', 24.89, 24.99],
                ['10m', 28.0, 29.7],
                ['6m', 50.0, 54.0]
            ];
            const match = ranges.find(([, low, high]) => freq >= low && freq <= high);
            return match ? match[0] : null;
        },

        async ft8BandChanged() {
            this.ft8SyncFrequencyFromBand();
            await this.ft8TuneSelectedBand();
        },

        async ft8TuneSelectedBand() {
            const frequency = this.ft8GetBandFrequency(this.ft8.selectedBand, this.ft8.mode);
            if (!frequency) {
                this.ft8.errorMessage = `${this.ft8.mode} frequency is not configured for ${this.ft8.selectedBand}`;
                return;
            }

            this.ft8.currentFrequency = frequency;
            this.ft8.errorMessage = '';

            try {
                await this.ft8TuneRadioFrequency(frequency, this.ft8.mode);
                this.ft8MaybeUpdateFreeTxOffset('band-change');
            } catch (error) {
                console.warn('Unable to tune FT8 band:', error);
                this.ft8.errorMessage = `Radio tune failed: ${error.message}`;
                this.ft8.pendingRadioTune = null;
            }
        },

        ft8MaybeUpdateFreeTxOffset(reason = '') {
            if (!this.ft8.wsjtz.freeFrequency.enabled) {
                return;
            }
            if (this.ft8.holdTxFreq && reason !== 'manual') {
                return;
            }
            if (reason === 'band-change' && !this.ft8.wsjtz.misc.autoTuneAfterBandChange) {
                return;
            }
            const offset = this.ft8FindFreeTxOffset();
            if (offset) {
                this.ft8SetTxOffset(offset);
            }
        },

        ft8FindFreeTxOffset() {
            const range = this.ft8TxOffsetRange();
            const occupied = (this.ft8.decodedMessages || [])
                .filter(message => (message.band || this.ft8.selectedBand) === this.ft8.selectedBand)
                .filter(message => String(message.mode || this.ft8.mode).toUpperCase() === this.ft8.mode)
                .map(message => Number(message.freq || 0))
                .filter(freq => Number.isFinite(freq) && freq >= range.low && freq <= range.high);
            const preferred = [1500, 1000, 2000, 750, 2250, 500, 2500, 2800, 1200, 1800];
            const candidates = [
                ...preferred,
                ...Array.from({ length: Math.floor((range.high - range.low) / 50) + 1 }, (_, index) => range.low + index * 50)
            ].filter((value, index, values) => value >= range.low && value <= range.high && values.indexOf(value) === index);
            return candidates.find(candidate => !occupied.some(freq => Math.abs(freq - candidate) < 60)) || null;
        },

        ft8TxControlPayload(extra = {}) {
            return {
                tx_audio_frequency: Number(this.ft8.txOffset || 1500),
                tx_even_first: Boolean(this.ft8.txEvenFirst),
                watchdog_enabled: Boolean(this.ft8.wsjtz.watchdog.enabled),
                watchdog_ft8: Number(this.ft8.wsjtz.watchdog.ft8 || 0),
                watchdog_ft4: Number(this.ft8.wsjtz.watchdog.ft4 || 0),
                auto_cq: Boolean(this.ft8.autoCQ),
                auto_call: Boolean(this.ft8.autoCall),
                cq_only: Boolean(this.ft8.cqOnly),
                auto_cq_limit: Number(this.ft8.automation.autoCQCount || 0),
                auto_call_limit: Number(this.ft8.automation.autoCallCount || 0),
                specialActivity: this.ft8SpecialActivityPayload(),
                ...extra
            };
        },

        ft8GenerateMessages() {
            const mycall = String(this.ft8.mycall || this.ft8.config.mycall || '').toUpperCase().trim();
            const mygrid = String(this.ft8.mygrid || this.ft8.config.mygrid || '').toUpperCase().trim().slice(0, 4);
            const call = String(this.ft8.selectedCall || '').toUpperCase().trim();
            const grid = String(this.ft8.selectedGrid || '').toUpperCase().trim().slice(0, 4);
            const report = this.ft8NormaliseReportValue(this.ft8.reportValue || -15);

            this.ft8.txMessages = [
                { id: 1, label: 'Tx 1', text: call ? `${call} ${mycall} ${mygrid}` : '' },
                { id: 2, label: 'Tx 2', text: call ? `${call} ${mycall} ${report}` : '' },
                { id: 3, label: 'Tx 3', text: call ? `${call} ${mycall} R${report}` : '' },
                { id: 4, label: 'Tx 4', text: call ? `${call} ${mycall} RR73` : '' },
                { id: 5, label: 'Tx 5', text: call ? `${call} ${mycall} 73` : '' },
                { id: 6, label: 'Tx 6', text: `CQ ${mycall} ${mygrid || grid || 'JN88'}` }
            ];
            if (!call) {
                this.ft8.selectedTxMessage = 6;
            } else if (this.ft8.selectedTxMessage === 6) {
                this.ft8.selectedTxMessage = 1;
            }
        },

        ft8NormaliseReportValue(value) {
            const text = String(value ?? '').trim().toUpperCase().replace(/^R/, '');
            const match = text.match(/^([+-]?)(\d{1,2})$/);
            if (!match) {
                return '-15';
            }
            const number = Math.max(-30, Math.min(30, Number(`${match[1] || ''}${match[2]}`)));
            const sign = number >= 0 ? '+' : '-';
            return `${sign}${String(Math.abs(number)).padStart(2, '0')}`;
        },

        ft8SignalReportFromDecode(message) {
            const snr = Number(message?.snr);
            const value = Number.isFinite(snr) ? Math.max(-30, Math.min(30, Math.round(snr))) : -15;
            const sign = value >= 0 ? '+' : '-';
            return `${sign}${String(Math.abs(value)).padStart(2, '0')}`;
        },

        ft8ResetQsoMessages() {
            const mycall = String(this.ft8.mycall || this.ft8.config.mycall || '').toUpperCase().trim();
            const mygrid = String(this.ft8.mygrid || this.ft8.config.mygrid || '').toUpperCase().trim().slice(0, 4) || 'JN88';
            this.ft8.txMessages = [
                { id: 1, label: 'Tx 1', text: '' },
                { id: 2, label: 'Tx 2', text: '' },
                { id: 3, label: 'Tx 3', text: '' },
                { id: 4, label: 'Tx 4', text: '' },
                { id: 5, label: 'Tx 5', text: '' },
                { id: 6, label: 'Tx 6', text: `CQ ${mycall} ${mygrid}` }
            ];
            this.ft8.selectedTxMessage = 6;
        },

        ft8AddTxDisplayRow(message, options = {}) {
            const text = String(message || '').trim().toUpperCase();
            if (!text) {
                return null;
            }
            this.ft8RestoreQsoTargetFromTxMessage(text);
            const selectedCall = String(this.ft8.selectedCall || this.ft8ActiveTxCall() || '').toUpperCase();
            const selectedMessage = selectedCall
                ? (this.ft8.selectedMessage || (this.ft8.decodedMessages || []).find(row => {
                    const rowText = String(row?.message || '').toUpperCase();
                    return rowText.split(/\s+/).map(part => part.replace(/[<>;,]/g, '')).includes(selectedCall);
                }))
                : null;
            const source = options.pending ? 'tx_pending' : 'tx';
            const existing = this.ft8.decodedMessages.find(row =>
                (row?.source === source || row?.direction === source) &&
                String(row?.message || '').trim().toUpperCase() === text
            );
            if (existing) {
                return existing;
            }
            const row = this.ft8NormalizeDecodedMessage({
                timestamp: new Date().toISOString(),
                message: text,
                snr: null,
                dt: null,
                freq: Number(this.ft8.txOffset || 1500),
                source,
                direction: source,
                band: this.ft8.selectedBand,
                mode: this.ft8.mode,
                base_frequency: this.ft8.currentFrequency,
                call_status: options.pending ? 'QUEUED TX' : 'TX',
                dxcc_status: selectedMessage?.dxcc_status || selectedMessage?.call_status || '-',
                country: selectedMessage?.country || selectedMessage?.dxcc_name || '',
                dxcc: selectedMessage?.dxcc || ''
            });
            this.ft8AppendDecodedMessage(row);
            this.ft8ScrollDecodePanesToBottom();
            return row;
        },

        async ft8ClearQsoTarget(options = {}) {
            const haltTx = options.haltTx !== false;
            if (haltTx && this.ft8.engine.transmit && (this.ft8.txEnabled || this.ft8.activeTxMessage)) {
                const response = await fetch('/api/ft8/tx/clear-qso', { method: 'POST' });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                }
                if (payload.stats) {
                    this.updateFT8Status(payload.stats);
                }
            }
            this.ft8.selectedMessage = null;
            this.ft8.selectedCall = '';
            this.ft8.selectedGrid = '';
            this.ft8.lookupTarget = '';
            this.ft8.activeTxMessage = '';
            this.ft8ResetQsoMessages();
            if (!options.keepStatus) {
                this.ft8.radioSyncMessage = 'QSO target cleared';
            }
        },

        async ft8EnableTx() {
            try {
                if (!this.ft8.connected) {
                    await this.ft8StartService();
                    if (!this.ft8.connected) {
                        return;
                    }
                }
                this.ft8GenerateMessages();
                const selected = this.ft8.txMessages.find(tx => tx.id === this.ft8.selectedTxMessage);
                if (!selected?.text) {
                    throw new Error('Select a decoded station or TX message first');
                }
                if (Number(selected.id) !== 6 && !this.ft8HasActiveQsoAttempt()) {
                    const selectedMessage = this.ft8.selectedMessage || this.ft8FindSelectedDecodedMessage();
                    if (!selectedMessage) {
                        throw new Error('Select or double-click a decoded station before TX');
                    }
                    await this.ft8EngageBackendTarget(selectedMessage, {
                        source: 'manual_tx_button',
                        replace_active: true,
                        expectedMessage: selected.text
                    });
                }
                const response = await fetch('/api/ft8/tx/enable', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.ft8TxControlPayload({
                        immediate: Boolean(this.ft8.immediateTxRequest)
                    }))
                });
                if (!response.ok) {
                    const payload = await response.json().catch(() => ({}));
                    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                }
                this.ft8.txEnabled = true;
                this.ft8.immediateTxRequest = false;
                this.ft8.autoSequence = true;
                this.ft8.errorMessage = '';
                await this.ft8PollStatus();
                if (!(Number(selected.id) === 6 && !this.ft8.autoCQ)) {
                    await this.ft8QueueSelectedTxMessage(selected.id, { immediate: true });
                }
            } catch (error) {
                this.ft8.immediateTxRequest = false;
                this.ft8.errorMessage = `Enable TX failed: ${error.message}`;
            }
        },

        async ft8HaltTx() {
            try {
                const response = await fetch('/api/ft8/tx/halt', { method: 'POST' });
                if (!response.ok) {
                    const payload = await response.json().catch(() => ({}));
                    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                }
                this.ft8.txEnabled = false;
                this.ft8.autoCQ = false;
                this.ft8.autoCall = false;
                this.ft8.radioSyncMessage = 'TX halted';
                await this.ft8PollStatus();
            } catch (error) {
                this.ft8.errorMessage = `Halt TX failed: ${error.message}`;
            }
        },

        async ft8ExtendWatchdog() {
            try {
                const response = await fetch('/api/ft8/tx/watchdog/extend', { method: 'POST' });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                }
                if (payload.stats) {
                    this.updateFT8Status(payload.stats);
                } else {
                    await this.ft8PollStatus();
                }
                const minutes = Math.max(1, Math.round(Number(payload.seconds || 0) / 60));
                this.ft8.radioSyncMessage = payload.extended
                    ? `Watchdog extended by ${minutes} min`
                    : 'Watchdog not extended';
            } catch (error) {
                this.ft8.errorMessage = `Watchdog extend failed: ${error.message}`;
            }
        },

        async ft8StopTransmitOnly() {
            if (!this.ft8.engine.transmit) {
                return;
            }
            try {
                const response = await fetch('/api/ft8/tx/abort-current', { method: 'POST' });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                }
                if (payload.stats) {
                    this.updateFT8Status(payload.stats);
                } else {
                    await this.ft8PollStatus();
                }
                this.ft8.radioSyncMessage = 'TX stopped; re-arm TX to transmit again';
            } catch (error) {
                this.ft8.errorMessage = `Stop current call failed: ${error.message}`;
            }
        },

        async ft8SyncBackendAutomationSettings() {
            try {
                const response = await fetch('/api/ft8/automation/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ operatorSettings: this.ft8OperatorSettingsPayload() })
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                }
                if (payload.automation) {
                    this.ft8.automationController = payload.automation;
                }
            } catch (error) {
                console.warn('Unable to sync backend Digital automation settings:', error);
            }
        },

        async ft8PrepareNextWsjtxTarget(options = {}) {
            this.ft8.wsjtxAutomation.preparing = true;
            this.ft8.wsjtxAutomation.lastError = '';
            try {
                const response = await fetch('/api/ft8/automation/wsjtx/prepare-next', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        cq_only: Boolean(options.cqOnly ?? this.ft8.cqOnly),
                        auto_call_start_only: Boolean(options.autoCallStartOnly)
                    })
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                }
                if (payload.automation) {
                    this.ft8.automationController = payload.automation;
                }
                if (payload.status !== 'prepared') {
                    this.ft8.wsjtxAutomation.lastPrepared = null;
                    this.ft8.wsjtxAutomation.lastError = payload.reason || 'No eligible WSJT-X target';
                    this.ft8.radioSyncMessage = `WSJT-X prepare: ${this.ft8.wsjtxAutomation.lastError}`;
                    return payload;
                }
                const target = payload.target || {};
                this.ft8.wsjtxAutomation.lastPrepared = {
                    call: target.call || '',
                    band: target.band || '',
                    mode: target.mode || '',
                    reason: target.reason || '',
                    txDf: payload.wsjtx_target?.txDf || '',
                    rxDf: payload.wsjtx_target?.rxDf || '',
                    txDfReason: payload.tx_df_plan?.reason || '',
                    occupied: Array.isArray(payload.tx_df_plan?.occupied) ? payload.tx_df_plan.occupied : []
                };
                const txDf = this.ft8.wsjtxAutomation.lastPrepared.txDf;
                const txSuffix = txDf ? ` TX ${txDf} Hz` : '';
                this.ft8.radioSyncMessage = `WSJT-X prepared ${target.call || 'target'}${txSuffix}; TX not armed`;
                return payload;
            } catch (error) {
                this.ft8.wsjtxAutomation.lastPrepared = null;
                this.ft8.wsjtxAutomation.lastError = error.message;
                this.ft8.errorMessage = `WSJT-X prepare failed: ${error.message}`;
                return null;
            } finally {
                this.ft8.wsjtxAutomation.preparing = false;
            }
        },

        ft8WsjtxQueueLabel() {
            const controller = this.ft8.automationController || {};
            const queue = Number(controller.queue_length || 0);
            const eligible = Number(controller.eligible_count || 0);
            return `${eligible}/${queue} targets`;
        },

        ft8WsjtxPersistenceLabel() {
            const persistence = this.ft8.automationController?.persistence;
            if (!persistence) {
                return 'DB unknown';
            }
            if (persistence.error) {
                return 'DB error';
            }
            if (persistence.enabled) {
                const loaded = Number(persistence.loaded_count || 0);
                return `DB PostgreSQL ${loaded} loaded`;
            }
            return 'DB memory only';
        },

        ft8WsjtxPersistenceTitle() {
            const persistence = this.ft8.automationController?.persistence;
            if (!persistence) {
                return 'Digital planner persistence state has not been reported yet.';
            }
            if (persistence.error) {
                return `Digital planner persistence error: ${persistence.error}`;
            }
            if (persistence.enabled) {
                const loaded = Number(persistence.loaded_count || 0);
                return `Digital planner target queue is backed by PostgreSQL; ${loaded} recent target${loaded === 1 ? '' : 's'} loaded at startup.`;
            }
            return 'Digital planner target queue is running in memory only for this session.';
        },

        ft8WsjtxPersistenceClass() {
            const persistence = this.ft8.automationController?.persistence;
            if (persistence?.error) {
                return 'error';
            }
            if (persistence?.enabled) {
                return 'postgres';
            }
            if (persistence) {
                return 'memory';
            }
            return 'unknown';
        },

        ft8WsjtxActiveTargetLabel() {
            const active = this.ft8.automationController?.active_target;
            if (active?.call) {
                return `${active.call} ${active.band || ''} ${active.mode || ''}`.trim();
            }
            const target = (this.ft8.automationController?.targets || [])[0];
            if (target?.call) {
                return `next ${target.call} ${target.band || ''} ${target.mode || ''}`.trim();
            }
            return 'no target';
        },

        ft8WsjtxDecisionLabel() {
            const prepared = this.ft8.wsjtxAutomation.lastPrepared;
            if (prepared?.call) {
                const offsets = [
                    prepared.rxDf ? `RX ${prepared.rxDf}` : '',
                    prepared.txDf ? `TX ${prepared.txDf}` : '',
                    prepared.txDfReason ? prepared.txDfReason.replace(/-/g, ' ') : '',
                ].filter(Boolean).join(' / ');
                return `prepared ${prepared.call}${offsets ? ` (${offsets})` : ''}`;
            }
            const error = this.ft8.wsjtxAutomation.lastError;
            if (error) {
                return error;
            }
            const decision = this.ft8.automationController?.last_decision || {};
            return String(decision.reason || decision.decision || 'listening').replaceAll('-', ' ');
        },

        async ft8ArmAutomationTx() {
            if (!this.ft8.connected) {
                await this.ft8StartService();
            }
            const response = await fetch('/api/ft8/tx/enable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.ft8TxControlPayload({
                    auto_call: true,
                    auto_cq: Boolean(this.ft8.autoCQ),
                    cq_only: Boolean(this.ft8.cqOnly),
                    immediate: true
                }))
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
            }
            this.ft8.txEnabled = true;
            this.ft8.autoSequence = true;
            if (payload.stats) {
                this.updateFT8Status(payload.stats);
            }
        },

        async ft8TuneTone() {
            try {
                const response = await fetch('/api/ft8/tx/tune', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tx_audio_frequency: Number(this.ft8.txOffset || 1500),
                        duration_seconds: 5
                    })
                });
                if (!response.ok) {
                    const payload = await response.json().catch(() => ({}));
                    throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
                }
                this.ft8.radioSyncMessage = 'Tune tone sent';
            } catch (error) {
                this.ft8.errorMessage = `Tune failed: ${error.message}`;
            }
        },

        ft8VisibleBandActivity() {
            const messages = Array.isArray(this.ft8.decodedMessages) ? this.ft8.decodedMessages : [];
            return this.ft8SortDigitalMessages(messages.filter(message => {
                const isTx = message?.direction === 'tx' || message?.source === 'tx' || message?.direction === 'tx_pending' || message?.source === 'tx_pending';
                return !isTx && message?._displayAccepted !== false && this.ft8PassesStableDecodeFilters(message);
            }));
        },

        ft8VisibleBandActivityRows() {
            return this.ft8WithDecodePassSeparators(this.ft8VisibleBandActivity());
        },

        ft8VisibleRxFrequency() {
            const messages = Array.isArray(this.ft8.decodedMessages) ? this.ft8.decodedMessages : [];
            const selected = this.ft8.selectedMessage;
            const rxOffset = Number(this.ft8.rxOffset || selected?.freq || 0);
            const selectedCall = String(this.ft8.selectedCall || this.ft8ActiveTxCall() || '').toUpperCase();
            if (!rxOffset) {
                return selected ? [selected] : [];
            }
            const nearby = messages.filter(message => {
                const text = String(message?.message || '').toUpperCase();
                if (message?.direction === 'tx' || message?.source === 'tx' || message?.direction === 'tx_pending' || message?.source === 'tx_pending') {
                    return true;
                }
                return Math.abs(Number(message.freq || 0) - rxOffset) <= 25;
            });
            if (nearby.length || !selected) {
                return this.ft8SortDigitalMessages(nearby);
            }
            return [selected];
        },

        ft8VisibleRxFrequencyRows() {
            return this.ft8WithDecodePassSeparators(this.ft8VisibleRxFrequency());
        },

        ft8SortDigitalMessages(messages) {
            const timestampValue = message => new Date(message?.timestamp || 0).getTime() || 0;
            const sorted = [...messages];
            const orderValue = message => Number(message?._receivedOrder || 0);
            return sorted.sort((a, b) =>
                timestampValue(a) - timestampValue(b) ||
                orderValue(a) - orderValue(b) ||
                Number(a?.freq || 0) - Number(b?.freq || 0)
            );
        },

        ft8SortAutomationMessages(messages) {
            const priority = String(this.ft8.automation.priority || 'last');
            const timestampValue = message => new Date(message?.timestamp || 0).getTime() || 0;
            const distanceValue = message => Number(message?.distance_km || message?.distance || 0);
            const sorted = [...messages];
            if (priority === 'signal') {
                return sorted.sort((a, b) => Number(b?.snr ?? -99) - Number(a?.snr ?? -99) || timestampValue(b) - timestampValue(a));
            }
            if (priority === 'distance') {
                return sorted.sort((a, b) => distanceValue(b) - distanceValue(a) || timestampValue(b) - timestampValue(a));
            }
            return sorted.sort((a, b) => timestampValue(b) - timestampValue(a));
        },

        ft8NormalizeDecodedMessage(message) {
            const normalized = { ...(message || {}) };
            normalized.mode = String(normalized.mode || this.ft8.mode || 'FT8').toUpperCase();
            normalized.band = normalized.band || this.ft8.selectedBand || this.ft8InferBandFromFrequency(this.ft8.currentFrequency);
            normalized.base_frequency = Number(normalized.base_frequency || normalized.frequency_mhz || this.ft8.currentFrequency || 0);
            normalized.callsign = normalized.callsign || normalized.call || this.getFT8MessageCall(normalized);
            normalized.grid = normalized.grid || normalized.gridsquare || this.getFT8MessageGrid(normalized);
            normalized.decode_pass_key = this.ft8DecodePassKey(normalized);
            normalized._statusPending = Boolean(normalized.callsign && (
                !this.ft8HasResolvedStatus(normalized.call_status) ||
                !this.ft8HasResolvedStatus(normalized.dxcc_status)
            ));
            return normalized;
        },

        ft8DecodePassKey(message) {
            const timestamp = this.formatFT8CompactTime(message?.timestamp || new Date().toISOString());
            const band = message?.band || this.ft8.selectedBand || '';
            const mode = String(message?.mode || this.ft8.mode || 'FT8').toUpperCase();
            const frequency = Number(message?.base_frequency || this.ft8.currentFrequency || 0);
            return `${timestamp}|${band}|${mode}|${frequency.toFixed(6)}`;
        },

        ft8DecodePassLabel(message) {
            const timestamp = this.formatFT8CompactTime(message?.timestamp || new Date().toISOString());
            const band = message?.band || this.ft8.selectedBand || '?';
            const mode = String(message?.mode || this.ft8.mode || 'FT8').toUpperCase();
            const frequency = Number(message?.base_frequency || this.ft8.currentFrequency || 0);
            const frequencyText = frequency > 0 ? `${frequency.toFixed(3)} MHz` : 'frequency unknown';
            return `${timestamp} UTC - ${band} ${mode} - ${frequencyText}`;
        },

        ft8WithDecodePassSeparators(messages) {
            const rows = [];
            let lastKey = '';
            for (const message of messages || []) {
                const key = message?.decode_pass_key || this.ft8DecodePassKey(message);
                if (key !== lastKey) {
                    rows.push({
                        _separator: true,
                        key: `pass-${key}`,
                        label: this.ft8DecodePassLabel(message)
                    });
                    lastKey = key;
                }
                rows.push(message);
            }
            return rows;
        },

        isFT8CQMessage(message) {
            const text = String(message?.message || '').trim().toUpperCase();
            if (text === 'CQ' || text.startsWith('CQ ')) {
                return true;
            }
            return this.ft8.automation.treat73AsCQ && /\b(RR73|73)\b/.test(text);
        },

        ft8AnalyzeMessage(message) {
            return {
                call: this.getFT8MessageCall(message),
                grid: this.getFT8MessageGrid(message),
                text: String(message?.message || '').trim().toUpperCase(),
                snr: Number(message?.snr ?? -99),
                isCQ: this.isFT8CQMessage(message),
                band: message?.band || this.ft8.selectedBand,
                mode: String(message?.mode || this.ft8.mode || 'FT8').toUpperCase(),
                dxcc: message?.dxcc || message?.country || message?.dxcc_name || '',
                continent: message?.continent || message?.cont || '',
                cqZone: message?.cq_zone || message?.cqZone || '',
                ituZone: message?.itu_zone || message?.ituZone || '',
                state: message?.state || message?.us_state || '',
                lotw: Boolean(message?.lotw || message?.lotw_user),
                needed: message?.needed || message?.need || {},
                neededOnBand: message?.needed_on_band || message?.need_on_band || {}
            };
        },

        ft8PassesDisplayFilters(message) {
            if (message?.direction === 'tx' || message?.source === 'tx') {
                return true;
            }
            const selectedCall = String(this.ft8.selectedCall || this.ft8ActiveTxCall() || '').toUpperCase();
            const text = String(message?.message || '').toUpperCase();
            if (selectedCall && this.ft8MessageIsCallingUs(message) && text.split(/\s+/).includes(selectedCall)) {
                return true;
            }
            const meta = this.ft8AnalyzeMessage(message);
            if (meta.snr < Number(this.ft8.automation.minSignal ?? -30)) {
                return false;
            }
            if (this.ft8.cqOnly && !meta.isCQ) {
                return false;
            }
            if (meta.call && this.ft8IsIgnoredCall(meta.call)) {
                return false;
            }
            if (this.ft8.filtering && !this.ft8MatchesNeedFilters(meta, this.ft8.filters)) {
                return false;
            }
            return true;
        },

        ft8PassesStableDecodeFilters(message) {
            if (message?.direction === 'tx' || message?.source === 'tx') {
                return true;
            }
            const selectedCall = String(this.ft8.selectedCall || this.ft8ActiveTxCall() || '').toUpperCase();
            const text = String(message?.message || '').toUpperCase();
            if (selectedCall && this.ft8MessageIsCallingUs(message) && text.split(/\s+/).includes(selectedCall)) {
                return true;
            }
            const meta = this.ft8AnalyzeMessage(message);
            if (meta.snr < Number(this.ft8.automation.minSignal ?? -30)) {
                return false;
            }
            if (this.ft8.cqOnly && !this.ft8IsCqOrClosingMessage(message)) {
                return false;
            }
            if (meta.call && this.ft8IsIgnoredCall(meta.call)) {
                return false;
            }
            return true;
        },

        ft8IsCqOrClosingMessage(message) {
            const text = String(message?.message || '').trim().toUpperCase();
            return text === 'CQ' || text.startsWith('CQ ') || /\b(RR73|73)\b/.test(text);
        },

        ft8PassesAutomationFilters(message, directedCaller = false) {
            const meta = this.ft8AnalyzeMessage(message);
            if (meta.snr < Number(this.ft8.automation.minSignal ?? -30)) {
                return false;
            }
            if (meta.call && this.ft8IsIgnoredCall(meta.call)) {
                return false;
            }
            if (this.ft8.cqOnly && !meta.isCQ && !directedCaller) {
                return false;
            }
            if (directedCaller && !this.ft8.wsjtz.misc.applyFilteringToCallers) {
                return true;
            }
            return this.ft8PassesDisplayFilters(message);
        },

        ft8AutomationGoalScore(meta, message = {}) {
            const callStatus = this.ft8NormalizeStatusKey(message.call_status || '');
            const dxccStatus = this.ft8NormalizeStatusKey(message.dxcc_status || '');
            const statusText = `${callStatus} ${dxccStatus}`.toLowerCase();

            if (dxccStatus === 'ATNO' || meta.needed?.dxcc) {
                return 1000;
            }
            if (meta.neededOnBand?.dxcc || /dxcc.*new band|c\/new band|w\/new band|new band\+mode|new band\/mode/i.test(statusText)) {
                return 800;
            }
            if (meta.neededOnBand?.call || /new band/i.test(callStatus)) {
                return 650;
            }
            if (meta.needed?.grid || meta.neededOnBand?.grid || /grid/i.test(statusText)) {
                return 500;
            }
            if (/new mode/i.test(statusText) || meta.needed?.mode || meta.neededOnBand?.mode) {
                return 350;
            }
            if (meta.needed?.call || /new call/i.test(callStatus)) {
                return 200;
            }
            return 0;
        },

        ft8MatchesNeedFilters(meta, filters) {
            if (filters.lotwOnly && !meta.lotw) {
                return false;
            }
            if (meta.continent && filters.continents && filters.continents[meta.continent] === false) {
                return false;
            }
            if (!this.ft8MatchesPrefixFilter(meta.call, this.ft8.filterPrefixes)) {
                return false;
            }
            if (!this.ft8MatchesStateFilter(meta.state)) {
                return false;
            }
            const activeNew = this.ft8ActiveNeedKeys(filters.new);
            const activeBand = this.ft8ActiveNeedKeys(filters.onBand);
            if (!activeNew.length && !activeBand.length) {
                return true;
            }
            const hasNeedData = Boolean(meta.needed && Object.keys(meta.needed).length) ||
                Boolean(meta.neededOnBand && Object.keys(meta.neededOnBand).length);
            if (!hasNeedData) {
                return true;
            }
            return activeNew.some(key => Boolean(meta.needed[key])) ||
                activeBand.some(key => Boolean(meta.neededOnBand[key]));
        },

        ft8ActiveNeedKeys(group) {
            const map = {
                call: 'call',
                dxcc: 'dxcc',
                continent: 'continent',
                grid: 'grid',
                cqZone: 'cqZone',
                ituZone: 'ituZone'
            };
            return Object.entries(group || {})
                .filter(([, enabled]) => enabled)
                .map(([key]) => map[key] || key);
        },

        ft8MatchesPrefixFilter(call, prefixesText) {
            if (this.ft8.prefixFilterMode === 'off') {
                return true;
            }
            const raw = String(prefixesText || '').trim();
            if (!raw || !call) {
                return true;
            }
            const lines = raw.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
            const activeLine = lines.find(line => line.includes(':') && line.split(':')[0].trim().toLowerCase() === this.ft8.selectedBand.toLowerCase()) ||
                lines.find(line => !line.includes(':'));
            if (!activeLine) {
                return true;
            }
            const tokens = activeLine.replace(/^[^:]+:/, '').split(',').map(token => token.trim().toUpperCase()).filter(Boolean);
            if (!tokens.length) {
                return true;
            }
            const matched = tokens.some(token => call.toUpperCase().startsWith(token.replace(/^\+/, '')));
            return this.ft8.prefixFilterMode === 'exclude' ? !matched : matched;
        },

        ft8MatchesStateFilter(state) {
            if (this.ft8.stateFilterMode === 'off') {
                return true;
            }
            const value = String(state || '').toUpperCase();
            if (!value) {
                return true;
            }
            const raw = String(this.ft8.stateFilter || '').trim();
            if (!raw) {
                return true;
            }
            const activeLine = raw.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
                .find(line => line.includes(':') && line.split(':')[0].trim().toLowerCase() === this.ft8.selectedBand.toLowerCase()) || raw;
            const tokens = activeLine.replace(/^[^:]+:/, '').split(',').map(token => token.trim().toUpperCase()).filter(Boolean);
            const matched = tokens.includes(value);
            return this.ft8.stateFilterMode === 'exclude' ? !matched : matched;
        },

        ft8ListIncludes(listText, call) {
            const value = String(call || '').toUpperCase();
            return String(listText || '')
                .split(/\s+/)
                .map(item => item.trim().toUpperCase())
                .filter(Boolean)
                .includes(value);
        },

        ft8IsIgnoredCall(call) {
            const value = String(call || '').toUpperCase();
            if (!value) {
                return false;
            }
            this.ft8PruneAutoIgnoreList();
            return this.ft8ListIncludes(this.ft8.ignoredStations, value) ||
                this.ft8ListIncludes(this.ft8.wsjtz.ignoreList.permanent, value) ||
                Boolean(this.ft8.autoIgnoredStations?.[value]);
        },

        ft8NormaliseAutoCallEntry(key) {
            const raw = this.ft8.autoCallQueued?.[key];
            if (!raw) {
                return { attempts: 0, lastQueued: 0, backoffUntil: 0 };
            }
            if (typeof raw === 'number') {
                return { attempts: 1, lastQueued: raw, backoffUntil: 0 };
            }
            return {
                attempts: Number(raw.attempts || 0),
                lastQueued: Number(raw.lastQueued || 0),
                backoffUntil: Number(raw.backoffUntil || 0)
            };
        },

        ft8PruneAutoCallBackoff() {
            const now = Date.now();
            const resetMs = Math.max(1, Number(this.ft8.automation.retryResetMinutes || 60)) * 60 * 1000;
            for (const [key, raw] of Object.entries(this.ft8.autoCallQueued || {})) {
                const entry = this.ft8NormaliseAutoCallEntry(key);
                if (entry.lastQueued && now - entry.lastQueued > resetMs) {
                    if (typeof this.$delete === 'function') {
                        this.$delete(this.ft8.autoCallQueued, key);
                    } else {
                        delete this.ft8.autoCallQueued[key];
                    }
                }
            }
            for (const [key, until] of Object.entries(this.ft8.autoCallBackoff || {})) {
                if (Number(until || 0) <= now) {
                    if (typeof this.$delete === 'function') {
                        this.$delete(this.ft8.autoCallBackoff, key);
                    } else {
                        delete this.ft8.autoCallBackoff[key];
                    }
                }
            }
        },

        ft8IsAutoCallBackedOff(key) {
            this.ft8PruneAutoCallBackoff();
            const now = Date.now();
            const entry = this.ft8NormaliseAutoCallEntry(key);
            return Number(this.ft8.autoCallBackoff?.[key] || entry.backoffUntil || 0) > now;
        },

        ft8RecordAutoCallAttempt(key) {
            const now = Date.now();
            const current = this.ft8NormaliseAutoCallEntry(key);
            const attempts = current.attempts + 1;
            const maxAttempts = Math.max(1, Math.min(20, Number(this.ft8.automation.maxAttemptsPerTarget || 3)));
            const backoffMs = Math.max(1, Number(this.ft8.automation.retryBackoffMinutes || 10)) * 60 * 1000;
            const entry = {
                attempts,
                lastQueued: now,
                backoffUntil: attempts >= maxAttempts ? now + backoffMs : now + 10 * 60 * 1000
            };
            if (typeof this.$set === 'function') {
                this.$set(this.ft8.autoCallQueued, key, entry);
                this.$set(this.ft8.autoCallBackoff, key, entry.backoffUntil);
            } else {
                this.ft8.autoCallQueued[key] = entry;
                this.ft8.autoCallBackoff[key] = entry.backoffUntil;
            }
            return entry;
        },

        ft8AutoIgnoreCall(call, reason = 'auto') {
            const value = String(call || '').toUpperCase();
            if (!this.ft8.autoIgnore || !value) {
                return;
            }
            const resetMinutes = Number(this.ft8.wsjtz.ignoreList.resetInterval || 0);
            const expiresAt = resetMinutes > 0 ? Date.now() + resetMinutes * 60 * 1000 : 0;
            if (typeof this.$set === 'function') {
                this.$set(this.ft8.autoIgnoredStations, value, { reason, expiresAt });
            } else {
                this.ft8.autoIgnoredStations[value] = { reason, expiresAt };
            }
        },

        ft8PruneAutoIgnoreList() {
            const now = Date.now();
            for (const [call, entry] of Object.entries(this.ft8.autoIgnoredStations || {})) {
                if (entry?.expiresAt && entry.expiresAt <= now) {
                    if (typeof this.$delete === 'function') {
                        this.$delete(this.ft8.autoIgnoredStations, call);
                    } else {
                        delete this.ft8.autoIgnoredStations[call];
                    }
                }
            }
        },

        ft8EvaluateAlert(message) {
            const meta = this.ft8AnalyzeMessage(message);
            if (!meta.call || !meta.isCQ) {
                return;
            }
            if (!this.ft8MatchesNeedFilters(meta, { ...this.ft8.filters, new: this.ft8.alerts.new, onBand: this.ft8.alerts.onBand })) {
                return;
            }
            const custom = String(this.ft8.customAlerts || '')
                .split(',')
                .map(item => item.trim().toUpperCase())
                .filter(Boolean);
            const hasAlertSelection = this.ft8ActiveNeedKeys(this.ft8.alerts.new).length ||
                this.ft8ActiveNeedKeys(this.ft8.alerts.onBand).length ||
                custom.length;
            if (!hasAlertSelection) {
                return;
            }
            if (custom.length && !custom.some(token => meta.call.includes(token) || meta.text.includes(token))) {
                return;
            }
            const key = `${meta.call}|${meta.band}|${meta.mode}|${message.timestamp || ''}`;
            if (this.ft8.lastAlertKeys[key]) {
                return;
            }
            this.ft8.lastAlertKeys[key] = true;
            const line = `${this.formatFT8Time(message.timestamp || new Date().toISOString())} ${meta.band} ${meta.mode} ${meta.call} ${meta.grid || ''} ${meta.dxcc || ''}`.trim();
            this.ft8.alertLog.unshift(line);
            this.ft8.alertLog = this.ft8.alertLog.slice(0, 100);
        },

        ft8AutomationPlanBands() {
            const parsed = this.ft8ParseBandPlan(this.ft8.automation.bandPlan);
            if (!parsed.length) {
                return [this.ft8.selectedBand];
            }
            const hour = new Date().getUTCHours();
            let active = parsed[0];
            for (const row of parsed) {
                if (hour >= row.hour) {
                    active = row;
                }
            }
            return active.bands;
        },

        ft8ParseBandPlan(planText) {
            return String(planText || '')
                .split(/\r?\n/)
                .map(line => line.trim())
                .filter(Boolean)
                .map(line => {
                    const [hourText, bandsText] = line.split(':');
                    return {
                        hour: Math.max(0, Math.min(23, Number(hourText))),
                        bands: String(bandsText || '').split(',').map(band => band.trim()).filter(Boolean)
                    };
                })
                .filter(row => Number.isFinite(row.hour) && row.bands.length)
                .sort((a, b) => a.hour - b.hour);
        },

        getFT8MessageCall(message) {
            if (message?.callsign || message?.call || message?.dxcall) {
                return String(message.callsign || message.call || message.dxcall).toUpperCase();
            }
            const parts = String(message?.message || '').trim().toUpperCase().split(/\s+/).map(part => part.replace(/[<>;,]/g, '')).filter(Boolean);
            if (!parts.length) {
                return '';
            }
            if (parts[0] === 'CQ') {
                return parts.slice(1).find(part => this.isFT8CallsignToken(part)) || '';
            }
            if (this.ft8.specialActivity.enabled && this.ft8.specialActivity.role === 'hound') {
                const bracketed = String(message?.message || '').toUpperCase().match(/<([^>]+)>/);
                if (bracketed && this.isFT8CallsignToken(bracketed[1])) {
                    return bracketed[1];
                }
                if (parts[0] === String(this.ft8.mycall || '').toUpperCase() && parts[1] && this.isFT8CallsignToken(parts[1])) {
                    return parts[1];
                }
            }
            return parts.find(part => part !== this.ft8.mycall.toUpperCase() && this.isFT8CallsignToken(part)) || '';
        },

        ft8MessageTokens(text) {
            return String(text || '')
                .trim()
                .toUpperCase()
                .split(/\s+/)
                .map(part => part.replace(/[<>;,]/g, ''))
                .filter(Boolean);
        },

        ft8PartnerCallFromTxText(text) {
            const mycall = String(this.ft8.mycall || this.ft8.config.mycall || '').toUpperCase().trim();
            const parts = this.ft8MessageTokens(text);
            if (!parts.length || parts[0] === 'CQ') {
                return '';
            }
            return parts.find(part => part !== mycall && this.isFT8CallsignToken(part)) || '';
        },

        ft8FindDecodedMessageForCall(call) {
            const wanted = String(call || '').toUpperCase().trim();
            if (!wanted) {
                return null;
            }
            return (this.ft8.decodedMessages || []).find(row => {
                if (row?.direction === 'tx' || row?.source === 'tx' || row?.direction === 'tx_pending' || row?.source === 'tx_pending') {
                    return false;
                }
                if (String(row?.callsign || row?.call || '').toUpperCase() === wanted) {
                    return true;
                }
                const rowCall = this.getFT8MessageCall(row);
                if (rowCall === wanted) {
                    return true;
                }
                return this.ft8MessageTokens(row?.message).includes(wanted);
            }) || null;
        },

        ft8RestoreQsoTargetFromTxMessage(text) {
            const call = this.ft8PartnerCallFromTxText(text);
            if (!call) {
                return false;
            }
            const match = this.ft8FindDecodedMessageForCall(call);
            const grid = match
                ? String(match.grid || match.gridsquare || this.getFT8MessageGrid(match) || '').toUpperCase()
                : '';
            const missingTarget = String(this.ft8.selectedCall || '').toUpperCase() !== call;
            const missingGrid = !this.ft8.selectedGrid && grid;
            const missingMessages = !(this.ft8.txMessages || []).some(tx => tx.id === 1 && tx.text);
            if (!missingTarget && !missingGrid && !missingMessages) {
                return false;
            }

            this.ft8.selectedCall = call;
            if (grid) {
                this.ft8.selectedGrid = grid;
            }
            if (!this.ft8.selectedMessage || this.getFT8MessageCall(this.ft8.selectedMessage) !== call) {
                this.ft8.selectedMessage = match || this.ft8.selectedMessage;
            }
            this.ft8.lookupTarget = call;

            const report = this.ft8MessageTokens(text).find(part => /^R?[+-]\d{2}$/.test(part));
            if (report) {
                this.ft8.reportValue = this.ft8NormaliseReportValue(report);
            }
            this.ft8GenerateMessages();
            if (this.ft8.selectedTxMessage === 6) {
                this.ft8.selectedTxMessage = 1;
            }
            return true;
        },

        ft8SyncActiveQsoToMainLog(status = {}) {
            const activeQso = status.active_qso || {};
            const pending = status.pending_tx_intent || this.ft8.pendingTxIntent || {};
            const call = String(
                status.active_target ||
                activeQso.their_call ||
                activeQso.callsign ||
                pending.call ||
                this.ft8.selectedCall ||
                this.ft8PartnerCallFromTxText(status.active_tx_message || this.ft8.activeTxMessage || '')
            ).toUpperCase().trim();
            if (!call) {
                this.ft8.lastLogSyncKey = '';
                return;
            }

            const attemptId = String(status.active_attempt_id || this.ft8.activeAttemptId || pending.attempt_id || '');
            const syncKey = `${attemptId || 'no-attempt'}|${call}`;
            if (this.ft8.lastLogSyncKey === syncKey) {
                return;
            }
            this.ft8.lastLogSyncKey = syncKey;

            const match = this.ft8FindDecodedMessageForCall(call);
            const payload = match ? this.ft8DigitalPayloadFromMessage(match) : {};
            const rawFrequency = Number(activeQso.frequency || pending.dial_frequency || payload.frequency_mhz || this.ft8.currentFrequency || 0);
            const frequencyMhz = rawFrequency > 1 && rawFrequency < 100
                ? rawFrequency
                : Number(this.ft8.currentFrequency || payload.frequency_mhz || 0);
            const grid = String(
                activeQso.their_grid ||
                activeQso.grid ||
                activeQso.gridsquare ||
                pending.grid ||
                payload.gridsquare ||
                this.ft8.selectedGrid ||
                ''
            ).toUpperCase();
            const logPayload = {
                ...payload,
                callsign: call,
                gridsquare: grid,
                frequency_mhz: frequencyMhz,
                band: pending.band || payload.band || this.ft8.selectedBand,
                mode: String(activeQso.mode || pending.mode || payload.mode || this.ft8.mode || 'FT8').toUpperCase(),
                comment: pending.message || status.active_tx_message || this.ft8.activeTxMessage || payload.comment || 'Active built-in digital QSO',
                call_status: payload.call_status || match?.call_status || '',
                dxcc_status: payload.dxcc_status || match?.dxcc_status || '',
                country: payload.country || match?.country || ''
            };

            this.ft8BroadcastDigitalEvent('decoded-selected', logPayload);
            if (typeof this.applyDigitalSelectionToLog === 'function' && document.body.dataset.ft8Standalone !== 'true') {
                this.applyDigitalSelectionToLog(logPayload, 'decoded-selected').catch(error => {
                    console.warn('Unable to sync active digital QSO to log form:', error);
                });
            }
        },

        ft8MessageIsCallingUs(message) {
            const mycall = String(this.ft8.mycall || this.ft8.config.mycall || '').toUpperCase().trim();
            if (!mycall) {
                return false;
            }
            const parts = String(message?.message || '').trim().toUpperCase().split(/\s+/).filter(Boolean);
            return parts.includes(mycall) && Boolean(parts.find(part => part !== mycall && this.isFT8CallsignToken(part)));
        },

        ft8ShouldAutoRespond(message, meta, spotTargetHeard) {
            if (spotTargetHeard || meta.isCQ) {
                return true;
            }
            return Boolean(this.ft8.wsjtz.misc.processTailenders && this.ft8MessageIsCallingUs(message));
        },

        ft8IsSuperFoxDecode(message) {
            const text = String(message?.message || '').toUpperCase();
            return Boolean(message?.superfox || message?.super_fox || message?.superfox_verified) ||
                /\b(VERIFIED|\$VERIFY\$|SUPERFOX|SUPER\s+FOX)\b/.test(text);
        },

        ft8SpecialActivityAllowsAutoCall(message, meta, spotTargetHeard) {
            const activity = this.ft8.specialActivity;
            if (!activity.enabled) {
                return true;
            }
            if (activity.role === 'fox') {
                this.ft8.errorMessage = 'Fox operation is not implemented in the built-in automation controller';
                return false;
            }
            if (activity.submode === 'foxhound') {
                if (this.ft8.mode !== 'FT8') {
                    return false;
                }
                if (activity.callOnlyAfterDecode && !spotTargetHeard && !meta.isCQ && !this.ft8MessageIsCallingUs(message)) {
                    return false;
                }
                const freeOffset = this.ft8FindFreeTxOffset();
                if (freeOffset) {
                    this.ft8SetTxOffset(freeOffset);
                }
                return true;
            }
            if (activity.submode === 'superfox') {
                if (!this.ft8.engine.superfoxRx) {
                    this.ft8.errorMessage = 'SuperFox RX decoder is not available in the built-in engine';
                    return false;
                }
                if (activity.callOnlyAfterDecode && !this.ft8IsSuperFoxDecode(message)) {
                    return false;
                }
                const freeOffset = this.ft8FindFreeTxOffset();
                if (freeOffset) {
                    this.ft8SetTxOffset(freeOffset);
                }
                return true;
            }
            return true;
        },

        isFT8CallsignToken(token) {
            const value = String(token || '').toUpperCase();
            if (!/^[A-Z0-9/]{3,12}$/.test(value) || !/[0-9]/.test(value)) {
                return false;
            }
            if (/^[A-R]{2}[0-9]{2}([A-X]{2})?$/.test(value)) {
                return false;
            }
            return !/^(73|RR73|RRR|R[+-]?[0-9]{2}|[+-]?[0-9]{2})$/.test(value);
        },

        getFT8MessageGrid(message) {
            const parts = String(message?.message || '').trim().toUpperCase().split(/\s+/).filter(Boolean);
            return parts.find(part => /^[A-R]{2}[0-9]{2}([A-X]{2})?$/.test(part) && !/^(RR73|73)$/.test(part)) || '';
        },

        ft8MessageClasses(message) {
            const text = String(message?.message || '').toUpperCase();
            const isTx = message?.direction === 'tx' || message?.source === 'tx' || message?.direction === 'tx_pending' || message?.source === 'tx_pending';
            const selectedCall = String(this.ft8.selectedCall || this.ft8ActiveTxCall() || '').toUpperCase();
            const mycall = String(this.ft8.mycall || this.ft8.config.mycall || '').toUpperCase();
            const isWorking = selectedCall && (
                this.getFT8MessageCall(message) === selectedCall ||
                text.split(/\s+/).includes(selectedCall)
            );
            const isReply = !isTx && selectedCall && mycall && text.split(/\s+/).includes(selectedCall) && text.split(/\s+/).includes(mycall);
            return {
                cq: this.isFT8CQMessage(message),
                tx: Boolean(isTx),
                selected: this.ft8.selectedMessage === message,
                'active-target': Boolean(isWorking && this.ft8.activeAttemptId),
                working: Boolean(isWorking),
                reply: Boolean(isReply)
            };
        },

        ft8SnrCell(message) {
            if (message?.direction === 'tx_pending' || message?.source === 'tx_pending') {
                return 'Tx*';
            }
            if (message?.direction === 'tx' || message?.source === 'tx') {
                return 'Tx';
            }
            const snr = Number(message?.snr || 0);
            return Number.isFinite(snr) ? snr.toFixed(0) : '';
        },

        ft8ActiveTxCall() {
            const parts = String(this.ft8.activeTxMessage || '').toUpperCase().split(/\s+/).filter(Boolean);
            if (!parts.length || parts[0] === 'CQ') {
                return '';
            }
            return parts[0];
        },

        ft8CycleProgressStyle() {
            return `width: ${Math.round(this.ft8.cycleProgress || 0)}%;`;
        },

        ft8CyclePhaseLabel() {
            if (!this.ft8.connected) {
                return 'Idle';
            }
            if (this.ft8.txInProgress) {
                return 'TX';
            }
            return this.ft8.slotIsTx ? 'TX armed' : 'RX';
        },

        ft8CycleTimeLabel() {
            const remaining = Math.max(0, Math.ceil(Number(this.ft8.cycleRemaining || 0)));
            const duration = Math.max(0, Math.round(Number(this.ft8.cycleDuration || 0)));
            return `${remaining}s / ${duration}s`;
        },

        ft8WatchdogLabel() {
            if (!this.ft8.txEnabled || !this.ft8.watchdogLimitSeconds) {
                return 'WD idle';
            }
            const remaining = Math.max(0, Math.ceil(Number(this.ft8.watchdogRemainingSeconds || 0)));
            const minutes = Math.floor(remaining / 60);
            const seconds = String(remaining % 60).padStart(2, '0');
            return `WD ${minutes}:${seconds}`;
        },

        ft8OperatorStatusLabel() {
            const state = String(this.ft8.digitalState || 'idle');
            const pending = this.ft8.pendingTxIntent || {};
            const message = String(
                pending.message ||
                this.ft8.pendingMessage ||
                this.ft8.activeTxMessage ||
                ''
            ).trim();
            const call = String(
                pending.call ||
                this.ft8.selectedCall ||
                this.ft8ActiveTxCall() ||
                ''
            ).toUpperCase();
            const lastDecision = (this.ft8.automationDecisions || [])[this.ft8.automationDecisions.length - 1] || {};
            const reason = String(lastDecision.reason || this.ft8.automationController?.last_decision?.reason || '').replaceAll('-', ' ');

            if (this.ft8.txInhibitReason) {
                return `Stopped: ${this.ft8.txInhibitReason}. Re-arm TX before another automatic transmission.`;
            }
            if (state === 'tx_active' && this.ft8.txInProgress) {
                return `Transmitting ${message || call || 'message'}; waiting for the current TX slot to finish.`;
            }
            if (state === 'tx_active') {
                return `Preparing ${message || call || 'message'} for the next confirmed TX opportunity.`;
            }
            if (state === 'tx_pending') {
                return `Queued ${message || call || 'message'} for the next safe TX opportunity.`;
            }
            if (call && this.ft8.activeAttemptId) {
                return `Working ${call}; waiting for a directed reply.`;
            }
            if (this.ft8.autoCall) {
                return reason ? `Auto Call searching: ${reason}.` : 'Auto Call searching for an eligible CQ.';
            }
            return reason ? `Automation idle: ${reason}.` : 'Automation idle.';
        },

        ft8MessageRowStyle(message) {
            const status = message?.dxcc_status || message?.call_status || '';
            const color = this.ft8StatusColor(message?.dxcc_status ? 'dxcc' : 'call', status);
            if (!status || status === '-') {
                return '';
            }
            return `border-left: 4px solid ${color};`;
        },

        formatFT8CompactTime(timestamp) {
            return this.formatFT8Time(timestamp).replaceAll(':', '');
        },

        formatFT8Frequency(frequency) {
            const value = Number(frequency || 0);
            return value ? value.toFixed(3) : '--.---';
        },

        ft8InferTransmitSlotFromDecode(message) {
            const rawTimestamp = message?.timestamp || message?.time || message?.decoded_at;
            const decodedAt = rawTimestamp ? new Date(rawTimestamp) : null;
            if (!decodedAt || Number.isNaN(decodedAt.getTime())) {
                return false;
            }
            const duration = String(message?.mode || this.ft8.mode || 'FT8').toUpperCase() === 'FT4' ? 7.5 : 15;
            const stationCycle = Math.floor((decodedAt.getTime() / 1000) / duration);
            const stationWasEven = (stationCycle % 2) === 0;
            this.ft8.txEvenFirst = !stationWasEven;
            return true;
        },

        ft8SetRxOffset(offset) {
            this.ft8.rxOffset = Math.max(200, Math.min(3000, Number(offset || 0)));
        },

        ft8SetTxOffset(offset) {
            const range = this.ft8TxOffsetRange();
            this.ft8.txOffset = Math.max(range.low, Math.min(range.high, Number(offset || 0)));
        },

        ft8TxOffsetRange() {
            const normalise = (low, high, fallbackLow, fallbackHigh) => {
                let min = Number.isFinite(Number(low)) ? Number(low) : fallbackLow;
                let max = Number.isFinite(Number(high)) ? Number(high) : fallbackHigh;
                min = Math.max(200, Math.min(5000, min));
                max = Math.max(200, Math.min(5000, max));
                if (min > max) {
                    [min, max] = [max, min];
                }
                return { low: min, high: max };
            };
            if (this.ft8.specialActivity.enabled && this.ft8.specialActivity.role === 'hound') {
                if (this.ft8.specialActivity.submode === 'foxhound') {
                    return normalise(this.ft8.specialActivity.houndTxMin, this.ft8.specialActivity.houndTxMax, 1000, 4000);
                }
                if (this.ft8.specialActivity.submode === 'superfox') {
                    return normalise(this.ft8.specialActivity.superFoxTxMin, this.ft8.specialActivity.superFoxTxMax, 200, 3000);
                }
            }
            return this.ft8.wsjtz.freeFrequency.range === 'narrow'
                ? { low: 500, high: 2000 }
                : { low: 200, high: 3000 };
        },

        ft8NormaliseFrequencyPlan(plan) {
            const incoming = Array.isArray(plan) ? plan : [];
            const byBand = new Map(incoming.map(row => [String(row.band || ''), row]));
            return FT8_DEFAULT_FREQUENCY_PLAN.map(defaultRow => {
                const row = byBand.get(defaultRow.band) || {};
                const normalise = (value) => {
                    const number = Number(value);
                    return Number.isFinite(number) && number > 0 ? number : null;
                };
                return {
                    band: defaultRow.band,
                    ft8: normalise(row.ft8 ?? defaultRow.ft8),
                    ft4: normalise(row.ft4 ?? defaultRow.ft4)
                };
            });
        },

        ft8ApplyFrequencyPlan(plan) {
            this.ft8.availableBands = this.ft8NormaliseFrequencyPlan(plan);
            if (!this.ft8.availableBands.some(row => row.band === this.ft8.selectedBand)) {
                this.ft8.selectedBand = this.ft8.availableBands[0]?.band || '20m';
            }
            if (!this.ft8GetBandFrequency(this.ft8.selectedBand, this.ft8.mode)) {
                const fallback = this.ft8.availableBands.find(row => this.ft8GetBandFrequency(row.band, this.ft8.mode));
                if (fallback) {
                    this.ft8.selectedBand = fallback.band;
                }
            }
            this.ft8SyncFrequencyFromBand();
        },

        ft8ResetFrequencyPlan() {
            this.ft8ApplyFrequencyPlan(cloneFT8FrequencyPlan());
            this.ft8PersistOperatorSettings();
        },

        ft8FrequencyPlanChanged() {
            this.ft8ApplyFrequencyPlan(this.ft8.availableBands);
            this.ft8PersistOperatorSettings();
        },

        // === Message Selection ===

        async ft8SelectMessage(message) {
            this.ft8.selectedMessage = message;
            this.ft8.rxOffset = Number(message.freq || this.ft8.rxOffset || 0);
            this.ft8.selectedCall = this.getFT8MessageCall(message);
            this.ft8.selectedGrid = this.getFT8MessageGrid(message);
            this.ft8.lookupTarget = this.ft8.selectedCall;
            this.ft8InferTransmitSlotFromDecode(message);
            this.ft8GenerateMessages();
            if (this.ft8.selectedCall) {
                this.ft8.selectedTxMessage = 1;
            }
            this.ft8EnrichDecodedMessage(message);
            this.ft8BroadcastDigitalEvent('decoded-selected', this.ft8DigitalPayloadFromMessage(message));
            console.log('Selected message:', message);
        },

        async ft8EngageQso(message) {
            try {
                await this.ft8SelectMessage(message);
                if (!this.ft8.selectedCall) {
                    this.ft8.errorMessage = 'Decoded row does not contain a workable callsign';
                    return;
                }
                if (!this.ft8.engine.transmit) {
                    this.ft8.errorMessage = 'TX engine is not available';
                    return;
                }
                this.ft8.selectedTxMessage = 1;
                this.ft8GenerateMessages();
                const firstMessage = this.ft8.txMessages.find(tx => tx.id === 1)?.text;
                if (!firstMessage) {
                    this.ft8.errorMessage = 'Unable to build first QSO message';
                    return;
                }
                await this.ft8EngageBackendTarget(message, {
                    source: 'manual_double_click',
                    replace_active: true,
                    expectedMessage: firstMessage
                });
                this.ft8.errorMessage = '';
            } catch (error) {
                this.ft8.errorMessage = `Engage failed: ${error.message}`;
            }
        },

        async ft8EngageBackendTarget(message, options = {}) {
            const target = this.ft8DigitalPayloadFromMessage(message);
            const payload = {
                source: options.source || 'manual_double_click',
                target: {
                    ...target,
                    timestamp: message?.timestamp,
                    message: message?.message || target.comment,
                    freq: Number(message?.freq || this.ft8.rxOffset || 0),
                    tx_audio_hz: Number(this.ft8.txOffset || 1500)
                },
                replace_active: options.replace_active !== false
            };
            const response = await fetch('/api/ft8/automation/engage', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.accepted) {
                throw new Error(result.detail || result.error || `HTTP ${response.status}`);
            }
            this.ft8.txEnabled = true;
            this.ft8.autoSequence = true;
            this.ft8.activeTxMessage = result.next_tx_message || options.expectedMessage || '';
            this.ft8AddTxDisplayRow(this.ft8.activeTxMessage, {
                pending: true,
                call: this.ft8.selectedCall,
                dxcc_status: message?.dxcc_status || '',
                call_status: message?.call_status || ''
            });
            if (result.stats) {
                this.updateFT8Status(result.stats);
            }
            if (result.automation) {
                this.ft8.automationController = result.automation;
            }
            this.ft8.radioSyncMessage = result.will_tx_now
                ? `TX started: ${this.ft8.activeTxMessage}`
                : `Queued next TX slot: ${this.ft8.activeTxMessage}`;
        },

        ft8DirectedPartsForSelected(message) {
            const selectedCall = String(this.ft8.selectedCall || this.ft8ActiveTxCall() || '').toUpperCase();
            const mycall = String(this.ft8.mycall || this.ft8.config.mycall || '').toUpperCase();
            if (!selectedCall || !mycall || message?.direction === 'tx' || message?.source === 'tx' || message?.direction === 'tx_pending' || message?.source === 'tx_pending') {
                return [];
            }
            const text = String(message?.message || '').toUpperCase();
            const clauses = text.split(';').map(clause =>
                clause.split(/\s+/).map(token => token.trim().replace(/[<>;,]/g, '').toUpperCase()).filter(Boolean)
            );
            return clauses.find(parts =>
                parts.length >= 2 &&
                parts.slice(0, 2).includes(mycall) &&
                parts.slice(0, 2).includes(selectedCall)
            ) || [];
        },

        async ft8QueueSelectedTxMessage(id, options = {}) {
            this.ft8.selectedTxMessage = id;
            this.ft8GenerateMessages();
            const selected = this.ft8.txMessages.find(tx => tx.id === id);
            if (!selected?.text) {
                return false;
            }
            if (Number(id) !== 6 && !this.ft8HasActiveQsoAttempt()) {
                const selectedMessage = this.ft8.selectedMessage || this.ft8FindSelectedDecodedMessage();
                if (!selectedMessage) {
                    throw new Error('Select or double-click a decoded station before TX');
                }
                await this.ft8EngageBackendTarget(selectedMessage, {
                    source: options.source || 'manual_tx_button',
                    replace_active: true,
                    expectedMessage: selected.text
                });
            }
            const response = await fetch('/api/ft8/tx/manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tx_id: Number(id),
                    immediate: Boolean(options.immediate)
                })
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
            }
            if (payload.stats) {
                this.updateFT8Status(payload.stats);
            }
            this.ft8AddTxDisplayRow(payload.message || selected.text, { pending: true });
            this.ft8.radioSyncMessage = `Manual TX queued by backend: ${payload.message || selected.text}`;
            return true;
        },

        ft8FindSelectedDecodedMessage() {
            const selectedCall = String(this.ft8.selectedCall || '').trim().toUpperCase();
            if (!selectedCall) {
                return null;
            }
            return (this.ft8.decodedMessages || []).find(message => {
                if (message?.direction === 'tx' || message?.source === 'tx' || message?.source === 'tx_pending') {
                    return false;
                }
                const call = String(this.getFT8MessageCall(message) || message?.callsign || message?.call || '').toUpperCase();
                return call === selectedCall;
            }) || null;
        },

        async ft8AutoCallChanged() {
            if (!this.ft8.autoCall) {
                this.ft8.automation.enabled = false;
                await this.ft8SyncBackendAutomationSettings();
                await this.ft8HaltTx();
                this.ft8ClearQsoTarget({ haltTx: false, keepStatus: true });
                this.ft8.radioSyncMessage = 'Auto Call stopped';
                return;
            }
            this.ft8.automation.enabled = true;
            this.ft8.automation.autoCallRemaining = Math.max(
                Number(this.ft8.automation.autoCallRemaining || 0),
                Number(this.ft8.automation.autoCallCount || 0)
            );
            await this.ft8SyncBackendAutomationSettings();
            await this.ft8ArmAutomationTx();
            await this.ft8RunAutoCallSweep();
        },

        async ft8RunAutoCallSweep() {
            if (!this.ft8.autoCall || !this.ft8.engine.transmit) {
                return false;
            }
            if (this.ft8HasActiveQsoAttempt()) {
                return false;
            }
            const candidates = this.ft8SortAutomationMessages(this.ft8VisibleBandActivity().filter(message => {
                if (message?.direction === 'tx' || message?.source === 'tx') {
                    return false;
                }
                const meta = this.ft8AnalyzeMessage(message);
                const spotTargetHeard = this.ft8IsActiveSpotTarget(meta.call, meta.band, meta.mode);
                return Boolean(meta.call && this.ft8ShouldAutoRespond(message, meta, spotTargetHeard));
            }));
            let submitted = false;
            for (const message of candidates) {
                submitted = await this.ft8MaybeAutoCall(message) || submitted;
            }
            await this.ft8PollStatus();
            return submitted;
        },

        ft8DigitalPayloadFromMessage(message) {
            const call = this.getFT8MessageCall(message) || message?.callsign || message?.call || '';
            const grid = this.getFT8MessageGrid(message) || message?.grid || message?.gridsquare || '';
            return {
                callsign: String(call || '').toUpperCase(),
                gridsquare: String(grid || '').toUpperCase(),
                frequency_mhz: Number(message?.base_frequency || this.ft8.currentFrequency || 0),
                band: message?.band || this.ft8.selectedBand,
                mode: String(message?.mode || this.ft8.mode || 'FT8').toUpperCase(),
                comment: message?.message || '',
                snr: message?.snr,
                dt: message?.dt,
                audio_offset: message?.freq || this.ft8.rxOffset,
                call_status: message?.call_status || '',
                dxcc_status: message?.dxcc_status || '',
                country: message?.country || message?.dxcc_name || ''
            };
        },

        ft8QsoPayload(qso) {
            const rawFrequency = Number(qso?.frequency_mhz ?? qso?.frequency ?? 0);
            const frequencyMhz = rawFrequency > 1 && rawFrequency < 100
                ? rawFrequency
                : Number(this.ft8.currentFrequency || 0);
            return {
                callsign: String(qso?.their_call || qso?.callsign || qso?.call || this.ft8.selectedCall || '').toUpperCase(),
                gridsquare: String(qso?.grid || qso?.gridsquare || this.ft8.selectedGrid || '').toUpperCase(),
                frequency_mhz: frequencyMhz,
                band: qso?.band || this.ft8.selectedBand,
                mode: String(qso?.mode || this.ft8.mode || 'FT8').toUpperCase(),
                rst_sent: qso?.rst_sent || qso?.report_sent || qso?.my_report || '+00',
                rst_received: qso?.rst_received || qso?.rst_rcvd || qso?.report_received || qso?.their_report || '+00',
                comment: qso?.comment || 'Completed in built-in digital window'
            };
        },

        async ft8EnrichDecodedMessage(message) {
            const call = this.getFT8MessageCall(message) || message?.callsign || message?.call;
            if (!call) {
                message.call_status = message.call_status || '-';
                message.dxcc_status = message.dxcc_status || '-';
                return;
            }
            const callsign = String(call).toUpperCase();
            const band = message?.band || this.ft8.selectedBand;
            const mode = String(message?.mode || this.ft8.mode || 'FT8').toUpperCase();
            const frequencyKhz = Number(message?.base_frequency || this.ft8.currentFrequency || 0) * 1000;
            const cacheKey = `${callsign}|${band || ''}|${mode}|${Math.round(frequencyKhz || 0)}`;
            const cached = this.ft8.statusCache[cacheKey];
            if (cached && Date.now() - cached.timestamp < 5 * 60 * 1000) {
                this.ft8ApplyDecodedStatus(message, cached.payload);
                await this.ft8MaybeAutoCall(message);
                return;
            }
            if (message._statusLoading) {
                return;
            }
            message.callsign = callsign;
            message._statusLoading = true;
            message._statusPending = true;
            if (!this.ft8.statusInflight[cacheKey]) {
                const params = new URLSearchParams();
                if (band) params.set('band', band);
                if (mode) params.set('mode', mode);
                if (frequencyKhz) params.set('frequency_khz', String(frequencyKhz));
                if (message?.message) params.set('comment', message.message);
                this.ft8.statusInflight[cacheKey] = fetch(`/api/spots/explain/${encodeURIComponent(callsign)}?${params.toString()}`, {
                    cache: 'no-store'
                })
                    .then(response => response.ok ? response.json() : null)
                    .finally(() => {
                        delete this.ft8.statusInflight[cacheKey];
                    });
            }
            try {
                const payload = await this.ft8.statusInflight[cacheKey];
                if (!payload?.ok) {
                    await this.ft8SubmitAutomationTarget(message);
                    if (!this.ft8HasResolvedStatus(message.call_status)) {
                        message.call_status = 'Unknown';
                    }
                    if (!this.ft8HasResolvedStatus(message.dxcc_status)) {
                        message.dxcc_status = 'Unknown';
                    }
                    message._statusPending = false;
                    return;
                }
                this.ft8.statusCache[cacheKey] = { payload, timestamp: Date.now() };
                this.ft8ApplyDecodedStatus(message, payload);
                await this.ft8MaybeAutoCall(message);
            } catch (error) {
                console.warn('Unable to enrich decoded digital message:', error);
                await this.ft8SubmitAutomationTarget(message);
                if (!this.ft8HasResolvedStatus(message.call_status)) {
                    message.call_status = 'Unknown';
                }
                if (!this.ft8HasResolvedStatus(message.dxcc_status)) {
                    message.dxcc_status = 'Unknown';
                }
                message._statusPending = false;
            } finally {
                message._statusLoading = false;
            }
        },

        ft8ApplyDecodedStatus(message, payload) {
            message.callsign = payload.callsign || message.callsign || this.getFT8MessageCall(message);
            message.call_status = payload.call?.status || message.call_status || 'Unknown';
            message.dxcc_status = payload.dxcc?.status || message.dxcc_status || 'Unknown';
            message.dxcc_tag = payload.dxcc?.tag || message.dxcc_tag || '';
            message.dxcc = payload.dxcc?.adif ?? message.dxcc;
            message.country = payload.cty?.entity || payload.cty?.country || message.country || '';
            message.cq_zone = payload.cty?.cq || payload.cty?.cq_zone || message.cq_zone || '';
            message.itu_zone = payload.cty?.itu || payload.cty?.itu_zone || message.itu_zone || '';
            message.continent = payload.cty?.continent || payload.cty?.cont || message.continent || '';
            message._statusPending = false;
            const callStatus = this.ft8NormalizeStatusKey(message.call_status);
            const dxccStatus = this.ft8NormalizeStatusKey(message.dxcc_status);
            message.needed = {
                call: callStatus === 'New Call',
                dxcc: dxccStatus === 'ATNO',
                continent: false,
                grid: callStatus.toLowerCase().includes('grid') || dxccStatus.toLowerCase().includes('grid'),
                cqZone: false,
                ituZone: false
            };
            message.needed_on_band = {
                call: callStatus.includes('New Band'),
                dxcc: dxccStatus.includes('New Band'),
                continent: false,
                grid: callStatus.toLowerCase().includes('grid') || dxccStatus.toLowerCase().includes('grid'),
                cqZone: false,
                ituZone: false
            };
            this.ft8SubmitAutomationTarget(message).catch(error => {
                console.warn('Unable to submit digital automation target:', error);
            });
        },

        async ft8SubmitAutomationTarget(message) {
            if (!message) {
                return null;
            }
            const payload = {
                target: {
                    ...message,
                    callsign: message.callsign || this.getFT8MessageCall(message),
                    band: message.band || this.ft8.selectedBand,
                    mode: String(message.mode || this.ft8.mode || 'FT8').toUpperCase(),
                    heard: message.source !== 'spot' && !message.is_spot,
                    base_frequency: message.base_frequency || this.ft8.currentFrequency
                }
            };
            try {
                const response = await fetch('/api/ft8/automation/target', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    return null;
                }
                const result = await response.json().catch(() => ({}));
                if (result.target) {
                    message.call_status = result.target.call_status || message.call_status || 'Unknown';
                    message.dxcc_status = result.target.dxcc_status || message.dxcc_status || 'Unknown';
                    message.country = result.target.country || message.country || '';
                    message.grid = result.target.grid || message.grid || '';
                }
                if (result.automation) {
                    this.ft8.automationController = result.automation;
                }
                return result;
            } catch (error) {
                console.warn('Unable to update backend digital automation target:', error);
                return null;
            }
        },

        ft8StatusIsWorked(status) {
            const normalized = this.ft8NormalizeStatusKey(status).toLowerCase();
            return normalized === 'worked' || normalized === 'confirmed';
        },

        ft8StatusHasPriorCallWork(status) {
            const normalized = this.ft8NormalizeStatusKey(status).toLowerCase();
            return ['worked', 'confirmed'].includes(normalized);
        },

        ft8HasResolvedStatus(status) {
            const value = String(status || '').trim();
            if (!value || value === '-') {
                return false;
            }
            return !['unknown', 'checking...', 'loading'].includes(value.toLowerCase());
        },

        async ft8MaybeAutoCall(message) {
            if (!this.ft8.autoCall || !this.ft8.connected || !this.ft8.engine.transmit) {
                return false;
            }
            if (Number(this.ft8.automation.autoCallRemaining || 0) <= 0) {
                return false;
            }
            if (message?.source === 'spot' || message?.is_spot) {
                return false;
            }
            const meta = this.ft8AnalyzeMessage(message);
            if (this.ft8HasActiveQsoAttempt(meta.call)) {
                return false;
            }
            if (!this.ft8AutomationModeAllowed(meta.mode)) {
                return false;
            }
            const spotTargetHeard = this.ft8.automation.spotHuntEnabled &&
                this.ft8IsActiveSpotTarget(meta.call, meta.band, meta.mode);
            if (!meta.call || meta.call === String(this.ft8.mycall || '').toUpperCase()) {
                return false;
            }
            const directedCaller = this.ft8MessageIsCallingUs(message);
            if (!this.ft8ShouldAutoRespond(message, meta, spotTargetHeard)) {
                return false;
            }
            if (!this.ft8SpecialActivityAllowsAutoCall(message, meta, spotTargetHeard)) {
                return false;
            }
            if (!this.ft8PassesAutomationFilters(message, directedCaller)) {
                return false;
            }
            if (this.ft8.automation.avoidLogged && this.ft8StatusHasPriorCallWork(message.call_status)) {
                return false;
            }
            const key = `${meta.call}|${meta.band || ''}|${meta.mode || ''}`;
            if (this.ft8IsAutoCallBackedOff(key)) {
                return false;
            }

            const result = await this.ft8SubmitAutomationTarget(message);
            if (!result || result.status !== 'queued') {
                return false;
            }
            this.ft8RecordAutoCallAttempt(key);
            this.ft8AutoIgnoreCall(meta.call, 'auto-call');
            this.ft8.radioSyncMessage = `Auto Call candidate registered: ${meta.call}`;
            return true;
        },

        ft8HasActiveQsoAttempt(candidateCall = '') {
            const activeCall = String(this.ft8.selectedCall || this.ft8ActiveTxCall() || '').toUpperCase().trim();
            if (activeCall) {
                return true;
            }
            if (this.ft8.activeTxMessage) {
                return true;
            }
            return Boolean((this.ft8.txQueue || []).length);
        },

        ft8CallStatusStyle(status) {
            const color = this.ft8StatusColor('call', status);
            return `font-weight: 700; color: ${color};`;
        },

        ft8DxccStatusStyle(status) {
            const color = this.ft8StatusColor('dxcc', status);
            return `font-weight: 700; color: ${color};`;
        },

        ft8StatusCellLabel(message, field) {
            const value = String(message?.[field] || '').trim();
            if (value) {
                return value;
            }
            return (message?._statusLoading || message?._statusPending) ? '...' : '-';
        },

        ft8StatusCellTitle(message, field) {
            const value = String(message?.[field] || '').trim();
            if (value) {
                return value;
            }
            return (message?._statusLoading || message?._statusPending) ? 'Checking Wavelog status' : '';
        },

        ft8StatusCellStyle(message, field, group) {
            const value = String(message?.[field] || '').trim();
            if (!value && (message?._statusLoading || message?._statusPending)) {
                return 'font-weight: 700; color: #9ca3af;';
            }
            return group === 'dxcc'
                ? this.ft8DxccStatusStyle(value)
                : this.ft8CallStatusStyle(value);
        },

        ft8StatusColor(group, status) {
            const colors = this.ft8.statusColors?.[group] || {};
            const normalized = this.ft8NormalizeStatusKey(status);
            const color = colors[normalized] || colors[status] || colors.Default || '#FFFFFF';
            return this.ft8CssColor(color);
        },

        ft8NormalizeStatusKey(status) {
            const value = String(status || '').trim();
            if (!value) {
                return 'Default';
            }
            const lower = value.toLowerCase();
            const statusMap = {
                'new band': 'New Band',
                'new mode': 'New Mode',
                'new band+mode': 'New Band+Mode',
                'new band/mode': 'New Band+Mode',
                'worked': 'Worked',
                'confirmed': 'Confirmed',
                'atno': 'ATNO',
                'unknown': 'Unknown'
            };
            if (statusMap[lower]) {
                return statusMap[lower];
            }
            if (lower.startsWith('c/') || lower.startsWith('w/')) {
                const prefix = value.slice(0, 2).toUpperCase();
                const suffix = value.slice(2).toLowerCase();
                if (suffix.includes('new band') && suffix.includes('new mode')) return `${prefix}New Band+Mode`;
                if (suffix.includes('new band')) return `${prefix}New Band`;
                if (suffix.includes('new mode')) return `${prefix}New Mode`;
            }
            return value;
        },

        ft8CssColor(color) {
            const value = String(color || '').trim();
            if (/^#[0-9a-fA-F]{8}$/.test(value)) {
                return `#${value.slice(3)}`;
            }
            if (/^#[0-9a-fA-F]{6}$/.test(value)) {
                return value;
            }
            return '#FFFFFF';
        },

        ft8ColorInputValue(group, key) {
            return this.ft8CssColor(this.ft8.statusColors?.[group]?.[key]);
        },

        ft8SetStatusColor(group, key, color) {
            if (!this.ft8.statusColors[group]) {
                this.ft8.statusColors[group] = {};
            }
            this.ft8.statusColors[group][key] = this.ft8CssColor(color);
            this.ft8PersistOperatorSettings();
        },

        ft8ResetStatusColors() {
            this.ft8.statusColors = cloneFT8StatusColors();
            this.ft8PersistOperatorSettings();
        },

        ft8ApplySharedStatusColors(colors) {
            if (!colors || typeof colors !== 'object') {
                return;
            }
            const mapped = cloneFT8StatusColors();
            const read = (key) => colors[key] ? this.ft8CssColor(colors[key]) : null;

            const shared = {
                'New Call': read('New Call'),
                'New Band': read('New band') || read('New Band'),
                'New Mode': read('New mode') || read('New Mode'),
                'New Band+Mode': read('New band+mode') || read('New Band+Mode'),
                'Worked': read('Worked'),
                'Confirmed': read('Confirmed'),
                'Unknown': read('Unknown'),
                'Default': read('Default')
            };
            for (const [key, value] of Object.entries(shared)) {
                if (value) mapped.call[key] = value;
            }

            for (const key of Object.keys(mapped.dxcc)) {
                const value = read(key);
                if (value) {
                    mapped.dxcc[key] = value;
                }
            }
            for (const key of ['ATNO', 'Worked', 'Confirmed', 'Unknown', 'Default']) {
                const value = read(key);
                if (value) {
                    mapped.dxcc[key] = value;
                }
            }
            this.ft8.statusColors = mapped;
        },

        async ft8LoadConfiguredStatusColors() {
            if (this.configData?.COLORS) {
                this.ft8ApplySharedStatusColors(this.configData.COLORS);
                return;
            }
            try {
                const response = await fetch('/api/config', { cache: 'no-store' });
                if (!response.ok) {
                    return;
                }
                const payload = await response.json();
                if (payload?.success && payload.config?.COLORS) {
                    this.ft8ApplySharedStatusColors(payload.config.COLORS);
                }
            } catch (error) {
                console.warn('Unable to load shared status colours:', error);
            } finally {
                this.ft8ApplyOperatorSettings(this.ft8.config.operatorSettings || {});
                this.ft8LoadStoredOperatorSettings();
            }
        },

        async ft8ClearDecoded() {
            this.ft8.decodedMessages = [];
            if (ft8Engine) {
                ft8Engine.clearDecodedMessages();
            }
            try {
                await fetch('/api/ft8/decoded/clear', { method: 'POST' });
            } catch (error) {
                console.warn('Unable to clear backend decoded messages:', error);
            }
        },

        // === Waterfall Display ===

        initFT8Waterfall() {
            const canvas = this.$refs.ft8Waterfall;
            if (!canvas) {
                console.warn('FT8 waterfall canvas not found');
                return;
            }

            const rect = canvas.getBoundingClientRect();
            canvas.width = Math.max(600, Math.floor(rect.width || 1200));
            canvas.height = 86;

            this.ft8.waterfallCtx = canvas.getContext('2d');

            // Clear canvas
            const ctx = this.ft8.waterfallCtx;
            ctx.fillStyle = '#000';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            console.log('✅ FT8 waterfall initialized:', canvas.width, 'x', canvas.height);
        },

        drawWaterfall() {
            if (!this.ft8.display.waterfall) {
                return;
            }
            const canvas = this.$refs.ft8Waterfall;
            if (!canvas || !this.ft8.waterfallCtx || !this.ft8.waterfallData.length) {
                return;
            }

            const ctx = this.ft8.waterfallCtx;
            const data = this.ft8VisibleWaterfallRows(this.ft8.waterfallData);

            const width = canvas.width;
            const height = canvas.height;

            ctx.fillStyle = '#000';
            ctx.fillRect(0, 0, width, height);

            const imageData = ctx.createImageData(width, height);
            const pixels = imageData.data;

            for (let y = 0; y < height; y++) {
                const rowData = data[data.length - 1 - y];
                if (!rowData || !rowData.length) {
                    continue;
                }

                for (let x = 0; x < width; x++) {
                    const sourceIndex = Math.min(rowData.length - 1, Math.floor((x / width) * rowData.length));
                    const intensity = this.ft8ClampWaterfallIntensity(rowData[sourceIndex]);
                    const color = this.getWaterfallRgb(intensity);
                    const offset = (y * width + x) * 4;
                    pixels[offset] = color[0];
                    pixels[offset + 1] = color[1];
                    pixels[offset + 2] = color[2];
                    pixels[offset + 3] = 255;
                }
            }

            ctx.putImageData(imageData, 0, 0);
            this.ft8.waterfallData = data;
        },

        ft8VisibleWaterfallRows(rows) {
            const canvas = this.$refs.ft8Waterfall;
            const maxRows = Math.max(1, Math.floor((canvas && canvas.height) || 86));
            return rows
                .filter(row => Array.isArray(row) && row.length > 0)
                .slice(-maxRows);
        },

        ft8ClampWaterfallIntensity(value) {
            const number = Number(value);
            if (!Number.isFinite(number)) {
                return 0;
            }
            return Math.max(0, Math.min(255, Math.round(number)));
        },

        getWaterfallRgb(intensity) {
            const normalized = intensity / 255;

            if (normalized < 0.25) {
                const t = normalized / 0.25;
                return [0, Math.floor(t * 255), 255];
            }
            if (normalized < 0.5) {
                const t = (normalized - 0.25) / 0.25;
                return [0, 255, Math.floor((1 - t) * 255)];
            }
            if (normalized < 0.75) {
                const t = (normalized - 0.5) / 0.25;
                return [Math.floor(t * 255), 255, 0];
            }

            const t = (normalized - 0.75) / 0.25;
            return [255, Math.floor((1 - t) * 255), 0];
        },

        getWaterfallColor(intensity) {
            // Convert intensity (0-255) to color (blue -> green -> yellow -> red)
            const normalized = intensity / 255;

            if (normalized < 0.25) {
                // Blue -> Cyan
                const t = normalized / 0.25;
                return `rgb(0, ${Math.floor(t * 255)}, 255)`;
            } else if (normalized < 0.5) {
                // Cyan -> Green
                const t = (normalized - 0.25) / 0.25;
                return `rgb(0, 255, ${Math.floor((1 - t) * 255)})`;
            } else if (normalized < 0.75) {
                // Green -> Yellow
                const t = (normalized - 0.5) / 0.25;
                return `rgb(${Math.floor(t * 255)}, 255, 0)`;
            } else {
                // Yellow -> Red
                const t = (normalized - 0.75) / 0.25;
                return `rgb(255, ${Math.floor((1 - t) * 255)}, 0)`;
            }
        },

        // === Utility Methods ===

        formatFT8Time(timestamp) {
            const date = new Date(timestamp);
            const hours = String(date.getUTCHours()).padStart(2, '0');
            const minutes = String(date.getUTCMinutes()).padStart(2, '0');
            const seconds = String(date.getUTCSeconds()).padStart(2, '0');
            return `${hours}:${minutes}:${seconds}`;
        },

        getFT8SNRClass(snr) {
            if (snr >= 0) return 'snr-good';
            if (snr >= -10) return 'snr-fair';
            return 'snr-weak';
        },

        ft8OperatorSettingsPayload() {
            return {
                cqOnly: this.ft8.cqOnly,
                filtering: this.ft8.filtering,
                filterPrefixes: this.ft8.filterPrefixes,
                prefixFilterMode: this.ft8.prefixFilterMode,
                stateFilterMode: this.ft8.stateFilterMode,
                stateFilter: this.ft8.stateFilter,
                ignoredStations: this.ft8.ignoredStations,
                autoIgnore: this.ft8.autoIgnore,
                customAlerts: this.ft8.customAlerts,
                filters: this.ft8.filters,
                alerts: this.ft8.alerts,
                specialActivity: this.ft8.specialActivity,
                automation: this.ft8.automation,
                wsjtz: this.ft8.wsjtz,
                display: this.ft8.display,
                frequencyPlan: this.ft8.availableBands,
                statusColors: this.ft8.statusColors
            };
        },

        ft8ApplyOperatorSettings(settings) {
            if (!settings || typeof settings !== 'object') {
                return;
            }
            for (const key of ['cqOnly', 'filtering', 'filterPrefixes', 'prefixFilterMode', 'stateFilterMode', 'stateFilter', 'ignoredStations', 'autoIgnore', 'customAlerts']) {
                if (settings[key] !== undefined) {
                    this.ft8[key] = settings[key];
                }
            }
            if (settings.filters) {
                this.ft8.filters = this.ft8DeepMerge(this.ft8.filters, settings.filters);
            }
            if (settings.alerts) {
                this.ft8.alerts = this.ft8DeepMerge(this.ft8.alerts, settings.alerts);
            }
            if (settings.specialActivity || settings.special_activity) {
                this.ft8ApplySpecialActivity(settings.specialActivity || settings.special_activity);
            }
            if (settings.automation) {
                this.ft8.automation = this.ft8DeepMerge(this.ft8.automation, settings.automation);
            }
            if (settings.wsjtz) {
                this.ft8.wsjtz = this.ft8DeepMerge(this.ft8.wsjtz, settings.wsjtz);
            }
            if (settings.display) {
                this.ft8.display = this.ft8DeepMerge(this.ft8.display, settings.display);
                this.ft8.config.waterfallEnabled = Boolean(this.ft8.display.waterfall);
            }
            if (settings.frequencyPlan || settings.availableBands) {
                this.ft8ApplyFrequencyPlan(settings.frequencyPlan || settings.availableBands);
            }
            if (settings.statusColors) {
                this.ft8.statusColors = this.ft8DeepMerge(this.ft8.statusColors, settings.statusColors);
            }
        },

        ft8DeepMerge(base, updates) {
            const output = Array.isArray(base) ? [...base] : { ...base };
            for (const [key, value] of Object.entries(updates || {})) {
                if (value && typeof value === 'object' && !Array.isArray(value) && output[key] && typeof output[key] === 'object') {
                    output[key] = this.ft8DeepMerge(output[key], value);
                } else {
                    output[key] = value;
                }
            }
            return output;
        },

        ft8LoadStoredOperatorSettings() {
            try {
                const raw = localStorage.getItem('om0rx.ft8.operatorSettings');
                if (raw) {
                    this.ft8ApplyOperatorSettings(JSON.parse(raw));
                }
            } catch (error) {
                console.warn('Unable to load FT8 operator settings:', error);
            }
        },

        ft8PersistOperatorSettings() {
            const payload = this.ft8OperatorSettingsPayload();
            this.ft8.config.operatorSettings = payload;
            this.ft8.config.waterfallEnabled = Boolean(this.ft8.display.waterfall);
            try {
                localStorage.setItem('om0rx.ft8.operatorSettings', JSON.stringify(payload));
            } catch (error) {
                console.warn('Unable to persist FT8 operator settings locally:', error);
            }
        },

        async ft8WaterfallSettingChanged() {
            this.ft8.config.waterfallEnabled = Boolean(this.ft8.display.waterfall);
            if (!this.ft8.display.waterfall) {
                this.ft8.waterfallData = [];
                const canvas = this.$refs.ft8Waterfall;
                const ctx = this.ft8.waterfallCtx;
                if (canvas && ctx) {
                    ctx.fillStyle = '#000';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                }
            } else {
                this.$nextTick(() => this.initFT8Waterfall());
            }
            this.ft8PersistOperatorSettings();
            if (this.ft8.connected) {
                try {
                    await this.ft8SyncServiceConfig();
                } catch (error) {
                    this.ft8.errorMessage = `Waterfall setting failed: ${error.message}`;
                }
            }
        },

        // === Configuration Management ===

        async ft8LoadSettings() {
            this.ft8.isLoading = true;
            this.ft8.loadingMessage = 'Loading configuration...';
            this.ft8.errorMessage = '';

            try {
                console.log('Loading FT8 configuration...');

                // Load configuration from server
                const configResponse = await fetch('/api/ft8/config');
                if (!configResponse.ok) {
                    const errorData = await configResponse.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${configResponse.status}: ${configResponse.statusText}`);
                }

                const configData = await configResponse.json();

                // Validate loaded config
                if (configData.mycall) {
                    const callValidation = validateCallsign(configData.mycall);
                    if (!callValidation.valid) {
                        console.warn('Invalid callsign in config:', callValidation.error);
                    }
                }

                if (configData.mygrid) {
                    const gridValidation = validateGridSquare(configData.mygrid);
                    if (!gridValidation.valid) {
                        console.warn('Invalid grid square in config:', gridValidation.error);
                    }
                }

                // Update config from server (direct assignment)
                Object.assign(this.ft8.config, configData);
                if (typeof configData.waterfallEnabled === 'boolean') {
                    this.ft8.display.waterfall = configData.waterfallEnabled;
                }
                this.ft8ApplyOperatorSettings(configData.operatorSettings);
                if (!this.ft8.engine.transmit) {
                    this.ft8.config.autoSequence = false;
                    this.ft8.config.txEnabled = false;
                }

                // Also update operate tab fields
                this.ft8.mode = configData.mode || 'FT8';
                this.ft8.mycall = configData.mycall || 'OM0RX';
                this.ft8.mygrid = configData.mygrid || 'JN88';
                this.ft8.autoSequence = this.ft8.engine.transmit ? (configData.auto_sequence || false) : false;
                this.ft8.txEnabled = this.ft8.engine.transmit ? (configData.tx_enabled || false) : false;
                await this.ft8PollRadioStatus();

                console.log('✅ FT8 configuration loaded successfully:', configData);
                this.ft8.errorMessage = '';

                // Load audio devices
                await this.ft8GetAudioDevices();

            } catch (error) {
                console.error('❌ Error loading FT8 configuration:', error);
                this.ft8.errorMessage = `Failed to load configuration: ${error.message}`;
                // Don't show alert for initial load - just log
                console.warn(this.ft8.errorMessage);

            } finally {
                this.ft8.isLoading = false;
                this.ft8.loadingMessage = '';
            }
        },

        async ft8SaveSettings() {
            this.ft8.isLoading = true;
            this.ft8.loadingMessage = 'Saving configuration...';
            this.ft8.errorMessage = '';

            try {
                // Validate before saving
                const callValidation = validateCallsign(this.ft8.config.mycall);
                if (!callValidation.valid) {
                    throw new Error(`Callsign validation: ${callValidation.error}`);
                }

                const gridValidation = validateGridSquare(this.ft8.config.mygrid);
                if (!gridValidation.valid) {
                    throw new Error(`Grid square validation: ${gridValidation.error}`);
                }

                const serverValidation = validateNetworkServer(this.ft8.config.networkServer);
                if (!serverValidation.valid) {
                    throw new Error(`Network server validation: ${serverValidation.error}`);
                }

                console.log('Saving FT8 configuration...');
                const configToSave = {
                    ...this.ft8.config,
                    operatorSettings: this.ft8OperatorSettingsPayload(),
                    waterfallEnabled: Boolean(this.ft8.display.waterfall),
                    autoSequence: this.ft8.engine.transmit ? this.ft8.config.autoSequence : false,
                    txEnabled: this.ft8.engine.transmit ? this.ft8.config.txEnabled : false,
                    auto_sequence: this.ft8.engine.transmit ? this.ft8.config.autoSequence : false,
                    tx_enabled: this.ft8.engine.transmit ? this.ft8.config.txEnabled : false
                };

                const response = await fetch('/api/ft8/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(configToSave)
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }

                console.log('✅ FT8 configuration saved successfully');
                this.ft8PersistOperatorSettings();
                this.ft8.configSaved = true;
                this.ft8.errorMessage = '';

                // Hide success message after 3 seconds
                setTimeout(() => {
                    this.ft8.configSaved = false;
                }, 3000);

                // Update operate tab from config
                this.ft8.mode = this.ft8.config.mode;
                this.ft8.mycall = this.ft8.config.mycall;
                this.ft8.mygrid = this.ft8.config.mygrid;

            } catch (error) {
                console.error('❌ Error saving FT8 configuration:', error);
                this.ft8.errorMessage = `Failed to save configuration: ${error.message}`;
                alert(this.ft8.errorMessage);

            } finally {
                this.ft8.isLoading = false;
                this.ft8.loadingMessage = '';
            }
        },

        async ft8GetAudioDevices() {
            try {
                const response = await fetch('/api/ft8/audio-devices');

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();
                this.ft8.audioDevices.input = data.input || [];
                this.ft8.audioDevices.output = data.output || [];
                console.log('✅ Audio devices loaded:', data);

            } catch (error) {
                console.error('❌ Error getting audio devices:', error);
                // Don't show error for audio devices - just use defaults
                this.ft8.audioDevices.input = [];
                this.ft8.audioDevices.output = [];
            }
        }
    }
};

// Export for use in main app
if (typeof window !== 'undefined') {
    window.ft8ModalMixin = ft8ModalMixin;
}
