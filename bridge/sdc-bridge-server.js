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
import http from 'http';
import https from 'https';
import os from 'os';
import { WebSocketServer } from 'ws';
import { WsjtxParser } from './wsjtx-parser.js';
import { buildCommand } from './wsjtx-protocol.js';

// Configuration from environment or defaults
const TCP_HOST = process.env.TCP_HOST || '127.0.0.1';
const TCP_PORT = parseInt(process.env.TCP_PORT || '12166');
const WSJTX_UDP_PORT = parseInt(process.env.WSJTX_UDP_PORT || '2237');
const WSJTX_UDP_MULTICAST = process.env.WSJTX_UDP_MULTICAST || '224.0.0.1';
const WS_PORT = parseInt(process.env.WS_PORT || '8091');
const WSJTX_COMMAND_PORT = parseInt(process.env.WSJTX_COMMAND_PORT || '8092');
const WSJTX_ENABLED = process.env.WSJTX_ENABLED !== 'false';
const BRIDGE_TEST_MODE = process.env.OM0RX_BRIDGE_TEST_MODE === '1';
const OM0RX_BACKEND_URL = (process.env.OM0RX_BACKEND_URL || 'http://127.0.0.1:8080').replace(/\/+$/, '');

// WebSocket server is created during startup. Keeping module import side-effect
// free in test mode lets protocol/diagnostic contracts be exercised safely.
let wss = null;

// WSJT-X Parser
const wsjtxParser = new WsjtxParser();
let latestWsjtxEndpoint = null;
let latestWsjtxClientId = '';
let wsjtxCommandSender = null;
let pendingQsoLoggedUploadTimer = null;
let pendingQsoLoggedData = null;
let wsjtxStats = {
  packets: 0,
  statuses: 0,
  decodes: 0,
  logged: 0,
  commands: 0,
  commandErrors: 0,
  loggedUploads: 0,
  loggedUploadErrors: 0,
  other: 0,
  lastPacket: null,
  lastStatus: null,
  lastDecode: null,
  lastLogged: null,
  lastLoggedUpload: null,
  lastCommand: null,
};
const WSJTX_TIMELINE_LIMIT = 80;
const wsjtxTimeline = [];
const WSJTX_RECENT_DECODE_LIMIT = 120;
const wsjtxRecentDecodes = [];

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
  if (!wss) {
    return;
  }
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

function summariseWsjtxPayload(payload = {}) {
  const target = payload.target && typeof payload.target === 'object' ? payload.target : payload;
  const summary = {};
  for (const [sourceKey, targetKey] of [
    ['call', 'call'],
    ['callsign', 'call'],
    ['dxCall', 'call'],
    ['grid', 'grid'],
    ['dxGrid', 'grid'],
    ['mode', 'mode'],
    ['dialFrequency', 'dialFrequency'],
    ['frequency', 'dialFrequency'],
    ['rxDf', 'rxDf'],
    ['txDf', 'txDf'],
    ['enableTx', 'enableTx'],
    ['holdTxFreq', 'holdTxFreq'],
    ['traceId', 'traceId'],
    ['trace_id', 'traceId'],
  ]) {
    if (target[sourceKey] !== undefined && summary[targetKey] === undefined) {
      summary[targetKey] = target[sourceKey];
    }
  }
  return summary;
}

function addWsjtxTimeline(entry) {
  const item = {
    ts: Date.now(),
    ...entry,
  };
  wsjtxTimeline.push(item);
  while (wsjtxTimeline.length > WSJTX_TIMELINE_LIMIT) {
    wsjtxTimeline.shift();
  }
  return item;
}

function commandCapabilities() {
  return {
    clear: true,
    replay: true,
    halt_tx: true,
    free_text: true,
    location: true,
    switch_configuration: true,
    configure: true,
    reply: true,
    start_target_qso: true,
  };
}

function getWsjtxClientSnapshot() {
  if (!latestWsjtxEndpoint) {
    return null;
  }
  return {
    address: latestWsjtxEndpoint.address,
    port: latestWsjtxEndpoint.port,
    id: latestWsjtxClientId,
    lastSeenMs: Date.now() - latestWsjtxEndpoint.ts,
  };
}

