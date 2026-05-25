# Frontend Logging Optimization Guide

## Overview

A centralized, leveled logging system has been implemented to replace scattered `console.log` calls throughout the frontend. This system provides:

✅ **Performance**: Zero overhead when debugging is disabled  
✅ **Control**: Granular filtering by log level and topic  
✅ **Smart Batching**: High-frequency events aggregated into summaries  
✅ **Change Detection**: Status updates logged only when values change  
✅ **Production Ready**: Silent in production builds by default

---

## Quick Start

### Default Behavior

By default, logging is **enabled in development** and **disabled in production**. The console shows important info and errors only.

### Enable Debug Mode

Add `?debug` to your URL to see all debug messages:

```
http://localhost:8000/?debug
```

### Filter by Log Level

Control verbosity with `?log=LEVEL`:

```
http://localhost:8000/?log=debug    # All messages
http://localhost:8000/?log=info     # Info, warn, error (default)
http://localhost:8000/?log=warn     # Warnings and errors only
http://localhost:8000/?log=error    # Errors only
```

### Filter by Topic

Show messages only from specific modules with `?topics=TOPIC1,TOPIC2`:

```
http://localhost:8000/?topics=ws,wsjtx     # WebSocket and WSJT-X only
http://localhost:8000/?topics=spots        # Spots updates only
http://localhost:8000/?topics=rotor,api    # Rotor and API calls
```

### Sample Logs (For High-Frequency Events)

Show only a percentage of logs with `?sample=0.1`:

```
http://localhost:8000/?log=debug&sample=0.1    # Show 10% of debug logs
```

---

## Available Topics

These topics are used throughout the application:

| Topic | Description |
|-------|-------------|
| `ws` | WebSocket connection and messages |
| `status` | Radio status updates |
| `spots` | DX spot reception and processing |
| `cluster` | Cluster connection status |
| `api` | API calls and responses |
| `config` | Configuration loading |
| `rotor` | Antenna rotor control |
| `wsjtx` | WSJT-X integration |
| `wavelog` | Wavelog integration |
| `sdc` | SDC Skimmer ticker |
| `init` | Module initialization |

---

## Log Levels

| Level | Priority | Use Case |
|-------|----------|----------|
| `error` | 0 (Highest) | Failures, exceptions, critical issues |
| `warn` | 1 | Deprecations, non-critical failures, retries |
| `info` | 2 | Important state changes, connections, user actions |
| `debug` | 3 (Lowest) | Detailed technical info, all parameter values |

---

## Common Scenarios

### Debugging WebSocket Issues

```
http://localhost:8000/?debug&topics=ws
```

This shows all WebSocket connection events, messages received, and commands sent.

### Tracking a Specific Contact

```
http://localhost:8000/?topics=wsjtx,wavelog
```

Shows WSJT-X auto-population and Wavelog logging operations.

### Production Support (Minimal Logging)

```
http://localhost:8000/?log=warn
```

Shows only warnings and errors—useful for identifying issues without noise.

### Performance Profiling

```
http://localhost:8000/?log=error
```

Completely silent unless something fails—good for measuring app performance.

---

## Smart Features

### Change Detection (Status Updates)

Status updates are logged **only when values change**, not on every update:

```javascript
// Before: Would log every update
// 📊 Updated radioStatus.frequency = 7040000
// 📊 Updated radioStatus.frequency = 7040000
// 📊 Updated radioStatus.frequency = 7040000

// After: Logs only actual changes
📊 Status: frequency = 7040100     // Only logs when frequency actually changed
```

### Batched Logging (Spot Updates)

High-frequency spot reception is aggregated:

```javascript
// Before: Would flood console
📡 Received spot: WE9XYZ 7040.5 kHz
📡 Received spot: K5ABC 14250.2 kHz
📡 Received spot: G3ABC 28500.1 kHz
...

// After: Summarized once per second
📡 Spots: Received 47 spots
```

### Info vs. Debug Levels

Important parameters use `info` level:
```javascript
log('info', 'status', `frequency = 7.040 MHz`);  // Visible in normal mode
log('debug', 'status', `monitor = 92`);          // Only with ?debug or ?log=debug
```

---

## For Developers

### Using the Logger in Your Code

Import the logger at the top of your module:

```javascript
import { log, batch, ChangeDetector, debugEnabled } from './logger.js';
```

### Basic Logging

