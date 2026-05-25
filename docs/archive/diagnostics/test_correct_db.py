#!/usr/bin/env python3
import os
import duckdb

db_path = r'c:\Projects\om0rx-radio-control\logs\qso_log.duckdb'
print(f'DB exists: {os.path.exists(db_path)}')
if os.path.exists(db_path):
    print(f'DB size: {os.path.getsize(db_path)} bytes')
    
    conn = duckdb.connect(db_path)
    # List all tables
    tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
    print(f'Tables: {tables}')
    
    if tables:
        for table in tables:
            table_name = table[0]
            count = conn.execute(f'SELECT COUNT(*) FROM {table_name}').fetchall()
            print(f'  {table_name}: {count[0][0]} records')
            
            if table_name == 'qsos':
                # Get oldest
                oldest = conn.execute('SELECT call, qso_date, time_on FROM qsos ORDER BY qso_date ASC, time_on ASC LIMIT 1').fetchall()
                print(f'  Oldest: {oldest[0] if oldest else "No records"}')
                
                # Get newest
                newest = conn.execute('SELECT call, qso_date, time_on FROM qsos ORDER BY qso_date DESC, time_on DESC LIMIT 1').fetchall()
                print(f'  Newest: {newest[0] if newest else "No records"}')
    
    conn.close()
else:
    print('DB file does not exist!')