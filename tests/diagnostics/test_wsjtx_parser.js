/**
 * Test the WSJT-X parser with the corrected magic number
 * This validates that the parser can now receive WSJT-X messages
 */

import { WsjtxParser } from '../../bridge/wsjtx-parser.js';

const parser = new WsjtxParser();

// Helper to build a test WSJT-X Status message
function buildStatusMessage(dialFrequency = 7074000, mode = 'FT8', dxCall = 'W5ABC', dxGrid = 'EM12') {
  const buf = Buffer.alloc(256);
  let offset = 0;

  // 1. Magic number: 0xadbccbda (big-endian)
  buf.writeUInt32BE(0xadbccbda, offset);
  offset += 4;

  // 2. Schema number: 3 (big-endian)
  buf.writeUInt32BE(3, offset);
  offset += 4;

  // 3. Message type: 1 (STATUS)
  buf.writeUInt8(1, offset);
  offset += 1;

  // Helper to write a string (QByteArray format: 4-byte length + data)
  const writeString = (str, off) => {
    const encoded = Buffer.from(str, 'utf8');
    buf.writeUInt32BE(encoded.length, off);
    encoded.copy(buf, off + 4);
    return off + 4 + encoded.length;
  };

  // 4. Id (utf8)
  offset = writeString('test_id', offset);

  // 5. Dial Frequency (quint64, big-endian)
  buf.writeBigInt64BE(BigInt(dialFrequency), offset);
  offset += 8;

  // 6. Mode (utf8)
  offset = writeString(mode, offset);

  // 7. DX call (utf8)
  offset = writeString(dxCall, offset);

  // 8. Report (utf8)
  offset = writeString('-15', offset);

  // 9. Tx Mode (utf8)
  offset = writeString(mode, offset);

  // 10. Tx Enabled (bool)
  buf.writeUInt8(1, offset);
  offset += 1;

  // 11. Transmitting (bool)
  buf.writeUInt8(0, offset);
  offset += 1;

  // 12. Decoding (bool)
  buf.writeUInt8(1, offset);
  offset += 1;

  // 13. Rx DF (quint32, big-endian)
  buf.writeUInt32BE(1000, offset);
  offset += 4;

  // 14. Tx DF (quint32, big-endian)
  buf.writeUInt32BE(1500, offset);
  offset += 4;

  // 15. DE call (utf8)
  offset = writeString('W5XYZ', offset);

  // 16. DE grid (utf8)
  offset = writeString('EM10', offset);

  // 17. DX grid (utf8)
  offset = writeString(dxGrid, offset);

  return buf.slice(0, offset);
}

// Test parsing
console.log('🧪 Testing WSJT-X Parser with corrected magic number\n');

const testBuffer = buildStatusMessage(7074000, 'FT8', 'W5ABC', 'EM12');
console.log(`📦 Built test buffer: ${testBuffer.length} bytes`);
console.log(`   Magic: 0x${testBuffer.readUInt32BE(0).toString(16)}`);
console.log(`   Schema: ${testBuffer.readUInt32BE(4)}`);
console.log(`   Type: ${testBuffer[8]} (STATUS)\n`);

const result = parser.parse(testBuffer);

if (result) {
  console.log('✅ Parser SUCCESS!\n');
  console.log('Parsed result:');
  console.log(`   Type: ${result.type}`);
  console.log(`   DX Call: ${result.dxCall}`);
  console.log(`   DX Grid: ${result.dxGrid}`);
  console.log(`   Mode: ${result.mode}`);
  console.log(`   Dial Frequency: ${result.dialFrequency} Hz (${Number(result.dialFrequency)/1e6} MHz)`);
  console.log(`   TX Enabled: ${result.txEnabled}`);
  console.log(`   Transmitting: ${result.transmitting}`);
  console.log(`   Decoding: ${result.decoding}`);
} else {
  console.log('❌ Parser FAILED to parse the buffer!\n');
  console.log('This could indicate:');
  console.log('   1. Magic number mismatch');
  console.log('   2. Field parsing error');
  console.log('   3. Buffer too short');
}
