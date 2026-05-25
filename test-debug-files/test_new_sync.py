#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

# Remove old DB to force full resync
db_path = r'c:\Projects\om0rx-radio-control\data\qso_log.duckdb'
if os.path.exists(db_path):
    os.remove(db_path)
    print(f"✅ Removed old database")

from adif_sync import ADIFDuckDBSync
import time
import duckdb

print("Initializing new sync...")
sync = ADIFDuckDBSync()

print("Starting full sync of ADIF file (this may take a minute)...")
start = time.time()
result = sync.sync()
elapsed = time.time() - start

print(f"\n{'='*60}")
print(f"Sync Result: {result}")
print(f"Time taken: {elapsed:.1f}s")
print(f"{'='*60}")

# Check the database
print("\nDatabase Statistics:")
conn = duckdb.connect(db_path)

# Get count of records
count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
print(f"✅ Total records: {count:,}")

# Get oldest and newest
oldest = conn.execute("SELECT call, qso_date, time_on FROM qso_records ORDER BY qso_date ASC, time_on ASC LIMIT 1").fetchall()
print(f"✅ Oldest: {oldest[0] if oldest else 'None'}")

newest = conn.execute("SELECT call, qso_date, time_on FROM qso_records ORDER BY qso_date DESC, time_on DESC LIMIT 1").fetchall()
print(f"✅ Newest: {newest[0] if newest else 'None'}")

# Check for 9Y4DG
calls_9y4dg = conn.execute("SELECT call, qso_date, time_on FROM qso_records WHERE call = '9Y4DG'").fetchall()
if calls_9y4dg:
    print(f"✅ 9Y4DG found: {calls_9y4dg}")
else:
    print(f"❌ 9Y4DG NOT found")

conn.close()
print(f"\n✅ Sync test complete!")