import json
import sys
import re
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

from radio_control.wavelog_api import WavelogClient
import aiohttp
import asyncio

async def test_detailed():
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
                
                # Get the first record with OM0AAO
                records = adif_data.split('<eor>')
                
                print(f"Total records: {len(records)}")
                
                # Find OM0AAO record
                target = 'OM0AAO'
                om0aao_record = None
                for idx, record in enumerate(records):
                    if target in record.upper():
                        om0aao_record = record
                        print(f"\nFound {target} at record index {idx}")
                        break
                
                if om0aao_record:
                    # Show the raw record
                    print(f"\nRaw record (first 500 chars):")
                    print(repr(om0aao_record[:500]))
                    
                    # Parse it manually
                    print(f"\nParsing manually:")
                    pattern = r'<([^:>]+):(\d+)>([^<]*)'
                    matches = re.findall(pattern, om0aao_record)
                    
                    qso_data = {}
                    for field_name, field_len, field_value in matches:
                        qso_data[field_name.lower()] = field_value
                        if field_name.upper() in ['CALL', 'QSO_DATE', 'MODE', 'FREQ']:
                            print(f"  {field_name.lower()}: '{field_value}'")
                    
                    print(f"\nTotal fields extracted: {len(qso_data)}")
                    call = qso_data.get('call', '').upper()
                    print(f"Extracted CALL field: '{call}'")
                    print(f"Target callsign: '{target.upper()}'")
                    print(f"Match result: {call == target.upper()}")

asyncio.run(test_detailed())
