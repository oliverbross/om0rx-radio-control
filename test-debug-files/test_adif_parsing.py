import json
import sys
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

from wavelog_api import WavelogClient
import aiohttp
import asyncio

async def test_parsing():
    client = WavelogClient()
    
    # Fetch the ADIF from Wavelog
    endpoint = f"{client.api_url}/api/get_contacts_adif"
    
    payload = {
        'key': client.api_key,
        'station_id': client.station_id,
        'fetchfromid': 0
    }
    
    print(f"Fetching from: {endpoint}")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            print(f"Status: {resp.status}")
            if resp.status == 200:
                result = await resp.json()
                print(f"API Response keys: {list(result.keys())}")
                print(f"Status: {result.get('status')}")
                print(f"Message: {result.get('message')}")
                print(f"Exported QSOs: {result.get('exported_qsos')}")
                
                if result.get('adif'):
                    adif_data = result['adif']
                    print(f"ADIF data length: {len(adif_data)} bytes")
                    
                    # Try parsing for OM0AAO
                    qsos = client._parse_adif_qsos(adif_data, 'OM0AAO', 5)
                    print(f"\nFound {len(qsos)} QSOs for OM0AAO")
                    
                    if qsos:
                        for idx, qso in enumerate(qsos[:3], 1):
                            print(f"  QSO {idx}: {qso.get('call')} on {qso.get('qso_date')} {qso.get('mode')} {qso.get('frequency')} MHz")
                    else:
                        # Try to debug - check what calls are in the ADIF
                        records = adif_data.split('<eor>')[:20]  # Check first 20 records
                        import re
                        print("\nChecking first records for callsigns...")
                        for i, record in enumerate(records[:5]):
                            pattern = r'<([^:>]+):(\d+)>([^<]*)'
                            matches = re.findall(pattern, record)
                            calls = [v for k, l, v in matches if k.upper() == 'CALL']
                            if calls:
                                print(f"  Record {i}: CALL={calls[0]}")
            else:
                text = await resp.text()
                print(f"Error: {text[:200]}")

asyncio.run(test_parsing())
