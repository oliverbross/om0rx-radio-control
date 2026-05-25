#!/usr/bin/env python3
"""
Test to understand how Wavelog's fetchfromid parameter works
"""

import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from radio_control import config
import aiohttp

async def test_fetchfromid():
    """Test different fetchfromid values to understand pagination"""
    print("=" * 70)
    print("Testing Wavelog fetchfromid parameter")
    print("=" * 70)
    
    api_url = config.WAVELOG_API_URL.rstrip('/')
    api_key = config.WAVELOG_API_KEY
    station_id = config.WAVELOG_STATION_ID
    endpoint = f"{api_url}/api/get_contacts_adif"
    
    connector = aiohttp.TCPConnector(limit=5, limit_per_host=3)
    timeout = aiohttp.ClientTimeout(total=60)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    
    try:
        # Test different fetchfromid values
        test_cases = [
            (0, 1, "fetchfromid=0, limit=1"),
            (0, 5, "fetchfromid=0, limit=5"),
            (100, 5, "fetchfromid=100, limit=5"),
            (1000, 5, "fetchfromid=1000, limit=5"),
            (41700, 5, "fetchfromid=41700, limit=5 (near end)"),
        ]
        
        for fetchfromid, limit, description in test_cases:
            print(f"\n🔍 Test: {description}")
            print("-" * 70)
            
            payload = {
                'key': api_key,
                'station_id': station_id,
                'fetchfromid': fetchfromid,
                'limit': limit
            }
            
            try:
                async with session.post(endpoint, json=payload) as resp:
                    if resp.status == 200:
                        response_text = await resp.text()
                        result = json.loads(response_text)
                        
                        exported_qsos = result.get('exported_qsos', 0)
                        print(f"   exported_qsos: {exported_qsos}")
                        
                        # Parse first and last QSO dates from ADIF
                        adif = result.get('adif', '')
                        
                        # Extract QSO_DATE fields
                        import re
                        dates = re.findall(r'<qso_date:8>(\d{8})', adif)
                        calls = re.findall(r'<call:(\d+)>([^<]+)', adif)
                        
                        if dates:
                            print(f"   First QSO date: {dates[0]} (ID would be 0-based)")
                            if len(dates) > 1:
                                print(f"   Last QSO date:  {dates[-1]}")
                            if calls:
                                print(f"   First call: {calls[0][1]}")
                                if len(calls) > 1:
                                    print(f"   Last call:  {calls[-1][1]}")
                        else:
                            print(f"   No QSO data found in response (ADIF length: {len(adif)} chars)")
                    else:
                        print(f"   Error: {resp.status}")
            except Exception as e:
                print(f"   Exception: {e}")
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_fetchfromid())