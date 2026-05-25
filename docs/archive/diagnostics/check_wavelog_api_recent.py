#!/usr/bin/env python3
"""Check most recent contacts in Wavelog API"""

import urllib.request
import json
import re

url = 'https://om0rx.wavelog.online/index.php/api/get_contacts_adif'
params = {'key': '<wavelog_api_key>', 'station_id': '1', 'fetchfromid': 0}

req = urllib.request.Request(url, data=json.dumps(params).encode('utf-8'), method='POST')
req.add_header('Content-Type', 'application/json')

print("Fetching ADIF data from Wavelog API...")
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    adif = data.get('adif', '')
    
    # Split by <EOR>
    records = re.split(r'<(?:eor|eoh)>\s*', adif, flags=re.IGNORECASE)
    
    print(f"Total records: {len(records) - 2}")  # -2 for header and trailing empty
    
    # Parse last 10 records
    print("\nParsing last 10 records...")
    
    recent_records = []
    for record_text in records[-12:-2]:  # Skip header and trailing
        record_text = record_text.strip()
        if not record_text:
            continue
            
        # Extract key fields
        call_match = re.search(r'<CALL:(\d+)>([^<]+)', record_text)
        date_match = re.search(r'<QSO_DATE:(\d+)>(\d+)', record_text)
        time_match = re.search(r'<TIME_ON:(\d+)>(\d+)', record_text)
        
        call = call_match.group(2) if call_match else "?"
        qso_date = date_match.group(2) if date_match else "?"
        time_on = time_match.group(2) if time_match else "?"
        
        recent_records.append((call, qso_date, time_on))
    
    # Display in order (these are the most recent 10)
    print("\nMost recent contacts (last 10):")
    for i, (call, date, time) in enumerate(reversed(recent_records), 1):
        print(f"  {i}. {call} - {date} {time}")
    
    # Search for R3WF specifically
    print("\nSearching for R3WF in all records...")
    r3wf_count = 0
    for record_text in records:
        if 'R3WF' in record_text.upper():
            call_match = re.search(r'<CALL:(\d+)>([^<]+)', record_text)
            date_match = re.search(r'<QSO_DATE:(\d+)>(\d+)', record_text)
            time_match = re.search(r'<TIME_ON:(\d+)>(\d+)', record_text)
            
            if call_match and date_match and time_match:
                call = call_match.group(2)
                qso_date = date_match.group(2)
                time_on = time_match.group(2)
                print(f"  Found: {call} - {qso_date} {time_on}")
                r3wf_count += 1
    
    if r3wf_count == 0:
        print("  R3WF not found in API response!")
    else:
        print(f"  Total R3WF records: {r3wf_count}")