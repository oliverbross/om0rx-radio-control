#!/usr/bin/env python3
"""
Test script to debug Wavelog recent QSOs API endpoint
"""

import asyncio
import aiohttp
import json
from radio_control.config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID

async def test_recent_qsos_endpoint():
    """Test the /api/qsos/{callsign} endpoint"""
    
    callsign = "MM3RA"  # Try without the /J1 first
    
    # Try different endpoint variations
    endpoints = [
        f"{WAVELOG_API_URL}/api/qsos/{callsign}",
        f"{WAVELOG_API_URL.replace('/index.php', '')}/api/qsos/{callsign}",
        f"{WAVELOG_API_URL.replace('/index.php', '')}/api/qso/{callsign}",
    ]
    
    params = {
        'api_key': WAVELOG_API_KEY,
        'key': WAVELOG_API_KEY,
        'station_id': WAVELOG_STATION_ID,
        'limit': 5
    }
    
    async with aiohttp.ClientSession() as session:
        for endpoint in endpoints:
            print(f"\n🔍 Testing endpoint: {endpoint}")
            try:
                # Try GET
                print(f"  Trying GET with params...")
                async with session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"  Status: {resp.status}")
                    print(f"  Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
                    
                    try:
                        text = await resp.text()
                        print(f"  Response (first 500 chars): {text[:500]}")
                        
                        if resp.status == 200:
                            try:
                                data = json.loads(text)
                                print(f"  ✅ JSON parsed successfully")
                                print(f"  Data keys: {data.keys() if isinstance(data, dict) else 'Array'}")
                                if isinstance(data, dict):
                                    print(f"  Data: {json.dumps(data, indent=2)[:500]}")
                                elif isinstance(data, list):
                                    print(f"  Data length: {len(data)}")
                                    if len(data) > 0:
                                        print(f"  First item: {json.dumps(data[0], indent=2)[:300]}")
                            except json.JSONDecodeError as e:
                                print(f"  ❌ Failed to parse JSON: {e}")
                    except Exception as e:
                        print(f"  Error reading response: {e}")
                        
            except Exception as e:
                print(f"  ❌ Request failed: {e}")
    
    # Also try with callsign including slash
    print("\n\n" + "="*60)
    print("Testing with slashed callsign (MM3RA/J1)")
    print("="*60)
    
    callsign = "MM3RA/J1"
    endpoint = f"{WAVELOG_API_URL}/api/qsos/{callsign}"
    
    async with aiohttp.ClientSession() as session:
        print(f"\n🔍 Testing endpoint: {endpoint}")
        try:
            print(f"  Trying GET with params...")
            async with session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"  Status: {resp.status}")
                text = await resp.text()
                print(f"  Response (first 500 chars): {text[:500]}")
        except Exception as e:
            print(f"  ❌ Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_recent_qsos_endpoint())