```javascript
// Simple log
log('info', 'mymodule', 'Something important happened');

// With data
log('debug', 'mymodule', 'Value:', myVariable);

// With multiple arguments
log('warn', 'mymodule', 'Status is:', status, '| Code:', errorCode);
```

### Change Detection (Avoiding Repetitive Logs)

```javascript
const detector = new ChangeDetector({ frequency: 0, mode: '' });

// Check if value changed before logging
if (detector.hasChanged('frequency', newFrequency)) {
  log('info', 'status', `frequency = ${newFrequency}`);
}
```

### Batching (For High-Frequency Events)

```javascript
// Aggregate 100+ spot messages into one log per second
batch(
  'spots',           // topic
  'info',            // level
  'received',        // key (groups multiple calls)
  (items) => `Received ${items.length} spots`,
  1000,              // batch window in ms
  spotData
);
```

### Conditional Logging

```javascript
// Only log if debugging is enabled
if (debugEnabled) {
  log('debug', 'mymodule', 'Expensive debug info...');
}
```

---

## Configuration at Runtime

You can change logging settings without reloading:

```javascript
// In browser console:
window.fluxLogger?.setConfig({
  currentLevel: 'debug',
  topics: ['ws', 'wsjtx'],
  sampleRate: 0.5
});

// Or check current config:
window.fluxLogger?.getConfig();
```

---

## Best Practices

### ✅ DO

- Use `info` for important state changes (connection, frequency, mode)
- Use `debug` for detailed parameters (slider values, internal state)
- Use `error` for exceptions and failures
- Use `warn` for recoverable issues or retries
- Group related logs with the same topic
- Use batching for high-frequency events (>10/second)

### ❌ DON'T

- Use `console.log()` directly (use `log()` instead)
- Log the same message on every update (use change detection)
- Log every array item (use batching)
- Log in production (debugging is disabled automatically)
- Use `info` level for debugging details (use `debug`)

---

## Performance Impact

### With Debugging Disabled (Default in Production)

- **Impact**: ~0% overhead
- **Why**: All `log()` calls return immediately
- **Console**: Silent, no formatting or JSON operations

### With DevTools Closed

- **Impact**: ~1-2% CPU when logging at normal levels
- **Why**: No console rendering, only native V8 logging

### With DevTools Open + Debugging Enabled

- **Impact**: ~5-10% CPU depending on log volume
- **Why**: Console rendering and formatting is expensive

---

## Examples

### Example 1: Check WebSocket Connection

```
URL: http://localhost:8000/?debug&topics=ws
Expected output:
✅ WS connected at 18:42:15.234 [ws]
📤 Command: frequency [ws]
📥 Received: status [ws]
```

### Example 2: Monitor Spot Streaming

```
URL: http://localhost:8000/?topics=spots
Expected output:
📡 Spots: Received 250 spots [spots]
📡 Spots: Received 312 spots [spots]
📡 Spots: Received 198 spots [spots]
```

### Example 3: Debug WSJT-X Issues

```
URL: http://localhost:8000/?log=debug&topics=wsjtx,wavelog,rotor
Expected output:
📍 Status: G3XYZ (IO91) [wsjtx]
📝 Saving QSO: G3XYZ [wavelog]
🌐 Auto-rotating to G3XYZ at IO91 [rotor]
✅ Form populated: G3XYZ @ 3.573 MHz [wsjtx]
```

---

## Troubleshooting

### Q: I don't see any logs

**A**: Make sure:
1. DevTools console is open (press F12)
2. You're in a browser (not production build)
3. Add `?debug` to URL: `http://localhost:8000/?debug`

### Q: Too many logs flooding the console

**A**: Use filtering:
```
?log=warn                    # Only important issues
?topics=ws,api              # Specific modules only
?sample=0.1&log=debug       # 10% sample rate
```

### Q: I need to see old logs

**A**: Browser console has limited buffer. Either:
- Take a screenshot before scrolling away
- Right-click console → Save as → View in text editor
- Implement server-side logging for persistent records

### Q: How do I disable logging?

**A**: Add to config or URL:
```
?log=error                  # Only errors
```

---

## Additional Resources

- **Files Modified**: `websocket.js`, `wsjtx-handler.js`, `sdc-ticker.js`
- **New File**: `logger.js` in `frontend/js/`
- **Configuration**: URL parameters (no build configuration needed)
- **Browser Support**: All modern browsers (Chrome, Firefox, Safari, Edge)

---

**Last Updated**: 2025-11-06  
**Version**: 1.0  
**Author**: Development Team