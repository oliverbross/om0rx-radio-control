import sys
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

from radio_control.wavelog_api import WavelogClient
import aiohttp
import asyncio
import re

async def test_debug():
    client = WavelogClient()
    
    endpoint = f"{client.api_url}/api/get_contacts_adif"
    
    payload = {
        'key': client.api_key,
        'station_id': client.station_id,
        'fetchfromid': 0
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                result = await resp.json()
                adif_data = result['adif']
                
                # Parse manually with debug
                records = adif_data.split('<eor>')
                print(f"Total records: {len(records)}")
                print(f"Record 0 length: {len(records[0])} chars")
                
                # Check first record after stripping
                first = records[0].strip()
                pattern = r'<([^:>]+):(\d+)>([^<]*)'
                matches = re.findall(pattern, first)
                
                print(f"\nFirst record fields: {len(matches)} fields")
                print("\nCALL fields found:")
                
                for field_name, field_len, field_value in matches:
                    if field_name.upper() == 'CALL':
                        stripped = field_value.strip()
                        print(f"  Raw: {repr(field_value)}")
                        print(f"  Stripped: {repr(stripped)}")
                        print(f"  Matches OM0AAO: {stripped.upper() == 'OM0AAO'}")

asyncio.run(test_debug())
