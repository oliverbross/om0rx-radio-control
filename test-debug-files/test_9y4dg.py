#!/usr/bin/env python3
import duckdb

conn = duckdb.connect(r'c:\Projects\om0rx-radio-control\data\qso_log.duckdb')

# Search for 9Y4DG
result = conn.execute("SELECT call, qso_date, time_on FROM qso_records WHERE call = '9Y4DG'").fetchall()
print(f'9Y4DG found: {result}')

# Count records with recent dates (2024 and 2025)
recent = conn.execute("SELECT COUNT(*) FROM qso_records WHERE qso_date >= '20240000'").fetchall()
print(f'Records with date >= 2024: {recent[0][0]}')

# Get a few records with the latest dates
latest = conn.execute("SELECT call, qso_date, time_on FROM qso_records ORDER BY qso_date DESC LIMIT 10").fetchall()
print(f'Latest 10 records:')
for r in latest:
    print(f'  {r}')

# Check ADIF file directly for 9Y4DG
print("\n=== Checking ADIF file directly ===")
with open(r'c:\Projects\om0rx-radio-control\logs\qso_log.adif', 'r') as f:
    content = f.read()
    if '9Y4DG' in content:
        # Find the record
        idx = content.find('9Y4DG')
        print(f"9Y4DG found in ADIF at position {idx}")
        # Print context around it
        start = max(0, idx - 100)
        end = min(len(content), idx + 200)
        print(f"Context: ...{content[start:end]}...")
    else:
        print("9Y4DG NOT found in ADIF file!")

conn.close()