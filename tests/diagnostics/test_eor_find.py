import sys
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

from wavelog_api import WavelogClient
import aiohttp
import asyncio

async def test_eor():
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
                
                # Search for EOR markers
                print("Searching for EOR variations...")
                for pattern in ['<eor>', '<EOR>', '<Eor>', '<eOR>']:
                    count = adif_data.count(pattern)
                    if count > 0:
                        print(f"Found '{pattern}': {count} times")
                        # Show context
                        idx = adif_data.find(pattern)
                        print(f"  Context: ...{repr(adif_data[max(0,idx-50):idx+50])}...")
                        break
                else:
                    print("No EOR tag found")
                    
                    # Look for patterns that might indicate record boundaries
                    print("\nLooking for common boundaries...")
                    # Check if there are multiple OM0AAO entries (indicating separate records)
                    om0_count = adif_data.count('OM0AAO')
                    print(f"OM0AAO appears {om0_count} times")
                    
                    # Find the positions of OM0AAO
                    idx = 0
                    positions = []
                    for i in range(min(3, om0_count)):
                        idx = adif_data.find('OM0AAO', idx)
                        if idx != -1:
                            positions.append(idx)
                            # Show what's between them
                            if i < 2:
                                next_idx = adif_data.find('OM0AAO', idx+1)
                                if next_idx != -1:
                                    between = adif_data[idx:next_idx]
                                    print(f"\nBetween OM0AAO #{i+1} and #{i+2}:")
                                    # Look for record separators
                                    if '\\n' in between:
                                        lines = between.split('\\n')
                                        print(f"  Has {len(lines)} lines")
                            idx += 1

asyncio.run(test_eor())
