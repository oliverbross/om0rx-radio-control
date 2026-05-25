#!/usr/bin/env python3
"""
Debug script to see the raw ADIF data from Wavelog API
"""

import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from radio_control import config
import aiohttp

async def test_raw_response():
    """Get raw API response to debug ADIF format"""
    print("=" * 60)
    print("Debugging Wavelog API Raw Response")
    print("=" * 60)
    
    api_url = config.WAVELOG_API_URL.rstrip('/')
    api_key = config.WAVELOG_API_KEY
    station_id = config.WAVELOG_STATION_ID
    
    endpoint = f"{api_url}/api/get_contacts_adif"
    
    # First discovery query
    discovery_payload = {
        'key': api_key,
        'station_id': station_id,
        'fetchfromid': 0,
        'limit': 999999
    }
    
    print(f"\n🔍 Step 1: Discovery Query")
    print(f"Endpoint: {endpoint}")
    print(f"Payload: {discovery_payload}")
    
    connector = aiohttp.TCPConnector(limit=5, limit_per_host=3)
    timeout = aiohttp.ClientTimeout(total=60)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    
    try:
        async with session.post(endpoint, json=discovery_payload) as resp:
            if resp.status == 200:
                discovery_response = await resp.text()
                discovery_result = json.loads(discovery_response)
                total_qsos = int(discovery_result.get('exported_qsos', 0))
                print(f"✅ Response Status: {resp.status}")
                print(f"   Total QSOs: {total_qsos}")
                print(f"   Response keys: {list(discovery_result.keys())}")
                print(f"   Message: {discovery_result.get('message')}")
                
                # Show first 500 chars of ADIF
                adif = discovery_result.get('adif', '')
                print(f"   ADIF data length: {len(adif)} chars")
                if adif:
                    print(f"   First 500 chars of ADIF:")
                    print("   " + adif[:500])
                    print("   ...")
                    print("   Last 200 chars of ADIF:")
                    print("   " + adif[-200:])
            else:
                print(f"❌ Error: {resp.status}")
                text = await resp.text()
                print(f"   Response: {text[:500]}")
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_raw_response())