/**
 * WSJT-X Integration Handler
 * 
 * Receives WSJT-X data from the bridge and:
 * 1. Auto-populates Log QSO form with DX call and grid (in index.html)
 * 2. Auto-rotates antenna to DX grid (if enabled)
 * 3. Saves completed QSOs to Wavelog with combined WSJT-X + QRZ data
 */

// Safe logging wrapper (Logger loaded by logger.js, falls back to console if not available)
// Use var instead of const to allow redeclaration across script files
var log = log || (window.Logger?.log || ((level, topic, ...args) => console[level]?.(`[${topic}]`, ...args)));
var debugEnabled = debugEnabled ?? (window.Logger?.debugEnabled ?? false);

let wsjtxData = {
  dxCall: '',
  dxGrid: '',
  dialFrequency: null,
  mode: '',
  txRst: '',
  rxRst: '',
  lastUpdate: null
};

let previousDxCall = '';
let wsjtxHandlerInitialized = false;

/**
 * Initialize WSJT-X handler
 */
function initWsjtxHandler() {
  if (wsjtxHandlerInitialized) {
    return;
  }
  wsjtxHandlerInitialized = true;
  if (debugEnabled) log('info', 'wsjtx', 'Handler initialized');
  
  // Listen for messages from sdc-ticker (which receives them from bridge WebSocket)
  window.addEventListener('wsjtx-message', handleWsjtxMessage);
}

/**
 * Handle incoming WSJT-X messages from bridge
 */
function handleWsjtxMessage(event) {
  const data = event.detail;
  
  if (!data || !data.source || data.source !== 'wsjtx') {
    return;
  }

  log('debug', 'wsjtx', 'Message received:', data.type);

  switch (data.type) {
    case 'wsjtx_status':
      handleWsjtxStatus(data);
      break;
    
    case 'wsjtx_decode':
      handleWsjtxDecode(data);
      break;
    
    case 'wsjtx_logged_adif':
      handleWsjtxLoggedAdif(data);
      break;

    case 'wsjtx_log_result':
      handleWsjtxLogResult(data);
      break;
    
    default:
      log('debug', 'wsjtx', 'Unknown message type:', data.type);
  }
}

/**
 * Handle WSJT-X Status message
 */
function handleWsjtxStatus(data) {
  if (!data.dxCall) {
    return;
  }

  log('info', 'wsjtx', `Status: ${data.dxCall} (${data.dxGrid})`);
  if (data.txRst) log('debug', 'wsjtx', `TX RST: ${data.txRst}`);
  if (data.rxRst) log('debug', 'wsjtx', `RX RST: ${data.rxRst}`);

  // Detect if a NEW contact started (different call)
  const isNewContact = data.dxCall !== previousDxCall;
  if (isNewContact && previousDxCall) {
    log('info', 'wsjtx', `New contact: ${previousDxCall} → ${data.dxCall}`);
    clearLogQsoForm();
  }
  previousDxCall = data.dxCall;

  // Store the data for later use
  wsjtxData = {
    dxCall: data.dxCall,
    dxGrid: data.dxGrid,
    dialFrequency: data.dialFrequency,
    mode: 'FT8', // Default mode for WSJT-X
    txRst: data.txRst || '',  // Capture actual RST values
    rxRst: data.rxRst || '',
    lastUpdate: Date.now()
  };

  // 1. Auto-populate Log QSO form with DX call and grid
  autoPopulateLogQsoForm(data.dxCall, data.dxGrid, data.dialFrequency, data.txRst, data.rxRst);

  // 2. Auto-rotate antenna if enabled
  autoRotateToGrid(data.dxCall, data.dxGrid, data.dialFrequency);
}

/**
 * Handle WSJT-X Decode message
 */
function handleWsjtxDecode(data) {
  log('debug', 'wsjtx', `Decode: ${data.message}`);
}

/**
 * Handle WSJT-X LoggedAdif message
 */
