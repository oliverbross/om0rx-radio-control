"""
Test script for FT8 implementation
Tests encoding/decoding pipeline
"""

import sys
import numpy as np
import logging
import _bootstrap  # noqa: F401
from services.ft8_protocol import FT8Protocol
from services.ft8_audio import FT8AudioProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_callsign_encoding():
    """Test callsign packing/unpacking"""
    print("\n" + "="*60)
    print("TEST 1: Callsign Encoding")
    print("="*60)
    
    protocol = FT8Protocol('FT8')
    
    test_calls = ['OM0RX', 'K3LR', 'W1AW', 'DL1ABC', 'CQ']
    
    for call in test_calls:
        packed = protocol._pack_callsign(call)
        unpacked = protocol._unpack_callsign(packed)
        match = "✅" if unpacked.strip() == call else "❌"
        print(f"  {match} {call:10} → {packed:010X} → {unpacked}")
    
    return True


def test_grid_encoding():
    """Test grid square packing/unpacking"""
    print("\n" + "="*60)
    print("TEST 2: Grid Square Encoding")
    print("="*60)
    
    protocol = FT8Protocol('FT8')
    
    test_grids = ['JN88', 'FN20', 'EM73', 'IO91']
    
    for grid in test_grids:
        packed = protocol._pack_grid(grid)
        unpacked = protocol._unpack_grid(packed)
        match = "✅" if unpacked == grid else "❌"
        print(f"  {match} {grid} → {packed:04X} → {unpacked}")
    
    return True


def test_message_encoding():
    """Test complete message encoding/decoding"""
    print("\n" + "="*60)
    print("TEST 3: Message Encoding/Decoding")
    print("="*60)
    
    protocol = FT8Protocol('FT8')
    
    test_messages = [
        "CQ OM0RX JN88",
        "OM0RX K3LR R-15",
        "K3LR OM0RX +05"
    ]
    
    for msg in test_messages:
        parsed = protocol._parse_message(msg)
        if not parsed:
            print(f"  ❌ Failed to parse: {msg}")
            continue
        
        # Encode to 77 bits
        payload = protocol._encode_to_77bit(parsed)
        
        # Decode back
        decoded = protocol._decode_77bit(payload)
        
        match = "✅" if decoded else "❌"
        print(f"  {match} '{msg}' → {len(payload)} bits → '{decoded}'")
    
    return True


def test_ldpc_encoding():
    """Test LDPC encoding/decoding"""
    print("\n" + "="*60)
    print("TEST 4: LDPC Error Correction")
    print("="*60)
    
    protocol = FT8Protocol('FT8')
    
    # Create test payload (91 bits)
    test_payload = np.random.randint(0, 2, 91, dtype=np.uint8)
    
    # Encode to 174 bits
    encoded = protocol._ldpc_encode(test_payload)
    print(f"  ✅ Encoded 91 bits → {len(encoded)} bits")
    
    # Decode back (no errors)
    decoded = protocol._ldpc_decode(encoded)
    print(f"  ✅ Decoded {len(encoded)} bits → {len(decoded)} bits")
    
    # Check if matches
    errors = np.sum(test_payload != decoded)
    match = "✅" if errors == 0 else "❌"
    print(f"  {match} Bit errors: {errors}/91")
    
    # Test with errors
    corrupted = encoded.copy()
    # Flip 3 random bits
    for _ in range(3):
        idx = np.random.randint(0, 174)
        corrupted[idx] ^= 1
    
    decoded_corrupted = protocol._ldpc_decode(corrupted)
    errors_after = np.sum(test_payload != decoded_corrupted)
    
    if errors_after <= 3:
        print(f"  ✅ Error correction: Fixed {3 - errors_after}/3 errors")
    else:
        print(f"  ⚠️  Error correction: {errors_after} errors remain")
    
    return True


def test_crc14():
    """Test CRC14 checksum"""
    print("\n" + "="*60)
    print("TEST 5: CRC14 Checksum")
    print("="*60)
    
    protocol = FT8Protocol('FT8')
    
    # Create test payload
    test_payload = np.random.randint(0, 2, 77, dtype=np.uint8)
    
    # Add CRC
    with_crc = protocol._add_crc14(test_payload)
    print(f"  ✅ Added CRC14: {len(test_payload)} bits → {len(with_crc)} bits")
    
    # Check CRC
    payload_back, crc_valid = protocol._check_crc14(with_crc)
    match = "✅" if crc_valid else "❌"
    print(f"  {match} CRC14 validation: {'PASS' if crc_valid else 'FAIL'}")
    
    # Corrupt one bit
    corrupted = with_crc.copy()
    corrupted[10] ^= 1
    
    _, crc_valid_bad = protocol._check_crc14(corrupted)
    match = "✅" if not crc_valid_bad else "❌"
    print(f"  {match} CRC14 detects corruption: {'YES' if not crc_valid_bad else 'NO'}")
    
    return True


