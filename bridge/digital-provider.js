// Protocol ownership and per-QSO pairing are independent of UDP/socket I/O.
export function localSourceAllowed(address, interfaces = {}) {
  if (address === '127.0.0.1' || address === '::1') return true;
  return Object.values(interfaces).flat().some(item => item?.address === address);
}
export function providerForClient(id = '') {
  if (id === 'MSHV-OM0RX-AUTO-DX') return 'mshv_auto_dx';
  if (['WSJT-X', 'WSJT-X - OM0RX-WSJT-Z', 'WSJT-Z', 'WSJT-Z - OM0RX-WSJT-Z'].includes(id)) return 'wsjtz';
  return null;
}

export function plannerOwnerForProvider(provider = 'none') {
  if (provider === 'mshv_auto_dx') return 'mshv';
  if (provider === 'wsjtz') return 'om0rx';
  return 'none';
}

export class LoggedQsoCoalescer {
  constructor(upload) {
    this.upload = upload;
    this.recent = new Map();
  }
  key(data) {
    const completed = data.timeOff || data.dateTime || '';
    return [data.provider || 'wsjtz', data.clientId || '', String(data.stationCallsign || '').toUpperCase(), String(data.dxCall || '').toUpperCase(), data.mode || 'FT8', Number(data.dialFrequency || 0), completed].join('|');
  }
  accept(type, data) {
    const key = this.key(data);
    const now = Date.now();
    for (const [entry, value] of this.recent) if (now - value.ts > 10000) this.recent.delete(entry);
    if (this.recent.get(key)?.type === 'LOGGED_ADIF' || (this.recent.has(key) && type !== 'LOGGED_ADIF')) return;
    if (type === 'LOGGED_ADIF') {
      this.recent.set(key, {ts: now, type});
      this.upload(data);
    } else if (type === 'QSO_LOGGED' && !this.recent.has(key)) {
      // Type 5 is the only immediate completion receipt and must reach the
      // backend's durable provisional store before a crash can erase it.
      // Type 12 is still uploaded separately as the authoritative ADIF event.
      this.recent.set(key, {ts: now, type});
      this.upload(data);
    }
  }
  reset() {
    this.recent.clear();
  }
}
