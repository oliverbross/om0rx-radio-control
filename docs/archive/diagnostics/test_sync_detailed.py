#!/usr/bin/env python3
import sys
import logging
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

from radio_control.adif_sync import ADIFDuckDBSync
import time

print("=" * 60)
print("Testing ADIF DuckDB Sync with Detailed Logging")
print("=" * 60)

# Initialize and run sync
sync = ADIFDuckDBSync()

# Remove old DB to force full resync
import os
db_path = r'c:\Projects\om0rx-radio-control\data\qso_log.duckdb'
if os.path.exists(db_path):
    os.remove(db_path)
    print(f"Removed old database: {db_path}")

# Reinitialize after removing DB
sync = ADIFDuckDBSync()

print("\nStarting sync...")
start = time.time()
result = sync.sync()
elapsed = time.time() - start

print(f"\nSync Result: {result}")
print(f"Time taken: {elapsed:.2f}s")

# Check the database
import duckdb
conn = duckdb.connect(db_path)

# Get count of records
count_result = conn.execute("SELECT COUNT(*) FROM qso_records").fetchall()
print(f"\nTotal records in DB: {count_result[0][0]}")

# Get oldest and newest
oldest = conn.execute("SELECT call, qso_date, time_on FROM qso_records ORDER BY qso_date ASC, time_on ASC LIMIT 1").fetchall()
print(f"Oldest: {oldest[0] if oldest else 'None'}")

newest = conn.execute("SELECT call, qso_date, time_on FROM qso_records ORDER BY qso_date DESC, time_on DESC LIMIT 1").fetchall()
print(f"Newest: {newest[0] if newest else 'None'}")

conn.close()