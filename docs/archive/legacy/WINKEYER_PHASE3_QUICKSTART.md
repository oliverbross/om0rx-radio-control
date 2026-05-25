# WinKeyer Phase 3: Quick Start Guide
**One-minute setup & testing reference**

---

## 🚀 5-Second Start

```javascript
// Open browser console (F12)
// Copy-paste one of these:

// 1. Check everything is loaded
console.log('✅ All modules ready:', !!window.winKeyerTester);

// 2. Connect device
winKeyerUI.connect();

// 3. Run full test
await window.winKeyerTester.runFullTestSuite();

// 4. See device feedback
window.feedbackHandler.getMetricsReport();

// 5. Check auto-reconnect
window.winKeyerUI.reconnectManager.getStats();
```

---

## 🔌 Connection Flow

```
1. Connect USB Cable → Device Ready
2. Click Config → Enable WinKeyer ✓
3. Set Port (COM3), Baud (1200), WPM (20) ✓
4. Click "Connect" in Widget
5. Watch 🟢 Connected appear
6. Device responds automatically to pot/buttons
```

---

## 📊 Real-Time Dashboard

```javascript
// One command to see everything:
setInterval(() => {
  const ui = window.winKeyerUI;
  const fb = window.feedbackHandler;
  const rc = ui.reconnectManager;
  console.clear();
  console.log('Connected:', ui.isConnected ? '✅' : '❌');
  console.log('POT updates:', fb.getMetrics().potUpdates);
  console.log('Button presses:', fb.getMetrics().buttonPresses);
  console.log('Status updates:', fb.getMetrics().statusUpdates);
  console.log('Reconnect attempts:', rc.getStats().connectionAttempts);
}, 5000);
```

---

## 🧪 Quick Tests

### Test 1: Potentiometer
```javascript
// Adjust physical pot on device
fb.getMetrics().potUpdates  // Should increase
```

### Test 2: Button Press
```javascript
// Press paddle/button on device
fb.getMetrics().buttonPresses  // Should increase
```

### Test 3: Connection Lost
```javascript
// Unplug USB cable
// Watch logs: 🔄 Reconnection attempt 1/5 (waiting 1000ms)
// Plug back in
// Should reconnect automatically
```

### Test 4: Full Suite
```javascript
await window.winKeyerTester.runFullTestSuite();
// Shows: ✅ 6/6 tests passed
```

### Test 5: Speed Change
```javascript
// Change WPM slider in config
winKeyerUI.setWpm(30);
// Should update device instantly
```

---

## 🔄 Auto-Reconnect Demo

```javascript
// Manual trigger
winKeyerUI.reconnectManager.startAutoReconnect();

// Watch in console - should show:
// 🔄 Reconnection attempt 1/5 (waiting 1000ms)
// 🔄 Reconnection attempt 2/5 (waiting 2000ms)
// ... up to 5 attempts with backoff

// Stop reconnection
winKeyerUI.reconnectManager.stopAutoReconnect();
```

---

## 📈 Performance Metrics

```javascript
// Get all metrics at once
const metrics = {
  feedback: window.feedbackHandler.getMetrics(),
  reconnect: window.winKeyerUI.reconnectManager.getStats(),
  config: window.winKeyerUI.vue.$data.winkeyer.config,
  connected: window.winKeyerUI.isConnected,
  connectionTime: window.winKeyerUI.connectionStartTime
};
console.table(metrics);
```

---

## 🐛 Debug Mode

```javascript
// Enable verbose logging
window.winKeyerTester.enableDebugMode();

// Get diagnostics
const dump = window.winKeyerTester.getDiagnosticDump();
console.log(JSON.stringify(dump, null, 2));

// Get configuration
window.winKeyerTester.getConfigReport();
```

---

## ❌ Quick Troubleshooting

