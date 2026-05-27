# flex_radio.py - FlexRadio SmartSDR TCP API client classes

import logging
import socket
import time

class FlexSpots:
    def __init__(self, host: str, port: int):
        self.host = host; self.port = int(port); self.sock=None; self.seq=100
    def connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=3.0)
            self.sock.settimeout(1.0)
            try: self.sock.recv(1024); self.sock.recv(1024)
            except Exception: pass
            logging.info("Flex TCP connected: %s:%s", self.host, self.port)
            return True
        except Exception as e:
            logging.warning("Flex TCP connect failed: %s", e); self.sock=None; return False
    @staticmethod
    def _enc(v:str)->str: return (v or "").replace(" ", "\x7F")
    def add_spot(self, rx_mhz, callsign, mode, source, spotter, comment, lifetime=3600, priority=3, color=None, ts_epoch=None):
        if not self.sock: return False
        self.seq+=1; ts = ts_epoch if ts_epoch is not None else int(time.time())
        parts=[
            f"C{self.seq}|spot add", f"rx_freq={rx_mhz:.6f}",
            f"callsign={self._enc(callsign)}", f"mode={self._enc(mode)}",
            f"source={self._enc(source)}", f"spotter_callsign={self._enc(spotter)}",
            f"timestamp={ts}", f"lifetime_seconds={int(lifetime)}",
            f"priority={int(priority)}", f"comment={self._enc(comment)}",
        ]
        if color: parts.append(f"color={color}")
        try:
            self.sock.sendall((" ".join(parts) + "\r").encode("ascii", errors="ignore"))
            try:
                resp=self.sock.recv(256).decode(errors="ignore").strip()
                if resp: logging.debug("Flex RESP: %s", resp)
            except Exception: pass
            return True
        except Exception as e:
            logging.warning("Flex TCP send failed: %s", e); return False
    def close(self):
        if self.sock:
            try: self.sock.close()
            except: pass
            self.sock=None



