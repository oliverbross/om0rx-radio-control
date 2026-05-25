/**
 * WinKeyer UI Controller
 * Manages Winkeyer widget state and interactions in the main app
 */

class WinKeyerUI {
  constructor(vueApp) {
    this.vue = vueApp;
    this.client = null;
    this.isConnected = false;
    this.showWpmSlider = false;
    this.errorCallback = null;  // For error notification to app
    this.lastError = null;
    
    // Phase 3 modules
    this.reconnectManager = null;
    this.feedbackHandler = null;
    this.tester = null;
    this.connectionStartTime = null;

    // Winkeyer data is already in Vue from app-main.js data()
    // We just need to ensure the reference works properly
    if (!this.vue.$data.winkeyer) {
      console.error('❌ WinKeyer data property not found in Vue instance!');
    }
  }

  /**
   * Register error callback for main app notifications
   */
  onError(callback) {
    this.errorCallback = callback;
  }

  /**
   * Emit error to registered callback
   */
  _emitError(message, type = 'warning') {
    this.lastError = message;
    this.vue.$data.winkeyer.lastError = message;
    this._log(`❌ ${message}`);
    if (this.errorCallback) {
      this.errorCallback({
        message,
        type,
        timestamp: new Date().toISOString()
      });
    }
  }

  /**
   * Initialize Winkeyer UI from config
   */
  async init(config) {
    console.log('[WK-UI] init() called with config:', config);
    
    if (!config.WINKEYER_ENABLED) {
      this.vue.$data.winkeyer.enabled = false;
      console.log('[WK-UI] WinKeyer disabled in config');
      return;
    }

    this.vue.$data.winkeyer.enabled = true;
    
    // Update config properties IN-PLACE to preserve Vue reactivity
    this.vue.$data.winkeyer.config.port = config.WINKEYER_PORT || 'COM3';
    this.vue.$data.winkeyer.config.baudRate = config.WINKEYER_BAUDRATE || 1200;
    this.vue.$data.winkeyer.config.defaultWpm = config.WINKEYER_DEFAULT_WPM || 20;
    
    // Update memories IN-PLACE to preserve Vue reactivity
    const newMemories = config.WINKEYER_MEMORIES || {
      M1: 'CQ DE OM0RX',
      M2: 'UR RST 599',
      M3: 'QSL TU DE OM0RX',
      M4: 'MNI TU'
    };
    Object.assign(this.vue.$data.winkeyer.memories, newMemories);
    
    this.vue.$data.winkeyer.currentWpm = config.WINKEYER_DEFAULT_WPM || 20;
    
    // Phase 3: Initialize advanced modules
    console.log('[WK-UI] Calling _initializePhase3Modules()');
    this._initializePhase3Modules();
  }

  /**
   * Initialize Phase 3 modules (auto-reconnect, feedback, testing)
   */
  _initializePhase3Modules() {
    console.log('[WK-UI] _initializePhase3Modules() called');
    console.log('[WK-UI] Class availability:', {
      WinKeyerReconnectManager: typeof window.WinKeyerReconnectManager,
      WinKeyerFeedbackHandler: typeof window.WinKeyerFeedbackHandler,
      WinKeyerTester: typeof window.WinKeyerTester
    });
    
    // Create reconnect manager
    if (window.WinKeyerReconnectManager) {
      this.reconnectManager = new WinKeyerReconnectManager(this, {
        maxRetries: 5,
        backoffMs: [1000, 2000, 5000, 10000, 30000],
        autoReconnectEnabled: true
      });
      console.log('[WK-UI] ✓ ReconnectManager created');
    } else {
      console.log('[WK-UI] ✗ WinKeyerReconnectManager not found');
    }

    // Create feedback handler
    if (window.WinKeyerFeedbackHandler) {
      this.feedbackHandler = new WinKeyerFeedbackHandler(this);
      window.feedbackHandler = this.feedbackHandler; // For tester access
      console.log('[WK-UI] ✓ FeedbackHandler created:', this.feedbackHandler);
    } else {
      console.log('[WK-UI] ✗ WinKeyerFeedbackHandler not found on window!');
    }

    // Create tester utility
    if (window.WinKeyerTester) {
      this.tester = new WinKeyerTester(this);
      window.winKeyerTester = this.tester; // For console access
      console.log('[WK-UI] ✓ Tester created');
    } else {
      console.log('[WK-UI] ✗ WinKeyerTester not found');
    }

    this._log('⚙️ Phase 3 modules initialized');
  }