| Issue | Fix |
|-------|-----|
| No 🟢 Connected | Check USB cable, device on, correct COM port |
| No pot updates | Physical pot working? Check device sending data |
| Reconnect fails | Verify port is correct, device reachable |
| Tests timeout | Device might be disconnected or unresponsive |
| Memory full warning | Clear logs: `winKeyerUI.vue.$data.winkeyer.logs = []` |

---

## 💡 Pro Tips

1. **Live monitoring**: Pin a terminal window with this code:
   ```javascript
   setInterval(() => {
     console.clear();
     console.log(window.feedbackHandler.getMetricsReport());
   }, 10000);
   ```

2. **Test without hardware**: 
   ```javascript
   window.winKeyerTester.simulateDeviceResponse('pot-change');
   ```

3. **Export logs**: 
   ```javascript
   copy(window.winKeyerUI.vue.$data.winkeyer.logs.join('\n'))
   ```

4. **Check all memories**:
   ```javascript
   console.table(window.winKeyerUI.vue.$data.winkeyer.memories);
   ```

5. **Monitor connection in real-time**:
   ```javascript
   new MutationObserver(() => {
     console.log('Status changed to:', winKeyerUI.vue.$data.winkeyer.status);
   }).observe(document.body, { subtree: true, characterData: true });
   ```

---

## 📋 Testing Checklist

- [ ] Modules loaded (run `console.log(window.winKeyerTester ? '✅' : '❌')`)
- [ ] Device connected (🟢 indicator shows)
- [ ] Connection time recorded
- [ ] Pot updates when adjusted
- [ ] Buttons tracked when pressed
- [ ] Status messages logged
- [ ] Test suite passes
- [ ] Auto-reconnect works (unplug USB, watch logs)
- [ ] Reconnect succeeds (plug USB back in)
- [ ] No memory leaks after 5 minutes

---

## 🎯 Expected Output Examples

### Connected State
```
Status: 🟢 Connected
Pot updates: 42
Button presses: 12
Status updates: 156
Extended messages: 8
Echo characters: 234
```

### Auto-Reconnect Logs
```
🔄 Starting auto-reconnect sequence...
🔄 Reconnection attempt 1/5 (waiting 1000ms)
⏳ Attempting connection (attempt 1)...
⚠️ Device error: Connection timeout
❌ Attempt 1 failed: Connection timeout
🔄 Reconnection attempt 2/5 (waiting 2000ms)
...
✅ Reconnected successfully after 3 attempts
```

### Test Suite Results
```
╔════════════════════════════════════════╗
║     WinKeyer Test Suite Report         ║
╠════════════════════════════════════════╣
║ Total Tests:     6                     ║
║ Passed:          6 ✅                  ║
║ Failed:          0 ❌                  ║
║ Errors:          0 ⚠️                  ║
╚════════════════════════════════════════╝
✅ Connection Test: PASSED
✅ WPM Setting Test: PASSED
✅ Memory Macros Test: PASSED
✅ Mode Configuration Test: PASSED
✅ Device Response Test: PASSED
✅ Feedback Handling Test: PASSED
```

---

## ⚡ One-Liner Commands

```javascript
// Copy any of these directly into console:

// See if everything is working
console.log(Object.keys(window).filter(k => k.includes('winkeyer')).join(', '))

// Quick status
console.log(`Connected: ${window.winKeyerUI.isConnected}, Pot updates: ${window.feedbackHandler.getMetrics().potUpdates}`)

// Auto-reconnect stats
console.table(window.winKeyerUI.reconnectManager.getStats())

// Recent logs
console.log(window.winKeyerUI.vue.$data.winkeyer.logs.slice(-5).join('\n'))

// Export all config
copy(JSON.stringify(window.winKeyerUI.vue.$data.winkeyer, null, 2))

// Clear all logs
window.winKeyerUI.vue.$data.winkeyer.logs = []
```

---

**That's it! You're ready to test Phase 3! 🚀**

For detailed information, see: `WINKEYER_PHASE3_COMPLETE.md`