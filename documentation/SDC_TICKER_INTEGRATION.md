# SDC Decoded CW Ticker Integration

## Overview

The FlexRadio Web Control application now includes real-time display of decoded CW text from the **SDC Skimmer** software. When the radio is in CW mode, a scrolling ticker displays decoded CW transmissions captured by SDC.

## Features

- **CW Mode Only**: The ticker appears only when `radioStatus.mode === 'CW'`
- **Real-time Updates**: Live decoded CW text from SDC Skimmer TCP broadcast
- **Connection Status**: Visual indicator showing SDC connection status (● Connected/Disconnected)
- **Auto-scrolling Ticker**: Last 10 decoded items displayed with bullet separators
- **Auto-reconnection**: Automatic reconnection with exponential backoff (max 10 attempts)
- **Green Monospace Display**: Terminal-style appearance with pulsing glow effect

## Architecture

```
┌─────────────────────────────────────────────────┐
│ SDC Skimmer (Windows/Linux)                     │
│ TCP Broadcast: 127.0.0.1:12166                  │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────v────────────────────────────────┐
│ Node.js TCP → WebSocket Bridge                  │
│ Connects to SDC TCP port                        │
│ Re-broadcasts as WebSocket msgs on :8091        │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────v────────────────────────────────┐
│ Web Application (Browser)                       │
│ ws://localhost:8091                             │
│ Displays in SDC Ticker Row (CW mode only)       │
└─────────────────────────────────────────────────┘
```

## Setup Instructions

### Step 1: Configure SDC Skimmer

1. Open SDC Skimmer application
2. Navigate to: **Global Setup** → **Misc tab**
3. Enable **"TCP Broadcast Data Port"**
4. Set port to: `12166` (or your preferred port)
5. Save configuration

### Step 2: Create Node.js TCP → WebSocket Bridge

Create a folder for the bridge application:

```bash
mkdir sdc-bridge
cd sdc-bridge
npm init -y
npm install ws
```

Create `server.js`:

```javascript
import net from 'net';
import { WebSocketServer } from 'ws';

const TCP_HOST = process.env.TCP_HOST || '127.0.0.1';
const TCP_PORT = parseInt(process.env.TCP_PORT || '12166');
const WS_PORT = parseInt(process.env.WS_PORT || '8091');

const wss = new WebSocketServer({ port: WS_PORT });
console.log(`🔌 WebSocket server ready on ws://localhost:${WS_PORT}`);

function broadcast(line) {
  const msg = JSON.stringify({ ts: Date.now(), text: line.trim() });
  for (const client of wss.clients) {
    if (client.readyState === 1) client.send(msg);
  }
}

function connectSDC() {
  console.log(`Connecting to SDC on ${TCP_HOST}:${TCP_PORT}…`);
  const client = net.createConnection({ host: TCP_HOST, port: TCP_PORT });

  client.on('connect', () => console.log('✅ Connected to SDC TCP stream'));
  client.on('data', data => {
    const lines = data.toString().split(/\r?\n/);
    lines.forEach(line => {
      if (line.trim()) broadcast(line);
    });
  });
  client.on('error', err => console.error('SDC error:', err.message));
  client.on('close', () => {
    console.log('⚠️ SDC connection closed, retrying in 5s…');
    setTimeout(connectSDC, 5000);
  });
}

connectSDC();
```

### Step 3: Start the Bridge Server

```bash
node server.js
```

Expected output:
```
🔌 WebSocket server ready on ws://localhost:8091
Connecting to SDC on 127.0.0.1:12166…
✅ Connected to SDC TCP stream
```

### Step 4: Use in Web Application

The SDC ticker will automatically:
1. Initialize on app startup
2. Attempt to connect to `ws://localhost:8091`
3. Display in a new row when radio enters CW mode
4. Show connection status (green = connected, red = disconnected)
5. Display decoded CW text as it arrives

## UI Components

### SDC Ticker Row (CW mode only)

Located between "Row 4: TX Frequency" and "Log QSO" panel:

```
┌─────────────────────────────────────────────────────────────┐
│ 📡 SDC Decoded                          ● Connected         │
├─────────────────────────────────────────────────────────────┤
│ K4ABC   •   N5DEF   •   W3GHI   •   K6JKL   •   N9MNO       │
└─────────────────────────────────────────────────────────────┘
```

### States

**Disconnected State:**
```
📡 SDC Decoded                          ● Disconnected
Connecting to SDC broadcast…
```

**No Data State:**
```
📡 SDC Decoded                          ● Connected
Listening for decoded CW…
```

**Active State:**
```
📡 SDC Decoded                          ● Connected
K4ABC   •   N5DEF   •   W3GHI   •   K6JKL   •   N9MNO
```

## Workflow: Clicking a CW Spot

1. **User clicks a CW DX spot** in the spot list
2. **Radio automatically tunes** to the spot's frequency
3. **Radio mode changes to CW**
4. **SDC ticker row appears** (v-if condition satisfied)
5. **Decoded CW text flows** into the ticker as SDC receives transmissions

## Configuration

### WebSocket Connection Parameters

- **Host**: `window.location.hostname` (auto-detected)
- **Port**: `8091` (hardcoded, can be modified in `sdc-ticker.js`)
- **URI**: `ws://localhost:8091`

### Buffer Management

- **Max Buffer Size**: 40 items (prevents memory bloat)
- **Display Items**: Last 10 items shown in ticker
- **Separator**: `   •   ` (bullet points between items)

### Reconnection Strategy