class FlexCtl:
    """
    Minimal SmartSDR TCP client for one slice (default: Slice A = id 0).
    Connects to FlexRadio via TCP port 4992, sends commands, parses status messages.
    
    Based on official SmartSDR API:
    https://github.com/flexradio/smartsdr-api-docs/wiki/SmartSDR-TCPIP-API
    """
    
    DEFAULT_BAND_FREQS = {
        '160m': 1.840000, '80m': 3.650000, '60m': 5.357000, '40m': 7.074000,
        '30m': 10.120000, '20m': 14.074000, '17m': 18.100000, '15m': 21.074000,
        '12m': 24.915000, '10m': 28.074000, '6m': 50.313000
    }
    
    def __init__(self, host: str, port: int, slice_id: int = 0):
        import socket as _s
        self.host, self.port = host, int(port)
        self.slice_id = int(slice_id)
        self.sock = None
        self.seq = 1000
        self._socket_mod = _s
        # Slice state tracking
        self.current_filter_lo = None
        self.current_filter_hi = None
        self.current_freq = None
        self.current_mode = None
        self.current_volume = None  # Volume/audio_level
        # Transmit state tracking (for 2-way sync)
        self.current_rfpower = None
        self.current_tunepower = None
        self.current_miclevel = None
        self.current_vox_enable = None
        self.current_mox = None  # MOX state
        self.current_break_in = None
        # State change tracking (for UI updates)
        self.last_state_changed = {}
        # Subscription timeout - re-subscribe if we haven't heard from radio in a while
        self.last_subscription_time = 0
        self.last_resubscribe_time = 0
        self.last_radio_message_time = 0
        logging.info(f"FlexCtl initialized for {host}:{port} slice {slice_id}")

    def connect(self) -> bool:
        """Connect to SmartSDR TCP API if not already connected."""
        if self.sock:
            return True
        try:
            logging.info(f"FlexCtl connecting to {self.host}:{self.port}...")
            self.sock = self._socket_mod.create_connection((self.host, self.port), timeout=3.0)
            self.sock.settimeout(1.0)
            
            # Read version and handle
            try:
                greeting = self.sock.recv(512).decode(errors="ignore")
                logging.debug(f"FlexCtl GREETING: {greeting.strip()}")
            except Exception as e:
                logging.warning(f"FlexCtl greeting read error: {e}")
            
            # Identify and subscribe
            self._send("client station=OM0RX")
            self._send("sub slice all")
            self._send("sub radio all")
            self._send("sub tx all")
            self._send("sub transmit all")
            self.last_resubscribe_time = time.time()
            
            # Test: Try to read subscription confirmation
            self.sock.settimeout(0.5)
            try:
                test_resp = self.sock.recv(4096).decode(errors="ignore")
                logging.info(f"🔌 POST-SUBSCRIPTION MSG: {test_resp[:300] if test_resp else 'NO RESPONSE'}")
            except socket.timeout:
                logging.warning("⚠️  No subscription confirmation received (timeout)")
            except Exception as e:
                logging.warning(f"⚠️  Error reading subscription confirm: {e}")
            
            self.sock.settimeout(1.0)
            
            logging.info("FlexCtl connected successfully")
            return True
        except Exception as e:
            logging.error(f"FlexCtl connect FAILED: {e}")
            self.sock = None
            return False

    def _send(self, cmd: str) -> bool:
        """Send command to radio, return True if successful."""
        if not self.connect():
            return False
        try:
            self.seq += 1
            wire = f"C{self.seq}|{cmd}\r"
            logging.debug(f"FlexCtl SEND: {cmd}")
            self.sock.sendall(wire.encode("ascii", errors="ignore"))
            
            # Try to read response
            try:
                resp = self.sock.recv(512).decode(errors="ignore").strip()
                if resp:
                    logging.debug(f"FlexCtl RECV: {resp}")
                    
                    # Update mode, filter, and frequency tracking from status messages
                    if "|slice" in resp and f"slice {self.slice_id} " in resp:
                        import re as _re
                        m_mode = _re.search(r"\bmode=([A-Z]+)", resp)
                        if m_mode:
                            self.current_mode = m_mode.group(1)
                            logging.debug(f"FlexCtl: Updated current_mode={self.current_mode}")
                        
                        # Track frequency
                        m_freq = _re.search(r"\bRF_frequency=([\d.]+)", resp)
                        if m_freq:
                            self.current_freq = float(m_freq.group(1))
                            logging.debug(f"FlexCtl: Updated current_freq={self.current_freq} MHz")
                        
                        # Track filter changes
                        m_flo = _re.search(r"\bfilter_lo=(-?\d+)", resp)
                        if m_flo:
                            self.current_filter_lo = int(m_flo.group(1))
                            logging.debug(f"FlexCtl: Updated current_filter_lo={self.current_filter_lo}")
                        
                        m_fhi = _re.search(r"\bfilter_hi=(-?\d+)", resp)
                        if m_fhi:
                            self.current_filter_hi = int(m_fhi.group(1))
                            logging.debug(f"FlexCtl: Updated current_filter_hi={self.current_filter_hi}")
                    
                    # Check for error responses
                    if resp.startswith("R") and "|" in resp:
                        parts = resp.split("|", 3)
                        if len(parts) >= 2:
                            hex_resp = parts[1]
                            if hex_resp != "00000000" and hex_resp != "0":
                                logging.warning(f"FlexCtl command '{cmd}' returned error: {hex_resp}")
                                return False  # Return False on error!
            except Exception as e:
                logging.debug(f"FlexCtl recv exception (may be normal): {e}")
            
            return True
        except Exception as e:
            logging.error(f"FlexCtl send FAILED for '{cmd}': {e}")
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            return False

    def get_current_levels(self, timeout: float = 1.5):
        """
        Query radio for current state and return dict with:
        - audio_level: volume 0-100
        - rfpower: TX power 1-100
        - tunepower: tune power 1-100
        - miclevel: mic level 0-100
        - filter_lo, filter_hi: filter edges in Hz
        - freq: current frequency in MHz
        - mode: current mode (USB, LSB, etc)
        """
        if not self.connect():
            logging.warning("FlexCtl get_current_levels: not connected")
            return {}
        
        logging.info("FlexCtl querying radio for initial state...")
        
        try:
            # Request current state
            self._send(f"slice list")
            self._send(f"sub slice all")
            self._send(f"sub tx all")
            self._send(f"sub transmit all")
        except Exception as e:
            logging.warning(f"FlexCtl get_current_levels: send error: {e}")
        
        # Collect responses for a while
        import time as _t, re as _re
        end = _t.time() + float(timeout)
        buf = b""
        levels = {}
        
        try:
            self.sock.settimeout(0.15)
        except Exception:
            pass
        
        while _t.time() < end:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    continue
                buf += chunk
                
                # Process complete lines
                while b"\n" in buf or b"\r" in buf:
                    m = _re.search(rb"[\r\n]+", buf)
                    if not m:
                        break
                    line = buf[:m.start()].decode(errors="ignore").strip()
                    buf = buf[m.end():]
                    
                    if not line:
                        continue
                    
                    logging.debug(f"FlexCtl STATUS: {line}")
                    
                    # Parse slice status messages: S<handle>|slice <id> key=val key=val...
                    if "|slice " in line and f"slice {self.slice_id} " in line:
                        # Extract key=value pairs
                        match = _re.search(rf"\|slice\s+{self.slice_id}\s+(.+)$", line)
                        if match:
                            kvs = match.group(1)
                            
                            # audio_level (NOT audio_gain)
                            m_vol = _re.search(r"\baudio_level=(\d+)", kvs)
                            if m_vol:
                                levels["audio_level"] = int(m_vol.group(1))
                                logging.debug(f"  Parsed audio_level={levels['audio_level']}")
                            
                            # filter_lo and filter_hi
                            m_flo = _re.search(r"\bfilter_lo=(-?\d+)", kvs)
                            if m_flo:
                                levels["filter_lo"] = int(m_flo.group(1))
                                logging.debug(f"  Parsed filter_lo={levels['filter_lo']}")
                            
                            m_fhi = _re.search(r"\bfilter_hi=(-?\d+)", kvs)
                            if m_fhi:
                                levels["filter_hi"] = int(m_fhi.group(1))
                                logging.debug(f"  Parsed filter_hi={levels['filter_hi']}")
                            
                            # freq
                            m_freq = _re.search(r"\bRF_frequency=([\d.]+)", kvs)
                            if m_freq:
                                levels["freq"] = float(m_freq.group(1))
                                logging.debug(f"  Parsed freq={levels['freq']}")
                            
                            # mode
                            m_mode = _re.search(r"\bmode=([A-Z]+)", kvs)
                            if m_mode:
                                levels["mode"] = m_mode.group(1)
                                logging.debug(f"  Parsed mode={levels['mode']}")
                            
                            # RIT/XIT
                            m_rit_on = _re.search(r"\brit_on=([01])", kvs)
                            if m_rit_on:
                                levels["rit_on"] = bool(int(m_rit_on.group(1)))
                            
                            m_rit_freq = _re.search(r"\brit_freq=(-?\d+)", kvs)
                            if m_rit_freq:
                                levels["rit_freq"] = int(m_rit_freq.group(1))
                            
                            m_xit_on = _re.search(r"\bxit_on=([01])", kvs)
                            if m_xit_on:
                                levels["xit_on"] = bool(int(m_xit_on.group(1)))
                            
                            m_xit_freq = _re.search(r"\bxit_freq=(-?\d+)", kvs)
                            if m_xit_freq:
                                levels["xit_freq"] = int(m_xit_freq.group(1))
                            
                            # AGC mode and threshold
                            m_agc = _re.search(r"\bagc_mode=(\w+)", kvs)
                            if m_agc:
                                levels["agc_mode"] = m_agc.group(1)
                            
                            m_agc_thresh = _re.search(r"\bagc_threshold=(\d+)", kvs)
                            if m_agc_thresh:
                                levels["agc_threshold"] = int(m_agc_thresh.group(1))
                            
                            # Tuning step
                            m_step = _re.search(r"\bstep=(\d+)", kvs)
                            if m_step:
                                levels["step"] = int(m_step.group(1))
                            
                            # DSP controls
                            m_nb = _re.search(r"\bnb_on=([01])", kvs)
                            if m_nb:
                                levels["nb"] = bool(int(m_nb.group(1)))
                            
                            m_nb_level = _re.search(r"\bnb_level=(\d+)", kvs)
                            if m_nb_level:
                                levels["nb_level"] = int(m_nb_level.group(1))
                            
                            m_nr = _re.search(r"\bnr_on=([01])", kvs)
                            if m_nr:
                                levels["nr"] = bool(int(m_nr.group(1)))
                            
                            m_nr_level = _re.search(r"\bnr_level=(\d+)", kvs)
                            if m_nr_level:
                                levels["nr_level"] = int(m_nr_level.group(1))
                            
                            m_anf = _re.search(r"\banf_on=([01])", kvs)
                            if m_anf:
                                levels["anf"] = bool(int(m_anf.group(1)))
                            
                            m_anf_level = _re.search(r"\banf_level=(\d+)", kvs)
                            if m_anf_level:
                                levels["anf_level"] = int(m_anf_level.group(1))
                            
                            m_apf = _re.search(r"\bapf_on=([01])", kvs)
                            if m_apf:
                                levels["apf"] = bool(int(m_apf.group(1)))
                            
                            m_apf_level = _re.search(r"\bapf_level=(\d+)", kvs)
                            if m_apf_level:
                                levels["apf_level"] = int(m_apf_level.group(1))
                    
                    # Parse transmit status: S<handle>|transmit ... or S<handle>|interlock ...
                    if "|transmit " in line or "|interlock " in line:
                        # rfpower
                        m_rf = _re.search(r"\brfpower=(\d+)", line)
                        if m_rf:
                            levels["rfpower"] = int(m_rf.group(1))
                            logging.debug(f"  Parsed rfpower={levels['rfpower']}")
                        
                        # tunepower (NOT tune_power)
                        m_tune = _re.search(r"\btunepower=(\d+)", line)
                        if m_tune:
                            levels["tunepower"] = int(m_tune.group(1))
                            logging.debug(f"  Parsed tunepower={levels['tunepower']}")
                        
                        # miclevel (NOT mic_level)
                        m_mic = _re.search(r"\bmiclevel=(\d+)", line)
                        if m_mic:
                            levels["miclevel"] = int(m_mic.group(1))
                            logging.debug(f"  Parsed miclevel={levels['miclevel']}")
                        
                        # vox_enable (0 or 1)
                        m_vox = _re.search(r"\bvox_enable=([01])", line)
                        if m_vox:
                            levels["vox_enable"] = bool(int(m_vox.group(1)))
                            logging.debug(f"  Parsed vox_enable={levels['vox_enable']}")
                        
                        # break_in
                        m_breakin = _re.search(r"\bbreak_in=([01])", line)
                        if m_breakin:
                            levels["break_in"] = bool(int(m_breakin.group(1)))
                            logging.debug(f"  Parsed break_in={levels['break_in']}")
                        
                        # monitor (mon)
                        m_mon = _re.search(r"\bmon=([01])", line)
                        if m_mon:
                            levels["mon"] = int(m_mon.group(1))
                        
                        # monitor gain
                        m_mon_gain = _re.search(r"\bmon_gain_sb=(\d+)", line)
                        if m_mon_gain:
                            levels["mon"] = int(m_mon_gain.group(1))
                
            except Exception as e:
                # Timeout is normal
                logging.debug(f"FlexCtl get_current_levels recv: {e}")
        
        # Update instance tracking
        if "filter_lo" in levels:
            self.current_filter_lo = levels["filter_lo"]
        if "filter_hi" in levels:
            self.current_filter_hi = levels["filter_hi"]
        if "freq" in levels:
            self.current_freq = levels["freq"]
        if "mode" in levels:
            self.current_mode = levels["mode"]
        
        logging.info(f"FlexCtl initial state: {levels}")
        return levels

    # --- Basic operations ---
    
    def set_mode(self, mode: str) -> bool:
        """Set demodulation mode (USB, LSB, CW, AM, FM, DIGU, DIGL, etc)."""
        mode_upper = (mode or '').upper()
        logging.info(f"FlexCtl set_mode: {mode_upper}")
        # Activate slice first (required for slice parameter changes)
        self._send(f"slice set {self.slice_id} active=1")
        ok = self._send(f"slice set {self.slice_id} mode={mode_upper}")
        
        if ok:
            self.current_mode = mode_upper
        return ok

    def tune_mhz(self, mhz: float) -> bool:
        """Tune slice to frequency in MHz."""
        try:
            f = float(mhz)
        except Exception:
            return False
        logging.info(f"FlexCtl tune to {f:.6f} MHz")
        ok = self._send(f"slice tune {self.slice_id} {f:.6f}")
        if ok:
            self.current_freq = f
        return ok

    def set_band(self, band: str) -> bool:
        """Tune to default frequency for band (160m-6m)."""
        mhz = self.DEFAULT_BAND_FREQS.get((band or '').lower())
        if mhz is None:
            logging.warning(f"FlexCtl set_band: unknown band '{band}'")
            return False
        logging.info(f"FlexCtl set_band: {band} -> {mhz} MHz")
        return self.tune_mhz(mhz)

    def add_spot(self, rx_mhz, callsign, mode, source, spotter, comment, lifetime=3600, priority=3, color=None, ts_epoch=None) -> bool:
        """Add a spot to SmartSDR panadapter display (via TCPIP API)."""
        if not self.sock:
            if not self.connect():
                return False
        
        try:
            self.seq += 1
            ts = ts_epoch if ts_epoch is not None else int(time.time())
            
            # Helper to encode strings (replace spaces with 0x7F)
            def _enc(v: str) -> str:
                return (v or "").replace(" ", "\x7F")
            
            parts = [
                f"C{self.seq}|spot add",
                f"rx_freq={rx_mhz:.6f}",
                f"callsign={_enc(callsign)}",
                f"mode={_enc(mode)}",
                f"source={_enc(source)}",
                f"spotter_callsign={_enc(spotter)}",
                f"timestamp={ts}",
                f"lifetime_seconds={int(lifetime)}",
                f"priority={int(priority)}",
                f"comment={_enc(comment)}",
            ]
            
            if color:
                parts.append(f"color={color}")
            
            cmd = " ".join(parts) + "\r"
            logging.debug(f"FlexCtl add_spot: {callsign} {rx_mhz:.3f} MHz {mode}")
            self.sock.sendall(cmd.encode("ascii", errors="ignore"))
            
            # Try to read response
            try:
                resp = self.sock.recv(256).decode(errors="ignore").strip()
                if resp:
                    logging.debug(f"FlexCtl add_spot response: {resp}")
            except Exception:
                pass
            
            return True
        except Exception as e:
            logging.warning(f"FlexCtl add_spot failed: {e}")
            return False

    # --- Audio / TX controls ---
    # CRITICAL: Use correct SmartSDR API parameter names!
    
    def set_volume(self, level: int) -> bool:
        """Set audio volume 0-100. API uses 'audio_level' NOT 'audio_gain'."""
        level = max(0, min(100, int(level)))
        logging.info(f"FlexCtl set_volume: {level}")
        # Activate slice first, then set audio_level
        self._send(f"slice set {self.slice_id} active=1")
        return self._send(f"slice set {self.slice_id} audio_level={level}")

    def set_volume_mute(self, muted: bool) -> bool:
        """Mute/unmute audio."""
        logging.info(f"FlexCtl set_volume_mute: {muted}")
        return self._send(f"slice set {self.slice_id} audio_mute={'1' if muted else '0'}")

    def _set_tx_slice(self) -> bool:
        """Mark this slice as TX slice."""
        self._send(f"slice set {self.slice_id} tx=1")
        return True

    def set_rf_power(self, pct: int) -> bool:
        """Set RF power 1-100. API uses 'rfpower'."""
        pct = max(1, min(100, int(pct)))
        logging.info(f"FlexCtl set_rf_power: {pct}")
        self._set_tx_slice()
        return self._send(f"transmit set rfpower={pct}")

    def set_tune_power(self, pct: int) -> bool:
        """Set tune power 1-100. API uses 'tunepower' NOT 'tune_power'."""
        pct = max(1, min(100, int(pct)))
        logging.info(f"FlexCtl set_tune_power: {pct}")
        self._set_tx_slice()
        return self._send(f"transmit set tunepower={pct}")

    def set_mic_level(self, pct: int) -> bool:
        """Set mic level 0-100. API uses 'miclevel' NOT 'mic_level'."""
        pct = max(0, min(100, int(pct)))
        logging.info(f"FlexCtl set_mic_level: {pct}")
        self._set_tx_slice()
        return self._send(f"transmit set miclevel={pct}")

    def set_tune(self, on: bool) -> bool:
        """Toggle TUNE mode. API command is 'transmit tune on' or 'transmit tune off'."""
        logging.info(f"FlexCtl set_tune: {'ON' if on else 'OFF'}")
        return self._send(f"transmit tune {'on' if on else 'off'}")

    def set_mox(self, on: bool) -> bool:
        """Toggle MOX (manual transmit). API command is 'xmit on' or 'xmit off'."""
        logging.info(f"FlexCtl set_mox: {'ON' if on else 'OFF'}")
        self._set_tx_slice()
        # Use simple xmit command
        return self._send(f"xmit {'on' if on else 'off'}")

    def set_vox(self, on: bool) -> bool:
        """Enable/disable VOX."""
        logging.info(f"FlexCtl set_vox: {'ON' if on else 'OFF'}")
        self._set_tx_slice()
        return self._send(f"transmit set vox_enable={'1' if on else '0'}")
    
    def set_breakin(self, on: bool) -> bool:
        """Enable/disable CW break-in (QSK)."""
        logging.info(f"FlexCtl set_breakin: {'ON' if on else 'OFF'}")
        self._set_tx_slice()
        return self._send(f"transmit set break_in={'1' if on else '0'}")
    
    def set_agc_threshold(self, value: int) -> bool:
        """Set AGC threshold 0-100."""
        value = max(0, min(100, int(value)))
        logging.info(f"FlexCtl set_agc_threshold: {value}")
        self._send(f"slice set {self.slice_id} active=1")
        return self._send(f"slice set {self.slice_id} agc_threshold={value}")
    
    def set_tuning_step(self, step_hz: int) -> bool:
        """Set tuning step in Hz (used by SmartSDR for VFO tuning increments)."""
        logging.info(f"FlexCtl set_tuning_step: {step_hz} Hz")
        self._send(f"slice set {self.slice_id} active=1")
        return self._send(f"slice set {self.slice_id} step={step_hz}")
    
    def set_rit(self, enabled: bool, freq_hz: int = 0) -> bool:
        """Enable/disable RIT and set offset in Hz."""
        logging.info(f"FlexCtl set_rit: enabled={enabled}, freq={freq_hz} Hz")
        self._send(f"slice set {self.slice_id} active=1")
        self._send(f"slice set {self.slice_id} rit_on={'1' if enabled else '0'}")
        if enabled and freq_hz != 0:
            self._send(f"slice set {self.slice_id} rit_freq={freq_hz}")
        return True
    
    def set_xit(self, enabled: bool, freq_hz: int = 0) -> bool:
        """Enable/disable XIT and set offset in Hz."""
        logging.info(f"FlexCtl set_xit: enabled={enabled}, freq={freq_hz} Hz")
        self._send(f"slice set {self.slice_id} active=1")
        self._send(f"slice set {self.slice_id} xit_on={'1' if enabled else '0'}")
        if enabled and freq_hz != 0:
            self._send(f"slice set {self.slice_id} xit_freq={freq_hz}")
        return True
    
    def set_monitor(self, level: int, auto_enable: bool = True) -> bool:
        """Set monitor level 0-100. If > 0 and auto_enable=True, enable monitor."""
        level = max(0, min(100, int(level)))
        logging.info(f"FlexCtl set_monitor: level={level}, auto_enable={auto_enable}")
        
        # If level > 0, enable monitor first
        if level > 0 and auto_enable:
            self._send(f"transmit set mon=1")
        elif level == 0:
            self._send(f"transmit set mon=0")
        
        return self._send(f"transmit set mon_gain_sb={level}")
    
    def set_dsp_level(self, control: str, level: int) -> bool:
        """Set DSP control level (nb_level, nr_level, anf_level, apf_level) 0-100."""
        level = max(0, min(100, int(level)))
        logging.info(f"FlexCtl set_dsp_level: {control}={level}")
        self._send(f"slice set {self.slice_id} active=1")
        return self._send(f"slice set {self.slice_id} {control}={level}")

    def set_filter_edges(self, lo: int, hi: int) -> bool:
        """Set filter edges in Hz using the filt command.
        
        The filt command works for ALL modes (CW, USB, LSB, etc).
        Format: filt <slice> <low> <high>
        """
        logging.info(f"FlexCtl set_filter: lo={lo} hi={hi} mode={self.current_mode}")
        
        # Use the dedicated filt command (not slice set!)
        ok = self._send(f"filt {self.slice_id} {lo} {hi}")
        
        if ok:
            self.current_filter_lo = lo
            self.current_filter_hi = hi
        else:
            logging.warning(f"Filter command failed: lo={lo}, hi={hi} for mode={self.current_mode}")
        return ok
    
    def refresh_radio_state(self) -> bool:
        """Query radio to refresh current state and read ALL pending subscription updates.
        
        This is used for 2-way sync to detect external changes made in SmartSDR.
        Reads all pending messages from the socket to catch mode/freq/filter/band/transmit changes.
        """
        if not self.connect():
            logging.error("❌ REFRESH FAILED: Could not connect to SmartSDR")
            return False
        
        try:
            import re as _re
            import time as _time
            # Set short timeout for non-blocking reads
            old_timeout = self.sock.gettimeout()
            self.sock.settimeout(0.2)  # 200ms timeout (was 100ms, too short)
            logging.debug(f"🔍 REFRESH STARTING: Connected to {self.host}:{self.port}, slice_id={self.slice_id}")
            
            # Re-subscribe only occasionally. Doing this every poll creates
            # noisy SmartSDR client activity and can make the radio look like
            # it is constantly being reconnected.
            now = _time.time()
            if now - float(self.last_resubscribe_time or 0) > 60:
                try:
                    self._send("sub slice all")
                    self._send("sub tx all")
                    self._send("sub transmit all")
                    self.last_resubscribe_time = now
                except Exception as e:
                    logging.debug(f"FlexCtl re-subscription attempt: {e}")
            
            # Read ALL pending messages from socket (not just one!)
            messages_read = 0
            state_changed = {}  # Track what changed
            
            while True:
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        logging.warning("FlexCtl socket closed by SmartSDR")
                        try:
                            self.sock.close()
                        except Exception:
                            pass
                        self.sock = None
                        return False
                    resp = chunk.decode(errors="ignore").strip()
                    if not resp:
                        break
                    
                    messages_read += 1
                    self.last_radio_message_time = _time.time()
                    logging.debug(f"FlexCtl refresh: {resp[:100]}...")  # Log first 100 chars
                    
                    # Parse ALL subscription updates for mode/freq/filter/band changes
                    if "|slice" in resp and f"slice {self.slice_id} " in resp:
                        logging.debug(f"FlexCtl: Processing slice message")
                        # LOG ACTUAL MESSAGE for debugging - this will show us what fields are in it!
                        logging.info(f"🔍 SLICE MESSAGE: {resp[:200]}")
                        # Update volume (audio_level) - track this for 2-way sync
                        m_vol = _re.search(r"\baudio_level=(\d+)", resp)
                        if m_vol:
                            new_volume = int(m_vol.group(1))
                            if self.current_volume is None or new_volume != self.current_volume:
                                if self.current_volume is not None:
                                    logging.info(f"FlexCtl: VOLUME CHANGED: {self.current_volume} → {new_volume}")
                                state_changed['volume'] = new_volume
                            self.current_volume = new_volume
                        
                        # Update mode
                        m_mode = _re.search(r"\bmode=([A-Z]+)", resp)
                        if m_mode:
                            new_mode = m_mode.group(1)
                            if self.current_mode is None or new_mode != self.current_mode:
                                if self.current_mode is not None:
                                    logging.info(f"FlexCtl: MODE CHANGED: {self.current_mode} → {new_mode}")
                                state_changed['mode'] = new_mode
                            self.current_mode = new_mode
                        
                        # Update frequency (band changes)
                        # Try RF_frequency first, then freq as fallback
                        m_freq = _re.search(r"\bRF_frequency=([\d.]+)", resp)
                        if m_freq:
                            logging.info(f"✅ FREQ MATCH (RF_frequency): {m_freq.group(1)}")
                        else:
                            m_freq = _re.search(r"\bfreq=([\d.]+)", resp)  # Fallback pattern
                            if m_freq:
                                logging.info(f"✅ FREQ MATCH (freq): {m_freq.group(1)}")
                        
                        if m_freq:
                            new_freq = float(m_freq.group(1))
                            # Check if frequency actually changed (initialize if None)
                            if self.current_freq is None or abs(new_freq - self.current_freq) > 0.0001:  # More than 100 Hz change
                                if self.current_freq is not None:
                                    logging.info(f"🎯 FREQ CHANGED: {self.current_freq:.6f} → {new_freq:.6f} MHz")
                                else:
                                    logging.info(f"🎯 FREQ INITIALIZED: {new_freq:.6f} MHz")
                                state_changed['freq'] = new_freq
                            self.current_freq = new_freq
                        else:
                            logging.debug(f"❌ NO FREQUENCY FIELD FOUND in slice message")
                        
                        # Update filter_lo
                        m_flo = _re.search(r"\bfilter_lo=(-?\d+)", resp)
                        if m_flo:
                            new_flo = int(m_flo.group(1))
                            if self.current_filter_lo is None or new_flo != self.current_filter_lo:
                                if self.current_filter_lo is not None:
                                    logging.info(f"FlexCtl: FILTER_LO CHANGED: {self.current_filter_lo} → {new_flo}")
                                state_changed['filter_lo'] = new_flo
                            self.current_filter_lo = new_flo
                        
                        # Update filter_hi
                        m_fhi = _re.search(r"\bfilter_hi=(-?\d+)", resp)
                        if m_fhi:
                            new_fhi = int(m_fhi.group(1))
                            if self.current_filter_hi is None or new_fhi != self.current_filter_hi:
                                if self.current_filter_hi is not None:
                                    logging.info(f"FlexCtl: FILTER_HI CHANGED: {self.current_filter_hi} → {new_fhi}")
                                state_changed['filter_hi'] = new_fhi
                            self.current_filter_hi = new_fhi
                        
                        # Track RIT/XIT
                        m_rit_on = _re.search(r"\brit_on=([01])", resp)
                        if m_rit_on:
                            state_changed['rit_enabled'] = bool(int(m_rit_on.group(1)))
                        
                        m_rit_freq = _re.search(r"\brit_freq=(-?\d+)", resp)
                        if m_rit_freq:
                            state_changed['rit_freq'] = int(m_rit_freq.group(1))
                        
                        m_xit_on = _re.search(r"\bxit_on=([01])", resp)
                        if m_xit_on:
                            state_changed['xit_enabled'] = bool(int(m_xit_on.group(1)))
                        
                        m_xit_freq = _re.search(r"\bxit_freq=(-?\d+)", resp)
                        if m_xit_freq:
                            state_changed['xit_freq'] = int(m_xit_freq.group(1))
                        
                        # Track AGC
                        m_agc = _re.search(r"\bagc_mode=(\w+)", resp)
                        if m_agc:
                            state_changed['agc_mode'] = m_agc.group(1)
                        
                        m_agc_thresh = _re.search(r"\bagc_threshold=(\d+)", resp)
                        if m_agc_thresh:
                            state_changed['agc_threshold'] = int(m_agc_thresh.group(1))
                        
                        # Tuning step
                        m_step = _re.search(r"\bstep=(\d+)", resp)
                        if m_step:
                            state_changed['step'] = int(m_step.group(1))
                        
                        # Track DSP controls
                        m_nb = _re.search(r"\bnb_on=([01])", resp)
                        if m_nb:
                            state_changed['nb_enabled'] = bool(int(m_nb.group(1)))
                        
                        m_nb_level = _re.search(r"\bnb_level=(\d+)", resp)
                        if m_nb_level:
                            state_changed['nb_level'] = int(m_nb_level.group(1))
                        
                        m_nr = _re.search(r"\bnr_on=([01])", resp)
                        if m_nr:
                            state_changed['nr_enabled'] = bool(int(m_nr.group(1)))
                        
                        m_nr_level = _re.search(r"\bnr_level=(\d+)", resp)
                        if m_nr_level:
                            state_changed['nr_level'] = int(m_nr_level.group(1))
                        
                        m_anf = _re.search(r"\banf_on=([01])", resp)
                        if m_anf:
                            state_changed['anf_enabled'] = bool(int(m_anf.group(1)))
                        
                        m_anf_level = _re.search(r"\banf_level=(\d+)", resp)
                        if m_anf_level:
                            state_changed['anf_level'] = int(m_anf_level.group(1))
                        
                        m_apf = _re.search(r"\bapf_on=([01])", resp)
                        if m_apf:
                            state_changed['apf_enabled'] = bool(int(m_apf.group(1)))
                        
                        m_apf_level = _re.search(r"\bapf_level=(\d+)", resp)
                        if m_apf_level:
                            state_changed['apf_level'] = int(m_apf_level.group(1))
                    
                    # Parse transmit/interlock updates for mic/drive/tune power and MOX state
                    if "|transmit " in resp or "|interlock " in resp:
                        # MOX state (transmit on/off)
                        m_mox = _re.search(r"\bmox=([01])", resp)
                        if m_mox:
                            new_mox = bool(int(m_mox.group(1)))
                            if self.current_mox is None or new_mox != self.current_mox:
                                if self.current_mox is not None:
                                    logging.info(f"FlexCtl: MOX STATE CHANGED: {self.current_mox} → {new_mox}")
                                state_changed['mox'] = new_mox
                            self.current_mox = new_mox
                    
                    # Parse transmit/interlock updates for mic/drive/tune power changes
                    if "|transmit " in resp or "|interlock " in resp:
                        # rfpower (Drive) - map to 'drive' for frontend
                        m_rf = _re.search(r"\brfpower=(\d+)", resp)
                        if m_rf:
                            new_rfpower = int(m_rf.group(1))
                            if self.current_rfpower is None or new_rfpower != self.current_rfpower:
                                if self.current_rfpower is not None:
                                    logging.info(f"FlexCtl: RFPOWER CHANGED: {self.current_rfpower} → {new_rfpower}")
                                state_changed['drive'] = new_rfpower  # Use 'drive' for frontend
                            self.current_rfpower = new_rfpower
                        
                        # tunepower - map to 'tune_power' for frontend
                        m_tune = _re.search(r"\btunepower=(\d+)", resp)
                        if m_tune:
                            new_tunepower = int(m_tune.group(1))
                            if self.current_tunepower is None or new_tunepower != self.current_tunepower:
                                if self.current_tunepower is not None:
                                    logging.info(f"FlexCtl: TUNEPOWER CHANGED: {self.current_tunepower} → {new_tunepower}")
                                state_changed['tune_power'] = new_tunepower  # Use 'tune_power' for frontend
                            self.current_tunepower = new_tunepower
                        
                        # miclevel (MIC LEVEL) - map to 'mic_level' for frontend
                        m_mic = _re.search(r"\bmiclevel=(\d+)", resp)
                        if m_mic:
                            new_miclevel = int(m_mic.group(1))
                            if self.current_miclevel is None or new_miclevel != self.current_miclevel:
                                if self.current_miclevel is not None:
                                    logging.info(f"FlexCtl: MICLEVEL CHANGED: {self.current_miclevel} → {new_miclevel}")
                                state_changed['mic_level'] = new_miclevel  # Use 'mic_level' for frontend
                            self.current_miclevel = new_miclevel
                        
                        # vox_enable
                        m_vox = _re.search(r"\bvox_enable=([01])", resp)
                        if m_vox:
                            new_vox = bool(int(m_vox.group(1)))
                            if self.current_vox_enable is None or new_vox != self.current_vox_enable:
                                if self.current_vox_enable is not None:
                                    logging.info(f"FlexCtl: VOX_ENABLE CHANGED: {self.current_vox_enable} → {new_vox}")
                                state_changed['vox_enable'] = new_vox
                            self.current_vox_enable = new_vox
                        
                        # break_in
                        m_breakin = _re.search(r"\bbreak_in=([01])", resp)
                        if m_breakin:
                            new_breakin = bool(int(m_breakin.group(1)))
                            if self.current_break_in is None or new_breakin != self.current_break_in:
                                if self.current_break_in is not None:
                                    logging.info(f"FlexCtl: BREAK_IN CHANGED: {self.current_break_in} → {new_breakin}")
                                state_changed['break_in'] = new_breakin
                            self.current_break_in = new_breakin
                        
                        # monitor
                        m_mon = _re.search(r"\bmon=([01])", resp)
                        if m_mon:
                            state_changed['monitor'] = int(m_mon.group(1))
                        
                        m_mon_gain = _re.search(r"\bmon_gain_sb=(\d+)", resp)
                        if m_mon_gain:
                            state_changed['monitor'] = int(m_mon_gain.group(1))
                    
                    # Meter messages ignored (smeter functionality removed)
                
                except socket.timeout:
                    # No more data available - this is normal
                    break
                except Exception as e:
                    logging.debug(f"FlexCtl refresh recv exception: {e}")
                    break
            
            # Restore original timeout
            if old_timeout is not None:
                self.sock.settimeout(old_timeout)
            
            # No messages during a poll is normal when the operator is not
            # changing radio state. Keep the TCP client connected.
            
            # Return state_changed dict for UI updates
            self.last_state_changed = state_changed
            
            logging.debug(f"FlexCtl refresh: Read {messages_read} message(s), changes: {list(state_changed.keys())}")
            return True
            
        except Exception as e:
            logging.error(f"FlexCtl refresh_radio_state FAILED: {e}")
            return False
