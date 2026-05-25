#!/usr/bin/env python3
"""Test config save functionality"""

import re
import os
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
config_path = project_root / "radio_control" / "config.py"

print(f"📝 Reading config from: {config_path}")
with open(config_path, 'r', encoding='utf-8') as f:
    original_txt = f.read()

print(f"✅ Read {len(original_txt)} bytes")

# Show current WINKEYER_ENABLED value
import _bootstrap  # noqa: F401
from radio_control import config
print(f"🔍 Current WINKEYER_ENABLED in memory: {config.WINKEYER_ENABLED}")

# Try to replace it
key = "WINKEYER_ENABLED"
new_value = False
formatted_value = "False"

def _replace_block(text, key, new_value_src):
    print(f"\n🔍 Looking for: ^[ \\t]*{key}\\s*=")
    start_re = re.compile(rf"^[ \t]*{re.escape(key)}\s*=", re.M)
    m = start_re.search(text)
    
    if not m:
        print(f"❌ Key '{key}' NOT FOUND in config file!")
        return None
    
    print(f"✅ Found '{key}' at position {m.start()}-{m.end()}")
    print(f"   Match: {repr(text[m.start():m.start()+50])}")
    
    rep = f"{key} = {new_value_src}"
    end_re = re.compile(r"^([A-Z_][A-Z0-9_]*\s*=)", re.M)
    m_end = end_re.search(text, pos=m.end())
    
    if m_end:
        print(f"✅ Found next key at position {m_end.start()}: {m_end.group()}")
        new_text = text[:m.start()] + rep + "\n" + text[m_end.start():]
    else:
        print(f"⚠️  No next key found, replacing to end of file")
        new_text = text[:m.start()] + rep + "\n"
    
    return new_text

new_txt = _replace_block(original_txt, key, formatted_value)

if new_txt is None:
    print("❌ Replacement failed!")
    exit(1)

print(f"\n📊 Size comparison: original={len(original_txt)}, new={len(new_txt)}")
print(f"📊 Changed: {original_txt != new_txt}")

# Check what was replaced
print(f"\n🔍 New value in file:")
new_line_match = re.search(rf"^{key}\s*=.*$", new_txt, re.M)
if new_line_match:
    print(f"   {new_line_match.group()}")

# Write to test file
test_path = project_root / "config_test.py"
print(f"\n💾 Writing test to: {test_path}")
with open(test_path, 'w', encoding='utf-8') as f:
    f.write(new_txt)

# Verify
with open(test_path, 'r', encoding='utf-8') as f:
    verify_txt = f.read()

if verify_txt == new_txt:
    print(f"✅ File written and verified successfully!")
    # Check the specific line
    for line in verify_txt.split('\n'):
        if 'WINKEYER_ENABLED' in line:
            print(f"✅ Line in file: {line}")
else:
    print(f"❌ File verification failed!")

print("\n✅ Test completed!")
