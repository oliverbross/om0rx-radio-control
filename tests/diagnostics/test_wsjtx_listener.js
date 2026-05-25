/**
 * WSJT-X UDP Listener Diagnostic Tool
 * 
 * This tool listens on the WSJT-X UDP port and:
 * 1. Shows if packets are being received
 * 2. Shows the raw magic number and message type
 * 3. Shows parsed message details if format is correct
 * 4. Helps diagnose why the integration isn't working
 * 
 * Usage:
 *   WSJTX_UDP_PORT=2237 node test_wsjtx_listener.js
 */

import dgram from 'dgram';
import { WsjtxParser } from '../../bridge/wsjtx-parser.js';

const WSJTX_UDP_PORT = parseInt(process.env.WSJTX_UDP_PORT || '2237');
const WSJTX_UDP_MULTICAST = process.env.WSJTX_UDP_MULTICAST || '224.0.0.1';
const parser = new WsjtxParser();

const udp = dgram.createSocket({ type: 'udp4', reuseAddr: true });
let packetCount = 0;

console.log(`
╔════════════════════════════════════════════════════════════════╗
║         WSJT-X UDP Listener Diagnostic Tool                    ║
╚════════════════════════════════════════════════════════════════╝

📡 Listening for WSJT-X UDP packets...
   Port: ${WSJTX_UDP_PORT}
   Address: 0.0.0.0 (all interfaces)

🟢 Waiting for WSJT-X to send messages...
   Make sure:
   1. WSJT-X Settings → Reporting → "Enable UDP Server" is CHECKED
   2. WSJT-X UDP port is set to ${WSJTX_UDP_PORT}
   3. WSJT-X is actually running

   (Messages will appear below as they arrive)

─────────────────────────────────────────────────────────────────
`);

udp.on('listening', () => {
  const a = udp.address();
  console.log(`✅ UDP socket bound to ${a.address}:${a.port}`);
  
  // Configure multicast
  if (WSJTX_UDP_MULTICAST !== '127.0.0.1') {
    try {
      udp.setMulticastLoopback(true);
      udp.setMulticastTTL(1);
      udp.addMembership(WSJTX_UDP_MULTICAST);
      console.log(`✅ Joined multicast group ${WSJTX_UDP_MULTICAST}\n`);
    } catch (e) {
      console.warn(`⚠️  Multicast configuration failed: ${e.message}\n`);
    }
  }
});

