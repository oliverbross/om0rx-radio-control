#!/usr/bin/env python3
"""
Test script to debug ADIF parsing
"""

import asyncio
import aiohttp
import json
import re
from config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID

async def test():
    endpoint = f"{WAVELOG_API_URL}/api/get_contacts_adif"
    
    payload = {
        'key': WAVELOG_API_KEY,
        'station_id': WAVELOG_STATION_ID,
        'fetchfromid': 0
    }
    
    print("Fetching ADIF data...")
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()
            adif_string = data['adif']
    
    print(f"ADIF size: {len(adif_string)} bytes")
    
    # Test parsing
    target_callsign = "OM0AAO"
    
    # Split by <EOR>
    records = adif_string.split('<EOR>')
    print(f"Total records: {len(records)}")
    
    # Test first few records
    print(f"\n--- First record (first 500 chars) ---")
    first_record = records[0].strip()
    print(first_record[:500])
    
    # Parse first record
    print(f"\n--- Parsing first record ---")
    qso_data = {}
    pattern = r'<([^:>]+):(\d+)>([^<]*)'
    matches = re.findall(pattern, first_record)
    
    print(f"Found {len(matches)} fields")
    
    for field_name, field_len, field_value in matches[:10]:
        # Show raw and stripped
        print(f"  {field_name}: raw='{repr(field_value)}' stripped='{field_value.strip()}'")
        qso_data[field_name.lower()] = field_value.strip()
    
    # Count matches by target callsign
    print(f"\n--- Counting OM0AAO matches ---")
    match_count = 0
    for idx, record in enumerate(records):
        record = record.strip()
        if not record:
            continue
        
        qso_data = {}
        matches = re.findall(pattern, record)
        
        for field_name, field_len, field_value in matches:
            qso_data[field_name.lower()] = field_value.strip()
        
        call = qso_data.get('call', '').upper()
        
        if call == target_callsign:
            match_count += 1
            if match_count <= 3:
                print(f"  Match #{match_count} at record {idx}: {call}")
                # Show some fields
                print(f"    date: {qso_data.get('qso_date', 'N/A')}")
                print(f"    time: {qso_data.get('time_on', 'N/A')}")
                print(f"    freq: {qso_data.get('freq', 'N/A')}")
                print(f"    mode: {qso_data.get('mode', 'N/A')}")
    
    print(f"\nTotal OM0AAO records: {match_count}")

if __name__ == "__main__":
    asyncio.run(test())