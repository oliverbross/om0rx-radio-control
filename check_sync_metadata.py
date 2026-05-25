#!/usr/bin/env python3
"""Check sync metadata in detail"""

import duckdb
from pathlib import Path

db_path = Path(__file__).parent / 'data' / 'qso_log.duckdb'

try:
    conn = duckdb.connect(str(db_path))
    
    # Get all columns from sync_metadata
    result = conn.execute("DESCRIBE sync_metadata").fetchall()
    print("📋 Sync Metadata Table Schema:")
    for row in result:
        print(f"   {row[0]}: {row[1]}")
    print()
    
    # Get the actual metadata
    metadata = conn.execute("SELECT * FROM sync_metadata").fetchall()
    print(f"📊 Sync Metadata Records: {len(metadata)}")
    
    for row in metadata:
        print(f"\n🔄 Sync Record:")
        print(f"   ID: {row[0]}")
        print(f"   Last Sync Timestamp: {row[1]}")
        print(f"   Last Wavelog Modified: {row[2]}")
        print(f"   Last Wavelog ID: {row[3]}")
        print(f"   Total Records Synced: {row[4]}")
        print(f"   Last Sync Added: {row[5]}")
        print(f"   Last Sync Updated: {row[6]}")
    
    # Actual count in qso_records
    actual_count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
    print(f"\n📊 Actual QSO Count: {actual_count}")
    
    # Check for mismatch
    if metadata and metadata[0][4] != actual_count:
        print(f"\n⚠️  MISMATCH: Metadata says {metadata[0][4]} but database has {actual_count} QSOs")
    else:
        print(f"\n✅ Counts match!")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()