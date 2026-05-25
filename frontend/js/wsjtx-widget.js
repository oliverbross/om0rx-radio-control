/**
 * WSJT-X Integration Widget
 * Handles WSJT-X QSO data display and auto-logging
 */

class WSJTXWidget {
  constructor() {
    this.ws = null;
    this.currentQSO = null;
    this.config = null;
    this.radioStatus = null;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 3;
    this.reconnectDelay = 5000;
    
    this.init();
  }

  async init() {
    // Fetch configuration
    try {
      const response = await fetch('/api/wsjtx/config');
      this.config = await response.json();
      
      if (!this.config.enabled) {
        console.log('🔕 WSJT-X integration disabled');
        return;
      }
      
      console.log('📡 WSJT-X configuration loaded:', this.config);
      this.connect();
    } catch (error) {
      console.warn('⚠️ Failed to load WSJT-X config:', error);
    }
  }

  connect() {
    const wsPort = this.config?.ws_port || 8092;
    const wsUrl = `ws://${window.location.hostname}:${wsPort}`;
    
    if (this.reconnectAttempts === 0) {
      console.log(`🔌 Connecting to WSJT-X WebSocket: ${wsUrl}`);
    }
    
    this.ws = new WebSocket(wsUrl);
    
    this.ws.onopen = () => {
      console.log('✅ WSJT-X WebSocket connected');
      this.isConnected = true;
      this.reconnectAttempts = 0;
    };
    
    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.handleMessage(msg);
      } catch (error) {
        console.debug('Debug: Could not parse WebSocket message:', error);
      }
    };
    
    this.ws.onerror = (error) => {
      console.debug('WSJT-X WebSocket error (attempt ' + (this.reconnectAttempts + 1) + ')');
      this.isConnected = false;
    };
    
    this.ws.onclose = () => {
      this.isConnected = false;
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
        console.warn(`⚠️ WSJT-X disconnected. Reconnecting in ${Math.round(delay / 1000)}s (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        setTimeout(() => this.connect(), delay);
      } else {
        console.warn('❌ WSJT-X: Max reconnect attempts reached. Giving up.');
      }
    };
  }

  handleMessage(msg) {
    if (!msg.source || msg.source !== 'wsjtx') {
      return;
    }

    const type = msg.type;
    
    if (type === 'Status') {
      this.handleStatus(msg);
    } else if (type === 'Decode') {
      this.handleDecode(msg);
    } else if (type === 'LoggedAdif') {
      this.handleLoggedAdif(msg);
    }
  }

  handleStatus(msg) {
    /**
     * Status message from WSJT-X when transmitting/receiving
     * dialFrequency, txEnabled, dxCall, dxGrid, mode, txRst, rxRst
     */
    if (msg.dxCall) {
      // New or ongoing QSO
      this.currentQSO = {
        call: msg.dxCall,
        grid: msg.dxGrid || '',
        mode: msg.mode,
        frequency_hz: msg.dialFrequency,
        rst_sent: parseInt(msg.txRst) || 599,
        rst_received: parseInt(msg.rxRst) || 599,
        started_at: new Date()
      };
      
      console.log(`📡 QSO Status: ${msg.dxCall} (${msg.dxGrid}) ${msg.mode}`);
      
      this.showModal(msg);
      this.populateLogForm(msg);
      
      // Auto-rotate if enabled
      if (this.config.auto_rotate && msg.dxGrid) {
        this.autoRotate(msg);
      }
    }
  }

  handleDecode(msg) {
    /**
     * Decode message from WSJT-X
     * Contains decoded CW/digital data
     */
    if (msg.message) {
      console.log(`🔤 Decode: ${msg.message}`);
      // Could update UI with decode messages if desired
    }
  }

  async handleLoggedAdif(msg) {
    /**
     * LoggedAdif message - QSO has been logged in WSJT-X
     * This is our signal to auto-log to Wavelog
     */
    console.log(`✅ WSJT-X Logged: ${msg.dxCall} on ${msg.mode}`);
    
    if (this.config.auto_log) {
      await this.autoLogQSO(msg);
    }
    
    // Close modal after a delay
    setTimeout(() => this.closeModal(), 2000);
    
    this.currentQSO = null;
  }

  async autoLogQSO(msg) {
    try {
      const logData = {
        call: msg.dxCall,
        grid: msg.dxGrid,
        mode: msg.mode,
        frequency_hz: msg.dialFrequency,
        rst_sent: parseInt(msg.txRst) || 599,
        rst_received: parseInt(msg.rxRst) || 599,
        operator: null,
        comments: `Auto-logged from WSJT-X (${msg.mode})`
      };
      
      console.log(`📝 Auto-logging to Wavelog: ${msg.dxCall}...`);
      
      const response = await fetch('/api/wsjtx/log-qso', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(logData)
      });
      
      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          console.log(`✅ Auto-logged successfully: ${msg.dxCall}`);
          this.showNotification('QSO logged to Wavelog!', 'success');
        } else {
          console.error('❌ Auto-log failed:', result);
          this.showNotification('Auto-log failed', 'error');
        }
      } else {
        console.error('❌ Auto-log HTTP error:', response.status);
        this.showNotification('Auto-log error', 'error');
      }
    } catch (error) {
      console.error('❌ Auto-log exception:', error);
      this.showNotification('Auto-log exception', 'error');
    }
  }

  async autoRotate(msg) {
    try {
      const rotateData = {
        call: msg.dxCall,
        grid: msg.dxGrid,
        frequency_hz: msg.dialFrequency
      };
      
      console.log(`🎯 Auto-rotating to ${msg.dxCall}...`);
      
      const response = await fetch('/api/wsjtx/auto-rotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rotateData)
      });
      
      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          console.log(`✅ Rotated to ${result.bearing}°`);
          this.updateModalBearing(result);
        } else {
          console.warn(`⚠️ Auto-rotate not available: ${result.reason}`);
        }
      }
    } catch (error) {
      console.error('❌ Auto-rotate error:', error);
    }
  }

  showModal(msg) {
    const modal = this.getOrCreateModal();
    
    // Update modal content
    const callEl = modal.querySelector('[data-field="call"]');
    const gridEl = modal.querySelector('[data-field="grid"]');
    const modeEl = modal.querySelector('[data-field="mode"]');
    const reportsEl = modal.querySelector('[data-field="reports"]');
    const bearingEl = modal.querySelector('[data-field="bearing"]');
    
    if (callEl) callEl.textContent = msg.dxCall;
    if (gridEl) gridEl.textContent = msg.dxGrid || '—';
    if (modeEl) modeEl.textContent = msg.mode;
    if (reportsEl) {
      const txRst = parseInt(msg.txRst) || 599;
      const rxRst = parseInt(msg.rxRst) || 599;
      reportsEl.textContent = `Sent: ${txRst} / Rcvd: ${rxRst}`;
    }
    if (bearingEl) bearingEl.style.display = 'none';
    
    modal.style.display = 'flex';
    
    // Auto-close if configured
    if (this.modalTimeout) clearTimeout(this.modalTimeout);
    // Don't auto-close, let LoggedAdif message close it
  }

  updateModalBearing(result) {
    const modal = this.getOrCreateModal();
    const bearingEl = modal.querySelector('[data-field="bearing"]');
    
    if (bearingEl) {
      bearingEl.innerHTML = `
        <strong>Bearing:</strong> ${result.bearing.toFixed(1)}°
        ${result.adjusted_bearing !== result.bearing ? ` → ${result.adjusted_bearing.toFixed(1)}° (adjusted)` : ''}
      `;
      bearingEl.style.display = 'block';
    }
  }

  closeModal() {
    const modal = document.getElementById('wsjtx-qso-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  getOrCreateModal() {
    let modal = document.getElementById('wsjtx-qso-modal');
    
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'wsjtx-qso-modal';
      modal.className = 'wsjtx-modal';
      modal.innerHTML = `
        <div class="wsjtx-modal-content">
          <div class="wsjtx-modal-header">
            <h2>🔊 WSJT-X QSO In Progress</h2>
            <button class="wsjtx-modal-close" type="button">&times;</button>
          </div>
          <div class="wsjtx-modal-body">
            <div class="wsjtx-field">
              <label>Call:</label>
              <span data-field="call">—</span>
            </div>
            <div class="wsjtx-field">
              <label>Grid:</label>
              <span data-field="grid">—</span>
            </div>
            <div class="wsjtx-field">
              <label>Mode:</label>
              <span data-field="mode">—</span>
            </div>
            <div class="wsjtx-field">
              <label>Reports:</label>
              <span data-field="reports">—</span>
            </div>
            <div class="wsjtx-field" style="display: none;">
              <label>Bearing:</label>
              <span data-field="bearing">—</span>
            </div>
          </div>
          <div class="wsjtx-modal-footer">
            <small>Auto-logging ${this.config.auto_log ? '✓' : '✗'} | Auto-rotate ${this.config.auto_rotate ? '✓' : '✗'}</small>
          </div>
        </div>
      `;
      
      // Close button handler
      modal.querySelector('.wsjtx-modal-close').addEventListener('click', () => {
        this.closeModal();
      });
      
      // Click outside to close
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          this.closeModal();
        }
      });
      
      document.body.appendChild(modal);
      this.addModalStyles();
    }
    
    return modal;
  }

  addModalStyles() {
    if (document.getElementById('wsjtx-modal-styles')) {
      return;
    }
    
    const style = document.createElement('style');
    style.id = 'wsjtx-modal-styles';
    style.textContent = `
      .wsjtx-modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: rgba(0, 0, 0, 0.5);
        z-index: 10000;
        align-items: center;
        justify-content: center;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      }
      
      .wsjtx-modal-content {
        background: white;
        border-radius: 12px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
        max-width: 400px;
        width: 90%;
        overflow: hidden;
        animation: slideIn 0.3s ease-out;
      }
      
      @keyframes slideIn {
        from {
          transform: translateY(-20px);
          opacity: 0;
        }
        to {
          transform: translateY(0);
          opacity: 1;
        }
      }
      
      .wsjtx-modal-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      
      .wsjtx-modal-header h2 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
      }
      
      .wsjtx-modal-close {
        background: rgba(255, 255, 255, 0.2);
        border: none;
        color: white;
        font-size: 28px;
        cursor: pointer;
        padding: 0;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
        transition: background 0.2s;
      }
      
      .wsjtx-modal-close:hover {
        background: rgba(255, 255, 255, 0.3);
      }
      
      .wsjtx-modal-body {
        padding: 24px;
      }
      
      .wsjtx-field {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid #f0f0f0;
      }
      
      .wsjtx-field:last-of-type {
        border-bottom: none;
      }
      
      .wsjtx-field label {
        font-weight: 600;
        color: #333;
        min-width: 80px;
      }
      
      .wsjtx-field span {
        text-align: right;
        color: #667eea;
        font-weight: 500;
        font-family: 'Courier New', monospace;
      }
      
      .wsjtx-modal-footer {
        background: #f8f9fa;
        padding: 12px 20px;
        text-align: center;
        color: #666;
        border-top: 1px solid #eee;
      }
      
      .wsjtx-modal-footer small {
        font-size: 12px;
      }
      
      /* Responsive */
      @media (max-width: 600px) {
        .wsjtx-modal-content {
          max-width: 95%;
        }
        
        .wsjtx-modal-body {
          padding: 16px;
        }
        
        .wsjtx-modal-header h2 {
          font-size: 16px;
        }
      }
    `;
    document.head.appendChild(style);
  }

  populateLogForm(msg) {
    /**
     * Try to find the Log QSO form and pre-fill it with WSJT-X data
     */
    try {
      // Try to dispatch a custom event for other components to listen to
      window.dispatchEvent(new CustomEvent('wsjtx-qso', {
        detail: {
          call: msg.dxCall,
          grid: msg.dxGrid,
          mode: msg.mode,
          frequency_hz: msg.dialFrequency
        }
      }));
    } catch (error) {
      console.debug('Debug: Could not dispatch event:', error);
    }
  }

  showNotification(message, type = 'info') {
    // Simple notification (can be enhanced to integrate with existing UI)
    console.log(`[${type.toUpperCase()}] ${message}`);
  }
}

// Auto-initialization DISABLED
// This class is kept for reference but should not be used
// WSJT-X handling is done via sdc-ticker.js + wsjtx-handler.js instead
// if (document.readyState === 'loading') {
//   document.addEventListener('DOMContentLoaded', () => {
//     window.wsjtxWidget = new WSJTXWidget();
//   });
// } else {
//   window.wsjtxWidget = new WSJTXWidget();
// }