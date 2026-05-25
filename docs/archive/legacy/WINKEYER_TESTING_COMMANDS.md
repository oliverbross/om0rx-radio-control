# 🧪 WinKeyer Phase 3 - Testing Commands Reference

**Copy & paste these directly into your browser console (F12)**

---

## ✅ Verification Commands

### Check Phase 3 is Loaded
```javascript
console.log({
  reconnect: !!window.WinKeyerReconnectManager,
  feedback: !!window.WinKeyerFeedbackHandler,
  tester: !!window.WinKeyerTester,
  instances: {
    ui: !!window.winKeyerUI,
    feedbackHandler: !!window.feedbackHandler,
    tester: !!window.winKeyerTester
  }
});
// Expected: All should be true ✅
```

### Quick System Check
```javascript
console.log(`
✅ QUICK STATUS CHECK
Connected: ${window.winKeyerUI.isConnected ? '🟢 YES' : '🔴 NO'}
Module: ${window.winKeyerTester ? '🟢 LOADED' : '🔴 MISSING'}
Config: ${window.winKeyerUI.vue.$data.winkeyer.enabled ? '✅ ENABLED' : '❌ DISABLED'}
`);
```

---

## 🔌 Connection Commands

### Connect to Device
```javascript
winKeyerUI.connect();
// Watch console for: ✅ Connected! WK Rev: [number]
```

### Disconnect
```javascript
winKeyerUI.disconnect();
// Watch console for: ✅ Disconnected
```

### Check Connection Status
```javascript
console.log({
  connected: winKeyerUI.isConnected,
  status: winKeyerUI.vue.$data.winkeyer.status,
  connectionTime: winKeyerUI.connectionStartTime,
  port: winKeyerUI.vue.$data.winkeyer.config.port,
  baudRate: winKeyerUI.vue.$data.winkeyer.config.baudRate
});
```

### View Recent Logs
```javascript
winKeyerUI.vue.$data.winkeyer.logs.slice(-10).forEach(log => console.log(log));
```

---

## 📊 Feedback Monitoring

### Get All Feedback Metrics
```javascript
window.feedbackHandler.getMetrics();
// Returns: {
//   potUpdates: number,
//   buttonPresses: number,
//   statusUpdates: number,
//   extendedMessages: number,
//   echoChars: number,
//   errors: number,
//   lastPotValue: number,
//   ...
// }
```

### Print Formatted Report
```javascript
console.log(window.feedbackHandler.getMetricsReport());
// Output:
// WinKeyer Feedback Metrics:
// ├─ Potentiometer Updates: 42
// ├─ Button Presses: 12
// ├─ Status Updates: 156
// ...
```

### Reset Metrics
```javascript
window.feedbackHandler.resetMetrics();
// Clears all counters for fresh test
```

### Monitor Pot Updates Only
```javascript
const initial = window.feedbackHandler.getMetrics().potUpdates;
console.log(`Pot updates: ${initial}`);
setTimeout(() => {
  const final = window.feedbackHandler.getMetrics().potUpdates;
  console.log(`Pot updates changed by: ${final - initial} (move pot to increase)`);
}, 5000);
```

### Monitor Button Presses
```javascript
const initial = window.feedbackHandler.getMetrics().buttonPresses;
console.log('Press button/paddle, this will update:');
setInterval(() => {
  const now = window.feedbackHandler.getMetrics().buttonPresses;
  console.log(`Button presses: ${now - initial}`);
}, 1000);
```

---

## 🔄 Auto-Reconnect Testing

### Start Auto-Reconnect
```javascript
window.winKeyerUI.reconnectManager.startAutoReconnect();
// Watch console for: 🔄 Reconnection attempt X/5 (waiting Xms)
```

### Stop Auto-Reconnect
```javascript
window.winKeyerUI.reconnectManager.stopAutoReconnect();
```

### Check Reconnect Status
```javascript
window.winKeyerUI.reconnectManager.getStats();
// Returns: {
//   isRetrying: boolean,
//   retryCount: number,
//   maxRetries: 5,
//   connectionAttempts: number,
//   failureReason: string,
//   lastSuccessfulConnection: Date,
//   autoReconnectEnabled: boolean
// }
```

### Watch Reconnect Attempts in Real-Time
```javascript
setInterval(() => {
  const stats = window.winKeyerUI.reconnectManager.getStats();
  console.clear();
  console.log('Reconnect Status:', stats);
  if (!stats.isRetrying) {
    console.log('✅ Not retrying');
  }
}, 2000);
```

---

## 🧪 Test Suite Commands

### Run Full Test Suite (All 6 Tests)
```javascript
await window.winKeyerTester.runFullTestSuite();
// Takes ~10 seconds
// Watch for: ✅ ALL TESTS PASSED or ❌ SOME FAILED
```