  /**
   * Connect to Winkeyer device
   */
  async connect() {
    if (this.isConnected) {
      console.warn('Already connected');
      return;
    }

    try {
      this.connectionStartTime = new Date();
      this.client = new WinKeyerClient({
        baudRate: this.vue.$data.winkeyer.config.baudRate,
        wpm: this.vue.$data.winkeyer.config.defaultWpm,
        onLog: (msg) => this._log(msg),
        onRaw: (b) => this._onRaw(b)
      });
      
      // Enable debug mode for diagnostic logging
      this.client.debugMode = true;
      this._log('🐛 Debug mode enabled - monitoring hardware button events');

      this.client.onOpen = async (rev) => {
        this._log(`✅ Connected! WK Rev: ${rev || '?'}`);
        this.isConnected = true;
        this.vue.$data.winkeyer.isConnected = true;
        this.vue.$data.winkeyer.status = '🟢 Connected';
        this.vue.$data.winkeyer.connectionTime = this.connectionStartTime.toISOString();
        this.vue.$data.winkeyer.lastError = null;

        // Set initial mode and WPM
        try {
          await this.client.setMode({
            paddleEcho: true,
            serialEcho: true,
            autospace: false,
            paddleSwap: false,
            keyMode: 'IAMBICB'
          });
          await this.client.setWpm(this.vue.$data.winkeyer.currentWpm);
        } catch (e) {
          this._emitError(`Error setting mode/WPM: ${e.message}`, 'error');
        }
      };

      this.client.onStatus = (status) => {
        // Log status for debugging
        this._log(`📊 Status received: tag=${status.tag}, keyDown=${status.keyDown}, busy=${status.busy}, breakIn=${status.breakIn}, xoff=${status.xoff}, rawByte=0x${status.rawByte?.toString(16).padStart(2, '0') || 'N/A'}`);
        console.log(`[WK-UI] onStatus called with:`, status);
        
        // Phase 3: Use feedback handler
        if (this.feedbackHandler) {
          console.log(`[WK-UI] feedbackHandler exists, calling handlers`);
          this.feedbackHandler.handleStatusFeedback(status);
          this.feedbackHandler.handleButtonFeedback(status);
        } else {
          console.log(`[WK-UI] feedbackHandler is null!`);
        }
      };

      this.client.onPot = async (wpm) => {
        // Phase 3: Use feedback handler
        if (this.feedbackHandler) {
          this.feedbackHandler.handlePotentiometerChange(wpm);
        }
        
        // Physical potentiometer changed
        this.vue.$data.winkeyer.currentWpm = wpm;
        try {
          await this.client.setWpm(wpm);
        } catch (e) {
          this._emitError(`Error setting WPM from pot: ${e.message}`, 'warning');
        }
      };

      this.client.onEcho = (ch) => {
        // Phase 3: Log echo for testing
        if (this.feedbackHandler) {
          this.feedbackHandler.handleEchoCharacter(ch);
        }
      };

      this.client.onExtended = (extended) => {
        // Log extended message for debugging
        this._log(`🔧 Extended message: paddleLeft=${extended.paddleLeft}, paddleRight=${extended.paddleRight}, wpm=${extended.wpm}, sidetone=${extended.sidetone}, flags=${extended.flags}`);
        
        // Phase 3: Handle extended messages
        if (this.feedbackHandler) {
          this.feedbackHandler.handleExtendedFeedback(extended);
        }
      };

      // Set error handler for device disconnection
      this.client.onError = (err) => {
        this._emitError(`Device error: ${err.message}`, 'error');
        this.disconnect();
      };

      await this.client.open();
    } catch (e) {
      const errorMsg = e.message || 'Unknown connection error';
      this._emitError(`Connection failed: ${errorMsg}`, 'error');
      this.vue.$data.winkeyer.status = `🔴 Error: ${errorMsg}`;
      this.client = null;
      this.isConnected = false;
      this.vue.$data.winkeyer.isConnected = false;
      
      // Phase 3: Trigger auto-reconnect
      if (this.reconnectManager && this.reconnectManager.autoReconnectEnabled) {
        this.reconnectManager.startAutoReconnect();
      }
    }
  }

