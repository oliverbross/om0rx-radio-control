# ui_components.py - Reusable UI components

class MultiCheckDropdown:
    """
    A reusable multi-select dropdown built with Menubutton + Menu + Checkbuttons.
    - Supports an "All" toggle.
    - on_change callback fires whenever selection changes.
    - get_selected() -> set of selected values or None if "All" is active (no filtering).
    """
    def __init__(self, parent, label, options=None, on_change=None):
        import tkinter as tk
        from tkinter import ttk
        self.parent = parent
        self.on_change = on_change
        self.frame = ttk.Frame(parent)
        ttk.Label(self.frame, text=label).pack(side='left', padx=(0,4))

        self.btn_text = tk.StringVar(value="All")
        self.btn = ttk.Menubutton(self.frame, textvariable=self.btn_text, width=18)
        self.menu = tk.Menu(self.btn, tearoff=0)
        self.btn['menu'] = self.menu

        self._vars = {}      # option -> BooleanVar
        self._all_var = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(label="All", variable=self._all_var, command=self._sync_all)
        self._options = []
        self.btn.pack(side='left')
        self.set_options(options or [])

    def _fire(self):
        if callable(self.on_change):
            self.on_change()

    def _sync_all(self):
        if self._all_var.get():
            for v in self._vars.values():
                v.set(False)
        self._refresh_label()
        self._fire()

    def _on_item_toggle(self):
        if any(v.get() for v in self._vars.values()):
            self._all_var.set(False)
        else:
            self._all_var.set(True)
        self._refresh_label()
        self._fire()

    def _refresh_label(self):
        sel = [opt for opt, var in self._vars.items() if var.get()]
        if self._all_var.get() or len(sel) == 0:
            self.btn_text.set("All")
        elif len(sel) == 1:
            self.btn_text.set(sel[0])
        else:
            self.btn_text.set(f"{len(sel)} selected")

    def set_options(self, options):
        import tkinter as tk
        options = [str(o) for o in sorted(set(options), key=lambda x: (len(x), x))]
        prev_selected = set([k for k,v in self._vars.items() if v.get()])
        was_all = self._all_var.get()

        self.menu.delete(0, 'end')
        self._all_var = tk.BooleanVar(value=was_all or (len(prev_selected)==0))
        self.menu.add_checkbutton(label="All", variable=self._all_var, command=self._sync_all)
        self._vars = {}
        for opt in options:
            var = tk.BooleanVar(value=(opt in prev_selected))
            self._vars[opt] = var
            self.menu.add_checkbutton(label=opt, variable=var, command=self._on_item_toggle)

        self._options = options
        if not any(v.get() for v in self._vars.values()):
            self._all_var.set(True)
        self._refresh_label()

    def get_selected(self):
        if self._all_var.get():
            return None
        sel = {opt for opt, var in self._vars.items() if var.get()}
        if sel and len(sel) == len(self._options):
            return None
        return sel