function getWsjtxStatsSnapshot() {
  const now = Date.now();
  const age = (entry) => entry && entry.ts ? now - entry.ts : null;
  return {
    ...wsjtxStats,
    recentDecodes: wsjtxRecentDecodes.slice(-50),
    lastPacketAgeMs: age(wsjtxStats.lastPacket),
    lastStatusAgeMs: age(wsjtxStats.lastStatus),
    lastDecodeAgeMs: age(wsjtxStats.lastDecode),
    lastLoggedAgeMs: age(wsjtxStats.lastLogged),
    lastCommandAgeMs: age(wsjtxStats.lastCommand),
  };
}

function dispatchWsjtxCommand(command, payload = {}) {
  if (command === 'status') {
    return {
      success: true,
      client: getWsjtxClientSnapshot(),
      capabilities: commandCapabilities(),
      timeline: wsjtxTimeline.slice(-25),
    };
  }

  const commandEntry = addWsjtxTimeline({
    direction: 'out',
    type: 'command',
    command,
    traceId: payload.traceId || (payload.target && payload.target.traceId) || '',
    payload: summariseWsjtxPayload(payload),
    client: getWsjtxClientSnapshot(),
  });
  wsjtxStats.commands += 1;
  wsjtxStats.lastCommand = commandEntry;

  if (!wsjtxCommandSender) {
    wsjtxStats.commandErrors += 1;
    commandEntry.success = false;
    commandEntry.error = 'WSJT-X UDP listener is not running';
    return { success: false, error: 'WSJT-X UDP listener is not running', traceId: commandEntry.traceId };
  }

  if (!latestWsjtxEndpoint) {
    wsjtxStats.commandErrors += 1;
    commandEntry.success = false;
    commandEntry.error = 'No WSJT-X client has been seen yet';
    return { success: false, error: 'No WSJT-X client has been seen yet', traceId: commandEntry.traceId };
  }

  const commandPayload = {
    ...payload,
    id: payload.id || latestWsjtxClientId || 'WSJT-X',
  };
  const packet = buildCommand(command, commandPayload);
  const result = wsjtxCommandSender(packet, command);
  result.traceId = commandEntry.traceId;
  commandEntry.success = result.success === true;
  commandEntry.bytes = result.bytes || 0;
  commandEntry.client = result.client || commandEntry.client;
  if (!result.success) {
    wsjtxStats.commandErrors += 1;
    commandEntry.error = result.error || 'command send failed';
  }
  return result;
}

// ============= SDC TCP CONNECTION =============

