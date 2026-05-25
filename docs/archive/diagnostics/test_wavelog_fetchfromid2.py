#!/usr/bin/env python3
"""
Test to understand how Wavelog's fetchfromid parameter works - with better parsing
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
            (0, 5, "START (fetchfromid=0)"),
            (41700, 5, "NEAR END (fetchfromid=41700)"),
        ]
        
        for fetchfromid, limit, description in test_cases:
            print(f"\n🔍 {description}")
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
                        print(f"   Exported QSOs: {exported_qsos}")
                        
                        # Show raw ADIF snippet
                        adif = result.get('adif', '')
                        
                        # Convert to lowercase for searching
                        adif_lower = adif.lower()
                        
                        # Find QSO_DATE and CALL
                        import re
                        dates = re.findall(r'<qso_date:8>(\d{8})', adif_lower)
                        calls_match = re.findall(r'<call:(\d+)>([^<]+)', adif_lower)
                        
                        if dates:
                            print(f"   Dates found: {dates}")
                            if calls_match:
                                print(f"   Calls found: {[c[1].upper() for c in calls_match]}")
                        else:
                            # Try uppercase
                            dates = re.findall(r'<QSO_DATE:8>(\d{8})', adif)
                            calls_match = re.findall(r'<CALL:(\d+)>([^<]+)', adif)
                            if dates:
                                print(f"   Dates found (uppercase): {dates}")
                                if calls_match:
                                    print(f"   Calls found (uppercase): {[c[1].upper() for c in calls_match]}")
                            else:
                                # Show first 300 chars of ADIF to debug
                                print(f"   ADIF content (first 300 chars):")
                                print(f"   {adif[:300]}")
                    else:
                        print(f"   Error: {resp.status}")
            except Exception as e:
                print(f"   Exception: {e}")
                import traceback
                traceback.print_exc()
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_fetchfromid())