function handleWsjtxLoggedAdif(data) {
  log('info', 'wsjtx', `QSO Logged: ${data.dxCall} (${data.dxGrid})`);
  // The bridge posts LoggedADIF directly to the backend. Keeping this handler
  // display-only prevents the browser from creating a second Wavelog QSO.
  wsjtxData = {
    ...wsjtxData,
    dxCall: data.dxCall || wsjtxData.dxCall,
    dxGrid: data.dxGrid || wsjtxData.dxGrid,
    dialFrequency: data.dialFrequency || wsjtxData.dialFrequency,
    mode: data.mode || wsjtxData.mode,
    txRst: data.txRst || wsjtxData.txRst,
    rxRst: data.rxRst || wsjtxData.rxRst,
    lastUpdate: Date.now()
  };
}

/**
 * Handle the bridge/backend result after a LoggedAdif QSO was sent to Wavelog.
 */
function handleWsjtxLogResult(data) {
  const qso = data.qso_data || {};
  const call = (qso.callsign || data.dxCall || wsjtxData.dxCall || '').toUpperCase();
  const status = data.success ? 'success' : 'error';
  const modalData = {
    callsign: call || 'Unknown',
    frequency: qso.frequency || (data.dialFrequency ? data.dialFrequency / 1_000_000 : ''),
    mode: qso.mode || data.mode || wsjtxData.mode || 'FT8',
    grid: qso.gridsquare || data.dxGrid || wsjtxData.dxGrid || '',
    rst_sent: qso.rst_sent || data.txRst || wsjtxData.txRst || '',
    rst_received: qso.rst_received || data.rxRst || wsjtxData.rxRst || '',
    country: qso.country || 'N/A',
    message: data.message || (data.queued ? 'QSO queued for retry' : 'QSO log failed')
  };

  log(
    status === 'success' ? 'info' : 'error',
    'wavelog',
    `WSJT-X QSO log result: ${status.toUpperCase()} ${modalData.callsign} - ${modalData.message}`
  );
  showWsjtxSaveModal(status, modalData);

  if (status === 'success' && window.vueInstance && typeof window.vueInstance.clearLoggingForm === 'function') {
    setTimeout(() => {
      window.vueInstance.clearLoggingForm();
    }, 2000);
  }
}

/**
 * Auto-populate the Log QSO form in index.html with WSJT-X data
 * Directly updates the Vue instance's loggingForm
 * Vue watchers will automatically trigger QRZ and DXCC lookups
 */
function autoPopulateLogQsoForm(dxCall, dxGrid, frequency, txRst, rxRst) {
  try {
    // Access the Vue instance from the main window
    if (!window.vueInstance) {
      log('warn', 'wsjtx', 'Vue instance not available for form population');
      return;
    }

    // Clear the form to ensure no stale data from previous contact
    if (typeof window.vueInstance.clearLoggingForm === 'function') {
      window.vueInstance.clearLoggingForm();
    }

    const form = window.vueInstance.loggingForm;
    
    // Populate the form fields
    form.callsign = dxCall.toUpperCase();
    form.gridsquare = dxGrid;
    
    if (frequency) {
      form.frequency = parseFloat((frequency / 1_000_000).toFixed(3));
    }
    
    form.mode = 'FT8';
    
    // Update RST values from WSJT-X
    if (txRst) {
      form.rst_sent = txRst;
    }
    if (rxRst) {
      form.rst_received = rxRst;
    }
    
    log('info', 'wsjtx', `Form populated: ${form.callsign} @ ${form.frequency} MHz`);
    log('debug', 'wsjtx', `Grid: ${form.gridsquare}, Mode: ${form.mode}`);

    if (typeof window.vueInstance.loadQRZProfile === 'function') {
      const triggerLookup = () => {
        window.vueInstance.loadQRZProfile({
          triggerRotor: false,
          includeHistory: false
        }).catch(error => {
          log('debug', 'wsjtx', `QRZ enrichment skipped: ${error.message}`);
        });
      };

      if (typeof window.vueInstance.$nextTick === 'function') {
        window.vueInstance.$nextTick(triggerLookup);
      } else {
        setTimeout(triggerLookup, 0);
      }
    }
    
  } catch (e) {
    log('warn', 'wsjtx', 'Could not auto-populate QSO form:', e.message);
  }
}

