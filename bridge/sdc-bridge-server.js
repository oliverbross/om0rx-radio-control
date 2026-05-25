// Multi-Protocol Bridge Server (SDC Skimmer + WSJT-X)
// 
// This server:
// 1. Connects to SDC Skimmer's TCP broadcast port (default: 12166)
// 2. Listens for WSJT-X UDP packets (default: 2237)
// 3. Re-broadcasts both as WebSocket messages
//
// Setup:
//   npm init -y
//   npm install
//   node sdc-bridge-server.js
//
// Environment variables:
//   TCP_HOST          - SDC host (default: 127.0.0.1)
//   TCP_PORT          - SDC broadcast port (default: 12166)
//   WSJTX_UDP_PORT    - WSJT-X UDP port (default: 2237)
//   WSJTX_UDP_MULTICAST - WSJT-X multicast address (default: 224.0.0.1)
//   WS_PORT           - WebSocket server port (default: 8091 for combined)
//
// Example:
//   TCP_HOST=192.168.1.100 WSJTX_UDP_PORT=2237 WS_PORT=8091 node sdc-bridge-server.js

import net from 'net';
import dgram from 'dgram';
import os from 'os';
import { WebSocketServer } from 'ws';
import { WsjtxParser } from './wsjtx-parser.js';

// Configuration from environment or defaults
const TCP_HOST = process.env.TCP_HOST || '127.0.0.1';
const TCP_PORT = parseInt(process.env.TCP_PORT || '12166');
const WSJTX_UDP_PORT = parseInt(process.env.WSJTX_UDP_PORT || '2237');
const WSJTX_UDP_MULTICAST = process.env.WSJTX_UDP_MULTICAST || '224.0.0.1';
const WS_PORT = parseInt(process.env.WS_PORT || '8091');
const WSJTX_ENABLED = process.env.WSJTX_ENABLED !== 'false';

// Create WebSocket server
const wss = new WebSocketServer({ port: WS_PORT });
console.log(`🔌 WebSocket server started on ws://localhost:${WS_PORT}`);
console.log(`📡 SDC Skimmer bridge: tcp://${TCP_HOST}:${TCP_PORT}`);
if (WSJTX_ENABLED) console.log(`📡 WSJT-X UDP listener: port ${WSJTX_UDP_PORT} (multicast: ${WSJTX_UDP_MULTICAST})`);

// WSJT-X Parser
const wsjtxParser = new WsjtxParser();

// ============= SDC PARSING =============

// Parse SKMTEXT format: "SKMTEXT:x,y,text"
// Extracts just the text portion (after the second comma)
// IMPORTANT: Do NOT trim() - spaces are meaningful decoded characters!
function parseSKMTEXT(line) {
  const match = line.match(/SKMTEXT:\d+,\d+,(.*?)(?:;|$)/);
  if (match && match[1] !== undefined) {
    return match[1];  // Return as-is, preserving spaces
  }
  return null;
}

// ============= WSJT-X PARSING =============

// Extract key fields from WSJT-X Status message
function extractStatusFields(msg) {
  return {
    type: 'Status',
    source: 'wsjtx',
    dialFrequency: msg.dialFrequency,
    txEnabled: msg.txEnabled,
    dxCall: msg.dxCall || '',
    dxGrid: msg.dxGrid || '',
    mode: msg.mode || '',
    txRst: msg.txRst || '',
    rxRst: msg.rxRst || '',
    ts: Date.now()
  };
}

// Extract key fields from WSJT-X Decode message
function extractDecodeFields(msg) {
  return {
    type: 'Decode',
    source: 'wsjtx',
    isNew: msg.isNew,
    frequency: msg.frequency,
    time: msg.time,
    delta: msg.delta,
    deltaFrequency: msg.deltaFrequency,
    mode: msg.mode || '',
    message: msg.message || '',
    lowConfidence: msg.lowConfidence,
    offAir: msg.offAir,
    ts: Date.now()
  };
}

// Extract key fields from WSJT-X LoggedAdif message
function extractLoggedAdifFields(msg) {
  return {
    type: 'LoggedAdif',
    source: 'wsjtx',
    dxCall: msg.dxCall || '',
    dxGrid: msg.dxGrid || '',
    dialFrequency: msg.dialFrequency,
    mode: msg.mode || '',
    txRst: msg.txRst || '',
    rxRst: msg.rxRst || '',
    adifText: msg.adifText || '',
    ts: Date.now()
  };
}

// ============= BROADCAST FUNCTION =============

