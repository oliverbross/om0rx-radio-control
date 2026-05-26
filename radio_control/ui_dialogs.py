# ui_dialogs.py - Dialog windows and UI helper components

import webbrowser
import logging
from radio_control.config_manager import _read_config_values, _update_config_file
from radio_control.utils import flex_probe_info


def _center_window(win, parent=None):
    """Center a window on its parent or screen"""
    try:
        win.update_idletasks()
        if parent is None:
            parent = win.master
        px = parent.winfo_rootx() if parent else 0
        py = parent.winfo_rooty() if parent else 0
        pw = parent.winfo_width() if parent else 800
        ph = parent.winfo_height() if parent else 600
        w = win.winfo_reqwidth(); h = win.winfo_reqheight()
        x = px + (pw - w)//2; y = py + (ph - h)//2
        win.geometry(f"{w}x{h}+{max(0,x)}+{max(0,y)}")
    except Exception:
        pass


def show_about_dialog(root):
    """Show about dialog"""
    import tkinter as tk
    from tkinter import ttk
    top = tk.Toplevel(root)
    top.title('About')
    top.transient(root); top.grab_set()
    frm = ttk.Frame(top, padding=16)
    frm.pack(fill='both', expand=True)
    msg = ('OM0RX Radio Control 2.0\n'
           '@2026 Oliver Bross OM0RX\n'
           'Based on Python, Wavelog custom API.')
    ttk.Label(frm, text=msg, justify='center').pack(pady=(4,12))
    ttk.Button(frm, text='OK', command=top.destroy).pack()
    _center_window(top, root)


def show_flex_info(root):
    """Show FlexRadio info dialog"""
    import tkinter as tk
    from tkinter import ttk
    top = tk.Toplevel(root)
    top.title('FlexRadio Info')
    top.transient(root); top.grab_set()
    frm = ttk.Frame(top, padding=16)
    frm.pack(fill='both', expand=True)
    # Read host/port from config
    try:
        from radio_control import config as _cfg
        host = getattr(_cfg, 'FLEX_TCP_HOST', '127.0.0.1')
        port = int(getattr(_cfg, 'FLEX_TCP_PORT', 4992))
    except Exception:
        host, port = '127.0.0.1', 4992
    ttk.Label(frm, text=f'Target: {host}:{port}', font=('TkDefaultFont', 10, 'bold')).pack(anchor='w')
    info, raw = flex_probe_info(host, port)
    if info:
        tree = ttk.Treeview(frm, columns=('v',), show='headings', height=min(10, len(info)))
        tree.heading('v', text='Value')
        tree.column('v', width=260)
        for k in sorted(info.keys()):
            tree.insert('', 'end', values=(f"{k}: {info[k]}",))
        tree.pack(fill='x', pady=(8,6))
    else:
        ttk.Label(frm, text='(No parsed fields from radio — connection may be blocked or radio busy)').pack(anchor='w', pady=(6,6))
    def open_docs():
        try:
            webbrowser.open('https://github.com/flexradio/smartsdr-api-docs/wiki/TCPIP-info')
        except Exception:
            pass
    btns = ttk.Frame(frm); btns.pack(fill='x', pady=(8,0))
    ttk.Button(btns, text='Open API Docs', command=open_docs).pack(side='left')
    ttk.Button(btns, text='Close', command=top.destroy).pack(side='right')
    _center_window(top, root)


