/**
 * WinKeyer Device Feedback Handler
 * Processes potentiometer, button, and status messages
 * Enables Phase 3: Device Integration & Testing
 */

class WinKeyerFeedbackHandler {
  constructor(ui) {
    this.ui = ui;
    this.feedbackMetrics = {
      potUpdates: 0,
      buttonPresses: 0,
      statusUpdates: 0,
      extendedMessages: 0,
      echoChars: 0,
      errors: 0,
      lastPotValue: null,
      lastButtonState: null,
      lastStatusByte: null
    };
    this.potDebounceTimer = null;
    this.potDebounceMs = 100; // Debounce pot updates by 100ms
    this.lastPotReportedValue = null;
  }

  /**
   * Handle potentiometer feedback (real-time WPM adjustment)
   * The hardware pot is the primary speed control - simply mirror it in the UI
   */
  handlePotentiometerChange(wpm) {
    this.feedbackMetrics.potUpdates++;
    this.feedbackMetrics.lastPotValue = wpm;

    // Debounce rapid pot changes
    if (this.potDebounceTimer) {
      clearTimeout(this.potDebounceTimer);
    }

    this.potDebounceTimer = setTimeout(() => {
      // Only update if value actually changed
      if (wpm !== this.lastPotReportedValue) {
        this.lastPotReportedValue = wpm;
        this.ui._log(`🎚️ Potentiometer: ${wpm} WPM`);
        
        // Update UI only - let hardware pot be the primary control
        if (this.ui.vue.$data.winkeyer) {
          this.ui.vue.$data.winkeyer.currentWpm = wpm;
        }
        // Note: Do NOT call setWpm() immediately to avoid lag - hardware pot drives the speed
      }
    }, this.potDebounceMs);
  }

  /**
   * Handle physical button/paddle feedback
   */
  handleButtonFeedback(status) {
    const { keyDown, breakIn, xoff, busy, rawByte } = status;

    // Debug: log all statuses
    console.log(`[WK-FEEDBACK] handleButtonFeedback called: keyDown=${keyDown}, rawByte=0x${rawByte?.toString(16).padStart(2, '0')}, lastState=${this.feedbackMetrics.lastButtonState ? JSON.stringify(this.feedbackMetrics.lastButtonState).substring(0, 50) : 'null'}`);

    // Detect button press (transition from up to down)
    const wasDown = this.feedbackMetrics.lastButtonState?.keyDown;
    console.log(`[WK-FEEDBACK] wasDown=${wasDown}, keyDown=${keyDown}, condition=${keyDown && !wasDown}`);
    
    if (keyDown && !wasDown) {
      this.feedbackMetrics.buttonPresses++;
      
      // Identify which button was pressed by the unique status byte signature
      const buttonNum = this._identifyButton(rawByte, breakIn, xoff, busy);
      console.log(`[WK-FEEDBACK] Button identified as: ${buttonNum}`);
      
      if (buttonNum) {
        this.ui._log(`🔘 Button ${buttonNum} pressed - triggering M${buttonNum}`);
        // Trigger the corresponding macro
        this.ui.sendMacro(`M${buttonNum}`).catch(e => {
          this.ui._log(`❌ Failed to send M${buttonNum}: ${e.message}`);
        });
      } else {
        this.ui._log(`🔘 Button/Paddle pressed (unrecognized signature: 0x${rawByte?.toString(16).padStart(2, '0')})`);
      }
    }

    this.feedbackMetrics.lastButtonState = { keyDown, breakIn, xoff, busy, rawByte };
  }

  /**
   * Identify which button (1-4) was pressed based on status byte signature
   * Button signatures from hardware testing:
   * Button 1: 0xc9 (xoff=true)
   * Button 2: 0xca (breakIn=true)
   * Button 3: 0xcc (busy=true)
   * Button 4: 0xd8
   */
  _identifyButton(rawByte, breakIn, xoff, busy) {
    if (!rawByte) return null;
    
    switch (rawByte) {
      case 0xc9: // Button 1: xoff=true signature
        return 1;
      case 0xca: // Button 2: breakIn=true signature
        return 2;
      case 0xcc: // Button 3: busy=true signature
        return 3;
      case 0xd8: // Button 4: unique signature
        return 4;
      default:
        return null;
    }
  }

  /**
   * Handle status byte feedback
   */
  handleStatusFeedback(status) {
    this.feedbackMetrics.statusUpdates++;
    this.feedbackMetrics.lastStatusByte = status;

    const { tag, keyDown, busy, breakIn, xoff } = status;

    // Build status description
    let statusDesc = [];
    if (keyDown) statusDesc.push('KEY_DOWN');
    if (busy) statusDesc.push('BUSY');
    if (breakIn) statusDesc.push('BREAK_IN');
    if (xoff) statusDesc.push('XOFF');

    if (statusDesc.length > 0) {
      this.ui._log(`📊 Status: [${statusDesc.join(',')}]`);
    }
  }

  /**
   * Handle extended message feedback (paddler positions, sidetone, etc)
   */
  handleExtendedFeedback(extended) {
    this.feedbackMetrics.extendedMessages++;

    const { paddleLeft, paddleRight, wpm, sidetone, flags } = extended;

    let paddleStatus = [];
    if (paddleLeft) paddleStatus.push('LEFT_PADDLE');
    if (paddleRight) paddleStatus.push('RIGHT_PADDLE');

    this.ui._log(
      `🔧 Extended: [${paddleStatus.join(',')}] WPM=${wpm} Sidetone=${sidetone}Hz`
    );
  }

  /**
   * Handle echo character feedback
   */
  handleEchoCharacter(ch) {
    this.feedbackMetrics.echoChars++;
    this.ui._log(`🔊 Echo: '${ch}'`);
  }

  /**
   * Handle device error
   */
  handleDeviceError(error) {
    this.feedbackMetrics.errors++;
    this.ui._log(`⚠️ Device Error: ${error.message}`);
  }

  /**
   * Get feedback metrics/statistics
   */
  getMetrics() {
    return {
      ...this.feedbackMetrics,
      uptime: this.getUptimeMs()
    };
  }

  /**
   * Get uptime since last reset
   */
  getUptimeMs() {
    if (!this.ui.isConnected) return 0;
    // Would need to track connection time separately
    return 0;
  }

  /**
   * Reset metrics
   */
  resetMetrics() {
    this.feedbackMetrics = {
      potUpdates: 0,
      buttonPresses: 0,
      statusUpdates: 0,
      extendedMessages: 0,
      echoChars: 0,
      errors: 0,
      lastPotValue: null,
      lastButtonState: null,
      lastStatusByte: null
    };
    this.lastPotReportedValue = null;
    this.ui._log('📊 Feedback metrics reset');
  }

  /**
   * Get formatted metrics report
   */
  getMetricsReport() {
    const m = this.getMetrics();
    return `
WinKeyer Feedback Metrics:
├─ Potentiometer Updates: ${m.potUpdates}
├─ Button Presses: ${m.buttonPresses}
├─ Status Updates: ${m.statusUpdates}
├─ Extended Messages: ${m.extendedMessages}
├─ Echo Characters: ${m.echoChars}
├─ Device Errors: ${m.errors}
├─ Last Pot Value: ${m.lastPotValue}
└─ Uptime: ${(m.uptime / 1000).toFixed(1)}s
    `.trim();
  }
}

window.WinKeyerFeedbackHandler = WinKeyerFeedbackHandler;
console.log('[WK-FEEDBACK] Class exported to window.WinKeyerFeedbackHandler:', typeof window.WinKeyerFeedbackHandler);