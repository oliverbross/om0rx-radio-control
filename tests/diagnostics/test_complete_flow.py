#!/usr/bin/env python3
"""Test complete config save flow with cache clearing"""

import json
import time
from pathlib import Path

print("🚀 Starting complete flow test...\n")

# First, check original value
print("1️⃣  Checking original config value in file...")
config_file = Path(r"c:\Projects\om0rx-radio-control\config.py")
with open(config_file, 'r') as f:
    for line in f:
        if line.strip().startswith('WINKEYER_ENABLED'):
            print(f"   Original: {line.strip()}")
            break

# For now, let's just verify the config file can be modified and reloaded correctly
print("\n2️⃣  Testing Python import + reload + cache clear...")

import sys
import importlib
from pathlib import Path as PathlibPath

# Clean cache first
pycache = PathlibPath(r"c:\Projects\om0rx-radio-control\__pycache__")
if pycache.exists():
    for pyc in pycache.glob('config*.pyc'):
        try:
            pyc.unlink()
            print(f"   Cleaned: {pyc.name}")
        except:
            pass

# Remove from sys.modules to force fresh import
if 'config' in sys.modules:
    del sys.modules['config']

# Import fresh
import config
print(f"   Fresh import: WINKEYER_ENABLED = {config.WINKEYER_ENABLED}")

# Now simulate the save
print("\n4️⃣  Simulating config save (change to False)...")
import re

with open(config_file, 'r', encoding='utf-8') as f:
    txt = f.read()

def replace_config(text, key, value):
    start_re = re.compile(rf"^[ \t]*{re.escape(key)}\s*=", re.M)
    m = start_re.search(text)
    if not m:
        return text
    rep = f"{key} = {value}"
    end_re = re.compile(r"^([A-Z_][A-Z0-9_]*\s*=)", re.M)
    m_end = end_re.search(text, pos=m.end())
    if m_end:
        return text[:m.start()] + rep + "\n" + text[m_end.start():]
    else:
        return text[:m.start()] + rep + "\n"

txt = replace_config(txt, "WINKEYER_ENABLED", "False")

# Write the file
with open(config_file, 'w', encoding='utf-8') as f:
    f.write(txt)
print("   File written with WINKEYER_ENABLED = False")

# Verify file
with open(config_file, 'r') as f:
    for line in f:
        if line.strip().startswith('WINKEYER_ENABLED'):
            print(f"   File contains: {line.strip()}")
            break

# Now clear cache and reload
print("\n5️⃣  Clearing cache and reloading module...")
if 'config' in sys.modules:
    del sys.modules['config']

pycache = PathlibPath(r"c:\Projects\om0rx-radio-control\__pycache__")
if pycache.exists():
    for pyc in pycache.glob('config*.pyc'):
        try:
            pyc.unlink()
            print(f"   Cleaned: {pyc.name}")
        except:
            pass

# Import again - should get fresh values
if 'config' in sys.modules:
    del sys.modules['config']
    
import config as config_fresh
print(f"   After reload: WINKEYER_ENABLED = {config_fresh.WINKEYER_ENABLED}")

if config_fresh.WINKEYER_ENABLED == False:
    print("\n✅ SUCCESS! Config change persists after reload!")
else:
    print("\n❌ FAILED! Config still shows old value after reload!")

# Restore original
print("\n6️⃣  Restoring original config...")
with open(config_file, 'r', encoding='utf-8') as f:
    txt = f.read()
txt = replace_config(txt, "WINKEYER_ENABLED", "True")
with open(config_file, 'w', encoding='utf-8') as f:
    f.write(txt)
print("   Restored to WINKEYER_ENABLED = True")

print("\n✅ Test complete!")