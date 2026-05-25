import sys
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

from radio_control.wavelog_api import WavelogClient
import aiohttp
import asyncio

async def test_complete_fix():
    client = WavelogClient()
    endpoint = f"{client.api_url}/api/get_contacts_adif"
    payload = {
        'key': client.api_key,
        'station_id': client.station_id,
        'fetchfromid': 0
    }
    
    print("Testing ADIF parsing with both fixes:")
    print("  1. Split on <EOR> (uppercase)")
    print("  2. Strip whitespace from field values")
    print("")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                result = await resp.json()
                adif_data = result['adif']
                
                # Test the parsing
                qsos = client._parse_adif_qsos(adif_data, 'OM0AAO', 5)
                
                print(f"✅ SUCCESS: Found {len(qsos)} QSOs for OM0AAO\n")
                
                if qsos:
                    print("Recent QSOs with OM0AAO:")
                    for idx, qso in enumerate(qsos, 1):
                        date = qso.get('qso_date', 'N/A')
                        time = qso.get('time_on', 'N/A')
                        mode = qso.get('mode', 'N/A')
                        freq = qso.get('frequency', 'N/A')
                        print(f"  {idx}. {qso.get('call')} - {date} {time[:2]}:{time[2:4]} - {mode} - {freq} MHz")
                else:
                    print("ERROR: Still no QSOs found!")

asyncio.run(test_complete_fix())
