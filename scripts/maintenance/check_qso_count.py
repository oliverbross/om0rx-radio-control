#!/usr/bin/env python3
"""Quick script to check how many QSOs are in DuckDB"""

import duckdb
import _bootstrap  # noqa: F401
from radio_control import config

db_path = config.DATA_DIR / 'qso_log.duckdb'

try:
    conn = duckdb.connect(str(db_path))
    
    # Check if table exists
    tables = conn.execute("SHOW TABLES").fetchall()
    print(f"📋 Tables in database: {tables}")
    print()
    
    if tables:
        # Count records
        count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
        print(f"📊 Total QSOs in DuckDB: {count}")
        
        # Get sync metadata
        try:
            metadata = conn.execute("SELECT * FROM sync_metadata WHERE id = 1").fetchone()
            if metadata:
                print(f"\n🔄 Sync Metadata:")
                print(f"   Last sync: {metadata[1]}")
                print(f"   Last Wavelog modified: {metadata[2]}")
                print(f"   Last Wavelog ID: {metadata[3]}")
                print(f"   Total records synced: {metadata[4]}")
                print(f"   Last sync added: {metadata[5]}")
                print(f"   Last sync updated: {metadata[6]}")
        except:
            print("\n⚠️  No sync metadata found")
        
        # Sample a few records
        if count > 0:
            sample = conn.execute("SELECT call, qso_date, time_on, mode FROM qso_records LIMIT 5").fetchall()
            print(f"\n📻 Sample QSOs:")
            for row in sample:
                print(f"   {row[0]} | {row[1]} {row[2]} | {row[3]}")
    else:
        print("❌ No tables found - database is empty")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
