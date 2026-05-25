/**
 * WinKeyerClient - Minimal CW Keyer Serial Interface
 * Extracted from /winkeyer reference implementation
 * Handles serial communication with Winkeyer devices
 */

class WinKeyerClient {
  constructor({ baudRate = 1200, wpm = 20, onLog = () => {}, onRaw = () => {} } = {}) {
    this.baudRate = baudRate;
    this.currentWpm = wpm;
    this.onLog = onLog;
    this.onRaw = onRaw;
    this.onOpen = () => {};
    this.onStatus = () => {};
    this.onPot = () => {};
    this.onEcho = () => {};
    this.onExtended = () => {};
    this._port = null;
    this._reader = null;
    this._writer = null;
    this._realOnEcho = null;
    this.debugMode = false; // Enable debug logging for button presses
  }

  async open() {
    if (!('serial' in navigator)) throw new Error('Web Serial API not available');
    this._port = await navigator.serial.requestPort();
    await this._port.open({ baudRate: this.baudRate });
    this._writer = this._port.writable.getWriter();
    await this._write([0x00, 0x02]); // Admin Open
    this._startReadLoop();
    let rev = null;
    try {
      rev = await this._awaitRevisionByte(800);
    } catch (e) {
      this.onLog('Revision not reported, continuing');
    }
    // Enable pushbutton notifications for hardware button support
    try {
      this.onLog('📤 Sending pushbutton notification command: [0x00, 0x0B, 0x01]');
      await this._write([0x00, 0x0b, 0x01]); // Admin: Set WK2 Mode, enable pushbutton notify
      this.onLog('✅ WK2 mode: pushbutton notify enabled - waiting for button presses...');
      // Give device a moment to process the command
      await new Promise(resolve => setTimeout(resolve, 100));
    } catch (e) {
      this.onLog('❌ Error sending pushbutton command: ' + e.message);
    }
    this.onOpen(rev);
  }

  async disconnect() {
    try {
      if (this._reader) {
        await this._reader.cancel();
        this._reader = null;
      }
    } catch (e) {
      this.onLog('Error canceling reader: ' + e.message);
    }
    try {
      if (this._writer) {
        // Send Host Close command to return device to standalone mode
        await this._write([0x00, 0x03]); // Admin: Host Close
        this.onLog('Host Close command sent');
        this._writer.releaseLock();
        this._writer = null;
      }
    } catch (e) {
      this.onLog('Error releasing writer: ' + e.message);
    }
    try {
      if (this._port) {
        await this._port.close();
        this._port = null;
      }
    } catch (e) {
      this.onLog('Error closing port: ' + e.message);
    }
    this.onLog('Disconnected');
  }

  async _write(arr) {
    if (!this._writer) throw new Error('Not connected');
    await this._writer.write(new Uint8Array(arr));
  }

  async setWpm(w) {
    const v = Math.max(5, Math.min(99, parseInt(w) || 20));
    this.currentWpm = v;
    await this._write([0x02, v]);
    this.onLog('WPM set ' + v);
  }

  async setMode({ paddleEcho = true, serialEcho = true, autospace = false, paddleSwap = false, keyMode = 'IAMBICB' } = {}) {
    let mode = 0;
    if (paddleEcho) mode |= 0b01000000;
    if (paddleSwap) mode |= 0b00100000;
    const keyModes = { IAMBICB: 0b00, IAMBICA: 0b01, ULTIMATIC: 0b10, BUG: 0b11 };
    mode |= (keyModes[keyMode] || 0) << 4;
    if (serialEcho) mode |= 0b00000100;
    if (autospace) mode |= 0b00000010;
    await this._write([0x0e, mode]);
    this.onLog('Mode set (0x' + mode.toString(16) + ')');
  }

  async reset() {
    await this._write([0x00, 0x01]);
  }

  async sendText(text) {
    if (!this._writer) throw new Error('Not connected');
    const bytes = [];
    for (let i = 0; i < text.length; i++) {
      bytes.push(text.charCodeAt(i));
    }
    await this._write(bytes);
  }