class MiniColorPicker:
    """Simple RGB color picker dialog"""
    def __init__(self, parent, initial='#FFFFFF', title='Pick colour'):
        import tkinter as tk
        from tkinter import ttk
        self.parent = parent
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.transient(parent)
        try:
            self.top.lift(); self.top.attributes('-topmost', True); self.top.after(100, lambda: self.top.attributes('-topmost', False))
        except Exception:
            pass
        self.top.grab_set()
        self.top.geometry('+400+300')
        # Normalize initial hex
        s = str(initial).strip()
        if s.startswith('#'): s = s[1:]
        if len(s)==8: s = s[2:]
        if len(s)!=6: s = 'FFFFFF'
        r = int(s[0:2],16); g=int(s[2:4],16); b=int(s[4:6],16)
        frm = ttk.Frame(self.top, padding=8); frm.pack(fill='both', expand=True)
        self.var_r = tk.IntVar(value=r)
        self.var_g = tk.IntVar(value=g)
        self.var_b = tk.IntVar(value=b)
        self.hex_var = tk.StringVar()
        def hex_from_rgb():
            h = '#%02X%02X%02X' % (self.var_r.get(), self.var_g.get(), self.var_b.get())
            self.hex_var.set(h)
            sw.configure(background=h)
        ttk.Label(frm, text='R').grid(row=0, column=0, sticky='e'); tk.Scale(frm, from_=0, to=255, orient='horizontal', variable=self.var_r, command=lambda *_: hex_from_rgb()).grid(row=0, column=1, sticky='ew')
        ttk.Label(frm, text='G').grid(row=1, column=0, sticky='e'); tk.Scale(frm, from_=0, to=255, orient='horizontal', variable=self.var_g, command=lambda *_: hex_from_rgb()).grid(row=1, column=1, sticky='ew')
        ttk.Label(frm, text='B').grid(row=2, column=0, sticky='e'); tk.Scale(frm, from_=0, to=255, orient='horizontal', variable=self.var_b, command=lambda *_: hex_from_rgb()).grid(row=2, column=1, sticky='ew')
        sw = tk.Label(frm, text='  preview  ', relief='sunken'); sw.grid(row=0, column=2, rowspan=3, padx=8)
        ttk.Entry(frm, textvariable=self.hex_var, width=10).grid(row=3, column=1, sticky='w', pady=(6,0))
        btns = ttk.Frame(frm); btns.grid(row=4, column=0, columnspan=3, pady=(8,0))
        ttk.Button(btns, text='OK', command=self._ok).pack(side='left', padx=6)
        ttk.Button(btns, text='Cancel', command=self._cancel).pack(side='left', padx=6)
        frm.columnconfigure(1, weight=1)
        hex_from_rgb()
        self.top.bind('<Escape>', lambda e: self._cancel())
        self.top.wait_window()
    def _ok(self):
        self.result = self.hex_var.get()
        self.top.destroy()
    def _cancel(self):
        self.result = None
        self.top.destroy()


