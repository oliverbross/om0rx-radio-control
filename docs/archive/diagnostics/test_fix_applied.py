import sys
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

# Fresh import after cache clear
from radio_control.wavelog_api import WavelogClient
import aiohttp
import asyncio

async def test_full_parsing():
    client = WavelogClient()
    
    endpoint = f"{client.api_url}/api/get_contacts_adif"
    
    payload = {
        'key': client.api_key,
        'station_id': client.station_id,
        'fetchfromid': 0
    }
    
    print("Testing ADIF parsing with strip() fix...")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                result = await resp.json()
                adif_data = result['adif']
                
                # Use the actual fixed method
                print(f"Parsing ADIF for OM0AAO (with fix)...")
                qsos = client._parse_adif_qsos(adif_data, 'OM0AAO', 5)
                
                print(f"\n✅ SUCCESS: Found {len(qsos)} QSOs for OM0AAO")
                if qsos:
                    print("\nQSO Details:")
                    for idx, qso in enumerate(qsos, 1):
                        print(f"  {idx}. {qso.get('call')} - {qso.get('qso_date')} {qso.get('mode')} {qso.get('frequency')} MHz")
                else:
                    print("ERROR: Still found 0 QSOs - strip() fix may not have applied")
            else:
                print(f"API error: {resp.status}")

asyncio.run(test_full_parsing())
