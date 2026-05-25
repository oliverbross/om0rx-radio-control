// WebSocket Communication Module
// FlexRadio Web Control v2.0 - WebSocket & Communication

// Safe logging wrapper (Logger loaded by logger.js, falls back to console if not available)
// Use var instead of const to allow redeclaration in other script files
var log = window.Logger?.log || ((level, topic, ...args) => console[level]?.(`[${topic}]`, ...args));
var batch = window.Logger?.batch || (() => {});
var ChangeDetector = window.Logger?.ChangeDetector || class {};
var debugEnabled = window.Logger?.debugEnabled ?? false;

if (debugEnabled) log('info', 'init', 'Loading websocket.js module');

// Status change detector for avoiding repetitive logs
const statusChangeDetector = new ChangeDetector();
let spotBatchCount = 0;

const websocketMethods = {
    // === WebSocket Connection ===
    
    connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/radio`;
        
        log('info', 'ws', 'Connecting to:', wsUrl);
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                log('info', 'ws', 'Connected');
                this.connected = true;
                this.showStatus('Connected to radio', 'success');
            };
            
            this.ws.onmessage = (event) => {
                const message = JSON.parse(event.data);
                log('debug', 'ws', 'Received:', message.type);
                
                if (message.type === 'status') {
                    this.updateRadioStatus(message.data);
                } else if (message.type === 'spots') {
                    // Accumulate spots instead of replacing
                    const newSpots = message.data;
                    spotBatchCount += newSpots.length;
                    
                    // Log spot reception in batches (once per second)
                    batch('spots', 'info', 'received', 
                      (items) => `Received ${items.reduce((sum, item) => sum + (typeof item === 'number' ? item : 1), 0)} spots`,
                      1000,
                      newSpots.length
                    );
                    
                    newSpots.forEach(newSpot => {
                        // Check if spot already exists (by callsign and frequency_mhz)
                        const freqMhz = newSpot.frequency_mhz || parseFloat(newSpot.frequency) / 1000;
                        const exists = this.dxSpots.some(s => {
                            const existingFreqMhz = s.frequency_mhz || parseFloat(s.frequency) / 1000;
                            return s.callsign === newSpot.callsign && 
                                   Math.abs(existingFreqMhz - freqMhz) < 0.001;
                        });
                        if (!exists) {
                            // If filtered search is active, queue the spot instead of showing immediately
                            if (this.hasActiveFilters() && this.isSearchingSpots) {
                                this.queuedRealtimeSpots.unshift(newSpot);
                                log('debug', 'spots', `Queued (filtered): ${newSpot.callsign} ${newSpot.frequency} kHz`);
                            } else {
                                this.dxSpots.unshift(newSpot);
                                
                                // If filters are active and search is complete, also add matching spot to filtered results
                                // This ensures new real-time spots appear even when filters are active with search results
                                if (this.hasActiveFilters() && this.filteredSearchResults.length > 0 && !this.isSearchingSpots) {
                                    if (this.matchesCurrentFilters(newSpot)) {
                                        this.filteredSearchResults.unshift(newSpot);
                                        log('debug', 'spots', `Added to filtered results: ${newSpot.callsign} ${newSpot.frequency} kHz`);
                                    }
                                }
                                
                                log('debug', 'spots', `Added: ${newSpot.callsign} ${newSpot.frequency} kHz`);
                            }
                        }
                    });
                    
                    // Trim to maxSpots (but keep accumulating)
                    if (this.dxSpots.length > this.maxSpots) {
                        this.dxSpots = this.dxSpots.slice(0, this.maxSpots);
                    }
                    
                    // Sync to popup window if open
                    if (this.spotsDetached) {
                        this.syncSpotsToWindow();
                    }
                }
            };
            
            this.ws.onerror = (error) => {
                log('error', 'ws', 'WebSocket error:', error);
                this.connected = false;
            };
            
            this.ws.onclose = () => {
                log('warn', 'ws', 'WebSocket closed');
                this.connected = false;
                this.showStatus('Disconnected from radio', 'error');
                
                // Auto-reconnect
                this.reconnectTimer = setTimeout(() => {
                    log('info', 'ws', 'Reconnecting...');
                    this.connectWebSocket();
                }, 5000);
            };
        } catch (error) {
            log('error', 'ws', 'Failed to create WebSocket:', error);
            this.connected = false;
        }
    },
    
    // === Fetch Initial Status ===
    
    async fetchInitialStatus() {
        try {
            const response = await fetch('/api/status');
            if (response.ok) {
                const data = await response.json();
                log('info', 'api', 'Initial status fetched');
                log('debug', 'api', 'Status data:', data);
                this.updateRadioStatus(data);
            }
        } catch (error) {
            log('error', 'api', 'Failed to fetch status:', error);
        }
    },
    
    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.config) {
                    log('info', 'config', 'Configuration loaded');
                    this.configData = { ...this.configData, ...data.config };
                    log('debug', 'config', 'ROTOR_ENABLED:', this.configData.ROTOR_ENABLED);
                }
            }
        } catch (error) {
            log('error', 'config', 'Failed to fetch config:', error);
        }
    },
    
    async loadRotorStatus() {
        try {
            const response = await fetch('/api/rotor/status');
            if (response.ok) {
                const data = await response.json();
                log('debug', 'rotor', 'Rotor status fetched');
                if (data.enabled) {
                    this.rotorConnected = data.azimuth !== null;
                    if (data.azimuth !== null) {
                        this.rotorAzimuth = data.azimuth;
                    }
                    log('info', 'rotor', 'Rotator connected');
                } else {
                    this.rotorConnected = false;
                }
            }
        } catch (error) {
            log('error', 'rotor', 'Failed to fetch rotor status:', error);
            this.rotorConnected = false;
        }
    },
    
    // === Update Radio Status ===
    
    updateRadioStatus(data) {
        const changes = statusChangeDetector.getChanges(data);
        
        Object.keys(data).forEach(key => {
            // Handle field name aliases from backend
            let actualKey = key;
            
            // Map backend field names to frontend field names
            const fieldMapping = {
                'freq': 'frequency',
                'rfpower': 'drive',
                'tunepower': 'tune_power',
                'miclevel': 'mic_level',
                'vox_enable': 'vox_enabled',
            };
            
            if (key in fieldMapping) {
                actualKey = fieldMapping[key];
            }
            
            // Update cluster connection status - log only if changed
            if (key === 'cluster_connected') {
                this.clusterConnected = data[key];
                this.clusterStatus.connected = data[key];
                if (statusChangeDetector.hasChanged('cluster_connected', data[key])) {
                    log('info', 'cluster', `Connection: ${data[key] ? 'Connected' : 'Disconnected'}`);
                }
            }
            
            // Update cluster info
            if (key === 'cluster_info' && typeof data[key] === 'object') {
                this.clusterStatus.activeName = data[key].activeName || '';
                this.clusterStatus.host = data[key].host || '';
                this.clusterStatus.port = data[key].port || '';
                log('debug', 'cluster', 'Info updated:', this.clusterStatus.activeName);
            }
            
            // Update radioStatus object - log significant changes only
            if (actualKey in this.radioStatus) {
                if (statusChangeDetector.hasChanged(actualKey, data[key])) {
                    this.radioStatus[actualKey] = data[key];
                    // Log important parameters, debug others
                    const importantParams = ['frequency', 'mode', 'mox', 'tune', 'vox_enabled'];
                    const logLevel = importantParams.includes(actualKey) ? 'info' : 'debug';
                    log(logLevel, 'status', `${actualKey} = ${data[key]}`);
                } else {
                    this.radioStatus[actualKey] = data[key];
                }
            }
            
            // Update TX state
            if (key === 'mox' || actualKey === 'mox') this.txState.mox = data[key];
            if (key === 'tune' || actualKey === 'tune') this.txState.tune = data[key];
            if (key === 'vox_enabled' || key === 'vox_enable' || actualKey === 'vox_enabled') this.txState.vox = data[key];
            if (key === 'break_in' || actualKey === 'break_in') this.txState.breakin = data[key];
            
            // Update control sliders
            if (actualKey === 'volume') this.controls.volume = data[key];
            if (actualKey === 'drive') this.controls.drive = data[key];
            if (actualKey === 'tune_power') this.controls.tunePower = data[key];
            if (actualKey === 'mic_level') this.controls.mic = data[key];
            if (actualKey === 'monitor') this.controls.monitor = data[key];
            if (actualKey === 'agc_threshold' || key === 'agc_threshold') this.controls.agcThreshold = data[key];
            
            // Sync logging form frequency only (not mode)
            if (actualKey === 'frequency') {
                this.loggingForm.frequency = data[key];
            }
            
            // Update RIT/XIT
            if (actualKey === 'rit_enabled') this.ritEnabled = data[key];
            if (actualKey === 'rit_freq') this.ritValue = data[key];
            if (actualKey === 'xit_enabled') this.xitEnabled = data[key];
            if (actualKey === 'xit_freq') this.xitValue = data[key];
            
            // Update DSP levels
            if (actualKey === 'nb_level') this.dspLevels.nb = data[key];
            if (actualKey === 'nr_level') this.dspLevels.nr = data[key];
            if (actualKey === 'anf_level') this.dspLevels.anf = data[key];
            if (actualKey === 'apf_level') this.dspLevels.apf = data[key];
        });
    },
    
    // === Send Command ===
    
    async sendCommand(endpoint, payload) {
        try {
            const response = await fetch(`/api/${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Command failed');
            }
            
            const result = await response.json();
            log('info', 'api', `${endpoint} succeeded`);
            log('debug', 'api', 'Response:', result);
            return result;
        } catch (error) {
            log('error', 'api', `${endpoint} failed:`, error);
            this.showStatus(`Error: ${error.message}`, 'error');
            throw error;
        }
    },
    
    // === WebSocket Command (for real-time updates) ===
    
    sendWebSocketCommand(command, params = {}) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            log('error', 'ws', 'WebSocket not connected');
            this.showStatus('Not connected to radio', 'error');
            return;
        }
        
        const message = {
            type: 'command',
            command: command,
            params: params
        };
        
        log('info', 'ws', `Command: ${command}`);
        log('debug', 'ws', 'Params:', params);
        this.ws.send(JSON.stringify(message));
    },
};

// Export for use in main app
window.FlexRadioWebSocket = websocketMethods;