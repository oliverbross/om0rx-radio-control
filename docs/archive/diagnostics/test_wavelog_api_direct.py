#!/usr/bin/env python3
"""Test Wavelog API pagination"""

import urllib.request
import urllib.error
import json

url = 'https://om0rx.wavelog.online/index.php/api/get_contacts_adif'

# Test batch 1
print("=" * 80)
print("BATCH 1: fetchfromid=0")
print("=" * 80)

params = {
    'key': '<wavelog_api_key>',
    'station_id': '1',
    'fetchfromid': 0
}

try:
    req = urllib.request.Request(url, data=json.dumps(params).encode('utf-8'), method='POST')
    req.add_header('Content-Type', 'application/json')
    
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        adif = data.get('adif', '')
        print(f'Response length: {len(adif)} chars')
        
        # Count <eor> tags
        eor_count = adif.count('<eor>')
        print(f'EOR count (records): {eor_count}')
        
        # Show first few lines
        lines = adif.split('\n')[:20]
        print("\nFirst 20 lines:")
        for i, line in enumerate(lines, 1):
            print(f"  {i}: {line[:80]}")
            
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

# Test batch 2
print("\n" + "=" * 80)
print("BATCH 2: fetchfromid=10")
print("=" * 80)

params2 = {
    'key': '<wavelog_api_key>',
    'station_id': '1',
    'fetchfromid': 10
}

try:
    req2 = urllib.request.Request(url, data=json.dumps(params2).encode('utf-8'), method='POST')
    req2.add_header('Content-Type', 'application/json')
    
    with urllib.request.urlopen(req2, timeout=10) as resp2:
        data2 = json.loads(resp2.read().decode('utf-8'))
        adif2 = data2.get('adif', '')
        print(f'Response length: {len(adif2)} chars')
        eor_count2 = adif2.count('<eor>')
        print(f'EOR count (records): {eor_count2}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()