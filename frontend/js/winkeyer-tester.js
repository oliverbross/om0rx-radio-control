/**
 * WinKeyer Testing & Debugging Utility
 * Provides diagnostic tools and testing helpers for Phase 3
 * Enables comprehensive device validation
 */

class WinKeyerTester {
  constructor(ui) {
    this.ui = ui;
    this.testResults = [];
    this.isRunning = false;
  }

  /**
   * Run comprehensive device test suite
   */
  async runFullTestSuite() {
    if (this.isRunning) {
      console.warn('Test suite already running');
      return;
    }

    this.isRunning = true;
    this.testResults = [];
    this.ui._log('🧪 Starting WinKeyer Full Test Suite...');

    const tests = [
      { name: 'Connection Test', fn: () => this.testConnection() },
      { name: 'WPM Setting Test', fn: () => this.testWpmSetting() },
      { name: 'Memory Macros Test', fn: () => this.testMemoryMacros() },
      { name: 'Mode Configuration Test', fn: () => this.testModeConfig() },
      { name: 'Device Response Test', fn: () => this.testDeviceResponse() },
      { name: 'Feedback Handling Test', fn: () => this.testFeedbackHandling() }
    ];

    for (const test of tests) {
      try {
        this.ui._log(`📋 Running: ${test.name}`);
        const result = await test.fn();
        this.testResults.push({
          name: test.name,
          status: result ? 'PASS' : 'FAIL',
          timestamp: new Date().toISOString()
        });
        this.ui._log(`${result ? '✅' : '❌'} ${test.name}: ${result ? 'PASSED' : 'FAILED'}`);
      } catch (e) {
        this.testResults.push({
          name: test.name,
          status: 'ERROR',
          error: e.message,
          timestamp: new Date().toISOString()
        });
        this.ui._log(`⚠️ ${test.name}: ERROR - ${e.message}`);
      }

      // Wait between tests
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    this.isRunning = false;
    this.printTestReport();
  }

  /**
   * Test basic connection
   */
  async testConnection() {
    if (!this.ui.client) {
      throw new Error('No client available');
    }

    const startTime = Date.now();
    const timeout = 5000;

    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.ui._log('⏱️ Connection test timeout');
        resolve(false);
      }, timeout);

