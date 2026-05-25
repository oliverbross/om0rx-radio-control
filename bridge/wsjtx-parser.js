/**
 * Minimal WSJT-X UDP Protocol Parser
 * Parses binary WSJT-X messages without external dependencies
 * 
 * WSJT-X sends Status messages containing:
 * - Dial frequency
 * - Mode
 * - DX Call
 * - DX Grid
 * 
 * And LoggedAdif messages when a QSO is logged
 */

const MAGIC = 0xadbccbda;
const MESSAGE_TYPES = {
  HEARTBEAT: 0,
  STATUS: 1,
  DECODE: 2,
  LOGGED_ADIF: 5,
  CLOSE: 6,
  REPLY: 7,
  HALT_TX: 8,
  FREE_TEXT: 9,
  LOCATION: 11,
  LOGGED_ADIF_V2: 14
};

class WsjtxParser {
  parse(buffer) {
    try {
      if (buffer.length < 12) {
        return null;
      }

      // Read magic number (4 bytes, big-endian)
      const magic = buffer.readUInt32BE(0);
      if (magic !== MAGIC) {
        return null;
      }

      // Read schema (4 bytes, big-endian)
      const schema = buffer.readUInt32BE(4);

      // Read message type (4 bytes, big-endian, quint32 in Qt format)
      // NOTE: Per NetworkMessage.hpp, msgType is a quint32, not a byte!
      const msgType = buffer.readUInt32BE(8);
      const typeName = Object.keys(MESSAGE_TYPES).find(
        k => MESSAGE_TYPES[k] === msgType
      ) || `UNKNOWN_${msgType}`;

      let offset = 12;  // Payload data starts after magic (4) + schema (4) + msgType (4)
      const msg = { type: typeName, msgType };

      // Parse based on message type
      switch (msgType) {
        case MESSAGE_TYPES.STATUS: // 1
          return this.parseStatus(buffer, offset, msg);
        
        case MESSAGE_TYPES.LOGGED_ADIF: // 5
          return this.parseLoggedAdif(buffer, offset, msg);
        
        case MESSAGE_TYPES.LOGGED_ADIF_V2: // 14
          return this.parseLoggedAdifV2(buffer, offset, msg);
        
        case MESSAGE_TYPES.DECODE: // 2
          return this.parseDecode(buffer, offset, msg);
        
        default:
          return msg;
      }
    } catch (e) {
      return null;
    }
  }

  readString(buffer, offset) {
    if (offset + 4 > buffer.length) return { str: '', offset };
    
    const len = buffer.readUInt32BE(offset);
    offset += 4;
    
    if (offset + len > buffer.length) return { str: '', offset };
    
    const str = buffer.toString('utf8', offset, offset + len);
    offset += len;
    
    return { str, offset };
  }

  readUInt64(buffer, offset) {
    const high = buffer.readUInt32BE(offset);
    const low = buffer.readUInt32BE(offset + 4);
    return { value: high * 0x100000000 + low, offset: offset + 8 };
  }

  parseStatus(buffer, offset, msg) {
    try {
      // Per NetworkMessage.hpp Status message format:
      
      // 1. Id (utf8)
      let result = this.readString(buffer, offset);
      offset = result.offset;

      // 2. Dial Frequency (quint64 - Hz)
      if (offset + 8 <= buffer.length) {
        msg.dialFrequency = Number(buffer.readBigInt64BE(offset));
        offset += 8;
      }

      // 3. Mode (utf8)
      result = this.readString(buffer, offset);
      msg.mode = result.str;
      offset = result.offset;

      // 4. DX call (utf8)
      result = this.readString(buffer, offset);
      msg.dxCall = result.str;
      offset = result.offset;

      // 5. Report (utf8)
      result = this.readString(buffer, offset);
      msg.report = result.str;
      offset = result.offset;

      // 6. Tx Mode (utf8)
      result = this.readString(buffer, offset);
      msg.txMode = result.str;
      offset = result.offset;

      // 7. Tx Enabled (bool)
      if (offset < buffer.length) {
        msg.txEnabled = buffer[offset] !== 0;
        offset++;
      }

      // 8. Transmitting (bool)
      if (offset < buffer.length) {
        msg.transmitting = buffer[offset] !== 0;
        offset++;
      }

      // 9. Decoding (bool)
      if (offset < buffer.length) {
        msg.decoding = buffer[offset] !== 0;
        offset++;
      }

      // 10. Rx DF (quint32)
      if (offset + 4 <= buffer.length) {
        msg.rxDf = buffer.readUInt32BE(offset);
        offset += 4;
      }

      // 11. Tx DF (quint32)
      if (offset + 4 <= buffer.length) {
        msg.txDf = buffer.readUInt32BE(offset);
        offset += 4;
      }

      // 12. DE call (utf8)
      result = this.readString(buffer, offset);
      msg.deCall = result.str;
      offset = result.offset;

      // 13. DE grid (utf8)
      result = this.readString(buffer, offset);
      msg.deGrid = result.str;
      offset = result.offset;

      // 14. DX grid (utf8)
      result = this.readString(buffer, offset);
      msg.dxGrid = result.str;
      offset = result.offset;

      return msg;
    } catch (e) {
      return msg;
    }
  }

