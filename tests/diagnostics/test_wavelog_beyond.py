#!/usr/bin/env python3
"""
Test if there are records beyond lastfetchedid 41705
"""

import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
import aiohttp

async def test_beyond_last():
    """Try to fetch records beyond the reported last ID"""
    print("=" * 70)
    print("Testing if there are records beyond lastfetchedid=41705")
    print("=" * 70)
    
    api_url = config.WAVELOG_API_URL.rstrip('/')
    api_key = config.WAVELOG_API_KEY
    station_id = config.WAVELOG_STATION_ID
    endpoint = f"{api_url}/api/get_contacts_adif"
    
    connector = aiohttp.TCPConnector(limit=5, limit_per_host=3)
    timeout = aiohttp.ClientTimeout(total=60)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    
    try:
        # Try to fetch records well beyond the last reported ID
        test_cases = [
            41705,
            41706,
            41800,
            42000,
            50000,
            99999999,
        ]
        
        for fetchfromid in test_cases:
            print(f"\n📍 Trying fetchfromid={fetchfromid}, limit=5")
            print("-" * 70)
            
            payload = {
                'key': api_key,
                'station_id': station_id,
                'fetchfromid': fetchfromid,
                'limit': 5
            }
            
            try:
                async with session.post(endpoint, json=payload) as resp:
                    if resp.status == 200:
                        response_text = await resp.text()
                        result = json.loads(response_text)
                        
                        exported_qsos = result.get('exported_qsos', 0)
                        lastfetchedid = result.get('lastfetchedid', 'NOT PROVIDED')
                        
                        print(f"   exported_qsos: {exported_qsos}")
                        print(f"   lastfetchedid: {lastfetchedid}")
                        
                        if exported_qsos > 0:
                            adif = result.get('adif', '').lower()
                            import re
                            dates = re.findall(r'<qso_date:8>(\d{8})', adif)
                            calls = re.findall(r'<call:(\d+)>([^<]+)', adif)
                            if dates:
                                print(f"   Found dates: {dates}")
                                if calls:
                                    print(f"   Found calls: {[c[1].strip() for c in calls[:3]]}")
                        else:
                            print(f"   ✓ No records returned (beyond last available)")
                    else:
                        print(f"   Error: {resp.status}")
            except Exception as e:
                print(f"   Exception: {e}")
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_beyond_last())