function startWebSocketServer() {
  if (wss) {
    return wss;
  }

  wss = new WebSocketServer({ port: WS_PORT });
  console.log(`🔌 WebSocket server started on ws://localhost:${WS_PORT}`);
  console.log(`📡 SDC Skimmer bridge: tcp://${TCP_HOST}:${TCP_PORT}`);
  if (WSJTX_ENABLED) console.log(`📡 WSJT-X UDP listener: port ${WSJTX_UDP_PORT} (multicast: ${WSJTX_UDP_MULTICAST})`);

  // Handle WebSocket connections
  wss.on('connection', (ws) => {
    console.log(`👤 WebSocket client connected. Total: ${wss.clients.size}`);
    ws.on('message', (raw) => {
      let request = null;
      try {
        request = JSON.parse(raw.toString());
      } catch (e) {
        return;
      }

      if (!request || request.type !== 'wsjtx_command') {
        return;
      }

      try {
        const result = dispatchWsjtxCommand(request.command, request.payload || {});
        ws.send(JSON.stringify({
          type: 'wsjtx_command_result',
          source: 'bridge',
          command: request.command,
          ...result,
          ts: Date.now(),
        }));
      } catch (e) {
        ws.send(JSON.stringify({
          type: 'wsjtx_command_result',
          source: 'bridge',
          command: request.command,
          success: false,
          error: e.message,
          ts: Date.now(),
        }));
      }
    });
    ws.on('close', () => {
      console.log(`👤 WebSocket client disconnected. Total: ${wss.clients.size}`);
    });
  });

  return wss;
}

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

  wsjtxCommandSender = (packet, command) => {
    const endpoint = latestWsjtxEndpoint;
    if (!endpoint) {
      return { success: false, error: 'No WSJT-X client endpoint is available' };
    }

    udp.send(packet, endpoint.port, endpoint.address);
    console.log(`📨 Sent WSJT-X command ${command} to ${endpoint.address}:${endpoint.port} (${packet.length} bytes)`);
    return {
      success: true,
      bytes: packet.length,
      client: getWsjtxClientSnapshot(),
    };
  };
  
  // Shared message handler for both sockets
  function handleWSJTXMessage(buf, rinfo) {
    console.log(`📦 UDP packet received from ${rinfo.address}:${rinfo.port} (${buf.length} bytes)`);
    wsjtxStats.packets += 1;
    wsjtxStats.lastPacket = {
      address: rinfo.address,
      port: rinfo.port,
      bytes: buf.length,
      ts: Date.now(),
    };
    
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

      latestWsjtxEndpoint = {
        address: rinfo.address,
        port: rinfo.port,
        ts: Date.now(),
      };
      if (msg.id) {
        latestWsjtxClientId = msg.id;
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
        wsjtxStats.statuses += 1;
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
        wsjtxStats.lastStatus = broadcastData;
        addWsjtxTimeline({
          direction: 'in',
          type: 'status',
          clientId: latestWsjtxClientId,
          dxCall: broadcastData.dxCall,
          dxGrid: broadcastData.dxGrid,
          dialFrequency: broadcastData.dialFrequency,
          txEnabled: broadcastData.txEnabled,
        });
      } else if (msg.type === 'DECODE') {
        wsjtxStats.decodes += 1;
        broadcastData = {
          type: 'wsjtx_decode',
          source: 'wsjtx',
          isNew: msg.isNew || false,
          frequency: msg.frequency ? Number(msg.frequency) : (wsjtxStats.lastStatus ? wsjtxStats.lastStatus.dialFrequency : null),
          dialFrequency: wsjtxStats.lastStatus ? wsjtxStats.lastStatus.dialFrequency : null,
          time: msg.time,
          snr: msg.snr,
          deltaFrequency: msg.deltaFrequency,
          mode: msg.mode || '',
          message: msg.message || '',
          ts: Date.now()
        };
        wsjtxStats.lastDecode = broadcastData;
        wsjtxRecentDecodes.push(broadcastData);
        while (wsjtxRecentDecodes.length > WSJTX_RECENT_DECODE_LIMIT) {
          wsjtxRecentDecodes.shift();
        }
        addWsjtxTimeline({
          direction: 'in',
          type: 'decode',
          clientId: latestWsjtxClientId,
          message: broadcastData.message,
          mode: broadcastData.mode,
          snr: broadcastData.snr,
          deltaFrequency: broadcastData.deltaFrequency,
        });
      } else if (msg.type === 'QSO_LOGGED' || msg.type === 'LOGGED_ADIF') {
        wsjtxStats.logged += 1;
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
        wsjtxStats.lastLogged = broadcastData;
        addWsjtxTimeline({
          direction: 'in',
          type: 'logged',
          clientId: latestWsjtxClientId,
          dxCall: broadcastData.dxCall,
          dxGrid: broadcastData.dxGrid,
          dialFrequency: broadcastData.dialFrequency,
          mode: broadcastData.mode,
        });
        scheduleLoggedQsoUpload(msg.type, broadcastData);
      } else {
        wsjtxStats.other += 1;
        broadcastData = {
          type: `wsjtx_${msg.msgType}`,
          source: 'wsjtx',
          ts: Date.now()
        };
        addWsjtxTimeline({
          direction: 'in',
          type: 'other',
          clientId: latestWsjtxClientId,
          messageType: msg.msgType,
        });
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

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk.toString();
      if (body.length > 1024 * 1024) {
        reject(new Error('Request body too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!body.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(body));
      } catch (e) {
        reject(e);
      }
    });
    req.on('error', reject);
  });
}

