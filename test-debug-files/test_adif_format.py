#!/usr/bin/env python3
"""Test ADIF format from Wavelog API"""

import urllib.request
import json
import re

url = 'https://om0rx.wavelog.online/index.php/api/get_contacts_adif'
params = {'key': '<wavelog_api_key>', 'station_id': '1', 'fetchfromid': 0}

req = urllib.request.Request(url, data=json.dumps(params).encode('utf-8'), method='POST')
req.add_header('Content-Type', 'application/json')

with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    adif = data.get('adif', '')
    
    print(f'Total length: {len(adif)} chars')
    print(f'<eor> count (lowercase): {adif.count("<eor>")}')
    print(f'<EOR> count (uppercase): {adif.count("<EOR>")}')
    print(f'<Eor> count (mixed): {adif.count("<Eor>")}')
    print(f'<eoh> count: {adif.count("<eoh>")}')
    print(f'<EOH> count: {adif.count("<EOH>")}')
    
    # Look for any line that ends with eor or EOR
    eor_matches = len(re.findall(r'</?eor>', adif, re.IGNORECASE))
    print(f'Regex matches for <eor>: {eor_matches}')
    
    # Show last 500 chars to see how records end
    print('\nLast 500 characters of ADIF:')
    print(repr(adif[-500:]))
    
    # Try to count by looking for patterns
    print('\nSearching for any end marker patterns:')
    print(f'  Lines containing "eor": {sum(1 for line in adif.split(chr(10)) if "eor" in line.lower())}')
    
    # Split by current regex and count
    records = re.split(r'<(?:eor|eoh)>\s*', adif, flags=re.IGNORECASE)
    print(f'\nRecords after split by regex: {len(records)}')
    print(f'First record preview (first 500 chars):\n{records[0][:500]}')
    if len(records) > 1:
        print(f'\nSecond record preview:\n{records[1][:500]}')