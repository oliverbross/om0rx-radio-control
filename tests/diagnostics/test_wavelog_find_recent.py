#!/usr/bin/env python3
"""
Binary search to find the highest ID with recent (Feb 2025) data
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

async def test_find_recent():
    """Binary search for the last ID with Feb 2025 data"""
    print("=" * 70)
    print("Binary search for latest QSO data")
    print("=" * 70)
    
    api_url = config.WAVELOG_API_URL.rstrip('/')
    api_key = config.WAVELOG_API_KEY
    station_id = config.WAVELOG_STATION_ID
    endpoint = f"{api_url}/api/get_contacts_adif"
    
    connector = aiohttp.TCPConnector(limit=5, limit_per_host=3)
    timeout = aiohttp.ClientTimeout(total=60)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    
    try:
        # First, find approximate range
        print("\n🔍 Finding data range...")
        test_points = [50000, 70000, 80000, 90000, 95000, 98000, 99000, 99500]
        
        latest_id_with_data = 0
        latest_date = None
        
        for testid in test_points:
            date = await get_date_at_id(session, endpoint, api_key, station_id, testid)
            if date:
                print(f"   ID {testid:6d} → {date}")
                latest_id_with_data = testid
                latest_date = date
            else:
                print(f"   ID {testid:6d} → No data")
                break
        
        if latest_id_with_data > 0:
            print(f"\n✅ Found data up to ID {latest_id_with_data} (date: {latest_date})")
            print(f"   To get the last 100 QSOs, use: fetchfromid={max(0, latest_id_with_data - 100)}")
        else:
            print(f"\n❌ No recent data found")
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_find_recent())