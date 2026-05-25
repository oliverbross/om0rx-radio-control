#!/usr/bin/env python3
"""
Check the lastfetchedid value from Wavelog API to understand ID mapping
"""

import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
import aiohttp

async def test_lastfetchedid():
    """Check lastfetchedid and exported_qsos values"""
    print("=" * 70)
    print("Understanding Wavelog ID mapping")
    print("=" * 70)
    
    api_url = config.WAVELOG_API_URL.rstrip('/')
    api_key = config.WAVELOG_API_KEY
    station_id = config.WAVELOG_STATION_ID
    endpoint = f"{api_url}/api/get_contacts_adif"
    
    connector = aiohttp.TCPConnector(limit=5, limit_per_host=3)
    timeout = aiohttp.ClientTimeout(total=60)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    
    try:
        # Test to find the actual last ID
        test_cases = [
            (0, 1, "Oldest"),
            (0, 100, "First 100"),
            (41600, 100, "Near claimed end"),
            (41700, 5, "Even nearer"),
        ]
        
        for fetchfromid, limit, description in test_cases:
            print(f"\n📍 {description} (fetchfromid={fetchfromid}, limit={limit})")
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
                        lastfetchedid = result.get('lastfetchedid', 'NOT PROVIDED')
                        message = result.get('message', '')
                        
                        print(f"   exported_qsos: {exported_qsos}")
                        print(f"   lastfetchedid: {lastfetchedid}")
                        print(f"   message: {message}")
                        
                        # Get first and last date
                        adif = result.get('adif', '').lower()
                        import re
                        dates = re.findall(r'<qso_date:8>(\d{8})', adif)
                        if dates:
                            print(f"   First date: {dates[0]}")
                            print(f"   Last date:  {dates[-1] if len(dates) > 1 else 'N/A'}")
                    else:
                        print(f"   Error: {resp.status}")
            except Exception as e:
                print(f"   Exception: {e}")
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_lastfetchedid())