class ConfigDialog:
    """Configuration dialog with tabbed interface"""
    def __init__(self, parent):
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
        self.top = tk.Toplevel(parent)
        self.top.title("Configuration")
        self.top.transient(parent)
        try:
            self.top.lift(); self.top.attributes('-topmost', True); self.top.after(100, lambda: self.top.attributes('-topmost', False))
        except Exception:
            pass
        self.top.grab_set()
        self.top.resizable(True, True)

        nb = ttk.Notebook(self.top); nb.pack(fill='both', expand=True, padx=8, pady=8)

        vals = _read_config_values()

        def row(parent, r, label, var, width=32, secret=False, browse=None):
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky='e', padx=6, pady=4)
            ent = ttk.Entry(parent, textvariable=var, width=width, show='*' if secret else '')
            ent.grid(row=r, column=1, sticky='we', padx=6, pady=4)
            if browse:
                def _pick():
                    p = browse()
                    if p: var.set(p)
                ttk.Button(parent, text="Browse…", command=_pick).grid(row=r, column=2, padx=6)
            return ent

        # DB tab
        db_fr = ttk.Frame(nb); nb.add(db_fr, text="Database")
        self.db_host = tk.StringVar(value=vals["DB_HOST"])
        self.db_port = tk.IntVar(value=int(vals["DB_PORT"]))
        self.db_name = tk.StringVar(value=vals["DB_NAME"])
        self.db_user = tk.StringVar(value=vals["DB_USER"])
        self.db_pass = tk.StringVar(value=vals["DB_PASS"])
        row(db_fr,0,"Host", self.db_host); row(db_fr,1,"Port", self.db_port)
        row(db_fr,2,"DB Name", self.db_name); row(db_fr,3,"User", self.db_user)
        row(db_fr,4,"Password", self.db_pass, secret=True)
        db_fr.columnconfigure(1, weight=1)

        # Station/Cluster tab
        st_fr = ttk.Frame(nb); nb.add(st_fr, text="Station & Cluster")
        self.my_station = tk.StringVar(value=vals["MY_STATION"])
        self.cl_host = tk.StringVar(value=vals["CLUSTER_HOST"])
        self.cl_port = tk.IntVar(value=int(vals["CLUSTER_PORT"]))
        self.cl_user = tk.StringVar(value=vals["CLUSTER_USER"])
        self.cl_pass = tk.StringVar(value=vals["CLUSTER_PASS"])
        row(st_fr,0,"My Station", self.my_station)
        row(st_fr,1,"Cluster Host", self.cl_host)
        row(st_fr,2,"Cluster Port", self.cl_port)
        row(st_fr,3,"Cluster Login", self.cl_user)
        row(st_fr,4,"Cluster Password", self.cl_pass, secret=True)
        st_fr.columnconfigure(1, weight=1)

        # Flex/UDP tab
        fu_fr = ttk.Frame(nb); nb.add(fu_fr, text="Flex & UDP")
        self.flex_host = tk.StringVar(value=vals["FLEX_TCP_HOST"])
        self.flex_port = tk.IntVar(value=int(vals["FLEX_TCP_PORT"]))
        self.flex_on   = tk.BooleanVar(value=bool(vals["FLEX_ENABLED_DEFAULT"]))
        self.udp_host  = tk.StringVar(value=vals["SDR_UDP_HOST"])
        self.udp_port  = tk.IntVar(value=int(vals["SDR_UDP_PORT"]))
        self.udp_on    = tk.BooleanVar(value=bool(vals["UDP_ENABLED_DEFAULT"]))
        row(fu_fr,0,"Flex TCP Host", self.flex_host)
        row(fu_fr,1,"Flex TCP Port", self.flex_port)
        ttk.Checkbutton(fu_fr, text="Flex enabled by default", variable=self.flex_on).grid(row=2, column=1, sticky='w', padx=6)
        row(fu_fr,3,"UDP Host", self.udp_host)
        row(fu_fr,4,"UDP Port", self.udp_port)
        ttk.Checkbutton(fu_fr, text="UDP enabled by default", variable=self.udp_on).grid(row=5, column=1, sticky='w', padx=6)
        fu_fr.columnconfigure(1, weight=1)

        # CTY/Paths tab
        cp_fr = ttk.Frame(nb); nb.add(cp_fr, text="CTY / Paths")
        self.cty_csv = tk.StringVar(value=vals["CTY_CSV_PATH"] or "")
        self.cty_dat = tk.StringVar(value=vals["CTY_DAT_PATH"] or "")
        def pick_file_csv():
            from tkinter import filedialog
            return filedialog.askopenfilename(title="Choose cty.csv", filetypes=[("CSV","*.csv"),("All","*.*")])
        def pick_file_dat():
            from tkinter import filedialog
            return filedialog.askopenfilename(title="Choose cty.dat", filetypes=[("DAT","*.dat"),("All","*.*")])
        row(cp_fr,0,"CTY CSV Path", self.cty_csv, browse=pick_file_csv)
        row(cp_fr,1,"CTY DAT Path", self.cty_dat, browse=pick_file_dat)
        cp_fr.columnconfigure(1, weight=1)

        # Logging tab
        lg_fr = ttk.Frame(nb); nb.add(lg_fr, text="Logging")
        self.log_level = tk.StringVar(value=str(vals["LOG_LEVEL"]))
        row(lg_fr,0,"Log Level (DEBUG/INFO/WARN)", self.log_level)
        lg_fr.columnconfigure(1, weight=1)

        
        # Specials tab
        sp_fr = ttk.Frame(nb); nb.add(sp_fr, text="Specials")
        self._sp_list = tk.Listbox(sp_fr, height=8, selectmode='browse')
        self._sp_list.grid(row=0, column=0, columnspan=3, sticky='nsew', padx=6, pady=6)
        for item in (vals.get("SPECIAL_PRESET") or []):
            self._sp_list.insert('end', item)
        def _sp_add():
            from tkinter import simpledialog
            s = simpledialog.askstring('Add Special', 'Special name:')
            if s:
                s=s.strip()
                if s and s not in self._sp_list.get(0,'end'):
                    self._sp_list.insert('end', s)
        def _sp_edit():
            sel = self._sp_list.curselection()
            if not sel: return
            idx = sel[0]
            from tkinter import simpledialog
            cur = self._sp_list.get(idx)
            s = simpledialog.askstring('Edit Special', 'Special name:', initialvalue=cur)
            if s:
                s=s.strip()
                self._sp_list.delete(idx); self._sp_list.insert(idx, s)
        def _sp_remove():
            sel = self._sp_list.curselection()
            if not sel: return
            self._sp_list.delete(sel[0])
        ttk.Button(sp_fr, text='Add', command=_sp_add).grid(row=1, column=0, padx=6, pady=(0,6), sticky='w')
        ttk.Button(sp_fr, text='Edit', command=_sp_edit).grid(row=1, column=1, padx=6, pady=(0,6))
        ttk.Button(sp_fr, text='Remove', command=_sp_remove).grid(row=1, column=2, padx=6, pady=(0,6))
        sp_fr.columnconfigure(0, weight=1); sp_fr.rowconfigure(0, weight=1)

        # Colours tab
        co_fr = ttk.Frame(nb); nb.add(co_fr, text="Colours")
        self._color_vars = {}
        color_keys = ['ATNO','New band','New mode','New band+mode','Need LoTW','Worked','Default']
        from radio_control import config as _cfg2
        cur_map = getattr(_cfg2, 'COLORS', {})
        from tkinter import colorchooser
        def _pick_color(key):
            v = self._color_vars[key]
            init = v.get() or '#FFFFFF'
            # Bring config window to the front so the dialog isn't hidden
            try:
                self.top.lift(); self.top.attributes('-topmost', True); self.top.after(50, lambda: self.top.attributes('-topmost', False)); self.top.focus_force()
            except Exception:
                pass
            # Try native dialog first
            rgb, hexv = (None, None)
            try:
                (rgb, hexv) = colorchooser.askcolor(color=init, title=f"Pick colour for {key}", parent=self.top)
            except Exception:
                hexv = None
            # Fallback: always open the mini picker if native returned None
            if not hexv:
                from tkinter import simpledialog
                s_hex = simpledialog.askstring('Pick colour', 'Hex (#RRGGBB or #AARRGGBB):', initialvalue=init, parent=self.top)
                hexv = s_hex
            if hexv:
                v.set(hexv)

        r=0
        for key in color_keys:
            ttk.Label(co_fr, text=key).grid(row=r, column=0, sticky='e', padx=6, pady=4)
            sv = tk.StringVar(value=str(cur_map.get(key, '')))
            self._color_vars[key] = sv
            ttk.Entry(co_fr, textvariable=sv, width=18).grid(row=r, column=1, sticky='w', padx=6, pady=4)
            ttk.Button(co_fr, text='Pick…', command=lambda k=key: _pick_color(k)).grid(row=r, column=2, padx=6)
            r+=1
        co_fr.columnconfigure(1, weight=1)
        
        # Buttons
        btn_fr = ttk.Frame(self.top); btn_fr.pack(fill='x', padx=8, pady=(0,8))
        def _save():
            updates = {
                "DB_HOST": self.db_host.get(),
                "DB_PORT": int(self.db_port.get() or 3306),
                "DB_NAME": self.db_name.get(),
                "DB_USER": self.db_user.get(),
                "DB_PASS": self.db_pass.get(),
                "MY_STATION": self.my_station.get(),
                "CLUSTER_HOST": self.cl_host.get(),
                "CLUSTER_PORT": int(self.cl_port.get() or 7300),
                "CLUSTER_USER": self.cl_user.get(),
                "CLUSTER_PASS": self.cl_pass.get(),
                "SDR_UDP_HOST": self.udp_host.get(),
                "SDR_UDP_PORT": int(self.udp_port.get() or 12061),
                "UDP_ENABLED_DEFAULT": bool(self.udp_on.get()),
                "FLEX_TCP_HOST": self.flex_host.get(),
                "FLEX_TCP_PORT": int(self.flex_port.get() or 4992),
                "FLEX_ENABLED_DEFAULT": bool(self.flex_on.get()),
                "CTY_CSV_PATH": self.cty_csv.get(),
                "CTY_DAT_PATH": self.cty_dat.get(),
                "LOG_LEVEL": self.log_level.get().upper() or "INFO",
                "SPECIAL_PRESET": [s for s in self._sp_list.get(0,'end')],
                "COLORS": {k: v.get() for k,v in self._color_vars.items()}
            }
            try:
                p = _update_config_file(updates)
                from tkinter import messagebox
                messagebox.showinfo("Saved", f"Configuration saved to:\n{p}\n\nRestart the bridge to apply runtime changes.")
                self.top.destroy()
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Save failed", str(e))

        ttk.Button(btn_fr, text="Save", command=_save).pack(side='right', padx=6)
        ttk.Button(btn_fr, text="Cancel", command=self.top.destroy).pack(side='right')


def _attach_menu_to_root(root):
    """Attach menu bar to root window"""
    import tkinter as tk
    from tkinter import messagebox
    menubar = tk.Menu(root)
    filem = tk.Menu(menubar, tearoff=0)
    def _open_config():
        try:
            ConfigDialog(root)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open Config: {e}")
    filem.add_command(label="Config…", command=_open_config)
    filem.add_separator()
    filem.add_command(label="Exit", command=root.destroy)
    menubar.add_cascade(label="File", menu=filem)
    radio_menu = tk.Menu(menubar, tearoff=0)
    radio_menu.add_command(label='FlexRadio', command=lambda r=root: show_flex_info(r))
    menubar.add_cascade(label='Radio', menu=radio_menu)
    about_menu = tk.Menu(menubar, tearoff=0)
    about_menu.add_command(label='About', command=lambda r=root: show_about_dialog(r))
    menubar.add_cascade(label='About', menu=about_menu)

    root.config(menu=menubar)
