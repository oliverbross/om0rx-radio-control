#!/usr/bin/env python3
"""
Test Wavelog API endpoints that can filter by callsign directly
"""

import asyncio
import aiohttp
import json
from radio_control.config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID

async def test_endpoints():
    """Test various endpoint variations for filtering by callsign"""
    
    callsign = "SV2HJQ"
    base_url = WAVELOG_API_URL.replace('/index.php', '')
    
    # Try different endpoint variations to get QSOs for a specific callsign
    endpoints = [
        # Try with /api/qsos (might support callsign filter)
        (f"{WAVELOG_API_URL}/api/qsos", "POST", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign,
            "station_id": WAVELOG_STATION_ID,
            "limit": 5
        }),
        
        # Try /api/qso/query
        (f"{WAVELOG_API_URL}/api/qso/query", "POST", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign,
            "limit": 5
        }),
        
        # Try /api/user/worked with band/mode
        (f"{WAVELOG_API_URL}/api/user/worked", "POST", {
            "key": WAVELOG_API_KEY,
            "callsign": callsign
        }),
        
        # Try with index.php variations
        (f"{base_url}/api/qsos", "POST", {
            "key": WAVELOG_API_KEY,
            "call": callsign,
            "limit": 5
        }),
        
        # Try GET with URL parameters
        (f"{WAVELOG_API_URL}/api/qsos?key={WAVELOG_API_KEY}&callsign={callsign}&limit=5", "GET", None),
        
        # Try /api/get_qsos_adif with callsign filter
        (f"{WAVELOG_API_URL}/api/get_qsos_adif", "POST", {
            "key": WAVELOG_API_KEY,
            "station_id": WAVELOG_STATION_ID,
            "callsign": callsign
        }),
    ]
    
    async with aiohttp.ClientSession() as session:
        for endpoint, method, payload in endpoints:
            print(f"\n{'='*70}")
            print(f"Testing: {method} {endpoint.split('/api/')[1] if '/api/' in endpoint else endpoint}")
            if payload:
                # Don't print full key
                display_payload = {k: (v[:10] + '...' if isinstance(v, str) and len(v) > 10 else v) for k, v in payload.items()}
                print(f"Payload: {json.dumps(display_payload)}")
            print('='*70)
            
            try:
                if method == "GET":
                    async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        print(f"Status: {resp.status}")
                        text = await resp.text()
                        
                        if resp.status == 200:
                            try:
                                data = json.loads(text)
                                print(f"✅ Valid JSON response")
                                
                                # Check what's in the response
                                if isinstance(data, dict):
                                    print(f"Keys: {list(data.keys())}")
                                    
                                    # Check for QSO data
                                    if 'data' in data:
                                        if isinstance(data['data'], list):
                                            print(f"  ✅ 'data' is array with {len(data['data'])} items")
                                            if len(data['data']) > 0:
                                                print(f"  First item: {json.dumps(data['data'][0], indent=2)[:300]}")
                                        else:
                                            print(f"  'data': {type(data['data'])}")
                                    
                                    if 'qsos' in data and isinstance(data['qsos'], list):
                                        print(f"  ✅ 'qsos' array with {len(data['qsos'])} items")
                                    
                                    if 'rows' in data and isinstance(data['rows'], list):
                                        print(f"  ✅ 'rows' array with {len(data['rows'])} items")
                                    
                                elif isinstance(data, list):
                                    print(f"✅ Array response with {len(data)} items")
                                    if len(data) > 0:
                                        print(f"First item: {json.dumps(data[0], indent=2)[:300]}")
                            except json.JSONDecodeError:
                                print(f"Response is not JSON: {text[:200]}")
                        else:
                            print(f"❌ Status {resp.status}: {text[:200]}")
                            
                else:  # POST
                    async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        print(f"Status: {resp.status}")
                        text = await resp.text()
                        
                        if resp.status == 200:
                            try:
                                data = json.loads(text)
                                print(f"✅ Valid JSON response")
                                
                                # Check what's in the response
                                if isinstance(data, dict):
                                    print(f"Keys: {list(data.keys())}")
                                    
                                    # Check for QSO data
                                    if 'data' in data:
                                        if isinstance(data['data'], list):
                                            print(f"  ✅ 'data' is array with {len(data['data'])} items")
                                            if len(data['data']) > 0:
                                                first_item = data['data'][0]
                                                print(f"  First item fields: {list(first_item.keys())[:10]}")
                                                print(f"  Full first item: {json.dumps(first_item, indent=2)[:500]}")
                                        else:
                                            print(f"  'data': {type(data['data'])}")
                                    
                                    if 'qsos' in data and isinstance(data['qsos'], list):
                                        print(f"  ✅ 'qsos' array with {len(data['qsos'])} items")
                                    
                                    if 'rows' in data and isinstance(data['rows'], list):
                                        print(f"  ✅ 'rows' array with {len(data['rows'])} items")
                                    
                                    if 'message' in data:
                                        print(f"Message: {data['message']}")
                                    
                                    if 'adif' in data:
                                        print(f"  ADIF data: {len(data['adif'])} bytes")
                                    
                                elif isinstance(data, list):
                                    print(f"✅ Array response with {len(data)} items")
                                    if len(data) > 0:
                                        print(f"First item: {json.dumps(data[0], indent=2)[:300]}")
                            except json.JSONDecodeError:
                                print(f"Response is not JSON: {text[:200]}")
                        else:
                            print(f"❌ Status {resp.status}: {text[:200]}")
                            
            except asyncio.TimeoutError:
                print(f"⏱️ Timeout")
            except Exception as e:
                print(f"❌ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_endpoints())