### Get Configuration Report
```javascript
console.log(window.winKeyerTester.getConfigReport());
// Output:
// WinKeyer Configuration Report:
// ├─ Enabled: true
// ├─ Port: COM3
// ├─ Baud Rate: 1200
// ├─ Default WPM: 20
// ├─ Status: 🟢 Connected
// └─ Connected: true
```

### Get Diagnostic Dump
```javascript
const dump = window.winKeyerTester.getDiagnosticDump();
console.log(JSON.stringify(dump, null, 2));
// Shows detailed debugging information
```

### Enable Debug Mode (Verbose Logging)
```javascript
window.winKeyerTester.enableDebugMode();
// All subsequent logs will include [WK-DEBUG] prefix
```

---

## 🎮 Simulation Commands (No Hardware Needed)

### Simulate Potentiometer Change
```javascript
window.winKeyerTester.simulateDeviceResponse('pot-change');
// Simulates random WPM value (5-50)
```

### Simulate Button Press
```javascript
window.winKeyerTester.simulateDeviceResponse('button-press');
// Simulates button press event
```

### Simulate Status Byte
```javascript
window.winKeyerTester.simulateDeviceResponse('status-byte');
// Simulates device status update
```

### Multiple Simulations
```javascript
// Simulate rapid pot changes
for (let i = 0; i < 10; i++) {
  window.winKeyerTester.simulateDeviceResponse('pot-change');
  await new Promise(r => setTimeout(r, 100));
}
// Then check metrics:
console.log(`Pot updates: ${window.feedbackHandler.getMetrics().potUpdates}`);
```

---

## 🎚️ Manual Control Commands

### Change WPM
```javascript
winKeyerUI.setWpm(30);  // Set to 30 WPM
winKeyerUI.setWpm(15);  // Set to 15 WPM (minimum 5, maximum 50)
```

### Send Memory
```javascript
winKeyerUI.sendMacro('M1');  // Send memory 1
winKeyerUI.sendMacro('M2');  // Send memory 2
winKeyerUI.sendMacro('M3');  // Send memory 3
winKeyerUI.sendMacro('M4');  // Send memory 4
```

### Check Memory Contents
```javascript
console.table(winKeyerUI.vue.$data.winkeyer.memories);
// Shows M1, M2, M3, M4 contents
```

### Update Memory
```javascript
winKeyerUI.updateMemory('M1', 'CQ DE OM0RX K');
winKeyerUI.updateMemory('M2', 'UR RST 599 QSL');
```

---

## 📈 Performance Monitoring

### One-Page Status Dashboard
```javascript
setInterval(() => {
  const ui = window.winKeyerUI;
  const fb = window.feedbackHandler;
  const rc = ui.reconnectManager;
  
  console.clear();
  console.log('═══ WinKeyer Status ═══');
  console.log('Connected:', ui.isConnected ? '✅' : '❌');
  console.log('Status:', ui.vue.$data.winkeyer.status);
  console.log('');
  console.log('─── Feedback Metrics ───');
  console.log('POT Updates:', fb.getMetrics().potUpdates);
  console.log('Button Presses:', fb.getMetrics().buttonPresses);
  console.log('Status Updates:', fb.getMetrics().statusUpdates);
  console.log('');
  console.log('─── Reconnect Stats ───');
  console.log('Attempts:', rc.getStats().connectionAttempts);
  console.log('Retrying:', rc.getStats().isRetrying);
  console.log('');
}, 3000);
```

### Memory Usage Check
```javascript
console.log({
  logsCount: winKeyerUI.vue.$data.winkeyer.logs.length,
  logsMaxSize: 50,
  recentMemory: performance.memory ? {
    used: (performance.memory.usedJSHeapSize / 1048576).toFixed(2) + ' MB',
    limit: (performance.memory.jsHeapSizeLimit / 1048576).toFixed(2) + ' MB'
  } : 'N/A'
});
```

---

## 🔧 Troubleshooting Commands

### Check for JavaScript Errors
```javascript
// Look for any errors in console (should be none)
console.error('Checking for errors...');
```

### Validate All Modules
```javascript
const modules = {
  WinKeyerClient: typeof window.WinKeyerClient,
  WinKeyerReconnectManager: typeof window.WinKeyerReconnectManager,
  WinKeyerFeedbackHandler: typeof window.WinKeyerFeedbackHandler,
  WinKeyerTester: typeof window.WinKeyerTester,
  WinKeyerUI: typeof window.WinKeyerUI
};
console.table(modules);
// All should be 'function'
```

### Export Logs to Text File
```javascript
const logs = winKeyerUI.vue.$data.winkeyer.logs;
const text = logs.join('\n');
const blob = new Blob([text], { type: 'text/plain' });
const url = URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = 'winkeyer-logs-' + new Date().toISOString() + '.txt';
a.click();
// Downloads logs as file
```

### Clear All Logs
```javascript
winKeyerUI.vue.$data.winkeyer.logs = [];
console.log('Logs cleared');
```

