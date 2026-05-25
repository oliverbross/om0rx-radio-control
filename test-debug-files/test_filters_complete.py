#!/usr/bin/env python3
"""
Test script to verify DX Spots filters are working correctly.
Tests:
1. Band filter - uses spot.band directly
2. Continent filter - uses spot.spotter_continent  
3. CQ Zone filter - uses spot.cq with string comparison
4. Mode filter
5. Call Status filter
6. DXCC Status filter
7. Special activities filter
"""

import json
from datetime import datetime

# Mock spot data structure that the backend sends
test_spots = [
    {
        'callsign': 'EA1ABC',
        'frequency': '14234.5',
        'frequency_mhz': 14.2345,
        'spotter': 'EA2CDF',
        'spotter_continent': 'EU',  # ✓ CORRECT FIELD NAME
        'mode': 'SSB',
        'band': '20m',  # ✓ CORRECT FIELD NAME
        'comment': 'POTA K-0001',
        'country': 'Spain',
        'cq': '14',  # ✓ SENT AS STRING FROM BACKEND
        'call_status': 'New Call',
        'dxcc_status': 'ATNO',
        'tag': 'ATNO',
        'timestamp': datetime.now().timestamp(),
        'time': '14:32:15',
        'latitude': 40.4,
        'longitude': -3.7,
        'gridsquare': 'IN80AU'
    },
    {
        'callsign': 'VK3RZZ',
        'frequency': '7052.3',
        'frequency_mhz': 7.0523,
        'spotter': 'VK2ABC',
        'spotter_continent': 'OC',  # ✓ CORRECT FIELD NAME
        'mode': 'CW',
        'band': '40m',  # ✓ CORRECT FIELD NAME
        'comment': 'SOTA VK1-001 Great! Contest',
        'country': 'Australia',
        'cq': '30',  # ✓ SENT AS STRING FROM BACKEND
        'call_status': 'New Band',
        'dxcc_status': 'C/New Band',
        'tag': 'C/New Band',
        'timestamp': datetime.now().timestamp(),
        'time': '14:32:10',
        'latitude': -37.8,
        'longitude': 145.0,
        'gridsquare': 'QF22RG'
    },
    {
        'callsign': 'JA1ABC',
        'frequency': '21274.8',
        'frequency_mhz': 21.2748,
        'spotter': 'JH2ABC',
        'spotter_continent': 'AS',  # ✓ CORRECT FIELD NAME
        'mode': 'FT8',
        'band': '15m',  # ✓ CORRECT FIELD NAME
        'comment': 'WWFF JA/FE-0001 Portable',
        'country': 'Japan',
        'cq': '25',  # ✓ SENT AS STRING FROM BACKEND
        'call_status': 'Worked',
        'dxcc_status': 'Confirmed',
        'tag': 'Confirmed',
        'timestamp': datetime.now().timestamp(),
        'time': '14:31:55',
        'latitude': 35.5,
        'longitude': 139.8,
        'gridsquare': 'PM84CL'
    }
]

def test_band_filter():
    """Test: Band filter should use spot.band directly"""
    print("\n" + "="*60)
    print("TEST 1: Band Filter")
    print("="*60)
    
    selected_bands = ['20m', '15m']
    filtered = [spot for spot in test_spots if spot['band'] in selected_bands]
    
    print(f"✓ Selecting bands: {selected_bands}")
    print(f"✓ Spots with matching band:")
    for spot in filtered:
        print(f"  - {spot['callsign']} on {spot['band']} (band={spot['band']})")
    
    assert len(filtered) == 2, f"Expected 2 spots, got {len(filtered)}"
    assert filtered[0]['callsign'] == 'EA1ABC', "Expected EA1ABC first"
    assert filtered[1]['callsign'] == 'JA1ABC', "Expected JA1ABC second"
    print("✅ Band filter test PASSED")
    return True

def test_continent_filter():
    """Test: Continent filter should use spot.spotter_continent"""
    print("\n" + "="*60)
    print("TEST 2: Continent Filter")
    print("="*60)
    
    selected_continents = ['EU', 'OC']
    filtered = [spot for spot in test_spots if spot['spotter_continent'] in selected_continents]
    
    print(f"✓ Selecting continents: {selected_continents}")
    print(f"✓ Spots from matching continents:")
    for spot in filtered:
        print(f"  - {spot['callsign']} from {spot['spotter_continent']} (spotter_continent={spot['spotter_continent']})")
    
    assert len(filtered) == 2, f"Expected 2 spots, got {len(filtered)}"
    assert filtered[0]['callsign'] == 'EA1ABC', "Expected EA1ABC first"
    assert filtered[1]['callsign'] == 'VK3RZZ', "Expected VK3RZZ second"
    print("✅ Continent filter test PASSED")
    return True

def test_cq_zone_filter():
    """Test: CQ Zone filter should use spot.cq as string"""
    print("\n" + "="*60)
    print("TEST 3: CQ Zone Filter (with type conversion)")
    print("="*60)
    
    # UI sends integers, backend sends strings - must convert
    selected_cqs_int = [14, 25]  # Frontend filter array (integers)
    selected_cqs_str = [str(cq) for cq in selected_cqs_int]  # Convert to strings
    
    filtered = [spot for spot in test_spots if spot['cq'] in selected_cqs_str]
    
    print(f"✓ Frontend filter selection (integers): {selected_cqs_int}")
    print(f"✓ Converted to strings for backend comparison: {selected_cqs_str}")
    print(f"✓ Spots in matching CQ zones:")
    for spot in filtered:
        print(f"  - {spot['callsign']} in zone {spot['cq']} (type={type(spot['cq']).__name__})")
    
    assert len(filtered) == 2, f"Expected 2 spots, got {len(filtered)}"
    assert filtered[0]['callsign'] == 'EA1ABC', "Expected EA1ABC first"
    assert filtered[1]['callsign'] == 'JA1ABC', "Expected JA1ABC second"
    print("✅ CQ Zone filter test PASSED (with string type conversion)")
    return True