/**
 * Clear the Log QSO form when a new contact starts
 */
function clearLogQsoForm() {
  try {
    if (!window.vueInstance) {
      log('warn', 'wsjtx', 'Vue instance not available - cannot clear form');
      return;
    }

    log('debug', 'wsjtx', 'Clearing form for new contact');
    
    if (typeof window.vueInstance.clearLoggingForm === 'function') {
      window.vueInstance.clearLoggingForm();
      log('debug', 'wsjtx', 'Form cleared');
    } else {
      log('warn', 'wsjtx', 'clearLoggingForm() not available');
    }
    
  } catch (e) {
    log('warn', 'wsjtx', 'Could not clear form:', e.message);
  }
}

/**
 * Auto-rotate antenna to DX grid
 */
function autoRotateToGrid(dxCall, dxGrid, dialFrequency) {
  try {
    // Check if auto-rotate is enabled in config
    let autoRotateEnabled = false;
    let rotorAutoMode = false;
    
    if (window.vueInstance && window.vueInstance.configData) {
      autoRotateEnabled = window.vueInstance.configData.WSJTX_AUTO_ROTATE;
      rotorAutoMode = window.vueInstance.configData.ROTOR_AUTO_ENABLED;
    }
    
    if (typeof autoRotateEnabled === 'undefined') {
      const config = window.configData || {};
      autoRotateEnabled = config.WSJTX_AUTO_ROTATE;
      rotorAutoMode = config.ROTOR_AUTO_ENABLED;
    }
    
    if (!autoRotateEnabled || !rotorAutoMode) {
      log('debug', 'rotor', 'Auto-rotate disabled');
      return;
    }

    if (!dxCall || !dxGrid || dxGrid.length < 4) {
      log('debug', 'rotor', 'Invalid call or grid for auto-rotate');
      return;
    }

    log('info', 'rotor', `Auto-rotating to ${dxCall} at ${dxGrid}`);

    fetch('/api/wsjtx/auto-rotate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        call: dxCall,
        grid: dxGrid,
        frequency_hz: dialFrequency
      })
    })
    .then(r => {
      if (!r.ok) {
        log('debug', 'rotor', `API returned ${r.status}`);
        return { success: false, reason: `HTTP ${r.status}` };
      }
      return r.json();
    })
    .then(result => {
      if (result && result.success) {
        log('info', 'rotor', `Rotation initiated: ${result.bearing}° (adjusted: ${result.adjusted_bearing}°)`);
      } else if (result) {
        log('debug', 'rotor', `Result: ${result.reason || 'No rotation'}`);
      }
    })
    .catch(e => {
      log('debug', 'rotor', `Auto-rotate skipped: ${e.message}`);
    });
  } catch (e) {
    log('debug', 'rotor', 'Could not auto-rotate:', e.message);
  }
}

/**
 * Log QSO to Wavelog if enabled
 * Combines WSJT-X data with QRZ/DXCC data that was gathered
 */
