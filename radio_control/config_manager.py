# config_manager.py - Configuration file management utilities

import os
import inspect
import importlib
import logging


def _config_path():
    """Resolve path to the active config.py loaded by this script."""
    import config as _cfg
    return os.path.abspath(inspect.getsourcefile(_cfg))


def _read_config_values():
    """Read all configuration values from config.py"""
    import config as _cfg
    vals = {
        "DB_HOST": _cfg.DB_HOST,
        "DB_PORT": _cfg.DB_PORT,
        "DB_NAME": _cfg.DB_NAME,
        "DB_USER": _cfg.DB_USER,
        "DB_PASS": _cfg.DB_PASS,
        "MY_STATION": _cfg.MY_STATION,
        "CLUSTER_HOST": _cfg.CLUSTER_HOST,
        "CLUSTER_PORT": _cfg.CLUSTER_PORT,
        "CLUSTER_USER": _cfg.CLUSTER_USER,
        "CLUSTER_PASS": _cfg.CLUSTER_PASS,
        "SDR_UDP_HOST": _cfg.SDR_UDP_HOST,
        "SDR_UDP_PORT": _cfg.SDR_UDP_PORT,
        "UDP_ENABLED_DEFAULT": _cfg.UDP_ENABLED_DEFAULT,
        "FLEX_TCP_HOST": _cfg.FLEX_TCP_HOST,
        "FLEX_TCP_PORT": _cfg.FLEX_TCP_PORT,
        "FLEX_ENABLED_DEFAULT": _cfg.FLEX_ENABLED_DEFAULT,
        "CTY_CSV_PATH": _cfg.CTY_CSV_PATH,
        "CTY_DAT_PATH": _cfg.CTY_DAT_PATH if 'CTY_DAT_PATH' in dir(_cfg) else "",
        "LOG_LEVEL": _cfg.LOG_LEVEL,
        "SPECIAL_PRESET": getattr(_cfg, "SPECIAL_PRESET", []),
        "COLORS": getattr(_cfg, "COLORS", {}),
    }
    return vals


def _format_py_value(v):
    """Format a Python value as a string for writing to config file"""
    if isinstance(v, str):
        s = v.replace('\\', '\\\\')
        return f"\"{s}\""
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        items = ", ".join(_format_py_value(x) for x in v)
        return f"[{items}]"
    if isinstance(v, dict):
        items = ", ".join(f"{_format_py_value(k)}: {_format_py_value(val)}" for k,val in v.items())
        return "{" + items + "}"
    return repr(v)


def _update_config_file(updates: dict):
    """Update configuration file with new values"""
    path = _config_path()
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()

    import re as _re

    def _replace_block(text, key, new_value_src):
        start_re = _re.compile(rf"^[ \t]*{_re.escape(key)}\s*=", _re.M)
        m = start_re.search(text)
        rep = f"{key} = {new_value_src}"
        if not m:
            if not text.endswith("\n"):
                text += "\n"
            return text + rep + "\n"
        end_re = _re.compile(r"^([A-Z_][A-Z0-9_]*\s*=)", _re.M)
        m_end = end_re.search(text, pos=m.end())
        if m_end:
            return text[:m.start()] + rep + "\n" + text[m_end.start():]
        else:
            return text[:m.start()] + rep + "\n"

    def _format_py_value_inner(v):
        if isinstance(v, str):
            s = v.replace("\\", "\\\\").replace('"', '\\\"')
            return "\""+ s + "\""
        if isinstance(v, bool):
            return "True" if v else "False"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, (list, tuple)):
            items = ", ".join(_format_py_value_inner(x) for x in v)
            return "[" + items + "]"
        if isinstance(v, dict):
            items = ", ".join(_format_py_value_inner(k) + ": " + _format_py_value_inner(val) for k,val in v.items())
            return "{" + items + "}"
        return repr(v)

    for k, v in updates.items():
        txt = _replace_block(txt, k, _format_py_value_inner(v))

    with open(path, 'w', encoding='utf-8') as f:
        f.write(txt)

    import config as _cfg
    import importlib as _imp
    _imp.reload(_cfg)
    return path