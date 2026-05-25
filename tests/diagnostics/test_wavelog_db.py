#!/usr/bin/env python3
"""Test script to debug Wavelog database queries"""

import sys
sys.path.insert(0, 'c:\\Projects\\om0rx-radio-control')

from wavelog_db import get_wavelog_db

db = get_wavelog_db()
qsos = db.get_all_qsos(limit=15)

print('📊 Most recent 15 contacts in Wavelog database:')
print('-' * 100)
for i, qso in enumerate(qsos, 1):
    callsign = qso.get('callsign', '?')
    qso_date = qso.get('qso_date', '?')
    time_on = qso.get('time_on', '?')
    mode = qso.get('mode', '?')
    band = qso.get('band', '?')
    print(f'{i}. {callsign} - {qso_date} {time_on} - {mode} on {band}')

# Search for R3WF specifically
print()
print('🔍 Searching for R3WF:')
r3wf = db.get_qsos_by_callsign('R3WF')
if r3wf:
    for qso in r3wf[:3]:
        print(f'   Found: {qso.get("qso_date")} {qso.get("time_on")}')
else:
    print('   ❌ R3WF not found in database')