  parseLoggedAdif(buffer, offset, msg) {
    try {
      // Per NetworkMessage.hpp "QSO Logged" message format (type 5):
      
      // 1. Id (unique key) - utf8
      let result = this.readString(buffer, offset);
      offset = result.offset;

      // 2. Date & Time Off - QDateTime (complex: need to skip)
      // QDateTime has: QDate (qint64) + QTime (quint32) + timespec (quint8) + optional offset
      // For now, we'll skip by looking for the pattern - just advance past it
      if (offset + 8 <= buffer.length) {
        offset += 8; // QDate as qint64
      }
      if (offset + 4 <= buffer.length) {
        offset += 4; // QTime as quint32
      }
      if (offset < buffer.length) {
        const timespec = buffer[offset];
        offset++; // timespec as quint8
        // If timespec==2, there's an offset (qint32)
        if (timespec === 2 && offset + 4 <= buffer.length) {
          offset += 4; // offset as qint32
        }
      }

      // 3. DX call - utf8
      result = this.readString(buffer, offset);
      msg.dxCall = result.str;
      offset = result.offset;

      // 4. DX grid - utf8
      result = this.readString(buffer, offset);
      msg.dxGrid = result.str;
      offset = result.offset;

      // 5. Tx frequency (Hz) - quint64
      if (offset + 8 <= buffer.length) {
        msg.dialFrequency = Number(buffer.readBigInt64BE(offset));
        offset += 8;
      }

      // 6. Mode - utf8
      result = this.readString(buffer, offset);
      msg.mode = result.str;
      offset = result.offset;

      // 7. Report sent - utf8
      result = this.readString(buffer, offset);
      msg.reportSent = result.str;
      offset = result.offset;

      // 8. Report received - utf8
      result = this.readString(buffer, offset);
      msg.reportReceived = result.str;
      offset = result.offset;

      return msg;
    } catch (e) {
      return msg;
    }
  }

  parseLoggedAdifV2(buffer, offset, msg) {
    // V2 has the same structure as V1
    return this.parseLoggedAdif(buffer, offset, msg);
  }

  parseDecode(buffer, offset, msg) {
    try {
      // Per NetworkMessage.hpp "Decode" message format (type 2):
      
      // 1. Id (unique key) - utf8
      let result = this.readString(buffer, offset);
      offset = result.offset;

      // 2. New - bool
      if (offset < buffer.length) {
        msg.isNew = buffer[offset] !== 0;
        offset++;
      }

      // 3. Time - QTime (quint32 - milliseconds since midnight)
      if (offset + 4 <= buffer.length) {
        msg.time = buffer.readUInt32BE(offset);
        offset += 4;
      }

      // 4. snr - qint32
      if (offset + 4 <= buffer.length) {
        msg.snr = buffer.readInt32BE(offset);
        offset += 4;
      }

      // 5. Delta time (S) - float (serialized as double, so 8 bytes, big-endian in Qt QDataStream)
      if (offset + 8 <= buffer.length) {
        msg.deltaTime = buffer.readDoubleBE(offset);
        offset += 8;
      }

      // 6. Delta frequency (Hz) - quint32
      if (offset + 4 <= buffer.length) {
        msg.deltaFrequency = buffer.readUInt32BE(offset);
        offset += 4;
      }

      // 7. Mode - utf8
      result = this.readString(buffer, offset);
      msg.mode = result.str;
      offset = result.offset;

      // 8. Message - utf8
      result = this.readString(buffer, offset);
      msg.message = result.str;
      offset = result.offset;

      // 9. Low confidence - bool
      if (offset < buffer.length) {
        msg.lowConfidence = buffer[offset] !== 0;
        offset++;
      }

      // 10. Off air - bool
      if (offset < buffer.length) {
        msg.offAir = buffer[offset] !== 0;
        offset++;
      }

      return msg;
    } catch (e) {
      return msg;
    }
  }
}

export { WsjtxParser };