function logQsoToWavelog(loggedAdifData) {
  try {
    // Check if Wavelog integration is enabled
    if (!window.vueInstance) {
      log('warn', 'wavelog', 'Vue instance not available');
      return;
    }
    
    const isWavelogEnabled = window.vueInstance.configData?.WAVELOG_ENABLED || 
                             window.vueInstance.wavelogEnabled;
    
    if (!isWavelogEnabled) {
      log('debug', 'wavelog', 'Integration disabled - skipping auto-save');
      return;
    }

    log('info', 'wavelog', `Saving QSO: ${loggedAdifData.dxCall}`);

    // Prepare QSO data combining WSJT-X data with gathered QRZ/DXCC info
    const frequency = loggedAdifData.dialFrequency ? parseFloat((loggedAdifData.dialFrequency / 1_000_000).toFixed(3)) : null;
    
    // Use actual RST values from the LoggedAdif message (from WSJT-X)
    // In FT8/FT4, these are strings like "-12", "-09", "+15", etc. (SNR values)
    // For Wavelog API, these can be strings or numbers - Wavelog normalizes them
    const txRst = loggedAdifData.txRst || wsjtxData.txRst || '';
    const rxRst = loggedAdifData.rxRst || wsjtxData.rxRst || '';
    
    // Validate and normalize RST values
    // FT8 reports are typically in format: "-12", "+15", "R-21", etc.
    // Wavelog accepts these as-is or can use defaults if empty
    let normalizedTxRst = txRst;
    let normalizedRxRst = rxRst;
    
    // If RST is empty, leave as empty string - Wavelog API will handle it
    // If RST has value, clean up any leading "R" or "S" prefix (some WSJT-X versions add these)
    if (normalizedTxRst) {
      normalizedTxRst = String(normalizedTxRst).replace(/^[RS]/, '').trim();
    }
    if (normalizedRxRst) {
      normalizedRxRst = String(normalizedRxRst).replace(/^[RS]/, '').trim();
    }
    
    // Start with basic WSJT-X data
    const qsoData = {
      callsign: loggedAdifData.dxCall.toUpperCase(),
      frequency: frequency,
      mode: loggedAdifData.mode || 'FT8',
      rst_sent: normalizedTxRst,  // String from WSJT-X (e.g., "-12", "-09")
      rst_received: normalizedRxRst,  // String from WSJT-X (e.g., "+15", "-21")
      gridsquare: loggedAdifData.dxGrid,
      notes: `Auto-logged from WSJT-X at ${new Date().toISOString()}`
    };
    
    // If RST values are empty, log a note (this is OK for digital modes)
    if (!normalizedTxRst || !normalizedRxRst) {
      log('debug', 'wavelog', `RST values empty (normal for FT8)`);
    } else {
      log('debug', 'wavelog', `Using RST: TX=${normalizedTxRst}, RX=${normalizedRxRst}`);
    }

    // Merge QRZ profile data if available
    if (window.vueInstance.qrzProfile && window.vueInstance.qrzProfile.success) {
      const qrzData = window.vueInstance.qrzProfile;
      if (qrzData.name) qsoData.name = qrzData.name;
      if (qrzData.addr1) qsoData.qth = qrzData.addr1;
      if (qrzData.state) qsoData.state = qrzData.state;
      if (qrzData.country) qsoData.country = qrzData.country;
    }

    // Merge DXCC data if available
    if (window.vueInstance.dxccStatus && window.vueInstance.dxccStatus.success) {
      const dxccData = window.vueInstance.dxccStatus;
      if (dxccData.cqzone) qsoData.cq_zone = dxccData.cqzone;
      if (dxccData.ituzone) qsoData.itu_zone = dxccData.ituzone;
      if (dxccData.continent) qsoData.continent = dxccData.continent;
    }

    log('debug', 'wavelog', 'Sending QSO data to backend via WSJT-X endpoint for QRZ enrichment');

    // Call the WSJT-X specific endpoint which enriches with QRZ data
    fetch('/api/wsjtx/log-qso', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        call: qsoData.callsign,
        frequency_hz: (qsoData.frequency || 0) * 1_000_000,
        mode: qsoData.mode,
        grid: qsoData.gridsquare,
        rst_sent: qsoData.rst_sent,
        rst_received: qsoData.rst_received,
        operator: null  // Will use default from backend config
      })
    })
    .then(response => {
      log('debug', 'wavelog', `API Response: ${response.status} ${response.statusText}`);
      
      if (!response.ok) {
        log('error', 'wavelog', `HTTP Error ${response.status}`);
        return response.text().then(text => {
          throw new Error(`HTTP ${response.status}: ${text}`);
        });
      }
      
      return response.json();
    })
    .then(result => {
      if (result.success || result.wavelog?.success) {
        log('info', 'wavelog', 'QSO saved successfully');
        
        // Use enriched data from backend response if available, otherwise fall back to sent data
        const enrichedData = result.qso_data || qsoData;
        showWsjtxSaveModal('success', {
          callsign: enrichedData.callsign,
          frequency: enrichedData.frequency,
          mode: enrichedData.mode,
          grid: enrichedData.gridsquare,
          rst_sent: enrichedData.rst_sent,
          rst_received: enrichedData.rst_received,
          name: enrichedData.name || 'N/A',
          country: enrichedData.country || 'N/A'
        });
        
        if (window.vueInstance && window.vueInstance.clearLoggingForm) {
          setTimeout(() => {
            window.vueInstance.clearLoggingForm();
          }, 2000);
        }
      } else {
        const errorMsg = result.message || result.wavelog?.message || 'Unknown error';
        log('error', 'wavelog', `Failed to save QSO: ${errorMsg}`);
        
        showWsjtxSaveModal('error', {
          callsign: qsoData.callsign,
          message: errorMsg
        });
      }
    })
    .catch(error => {
      log('error', 'wavelog', `Error saving QSO: ${error.message}`);
      
      showWsjtxSaveModal('error', {
        callsign: qsoData.callsign,
        message: error.message
      });
    });

  } catch (e) {
    log('warn', 'wavelog', `Could not save QSO: ${e.message}`);
  }
}

