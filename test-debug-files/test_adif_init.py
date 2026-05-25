#!/usr/bin/env python
"""Test ADIF sync initialization"""

import sys
sys.path.insert(0, 'c:\\Projects\\om0rx-radio-control')

try:
    from adif_sync import init_adif_sync
    print("[TEST] Importing init_adif_sync...")
    
    sync_mgr = init_adif_sync()
    print(f"[OK] Initialized: {sync_mgr}")
    print(f"[OK] Type: {type(sync_mgr)}")
    print(f"[OK] Has sync method: {hasattr(sync_mgr, 'sync')}")
    
    print("[TEST] Calling sync()...")
    result = sync_mgr.sync()
    print(f"[OK] Sync result: {result}")
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()