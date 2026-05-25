#!/usr/bin/env python3
"""
Test qso/query endpoint with correct parameters
"""

import asyncio
import aiohttp
import json
from config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID

async def test():
    callsign = "SV2HJQ"
    
    # Test /api/qso/query with different param combinations
    tests = [
        # Try without station_id (since it complained about it)
        (f"{WAVELOG_API_URL}/api/qso/query", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign
        }),
        
        # Try with different field names
        (f"{WAVELOG_API_URL}/api/qso/query", {
            "key": WAVELOG_API_KEY,
            "call": callsign
        }),
        
        # Try with station_profile_id instead
        (f"{WAVELOG_API_URL}/api/qso/query", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign,
            "station_profile_id": WAVELOG_STATION_ID
        }),
        
        # Try get_contacts_adif with callsign search
        (f"{WAVELOG_API_URL}/api/get_contacts_adif", {
            "key": WAVELOG_API_KEY,
            "station_id": WAVELOG_STATION_ID,
            "callsign": callsign,
            "limit": 5
        }),
        
        # Try without fetchfromid
        (f"{WAVELOG_API_URL}/api/get_contacts_adif", {
            "key": WAVELOG_API_KEY,
            "station_id": WAVELOG_STATION_ID,
            "call": callsign
        }),
    ]
    
    async with aiohttp.ClientSession() as session:
        for endpoint, payload in tests:
            endpoint_name = endpoint.split('/api/')[1]
            print(f"\n{'='*70}")
            print(f"Testing: {endpoint_name}")
            print(f"Params: {list(payload.keys())}")
            print('='*70)
            
            try:
                async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"Status: {resp.status}")
                    text = await resp.text()
                    
                    if resp.status in (200, 201):
                        try:
                            data = json.loads(text)
                            print(f"✅ Valid JSON")
                            print(f"Response keys: {list(data.keys())}")
                            
                            # Check various response formats
                            for key in ['data', 'qsos', 'rows', 'adif', 'contacts']:
                                if key in data:
                                    value = data[key]
                                    if isinstance(value, str):
                                        print(f"  {key}: string ({len(value)} bytes)")
                                        if value.startswith('<'):
                                            # It's ADIF data
                                            eor_count = value.count('<EOR>')
                                            print(f"    - ADIF with {eor_count} records")
                                    elif isinstance(value, list):
                                        print(f"  {key}: array ({len(value)} items)")
                                        if len(value) > 0:
                                            print(f"    - First item has {len(value[0]) if isinstance(value[0], dict) else 'N/A'} fields")
                                    elif isinstance(value, dict):
                                        print(f"  {key}: dict with keys {list(value.keys())[:5]}")
                            
                            if 'message' in data:
                                print(f"  Message: {data['message']}")
                            
                            if 'status' in data:
                                print(f"  Status: {data['status']}")
                                
                        except json.JSONDecodeError:
                            print(f"Response is not JSON")
                            print(f"First 200 chars: {text[:200]}")
                    else:
                        print(f"Status {resp.status}")
                        print(f"Response: {text[:200]}")
                        
            except asyncio.TimeoutError:
                print(f"Timeout")
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())