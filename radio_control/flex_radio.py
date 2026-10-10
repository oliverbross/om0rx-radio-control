# flex_radio.py - FlexRadio SmartSDR TCP API client classes

import logging
import re
import socket
import threading
import time

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
    BAND_RANGES = {
        "160m": (1.8, 2.0),
        "80m": (3.5, 4.0),
        "60m": (5.0, 5.5),
        "40m": (7.0, 7.3),
        "30m": (10.1, 10.15),
        "20m": (14.0, 14.35),
        "17m": (18.068, 18.168),
        "15m": (21.0, 21.45),
        "12m": (24.89, 24.99),
        "10m": (28.0, 29.7),
        "6m": (50.0, 54.0),
    }
    DEFAULT_ANTENNA_POLICY = {
        "enabled": True,
        "bands": {
            "160m": "ANT2",
            "80m": "ANT2",
            "60m": "ANT2",
            "40m": "ANT2",
            "30m": "ANT2",
            "20m": "ANT1",
            "17m": "ANT1",
            "15m": "ANT1",
            "12m": "ANT1",
            "10m": "ANT1",
        },
    }
    
    def __init__(self, host: str, port: int, slice_id: int = 0):
        import socket as _s
        self.host, self.port = host, int(port)
        self.slice_id = int(slice_id)
        self.sock = None
        self.seq = 1000
        self._socket_mod = _s
        self._io_lock = threading.RLock()
        # Slice state tracking
        self.current_filter_lo = None
        self.current_filter_hi = None
        self.current_freq = None
        self.current_mode = None
        self.current_volume = None  # Volume/audio_level
        self.current_rx_ant = None
        self.current_tx_ant = None
        self._last_antenna_policy = None
        self._pending_antenna_policy_freq = None
        # Transmit state tracking (for 2-way sync)
        self.current_rfpower = None
        self.current_tunepower = None
        self.current_miclevel = None
        self.current_vox_enable = None
        self.current_mox = None  # MOX state
        self.current_interlock_state = None
        self.current_break_in = None
        # State change tracking (for UI updates)
        self.last_state_changed = {}
        # Subscription timeout - re-subscribe if we haven't heard from radio in a while
        self.last_subscription_time = 0
        self.last_resubscribe_time = 0
        self.last_radio_message_time = 0
        self.last_command_time = 0
        self.last_tx_active_time = 0
        self.last_tx_state_time = 0
        # SmartSDR is a byte stream: one recv() may contain several records or
        # only part of one. Keep framing state across polls and command replies.
        self._receive_buffer = b""
        self._pending_lines = []
        # Transmit settings are scoped to the active SmartSDR GUI client on
        # MultiFlex radios.  An unbound TCP client can receive an OK response
        # for ``transmit set`` while its GUI-visible RF power remains unchanged.
        self.bound_gui_client_id = None
        self.bound_gui_client_handle = None
        self.preferred_station_name = ""
        self._gui_binding_confirmed = False
        self.slice_states = {}
        self.current_tx_slice_id = None
        logging.info(f"FlexCtl initialized for {host}:{port} slice {slice_id}")

    def _queue_received(self, chunk: bytes) -> None:
        """Frame complete CR/LF-delimited SmartSDR records from a TCP chunk."""
        if not chunk:
            return
        self._receive_buffer += chunk
        parts = re.split(rb"[\r\n]+", self._receive_buffer)
        if self._receive_buffer.endswith((b"\r", b"\n")):
            self._receive_buffer = b""
        else:
            self._receive_buffer = parts.pop() if parts else self._receive_buffer
        self._pending_lines.extend(
            part.decode(errors="ignore").strip() for part in parts if part.strip()
        )

    @staticmethod
    def band_for_frequency(mhz: float):
        try:
            freq = float(mhz)
        except Exception:
            return None
        for band, (lo, hi) in FlexCtl.BAND_RANGES.items():
            if lo <= freq <= hi:
                return band
        return None

    @staticmethod
    def _normalize_antenna_policy(policy):
        if not isinstance(policy, dict):
            policy = {}
        default = FlexCtl.DEFAULT_ANTENNA_POLICY
        enabled = policy.get("enabled", default["enabled"])
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
        bands = policy.get("bands")
        if not isinstance(bands, dict):
            bands = {}
        merged_bands = dict(default["bands"])
        for band, value in bands.items():
            clean_band = str(band or "").strip().lower()
            if clean_band not in FlexCtl.BAND_RANGES:
                continue
            if isinstance(value, dict):
                rx = str(value.get("rx") or value.get("rxAnt") or value.get("antenna") or "").strip().upper()
                tx = str(value.get("tx") or value.get("txAnt") or value.get("antenna") or rx).strip().upper()
                if rx or tx:
                    merged_bands[clean_band] = {"rx": rx or tx, "tx": tx or rx}
            else:
                antenna = str(value or "").strip().upper()
                if antenna:
                    merged_bands[clean_band] = antenna
        return {"enabled": bool(enabled), "bands": merged_bands}

    @staticmethod
    def _policy_entry_to_rx_tx(entry):
        if isinstance(entry, dict):
            rx = str(entry.get("rx") or entry.get("rxAnt") or entry.get("antenna") or "").strip().upper()
            tx = str(entry.get("tx") or entry.get("txAnt") or entry.get("antenna") or rx).strip().upper()
            if rx or tx:
                return {"rx": rx or tx, "tx": tx or rx}
            return None
        antenna = str(entry or "").strip().upper()
        if not antenna:
            return None
        return {"rx": antenna, "tx": antenna}

    @staticmethod
    def desired_antennas_for_frequency(mhz: float, policy=None):
        """Return configured OM0RX SmartSDR RX/TX antenna policy for a frequency."""
        normalized = FlexCtl._normalize_antenna_policy(policy or FlexCtl.DEFAULT_ANTENNA_POLICY)
        if not normalized.get("enabled", True):
            return None
        band = FlexCtl.band_for_frequency(mhz)
        if not band:
            return None
        entry = normalized.get("bands", {}).get(band)
        antennas = FlexCtl._policy_entry_to_rx_tx(entry)
        if not antennas:
            return None
        return {"band": band, **antennas}

    def desired_antennas_for_current_config(self, mhz: float):
        try:
            from radio_control import config as app_config
            policy = getattr(app_config, "FLEX_ANTENNA_POLICY", self.DEFAULT_ANTENNA_POLICY)
        except Exception:
            policy = self.DEFAULT_ANTENNA_POLICY
        return self.desired_antennas_for_frequency(mhz, policy)

    @staticmethod
    def _is_transmitting_state(state) -> bool:
        return str(state or "").upper() in {"TRANSMITTING", "PTT_REQUESTED"}

    def _tx_active_recently(self) -> bool:
        """Return whether antenna switching must remain blocked.

        An active TX state never expires heuristically. Unknown state also fails
        closed until the radio explicitly reports receive/ready.
        """
        if self.current_mox is True or self._is_transmitting_state(self.current_interlock_state):
            return True
        receive_state = str(self.current_interlock_state or "").upper() in {
            "READY", "RECEIVE", "NOT_READY", "TIMEOUT", "TX_FAULT"
        }
        return self.current_mox is None and not receive_state

    def _record_antenna_values(self, text: str, levels: dict | None = None, state_changed: dict | None = None) -> None:
        if not text:
            return
        m_rx = re.search(r"\brxant=([A-Z0-9_]+)", text)
        if m_rx:
            new_rx = m_rx.group(1)
            if self.current_rx_ant is None or new_rx != self.current_rx_ant:
                if state_changed is not None:
                    state_changed["rx_ant"] = new_rx
                logging.info("FlexCtl: RX ANT CHANGED: %s -> %s", self.current_rx_ant, new_rx)
            self.current_rx_ant = new_rx
            if levels is not None:
                levels["rx_ant"] = new_rx

        m_tx = re.search(r"\b(?:txant|tx_antenna)=([A-Z0-9_]+)", text)
        if m_tx:
            new_tx = m_tx.group(1)
            if self.current_tx_ant is None or new_tx != self.current_tx_ant:
                if state_changed is not None:
                    state_changed["tx_ant"] = new_tx
                logging.info("FlexCtl: TX ANT CHANGED: %s -> %s", self.current_tx_ant, new_tx)
            self.current_tx_ant = new_tx
            if levels is not None:
                levels["tx_ant"] = new_tx

    def enforce_antenna_policy(self, mhz: float | None = None, *, reason: str = "frequency") -> bool:
        """Keep OM0RX antenna routing consistent across WSJT-Z band changes."""
        freq = mhz if mhz is not None else self.current_freq
        desired = self.desired_antennas_for_current_config(freq)
        if not desired:
            return True
        desired_rx = desired["rx"]
        desired_tx = desired["tx"]

        needs_rx = self.current_rx_ant != desired_rx
        needs_tx = self.current_tx_ant != desired_tx
        cache_key = (round(float(freq), 3), desired["band"], desired_rx, desired_tx)
        # No antenna write is needed, so TX state is irrelevant. This is a
        # common path while a fresh interlock update is briefly delayed; do not
        # turn a no-op policy check into a failed station-route transaction.
        if (
            not needs_rx
            and not needs_tx
            and self._last_antenna_policy == cache_key
        ):
            return True

        if self._tx_active_recently():
            self._pending_antenna_policy_freq = float(freq)
            logging.info(
                "FlexCtl antenna policy deferred while TX active: %.6f MHz %s -> rx=%s tx=%s",
                float(freq),
                desired["band"],
                desired_rx,
                desired_tx,
            )
            return False

        logging.info(
            "FlexCtl antenna policy: %.6f MHz %s -> rx=%s tx=%s (%s, current rx=%s tx=%s)",
            float(freq),
            desired["band"],
            desired_rx,
            desired_tx,
            reason,
            self.current_rx_ant,
            self.current_tx_ant,
        )
        ok = True
        self._send(f"slice set {self.slice_id} active=1")
        if needs_rx:
            ok = self._send(f"slice set {self.slice_id} rxant={desired_rx}") and ok
            if ok:
                self.current_rx_ant = desired_rx
        if needs_tx:
            tx_ok = self._send(f"slice set {self.slice_id} txant={desired_tx}")
            if not tx_ok:
                tx_ok = self._send(f"transmit set tx_antenna={desired_tx}")
            ok = tx_ok and ok
            if tx_ok:
                self.current_tx_ant = desired_tx
        if ok:
            self._last_antenna_policy = cache_key
            self._pending_antenna_policy_freq = None
            self.last_state_changed.update({"rx_ant": self.current_rx_ant, "tx_ant": self.current_tx_ant})
        return ok

    def connect(self) -> bool:
        """Connect to SmartSDR TCP API if not already connected."""
        with self._io_lock:
            if self.sock:
                return True
            try:
                logging.info(f"FlexCtl connecting to {self.host}:{self.port}...")
                self.sock = self._socket_mod.create_connection((self.host, self.port), timeout=3.0)
                self.sock.settimeout(1.0)
                self._receive_buffer = b""
                self._pending_lines.clear()
                
                # Read version and handle
                try:
                    greeting = self.sock.recv(512)
                    self._queue_received(greeting)
                    logging.debug(f"FlexCtl GREETING: {greeting.decode(errors='ignore').strip()}")
                except Exception as e:
                    logging.warning(f"FlexCtl greeting read error: {e}")
                
                # Discover and bind to the active SmartSDR GUI context before
                # reading or changing transmitter settings.  ``client station``
                # is GUI-only and returns 5000002C for this non-GUI client.
                self._send("sub client all")
                if self.bound_gui_client_id:
                    self._gui_binding_confirmed = self._send(
                        f"client bind client_id={self.bound_gui_client_id}"
                    )
                if not self._gui_binding_confirmed:
                    logging.warning(
                        "FlexCtl could not bind to an active SmartSDR GUI client; "
                        "transmit-setting writes will remain inhibited"
                    )

                # Identify and subscribe. "sub transmit all" returns
                # 500000A3 on this station and is not needed for TX/interlock
                # updates, which arrive through "sub tx all".
                self._send("sub slice all")
                self._send("sub radio all")
                self._send("sub tx all")
                self.last_resubscribe_time = time.time()
                
                # Test: Try to read subscription confirmation
                self.sock.settimeout(0.5)
                try:
                    test_resp = self.sock.recv(4096)
                    self._queue_received(test_resp)
                    logging.info(f"POST-SUBSCRIPTION MSG: {test_resp[:300] if test_resp else 'NO RESPONSE'}")
                    while self._pending_lines:
                        line = self._pending_lines.pop(0)
                        self._record_basic_status_from_line(line)
                except socket.timeout:
                    logging.debug("No subscription confirmation received (timeout)")
                except Exception as e:
                    logging.warning(f"Error reading subscription confirm: {e}")
                
                self.sock.settimeout(1.0)
                
                logging.info("FlexCtl connected successfully")
                return True
            except Exception as e:
                logging.error(f"FlexCtl connect FAILED: {e}")
                self.sock = None
                self.bound_gui_client_id = None
                self.bound_gui_client_handle = None
                self.current_tx_slice_id = None
                self.slice_states.clear()
                self._receive_buffer = b""
                self._pending_lines.clear()
                return False

    def close(self) -> None:
        """Close the SmartSDR TCP socket."""
        with self._io_lock:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
                self._gui_binding_confirmed = False
                self.bound_gui_client_id = None
                self.bound_gui_client_handle = None
                self.current_tx_slice_id = None
                self.slice_states.clear()

    def connect_tx_state_probe(
        self,
        timeout: float = 1.5,
        *,
        requested_at: float | None = None,
    ) -> bool:
        """Open a minimal read-only TX/interlock subscription.

        A normal :meth:`connect` subscribes to slice, radio, and TX streams and
        waits for several command responses.  Station safety checks only need
        the TX/interlock stream.  Reusing the full connection path for every
        proof created a burst of unnecessary SmartSDR clients and could exceed
        the coordinator's timeout between consecutive training points.

        This probe sends only ``sub tx all`` and succeeds only after both the
        command acknowledgement and an interlock/transmit status newer than
        ``requested_at`` have been observed.  It never sends a radio mutation.
        """
        with self._io_lock:
            started = time.monotonic()
            requested_at = float(requested_at or time.time())
            budget = max(0.25, min(3.0, float(timeout)))
            deadline = started + budget
            acknowledged = False
            try:
                self.sock = self._socket_mod.create_connection(
                    (self.host, self.port),
                    timeout=budget,
                )
                self.sock.settimeout(min(0.20, budget))
                self._receive_buffer = b""
                self._pending_lines.clear()

                # The greeting is informational.  Parse it if immediately
                # available, but do not spend the proof budget waiting for it.
                try:
                    greeting = self.sock.recv(512)
                    self._queue_received(greeting)
                except socket.timeout:
                    pass

                self.seq += 1
                sequence = self.seq
                response_prefix = f"R{sequence}|"
                self.sock.sendall(f"C{sequence}|sub tx all\r".encode("ascii"))

                while time.monotonic() < deadline:
                    while self._pending_lines:
                        line = self._pending_lines.pop(0)
                        self._record_basic_status_from_line(line)
                        if line.startswith(response_prefix):
                            parts = line.split("|", 2)
                            response_code = parts[1] if len(parts) >= 2 else ""
                            if response_code not in {"00000000", "0"}:
                                logging.warning(
                                    "FlexCtl TX proof subscription rejected: %s",
                                    response_code or "missing response code",
                                )
                                return False
                            acknowledged = True
                    if acknowledged and self.last_tx_state_time >= requested_at:
                        return True
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.sock.settimeout(min(0.20, remaining))
                    try:
                        chunk = self.sock.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    self._queue_received(chunk)
                return False
            except Exception as exc:
                logging.warning("FlexCtl minimal TX proof failed: %s", exc)
                return False
            finally:
                logging.info(
                    "FlexCtl TX proof completed confirmed=%s interlock=%s mox=%s duration_ms=%d",
                    bool(acknowledged and self.last_tx_state_time >= requested_at),
                    self.current_interlock_state,
                    self.current_mox,
                    round((time.monotonic() - started) * 1000),
                )

    def refresh_tx_state_probe(
        self,
        timeout: float = 1.5,
        *,
        expect_transmitting: bool | None = None,
    ) -> dict:
        """Refresh TX state on an existing subscribed socket without reconnecting.

        A lightweight ``sub tx all`` acknowledgement is used as an ordered
        barrier on the existing TCP stream.  All interlock transitions queued
        before that acknowledgement are parsed, and the call may wait for the
        requested receive/transmit state.  No radio mutation is sent.
        """
        with self._io_lock:
            requested_at = time.time()
            started = time.monotonic()
            budget = max(0.25, min(3.0, float(timeout)))
            deadline = started + budget
            acknowledged = False
            if self.sock is None:
                return {
                    "confirmed": False,
                    "connected": False,
                    "requested_at": requested_at,
                    "observed_at": float(self.last_tx_state_time or 0),
                    "mox": self.current_mox,
                    "interlock_state": self.current_interlock_state,
                }

            old_timeout = self.sock.gettimeout()
            try:
                self.seq += 1
                sequence = self.seq
                response_prefix = f"R{sequence}|"
                self.sock.sendall(f"C{sequence}|sub tx all\r".encode("ascii"))

                while time.monotonic() < deadline:
                    while self._pending_lines:
                        line = self._pending_lines.pop(0)
                        self._record_basic_status_from_line(line)
                        if line.startswith(response_prefix):
                            parts = line.split("|", 2)
                            code = parts[1] if len(parts) >= 2 else ""
                            if code not in {"00000000", "0"}:
                                logging.warning(
                                    "FlexCtl persistent TX monitor refresh rejected: %s",
                                    code or "missing response code",
                                )
                                return {
                                    "confirmed": False,
                                    "connected": True,
                                    "requested_at": requested_at,
                                    "observed_at": float(self.last_tx_state_time or 0),
                                    "mox": self.current_mox,
                                    "interlock_state": self.current_interlock_state,
                                }
                            acknowledged = True

                    interlock = str(self.current_interlock_state or "").upper()
                    transmitting = bool(
                        self.current_mox is True or interlock == "TRANSMITTING"
                    )
                    state_known = bool(self.last_tx_state_time)
                    expected = (
                        True
                        if expect_transmitting is None
                        else transmitting is expect_transmitting
                    )
                    if acknowledged and state_known and expected:
                        proof_at = time.time()
                        logging.info(
                            "FlexCtl persistent TX monitor proof confirmed interlock=%s "
                            "mox=%s expected_tx=%s duration_ms=%d",
                            self.current_interlock_state,
                            self.current_mox,
                            expect_transmitting,
                            round((time.monotonic() - started) * 1000),
                        )
                        return {
                            "confirmed": True,
                            "connected": True,
                            "requested_at": requested_at,
                            "observed_at": float(self.last_tx_state_time or 0),
                            "proof_at": proof_at,
                            "mox": self.current_mox,
                            "interlock_state": self.current_interlock_state,
                        }

                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.sock.settimeout(min(0.20, remaining))
                    try:
                        chunk = self.sock.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        self.close()
                        break
                    self._queue_received(chunk)
            except Exception as exc:
                logging.warning("FlexCtl persistent TX monitor refresh failed: %s", exc)
                self.close()
            finally:
                if self.sock is not None and old_timeout is not None:
                    try:
                        self.sock.settimeout(old_timeout)
                    except Exception:
                        pass

            logging.warning(
                "FlexCtl persistent TX monitor proof unconfirmed ack=%s interlock=%s "
                "mox=%s expected_tx=%s duration_ms=%d",
                acknowledged,
                self.current_interlock_state,
                self.current_mox,
                expect_transmitting,
                round((time.monotonic() - started) * 1000),
            )
            return {
                "confirmed": False,
                "connected": self.sock is not None,
                "requested_at": requested_at,
                "observed_at": float(self.last_tx_state_time or 0),
                "mox": self.current_mox,
                "interlock_state": self.current_interlock_state,
            }

    def _record_basic_status_from_line(self, line: str) -> None:
        """Update cached state from async status lines that arrive while sending commands."""
        self._record_slice_status_from_line(line)
        if ("|client " in line or "|gui_client " in line) and " connected " in line:
            client_id = re.search(r"\bclient_id=([^\s]+)", line)
            program = re.search(r"\bprogram=([^\s]+)", line)
            station = re.search(r"\bstation=([^\s]+)", line)
            handle = re.search(r"\|(?:gui_)?client\s+([^\s]+)", line)
            preferred = re.sub(r"[^a-z0-9]", "", self.preferred_station_name.lower())
            observed = re.sub(r"[^a-z0-9]", "", station.group(1).lower()) if station else ""
            preferred_match = bool(preferred and observed == preferred)
            legacy_match = bool(
                not preferred and program and program.group(1).lower().startswith("smartsdr")
            )
            if client_id and (preferred_match or legacy_match):
                self.bound_gui_client_id = client_id.group(1)
                self.bound_gui_client_handle = handle.group(1).lower() if handle else None

        if "|slice" in line and f"slice {self.slice_id} " in line:
            self._record_antenna_values(line)

            m_mode = re.search(r"\bmode=([A-Z]+)", line)
            if m_mode:
                self.current_mode = m_mode.group(1)

            m_freq = re.search(r"\bRF_frequency=([\d.]+)", line)
            if not m_freq:
                m_freq = re.search(r"\bfreq=([\d.]+)", line)
            if m_freq:
                self.current_freq = float(m_freq.group(1))

            m_flo = re.search(r"\bfilter_lo=(-?\d+)", line)
            if m_flo:
                self.current_filter_lo = int(m_flo.group(1))

            m_fhi = re.search(r"\bfilter_hi=(-?\d+)", line)
            if m_fhi:
                self.current_filter_hi = int(m_fhi.group(1))

        if "|interlock " in line:
            m_state = re.search(r"\bstate=([A-Z_]+)", line)
            if m_state:
                self.last_tx_state_time = time.time()
                self.current_interlock_state = m_state.group(1)
                if self.current_interlock_state == "TRANSMITTING":
                    self.current_mox = True
                    self.last_tx_active_time = time.time()
                elif self.current_interlock_state in {"READY", "RECEIVE", "NOT_READY", "TIMEOUT", "TX_FAULT"}:
                    self.current_mox = False

        if "|transmit " in line or "|interlock " in line:
            self._record_antenna_values(line)

            m_mox = re.search(r"\bmox=([01])", line)
            if m_mox:
                self.last_tx_state_time = time.time()
                self.current_mox = bool(int(m_mox.group(1)))
                if self.current_mox:
                    self.last_tx_active_time = time.time()

    def _record_slice_status_from_line(self, line: str) -> None:
        """Track every station slice so CAT VFO A/B state remains addressable."""
        match = re.search(r"\|slice\s+(\d+)\s*(.*)$", line)
        if not match:
            return
        slice_id = int(match.group(1))
        body = match.group(2)
        properties = {
            key: value
            for key, value in re.findall(r"\b([A-Za-z_]+)=([^\s]+)", body)
        }
        if re.search(r"\bremoved(?:=1)?\b", body):
            self.slice_states.pop(slice_id, None)
            if self.current_tx_slice_id == slice_id:
                self.current_tx_slice_id = None
            return
        state = dict(self.slice_states.get(slice_id) or {"slice_id": slice_id})
        for source, target in (
            ("index_letter", "index_letter"),
            ("mode", "mode"),
            ("client_handle", "client_handle"),
            ("rxant", "rx_antenna"),
            ("txant", "tx_antenna"),
        ):
            if source in properties:
                state[target] = (
                    properties[source].upper()
                    if source != "client_handle"
                    else properties[source].lower()
                )
        frequency = properties.get("RF_frequency") or properties.get("freq")
        if frequency is not None:
            try:
                state["frequency"] = float(frequency)
            except ValueError:
                pass
        for source, target in (
            ("active", "active"),
            ("tx", "transmit"),
            ("in_use", "in_use"),
        ):
            if source in properties:
                state[target] = properties[source].upper() in {"1", "T", "TRUE"}
        state["updated_at"] = time.time()
        self.slice_states[slice_id] = state
        if state.get("transmit") is True:
            self.current_tx_slice_id = slice_id

    def get_slice_states(self) -> list[dict]:
        """Return current slices owned by the bound station client, ordered by ID."""
        if self.preferred_station_name and not self.bound_gui_client_handle:
            return []
        states = self.slice_states.values()
        if self.bound_gui_client_handle:
            states = (
                state
                for state in states
                if str(state.get("client_handle") or "").lower()
                == self.bound_gui_client_handle
            )
        return [dict(state) for state in sorted(states, key=lambda item: item["slice_id"])]

    def _send(self, cmd: str) -> bool:
        """Send command to radio and wait for the matching command response."""
        ok, _response = self._send_with_response(cmd)
        return ok

    def _send_with_response(self, cmd: str):
        """Send command and return (success, response_body) for matching response."""
        if not self.connect():
            return False, ""
        with self._io_lock:
            old_timeout = None
            try:
                self.seq += 1
                seq = self.seq
                wire = f"C{seq}|{cmd}\r"
                logging.debug(f"FlexCtl SEND: {cmd}")
                self.sock.sendall(wire.encode("ascii", errors="ignore"))

                response_prefix = f"R{seq}|"
                old_timeout = self.sock.gettimeout()
                try:
                    self.sock.settimeout(0.25)
                except Exception:
                    old_timeout = None
                deadline = time.time() + 1.5
                saw_anything = False
                try:
                    while time.time() < deadline:
                        try:
                            chunk = self.sock.recv(4096)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        saw_anything = True
                        self._queue_received(chunk)
                        while self._pending_lines:
                            line = self._pending_lines.pop(0)
                            logging.debug(f"FlexCtl RECV: {line}")
                            self._record_basic_status_from_line(line)
                            if not line.startswith(response_prefix):
                                continue
                            parts = line.split("|", 2)
                            hex_resp = parts[1] if len(parts) >= 2 else ""
                            response_body = parts[2] if len(parts) >= 3 else ""
                            if hex_resp in {"00000000", "0"}:
                                return True, response_body
                            logging.warning(f"FlexCtl command '{cmd}' returned error: {hex_resp}")
                            return False, response_body
                except Exception as e:
                    logging.debug(f"FlexCtl recv exception (may be normal): {e}")

                if saw_anything:
                    logging.warning("FlexCtl command '%s' did not receive matching response %s", cmd, response_prefix)
                else:
                    logging.warning("FlexCtl command '%s' timed out without a response", cmd)
                return False, ""
            except Exception as e:
                logging.error(f"FlexCtl send FAILED for '{cmd}': {e}")
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
                return False, ""
            finally:
                try:
                    if self.sock and old_timeout is not None:
                        self.sock.settimeout(old_timeout)
                except Exception:
                    pass

    def get_current_levels(self, timeout: float = 1.5, *, apply_antenna_policy: bool = True):
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
        self._io_lock.acquire()
        old_timeout = None
        import re as _re
        import time as _t
        end = _t.time() + float(timeout)
        buf = b""
        levels = {}
        state_changed = {}
        try:
            if not self.connect():
                logging.warning("FlexCtl get_current_levels: not connected")
                self._io_lock.release()
                return {}

            logging.info("FlexCtl querying radio for current state...")

            # Collect responses for a while
            def parse_values(text: str) -> None:
                """Parse SmartSDR key/value state from a slice/transmit payload."""
                if not text:
                    return
                self._record_antenna_values(text, levels)

                m_vol = _re.search(r"\baudio_level=(\d+)", text)
                if m_vol:
                    levels["audio_level"] = int(m_vol.group(1))

                m_flo = _re.search(r"\bfilter_lo=(-?\d+)", text)
                if m_flo:
                    levels["filter_lo"] = int(m_flo.group(1))

                m_fhi = _re.search(r"\bfilter_hi=(-?\d+)", text)
                if m_fhi:
                    levels["filter_hi"] = int(m_fhi.group(1))

                m_freq = _re.search(r"\bRF_frequency=([\d.]+)", text)
                if not m_freq:
                    m_freq = _re.search(r"\bfreq=([\d.]+)", text)
                if m_freq:
                    levels["freq"] = float(m_freq.group(1))

                m_mode = _re.search(r"\bmode=([A-Z]+)", text)
                if m_mode:
                    levels["mode"] = m_mode.group(1)

                m_rit_on = _re.search(r"\brit_on=([01])", text)
                if m_rit_on:
                    levels["rit_on"] = bool(int(m_rit_on.group(1)))

                m_rit_freq = _re.search(r"\brit_freq=(-?\d+)", text)
                if m_rit_freq:
                    levels["rit_freq"] = int(m_rit_freq.group(1))

                m_xit_on = _re.search(r"\bxit_on=([01])", text)
                if m_xit_on:
                    levels["xit_on"] = bool(int(m_xit_on.group(1)))

                m_xit_freq = _re.search(r"\bxit_freq=(-?\d+)", text)
                if m_xit_freq:
                    levels["xit_freq"] = int(m_xit_freq.group(1))

                m_agc = _re.search(r"\bagc_mode=(\w+)", text)
                if m_agc:
                    levels["agc_mode"] = m_agc.group(1)

                m_agc_thresh = _re.search(r"\bagc_threshold=(\d+)", text)
                if m_agc_thresh:
                    levels["agc_threshold"] = int(m_agc_thresh.group(1))

                m_step = _re.search(r"\bstep=(\d+)", text)
                if m_step:
                    levels["step"] = int(m_step.group(1))

                for key in ("nb", "nr", "anf", "apf"):
                    m_enabled = _re.search(rf"\b{key}_on=([01])", text)
                    if m_enabled:
                        levels[key] = bool(int(m_enabled.group(1)))
                    m_level = _re.search(rf"\b{key}_level=(\d+)", text)
                    if m_level:
                        levels[f"{key}_level"] = int(m_level.group(1))

                m_state = _re.search(r"\bstate=([A-Z_]+)", text)
                if m_state:
                    levels["interlock_state"] = m_state.group(1)
                    levels["mox"] = levels["interlock_state"] == "TRANSMITTING"
                    if levels["mox"]:
                        self.last_tx_active_time = time.time()

                # ``sub tx all`` also returns one ``transmit band`` row per
                # saved band.  Those are persistence records, not live drive.
                m_rf = (
                    None
                    if "|transmit band " in text
                    else _re.search(r"\brfpower=(\d+)", text)
                )
                if m_rf:
                    levels["rfpower"] = int(m_rf.group(1))

                m_tune = _re.search(r"\btunepower=(\d+)", text)
                if m_tune:
                    levels["tunepower"] = int(m_tune.group(1))

                m_mic = _re.search(r"\bmiclevel=(\d+)", text)
                if m_mic:
                    levels["miclevel"] = int(m_mic.group(1))

                m_vox = _re.search(r"\bvox_enable=([01])", text)
                if m_vox:
                    levels["vox_enable"] = bool(int(m_vox.group(1)))

                m_breakin = _re.search(r"\bbreak_in=([01])", text)
                if m_breakin:
                    levels["break_in"] = bool(int(m_breakin.group(1)))

                m_mox = _re.search(r"\bmox=([01])", text)
                if m_mox:
                    levels["mox"] = bool(int(m_mox.group(1)))

                m_mon = _re.search(r"\bmon=([01])", text)
                if m_mon:
                    levels["mon"] = int(m_mon.group(1))

                m_mon_gain = _re.search(r"\bmon_gain_sb=(\d+)", text)
                if m_mon_gain:
                    levels["mon"] = int(m_mon_gain.group(1))

            def send_no_wait(cmd: str) -> None:
                self.seq += 1
                wire = f"C{self.seq}|{cmd}\r"
                logging.debug(f"FlexCtl SEND snapshot: {cmd}")
                self.sock.sendall(wire.encode("ascii", errors="ignore"))

            # Request current state
            ok, slice_body = self._send_with_response("slice list")
            if ok and slice_body:
                parse_values(slice_body)
            send_no_wait("sub slice all")
            send_no_wait("sub tx all")
        except Exception as e:
            logging.warning(f"FlexCtl get_current_levels: send error: {e}")

        try:
            old_timeout = self.sock.gettimeout()
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

                    self._record_basic_status_from_line(line)

                    # Any complete SmartSDR status/response received by this
                    # explicit snapshot is a fresh radio observation.  The
                    # background coordinator uses this timestamp to decide
                    # whether station actions may trust the FLEX route.
                    self.last_radio_message_time = _t.time()
                    
                    logging.debug(f"FlexCtl STATUS: {line}")
                    
                    # Parse slice status messages: S<handle>|slice <id> key=val key=val...
                    if "|slice " in line and f"slice {self.slice_id} " in line:
                        # Extract key=value pairs
                        match = _re.search(rf"\|slice\s+{self.slice_id}\s+(.+)$", line)
                        if match:
                            kvs = match.group(1)
                            self._record_antenna_values(kvs, levels, state_changed)
                            
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
                            if not m_freq:
                                m_freq = _re.search(r"\bfreq=([\d.]+)", kvs)
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
                        self._record_antenna_values(line, levels)

                        m_state = _re.search(r"\bstate=([A-Z_]+)", line)
                        if m_state:
                            levels["interlock_state"] = m_state.group(1)
                            levels["mox"] = levels["interlock_state"] == "TRANSMITTING"
                            if levels["mox"]:
                                self.last_tx_active_time = _t.time()
                            logging.debug(f"  Parsed interlock_state={levels['interlock_state']}")

                        # rfpower
                        m_rf = (
                            None
                            if "|transmit band " in line
                            else _re.search(r"\brfpower=(\d+)", line)
                        )
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

                        # mox
                        m_mox = _re.search(r"\bmox=([01])", line)
                        if m_mox:
                            levels["mox"] = bool(int(m_mox.group(1)))
                            if levels["mox"]:
                                self.last_tx_active_time = _t.time()
                            logging.debug(f"  Parsed mox={levels['mox']}")

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
        if "audio_level" in levels:
            self.current_volume = levels["audio_level"]
        if "rx_ant" in levels:
            self.current_rx_ant = levels["rx_ant"]
        if "tx_ant" in levels:
            self.current_tx_ant = levels["tx_ant"]
        if "rfpower" in levels:
            self.current_rfpower = levels["rfpower"]
        if "tunepower" in levels:
            self.current_tunepower = levels["tunepower"]
        if "miclevel" in levels:
            self.current_miclevel = levels["miclevel"]
        if "vox_enable" in levels:
            self.current_vox_enable = levels["vox_enable"]
        if "mox" in levels:
            self.current_mox = levels["mox"]
        if "interlock_state" in levels:
            self.current_interlock_state = levels["interlock_state"]
        if apply_antenna_policy and self.current_freq is not None:
            # During an externally-owned (MSHV) cross-band transition the
            # station interlock may prepare the target antenna before CAT has
            # moved the slice.  A background snapshot of the old frequency
            # must not immediately undo that preparation.
            policy_freq = self.current_freq
            pending_until = float(getattr(self, "pending_external_frequency_until", 0) or 0)
            if pending_until > time.time():
                policy_freq = float(getattr(self, "pending_external_frequency", policy_freq))
            else:
                self.pending_external_frequency = None
                self.pending_external_frequency_until = 0
            self.enforce_antenna_policy(policy_freq, reason="snapshot poll")
        
        logging.info(f"FlexCtl current state: {levels}")
        try:
            if self.sock and old_timeout is not None:
                self.sock.settimeout(old_timeout)
        except Exception:
            pass
        finally:
            self._io_lock.release()
        return levels

    def get_fresh_tx_state(self, timeout: float = 1.5):
        """Require TX state from an independent, newly subscribed TCP client.

        Re-subscribing an already subscribed socket does not always replay its
        current state.  A short-lived independent client has no cache and its
        initial TX subscription produces an authoritative interlock status.
        The probe never sends tune, MOX-on, PTT, or antenna commands.
        """
        requested_at = time.time()
        probe = self._new_tx_state_probe()
        try:
            connected = probe.connect_tx_state_probe(
                timeout,
                requested_at=requested_at,
            )
            observed_at = float(probe.last_tx_state_time or 0)
            return {
                "confirmed": bool(connected and observed_at >= requested_at),
                "requested_at": requested_at,
                "observed_at": observed_at,
                "mox": probe.current_mox,
                "interlock_state": probe.current_interlock_state,
            }
        finally:
            probe.close()

    def _new_tx_state_probe(self):
        return FlexCtl(self.host, self.port, self.slice_id)

    # --- Basic operations ---
    
    def set_mode(self, mode: str) -> bool:
        from services.digital_engine import backend_radio_control_allowed
        if not backend_radio_control_allowed():
            return False
        """Set demodulation mode (USB, LSB, CW, AM, FM, DIGU, DIGL, etc)."""
        mode_upper = (mode or '').upper()
        logging.info(f"FlexCtl set_mode: {mode_upper}")
        # Activate slice first (required for slice parameter changes)
        self._send(f"slice set {self.slice_id} active=1")
        ok = self._send(f"slice set {self.slice_id} mode={mode_upper}")
        
        if ok:
            self.current_mode = mode_upper
            self.last_command_time = time.time()
        return ok

    def tune_mhz(self, mhz: float) -> bool:
        from services.digital_engine import backend_radio_control_allowed
        if not backend_radio_control_allowed():
            return False
        """Tune slice to frequency in MHz."""
        try:
            f = float(mhz)
        except Exception:
            return False
        logging.info(f"FlexCtl tune to {f:.6f} MHz")
        ok = self._send(f"slice tune {self.slice_id} {f:.6f}")
        if ok:
            self.current_freq = f
            self.last_command_time = time.time()
            self.enforce_antenna_policy(f, reason="explicit tune")
        return ok

    def set_band(self, band: str) -> bool:
        from services.digital_engine import backend_radio_control_allowed
        if not backend_radio_control_allowed():
            return False
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

        self._io_lock.acquire()
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
        finally:
            self._io_lock.release()

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
        target = self.current_tx_slice_id
        if target is None:
            target = self.slice_id
        return self._send(f"slice set {target} tx=1")

    def _ensure_gui_binding(self, *, force: bool = False) -> bool:
        """Bind transmitter controls to the active SmartSDR GUI context.

        SmartSDR may invalidate a non-GUI client's binding when another client
        (notably MSHV) reconnects.  Transmitter writes therefore use ``force``
        so an earlier successful bind is never treated as permanent.
        """
        if not force and self._gui_binding_confirmed and self.bound_gui_client_id:
            return True
        if force:
            self._gui_binding_confirmed = False
        if not self._send("sub client all") or not self.bound_gui_client_id:
            return False
        self._gui_binding_confirmed = self._send(
            f"client bind client_id={self.bound_gui_client_id}"
        )
        return self._gui_binding_confirmed

    def set_rf_power(self, pct: int) -> bool:
        """Set RF power 1-100. API uses 'rfpower'."""
        pct = max(1, min(100, int(pct)))
        logging.info(f"FlexCtl set_rf_power: {pct}")
        # Explicitly bind the transmitter to this slice before changing drive.
        # A successful command response only confirms that SmartSDR accepted
        # the write; subscribed radio state remains the readback authority.
        if not self._ensure_gui_binding(force=True) or not self._set_tx_slice():
            return False
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
        from services.digital_engine import backend_radio_control_allowed
        if on and not backend_radio_control_allowed():
            return False
        """Toggle TUNE mode. API command is 'transmit tune on' or 'transmit tune off'."""
        logging.info(f"FlexCtl set_tune: {'ON' if on else 'OFF'}")
        return self._send(f"transmit tune {'on' if on else 'off'}")

    def set_mox(self, on: bool) -> bool:
        from services.digital_engine import backend_radio_control_allowed
        if on and not backend_radio_control_allowed():
            return False
        """Toggle MOX (manual transmit)."""
        logging.info(f"FlexCtl set_mox: {'ON' if on else 'OFF'}")
        self._set_tx_slice()
        if self._send(f"xmit {'1' if on else '0'}"):
            return True
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
            self._send("transmit set mon=1")
        elif level == 0:
            self._send("transmit set mon=0")
        
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

        self._io_lock.acquire()
        try:
            import re as _re
            import time as _time
            # Keep this drain bounded. SmartSDR meter/status traffic can be
            # continuous; waiting for a quiet socket would otherwise hold the
            # process-wide main Flex I/O lock indefinitely and starve safety
            # operations queued behind it.
            old_timeout = self.sock.gettimeout()
            drain_started = _time.monotonic()
            drain_deadline = drain_started + 0.15
            max_messages = 256
            self.sock.settimeout(0.05)
            logging.debug(f"🔍 REFRESH STARTING: Connected to {self.host}:{self.port}, slice_id={self.slice_id}")
            
            # Re-subscribe only occasionally. Doing this every poll creates
            # noisy SmartSDR client activity and can make the radio look like
            # it is constantly being reconnected.
            now = _time.time()
            if now - float(self.last_resubscribe_time or 0) > 60:
                try:
                    self._send("sub slice all")
                    self._send("sub tx all")
                    self.last_resubscribe_time = now
                except Exception as e:
                    logging.debug(f"FlexCtl re-subscription attempt: {e}")
            
            # Read ALL pending messages from socket (not just one!)
            messages_read = 0
            state_changed = {}  # Track what changed
            
            while messages_read < max_messages and _time.monotonic() < drain_deadline:
                try:
                    if self._pending_lines:
                        resp = self._pending_lines.pop(0)
                    else:
                        remaining = max(0.001, drain_deadline - _time.monotonic())
                        self.sock.settimeout(min(0.05, remaining))
                        chunk = self.sock.recv(4096)
                        if not chunk:
                            logging.warning("FlexCtl socket closed by SmartSDR")
                            try:
                                self.sock.close()
                            except Exception:
                                pass
                            self.sock = None
                            self._receive_buffer = b""
                            self._pending_lines.clear()
                            return False
                        self._queue_received(chunk)
                        if not self._pending_lines:
                            continue
                        resp = self._pending_lines.pop(0)
                    
                    messages_read += 1
                    self.last_radio_message_time = _time.time()
                    logging.debug(f"FlexCtl refresh: {resp[:100]}...")  # Log first 100 chars
                    
                    # Parse ALL subscription updates for mode/freq/filter/band changes
                    if "|slice" in resp and f"slice {self.slice_id} " in resp:
                        logging.debug("FlexCtl: Processing slice message")
                        # LOG ACTUAL MESSAGE for debugging - this will show us what fields are in it!
                        logging.info(f"🔍 SLICE MESSAGE: {resp[:200]}")
                        self._record_antenna_values(resp, state_changed=state_changed)
                        antenna_changed = "rx_ant" in state_changed or "tx_ant" in state_changed
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
                            self.enforce_antenna_policy(new_freq, reason="radio frequency update")
                        else:
                            logging.debug("❌ NO FREQUENCY FIELD FOUND in slice message")
                            if antenna_changed and self.current_freq:
                                self.enforce_antenna_policy(self.current_freq, reason="radio antenna update")
                        
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
                        self._record_antenna_values(resp, state_changed=state_changed)

                        m_state = _re.search(r"\bstate=([A-Z_]+)", resp)
                        if m_state:
                            self.last_tx_state_time = _time.time()
                            new_state = m_state.group(1)
                            if self.current_interlock_state is None or new_state != self.current_interlock_state:
                                state_changed['interlock_state'] = new_state
                                logging.info(f"FlexCtl: INTERLOCK STATE CHANGED: {self.current_interlock_state} → {new_state}")
                            self.current_interlock_state = new_state
                            if new_state == "TRANSMITTING":
                                new_mox = True
                            elif new_state in {"READY", "RECEIVE", "NOT_READY", "TIMEOUT", "TX_FAULT"}:
                                new_mox = False
                            else:
                                new_mox = self.current_mox
                            if new_mox is not None and (self.current_mox is None or new_mox != self.current_mox):
                                state_changed['mox'] = new_mox
                            if new_mox is not None:
                                self.current_mox = new_mox
                                if new_mox:
                                    self.last_tx_active_time = _time.time()
                            if (
                                not self.current_mox
                                and self._pending_antenna_policy_freq is not None
                            ):
                                self.enforce_antenna_policy(
                                    self._pending_antenna_policy_freq,
                                    reason="deferred after TX",
                                )

                        # MOX state (transmit on/off)
                        m_mox = _re.search(r"\bmox=([01])", resp)
                        if m_mox:
                            self.last_tx_state_time = _time.time()
                            new_mox = bool(int(m_mox.group(1)))
                            if self.current_mox is None or new_mox != self.current_mox:
                                if self.current_mox is not None:
                                    logging.info(f"FlexCtl: MOX STATE CHANGED: {self.current_mox} → {new_mox}")
                                state_changed['mox'] = new_mox
                            self.current_mox = new_mox
                            if self.current_mox:
                                self.last_tx_active_time = _time.time()
                            if not self.current_mox and self._pending_antenna_policy_freq is not None:
                                self.enforce_antenna_policy(
                                    self._pending_antenna_policy_freq,
                                    reason="deferred after MOX",
                                )
                    
                    # Parse transmit/interlock updates for mic/drive/tune power changes
                    if "|transmit " in resp or "|interlock " in resp:
                        # rfpower (Drive) - map to 'drive' for frontend
                        m_rf = (
                            None
                            if "|transmit band " in resp
                            else _re.search(r"\brfpower=(\d+)", resp)
                        )
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

            if self._pending_antenna_policy_freq is not None and not self._tx_active_recently():
                self.enforce_antenna_policy(
                    self._pending_antenna_policy_freq,
                    reason="deferred poll retry",
                )

            # Return state_changed dict for UI updates
            self.last_state_changed = state_changed
            
            budget_exhausted = bool(
                messages_read >= max_messages or _time.monotonic() >= drain_deadline
            )
            logging.debug(
                "FlexCtl refresh: read=%d duration_ms=%d budget_exhausted=%s changes=%s",
                messages_read,
                round((_time.monotonic() - drain_started) * 1000),
                budget_exhausted,
                list(state_changed.keys()),
            )
            return True
            
        except Exception as e:
            logging.error(f"FlexCtl refresh_radio_state FAILED: {e}")
            return False
        finally:
            self._io_lock.release()