function broadcast(data) {
  const msg = JSON.stringify(data);
  
  let count = 0;
  for (const client of wss.clients) {
    if (client.readyState === 1) { // 1 = OPEN
      client.send(msg);
      count++;
    }
  }
  
  if (count > 0 && data.source !== 'sdc') {
    // Log WSJT-X broadcasts
    if (data.type === 'LoggedAdif') {
      console.log(`📤 Broadcast LoggedAdif to ${count} client(s): ${data.dxCall} @ ${(data.dialFrequency/1e6).toFixed(3)} MHz`);
    } else if (data.type === 'Status' && data.dxCall) {
      console.log(`📤 Broadcast Status to ${count} client(s): Working ${data.dxCall}`);
    } else if (data.type === 'Decode') {
      console.log(`📤 Broadcast Decode to ${count} client(s): "${data.message}"`);
    }
  } else if (count > 0 && data.source === 'sdc') {
    console.log(`📤 Broadcast SDC to ${count} client(s): "${data.text}"`);
  }
}

// ============= SDC TCP CONNECTION =============

// Handle WebSocket connections
wss.on('connection', (ws) => {
  console.log(`👤 WebSocket client connected. Total: ${wss.clients.size}`);
  ws.on('close', () => {
    console.log(`👤 WebSocket client disconnected. Total: ${wss.clients.size}`);
  });
});

// Connect to SDC TCP broadcast stream
function connectSDC() {
  console.log(`📡 Connecting to SDC on ${TCP_HOST}:${TCP_PORT}…`);
  
  const client = net.createConnection({ 
    host: TCP_HOST, 
    port: TCP_PORT 
  });

  // On successful connection
  client.on('connect', () => {
    console.log('✅ Connected to SDC TCP stream');
  });

  // On data received from SDC
  client.on('data', (data) => {
    const lines = data.toString().split(/\r?\n/);
    lines.forEach(line => {
      if (line.trim()) {
        // Only process SKMTEXT messages (ignore other SDC messages)
        if (!line.includes('SKMTEXT')) {
          return;
        }
        
        const extractedText = parseSKMTEXT(line);
        if (!extractedText) {
          return;
        }
        
        broadcast({ 
          ts: Date.now(), 
          text: extractedText,
          source: 'sdc'
        });
      }
    });
  });

  // On connection error
  client.on('error', (err) => {
    console.error('❌ SDC connection error:', err.message);
  });

  // On connection closed
  client.on('close', () => {
    console.log('⚠️  SDC connection closed. Retrying in 5 seconds…');
    setTimeout(connectSDC, 5000);
  });
}

// ============= GET LOCAL IP ADDRESS =============

function getLocalIPAddress() {
  const interfaces = os.networkInterfaces();
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name]) {
      // Skip internal (loopback) and non-IPv4 addresses
      if (iface.family === 'IPv4' && !iface.internal) {
        return iface.address;
      }
    }
  }
  // Fallback to localhost if no external interface found
  return '0.0.0.0';
}

// ============= WSJT-X UDP LISTENER =============