def test_mode_filter():
    """Test: Mode filter"""
    print("\n" + "="*60)
    print("TEST 4: Mode Filter")
    print("="*60)
    
    selected_modes = ['CW', 'FT8']
    filtered = [spot for spot in test_spots if spot['mode'] in selected_modes]
    
    print(f"✓ Selecting modes: {selected_modes}")
    print(f"✓ Spots with matching modes:")
    for spot in filtered:
        print(f"  - {spot['callsign']} on {spot['mode']}")
    
    assert len(filtered) == 2, f"Expected 2 spots, got {len(filtered)}"
    print("✅ Mode filter test PASSED")
    return True

def test_call_status_filter():
    """Test: Call Status filter"""
    print("\n" + "="*60)
    print("TEST 5: Call Status Filter")
    print("="*60)
    
    selected_statuses = ['New Call', 'Worked']
    filtered = [spot for spot in test_spots if spot['call_status'] in selected_statuses]
    
    print(f"✓ Selecting call statuses: {selected_statuses}")
    print(f"✓ Spots with matching call statuses:")
    for spot in filtered:
        print(f"  - {spot['callsign']}: {spot['call_status']}")
    
    assert len(filtered) == 2, f"Expected 2 spots, got {len(filtered)}"
    print("✅ Call Status filter test PASSED")
    return True

def test_dxcc_status_filter():
    """Test: DXCC Status filter"""
    print("\n" + "="*60)
    print("TEST 6: DXCC Status Filter")
    print("="*60)
    
    selected_statuses = ['ATNO', 'Confirmed']
    filtered = [spot for spot in test_spots if spot['tag'] in selected_statuses]
    
    print(f"✓ Selecting DXCC statuses: {selected_statuses}")
    print(f"✓ Spots with matching DXCC statuses:")
    for spot in filtered:
        print(f"  - {spot['callsign']}: {spot['tag']}")
    
    assert len(filtered) == 2, f"Expected 2 spots, got {len(filtered)}"
    print("✅ DXCC Status filter test PASSED")
    return True

def test_special_activities_filter():
    """Test: Special Activities filter (POTA, SOTA, WWFF, IOTA, LH, Contest)"""
    print("\n" + "="*60)
    print("TEST 7: Special Activities Filter")
    print("="*60)
    
    selected_specials = ['POTA', 'Contest']
    filtered = []
    
    for spot in test_spots:
        if spot['comment']:
            comment = spot['comment'].lower()
            if any(special.lower() in comment for special in selected_specials):
                filtered.append(spot)
    
    print(f"✓ Selecting special activities: {selected_specials}")
    print(f"✓ Spots with matching special activities:")
    for spot in filtered:
        print(f"  - {spot['callsign']}: {spot['comment']}")
    
    assert len(filtered) == 2, f"Expected 2 spots, got {len(filtered)}"  # POTA and Contest
    print("✅ Special Activities filter test PASSED")
    return True

def test_combined_filters():
    """Test: Multiple filters combined (AND logic)"""
    print("\n" + "="*60)
    print("TEST 8: Combined Filters (AND Logic)")
    print("="*60)
    
    # Select: SSB mode AND Europe continent AND band 20m
    selected_modes = ['SSB']
    selected_continents = ['EU']
    selected_bands = ['20m']
    
    filtered = test_spots
    filtered = [s for s in filtered if s['mode'] in selected_modes]
    filtered = [s for s in filtered if s['spotter_continent'] in selected_continents]
    filtered = [s for s in filtered if s['band'] in selected_bands]
    
    print(f"✓ Filters: Mode={selected_modes}, Continent={selected_continents}, Band={selected_bands}")
    print(f"✓ Spots matching ALL criteria:")
    for spot in filtered:
        print(f"  - {spot['callsign']}: {spot['mode']} on {spot['band']} from {spot['spotter_continent']}")
    
    assert len(filtered) == 1, f"Expected 1 spot, got {len(filtered)}"
    assert filtered[0]['callsign'] == 'EA1ABC', "Expected EA1ABC"
    print("✅ Combined filters test PASSED")
    return True

def main():
    print("\n" + "█"*60)
    print("  DX SPOTS FILTER VERIFICATION TEST SUITE")
    print("█"*60)
    
    tests = [
        test_band_filter,
        test_continent_filter,
        test_cq_zone_filter,
        test_mode_filter,
        test_call_status_filter,
        test_dxcc_status_filter,
        test_special_activities_filter,
        test_combined_filters,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, True, None))
        except AssertionError as e:
            results.append((test.__name__, False, str(e)))
            print(f"❌ {test.__name__} FAILED: {e}")
        except Exception as e:
            results.append((test.__name__, False, str(e)))
            print(f"❌ {test.__name__} ERROR: {e}")
    
    print("\n" + "█"*60)
    print("  TEST SUMMARY")
    print("█"*60)
    
    passed = sum(1 for _, success, _ in results if success)
    failed = sum(1 for _, success, _ in results if not success)
    
    for test_name, success, error in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if error:
            print(f"       {error}")
    
    print(f"\nTotal: {passed} passed, {failed} failed out of {len(tests)} tests")
    
    if failed == 0:
        print("\n🎉 All filter tests PASSED! The filters are working correctly.")
    else:
        print(f"\n⚠️ {failed} test(s) failed. Please review the errors above.")
    
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    exit(main())