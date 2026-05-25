// Test script to check if WSJT-X packets are being received
import dgram from 'dgram';

const WSJTX_UDP_PORT = parseInt(process.env.WSJTX_UDP_PORT || '2237');
const WSJTX_UDP_MULTICAST = process.env.WSJTX_UDP_MULTICAST || '224.0.0.1';

const socket = dgram.createSocket('udp4');

socket.on('message', (msg, rinfo) => {
    console.log(`\n📨 WSJT-X packet received from ${rinfo.address}:${rinfo.port}`);
    console.log(`   Size: ${msg.length} bytes`);
    console.log(`   Data (first 100 bytes): ${msg.slice(0, 100).toString('hex')}`);
    console.log(`   ASCII preview: ${msg.toString('ascii', 0, Math.min(50, msg.length))}`);
});

socket.on('error', (err) => {
    console.error('Socket error:', err);
});

socket.on('listening', () => {
    console.log(`✅ Listening for WSJT-X packets on UDP port ${WSJTX_UDP_PORT}`);
    console.log(`   Multicast address: ${WSJTX_UDP_MULTICAST}`);
    console.log(`\n   Make sure WSJT-X is running with "Enable UDP Server" checked`);
    console.log(`   Waiting for packets...\n`);
});

socket.bind(WSJTX_UDP_PORT);

// Try multicast (may fail on Windows with EHOSTUNREACH, but fallback to 0.0.0.0 works)
try {
    socket.addMembership(WSJTX_UDP_MULTICAST);
    console.log(`📡 Added multicast membership for ${WSJTX_UDP_MULTICAST}`);
} catch (err) {
    console.log(`⚠️  Multicast membership failed (Windows limitation): ${err.code}`);
    console.log(`   Will still receive on all interfaces\n`);
}