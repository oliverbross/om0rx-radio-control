#!/usr/bin/env node
/**
 * Diagnostic Tool: Check WSJT-X UDP Listener Status
 * 
 * This script helps diagnose why WSJT-X data isn't flowing to the application
 */

import dgram from 'dgram';
import { WsjtxParser } from './wsjtx-parser.js';

console.log('\n' + '='.repeat(60));
console.log('🔍 WSJT-X UDP Listener Diagnostic Tool');
console.log('='.repeat(60) + '\n');

const WSJTX_UDP_PORT = parseInt(process.env.WSJTX_UDP_PORT || '2237');
const WSJTX_UDP_MULTICAST = process.env.WSJTX_UDP_MULTICAST || '224.0.0.1';

console.log('📋 Configuration:');
console.log(`   Port: ${WSJTX_UDP_PORT}`);
console.log(`   Multicast: ${WSJTX_UDP_MULTICAST}`);
console.log('');

const udp = dgram.createSocket({ type: 'udp4', reuseAddr: true });
const wsjtxParser = new WsjtxParser();

let packetCount = 0;
const startTime = Date.now();

udp.on('listening', () => {
  const addr = udp.address();
  console.log(`✅ UDP Socket listening on ${addr.address}:${addr.port}\n`);
  
  if (WSJTX_UDP_MULTICAST && WSJTX_UDP_MULTICAST !== '127.0.0.1') {
    try {
      console.log(`🔧 Configuring multicast...'`);
      udp.setMulticastLoopback(true);
      udp.setMulticastTTL(1);
      udp.addMembership(WSJTX_UDP_MULTICAST);
      console.log(`✅ Multicast group ${WSJTX_UDP_MULTICAST} joined\n`);
    } catch (e) {
      console.error(`❌ Multicast config failed: ${e.message}\n`);
    }
  }
  
  console.log('⏳ Waiting for WSJT-X packets...\n');
  console.log('📝 CHECKLIST - If no packets arrive, verify in WSJT-X:');
  console.log('   1. Settings → Reporting → "Enable UDP Server" is CHECKED ✓');
  console.log('   2. UDP Server address: 127.0.0.1 (localhost)');
  console.log('   3. UDP Server port: 2237');
  console.log('   4. WSJT-X is running and in RX/TX mode (not idle)');
  console.log('   5. Windows Firewall allows UDP on port 2237');
  console.log('   6. Click on a CQ (decode) or double-click a station\n');
  console.log('='.repeat(60) + '\n');
});

udp.on('message', (buf, rinfo) => {
  packetCount++;
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  
  console.log(`\n📦 Packet #${packetCount} received at ${elapsed}s from ${rinfo.address}:${rinfo.port}`);
  console.log(`   Size: ${buf.length} bytes`);
  
  // Show raw header info
  if (buf.length >= 12) {
    const magic = buf.readUInt32BE(0);
    const schema = buf.readUInt32BE(4);
    const msgType = buf.readUInt32BE(8);
    console.log(`   Magic: 0x${magic.toString(16).padStart(8, '0')} Schema: ${schema} Type: ${msgType}`);
  }
  
  try {
    const msg = wsjtxParser.parse(buf);
    if (msg) {
      console.log(`   ✅ Parsed successfully: ${msg.type}`);
      
      if (msg.type === 'STATUS') {
        console.log(`      DX Call: ${msg.dxCall || '(none)'}`);
        console.log(`      DX Grid: ${msg.dxGrid || '(none)'}`);
        console.log(`      Frequency: ${msg.dialFrequency ? (msg.dialFrequency / 1e6).toFixed(3) + ' MHz' : '(none)'}`);
      } else if (msg.type === 'DECODE') {
        console.log(`      Message: "${msg.message || '(none)'}"`);
        console.log(`      Frequency: ${msg.frequency ? (msg.frequency / 1e6).toFixed(3) + ' MHz' : '(none)'}`);
      } else if (msg.type === 'LOGGED_ADIF' || msg.type === 'LOGGED_ADIF_V2') {
        console.log(`      DX Call: ${msg.dxCall || '(none)'}`);
        console.log(`      DX Grid: ${msg.dxGrid || '(none)'}`);
      }
    } else {
      console.log(`   ⚠️  Parse returned null (may be non-WSJT-X packet)`);
    }
  } catch (e) {
    console.log(`   ⚠️  Parse error: ${e.message}`);
  }
});

udp.on('error', (err) => {
  console.error(`\n❌ UDP Socket error: ${err.message}`);
  if (err.code === 'EADDRINUSE') {
    console.error(`   Port ${WSJTX_UDP_PORT} is already in use!`);
    console.error(`   Is the bridge server already running?`);
    console.error(`   Try: netstat -ano | findstr :${WSJTX_UDP_PORT}`);
  }
});

// Bind socket
try {
  udp.bind(WSJTX_UDP_PORT, '0.0.0.0');
} catch (e) {
  console.error(`❌ Failed to bind socket: ${e.message}`);
  process.exit(1);
}

// Auto-exit after 60 seconds
setTimeout(() => {
  console.log('\n' + '='.repeat(60));
  console.log(`⏱️  Timeout: 60 seconds elapsed\n`);
  
  if (packetCount === 0) {
    console.log('❌ NO WSJT-X PACKETS RECEIVED!\n');
    console.log('🔧 Troubleshooting Steps:');
    console.log('   1. Verify WSJT-X Settings:');
    console.log('      - File → Settings → Reporting');
    console.log('      - Enable UDP Server: ✓ CHECKED');
    console.log('      - Server address: 127.0.0.1');
    console.log('      - Server port: 2237');
    console.log('');
    console.log('   2. Verify WSJT-X is active:');
    console.log('      - Start receiving (RX or TX mode)');
    console.log('      - Click on a CQ or decode');
    console.log('');
    console.log('   3. Check Windows Firewall:');
    console.log('      - Whitelist Node.js for UDP');
    console.log('      - Whitelist WSJT-X for UDP');
    console.log('');
    console.log('   4. Test direct UDP:');
    console.log('      - Open Command Prompt');
    console.log('      - Run: netstat -ano | findstr :2237');
    console.log('      - See if anything is listening/sending');
    console.log('');
  } else {
    console.log(`✅ SUCCESS! Received ${packetCount} WSJT-X packet(s)\n`);
    console.log('🎉 Your WSJT-X → Bridge connection is working!');
    console.log('   Messages should now flow through the web interface\n');
  }
  
  console.log('='.repeat(60) + '\n');
  udp.close();
  process.exit(packetCount === 0 ? 1 : 0);
}, 60000);

console.log('Press Ctrl+C to stop\n');

// Handle Ctrl+C
process.on('SIGINT', () => {
  console.log('\n\n' + '='.repeat(60));
  console.log('Diagnostic stopped by user');
  console.log('='.repeat(60) + '\n');
  udp.close();
  process.exit(0);
});