function startWSJTXListener() {
  if (!WSJTX_ENABLED) {
    console.log('⚠️  WSJT-X listener disabled');
    return;
  }

  // Create a SINGLE socket that listens on all interfaces (0.0.0.0)
  // This receives both multicast AND localhost packets on all interfaces
  // Windows has issues with dual sockets on same port, so we use reuseAddr for flexibility
  const udp = dgram.createSocket({ type: 'udp4', reuseAddr: true });
  
  // Shared message handler for both sockets
  function handleWSJTXMessage(buf, rinfo) {
    console.log(`📦 UDP packet received from ${rinfo.address}:${rinfo.port} (${buf.length} bytes)`);
    
    try {
      // Show raw packet inspection
      if (buf.length >= 12) {
        const magic = buf.readUInt32BE(0);
        const schema = buf.readUInt32BE(4);
        const msgType = buf.readUInt32BE(8);
        console.log(`   Magic: 0x${magic.toString(16).padStart(8, '0')}, Schema: ${schema}, MsgType: ${msgType}`);
        
        const hexDump = buf.slice(0, 48).toString('hex');
        console.log(`   Raw (hex): ${hexDump}`);
      }
      
      const msg = wsjtxParser.parse(buf);
      
      if (!msg) {
        console.warn(`⚠️  Failed to parse packet: magic number or format issue`);
        const magic = buf.length >= 4 ? `0x${buf.readUInt32BE(0).toString(16)}` : 'N/A';
        console.warn(`    Magic: ${magic}, Size: ${buf.length} bytes`);
        console.warn(`    First 32 bytes: ${buf.slice(0, 32).toString('hex')}`);
        return;
      }
      
      console.log(`✅ Parsed ${msg.type} message`);
      if (msg.type === 'DECODE') {
        if (msg.isNew) console.log(`   New Decode`);
        if (msg.message) console.log(`   Message: "${msg.message}"`);
        if (msg.snr !== undefined) console.log(`   SNR: ${msg.snr} dB`);
        if (msg.deltaFrequency) console.log(`   DF: ${msg.deltaFrequency} Hz`);
      } else {
        if (msg.dxCall) console.log(`   DX Call: ${msg.dxCall}`);
        if (msg.mode) console.log(`   Mode: ${msg.mode}`);
        if (msg.dialFrequency) console.log(`   Frequency: ${msg.dialFrequency} Hz`);
      }
      
      let broadcastData = null;

      if (msg.type === 'STATUS') {
        broadcastData = {
          type: 'wsjtx_status',
          source: 'wsjtx',
          dialFrequency: msg.dialFrequency ? Number(msg.dialFrequency) : null,
          dxCall: msg.dxCall || '',
          dxGrid: msg.dxGrid || '',
          txEnabled: msg.txEnabled || false,
          txRst: msg.txRst || '',
          rxRst: msg.rxRst || '',
          ts: Date.now()
        };
      } else if (msg.type === 'DECODE') {
        broadcastData = {
          type: 'wsjtx_decode',
          source: 'wsjtx',
          isNew: msg.isNew || false,
          frequency: msg.frequency ? Number(msg.frequency) : null,
          time: msg.time,
          deltaFrequency: msg.deltaFrequency,
          mode: msg.mode || '',
          message: msg.message || '',
          ts: Date.now()
        };
      } else if (msg.type === 'LOGGED_ADIF' || msg.type === 'LOGGED_ADIF_V2') {
        broadcastData = {
          type: 'wsjtx_logged_adif',
          source: 'wsjtx',
          dxCall: msg.dxCall || '',
          dxGrid: msg.dxGrid || '',
          dialFrequency: msg.dialFrequency ? Number(msg.dialFrequency) : null,
          mode: msg.mode || '',
          txRst: msg.reportSent || msg.txRst || '',
          rxRst: msg.reportReceived || msg.rxRst || '',
          adifText: msg.adifText || '',
          ts: Date.now()
        };
      } else {
        broadcastData = {
          type: `wsjtx_${msg.msgType}`,
          source: 'wsjtx',
          ts: Date.now()
        };
      }

      if (broadcastData) {
        broadcast(broadcastData);
      }
    } catch (e) {
      console.debug(`Debug: Could not parse UDP packet: ${e.message}`);
    }
  }
  
  udp.on('listening', () => {
    const a = udp.address();
    console.log(`✅ WSJT-X UDP listening on ${a.address}:${a.port}`);
    console.log(`   Waiting for WSJT-X packets...`);
    console.log(`   Make sure WSJT-X Settings > Reporting > "Enable UDP Server" is checked`);
    
    try {
      udp.setRecvBufferSize?.(256 * 1024);
      console.log(`  ✓ Recv buffer increased to 256KB`);
    } catch (e) {
      // Not critical
    }
    
    if (WSJTX_UDP_MULTICAST && WSJTX_UDP_MULTICAST !== '127.0.0.1') {
      try {
        console.log(`🔧 Configuring multicast socket...`);
        udp.setMulticastLoopback(true);
        console.log(`  ✓ Multicast loopback enabled`);
        udp.setMulticastTTL(1);
        console.log(`  ✓ Multicast TTL set to 1`);
        
        // Get the local IP address
        const localIP = getLocalIPAddress();
        
        // Join multicast on BOTH interfaces:
        // 1. Loopback (127.0.0.1) - where WSJT-X might be sending
        // 2. Local network interface - where it should be sending
        
        const interfacesToJoin = ['127.0.0.1', localIP];
        
        for (const iface of interfacesToJoin) {
          try {
            udp.addMembership(WSJTX_UDP_MULTICAST, iface);
            console.log(`✅ Joined multicast group ${WSJTX_UDP_MULTICAST} on ${iface}`);
          } catch (e) {
            console.warn(`⚠️  Failed to join on ${iface}: ${e.code}`);
          }
        }
      } catch (e) {
        console.warn(`⚠️  Multicast config: ${e.message}`);
      }
    }
  });

  udp.on('message', handleWSJTXMessage);

  udp.on('error', (err) => {
    console.error(`❌ WSJT-X UDP error: ${err.message}`);
  });

  // CRITICAL: Bind to PORT ONLY (no address) for multicast reception on Windows
  // When you don't specify an address, the socket listens on all interfaces
  // This allows the OS to properly route multicast packets to this socket
  // The listening event handler (registered above) will configure multicast AFTER bind completes
  udp.bind(WSJTX_UDP_PORT);
}

// ============= STARTUP =============

// Start the SDC connection
connectSDC();

// Start the WSJT-X listener
startWSJTXListener();

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down...');
  wss.clients.forEach(client => client.close());
  wss.close();
  process.exit(0);
});

console.log('\n📝 Configuration:');
console.log(`   SDC TCP Host: ${TCP_HOST}:${TCP_PORT}`);
console.log(`   WSJT-X UDP: ${WSJTX_ENABLED ? `Enabled on port ${WSJTX_UDP_PORT} (multicast: ${WSJTX_UDP_MULTICAST})` : 'Disabled'}`);
console.log(`   WebSocket Port: ${WS_PORT}`);
console.log('\n💡 Press Ctrl+C to stop the server\n');
