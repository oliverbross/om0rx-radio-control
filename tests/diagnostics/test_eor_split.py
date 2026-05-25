import sys
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

from wavelog_api import WavelogClient
import aiohttp
import asyncio
import json

async def test_split():
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
                
                # Show first 300 chars
                print("First 500 chars of ADIF data:")
                print(repr(adif_data[:500]))
                
                print("\n\nSearching for <eor> pattern:")
                if '<eor>' in adif_data:
                    print(f"Found literal <eor> tags")
                elif '\\r\\n<eor>\\r\\n' in adif_data:
                    print(f"Found <eor> with escape sequences")
                    # Count them
                    count = adif_data.count('\\r\\n<eor>\\r\\n')
                    print(f"Total <eor> occurrences: {count}")
                else:
                    print(f"No <eor> found in expected form")
                    
                # Check for newlines
                print(f"\nActual newline characters:")
                print(f"  \\r count: {adif_data.count(chr(13))}")
                print(f"  \\n count: {adif_data.count(chr(10))}")
                print(f"  Literal \\\\r\\\\n count: {adif_data.count(repr('\\r\\n'))}")

asyncio.run(test_split())