  /**
   * Disconnect from Winkeyer device
   */
  async disconnect() {
    if (!this.isConnected || !this.client) {
      console.warn('Not connected');
      return;
    }

    try {
      // Phase 3: Stop auto-reconnect when manually disconnecting
      if (this.reconnectManager) {
        this.reconnectManager.stopAutoReconnect();
      }

      await this.client.disconnect();
      this.isConnected = false;
      this.vue.$data.winkeyer.isConnected = false;
      this.vue.$data.winkeyer.status = '🔴 Disconnected';
      this.vue.$data.winkeyer.connectionTime = null;
      this.vue.$data.winkeyer.lastError = null;
      this._log('✅ Disconnected');
      this.client = null;
      this.connectionStartTime = null;
    } catch (e) {
      this._emitError(`Disconnect error: ${e.message}`, 'warning');
    }
  }

  /**
   * Set WPM speed
   */
  async setWpm(wpm) {
    if (!this.isConnected || !this.client) {
      this._emitError(`Cannot set WPM: WinKeyer not connected`, 'warning');
      return;
    }

    const v = Math.max(5, Math.min(50, parseInt(wpm) || 20));
    this.vue.$data.winkeyer.currentWpm = v;

    try {
      this._log(`⚡ Setting WPM: ${v}`);
      await this.client.setWpm(v);
    } catch (e) {
      this._emitError(`Error setting WPM to ${v}: ${e.message}`, 'error');
    }
  }

  /**
   * Send macro from memory
   */
  async sendMacro(memory) {
    if (!this.isConnected || !this.client) {
      this._emitError(`Cannot send macro: WinKeyer not connected`, 'warning');
      return;
    }

    const text = this.vue.$data.winkeyer.memories[memory];
    if (!text) {
      this._emitError(`Memory ${memory} not found or empty`, 'warning');
      return;
    }

    try {
      this._log(`📡 Sending ${memory}: "${text}"`);
      await this.client.sendText(text);
      this._log(`✅ ${memory} transmitted successfully`);
    } catch (e) {
      this._emitError(`Error sending macro ${memory}: ${e.message}`, 'error');
    }
  }

  /**
   * Toggle WPM slider visibility
   */
  toggleWpmSlider() {
    this.vue.$data.winkeyer.showWpmSlider = !this.vue.$data.winkeyer.showWpmSlider;
  }

  /**
   * Update Winkeyer config
   */
  updateConfig(config) {
    this.vue.$data.winkeyer.config = {
      ...this.vue.$data.winkeyer.config,
      ...config
    };
  }

  /**
   * Update memory definition
   */
  updateMemory(memoryKey, text) {
    this.vue.$data.winkeyer.memories[memoryKey] = text;
  }

  /**
   * Internal: Log message
   */
  _log(msg) {
    const ts = new Date().toLocaleTimeString();
    const logEntry = `[${ts}] ${msg}`;
    this.vue.$data.winkeyer.logs.push(logEntry);
    // Keep only last 50 logs
    if (this.vue.$data.winkeyer.logs.length > 50) {
      this.vue.$data.winkeyer.logs.shift();
    }
    console.log(logEntry);
  }

  /**
   * Internal: Handle raw bytes from device
   */
  _onRaw(b) {
    // Raw byte handler for additional debugging
    // Check the browser console for [WK-DEBUG] logs
  }

  /**
   * Diagnostic helper: Enable/disable debug logging
   */
  setDebugMode(enabled) {
    if (this.client) {
      this.client.debugMode = enabled;
      this._log(`🐛 Debug mode: ${enabled ? 'ENABLED - check browser console' : 'DISABLED'}`);
    }
  }

  /**
   * Diagnostic helper: Print current connection state
   */
  printDiagnostics() {
    const diags = {
      connected: this.isConnected,
      clientExists: !!this.client,
      debugMode: this.client?.debugMode || false,
      status: this.vue.$data.winkeyer.status,
      recentLogs: this.vue.$data.winkeyer.logs.slice(-10)
    };
    console.log('🔍 WinKeyer Diagnostics:', diags);
    this._log('📋 Diagnostics printed to console');
    return diags;
  }
}

// Export for use in main app
window.WinKeyerUI = WinKeyerUI;
console.log('[WK-UI] WinKeyerUI class exported to window');