  _startReadLoop() {
    const reader = this._port.readable.getReader();
    this._reader = reader;
    (async () => {
      try {
        let extBuf = [];
        let inExtended = false;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          if (!value) continue;
          for (let b of value) {
            this.onRaw(b);
            if (this.debugMode) {
              console.log(`[WK-DEBUG] Raw byte: 0x${b.toString(16).padStart(2, '0')} (${b})`);
            }
            // Extended block start
            if (b === 0xe0) {
              inExtended = true;
              extBuf = [];
              if (this.debugMode) console.log('[WK-DEBUG] Extended block started');
              continue;
            }
            if (inExtended) {
              extBuf.push(b);
              if (this.debugMode) {
                console.log(`[WK-DEBUG] Extended buffer: [${extBuf.map(x => '0x' + x.toString(16).padStart(2, '0')).join(', ')}]`);
              }
              if (extBuf.length >= 4) {
                this._handleExtended(extBuf);
                extBuf = [];
                inExtended = false;
              }
              continue;
            }
            // Status byte C0..FF
            if ((b & 0xc0) === 0xc0) {
              if (this.debugMode) {
                console.log(`[WK-DEBUG] Status byte: 0x${b.toString(16).padStart(2, '0')}`);
              }
              this._handleStatus(b);
              continue;
            }
            // WK1/2 pot: 10xxxxxx (0x80..0xBF)
            if ((b & 0xc0) === 0x80) {
              const raw = b & 0x3f;
              const wpm = Math.round(5 + (raw / 63) * (99 - 5));
              if (this.debugMode) console.log(`[WK-DEBUG] Pot change: ${wpm} WPM`);
              this.onPot(wpm);
              continue;
            }
            // WK3 pot: 0x90..0xFF
            if (b >= 0x90 && b <= 0xff) {
              const wpm = Math.round(((b - 0x90) / (0xff - 0x90)) * (40 - 5) + 5);
              if (this.debugMode) console.log(`[WK-DEBUG] Pot change (WK3): ${wpm} WPM`);
              this.onPot(wpm);
              continue;
            }
            // Printable ASCII
            if ((b >= 0x20 && b <= 0x7e) || b === 0x0a || b === 0x0d) {
              if (this.debugMode) {
                console.log(`[WK-DEBUG] Echo: '${String.fromCharCode(b)}'`);
              }
              if (this._realOnEcho) this._realOnEcho(String.fromCharCode(b));
              else this.onEcho(String.fromCharCode(b));
            } else if (this.debugMode) {
              // Log any unrecognized bytes that might be button press data
              console.warn(`[WK-DEBUG-UNRECOGNIZED] Byte: 0x${b.toString(16).padStart(2, '0')} (${b}) - might be button data`);
            }
          }
        }
      } catch (e) {
        this.onLog('Read error: ' + e.message);
      } finally {
        reader.releaseLock();
      }
    })();
  }

  _handleStatus(b) {
    const tag = (b >> 6) & 3;
    const keyDown = !!(b & 0x08);
    const busy = !!(b & 0x04);
    const breakIn = !!(b & 0x02);
    const xoff = !!(b & 0x01);
    // Pass the raw byte for button identification
    this.onStatus({ tag, keyDown, busy, breakIn, xoff, rawByte: b });
  }

  _handleExtended(bytes) {
    const b1 = bytes[0],
      b2 = bytes[1],
      b3 = bytes[2],
      b4 = bytes[3];
    const paddleLeft = !!(b1 & 0x01);
    const paddleRight = !!(b1 & 0x02);
    const wpm = b2;
    const sidetone = b3 * 10;
    const flags = b4;
    this.onExtended({ paddleLeft, paddleRight, wpm, sidetone, flags });
  }

  async _awaitRevisionByte(timeout = 800) {
    return new Promise((resolve, reject) => {
      let done = false;
      const t = setTimeout(() => {
        if (!done) {
          done = true;
          reject(new Error('rev timeout'));
        }
      }, timeout);
      const prev = this.onEcho;
      this._realOnEcho = prev;
      this.onEcho = (ch) => {
        if (!done) {
          done = true;
          clearTimeout(t);
          this.onEcho = prev;
          resolve(ch.charCodeAt(0));
        }
      };
    });
  }
}