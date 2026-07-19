"""Live diagnostic for Wavelog log service database retrieval."""

import sys
import _bootstrap  # noqa: F401
from services.wavelog_log import get_wavelog_log_service

def test_log_service():
    """Test the Wavelog Log Service"""
    print("🧪 Testing Wavelog Log Service...\n")
    
    try:
        # Get service instance
        service = get_wavelog_log_service()
        print("✅ Service instance created\n")
        
        # Test 1: Get log statistics
        print("📊 Test 1: Getting log statistics...")
        stats = service.get_log_stats()
        print("✅ Statistics retrieved:")
        print(f"   - Total QSOs: {stats['total_qsos']}")
        print(f"   - Unique DXCC: {stats['unique_dxcc']}")
        print(f"   - Unique Calls: {stats['unique_calls']}")
        print(f"   - First QSO: {stats['first_qso']}")
        print(f"   - Last QSO: {stats['last_qso']}\n")
        
        # Test 2: Get log entries (limit 10)
        print("📋 Test 2: Getting 10 most recent log entries...")
        entries = service.get_log_entries(limit=10)
        print(f"✅ Retrieved {len(entries)} entries\n")
        
        if entries:
            print("📝 Sample entry (most recent):")
            entry = entries[0]
            print(f"   - Callsign: {entry['callsign']}")
            print(f"   - Time: {entry['time_on']}")
            print(f"   - Band: {entry['band']}")
            print(f"   - Mode: {entry['mode']}")
            print(f"   - Frequency: {entry['frequency']:.3f} MHz")
            print(f"   - RST Sent: {entry['rst_sent']}")
            print(f"   - RST Rcvd: {entry['rst_rcvd']}")
            print(f"   - Country: {entry['country']}")
            
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = test_log_service()
    sys.exit(0 if success else 1)
