/**
 * WinKeyer Auto-Reconnect Module
 * Handles connection recovery with exponential backoff
 * Enables Phase 3: Device Integration & Testing
 */

class WinKeyerReconnectManager {
  constructor(ui, options = {}) {
    this.ui = ui;
    this.isRetrying = false;
    this.retryCount = 0;
    this.maxRetries = options.maxRetries || 5;
    this.backoffMs = options.backoffMs || [1000, 2000, 5000, 10000, 30000]; // 1s, 2s, 5s, 10s, 30s
    this.retryTimeout = null;
    this.monitorInterval = null;
    this.autoReconnectEnabled = options.autoReconnectEnabled !== false;
    
    // Track connection health
    this.lastSuccessfulConnection = null;
    this.connectionAttempts = 0;
    this.failureReason = null;
  }

  /**
   * Start automatic reconnection attempts
   */
  startAutoReconnect() {
    if (this.isRetrying) {
      console.warn('⚠️ Auto-reconnect already in progress');
      return;
    }

    this.isRetrying = true;
    this.retryCount = 0;
    this.connectionAttempts = 0;
    this.ui._log('🔄 Starting auto-reconnect sequence...');
    this._attemptConnection();
  }

  /**
   * Stop automatic reconnection
   */
  stopAutoReconnect() {
    if (this.retryTimeout) {
      clearTimeout(this.retryTimeout);
      this.retryTimeout = null;
    }
    if (this.monitorInterval) {
      clearInterval(this.monitorInterval);
      this.monitorInterval = null;
    }
    this.isRetrying = false;
    this.retryCount = 0;
    this.ui._log('⏹️ Auto-reconnect stopped');
  }

  /**
   * Attempt a connection with backoff
   */
  async _attemptConnection() {
    this.connectionAttempts++;
    const attemptNum = this.retryCount + 1;
    
    if (this.retryCount >= this.maxRetries) {
      this.ui._log(`❌ Max retries (${this.maxRetries}) exceeded. Giving up.`);
      this.ui._emitError('Max reconnection attempts exceeded', 'error');
      this.stopAutoReconnect();
      return;
    }

    // Calculate backoff delay
    const backoffIndex = Math.min(this.retryCount, this.backoffMs.length - 1);
    const delayMs = this.backoffMs[backoffIndex];
    
    this.ui._log(`🔄 Reconnection attempt ${attemptNum}/${this.maxRetries} (waiting ${delayMs}ms)`);
    
    this.retryTimeout = setTimeout(async () => {
      try {
        this.ui._log(`⏳ Attempting connection (attempt ${attemptNum})...`);
        await this.ui.connect();
        
        // Success!
        this.lastSuccessfulConnection = new Date();
        this.ui._log(`✅ Reconnected successfully after ${attemptNum} attempts`);
        this.stopAutoReconnect();
        this._startHealthMonitor();
        
      } catch (e) {
        this.failureReason = e.message;
        this.ui._log(`❌ Attempt ${attemptNum} failed: ${e.message}`);
        this.retryCount++;
        
        if (this.retryCount < this.maxRetries) {
          this._attemptConnection();
        } else {
          this.ui._log(`❌ All ${this.maxRetries} reconnection attempts failed`);
          this.stopAutoReconnect();
        }
      }
    }, delayMs);
  }

  /**
   * Start monitoring connection health
   */
  _startHealthMonitor() {
    if (this.monitorInterval) return;
    
    this.monitorInterval = setInterval(() => {
      if (!this.ui.isConnected) {
        this.ui._log('⚠️ Connection lost detected by monitor');
        clearInterval(this.monitorInterval);
        this.monitorInterval = null;
        
        // Only auto-reconnect if enabled
        if (this.autoReconnectEnabled) {
          this.startAutoReconnect();
        }
      }
    }, 5000); // Check every 5 seconds
  }

  /**
   * Get connection stats
   */
  getStats() {
    return {
      isRetrying: this.isRetrying,
      retryCount: this.retryCount,
      maxRetries: this.maxRetries,
      connectionAttempts: this.connectionAttempts,
      failureReason: this.failureReason,
      lastSuccessfulConnection: this.lastSuccessfulConnection,
      autoReconnectEnabled: this.autoReconnectEnabled
    };
  }
}

window.WinKeyerReconnectManager = WinKeyerReconnectManager;