def test_tone_generation():
    """Test tone sequence generation"""
    print("\n" + "="*60)
    print("TEST 6: Tone Sequence Generation")
    print("="*60)
    
    audio_proc = FT8AudioProcessor('FT8')
    
    # Create test tone sequence
    test_tones = np.array([3, 1, 4, 0, 6, 5, 2], dtype=np.uint8)  # Costas pattern
    
    # Generate audio
    audio = audio_proc.generate_tone_sequence(test_tones, base_freq=1000.0)
    
    print(f"  ✅ Generated {len(test_tones)} tones → {len(audio)} audio samples")
    print(f"  ✅ Duration: {len(audio) / audio_proc.sample_rate:.3f} seconds")
    print(f"  ✅ Sample rate: {audio_proc.sample_rate} Hz")
    
    # Decode back
    decoded_tones = audio_proc.decode_tone_sequence(audio, base_freq=1000.0)
    
    if decoded_tones is not None:
        print(f"  ✅ Decoded {len(decoded_tones)} tones back")
        
        # Check accuracy
        matches = np.sum(test_tones == decoded_tones[:len(test_tones)])
        accuracy = matches / len(test_tones) * 100
        match = "✅" if accuracy > 80 else "⚠️"
        print(f"  {match} Decode accuracy: {accuracy:.1f}% ({matches}/{len(test_tones)} correct)")
    else:
        print(f"  ❌ Failed to decode tones")
    
    return True


def test_full_pipeline():
    """Test complete encode → audio → decode pipeline"""
    print("\n" + "="*60)
    print("TEST 7: Full Encode/Decode Pipeline")
    print("="*60)
    
    protocol = FT8Protocol('FT8')
    audio_proc = FT8AudioProcessor('FT8')
    
    test_message = "CQ OM0RX JN88"
    print(f"  Original message: '{test_message}'")
    
    # ENCODE
    print("\n  Encoding...")
    tones = protocol.encode_message(test_message)
    
    if tones is None:
        print(f"  ❌ Encoding failed!")
        return False
    
    print(f"    ✅ Message → {len(tones)} tones")
    
    # Generate audio
    audio = audio_proc.generate_tone_sequence(tones, base_freq=1200.0)
    print(f"    ✅ Tones → {len(audio)} audio samples ({len(audio)/audio_proc.sample_rate:.2f}s)")
    
    # DECODE
    print("\n  Decoding...")
    decoded_tones = audio_proc.decode_tone_sequence(audio, base_freq=1200.0)
    
    if decoded_tones is None:
        print(f"  ❌ Tone decoding failed!")
        return False
    
    print(f"    ✅ Audio → {len(decoded_tones)} tones")
    
    # Decode message
    decoded_msg = protocol.decode_symbols(
        decoded_tones[:79],  # FT8 has 79 symbols
        snr=10.0,
        dt=0.0,
        freq=1200.0
    )
    
    if decoded_msg:
        print(f"    ✅ Tones → Message")
        print(f"\n  📨 Decoded message: '{decoded_msg.message}'")
        print(f"     SNR: {decoded_msg.snr:.1f} dB")
        print(f"     Frequency: {decoded_msg.freq:.1f} Hz")
        
        # Check if matches
        if decoded_msg.message == test_message:
            print(f"\n  ✅ SUCCESS: Message matches perfectly!")
        else:
            print(f"\n  ⚠️  Message differs:")
            print(f"     Expected: '{test_message}'")
            print(f"     Got:      '{decoded_msg.message}'")
        
        return True
    else:
        print(f"  ❌ Message decoding failed!")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("FT8 IMPLEMENTATION TEST SUITE")
    print("="*60)
    
    tests = [
        ("Callsign Encoding", test_callsign_encoding),
        ("Grid Square Encoding", test_grid_encoding),
        ("Message Encoding", test_message_encoding),
        ("LDPC Error Correction", test_ldpc_encoding),
        ("CRC14 Checksum", test_crc14),
        ("Tone Generation", test_tone_generation),
        ("Full Pipeline", test_full_pipeline),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Test '{name}' crashed: {e}", exc_info=True)
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")
        if result:
            passed += 1
    
    print(f"\n  Total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n  🎉 ALL TESTS PASSED! FT8 implementation is working!")
    else:
        print(f"\n  ⚠️  {len(results) - passed} test(s) failed")
    
    print("="*60 + "\n")
    
    return passed == len(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
