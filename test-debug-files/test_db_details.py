#!/usr/bin/env python3
import os
import duckdb

db_path = r'c:\Projects\om0rx-radio-control\data\qso_log.duckdb'

conn = duckdb.connect(db_path)

# Check sync_metadata
print("=== SYNC METADATA ===")
metadata = conn.execute("SELECT * FROM sync_metadata").fetchall()
for row in metadata:
    print(f"  {row}")

# Check qso_records table structure and content
print("\n=== QSO_RECORDS TABLE ===")
cols = conn.execute("DESCRIBE qso_records").fetchall()
print("Columns:")
for col in cols:
    print(f"  {col}")

# Get count
count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchall()
print(f"\nTotal records: {count[0][0]}")

# Get oldest and newest
oldest = conn.execute("SELECT call, qso_date, time_on FROM qso_records ORDER BY qso_date ASC, time_on ASC LIMIT 1").fetchall()
print(f"Oldest: {oldest[0] if oldest else 'None'}")

newest = conn.execute("SELECT call, qso_date, time_on FROM qso_records ORDER BY qso_date DESC, time_on DESC LIMIT 1").fetchall()
print(f"Newest: {newest[0] if newest else 'None'}")

# Sample a few records
print("\nSample records:")
samples = conn.execute("SELECT call, qso_date, time_on FROM qso_records LIMIT 5").fetchall()
for s in samples:
    print(f"  {s}")

conn.close()