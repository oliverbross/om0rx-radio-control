# spot_ui.py - Spot display UI with Tkinter

import logging
import queue
import threading
from radio_control.classifier import FilterModel
from radio_control.ui_components import MultiCheckDropdown
from radio_control.utils import _apply_dark_theme
from radio_control.ui_dialogs import _attach_menu_to_root
from radio_control.flex_radio import FlexCtl
from radio_control.config import FLEX_TCP_HOST, FLEX_TCP_PORT, SPECIAL_PATTERNS

class SpotUi:
    def __init__(self, enabled=False):
        self.enabled=enabled; self.q=queue.Queue(); self.thread=None; self.filter=FilterModel(); self.rows=[]
        self._opt_bands=set(); self._opt_modes=set(); self._opt_cq=set(); self._opt_cs=set(); self._opt_dxcc=set(); self._opt_special=set()

    def start(self):
        if not self.enabled: return
        def run():
            try:
                import tkinter as tk
                from tkinter import ttk
            except Exception as e:
                logging.warning("UI disabled (Tk): %s", e); return

            root=tk.Tk(); root.title("Wave-Flex Bridge — Live Spots")
            _apply_dark_theme(root)
            _apply_dark_theme(root)
            _attach_menu_to_root(root)

            ctrl=ttk.Frame(root); ctrl.pack(fill='x', padx=6, pady=4)

            # --- FlexRadio Control toolbar ---
            try:
                flex_host = FLEX_TCP_HOST
                flex_port = int(FLEX_TCP_PORT)
            except Exception:
                flex_host, flex_port = '127.0.0.1', 4992

            flex_fr = ttk.Labelframe(root, text="FlexRadio Control")
            flex_fr.pack(fill='x', padx=6, pady=(0,6))

            # Create controller FIRST (Slice A = 0) - MUST be before UI controls that reference it
            _flex_ctl = FlexCtl(flex_host, flex_port, slice_id=0)
            
            # ---- New right-side control strip (Volume/Mute, Drive, Tune power, Mic; TUNE/MOX/VOX) ----
            strip = ttk.Frame(flex_fr)

            # Vars for sliders + numeric readouts
            vol_var  = tk.IntVar(value=0)
            drv_var  = tk.IntVar(value=10)
            tun_var  = tk.IntVar(value=10)
            mic_var  = tk.IntVar(value=0)

            # Volume + mute
            mute_var = tk.BooleanVar(value=False)
            ttk.Label(strip, text='Volume').pack(side='left', padx=(12,4))
            vol_scale = ttk.Scale(strip, from_=0, to=100, orient='horizontal', length=120, variable=vol_var,
                      command=lambda v: (val_vol.config(text=str(int(float(v)))), _flex_ctl.set_volume(int(float(v)))))
            vol_scale.pack(side='left')
            ttk.Checkbutton(strip, text='🔈', variable=mute_var,
                            command=lambda: _flex_ctl.set_volume_mute(mute_var.get())).pack(side='left', padx=4)

            # Drive
            ttk.Label(strip, text='Drive').pack(side='left', padx=(12,4))
            drv_scale = ttk.Scale(strip, from_=1, to=100, orient='horizontal', length=110, variable=drv_var,
                      command=lambda v: (val_drv.config(text=str(int(float(v)))), _flex_ctl.set_rf_power(int(float(v)))))
            drv_scale.pack(side='left')

            # Tune power
            ttk.Label(strip, text='Tune').pack(side='left', padx=(12,4))
            tun_scale = ttk.Scale(strip, from_=1, to=100, orient='horizontal', length=110, variable=tun_var,
                      command=lambda v: (val_tun.config(text=str(int(float(v)))), _flex_ctl.set_tune_power(int(float(v)))))
            tun_scale.pack(side='left')

            # Mic level
            ttk.Label(strip, text='Mic').pack(side='left', padx=(12,4))
            mic_scale = ttk.Scale(strip, from_=0, to=100, orient='horizontal', length=110, variable=mic_var,
                      command=lambda v: (val_mic.config(text=str(int(float(v)))), _flex_ctl.set_mic_level(int(float(v)))))
            mic_scale.pack(side='left')

            # Pack the slider strip first (so it appears at the top)
            strip.pack(side='top', anchor='e', padx=8, pady=4)

            # small numeric readouts under sliders (create frame but don't pack yet)
            vals = ttk.Frame(flex_fr)
            ttk.Label(vals, text='Vol').pack(side='left', padx=(16,2))
            val_vol = ttk.Label(vals, text='0'); val_vol.pack(side='left')
            ttk.Label(vals, text='   Drive').pack(side='left', padx=(24,2))
            val_drv = ttk.Label(vals, text='10'); val_drv.pack(side='left')
            ttk.Label(vals, text='   Tune').pack(side='left', padx=(24,2))
            val_tun = ttk.Label(vals, text='10'); val_tun.pack(side='left')
            ttk.Label(vals, text='   Mic').pack(side='left', padx=(24,2))
            val_mic = ttk.Label(vals, text='0'); val_mic.pack(side='left')
            # Filter values display
            ttk.Label(vals, text='   Lo').pack(side='left', padx=(24,2))
            val_flo = ttk.Label(vals, text='—'); val_flo.pack(side='left')
            ttk.Label(vals, text='   Hi').pack(side='left', padx=(8,2))
            val_fhi = ttk.Label(vals, text='—'); val_fhi.pack(side='left')
            
            # Pack the value labels AFTER the sliders (so they appear below)
            vals.pack(side='top', anchor='e', padx=6, pady=(0,2))

            # Try to pull initial levels from radio NOW (after all UI elements exist)
            try:
                logging.info("Fetching initial radio state...")
                _levels = _flex_ctl.get_current_levels()
                logging.info(f"Got initial levels: {_levels}")
                
                # Update UI with current radio state
                # CRITICAL: Use correct API parameter names!
                if 'audio_level' in _levels:  # NOT audio_gain
                    vol_var.set(int(_levels['audio_level']))
                    val_vol.config(text=str(vol_var.get()))
                    logging.info(f"Set volume slider to {vol_var.get()}")
                
                if 'rfpower' in _levels:
                    drv_var.set(int(_levels['rfpower']))
                    val_drv.config(text=str(drv_var.get()))
                    logging.info(f"Set drive slider to {drv_var.get()}")
                
                if 'tunepower' in _levels:  # NOT tune_power
                    tun_var.set(int(_levels['tunepower']))
                    val_tun.config(text=str(tun_var.get()))
                    logging.info(f"Set tune power slider to {tun_var.get()}")
                
                if 'miclevel' in _levels:  # NOT mic_level
                    mic_var.set(int(_levels['miclevel']))
                    val_mic.config(text=str(mic_var.get()))
                    logging.info(f"Set mic slider to {mic_var.get()}")
                
                if 'filter_lo' in _levels:
                    val_flo.config(text=str(_levels['filter_lo']))
                    logging.info(f"Set filter_lo display to {_levels['filter_lo']}")
                
                if 'filter_hi' in _levels:
                    val_fhi.config(text=str(_levels['filter_hi']))
                    logging.info(f"Set filter_hi display to {_levels['filter_hi']}")
                
                # TODO: Highlight current band and mode buttons based on freq and mode
                
            except Exception as _e:
                logging.error(f"Init levels fetch failed: {_e}", exc_info=True)

            # TUNE / MOX / VOX toggles
            tune_on = tk.BooleanVar(value=False)
            mox_on  = tk.BooleanVar(value=False)
            vox_on  = tk.BooleanVar(value=False)
            tune_state = tk.BooleanVar(value=False)
            mox_state  = tk.BooleanVar(value=False)
            
            # Update VOX from initial state if available
            if 'vox_enable' in _levels:
                vox_on.set(_levels['vox_enable'])
                logging.info(f"Set VOX checkbox to {_levels['vox_enable']}")
            
            def _toggle_tune():
                tune_state.set(not tune_state.get())
                _flex_ctl.set_tune(tune_state.get())
                btn_tune.config(text='TUNE ON' if tune_state.get() else 'TUNE')
            def _toggle_mox():
                mox_state.set(not mox_state.get())
                _flex_ctl.set_mox(mox_state.get())
                btn_mox.config(text='MOX ON' if mox_state.get() else 'MOX')
            btn_tune = ttk.Button(strip, text='TUNE', command=_toggle_tune); btn_tune.pack(side='left', padx=6)
            btn_mox  = ttk.Button(strip, text='MOX',  command=_toggle_mox);  btn_mox.pack(side='left', padx=6)
            ttk.Checkbutton(strip, text='VOX', variable=vox_on,
                            command=lambda: _flex_ctl.set_vox(vox_on.get())).pack(side='left', padx=6)
            # ---- Dynamic filter bar under the modes row ----
            filter_fr = ttk.Frame(flex_fr); filter_fr.pack(fill='x', padx=6, pady=(0,4), side='bottom')
            ttk.Label(filter_fr, text='Filters:').pack(side='left', padx=(0,8))

            def _fmt_bw(hz:int)->str:
                return f"{hz/1000:.1f}K" if hz>=1000 else f"{hz} Hz"

            def _set_filter(mode:str, bw:int):
                # map to lo/hi
                m = mode.upper()
                if m in ('USB','DIGU'):
                    lo, hi = 100, min(100+bw, 12000)
                elif m in ('LSB','DIGL'):
                    lo, hi = -(100+bw), -100
                elif m=='AM':
                    half = max(300, bw//2); lo, hi = -half, half
                elif m=='CW':
                    half = max(25,  bw//2); lo, hi = -half, half
                else:
                    lo, hi = 100, min(100+bw, 12000)
                ok = _flex_ctl.set_filter_edges(lo, hi)
                if ok:
                    val_flo.config(text=str(lo))
                    val_fhi.config(text=str(hi))
                    # Update stored filter values for highlighting
                    _flex_ctl.current_filter_lo = lo
                    _flex_ctl.current_filter_hi = hi
                    # Re-highlight filter buttons
                    refresh_filter_buttons(mode)
                else:
                    logging.warning(f"Filter command failed: lo={lo}, hi={hi} for mode={mode}")

            def refresh_filter_buttons(cur_mode:str):
                # remove old
                for w in list(filter_fr.pack_slaves())[1:]:
                    w.destroy()
                if cur_mode in ('USB','LSB'):
                    presets = [1800,2100,2400,2700,2900,3300,4000,6000]
                elif cur_mode in ('DIGU','DIGL'):
                    presets = [100,300,600,1000,1500,2000,3000,6000]
                elif cur_mode=='AM':
                    # FlexRadio AM filter widths supported by SmartSDR
                    presets = [5600,6000,8000,10000,12000,14000,16000,20000]
                elif cur_mode=='CW':
                    # FlexRadio CW filter widths supported by SmartSDR
                    presets = [50,100,250,400,500,800,1000,3000]  # Total bandwidth in Hz
                else:
                    presets = [2400,2700,2900]
                for bw in presets:
                    btn = ttk.Button(filter_fr, text=_fmt_bw(bw),
                                command=lambda mm=cur_mode, ww=bw: _set_filter(mm, ww))
                    btn.pack(side='left', padx=2)
                    # Highlight current filter if matches
                    try:
                        if hasattr(_flex_ctl, 'current_filter_lo') and hasattr(_flex_ctl, 'current_filter_hi') and _flex_ctl.current_filter_lo is not None and _flex_ctl.current_filter_hi is not None:
                            m = cur_mode.upper()  # Use cur_mode, not mm (which is lambda capture)
                            if m in ('USB','DIGU'):
                                expected_lo, expected_hi = 100, min(100+bw, 12000)
                            elif m in ('LSB','DIGL'):
                                expected_lo, expected_hi = -(100+bw), -100
                            elif m=='AM':
                                half = max(300, bw//2); expected_lo, expected_hi = -half, half
                            elif m=='CW':
                                half = max(25,  bw//2); expected_lo, expected_hi = -half, half
                            else:
                                expected_lo, expected_hi = 100, min(100+bw, 12000)
                            
                            # Debug logging
                            logging.debug(f"Filter button {_fmt_bw(bw)}: expected_lo={expected_lo}, expected_hi={expected_hi}, current_lo={_flex_ctl.current_filter_lo}, current_hi={_flex_ctl.current_filter_hi}")
                            
                            if expected_lo == _flex_ctl.current_filter_lo and expected_hi == _flex_ctl.current_filter_hi:
                                btn.config(style='Highlight.TButton')
                                logging.debug(f"Filter button {_fmt_bw(bw)} HIGHLIGHTED")
                    except Exception as e:
                        logging.error(f"Filter highlight error for {_fmt_bw(bw)}: {e}", exc_info=True)

            # seed as USB
            refresh_filter_buttons('USB')
# Filters Setup block under Flexradio Control
            filters_fr = ttk.Labelframe(root, text='Filters Setup')
            filters_fr.pack(fill='x', padx=6, pady=(0,6))


            # FlexCtl controller was already created above (before UI controls)
            
            # Store button references for highlighting
            band_buttons = {}
            mode_buttons = {}

            def _flex_band(b):
                ok = _flex_ctl.set_band(b)
                if ok:
                    # Highlight the selected band button
                    for btn_b, btn_widget in band_buttons.items():
                        if btn_b == b:
                            btn_widget.config(style='Highlight.TButton')
                        else:
                            btn_widget.config(style='TButton')
                if not ok:
                    logging.warning("Failed to switch Flex to band %s", b)

            def _flex_mode(m):
                ok = _flex_ctl.set_mode(m)
                if ok:
                    # Highlight the selected mode button
                    for btn_m, btn_widget in mode_buttons.items():
                        if btn_m == m:
                            btn_widget.config(style='Highlight.TButton')
                        else:
                            btn_widget.config(style='TButton')
                try:
                    refresh_filter_buttons(m)
                except Exception:
                    pass
                if not ok:
                    logging.warning("Failed to set Flex mode %s", m)

            # Bands row
            bands = ['160m','80m','60m','40m','30m','20m','17m','15m','12m','10m','6m']
            b_row = ttk.Frame(flex_fr); b_row.pack(fill='x', padx=6, pady=4)
            for b in bands:
                btn = ttk.Button(b_row, text=b.upper(), width=6, command=lambda bb=b: _flex_band(bb))
                btn.pack(side='left', padx=2, pady=2)
                band_buttons[b] = btn

            # Modes row
            m_row = ttk.Frame(flex_fr); m_row.pack(fill='x', padx=6, pady=(0,6))
            # Sideband helpers based on common convention: 160-40 LSB, 20-6 USB.
            def _set_sideband_for_current(band_name):
                b = (band_name or '').lower()
                if b in ('160m','80m','40m'):
                    _flex_mode('LSB')
                else:
                    _flex_mode('USB')
            # Explicit mode buttons
            for label, mode in [('LSB','LSB'),('USB','USB'),('CW','CW'),('AM','AM'),('DIGU','DIGU'),('DIGL','DIGL')]:
                btn = ttk.Button(m_row, text=label, width=6, command=lambda mm=mode: (_flex_mode(mm), refresh_filter_buttons(mm)))
                btn.pack(side='left', padx=2, pady=2)
                mode_buttons[mode] = btn

            # NOW sync UI with current radio state (band, mode, filter)
            def _sync_ui_with_radio():
                """Highlight current band, mode, and filter buttons based on radio state"""
                try:
                    logging.debug("Syncing UI buttons with current radio state...")
                    
                    # Use FlexCtl instance variables (updated by _send() parsing and subscriptions)
                    freq_mhz = _flex_ctl.current_freq
                    current_mode = _flex_ctl.current_mode
                    filter_lo = _flex_ctl.current_filter_lo
                    filter_hi = _flex_ctl.current_filter_hi
                    
                    logging.debug(f"Radio state from FlexCtl: freq={freq_mhz}, mode={current_mode}, filter_lo={filter_lo}, filter_hi={filter_hi}")
                    
                    # Determine band from frequency
                    if freq_mhz:
                        current_band = None
                        # Map frequency to band
                        if 1.8 <= freq_mhz < 2.0:
                            current_band = '160m'
                        elif 3.5 <= freq_mhz < 4.0:
                            current_band = '80m'
                        elif 5.0 <= freq_mhz < 6.0:
                            current_band = '60m'
                        elif 7.0 <= freq_mhz < 7.3:
                            current_band = '40m'
                        elif 10.0 <= freq_mhz < 10.2:
                            current_band = '30m'
                        elif 14.0 <= freq_mhz < 14.4:
                            current_band = '20m'
                        elif 18.0 <= freq_mhz < 18.2:
                            current_band = '17m'
                        elif 21.0 <= freq_mhz < 21.5:
                            current_band = '15m'
                        elif 24.8 <= freq_mhz < 25.0:
                            current_band = '12m'
                        elif 28.0 <= freq_mhz < 29.7:
                            current_band = '10m'
                        elif 50.0 <= freq_mhz < 54.0:
                            current_band = '6m'
                        
                        if current_band:
                            logging.info(f"Current band: {current_band} (freq={freq_mhz} MHz)")
                            for b, btn_widget in band_buttons.items():
                                if b.lower() == current_band.lower():
                                    btn_widget.config(style='Highlight.TButton')
                                    logging.debug(f"Band button {b} HIGHLIGHTED")
                                else:
                                    btn_widget.config(style='TButton')
                    
                    # Highlight mode button
                    if current_mode:
                        logging.debug(f"Current mode: {current_mode}")
                        mode_upper = current_mode.upper() if current_mode else ""
                        for m, btn_widget in mode_buttons.items():
                            if m.upper() == mode_upper:
                                btn_widget.config(style='Highlight.TButton')
                                logging.debug(f"Mode button {m} HIGHLIGHTED")
                            else:
                                btn_widget.config(style='TButton')
                        
                        # Refresh filter buttons for current mode and highlight active filter
                        logging.debug(f"Refreshing filter buttons for mode: {current_mode}")
                        refresh_filter_buttons(current_mode)
                    
                    # Update filter value displays
                    if filter_lo is not None:
                        val_flo.config(text=str(filter_lo))
                    if filter_hi is not None:
                        val_fhi.config(text=str(filter_hi))
                    
                    # Sync transmit parameters (mic/drive/tune) if they changed in SmartSDR
                    if hasattr(_flex_ctl, 'last_state_changed'):
                        state_changes = _flex_ctl.last_state_changed
                        
                        # Update mic level slider
                        if 'miclevel' in state_changes:
                            new_mic = state_changes['miclevel']
                            mic_var.set(new_mic)
                            val_mic.config(text=str(new_mic))
                            logging.info(f"UI SYNC: Mic slider updated to {new_mic}")
                        
                        # Update drive slider
                        if 'rfpower' in state_changes:
                            new_drive = state_changes['rfpower']
                            drv_var.set(new_drive)
                            val_drv.config(text=str(new_drive))
                            logging.info(f"UI SYNC: Drive slider updated to {new_drive}")
                        
                        # Update tune power slider
                        if 'tunepower' in state_changes:
                            new_tune = state_changes['tunepower']
                            tun_var.set(new_tune)
                            val_tun.config(text=str(new_tune))
                            logging.info(f"UI SYNC: Tune slider updated to {new_tune}")
                        
                        # Update VOX checkbox
                        if 'vox_enable' in state_changes:
                            new_vox = state_changes['vox_enable']
                            vox_on.set(new_vox)
                            logging.info(f"UI SYNC: VOX checkbox updated to {new_vox}")
                        
                        # Clear state_changed dict after processing
                        _flex_ctl.last_state_changed = {}
                    
                except Exception as e:
                    logging.error(f"Failed to sync UI with radio: {e}", exc_info=True)
            
            # Continuous polling function for 2-way sync
            def _poll_radio_state():
                """Continuously poll radio state to detect external changes (from SmartSDR)"""
                try:
                    # First, query radio to read ALL pending subscription updates
                    # This catches external changes made in SmartSDR (mode/freq/filter/band)
                    _flex_ctl.refresh_radio_state()
                    
                    # Then sync UI with updated radio state
                    _sync_ui_with_radio()
                except Exception as e:
                    logging.error(f"Error during radio state polling: {e}", exc_info=True)
                finally:
                    # Schedule next poll (every 1 second for fast response)
                    root.after(1000, _poll_radio_state)
            
            # Start initial sync after a short delay, then begin continuous polling
            root.after(500, _poll_radio_state)

            # helper to check row against UI (including "Special" which may not exist in FilterModel)
            def _row_matches(row):
                # Update FilterModel from dropdowns
                self.filter.bands = dd_band.get_selected()
                self.filter.modes = dd_mode.get_selected()
                self.filter.cq    = dd_cq.get_selected()
                self.filter.call_status = dd_cs.get_selected()
                self.filter.dxcc  = dd_dx.get_selected()
                # Try to set special if FilterModel supports it
                try:
                    self.filter.special = dd_sp.get_selected()
                except Exception:
                    pass
                base_ok = self.filter.match(row)

                # apply "Special" locally as well (supports comma-separated specials)
                sp_sel = dd_sp.get_selected()  # None => All
                if sp_sel is None:
                    return base_ok
                raw = (row[10] or "").strip()
                if not raw:
                    row_tags = {"(none)"}
                else:
                    row_tags = {t.strip() for t in raw.split(",") if t.strip()}
                # if user selected "(none)", match rows with no specials
                if "(none)" in sp_sel and row_tags == {"(none)"}:
                    return base_ok
                return base_ok and (len(row_tags & sp_sel) > 0)

            def refresh_table():
                for i in tv.get_children(): tv.delete(i)
                for r,tag in reversed(self.rows):
                    if _row_matches(r):
                        # Apply DXCC status filter on row tag if user selected any
                        _dx_sel = dd_dx.get_selected()
                        if _dx_sel is not None:
                            if not tag or tag not in _dx_sel:
                                continue
                        tv.insert('', 'end', values=r, tags=(tag,) if tag else ())

            dd_band = MultiCheckDropdown(filters_fr, "Band:", [], on_change=refresh_table)
            dd_mode = MultiCheckDropdown(filters_fr, "Mode:", [], on_change=refresh_table)
            dd_cq   = MultiCheckDropdown(filters_fr, "CQ:",   [], on_change=refresh_table)
            dd_cs   = MultiCheckDropdown(filters_fr, "Call Status:", [], on_change=refresh_table)
            dd_dx   = MultiCheckDropdown(filters_fr, "DXCC:", [], on_change=refresh_table)
            dd_sp   = MultiCheckDropdown(filters_fr, "Special:", [], on_change=refresh_table)
            try:
                import config as _cfg_sp
                self._opt_special = set(['(none)'] + list(getattr(_cfg_sp, 'SPECIAL_PRESET', [])))
                dd_sp.set_options(sorted(self._opt_special))
            except Exception:
                pass

                        # Pre-populate dropdowns immediately (no need to wait for a spot)
            _fixed_bands = ['160m','80m','60m','40m','30m','20m','17m','15m','12m','10m','6m']
            _fixed_modes = ['CW','SSB','LSB','USB','AM','FM','DIGU','DIGL','FT8','FT4','RTTY','SSTV']
            _fixed_cq    = [str(i) for i in range(1,41)]
            _fixed_cs    = ['New Call','Worked','Confirmed','New Band','New Mode','New Band+Mode']
            _dx_statuses = ['ATNO','New band','New mode','New band+mode','Need LoTW','Worked','Confirmed']
            try:
                import config as _cfg
                _special_from_cfg = list(getattr(_cfg, 'SPECIAL_PRESET', []))
            except Exception:
                _special_from_cfg = []
            _special_opts = ['(none)'] + [x for x in _special_from_cfg if x and x != '(none)']
            dd_band.set_options(_fixed_bands)
            dd_mode.set_options(_fixed_modes)
            dd_cq.set_options(_fixed_cq)
            dd_cs.set_options(_fixed_cs)
            dd_dx.set_options(_dx_statuses)
            dd_sp.set_options(_special_opts)
            for dd in (dd_band, dd_mode, dd_cq, dd_cs, dd_dx, dd_sp):
                dd.frame.pack(side='left', padx=6)

            cols=("Time(UTC)","Band","kHz","Mode","Callsign","Country","CQ","Spotter","Call Status","DXCC","Special","Comment")
            tv=ttk.Treeview(root, columns=cols, show="headings", height=26)
            widths={"Time(UTC)":120,"Band":60,"kHz":80,"Mode":70,"Callsign":90,"Country":160,"CQ":40,
                    "Spotter":90,"Call Status":120,"DXCC":120,"Special":200,"Comment":420}
            for c in cols:
                tv.heading(c, text=c)
                tv.column(c, width=widths.get(c,110), anchor="w", stretch=(c=="Comment"))
            try:
                import config as _cfg_colors
                for _k,_v in getattr(_cfg_colors, "COLORS", {}).items():
                    if _k != "Default":
                        try: tv.tag_configure(_k, background=_to_tk_hex(_v))
                        except Exception: pass
            except Exception:
                pass
            tv.pack(fill="both", expand=True)

            def _add_special_options_from_raw(raw):
                raw = (raw or "").strip()
                if not raw:
                    self._opt_special.add("(none)")
                    return True
                changed=False
                for t in [t.strip() for t in raw.split(",") if t.strip()]:
                    if t not in self._opt_special:
                        self._opt_special.add(t); changed=True
                return changed

            def _update_option_sets_from_row(row):
                b=row[1]; m=row[3]; cq=row[6]; cs=row[8]; dx=row[9]; sp=row[10]
                updated=False
                if b not in self._opt_bands: self._opt_bands.add(b); updated=True
                if m not in self._opt_modes: self._opt_modes.add(m); updated=True
                if cq and cq not in ("-",) and cq not in self._opt_cq: self._opt_cq.add(cq); updated=True
                if cs not in self._opt_cs: self._opt_cs.add(cs); updated=True
                if dx not in self._opt_dxcc: self._opt_dxcc.add(dx); updated=True
                if _add_special_options_from_raw(sp): updated=True
                if updated:
                    dd_band.set_options(self._opt_bands)
                    dd_mode.set_options(self._opt_modes)
                    dd_cq.set_options(sorted(self._opt_cq, key=lambda x: (len(x), x)))
                    dd_cs.set_options(self._opt_cs)
                    # dd_dx.set_options(self._opt_dxcc)  # keep DXCC dropdown as status buckets
                    dd_sp.set_options(self._opt_special)

            def pump():
                try:
                    while True:
                        row,tag=self.q.get_nowait()
                        self.rows.append((row,tag))
                        _update_option_sets_from_row(row)
                        if _row_matches(row):
                            tv.insert("",0,values=row,tags=(tag,) if tag else ())
                except queue.Empty: pass
                root.after(200,pump)

            pump(); root.mainloop()

        self.thread=threading.Thread(target=run,daemon=True); self.thread.start()

    def add(self,row,tag=None):
        if self.enabled: self.q.put((row,tag))

class BridgeRuntime:
    def __init__(self):
        self.spots_seen=0; self.spots_sent=0; self.spots_dedup=0
        self.cluster_connected=False; self.udp_ok=False; self.flex_ok=False; self.last_spot_at=None

def _to_tk_hex(val:str) -> str:
    try:
        if not isinstance(val, str):
            return val
        s = val.strip()
        if s.startswith('#'):
            s = s[1:]
        # If ARGB (8 bytes), drop alpha
        if len(s) == 8:
            s = s[2:]
        if len(s) == 6:
            return '#' + s
    except Exception:
        pass
    return val

def color_for_tag(tag:str):
    try:
        import config as _cfgc
        cmap = getattr(_cfgc, "COLORS", {})
        return cmap.get(tag, cmap.get("Default", COLOR_DEFAULT))
    except Exception:
        return COLOR_DEFAULT
