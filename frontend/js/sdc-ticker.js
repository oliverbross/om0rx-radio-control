// SDC Decoded CW Text Ticker Module
// Connects to SDC Skimmer TCP Broadcast via WebSocket bridge

// Safe logging wrapper (Logger loaded by logger.js, falls back to console if not available)
// Use var instead of const to allow redeclaration across script files
var log = log || (window.Logger?.log || ((level, topic, ...args) => console[level]?.(`[${topic}]`, ...args)));
var debugEnabled = debugEnabled ?? (window.Logger?.debugEnabled ?? false);

if (debugEnabled) log('info', 'init', 'Loading sdc-ticker.js module');

window.SDCTicker = {
    data: {
        sdcConnected: false,
        sdcBuffer: [],
        sdcTickerContent: '',
        sdcWebSocket: null,
        sdcMaxBufferSize: 255,  // Adjusted to prevent horizontal scrollbar
        sdcReconnectDelay: 5000,
        sdcReconnectAttempts: 0,
        sdcMaxReconnectAttempts: 3,
    },

    methods: {
        // Initialize SDC WebSocket connection
        initSDCTicker() {
            if (this.sdcReconnectAttempts === 0) {
                log('info', 'sdc', 'Initializing WebSocket connection');
            }
            
            // Connect to SDC WebSocket bridge
            const wsUrl = `ws://${window.location.hostname}:8091`;
            
            try {
                this.sdcWebSocket = new WebSocket(wsUrl);
                
                this.sdcWebSocket.onopen = () => {
                    log('info', 'sdc', 'WebSocket connected');
                    this.sdcConnected = true;
                    if (window.app) window.app.sdcConnected = true;
                    this.sdcReconnectAttempts = 0;
                };
                
                this.sdcWebSocket.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        
                        // Handle SDC messages (decoded CW text)
                        if (data.text && data.source === 'sdc') {
                            this.addSDCText(data.text);
                        }
                        
                        // Handle WSJT-X messages (forward to handler)
                        if (data.source === 'wsjtx') {
                            log('debug', 'sdc', `Forwarding WSJT-X: ${data.type}`);
                            window.dispatchEvent(new CustomEvent('wsjtx-message', { detail: data }));
                        }
                    } catch (e) {
                        log('warn', 'sdc', `Failed to parse message: ${e.message}`);
                    }
                };
                
                this.sdcWebSocket.onerror = (error) => {
                    log('debug', 'sdc', `WebSocket error (attempt ${this.sdcReconnectAttempts + 1})`);
                    this.sdcConnected = false;
                    if (window.app) window.app.sdcConnected = false;
                };
                
                this.sdcWebSocket.onclose = () => {
                    this.sdcConnected = false;
                    if (window.app) window.app.sdcConnected = false;
                    this.scheduleSDCReconnect();
                };
            } catch (e) {
                log('debug', 'sdc', `Failed to create WebSocket (attempt ${this.sdcReconnectAttempts + 1})`);
                this.scheduleSDCReconnect();
            }
        },

        // Add decoded CW text to buffer and update ticker
        addSDCText(text) {
            // Skip only if completely empty, preserve spaces!
            if (text === null || text === undefined) {
                return;
            }
            
            this.sdcBuffer.push(text);
            if (window.app) window.app.sdcBuffer.push(text);
            
            // Keep buffer size limited
            if (this.sdcBuffer.length > this.sdcMaxBufferSize) {
                this.sdcBuffer.shift();
                if (window.app) window.app.sdcBuffer.shift();
            }
            
            // Update ticker display with last 10 items
            this.updateSDCTicker();
        },

        // Update ticker display content
        updateSDCTicker() {
            if (this.sdcBuffer.length === 0) {
                this.sdcTickerContent = '';
                if (window.app) window.app.sdcTickerContent = '';
                return;
            }
            
            // Show last 200+ characters as continuous scrolling text
            // This maximizes use of the row width
            const displayItems = this.sdcBuffer.slice(-200);
            
            // Concatenate all characters directly (no bullets between each)
            // Spaces separate words and will have bullets
            let result = '';
            for (let i = 0; i < displayItems.length; i++) {
                const char = displayItems[i];
                const nextChar = i < displayItems.length - 1 ? displayItems[i + 1] : null;
                
                result += char;
                
                // Add bullet separator between words (when space is encountered)
                if (char === ' ' && nextChar && nextChar !== ' ') {
                    result += '   •   ';
                }
            }
            
            this.sdcTickerContent = result;
            if (window.app) window.app.sdcTickerContent = result;
            
            // Auto-scroll the ticker display if element exists
            this.$nextTick(() => {
                if (this.$refs.sdcTickerDisplay) {
                    this.$refs.sdcTickerDisplay.scrollLeft = this.$refs.sdcTickerDisplay.scrollWidth;
                }
            });
        },

        // Schedule reconnection attempt with exponential backoff
        scheduleSDCReconnect() {
            if (this.sdcReconnectAttempts >= this.sdcMaxReconnectAttempts) {
                log('warn', 'sdc', 'Max reconnect attempts reached');
                return;
            }
            
            this.sdcReconnectAttempts++;
            const delay = this.sdcReconnectDelay * Math.pow(1.5, this.sdcReconnectAttempts - 1);
            log('warn', 'sdc', `Disconnected. Reconnecting in ${Math.round(delay / 1000)}s (attempt ${this.sdcReconnectAttempts}/${this.sdcMaxReconnectAttempts})`);
            
            setTimeout(() => {
                if (!this.sdcConnected) {
                    this.initSDCTicker();
                }
            }, delay);
        },

        // Clear SDC buffer
        clearSDCBuffer() {
            this.sdcBuffer = [];
            this.sdcTickerContent = '';
            if (window.app) {
                window.app.sdcBuffer = [];
                window.app.sdcTickerContent = '';
            }
        },

        // Cleanup SDC connection
        cleanupSDCTicker() {
            if (this.sdcWebSocket) {
                try {
                    this.sdcWebSocket.close();
                } catch (e) {
                    log('warn', 'sdc', `Error closing WebSocket: ${e.message}`);
                }
                this.sdcWebSocket = null;
            }
            this.sdcConnected = false;
            if (window.app) window.app.sdcConnected = false;
        }
    }
};

if (debugEnabled) log('info', 'init', 'SDC Ticker module loaded');