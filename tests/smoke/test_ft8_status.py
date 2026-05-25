"""
Quick FT8 Service Status Check
Tests if FT8 service is running and processing audio
"""

import asyncio
import sounddevice as sd
import numpy as np
import _bootstrap  # noqa: F401
from services.ft8_service import FT8Service
from services.ft8_audio import FT8AudioProcessor

async def test_ft8_status():
    print("=" * 60)
    print("FT8 SERVICE STATUS CHECK")
    print("=" * 60)
    
    # 1. Check audio devices
    print("\n1️⃣  AUDIO DEVICES:")
    try:
        devices = sd.query_devices()
        print(f"   ✅ Found {len(devices)} audio devices")
        
        print("\n   📥 INPUT DEVICES:")
        for idx, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                print(f"      {idx}: {device['name']}")
        
        print("\n   📤 OUTPUT DEVICES:")
        for idx, device in enumerate(devices):
            if device['max_output_channels'] > 0:
                print(f"      {idx}: {device['name']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 2. Test FT8 Audio Processor
    print("\n2️⃣  FT8 AUDIO PROCESSOR:")
    try:
        processor = FT8AudioProcessor(sample_rate=12000)
        print(f"   ✅ Created audio processor")
        print(f"   📊 Sample rate: {processor.sample_rate} Hz")
        print(f"   🔊 Buffer size: {len(processor.audio_buffer)} samples")
        
        # Test with dummy audio
        dummy_audio = np.random.randn(12000 * 15).astype(np.float32)  # 15 seconds
        waterfall = processor.generate_waterfall(dummy_audio)
        print(f"   ✅ Waterfall generation works: {len(waterfall)} rows")
        
        # Test signal detection
        signals = processor.detect_ft8_signals_with_sync(dummy_audio[:12000*13])
        print(f"   ✅ Signal detection works: found {len(signals)} signals")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # 3. Test FT8 Service
    print("\n3️⃣  FT8 SERVICE:")
    try:
        service = FT8Service(mode='FT8', mycall='OM0RX', mygrid='JN88')
        print(f"   ✅ Created FT8 service")
        print(f"   📻 Mode: {service.mode}")
        print(f"   📞 Callsign: {service.mycall}")
        print(f"   📍 Grid: {service.mygrid}")
        
        # Check if service can start
        print("\n   🚀 Attempting to start service...")
        await service.start()
        print(f"   ✅ Service started successfully!")
        
        # Wait a bit and check status
        await asyncio.sleep(3)
        stats = service.get_stats()
        print(f"\n   📊 Service Stats:")
        print(f"      Enabled: {stats.get('enabled', False)}")
        print(f"      TX Enabled: {stats.get('tx_enabled', False)}")
        print(f"      Auto Sequence: {stats.get('auto_sequence', False)}")
        print(f"      Is TX Cycle: {stats.get('is_tx_cycle', False)}")
        print(f"      Decoded: {stats.get('decoded_count', 0)}")
        print(f"      Transmitted: {stats.get('transmitted_count', 0)}")
        print(f"      QSOs: {stats.get('qso_completed', 0)}")
        print(f"      Uptime: {stats.get('uptime', 0):.1f}s")
        
        # Check waterfall data
        waterfall = service.get_waterfall_data()
        print(f"      Waterfall: {len(waterfall)} rows")
        
        # Stop service
        print("\n   🛑 Stopping service...")
        await service.stop()
        print(f"   ✅ Service stopped")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("STATUS CHECK COMPLETE")
    print("=" * 60)
    print("\nIf you see errors above, the FT8 service may not be working correctly.")
    print("If everything is ✅, the service is functional but may need:")
    print("  1. Real audio input (not dummy data)")
    print("  2. Actual FT8 signals on the frequency")
    print("  3. Correct audio device selection")
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(test_ft8_status())
