const MAGIC = 0xadbccbda;
const DEFAULT_SCHEMA = 3;

const MESSAGE_TYPES = Object.freeze({
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
  WSPR_DECODE: 10,
  LOCATION: 11,
  LOGGED_ADIF: 12,
  HIGHLIGHT_CALLSIGN: 13,
  SWITCH_CONFIGURATION: 14,
  CONFIGURE: 15,
  ANNOTATION_INFO: 16,
  OM0RX_START_TARGET_QSO: 17,
});

class QtStreamWriter {
  constructor() {
    this.parts = [];
  }

  buffer() {
    return Buffer.concat(this.parts);
  }

  writeUInt8(value) {
    const buf = Buffer.alloc(1);
    buf.writeUInt8(Number(value) & 0xff, 0);
    this.parts.push(buf);
    return this;
  }

  writeBool(value) {
    return this.writeUInt8(value ? 1 : 0);
  }

  writeUInt32(value) {
    const buf = Buffer.alloc(4);
    buf.writeUInt32BE(Number(value) >>> 0, 0);
    this.parts.push(buf);
    return this;
  }

  writeInt32(value) {
    const buf = Buffer.alloc(4);
    buf.writeInt32BE(Number(value) || 0, 0);
    this.parts.push(buf);
    return this;
  }

  writeUInt64(value) {
    const buf = Buffer.alloc(8);
    buf.writeBigUInt64BE(BigInt(value || 0), 0);
    this.parts.push(buf);
    return this;
  }

  writeDouble(value) {
    const buf = Buffer.alloc(8);
    buf.writeDoubleBE(Number(value) || 0, 0);
    this.parts.push(buf);
    return this;
  }

  writeByteArray(value) {
    const data = Buffer.from(value == null ? '' : String(value), 'utf8');
    this.writeUInt32(data.length);
    this.parts.push(data);
    return this;
  }

  writeQTime(value) {
    return this.writeUInt32(normalizeQTime(value));
  }
}

function normalizeQTime(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, Math.min(86399999, Math.trunc(value)));
  }

  const text = String(value || '').trim();
  const match = text.match(/^(\d{2})(?::?(\d{2}))(?::?(\d{2}))?(?:\.(\d{1,3}))?$/);
  if (!match) {
    return 0;
  }

  const hours = Number(match[1] || 0);
  const minutes = Number(match[2] || 0);
  const seconds = Number(match[3] || 0);
  const millis = Number((match[4] || '').padEnd(3, '0') || 0);
  return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis;
}

function beginMessage(type, id = 'WSJT-X', schema = DEFAULT_SCHEMA) {
  const writer = new QtStreamWriter();
  writer.writeUInt32(MAGIC);
  writer.writeUInt32(schema);
  writer.writeUInt32(type);
  writer.writeByteArray(id || 'WSJT-X');
  return writer;
}

function buildClear({ id, window = 0, schema } = {}) {
  return beginMessage(MESSAGE_TYPES.CLEAR, id, schema).writeUInt8(window).buffer();
}

function buildReplay({ id, schema } = {}) {
  return beginMessage(MESSAGE_TYPES.REPLAY, id, schema).buffer();
}

function buildHaltTx({ id, autoOnly = false, schema } = {}) {
  return beginMessage(MESSAGE_TYPES.HALT_TX, id, schema).writeBool(autoOnly).buffer();
}

function buildFreeText({ id, text = '', send = true, schema } = {}) {
  return beginMessage(MESSAGE_TYPES.FREE_TEXT, id, schema)
    .writeByteArray(text)
    .writeBool(send)
    .buffer();
}

function buildLocation({ id, location = '', schema } = {}) {
  return beginMessage(MESSAGE_TYPES.LOCATION, id, schema).writeByteArray(location).buffer();
}

function buildSwitchConfiguration({ id, configuration = '', schema } = {}) {
  return beginMessage(MESSAGE_TYPES.SWITCH_CONFIGURATION, id, schema)
    .writeByteArray(configuration)
    .buffer();
}

function buildConfigure({
  id,
  mode = '',
  frequencyTolerance = 0xffffffff,
  submode = '',
  fastMode = false,
  trPeriod = 0xffffffff,
  rxDf = 0xffffffff,
  dxCall = '',
  dxGrid = '',
  generateMessages = false,
  schema,
} = {}) {
  return beginMessage(MESSAGE_TYPES.CONFIGURE, id, schema)
    .writeByteArray(mode)
    .writeUInt32(frequencyTolerance)
    .writeByteArray(submode)
    .writeBool(fastMode)
    .writeUInt32(trPeriod)
    .writeUInt32(rxDf)
    .writeByteArray(dxCall)
    .writeByteArray(dxGrid)
    .writeBool(generateMessages)
    .buffer();
}

function buildReply({
  id,
  time = 0,
  snr = 0,
  deltaTime = 0,
  deltaFrequency = 1500,
  mode = 'FT8',
  message = '',
  lowConfidence = false,
  modifiers = 0,
  schema,
} = {}) {
  return beginMessage(MESSAGE_TYPES.REPLY, id, schema)
    .writeQTime(time)
    .writeInt32(snr)
    .writeDouble(deltaTime)
    .writeUInt32(deltaFrequency)
    .writeByteArray(mode)
    .writeByteArray(message)
    .writeBool(lowConfidence)
    .writeUInt8(modifiers)
    .buffer();
}

function buildOm0rxStartTargetQso({ id, target = {}, schema } = {}) {
  const payload = JSON.stringify({
    version: 1,
    target,
  });
  return beginMessage(MESSAGE_TYPES.OM0RX_START_TARGET_QSO, id, schema)
    .writeByteArray(payload)
    .buffer();
}

function buildCommand(command, payload = {}) {
  switch (command) {
    case 'clear':
      return buildClear(payload);
    case 'replay':
      return buildReplay(payload);
    case 'halt_tx':
      return buildHaltTx(payload);
    case 'free_text':
      return buildFreeText(payload);
    case 'location':
      return buildLocation(payload);
    case 'switch_configuration':
      return buildSwitchConfiguration(payload);
    case 'configure':
      return buildConfigure(payload);
    case 'reply':
      return buildReply(payload);
    case 'start_target_qso':
      return buildOm0rxStartTargetQso(payload);
    default:
      throw new Error(`Unsupported WSJT-X command: ${command}`);
  }
}

export {
  MAGIC,
  DEFAULT_SCHEMA,
  MESSAGE_TYPES,
  QtStreamWriter,
  normalizeQTime,
  buildClear,
  buildReplay,
  buildHaltTx,
  buildFreeText,
  buildLocation,
  buildSwitchConfiguration,
  buildConfigure,
  buildReply,
  buildOm0rxStartTargetQso,
  buildCommand,
};
