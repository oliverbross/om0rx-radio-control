#!/usr/bin/env python3
"""
Script to fix the cluster configuration save/load issue
"""
import re
from pathlib import Path

backend_file = Path(__file__).resolve().parent / "backend" / "main.py"

with open(backend_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Add CLUSTERS to GET endpoint config_data
print("Fix 1: Adding CLUSTERS to GET /api/config endpoint...")
old_pattern1 = r'("MY_STATION": cfg\.MY_STATION,\n\s*"CLUSTER_HOST": cfg\.CLUSTER_HOST,)'
new_text1 = r'"MY_STATION": cfg.MY_STATION,\n            "CLUSTERS": getattr(cfg, \'CLUSTERS\', []),\n            "CLUSTER_HOST": cfg.CLUSTER_HOST,'
content = re.sub(old_pattern1, new_text1, content)
print("✅ Added CLUSTERS to GET endpoint")

# Fix 2: Improve _format_py_value to handle lists
print("Fix 2: Enhancing _format_py_value function...")
old_func = r'(def _format_py_value\(v\):.*?if isinstance\(v, dict\):.*?return "\{" \+ ", "\.join\(items\) \+ "\}")\s*return repr\(v\)'
new_func = r'''\1
            if isinstance(v, (list, tuple)):
                # Handle lists and tuples (e.g., CLUSTERS array)
                items = []
                for item in v:
                    if isinstance(item, dict):
                        # Format dict items in list
                        dict_items = []
                        for k, val in item.items():
                            if isinstance(val, str):
                                escaped_val = val.replace("\\", "\\\\").replace('"', '\\"')
                                dict_items.append(f'"{k}": "{escaped_val}"')
                            elif isinstance(val, bool):
                                dict_items.append(f'"{k}": {"True" if val else "False"}')
                            else:
                                dict_items.append(f'"{k}": {val}')
                        items.append("{" + ", ".join(dict_items) + "}")
                    elif isinstance(item, str):
                        escaped_item = item.replace("\\", "\\\\").replace('"', '\\"')
                        items.append(f'"{escaped_item}"')
                    else:
                        items.append(str(item))
                return "[" + ", ".join(items) + "]"
            return repr(v)'''

# Use DOTALL flag for regex
content = re.sub(old_func, new_func, content, flags=re.DOTALL)
print("✅ Enhanced _format_py_value function")

# Write back
with open(backend_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ All fixes applied successfully!")
