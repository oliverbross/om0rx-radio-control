#!/usr/bin/env python3
"""
Test different Wavelog API endpoints to find QSO data
"""

import asyncio
import aiohttp
import json
from config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID
import urllib.parse

async def test_endpoints():
    """Test various endpoint variations"""
    
    callsign = "MM3RA"
    base_url = WAVELOG_API_URL.replace('/index.php', '')
    
    # Different endpoint variations to try
    endpoints = [
        # Try with query parameter
        (f"{base_url}/api/qsos?callsign={callsign}&api_key={WAVELOG_API_KEY}", "GET", None),
        (f"{base_url}/api/qsos?call={callsign}&api_key={WAVELOG_API_KEY}", "GET", None),
        (f"{base_url}/api/user/worked?callsign={callsign}&api_key={WAVELOG_API_KEY}", "GET", None),
        (f"{base_url}/api/user/worked?call={callsign}&api_key={WAVELOG_API_KEY}", "GET", None),
        
        # Try POST endpoints
        (f"{base_url}/api/qsos", "POST", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign
        }),
        (f"{base_url}/api/worked", "POST", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign
        }),
        (f"{base_url}/api/qso/query", "POST", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign
        }),
        (f"{WAVELOG_API_URL}/api/qsos", "POST", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign,
            "station_id": WAVELOG_STATION_ID
        }),
        
        # Try index.php variations
        (f"{WAVELOG_API_URL}/api/user/worked?callsign={callsign}&api_key={WAVELOG_API_KEY}", "GET", None),
        (f"{WAVELOG_API_URL.replace('/index.php', '')}/user/qsos?callsign={callsign}&api_key={WAVELOG_API_KEY}", "GET", None),
    ]
    
    async with aiohttp.ClientSession() as session:
        for i, (endpoint, method, payload) in enumerate(endpoints):
            print(f"\n{'='*60}")
            print(f"Test {i+1}: {method} {endpoint}")
            if payload:
                print(f"Payload: {json.dumps(payload, indent=2)}")
            print('='*60)
            
            try:
                if method == "GET":
                    async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        print(f"Status: {resp.status}")
                        text = await resp.text()
                        print(f"Response (first 300 chars): {text[:300]}")
                        
                        if resp.status == 200 and text.strip().startswith('{'):
                            try:
                                data = json.loads(text)
                                print(f"✅ Valid JSON")
                                if isinstance(data, dict):
                                    print(f"  Keys: {list(data.keys())[:10]}")
                                    if 'data' in data:
                                        print(f"  data type: {type(data['data'])}")
                                    if 'qsos' in data:
                                        print(f"  qsos type: {type(data['qsos'])}")
                                    if 'rows' in data:
                                        print(f"  rows type: {type(data['rows'])}")
                                elif isinstance(data, list):
                                    print(f"✅ Array response with {len(data)} items")
                            except:
                                pass
                else:  # POST
                    async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        print(f"Status: {resp.status}")
                        text = await resp.text()
                        print(f"Response (first 300 chars): {text[:300]}")
                        
                        if resp.status == 200 and text.strip().startswith('{'):
                            try:
                                data = json.loads(text)
                                print(f"✅ Valid JSON")
                                if isinstance(data, dict):
                                    print(f"  Keys: {list(data.keys())[:10]}")
                                elif isinstance(data, list):
                                    print(f"✅ Array response with {len(data)} items")
                            except:
                                pass
                                
            except asyncio.TimeoutError:
                print(f"⏱️ Timeout")
            except Exception as e:
                print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_endpoints())