/**
 * Show a beautiful modal with QSO save status
 * Auto-closes after 6 seconds or when user clicks X
 */
function showWsjtxSaveModal(status, data) {
  try {
    log('debug', 'wsjtx', 'Showing QSO save modal');

    const existingOverlay = document.getElementById('wsjtx-modal-overlay');
    if (existingOverlay?.parentNode) {
      existingOverlay.parentNode.removeChild(existingOverlay);
    }
    
    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'wsjtx-modal-overlay';
    overlay.id = 'wsjtx-modal-overlay';
    
    // Create modal content
    const modal = document.createElement('div');
    modal.className = `wsjtx-modal-content wsjtx-modal-${status}`;
    modal.id = 'wsjtx-modal-content';
    
    // Close button
    const closeBtn = document.createElement('button');
    closeBtn.className = 'wsjtx-modal-close';
    closeBtn.innerHTML = '✕';
    closeBtn.title = 'Close';
    
    // Modal title
    const title = document.createElement('div');
    title.className = 'wsjtx-modal-title';
    
    if (status === 'success') {
      title.innerHTML = '<span class="wsjtx-modal-icon">✅</span> QSO Logged Successfully!';
    } else {
      title.innerHTML = '<span class="wsjtx-modal-icon">❌</span> Failed to Log QSO';
    }
    
    // Modal body
    const body = document.createElement('div');
    body.className = 'wsjtx-modal-body';
    
    if (status === 'success') {
      // Create grid for QSO data
      const fields = document.createElement('div');
      fields.className = 'wsjtx-qso-field';
      
      // Add fields
      const addField = (label, value, fullWidth = false) => {
        const row = document.createElement('div');
        row.className = `wsjtx-qso-row ${fullWidth ? 'full' : ''}`;
        
        const labelElem = document.createElement('div');
        labelElem.className = 'wsjtx-qso-label';
        labelElem.textContent = label;
        
        const valueElem = document.createElement('div');
        valueElem.className = 'wsjtx-qso-value';
        valueElem.textContent = value;
        
        row.appendChild(labelElem);
        row.appendChild(valueElem);
        fields.appendChild(row);
      };
      
      addField('Call', data.callsign);
      addField('Frequency', `${data.frequency} MHz`);
      addField('Mode', data.mode);
      addField('Grid', data.grid || 'N/A');
      addField('RST Sent', data.rst_sent || 'N/A');
      addField('RST Rcvd', data.rst_received || 'N/A');
      
      if (data.name) {
        addField('Name', data.name, true);
      }
      
      if (data.country) {
        addField('Country', data.country, true);
      }
      
      body.appendChild(fields);
    } else {
      // Error message
      const errorField = document.createElement('div');
      errorField.className = 'wsjtx-qso-field';
      
      const callRow = document.createElement('div');
      callRow.className = 'wsjtx-qso-row full';
      const callLabel = document.createElement('div');
      callLabel.className = 'wsjtx-qso-label';
      callLabel.textContent = 'Call';
      const callValue = document.createElement('div');
      callValue.className = 'wsjtx-qso-value';
      callValue.textContent = data.callsign || 'Unknown';
      callRow.appendChild(callLabel);
      callRow.appendChild(callValue);
      errorField.appendChild(callRow);
      
      const errorRow = document.createElement('div');
      errorRow.className = 'wsjtx-qso-row full';
      const errorLabel = document.createElement('div');
      errorLabel.className = 'wsjtx-qso-label';
      errorLabel.textContent = 'Error';
      const errorValue = document.createElement('div');
      errorValue.className = 'wsjtx-qso-value';
      errorValue.textContent = data.message || 'Unknown error';
      errorRow.appendChild(errorLabel);
      errorRow.appendChild(errorValue);
      errorField.appendChild(errorRow);
      
      body.appendChild(errorField);
    }
    
    // Modal footer with timer
    const footer = document.createElement('div');
    footer.className = 'wsjtx-modal-footer';
    footer.innerHTML = 'Auto-closing in <span class="wsjtx-modal-timer">6</span>s or press ✕';
    
    // Assemble modal
    modal.appendChild(closeBtn);
    modal.appendChild(title);
    modal.appendChild(body);
    modal.appendChild(footer);
    overlay.appendChild(modal);
    
    // Add to page
    document.body.appendChild(overlay);
    
    // Timer logic
    let timeLeft = 6;
    const timerElement = footer.querySelector('.wsjtx-modal-timer');
    
    const updateTimer = () => {
      timeLeft--;
      timerElement.textContent = timeLeft;
      
      if (timeLeft <= 0) {
        closeModal();
      }
    };
    
    const timerInterval = setInterval(updateTimer, 1000);
    
    const closeModal = () => {
      clearInterval(timerInterval);
      overlay.style.animation = 'fadeOut 0.3s ease-in-out forwards';
      setTimeout(() => {
        if (overlay.parentNode) {
          overlay.parentNode.removeChild(overlay);
        }
      }, 300);
    };
    
    // Add fade-out animation
    if (!document.querySelector('style[data-wsjtx-animations]')) {
      const style = document.createElement('style');
      style.setAttribute('data-wsjtx-animations', 'true');
      style.textContent = `
        @keyframes fadeOut {
          from { opacity: 1; }
          to { opacity: 0; }
        }
      `;
      document.head.appendChild(style);
    }
    
    // Close button click handler
    closeBtn.addEventListener('click', () => {
      log('debug', 'wsjtx', 'Modal closed by user');
      closeModal();
    });
    
    // Click outside modal to close
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        closeModal();
      }
    });
    
    log('debug', 'wsjtx', 'Modal displayed - auto-close in 6 seconds');
    
  } catch (e) {
    log('error', 'wsjtx', `Error showing modal: ${e.message}`);
  }
}

/**
 * Get current WSJT-X data
 */
function getWsjtxData() {
  return wsjtxData;
}

// Export functions
window.wsjtxHandler = {
  init: initWsjtxHandler,
  handle: handleWsjtxMessage,
  getData: getWsjtxData,
  showSaveModal: showWsjtxSaveModal
};

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initWsjtxHandler);
} else {
  initWsjtxHandler();
}
