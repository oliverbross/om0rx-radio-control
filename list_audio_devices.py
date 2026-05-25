"""List available audio devices"""
import sounddevice as sd

devices = sd.query_devices()
print("=== Available Audio Devices ===\n")

for i, device in enumerate(devices):
    name = device['name']
    max_in = device['max_input_channels']
    max_out = device['max_output_channels']
    
    # Highlight FlexRadio/DAX devices
    if 'DAX' in name or 'Flex' in name or 'FlexRadio' in name:
        print(f"🎵 {i}: {name}")
        print(f"   Input channels: {max_in}, Output channels: {max_out}")
        print()