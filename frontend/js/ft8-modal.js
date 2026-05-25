/**
 * FT8/FT4 Digital Mode Modal
 * Handles FT8/FT4 decoding, encoding, and QSO management
 */

// Import FT8 decoder (will be loaded dynamically)
let ft8Decoder = null;

// Load FT8 decoder module
async function loadFT8Decoder() {
    if (!ft8Decoder) {
        try {
            const module = await import('./ft8-decoder.js');
            ft8Decoder = module.default;
            console.log('✅ FT8 Decoder module loaded');
        } catch (error) {
            console.error('❌ Failed to load FT8 decoder:', error);
        }
    }
    return ft8Decoder;
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
                isTxCycle: false,
                bandwidth: 50,
                activeTab: 'operate',  // 'operate' or 'settings'
                configSaved: false,
                
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
                    pttMethod: 'CAT',
                    audioInput: 'default',
                    audioOutput: 'default',
                    sampleRate: 12000,
                    autoSequence: false,
                    txEnabled: false,
                    waterfallHeight: 100,
                    useFlexRadioAudio: true
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
                waterfallCtx: null
            },
            
            // WebSocket
            ft8Ws: null
        };
    },
    
    methods: {
        // === Modal Control ===
        
        async openFT8Modal() {
            console.log('Opening FT8 modal');
            this.showFT8Modal = true;
            
            // Load FT8 decoder module
            await loadFT8Decoder();
            
            // Set decoder mode
            if (ft8Decoder) {
                ft8Decoder.setMode(this.ft8.mode);
            }
            
            // Load configuration (includes audio devices)
            this.ft8LoadSettings();
            
            // Initialize waterfall canvas
            this.$nextTick(() => {
                this.initFT8Waterfall();
            });
            
            // Connect to FT8 WebSocket
            this.connectFT8WebSocket();
        },
        
        closeFT8Modal() {
            console.log('Closing FT8 modal');
            this.showFT8Modal = false;
            
            // Cleanup decoder
            if (ft8Decoder) {
                ft8Decoder.clearDecodedMessages();
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
                    this.handleFT8WebSocketMessage(data);
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
        
        handleFT8WebSocketMessage(data) {
            const { type, data: payload } = data;
            
            switch (type) {
                case 'status':
                    this.updateFT8Status(payload);
                    break;
                    
                case 'decoded':
                    this.addDecodedMessage(payload);
                    break;
                
                case 'audio_stream':
                    // Client-side decoding: Process audio data in browser
                    this.handleAudioStream(payload);
                    break;
                    
                case 'waterfall':
                    // Defer waterfall drawing to next frame to avoid blocking
                    requestAnimationFrame(() => {
                        this.updateWaterfall(payload);
                    });
                    break;
                    
                case 'qsos':
                    this.ft8.activeQSOs = payload;
                    break;
                    
                case 'qso_complete':
                    this.handleQSOComplete(payload);
                    break;
                    
                case 'transmitting':
                    this.handleTransmitting(payload);
                    break;
                    
                default:
                    console.log('Unknown FT8 WebSocket message type:', type);
            }
        },
        
        async handleAudioStream(audioData) {
            try {
                // Ensure decoder is loaded
                if (!ft8Decoder) {
                    await loadFT8Decoder();
                }
                
                if (ft8Decoder && ft8Decoder.initialized) {
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
                    
                    // Process audio in decoder
                    ft8Decoder.processAudio(samples);
                    
                    // Get waterfall data from decoder
                    const waterfallData = ft8Decoder.getWaterfallData();
                    if (waterfallData.length > 0) {
                        this.ft8.waterfallData = waterfallData;
                        requestAnimationFrame(() => {
                            this.drawWaterfall();
                        });
                    }
                    
                    // Get decoded messages from decoder
                    const decodedMsgs = ft8Decoder.getDecodedMessages();
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
            this.ft8.connected = status.enabled;
            this.ft8.txEnabled = status.tx_enabled;
            this.ft8.autoSequence = status.auto_sequence;
            this.ft8.isTxCycle = status.is_tx_cycle;
            this.ft8.stats = {
                decoded_count: status.decoded_count,
                transmitted_count: status.transmitted_count,
                qso_completed: status.qso_completed,
                uptime: status.uptime
            };
            this.ft8.txQueue = Array(status.tx_queue_length).fill('queued');
        },
        
        addDecodedMessage(message) {
            // Add to beginning of list
            this.ft8.decodedMessages.unshift(message);
            
            // Keep only last 100 messages
            if (this.ft8.decodedMessages.length > 100) {
                this.ft8.decodedMessages.pop();
            }
            
            // Play notification sound for CQ
            if (message.message.includes('CQ')) {
                // Could add audio notification here
            }
        },
        
        updateWaterfall(data) {
            if (Array.isArray(data) && data.length > 0) {
                this.ft8.waterfallData = data;
                this.drawWaterfall();
            }
        },
        
        handleQSOComplete(qso) {
            console.log('QSO complete:', qso);
            
            // Show notification
            this.$nextTick(() => {
                alert(`QSO Complete with ${qso.their_call}!`);
            });
            
            // Could trigger logging here
        },
        
        handleTransmitting(data) {
            console.log('Transmitting:', data.message);
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
                
                const serverValidation = validateNetworkServer(
                    this.ft8.networkServer || '192.168.0.199:4992'
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
                        auto_sequence: this.ft8.autoSequence,
                        tx_enabled: this.ft8.txEnabled,
                        audioInput: this.ft8.audioInput || 'default',
                        audioOutput: this.ft8.audioOutput || 'default',
                        sampleRate: this.ft8.sampleRate || 12000,
                        waterfallHeight: this.ft8.waterfallHeight || 100,
                        networkServer: this.ft8.networkServer || '192.168.0.199:4992',
                        pttMethod: this.ft8.pttMethod || 'CAT',
                        useFlexRadioAudio: this.ft8.useFlexRadioAudio !== undefined ? this.ft8.useFlexRadioAudio : true
                    })
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }
                
                console.log('✅ FT8 service started successfully');
                this.ft8.connected = true;
                this.ft8.errorMessage = '';
                
            } catch (error) {
                console.error('❌ Error starting FT8 service:', error);
                this.ft8.errorMessage = `Failed to start FT8: ${error.message}`;
                this.ft8.connected = false;
                
                // Show error to user
                alert(this.ft8.errorMessage);
                
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
            this.ft8.bandwidth = this.ft8.mode === 'FT8' ? 50 : 100;
        },
        
        // === Message Selection ===
        
        ft8SelectMessage(message) {
            this.ft8.selectedMessage = message;
            console.log('Selected message:', message);
        },
        
        ft8ClearDecoded() {
            this.ft8.decodedMessages = [];
        },
        
        // === TX Controls ===
        
        async ft8CallCQ() {
            this.ft8.isLoading = true;
            this.ft8.loadingMessage = 'Queueing CQ...';
            this.ft8.errorMessage = '';
            
            try {
                const response = await fetch('/api/ft8/cq', {
                    method: 'POST'
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }
                
                console.log('✅ CQ queued successfully');
                
            } catch (error) {
                console.error('❌ Error calling CQ:', error);
                this.ft8.errorMessage = `Failed to queue CQ: ${error.message}`;
                alert(this.ft8.errorMessage);
                
            } finally {
                this.ft8.isLoading = false;
                this.ft8.loadingMessage = '';
            }
        },
        
        async ft8ReplySelected() {
            if (!this.ft8.selectedMessage) {
                this.ft8.errorMessage = 'No message selected';
                alert('No message selected');
                return;
            }
            
            // Extract callsign from message
            const parts = this.ft8.selectedMessage.message.split(' ');
            let theirCall = null;
            
            if (parts[0] === 'CQ') {
                theirCall = parts[1];
            } else {
                theirCall = parts[0];
            }
            
            if (!theirCall) {
                this.ft8.errorMessage = 'Could not extract callsign from message';
                alert(this.ft8.errorMessage);
                return;
            }
            
            this.ft8.isLoading = true;
            this.ft8.loadingMessage = 'Queueing reply...';
            this.ft8.errorMessage = '';
            
            try {
                const response = await fetch('/api/ft8/reply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        their_call: theirCall.toUpperCase().trim(),
                        report: 'R-15'
                    })
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }
                
                console.log('✅ Reply queued successfully');
                
            } catch (error) {
                console.error('❌ Error replying:', error);
                this.ft8.errorMessage = `Failed to queue reply: ${error.message}`;
                alert(this.ft8.errorMessage);
                
            } finally {
                this.ft8.isLoading = false;
                this.ft8.loadingMessage = '';
            }
        },
        
        async ft8SendReport() {
            if (!this.ft8.selectedMessage) {
                this.ft8.errorMessage = 'No message selected';
                alert('No message selected');
                return;
            }
            
            const parts = this.ft8.selectedMessage.message.split(' ');
            const theirCall = parts[0] === 'CQ' ? parts[1] : parts[0];
            
            const message = `${theirCall} ${this.ft8.mycall} R-15`;
            await this.ft8SendMessage(message);
        },
        
        async ft8SendRRR() {
            if (!this.ft8.selectedMessage) {
                this.ft8.errorMessage = 'No message selected';
                alert('No message selected');
                return;
            }
            
            const parts = this.ft8.selectedMessage.message.split(' ');
            const theirCall = parts[0] === 'CQ' ? parts[1] : parts[0];
            
            const message = `${theirCall} ${this.ft8.mycall} RRR`;
            await this.ft8SendMessage(message);
        },
        
        async ft8Send73(theirCall) {
            if (!theirCall || typeof theirCall !== 'string') {
                this.ft8.errorMessage = 'Invalid callsign';
                alert('Invalid callsign');
                return;
            }
            
            this.ft8.isLoading = true;
            this.ft8.loadingMessage = 'Sending 73...';
            this.ft8.errorMessage = '';
            
            try {
                const sanitizedCall = encodeURIComponent(theirCall.toUpperCase().trim());
                const response = await fetch(`/api/ft8/send73?their_call=${sanitizedCall}`, {
                    method: 'POST'
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }
                
                console.log('✅ 73 queued successfully');
                
            } catch (error) {
                console.error('❌ Error sending 73:', error);
                this.ft8.errorMessage = `Failed to send 73: ${error.message}`;
                alert(this.ft8.errorMessage);
                
            } finally {
                this.ft8.isLoading = false;
                this.ft8.loadingMessage = '';
            }
        },
        
        async ft8SendCustom() {
            const trimmedMessage = this.ft8.customMessage.trim();
            if (!trimmedMessage) {
                this.ft8.errorMessage = 'Message cannot be empty';
                alert('Message cannot be empty');
                return;
            }
            
            await this.ft8SendMessage(trimmedMessage);
            this.ft8.customMessage = '';
        },
        
        async ft8SendMessage(message) {
            if (!message || typeof message !== 'string') {
                this.ft8.errorMessage = 'Invalid message';
                alert('Invalid message');
                return;
            }
            
            this.ft8.isLoading = true;
            this.ft8.loadingMessage = 'Transmitting...';
            this.ft8.errorMessage = '';
            
            try {
                const response = await fetch('/api/ft8/transmit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message.trim() })
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }
                
                console.log('✅ Message queued successfully:', message);
                
            } catch (error) {
                console.error('❌ Error sending message:', error);
                this.ft8.errorMessage = `Failed to send message: ${error.message}`;
                alert(this.ft8.errorMessage);
                
            } finally {
                this.ft8.isLoading = false;
                this.ft8.loadingMessage = '';
            }
        },
        
        // === Waterfall Display ===
        
        initFT8Waterfall() {
            const canvas = this.$refs.ft8Waterfall;
            if (!canvas) {
                console.warn('FT8 waterfall canvas not found');
                return;
            }
            
            // Set canvas size
            canvas.width = 600;
            canvas.height = 300;
            
            this.ft8.waterfallCtx = canvas.getContext('2d');
            
            // Clear canvas
            const ctx = this.ft8.waterfallCtx;
            ctx.fillStyle = '#000';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            
            console.log('✅ FT8 waterfall initialized:', canvas.width, 'x', canvas.height);
        },
        
        drawWaterfall() {
            const canvas = this.$refs.ft8Waterfall;
            if (!canvas || !this.ft8.waterfallCtx || !this.ft8.waterfallData.length) {
                return;
            }
            
            const ctx = this.ft8.waterfallCtx;
            const data = this.ft8.waterfallData;
            
            const width = canvas.width;
            const height = canvas.height;
            
            // Clear canvas
            ctx.fillStyle = '#000';
            ctx.fillRect(0, 0, width, height);
            
            // Draw waterfall (scroll down)
            const rowHeight = height / data.length;
            
            for (let row = 0; row < data.length; row++) {
                const rowData = data[row];
                const y = row * rowHeight;
                
                for (let i = 0; i < rowData.length && i < width; i++) {
                    const intensity = rowData[i];
                    const color = this.getWaterfallColor(intensity);
                    
                    ctx.fillStyle = color;
                    ctx.fillRect(i, y, 1, rowHeight);
                }
            }
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
                
                // Also update operate tab fields
                this.ft8.mode = configData.mode || 'FT8';
                this.ft8.mycall = configData.mycall || 'OM0RX';
                this.ft8.mygrid = configData.mygrid || 'JN88';
                this.ft8.autoSequence = configData.auto_sequence || false;
                this.ft8.txEnabled = configData.tx_enabled || false;
                
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
                const response = await fetch('/api/ft8/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(this.ft8.config)
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }
                
                console.log('✅ FT8 configuration saved successfully');
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