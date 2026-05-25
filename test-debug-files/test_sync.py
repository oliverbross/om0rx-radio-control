#!/usr/bin/env python3
import sys
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

from adif_sync import ADIFDuckDBSync
import time

print("Testing ADIF DuckDB Sync...")
sync = ADIFDuckDBSync()

start = time.time()
result = sync.sync()
elapsed = time.time() - start

print(f"Sync result: {result}")
print(f"Time taken: {elapsed:.2f}s")

# Check the database
import duckdb
conn = duckdb.connect(r'c:\Projects\om0rx-radio-control\logs\adif_qsos.duckdb')
tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
print(f"Tables after sync: {tables}")

if tables:
    for table in tables:
        table_name = table[0]
        count = conn.execute(f'SELECT COUNT(*) FROM {table_name}').fetchall()
        print(f"  {table_name}: {count[0][0]} records")
        
        if table_name == 'qsos':
            # Get oldest
            oldest = conn.execute('SELECT call, qso_date, time_on FROM qsos ORDER BY qso_date ASC, time_on ASC LIMIT 1').fetchall()
            print(f"  Oldest: {oldest[0] if oldest else 'No records'}")
            
            # Get newest
            newest = conn.execute('SELECT call, qso_date, time_on FROM qsos ORDER BY qso_date DESC, time_on DESC LIMIT 1').fetchall()
            print(f"  Newest: {newest[0] if newest else 'No records'}")

conn.close()