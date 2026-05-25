#!/usr/bin/env python3
"""Test config save + reload flow"""

import re
import os
import importlib
import sys

config_path = r"c:\Projects\om0rx-radio-control\config.py"

# Import config initially
print("📦 Importing config module...")
import config
print(f"✅ config.WINKEYER_ENABLED = {config.WINKEYER_ENABLED}")

# Simulate the save function
print("\n💾 Simulating config save...")
with open(config_path, 'r', encoding='utf-8') as f:
    txt = f.read()

def _format_py_value(v):
    if isinstance(v, bool):
        return "True" if v else "False"
    return repr(v)

def _replace_block(text, key, new_value_src):
    start_re = re.compile(rf"^[ \t]*{re.escape(key)}\s*=", re.M)
    m = start_re.search(text)
    rep = f"{key} = {new_value_src}"
    if not m:
        return None
    end_re = re.compile(r"^([A-Z_][A-Z0-9_]*\s*=)", re.M)
    m_end = end_re.search(text, pos=m.end())
    if m_end:
        return text[:m.start()] + rep + "\n" + text[m_end.start():]
    else:
        return text[:m.start()] + rep + "\n"

# Change it to False
txt = _replace_block(txt, "WINKEYER_ENABLED", _format_py_value(False))
print(f"✅ Modified text")

# Write it back
with open(config_path, 'w', encoding='utf-8') as f:
    f.write(txt)
print(f"✅ Written to {config_path}")

# Check what's in the file now
with open(config_path, 'r') as f:
    for line in f:
        if 'WINKEYER_ENABLED' in line:
            print(f"✅ File now contains: {line.rstrip()}")
            break

# Try to reload the module
print("\n🔄 Reloading config module...")
importlib.reload(config)

print(f"✅ After reload: config.WINKEYER_ENABLED = {config.WINKEYER_ENABLED}")

# Try another approach - what if we check the raw file?
print("\n🔍 Direct file check:")
with open(config_path, 'r') as f:
    for line in f:
        if 'WINKEYER_ENABLED' in line and not line.strip().startswith('#'):
            print(f"   {line.rstrip()}")

# Restore original
print("\n♻️  Restoring original config...")
txt = _replace_block(txt, "WINKEYER_ENABLED", _format_py_value(True))
with open(config_path, 'w', encoding='utf-8') as f:
    f.write(txt)
print("✅ Done")