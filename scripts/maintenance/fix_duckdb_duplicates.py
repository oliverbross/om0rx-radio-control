"""
Fix DuckDB Duplicates - Remove duplicate QSO records
This script identifies and removes duplicate QSO records from the DuckDB database.

Duplicates are identified by the combination of (call, qso_date, time_on).
For each duplicate group, we keep the first record (lowest ID) and delete the rest.
"""

import duckdb
from pathlib import Path
import _bootstrap  # noqa: F401
from radio_control import config

# Paths
DB_PATH = config.DATA_DIR / 'qso_log.duckdb'

def fix_duplicates():
    """Remove duplicate QSO records from the database"""
    
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return False
    
    try:
        print(f"\n{'='*80}")
        print("🔧 DuckDB Duplicate Removal Tool")
        print(f"{'='*80}\n")
        
        # Connect to database
        conn = duckdb.connect(DB_PATH)
        print(f"✅ Connected to database: {DB_PATH}")
        
        # Step 1: Get statistics on duplicates
        print("\n📊 Analyzing duplicates...")
        
        # Find all duplicate groups
        duplicates_query = """
        SELECT 
            call, qso_date, time_on, COUNT(*) as count, 
            MIN(id) as min_id, MAX(id) as max_id
        FROM qso_records
        WHERE call IS NOT NULL
        GROUP BY call, qso_date, time_on
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        """
        
        duplicates = conn.execute(duplicates_query).fetchall()
        
        if not duplicates:
            print("✅ No duplicates found in database!")
            conn.close()
            return True
        
        print(f"\n⚠️  Found {len(duplicates)} duplicate groups:")
        print(f"   Total duplicate records to remove: {sum(d[2] - 1 for d in duplicates if isinstance(d[2], int))}")
        
        total_dupes = 0
        for i, (call, qso_date, time_on, count, min_id, max_id) in enumerate(duplicates[:10], 1):
            print(f"   {i}. {call:12} | {qso_date} {time_on:6} | {count} copies (IDs: {min_id}-{max_id})")
            total_dupes += (count - 1)
        
        if len(duplicates) > 10:
            print(f"   ... and {len(duplicates) - 10} more duplicate groups")
            # Recalculate total for all groups
            total_dupes = 0
            for call, qso_date, time_on, count, min_id, max_id in duplicates:
                total_dupes += (count - 1)
        
        print(f"\n   Total records to remove: {total_dupes}")
        
        # Step 2: Get baseline record count
        before_count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
        print(f"\n📈 Current total records: {before_count:,}")
        
        # Step 3: Remove duplicates
        print("\n🔄 Removing duplicates...")
        
        # Strategy: For each duplicate group, keep the record with the lowest ID
        # and delete all others
        delete_query = """
        DELETE FROM qso_records
        WHERE id NOT IN (
            SELECT MIN(id) as keep_id
            FROM qso_records
            WHERE call IS NOT NULL
            GROUP BY call, qso_date, time_on
        )
        AND call IS NOT NULL
        """
        
        conn.execute(delete_query)
        conn.commit()
        
        # Step 4: Verify removal
        after_count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
        removed_count = before_count - after_count
        
        print("✅ Duplicates removed successfully!")
        print("\n📊 Summary:")
        print(f"   Before: {before_count:,} records")
        print(f"   After:  {after_count:,} records")
        print(f"   Removed: {removed_count:,} duplicate records")
        
        # Step 5: Verify no more duplicates
        print("\n🔍 Verifying no duplicates remain...")
        remaining_dupes = conn.execute("""
            SELECT COUNT(DISTINCT call) as groups_with_dupes
            FROM (
                SELECT call, qso_date, time_on, COUNT(*) as count
                FROM qso_records
                WHERE call IS NOT NULL
                GROUP BY call, qso_date, time_on
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        
        if remaining_dupes == 0:
            print("✅ Verification passed! No duplicates remain.")
        else:
            print(f"⚠️  Warning: {remaining_dupes} duplicate groups still exist!")
            conn.close()
            return False
        
        # Step 6: Get updated unique callsigns
        unique_calls = conn.execute("SELECT COUNT(DISTINCT call) FROM qso_records").fetchone()[0]
        print("\n📋 Database statistics:")
        print(f"   Total QSOs: {after_count:,}")
        print(f"   Unique callsigns: {unique_calls:,}")
        
        # Close connection
        conn.close()
        
        print("\n✅ All done! Database cleaned successfully.")
        print(f"{'='*80}\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    
    success = fix_duplicates()
    sys.exit(0 if success else 1)