### Reset All State
```javascript
winKeyerUI.disconnect();
setTimeout(() => {
  winKeyerUI.vue.$data.winkeyer = {
    enabled: true,
    isConnected: false,
    currentWpm: 20,
    showWpmSlider: false,
    memories: {
      M1: 'CQ DE OM0RX',
      M2: 'UR RST 599',
      M3: 'QSL TU DE OM0RX',
      M4: 'MNI TU'
    },
    status: 'Disconnected',
    logs: [],
    lastError: null,
    connectionTime: null,
    config: {
      port: 'COM3',
      baudRate: 1200,
      defaultWpm: 20
    }
  };
  console.log('State reset');
}, 500);
```

---

## 🎯 Test Scenarios

### Scenario 1: Basic Connection (5 min)
```javascript
// 1. Connect
winKeyerUI.connect();

// 2. Wait for: ✅ Connected! WK Rev: [number]

// 3. Verify
console.log(winKeyerUI.isConnected);  // Should be true

// 4. Check config loaded
console.log(winKeyerUI.vue.$data.winkeyer.status);
```

### Scenario 2: Device Feedback (10 min)
```javascript
// 1. Connect
winKeyerUI.connect();

// 2. Get initial metrics
const start = window.feedbackHandler.getMetrics();

// 3. Interact with device
// - Adjust physical pot on keyer
// - Press buttons/paddles

// 4. Check updated metrics (5 seconds later)
const end = window.feedbackHandler.getMetrics();
console.log({
  potIncreased: end.potUpdates > start.potUpdates,
  buttonPresses: end.buttonPresses - start.buttonPresses,
  statusUpdates: end.statusUpdates - start.statusUpdates
});
```

### Scenario 3: Auto-Reconnect (15 min)
```javascript
// 1. Connect device first
winKeyerUI.connect();

// 2. Verify connected
console.log('Connected:', winKeyerUI.isConnected);

// 3. Unplug USB cable from device

// 4. Watch logs for reconnection attempts:
// 🔄 Reconnection attempt 1/5 (waiting 1000ms)
// 🔄 Reconnection attempt 2/5 (waiting 2000ms)
// etc.

// 5. Plug USB back in

// 6. Verify reconnects: ✅ Reconnected successfully

// 7. Check stats
console.log(winKeyerUI.reconnectManager.getStats());
```

### Scenario 4: Full Test Suite (10 min)
```javascript
// Make sure device is connected first
console.log('Connected:', winKeyerUI.isConnected);

// Run suite
await window.winKeyerTester.runFullTestSuite();

// Check results printed to console
// Should see all 6 tests passing ✅
```

---

## 💡 Pro Tips

### Tip 1: Copy Logs to Clipboard
```javascript
copy(window.winKeyerUI.vue.$data.winkeyer.logs.join('\n'));
// Now paste anywhere with Ctrl+V
```

### Tip 2: Watch a Single Metric
```javascript
let lastPot = 0;
const watch = setInterval(() => {
  const pot = window.feedbackHandler.getMetrics().potUpdates;
  if (pot !== lastPot) {
    console.log(`Pot updates: ${pot}`);
    lastPot = pot;
  }
}, 100);
// Stop with: clearInterval(watch);
```

### Tip 3: Benchmark a Command
```javascript
console.time('Connect');
await winKeyerUI.connect();
console.timeEnd('Connect');
```

### Tip 4: Table Format for Metrics
```javascript
console.table({
  'POT Updates': window.feedbackHandler.getMetrics().potUpdates,
  'Button Presses': window.feedbackHandler.getMetrics().buttonPresses,
  'Status Updates': window.feedbackHandler.getMetrics().statusUpdates,
  'Echo Chars': window.feedbackHandler.getMetrics().echoChars,
  'Errors': window.feedbackHandler.getMetrics().errors
});
```

### Tip 5: JSON Export
```javascript
const state = JSON.stringify(winKeyerUI.vue.$data.winkeyer, null, 2);
console.log(state);
// Copy to paste into bug reports
```

---

## 📞 Quick Reference

| Command | Purpose |
|---------|---------|
| `winKeyerUI.connect()` | Connect to device |
| `winKeyerUI.disconnect()` | Disconnect |
| `feedbackHandler.getMetricsReport()` | See feedback stats |
| `await winKeyerTester.runFullTestSuite()` | Run 6 tests |
| `winKeyerTester.getConfigReport()` | Check config |
| `winKeyerUI.reconnectManager.getStats()` | Reconnect status |
| `winKeyerUI.setWpm(20)` | Change speed |
| `winKeyerUI.sendMacro('M1')` | Send memory |
| `winKeyerTester.enableDebugMode()` | Verbose logging |
| `console.clear()` | Clear console |

---

**Ready to test? Paste commands above directly into browser console (F12) and watch the magic happen! 🚀**
