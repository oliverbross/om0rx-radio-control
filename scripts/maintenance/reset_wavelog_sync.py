"""
Reset Wavelog→DuckDB Sync
Clears sync metadata and optionally all synced data to force a fresh initial sync
"""

import _bootstrap  # noqa: F401
from radio_control.wavelog_duckdb_sync import get_wavelog_sync
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Reset the Wavelog sync"""
    print("\n" + "="*60)
    print("Wavelog→DuckDB Sync Reset Tool")
    print("="*60 + "\n")
    
    # Ask user if they want to clear data too
    print("This will reset the sync metadata to force a fresh initial sync.")
    print("\nOptions:")
    print("  1. Reset metadata only (keeps existing synced data)")
    print("  2. Reset metadata AND clear all synced data (fresh start)")
    print("  3. Cancel")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "3":
        print("\n❌ Cancelled by user")
        return
    
    clear_data = (choice == "2")
    
    if clear_data:
        confirm = input("\n⚠️  WARNING: This will delete all synced QSOs from DuckDB!\n"
                       "Type 'YES' to confirm: ").strip()
        if confirm != "YES":
            print("\n❌ Cancelled - confirmation not received")
            return
    
    print("\n🔄 Resetting sync...")
    
    try:
        # Get sync manager
        sync_manager = get_wavelog_sync()
        
        # Reset sync
        result = sync_manager.reset_sync(clear_data=clear_data)
        
        if result.get('success'):
            print(f"\n✅ {result['message']}")
            if result['data_cleared']:
                print("   All synced QSO data has been cleared")
            print("\n📋 Next steps:")
            print("   1. The sync will automatically restart on next cycle (60 seconds)")
            print("   2. Or restart the backend to trigger immediate sync")
            print(f"\n   The initial sync will process records in batches of 1000")
            print(f"   Watch the logs for progress updates")
        else:
            print(f"\n❌ Reset failed: {result.get('error', 'Unknown error')}")
            return 1
            
    except Exception as e:
        logger.error(f"Error resetting sync: {e}", exc_info=True)
        print(f"\n❌ Error: {str(e)}")
        return 1
    
    print("\n" + "="*60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
