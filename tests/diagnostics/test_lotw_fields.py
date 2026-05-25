#!/usr/bin/env python3
"""
Debug script to inspect LOTW fields in Wavelog ADIF data
"""

import asyncio
import aiohttp
import re
import json
from config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID

async def test():
    endpoint = f"{WAVELOG_API_URL}/api/get_contacts_adif"
    
    payload = {
        'key': WAVELOG_API_KEY,
        'station_id': WAVELOG_STATION_ID,
        'fetchfromid': 0
    }
    
    print("Fetching ADIF data from Wavelog...")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                result = await resp.json()
                adif_data = result['adif']
                
                print(f"ADIF size: {len(adif_data)} bytes")
                
                # Split by EOR to get individual records
                records = adif_data.split('<EOR>')
                print(f"Total records: {len(records)}")
                
                # Scan all records for LOTW-related fields
                lotw_fields = set()
                qsl_fields = set()
                records_with_lotw = 0
                records_with_qsl = 0
                
                for idx, record in enumerate(records[:100]):  # Check first 100 records
                    record_lower = record.lower()
                    
                    # Find all field names in this record
                    pattern = r'<([^:>]+):(\d+)>([^<]*)'
                    matches = re.findall(pattern, record, re.IGNORECASE)
                    
                    for field_name, field_len, field_value in matches:
                        field_lower = field_name.lower()
                        
                        if 'lotw' in field_lower:
                            lotw_fields.add(field_lower)
                            if field_value and field_value.strip():
                                records_with_lotw += 1
                        
                        if 'qsl' in field_lower:
                            qsl_fields.add(field_lower)
                            if field_value and field_value.strip():
                                records_with_qsl += 1
                
                print(f"\n📊 LOTW-related fields found: {lotw_fields}")
                print(f"   Records with LOTW data: {records_with_lotw}/100")
                print(f"\n📊 QSL-related fields found: {qsl_fields}")
                print(f"   Records with QSL data: {records_with_qsl}/100")
                
                # Sample a record and show all its fields
                print(f"\n📋 Sample record fields (first record with data):")
                for idx, record in enumerate(records):
                    if idx > 0 and len(record) > 50:  # Skip empty, get first real record
                        pattern = r'<([^:>]+):(\d+)>([^<]*)'
                        matches = re.findall(pattern, record, re.IGNORECASE)
                        
                        print(f"\nRecord {idx} fields:")
                        for field_name, field_len, field_value in matches:
                            if field_value and field_value.strip():
                                print(f"  <{field_name}> = '{field_value}'")
                        break
                
                # Look specifically for OM0AAO records
                print(f"\n🔍 Looking for OM0AAO records...")
                om0aao_found = 0
                for idx, record in enumerate(records):
                    if 'OM0AAO' in record:
                        om0aao_found += 1
                        pattern = r'<([^:>]+):(\d+)>([^<]*)'
                        matches = re.findall(pattern, record, re.IGNORECASE)
                        
                        print(f"\nOM0AAO record {om0aao_found} (index {idx}):")
                        for field_name, field_len, field_value in matches:
                            if field_value and field_value.strip():
                                field_lower = field_name.lower()
                                if 'lotw' in field_lower or 'qsl' in field_lower or field_lower in ['call', 'qso_date', 'mode', 'band', 'freq']:
                                    print(f"  <{field_name}> = '{field_value}'")
                        
                        if om0aao_found >= 3:
                            break
            else:
                print(f"API error: {resp.status}")

if __name__ == "__main__":
    asyncio.run(test())