- **Initial Delay**: 3 seconds
- **Max Attempts**: 10 reconnection attempts
- **Behavior**: Automatically retries on connection loss
- **Reset**: Attempts counter resets on successful connection

## JavaScript Module Structure

### File: `frontend/js/sdc-ticker.js`

Exports `window.SDCTicker` object with:

**Data Properties:**
- `sdcConnected`: Boolean, connection status
- `sdcBuffer`: Array, decoded text buffer
- `sdcTickerContent`: String, formatted display text
- `sdcWebSocket`: WebSocket instance
- `sdcMaxBufferSize`: Buffer size limit (40)
- `sdcReconnectDelay`: Milliseconds between reconnection attempts (3000)
- `sdcReconnectAttempts`: Current attempt count
- `sdcMaxReconnectAttempts`: Maximum retry attempts (10)

**Methods:**
- `initSDCTicker()`: Initialize WebSocket connection
- `addSDCText(text)`: Add decoded text to buffer
- `updateSDCTicker()`: Update display content
- `scheduleSDCReconnect()`: Schedule reconnection attempt
- `clearSDCBuffer()`: Clear buffer and display
- `cleanupSDCTicker()`: Close WebSocket and cleanup

## Styling

### CSS Classes (in `frontend/main-styles.css`)

- `.sdc-ticker-row`: Main container
- `.sdc-ticker-header`: Title and status area
- `.sdc-ticker-title`: "📡 SDC Decoded" text
- `.sdc-connection-status`: Status indicator
- `.sdc-connection-status.connected`: Green indicator
- `.sdc-connection-status.disconnected`: Red indicator
- `.sdc-ticker-display`: Text display area
- `.sdc-ticker-message`: Status messages
- `.sdc-ticker-text`: Decoded CW text with pulsing animation
- `@keyframes sdc-pulse`: Pulsing glow effect

### Colors

- **Title**: Purple (`#9d4edd`)
- **Connected**: Bright Green (`#00ff00`)
- **Disconnected**: Red (`#ff4444`)
- **Text**: Bright Green (`#00ff00`)
- **Background**: Dark gradient

## Troubleshooting

### SDC Ticker Shows "Disconnected"

**Possible Causes:**

1. **Node.js bridge not running**
   - Start the bridge: `node server.js`
   - Check port 8091 is not in use: `lsof -i :8091` (Unix) or `netstat -ano | findstr :8091` (Windows)

2. **SDC Skimmer not broadcasting**
   - Verify SDC is configured with TCP Broadcast enabled
   - Check port 12166 is correct in bridge configuration
   - Restart SDC Skimmer

3. **Firewall blocking**
   - Allow port 8091 on localhost
   - Windows: `netsh advfirewall firewall add rule name="SDC Bridge" dir=in action=allow program="node.exe" protocol=tcp localport=8091`

4. **Wrong hostname**
   - Ensure bridge is accessible at `localhost:8091`
   - Try from another browser tab: `webSocket = new WebSocket('ws://localhost:8091')`

### No Decoded Text Appearing

**Possible Causes:**

1. **SDC not receiving signals**
   - Verify SDC Skimmer is running and receiving CW transmissions
   - Check radio antenna connection
   - Monitor SDC application directly

2. **Radio not in CW mode**
   - Switch to CW mode
   - Verify `radioStatus.mode === 'CW'` in browser console

3. **Bridge not receiving from SDC**
   - Check SDC Broadcast output is active
   - Monitor bridge console for incoming data

### Excessive Reconnection Attempts

The ticker will stop attempting reconnection after 10 failed attempts to prevent resource drain.

**Recovery:**
- Restart Node.js bridge server
- Restart web browser
- Reload web application

## Browser Console Debugging

Check browser console (F12 → Console tab) for:

```javascript
// Check module loaded
window.SDCTicker ? '✅' : '❌'

// Check data properties
this.$data.sdcConnected
this.$data.sdcBuffer
this.$data.sdcTickerContent

// Check WebSocket status
window.SDCTicker.sdcWebSocket?.readyState
// 0 = CONNECTING, 1 = OPEN, 2 = CLOSING, 3 = CLOSED

// Manual reconnect
this.initSDCTicker()

// Clear buffer
this.clearSDCBuffer()
```

## Performance Considerations

- **Buffer Limit**: Maximum 40 items prevents unlimited memory growth
- **Display Update**: Only last 10 items rendered (efficient DOM updates)
- **Auto-scroll**: Lazy-loaded via `$nextTick()` to prevent layout thrashing
- **Reconnection**: Exponential backoff prevents connection spam

## Future Enhancements

Potential additions:
- [ ] Configurable buffer size via UI settings
- [ ] Export decoded CW to log file
- [ ] CW text filtering/search
- [ ] Statistics (callsigns per minute, most active frequencies)
- [ ] Sound notification on incoming transmissions
- [ ] Integration with QSO logging (auto-detect callsigns)

## Files Modified

- `frontend/index.html` - Added SDC ticker row HTML
- `frontend/main-styles.css` - Added SDC ticker styles
- `frontend/js/sdc-ticker.js` - New SDC module (created)
- `frontend/js/app-main.js` - Integrated SDC module into Vue app

## Related Documentation

- `sdc_integration_guide.doc` - Original integration guide (from ChatGPT)
- FlexRadio Web Control Architecture
- Vue.js 3 Documentation (for extending the ticker)

---

**Version**: 1.0  
**Date**: 2025-01-15  
**Author**: Integration into FlexRadio Web Control