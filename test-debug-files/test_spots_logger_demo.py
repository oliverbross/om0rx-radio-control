#!/usr/bin/env python3
"""
Demo script for DX Spots Logger
Shows how to query and work with the spots database
"""

from datetime import datetime, UTC, date, timedelta
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from spots_logger import get_spots_logger, SpotsLogger


def demo_logging():
    """Demo: Create some sample data"""
    print("\n" + "="*60)
    print("DEMO: Logging Sample Spots")
    print("="*60)
    
    logger = get_spots_logger()
    
    # Sample spots data to log
    sample_spots = [
        {
            'spotter': 'N0ZZZ',
            'freq_khz': 14277.5,
            'freq_khz_str': '14277.5',
            'dxcall': 'JA1ABC',
            'comment': 'FT8 POTA K-1234',
            'timestamp': datetime.now(UTC)
        },
        {
            'spotter': 'DL1XYZ',
            'freq_khz': 7074.0,
            'freq_khz_str': '7074.0',
            'dxcall': 'ZL2ABC',
            'comment': 'FT8',
            'timestamp': datetime.now(UTC)
        },
        {
            'spotter': 'G3XYZ',
            'freq_khz': 21074.0,
            'freq_khz_str': '21074.0',
            'dxcall': 'CE3XYZ',
            'comment': 'FT8 SOTA S-123',
            'timestamp': datetime.now(UTC)
        },
        {
            'spotter': 'KN7ZZZ',
            'freq_khz': 3573.0,
            'freq_khz_str': '3573.0',
            'dxcall': 'W1AW',
            'comment': 'FT8',
            'timestamp': datetime.now(UTC)
        },
    ]
    
    logged_count = 0
    for spot in sample_spots:
        if logger.log_spot(spot):
            logged_count += 1
    
    print(f"✅ Logged {logged_count} sample spots")


def demo_queries():
    """Demo: Query the database"""
    print("\n" + "="*60)
    print("DEMO: Database Queries")
    print("="*60)
    
    logger = get_spots_logger()
    
    # Total count
    total = logger.get_spot_count()
    print(f"\n📊 Total spots in database: {total}")
    
    # Band statistics
    print("\n🎯 Spots by Band:")
    band_stats = logger.get_stats_by_band()
    for stat in band_stats:
        print(f"  {stat['band']:6s}: {stat['total_spots']:4d} spots, "
              f"{stat['unique_callsigns']:3d} calls, "
              f"{stat['countries']:3d} countries")
    
    # Mode statistics
    print("\n📡 Spots by Mode:")
    mode_stats = logger.get_stats_by_mode()
    for stat in mode_stats:
        print(f"  {stat['mode']:8s}: {stat['total_spots']:4d} spots, "
              f"{stat['unique_callsigns']:3d} calls")
    
    # Country statistics
    print("\n🌍 Top Countries:")
    country_stats = logger.get_stats_by_country(limit=10)
    for stat in country_stats:
        country = stat['country'] or 'Unknown'
        print(f"  {country:20s}: {stat['total_spots']:4d} spots, "
              f"{stat['unique_callsigns']:3d} calls")
    
    # Recent spots
    print("\n⏰ Most Recent Spots (last 5):")
    recent = logger.get_recent_spots(limit=5)
    for spot in recent:
        timestamp = spot['received_at']
        print(f"  {timestamp} - {spot['callsign']:8s} on {spot['band']:5s} "
              f"({spot['mode']:6s}) by {spot['spotter']}")
    
    # Special event spots
    print("\n🎉 Special Event Spots:")
    special = logger.get_special_event_spots(limit=5)
    if special:
        for spot in special:
            print(f"  {spot['callsign']:8s}: {spot['special_tags']}")
    else:
        print("  (None found)")


def demo_exports():
    """Demo: Export functionality"""
    print("\n" + "="*60)
    print("DEMO: Export to CSV")
    print("="*60)
    
    logger = get_spots_logger()
    
    export_dir = Path(__file__).parent / "data"
    export_file = export_dir / "spots_demo_export.csv"
    
    count = logger.export_csv(str(export_file))
    print(f"✅ Exported {count} spots to: {export_file}")


def demo_specific_queries():
    """Demo: Specific lookup queries"""
    print("\n" + "="*60)
    print("DEMO: Specific Callsign Queries")
    print("="*60)
    
    logger = get_spots_logger()
    
    # Find all spots for a specific callsign
    callsigns_to_check = ['JA1ABC', 'W1AW', 'ZL2ABC']
    
    for call in callsigns_to_check:
        spots = logger.get_spots_by_callsign(call, limit=5)
        print(f"\n📍 Spots for {call}: {len(spots)} found")
        for spot in spots:
            print(f"    {spot['time_utc']} - {spot['band']:5s} ({spot['mode']:6s}) "
                  f"by {spot['spotter']:10s}")


def main():
    """Run all demos"""
    print("\n" + "🔍 DX SPOTS LOGGER DEMO".center(60, "="))
    print("This demo shows all the capabilities of the spots logging system\n")
    
    # Check if we have data
    logger = get_spots_logger()
    total = logger.get_spot_count()
    
    if total == 0:
        print("⚠️  Database is empty. Logging sample spots first...\n")
        demo_logging()
    
    # Run demos
    demo_queries()
    demo_specific_queries()
    demo_exports()
    
    print("\n" + "="*60)
    print("✅ Demo Complete!")
    print("="*60)
    print("\nAvailable API Endpoints:")
    print("  GET  /api/spots/count                      - Total spot count")
    print("  GET  /api/spots/stats/band                 - Band statistics")
    print("  GET  /api/spots/stats/mode                 - Mode statistics")
    print("  GET  /api/spots/stats/country              - Country statistics")
    print("  GET  /api/spots/recent                     - Recent spots")
    print("  GET  /api/spots/callsign/{callsign}        - Spots for callsign")
    print("  GET  /api/spots/special                    - Special event spots")
    print("  POST /api/spots/export/csv                 - Export to CSV")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()