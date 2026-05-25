#!/usr/bin/env python3
"""
Precise search for the last QSO ID
"""

import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
import aiohttp

async def get_date_at_id(session, endpoint, api_key, station_id, fetchfromid):
    """Fetch one QSO at given ID and return its date"""
    payload = {
        'key': api_key,
        'station_id': station_id,
        'fetchfromid': fetchfromid,
        'limit': 1
    }
    
    try:
        async with session.post(endpoint, json=payload) as resp:
            if resp.status == 200:
                result = json.loads(await resp.text())
                if result.get('exported_qsos', 0) > 0:
                    adif = result.get('adif', '').lower()
                    import re
                    dates = re.findall(r'<qso_date:8>(\d{8})', adif)
                    if dates:
                        return dates[0]
    except:
        pass
    return None

async def test_precise():
    """Find exact last ID"""
    print("=" * 70)
    print("Finding exact last QSO ID")
    print("=" * 70)
    
    api_url = config.WAVELOG_API_URL.rstrip('/')
    api_key = config.WAVELOG_API_KEY
    station_id = config.WAVELOG_STATION_ID
    endpoint = f"{api_url}/api/get_contacts_adif"
    
    connector = aiohttp.TCPConnector(limit=5, limit_per_host=3)
    timeout = aiohttp.ClientTimeout(total=60)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    
    try:
        # Narrow search: between 70000 and 80000
        print("\n🔍 Refining search between 70000 and 80000...")
        test_points = [70000, 72000, 74000, 76000, 78000, 79000, 79500, 79750, 79900, 79950, 79975, 79990, 79999]
        
        latest_id = 70000
        latest_date = "20250610"
        
        for testid in test_points:
            date = await get_date_at_id(session, endpoint, api_key, station_id, testid)
            if date:
                print(f"   ID {testid:6d} → {date} ✓")
                latest_id = testid
                latest_date = date
            else:
                print(f"   ID {testid:6d} → No data ✗")
        
        print(f"\n✅ Latest data found:")
        print(f"   ID: {latest_id}")
        print(f"   Date: {latest_date}")
        print(f"\n📊 To get the last 100 QSOs, use:")
        print(f"   fetchfromid: {max(0, latest_id - 100)}")
        print(f"   limit: 100")
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_precise())