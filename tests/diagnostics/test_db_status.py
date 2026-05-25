#!/usr/bin/env python3
import sqlite3
db_path = 'c:\\Projects\\om0rx-radio-control\\data\\wavelog.db'
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f'Database: {db_path}')
    print('Tables in database:')
    for table in tables:
        print(f'  {table[0]}')
        # Get count for each table
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f'    Count: {count}')
        except Exception as e:
            print(f'    Error: {e}')
    
    # Check for recent QSOs
    if tables:
        cursor.execute("SELECT callsign, qso_date, time_on FROM qsos ORDER BY qso_date DESC, time_on DESC LIMIT 5")
        latest = cursor.fetchall()
        print('\nLatest 5 QSOs:')
        for row in latest:
            print(f'  {row[0]} - {row[1]} {row[2]}')
    
    conn.close()
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()