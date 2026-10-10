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
  CLEAR: 3,
  REPLY: 4,
  QSO_LOGGED: 5,
  CLOSE: 6,
  REPLAY: 7,
  HALT_TX: 8,
  FREE_TEXT: 9,
  LOCATION: 11,
  LOGGED_ADIF: 12,
  HIGHLIGHT_CALLSIGN: 13,
  SWITCH_CONFIGURATION: 14,
  CONFIGURE: 15,
  ANNOTATION_INFO: 16
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
        
        case MESSAGE_TYPES.QSO_LOGGED: // 5
          return this.parseQsoLogged(buffer, offset, msg);

        case MESSAGE_TYPES.LOGGED_ADIF: // 12
          return this.parseLoggedAdif(buffer, offset, msg);
        
        case MESSAGE_TYPES.DECODE: // 2
          return this.parseDecode(buffer, offset, msg);
        
        default:
          this.parseMessageId(buffer, offset, msg);
          return msg;
      }
    } catch (e) {
      return null;
    }
  }

  parseMessageId(buffer, offset, msg) {
    const result = this.readString(buffer, offset);
    msg.id = result.str;
    return msg;
  }

  readString(buffer, offset) {
    if (offset + 4 > buffer.length) return { str: '', offset, complete: false };
    
    const len = buffer.readUInt32BE(offset);
    offset += 4;
    
    if (offset + len > buffer.length) return { str: '', offset, complete: false };
    
    const str = buffer.toString('utf8', offset, offset + len);
    offset += len;
    
    return { str, offset, complete: true };
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
      msg.id = result.str;
      offset = result.offset;
      if (!result.complete) return msg;

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

      // 15+. Later WSJT-X schemas append fields after DX grid. Keep parsing
      // optional fields so OM0RX-patched WSJT-Z can expose a direct QSO state
      // heartbeat while stock clients remain compatible.
      if (offset < buffer.length) {
        msg.watchdogTimeout = buffer[offset] !== 0;
        offset++;
      }

      if (offset < buffer.length) {
        result = this.readString(buffer, offset);
        msg.subMode = result.str;
        offset = result.offset;
      }

      if (offset < buffer.length) {
        msg.fastMode = buffer[offset] !== 0;
        offset++;
      }

      if (offset < buffer.length) {
        msg.specialOpMode = buffer[offset];
        offset++;
      }

      if (offset + 4 <= buffer.length) {
        msg.frequencyTolerance = buffer.readUInt32BE(offset);
        offset += 4;
      }

      if (offset + 4 <= buffer.length) {
        msg.trPeriod = buffer.readUInt32BE(offset);
        offset += 4;
      }

      if (offset < buffer.length) {
        result = this.readString(buffer, offset);
        msg.configurationName = result.str;
        offset = result.offset;
      }

      if (offset < buffer.length) {
        result = this.readString(buffer, offset);
        msg.txMessage = result.str;
        offset = result.offset;
      }

      if (offset < buffer.length) {
        result = this.readString(buffer, offset);
        msg.qsoState = result.str;
        offset = result.offset;
      }

      return msg;
    } catch (e) {
      return msg;
    }
  }

  parseQsoLogged(buffer, offset, msg) {
    try {
      // Per NetworkMessage.hpp "QSO Logged" message format (type 5):
      
      // 1. Id (unique key) - utf8
      let result = this.readString(buffer, offset);
      msg.id = result.str;
      offset = result.offset;
      if (!result.complete) return msg;

      // 2. Date & Time Off - QDateTime (complex: need to skip)
      // QDateTime has: QDate (qint64) + QTime (quint32) + timespec (quint8) + optional offset
      // For now, we'll skip by looking for the pattern - just advance past it
      if (offset + 13 > buffer.length) return msg;
      const julianDay = Number(buffer.readBigInt64BE(offset));
      const milliseconds = buffer.readUInt32BE(offset + 8);
      const spec = buffer.readUInt8(offset + 12);
      if (spec === 2 && offset + 17 > buffer.length) return msg;
      const zoneSeconds = spec === 2 ? buffer.readInt32BE(offset + 13) : 0;
      // UTC and fixed-offset QDateTime; local/timezone values are left unset
      // instead of inventing a UTC time that would defeat durable dedupe.
      if ((spec === 1 || spec === 2) && julianDay > 0 && milliseconds < 86400000) {
        msg.dateTime = new Date((julianDay - 2440588) * 86400000 + milliseconds - zoneSeconds * 1000).toISOString();
        msg.timeOff = msg.dateTime;
      }
      offset += spec === 2 ? 17 : 13;

      // 3. DX call - utf8
      result = this.readString(buffer, offset);
      msg.dxCall = result.str;
      offset = result.offset;
      if (!result.complete) return msg;

      // 4. DX grid - utf8
      result = this.readString(buffer, offset);
      msg.dxGrid = result.str;
      offset = result.offset;
      if (!result.complete) return msg;

      // 5. Tx frequency (Hz) - quint64
      if (offset + 8 > buffer.length) return msg;
      msg.dialFrequency = Number(buffer.readBigInt64BE(offset));
      offset += 8;

      // 6. Mode - utf8
      result = this.readString(buffer, offset);
      msg.mode = result.str;
      offset = result.offset;
      if (!result.complete) return msg;

      // 7. Report sent - utf8
      result = this.readString(buffer, offset);
      msg.reportSent = result.str;
      offset = result.offset;
      if (!result.complete) return msg;

      // 8. Report received - utf8
      result = this.readString(buffer, offset);
      msg.reportReceived = result.str;
      offset = result.offset;

      return msg;
    } catch (e) {
      return msg;
    }
  }

  parseLoggedAdif(buffer, offset, msg) {
    try {
      let result = this.readString(buffer, offset);
      msg.id = result.str;
      offset = result.offset;

      result = this.readString(buffer, offset);
      msg.adifText = result.str;
      this.applyAdifFields(msg, msg.adifText);
      return msg;
    } catch (e) {
      return msg;
    }
  }

  applyAdifFields(msg, adifText) {
    const fields = {};
    const re = /<([^:>]+):(\d+)(?::[^>]*)?>([^<]*)/gi;
    let match;
    while ((match = re.exec(adifText || ''))) {
      const name = String(match[1] || '').trim().toLowerCase();
      const length = Number(match[2] || 0);
      fields[name] = String(match[3] || '').slice(0, length).trim();
    }

    msg.dxCall = fields.call || msg.dxCall || '';
    msg.dxGrid = fields.gridsquare || msg.dxGrid || '';
    msg.mode = fields.mode || msg.mode || '';
    if (fields.submode) msg.mode = fields.submode;
    msg.reportSent = fields.rst_sent || msg.reportSent || '';
    msg.reportReceived = fields.rst_rcvd || msg.reportReceived || '';
    if (fields.freq) {
      const mhz = Number(fields.freq);
      if (Number.isFinite(mhz)) {
        msg.dialFrequency = Math.round(mhz * 1_000_000);
      }
    }
    if (fields.qso_date && fields.time_on) {
      const date = String(fields.qso_date).replace(/\D/g, '').slice(0, 8);
      const clock = String(fields.time_on).replace(/\D/g, '').padEnd(6, '0').slice(0, 6);
      if (date.length === 8 && clock.length === 6) {
        const iso = `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}T${clock.slice(0, 2)}:${clock.slice(2, 4)}:${clock.slice(4, 6)}Z`;
        const parsed = new Date(iso);
        if (!Number.isNaN(parsed.getTime())) {
          msg.dateTime = parsed.toISOString();
          msg.timeOn = msg.dateTime;
        }
      }
    }
    if (fields.qso_date_off && fields.time_off) {
      const date = String(fields.qso_date_off).replace(/\D/g, '').slice(0, 8);
      const clock = String(fields.time_off).replace(/\D/g, '').padEnd(6, '0').slice(0, 6);
      if (date.length === 8 && clock.length === 6) {
        const parsed = new Date(`${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}T${clock.slice(0, 2)}:${clock.slice(2, 4)}:${clock.slice(4, 6)}Z`);
        if (!Number.isNaN(parsed.getTime())) msg.timeOff = parsed.toISOString();
      }
    } else if (fields.time_off && fields.qso_date) {
      const date = String(fields.qso_date).replace(/\D/g, '').slice(0, 8);
      const clock = String(fields.time_off).replace(/\D/g, '').padEnd(6, '0').slice(0, 6);
      const parsed = new Date(`${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}T${clock.slice(0, 2)}:${clock.slice(2, 4)}:${clock.slice(4, 6)}Z`);
      if (!Number.isNaN(parsed.getTime())) msg.timeOff = parsed.toISOString();
    }
  }

  parseDecode(buffer, offset, msg) {
    try {
      // Per NetworkMessage.hpp "Decode" message format (type 2):
      
      // 1. Id (unique key) - utf8
      let result = this.readString(buffer, offset);
      msg.id = result.str;
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