function sendJson(res, status, payload) {
  const data = JSON.stringify(payload);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(data),
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  });
  res.end(data);
}

function postJson(url, payload, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const data = JSON.stringify(payload);
    const transport = target.protocol === 'https:' ? https : http;
    const req = transport.request({
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      path: `${target.pathname}${target.search}`,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
      },
      timeout: timeoutMs,
    }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        let parsed = {};
        try {
          parsed = body ? JSON.parse(body) : {};
        } catch {
          parsed = { raw: body };
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve({ statusCode: res.statusCode, body: parsed });
        } else {
          const message = parsed.detail || parsed.error || parsed.message || body || `HTTP ${res.statusCode}`;
          reject(new Error(typeof message === 'string' ? message : JSON.stringify(message)));
        }
      });
    });
    req.on('timeout', () => {
      req.destroy(new Error(`POST ${url} timed out after ${timeoutMs}ms`));
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

function buildLoggedQsoUpload(loggedData) {
  if (!loggedData || !loggedData.dxCall) return null;
  return {
    call: String(loggedData.dxCall || '').trim().toUpperCase(),
    frequency_hz: loggedData.dialFrequency ? Number(loggedData.dialFrequency) : null,
    mode: loggedData.mode || 'FT8',
    grid: loggedData.dxGrid || '',
    rst_sent: loggedData.txRst || '',
    rst_received: loggedData.rxRst || '',
    comments: loggedData.adifText ? 'Auto-logged from WSJT-X UDP ADIF' : 'Auto-logged from WSJT-X UDP QSO Logged',
    adif_text: loggedData.adifText || '',
    source: 'wsjtx-bridge',
  };
}

async function uploadLoggedQsoToBackend(loggedData) {
  const payload = buildLoggedQsoUpload(loggedData);
  if (!payload) {
    return;
  }
  const uploadEntry = {
    ts: Date.now(),
    call: payload.call,
    mode: payload.mode,
    dialFrequency: payload.frequency_hz,
    success: false,
    error: '',
  };
  try {
    const result = await postJson(`${OM0RX_BACKEND_URL}/api/wsjtx/log-qso`, payload);
    uploadEntry.success = true;
    uploadEntry.statusCode = result.statusCode;
    uploadEntry.result = result.body;
    wsjtxStats.loggedUploads += 1;
    console.log(`✅ WSJT-X logged QSO uploaded to OM0RX backend: ${payload.call}`);
  } catch (error) {
    uploadEntry.error = error.message || String(error);
    wsjtxStats.loggedUploadErrors += 1;
    console.warn(`⚠️  WSJT-X logged QSO backend upload failed for ${payload.call}: ${uploadEntry.error}`);
  } finally {
    wsjtxStats.lastLoggedUpload = uploadEntry;
    addWsjtxTimeline({
      direction: 'out',
      type: 'logged_upload',
      clientId: latestWsjtxClientId,
      dxCall: payload.call,
      mode: payload.mode,
      dialFrequency: payload.frequency_hz,
      success: uploadEntry.success,
      error: uploadEntry.error,
    });
  }
}

function scheduleLoggedQsoUpload(messageType, loggedData) {
  if (messageType === 'LOGGED_ADIF') {
    if (pendingQsoLoggedUploadTimer) {
      clearTimeout(pendingQsoLoggedUploadTimer);
      pendingQsoLoggedUploadTimer = null;
      pendingQsoLoggedData = null;
    }
    uploadLoggedQsoToBackend(loggedData);
    return;
  }

  if (messageType !== 'QSO_LOGGED') {
    return;
  }

  if (pendingQsoLoggedUploadTimer) {
    clearTimeout(pendingQsoLoggedUploadTimer);
  }
  pendingQsoLoggedData = loggedData;
  pendingQsoLoggedUploadTimer = setTimeout(() => {
    const fallback = pendingQsoLoggedData;
    pendingQsoLoggedUploadTimer = null;
    pendingQsoLoggedData = null;
    uploadLoggedQsoToBackend(fallback);
  }, 1500);
}

function startWsjtxCommandServer() {
  const server = http.createServer(async (req, res) => {
    if (req.method === 'OPTIONS') {
      sendJson(res, 200, { ok: true });
      return;
    }

    if (req.method === 'GET' && req.url === '/wsjtx/status') {
      sendJson(res, 200, getWsjtxStatusSnapshot());
      return;
    }

    if (req.method !== 'POST' || req.url !== '/wsjtx/command') {
      sendJson(res, 404, { success: false, error: 'Not found' });
      return;
    }

    try {
      const request = await readJsonBody(req);
      if (!request.command) {
        sendJson(res, 400, { success: false, error: 'Missing command' });
        return;
      }

      const result = dispatchWsjtxCommand(request.command, request.payload || {});
      sendJson(res, result.success ? 200 : 409, {
        command: request.command,
        ...result,
      });
    } catch (e) {
      sendJson(res, 400, { success: false, error: e.message });
    }
  });

  server.listen(WSJTX_COMMAND_PORT, '127.0.0.1', () => {
    console.log(`🎛️  WSJT-X command API: http://127.0.0.1:${WSJTX_COMMAND_PORT}/wsjtx/command`);
  });
}

function getWsjtxStatusSnapshot() {
  return {
    success: true,
    enabled: WSJTX_ENABLED,
    client: getWsjtxClientSnapshot(),
    stats: getWsjtxStatsSnapshot(),
    capabilities: commandCapabilities(),
    timeline: wsjtxTimeline.slice(-25),
  };
}

export function __resetWsjtxBridgeDiagnosticsForTest() {
  if (pendingQsoLoggedUploadTimer) {
    clearTimeout(pendingQsoLoggedUploadTimer);
    pendingQsoLoggedUploadTimer = null;
  }
  pendingQsoLoggedData = null;
  latestWsjtxEndpoint = null;
  latestWsjtxClientId = '';
  wsjtxCommandSender = null;
  wsjtxStats = {
    packets: 0,
    statuses: 0,
    decodes: 0,
    logged: 0,
    commands: 0,
    commandErrors: 0,
    loggedUploads: 0,
    loggedUploadErrors: 0,
    other: 0,
    lastPacket: null,
    lastStatus: null,
    lastDecode: null,
    lastLogged: null,
    lastLoggedUpload: null,
    lastCommand: null,
  };
  wsjtxTimeline.length = 0;
  wsjtxRecentDecodes.length = 0;
}

export function __dispatchWsjtxCommandForTest(command, payload = {}) {
  return dispatchWsjtxCommand(command, payload);
}

export function __getWsjtxStatusForTest() {
  return getWsjtxStatusSnapshot();
}

export function __buildLoggedQsoUploadForTest(loggedData) {
  return buildLoggedQsoUpload(loggedData);
}

// ============= STARTUP =============

if (!BRIDGE_TEST_MODE) {
  // Start WebSocket server
  startWebSocketServer();

  // Start the SDC connection
  connectSDC();

  // Start the WSJT-X listener
  startWSJTXListener();

  // Start local command API for backend-driven automation
  startWsjtxCommandServer();

  // Graceful shutdown
  process.on('SIGINT', () => {
    console.log('\n🛑 Shutting down...');
    if (wss) {
      wss.clients.forEach(client => client.close());
      wss.close();
    }
    process.exit(0);
  });

  console.log('\n📝 Configuration:');
  console.log(`   SDC TCP Host: ${TCP_HOST}:${TCP_PORT}`);
  console.log(`   WSJT-X UDP: ${WSJTX_ENABLED ? `Enabled on port ${WSJTX_UDP_PORT} (multicast: ${WSJTX_UDP_MULTICAST})` : 'Disabled'}`);
  console.log(`   WebSocket Port: ${WS_PORT}`);
  console.log(`   WSJT-X Command API Port: ${WSJTX_COMMAND_PORT}`);
  console.log('\n💡 Press Ctrl+C to stop the server\n');
}