udp.on('message', (buf, rinfo) => {
  packetCount++;
  
  // Show raw packet info
  console.log(`\n📦 Packet #${packetCount} received from ${rinfo.address}:${rinfo.port} (${buf.length} bytes)`);
  
  // Check magic number
  if (buf.length < 4) {
    console.log(`   ⚠️  Packet too short (${buf.length} bytes)`);
    return;
  }
  
  const magic = buf.readUInt32BE(0);
  console.log(`   Magic number: 0x${magic.toString(16).padStart(8, '0')}`);
  
  if (magic === 0xadbccbda) {
    console.log(`   ✅ CORRECT magic number (0xadbccbda)`);
  } else {
    console.log(`   ❌ WRONG magic number!`);
    console.log(`      Expected: 0xadbccbda`);
    console.log(`      Got:      0x${magic.toString(16)}`);
    return;
  }
  
  // Check schema
  if (buf.length >= 8) {
    const schema = buf.readUInt32BE(4);
    console.log(`   Schema: ${schema}`);
  }
  
  // Check message type
  if (buf.length >= 9) {
    const msgType = buf[8];
    const typeNames = {
      0: 'HEARTBEAT',
      1: 'STATUS',
      2: 'DECODE',
      3: 'CLEAR',
      4: 'REPLY',
      5: 'QSO_LOGGED',
      6: 'CLOSE',
      7: 'REPLAY',
      8: 'HALT_TX',
      9: 'FREE_TEXT',
      10: 'WSPR_DECODE',
      11: 'LOCATION',
      12: 'LOGGED_ADIF',
      14: 'LOGGED_ADIF_V2'
    };
    const typeName = typeNames[msgType] || `UNKNOWN_${msgType}`;
    console.log(`   Message Type: ${msgType} (${typeName})`);
  }
  
  // Try to parse the message
  console.log(`\n   Attempting to parse...`);
  const parsed = parser.parse(buf);
  
  if (parsed) {
    console.log(`   ✅ Parsed successfully!\n`);
    
    // Show parsed data based on message type
    if (parsed.type === 'STATUS') {
      console.log(`      Type: Status`);
      if (parsed.dialFrequency) console.log(`      Frequency: ${Number(parsed.dialFrequency)/1e6} MHz`);
      if (parsed.mode) console.log(`      Mode: ${parsed.mode}`);
      if (parsed.dxCall) console.log(`      DX Call: ${parsed.dxCall}`);
      if (parsed.dxGrid) console.log(`      DX Grid: ${parsed.dxGrid}`);
      if (parsed.txEnabled !== undefined) console.log(`      TX Enabled: ${parsed.txEnabled}`);
      if (parsed.transmitting !== undefined) console.log(`      Transmitting: ${parsed.transmitting}`);
      if (parsed.decoding !== undefined) console.log(`      Decoding: ${parsed.decoding}`);
    } else if (parsed.type === 'DECODE') {
      console.log(`      Type: Decode`);
      if (parsed.isNew !== undefined) console.log(`      New: ${parsed.isNew}`);
      if (parsed.message) console.log(`      Message: "${parsed.message}"`);
      if (parsed.mode) console.log(`      Mode: ${parsed.mode}`);
      if (parsed.snr) console.log(`      SNR: ${parsed.snr} dB`);
      if (parsed.deltaFrequency) console.log(`      Delta Frequency: ${parsed.deltaFrequency} Hz`);
    } else if (parsed.type === 'LOGGED_ADIF' || parsed.type === 'LOGGED_ADIF_V2') {
      console.log(`      Type: QSO Logged`);
      if (parsed.dxCall) console.log(`      DX Call: ${parsed.dxCall}`);
      if (parsed.dxGrid) console.log(`      DX Grid: ${parsed.dxGrid}`);
      if (parsed.dialFrequency) console.log(`      Frequency: ${Number(parsed.dialFrequency)/1e6} MHz`);
      if (parsed.mode) console.log(`      Mode: ${parsed.mode}`);
    } else {
      console.log(`      Type: ${parsed.type}`);
      console.log(`      Details: ${JSON.stringify(parsed, null, 2)}`);
    }
  } else {
    console.log(`   ❌ Failed to parse message`);
    console.log(`      This could indicate:
      1. Message format is corrupted
      2. Parser doesn't handle this message type yet
      3. Buffer is incomplete`);
  }
  
  console.log(`\n─────────────────────────────────────────────────────────────────`);
});

udp.on('error', (err) => {
  console.error(`\n❌ UDP Error: ${err.message}`);
  if (err.code === 'EADDRINUSE') {
    console.error(`\n   Port ${WSJTX_UDP_PORT} is already in use!`);
    console.error(`   Make sure another instance isn't running.`);
  }
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log(`\n\n╔════════════════════════════════════════════════════════════════╗`);
  console.log(`║ Summary                                                         ║`);
  console.log(`╚════════════════════════════════════════════════════════════════╝`);
  console.log(`\nTotal packets received: ${packetCount}`);
  
  if (packetCount === 0) {
    console.log(`
❌ NO PACKETS RECEIVED

This means:
1. WSJT-X is not sending UDP packets
2. WSJT-X "Enable UDP Server" is not checked
3. WSJT-X UDP port doesn't match (should be ${WSJTX_UDP_PORT})
4. Firewall is blocking the packets
5. WSJT-X is not running

Action items:
- Open WSJT-X Settings → Reporting
- Ensure "Enable UDP Server" is CHECKED
- Ensure UDP port is set to ${WSJTX_UDP_PORT}
- Restart WSJT-X
- Try again`);
  } else {
    console.log(`
✅ Packets are being received!

This means:
- WSJT-X is configured correctly
- UDP messages are reaching the bridge
- Check the bridge server logs for broadcast messages`);
  }
  
  console.log(`\n🛑 Listening stopped.\n`);
  process.exit(0);
});

// Bind to the UDP port
udp.bind(WSJTX_UDP_PORT);
