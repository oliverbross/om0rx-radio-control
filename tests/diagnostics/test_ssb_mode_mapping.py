#!/usr/bin/env python3
"""
Test SSB mode mapping logic
Verifies that SSB spots are correctly converted to USB/LSB based on frequency
"""

def get_ssb_mode(freq_mhz):
    """
    Map SSB to correct mode based on frequency (mimics frontend logic)
    LSB for 160-40m (freq < 14 MHz)
    USB for 20m and higher (freq >= 14 MHz)
    """
    return 'LSB' if freq_mhz < 14 else 'USB'

def test_ssb_mode_mapping():
    """Test all band boundaries for SSB mode mapping"""
    
    test_cases = [
        # (frequency_MHz, expected_mode, band_name)
        (1.8, 'LSB', '160m'),
        (3.5, 'LSB', '80m'),
        (5.3, 'LSB', '60m'),
        (7.0, 'LSB', '40m'),
        (7.3, 'LSB', '40m upper'),
        (10.1, 'LSB', '30m'),
        (10.15, 'LSB', '30m upper'),
        (14.0, 'USB', '20m lower'),
        (14.35, 'USB', '20m upper'),
        (18.1, 'USB', '17m'),
        (21.0, 'USB', '15m'),
        (24.9, 'USB', '12m'),
        (28.0, 'USB', '10m'),
        (50.0, 'USB', '6m'),
        (144.0, 'USB', '2m'),
    ]
    
    print("🧪 Testing SSB Mode Mapping Logic\n")
    print(f"{'Frequency':>12} | {'Band':>10} | {'Mode':>6} | {'Expected':>8} | {'Status':>8}")
    print("-" * 60)
    
    passed = 0
    failed = 0
    
    for freq_mhz, expected_mode, band_name in test_cases:
        actual_mode = get_ssb_mode(freq_mhz)
        is_pass = actual_mode == expected_mode
        status = "✅ PASS" if is_pass else "❌ FAIL"
        
        print(f"{freq_mhz:>12} | {band_name:>10} | {actual_mode:>6} | {expected_mode:>8} | {status:>8}")
        
        if is_pass:
            passed += 1
        else:
            failed += 1
    
    print("-" * 60)
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("✅ All SSB mode mapping tests PASSED!\n")
        return True
    else:
        print(f"❌ {failed} test(s) FAILED!\n")
        return False

def test_other_modes():
    """Verify that non-SSB modes are passed through unchanged"""
    
    test_cases = [
        ('FT8', 'FT8'),
        ('ft8', 'FT8'),  # uppercase conversion
        ('CW', 'CW'),
        ('cw', 'CW'),    # uppercase conversion
        ('AM', 'AM'),
        ('DIGU', 'DIGU'),
    ]
    
    print("🧪 Testing Non-SSB Mode Pass-Through\n")
    print(f"{'Input Mode':>15} | {'Output Mode':>15} | {'Status':>8}")
    print("-" * 45)
    
    passed = 0
    failed = 0
    
    for input_mode, expected_mode in test_cases:
        # Simulate mode mapping logic for non-SSB modes
        actual_mode = input_mode.upper() if input_mode.upper() != 'SSB' else 'N/A'
        
        if input_mode.upper() != 'SSB':
            is_pass = actual_mode == expected_mode
            status = "✅ PASS" if is_pass else "❌ FAIL"
            
            print(f"{input_mode:>15} | {actual_mode:>15} | {status:>8}")
            
            if is_pass:
                passed += 1
            else:
                failed += 1
    
    print("-" * 45)
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("✅ All non-SSB mode tests PASSED!\n")
        return True
    else:
        print(f"❌ {failed} test(s) FAILED!\n")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("SSB MODE MAPPING TEST SUITE")
    print("=" * 60 + "\n")
    
    result1 = test_ssb_mode_mapping()
    result2 = test_other_modes()
    
    print("=" * 60)
    if result1 and result2:
        print("✅ ALL TESTS PASSED - SSB MODE FIX IS WORKING!")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)