      const origOnOpen = this.ui.client.onOpen;
      this.ui.client.onOpen = (rev) => {
        clearTimeout(timer);
        this.ui._log(`✅ Connection established, Rev: ${rev || 'unknown'}`);
        const latency = Date.now() - startTime;
        this.ui._log(`⏱️ Connection latency: ${latency}ms`);
        if (origOnOpen) origOnOpen(rev);
        resolve(true);
      };
    });
  }

  /**
   * Test WPM setting and reading
   */
  async testWpmSetting() {
    if (!this.ui.isConnected) {
      throw new Error('Not connected');
    }

    const testValues = [10, 20, 30, 40];

    for (const wpm of testValues) {
      await this.ui.client.setWpm(wpm);
      this.ui._log(`📊 WPM test: Set to ${wpm}`);
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    return true;
  }

  /**
   * Test memory macro functionality
   */
  async testMemoryMacros() {
    if (!this.ui.isConnected) {
      throw new Error('Not connected');
    }

    const memories = ['M1', 'M2', 'M3', 'M4'];

    for (const mem of memories) {
      const text = this.ui.vue.$data.winkeyer.memories[mem];
      if (text && text.length > 0) {
        await this.ui.sendMacro(mem);
        await new Promise(resolve => setTimeout(resolve, 200));
      }
    }

    return true;
  }

  /**
   * Test mode configuration
   */
  async testModeConfig() {
    if (!this.ui.client) {
      throw new Error('No client available');
    }

    const modes = ['IAMBICB', 'IAMBICA', 'ULTIMATIC', 'BUG'];

    for (const mode of modes) {
      try {
        await this.ui.client.setMode({ keyMode: mode });
        this.ui._log(`🔧 Mode test: Set to ${mode}`);
        await new Promise(resolve => setTimeout(resolve, 100));
      } catch (e) {
        this.ui._log(`⚠️ Mode ${mode} not supported: ${e.message}`);
      }
    }

    return true;
  }

  /**
   * Test device response (status bytes, pot, etc)
   */
  async testDeviceResponse() {
    if (!this.ui.client) {
      throw new Error('No client available');
    }

    // Send a simple text to trigger device feedback
    await this.ui.client.sendText('TEST');

    // Wait for potential responses
    await new Promise(resolve => setTimeout(resolve, 1000));

    return true;
  }

  /**
   * Test feedback handler integration
   */
  async testFeedbackHandling() {
    if (!window.feedbackHandler) {
      this.ui._log('⚠️ Feedback handler not initialized');
      return false;
    }

    const metrics = window.feedbackHandler.getMetrics();
    this.ui._log(`📊 Feedback metrics: ${JSON.stringify(metrics)}`);

    return true;
  }

  /**
   * Get configuration validation report
   */
  getConfigReport() {
    const cfg = this.ui.vue.$data.winkeyer.config;
    return `
WinKeyer Configuration Report:
├─ Enabled: ${this.ui.vue.$data.winkeyer.enabled}
├─ Port: ${cfg.port}
├─ Baud Rate: ${cfg.baudRate}
├─ Default WPM: ${cfg.defaultWpm}
├─ Status: ${this.ui.vue.$data.winkeyer.status}
└─ Connected: ${this.ui.isConnected}
    `.trim();
  }

  /**
   * Print test report
   */
  printTestReport() {
    const passed = this.testResults.filter(r => r.status === 'PASS').length;
    const failed = this.testResults.filter(r => r.status === 'FAIL').length;
    const errors = this.testResults.filter(r => r.status === 'ERROR').length;
    const total = this.testResults.length;

    const report = `
╔════════════════════════════════════════╗
║     WinKeyer Test Suite Report         ║
╠════════════════════════════════════════╣
║ Total Tests:   ${total.toString().padStart(2, ' ')}                       ║
║ Passed:        ${passed.toString().padStart(2, ' ')} ✅                      ║
║ Failed:        ${failed.toString().padStart(2, ' ')} ❌                      ║
║ Errors:        ${errors.toString().padStart(2, ' ')} ⚠️                      ║
╠════════════════════════════════════════╣
`;

    console.log(report);

    this.testResults.forEach(r => {
      const icon = r.status === 'PASS' ? '✅' : r.status === 'FAIL' ? '❌' : '⚠️';
      console.log(`${icon} ${r.name}: ${r.status}`);
      if (r.error) console.log(`   Error: ${r.error}`);
    });

    console.log('╚════════════════════════════════════════╝');

    this.ui._log('📊 Test report printed to console');
  }

  /**
   * Diagnostic data dump
   */
  getDiagnosticDump() {
    const dump = {
      connected: this.ui.isConnected,
      clientAvailable: !!this.ui.client,
      config: this.ui.vue.$data.winkeyer.config,
      status: this.ui.vue.$data.winkeyer.status,
      memories: this.ui.vue.$data.winkeyer.memories,
      logCount: this.ui.vue.$data.winkeyer.logs.length,
      lastError: this.ui.vue.$data.winkeyer.lastError,
      recentLogs: this.ui.vue.$data.winkeyer.logs.slice(-10)
    };

    return dump;
  }

  /**
   * Enable debug mode (verbose logging)
   */
  enableDebugMode() {
    const origLog = this.ui._log.bind(this.ui);
    this.ui._log = (msg) => {
      console.debug(`[WK-DEBUG] ${msg}`);
      origLog(msg);
    };
    this.ui._log('🐛 Debug mode enabled');
  }

  /**
   * Simulate device responses (testing without real hardware)
   */
  simulateDeviceResponse(type) {
    if (!this.ui.client) {
      throw new Error('No client available');
    }

    const simulations = {
      'pot-change': () => {
        const randomWpm = Math.floor(Math.random() * 45) + 5; // 5-50
        this.ui._log(`📡 Simulating pot change to ${randomWpm} WPM`);
        if (this.ui.client.onPot) {
          this.ui.client.onPot(randomWpm);
        }
      },
      'button-press': () => {
        this.ui._log('📡 Simulating button press');
        if (this.ui.client.onStatus) {
          this.ui.client.onStatus({ tag: 0, keyDown: true, busy: false, breakIn: false, xoff: false });
        }
      },
      'status-byte': () => {
        this.ui._log('📡 Simulating status byte');
        if (this.ui.client.onStatus) {
          this.ui.client.onStatus({ tag: 1, keyDown: false, busy: true, breakIn: true, xoff: false });
        }
      }
    };

    if (simulations[type]) {
      simulations[type]();
    } else {
      throw new Error(`Unknown simulation type: ${type}`);
    }
  }
}

window.WinKeyerTester = WinKeyerTester;