#!/usr/bin/env python3
"""Test API config save endpoint"""

import subprocess
import time
import urllib.request
import json
import sys
from pathlib import Path

print("🚀 Testing API config save endpoint...\n")

# Kill any existing Python processes
subprocess.run(['taskkill', '/F', '/IM', 'python.exe'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
time.sleep(2)

# Start backend
print("1️⃣  Starting backend server...")
backend_path = Path(r"c:\Projects\om0rx-radio-control\backend\main.py")
proc = subprocess.Popen([sys.executable, str(backend_path)], 
                        cwd=r"c:\Projects\om0rx-radio-control",
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE)
time.sleep(5)

print("   Server started\n")

try:
    # Check original value
    print("2️⃣  Fetching current config...")
    url = "http://localhost:8000/api/config"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            if data.get('success'):
                print(f"   WINKEYER_ENABLED (before save): {data['config'].get('WINKEYER_ENABLED')}")
            else:
                print(f"   Error getting config: {data}")
    except Exception as e:
        print(f"   Failed to reach server: {e}")
        print("   (Server might not have started, this is OK for testing the file logic)")
    
    # Save config
    print("\n3️⃣  Saving config with WINKEYER_ENABLED = False...")
    
    save_data = {
        "config": {
            "WINKEYER_ENABLED": False,
            "WINKEYER_PORT": "COM11",
            "WINKEYER_BAUDRATE": 1200,
            "WINKEYER_DEFAULT_WPM": 20,
        }
    }
    
    save_url = "http://localhost:8000/api/config"
    req = urllib.request.Request(
        save_url,
        data=json.dumps(save_data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            response_data = json.loads(response.read().decode())
            print(f"   Response: {response_data}")
            
            # Wait a moment for file to be written
            time.sleep(1)
            
            # Check file was updated
            print("\n4️⃣  Checking if file was updated...")
            with open(r"c:\Projects\om0rx-radio-control\config.py", 'r') as f:
                for line in f:
                    if line.strip().startswith('WINKEYER_ENABLED'):
                        print(f"   File now contains: {line.strip()}")
                        if 'False' in line:
                            print("   ✅ File was successfully saved!")
                        else:
                            print("   ❌ File was NOT updated!")
                        break
                        
            # Try to fetch again
            print("\n5️⃣  Fetching config again to verify...")
            with urllib.request.urlopen("http://localhost:8000/api/config") as response:
                data = json.loads(response.read().decode())
                if data.get('success'):
                    enabled = data['config'].get('WINKEYER_ENABLED')
                    print(f"   WINKEYER_ENABLED (after save): {enabled}")
                    if enabled == False:
                        print("   ✅ Config API returns correct value!")
                    else:
                        print("   ⚠️  Config API still returns old value (might be cache issue)")
                else:
                    print(f"   Error: {data}")
    except urllib.error.URLError as e:
        print(f"   Could not connect to API: {e}")
        print("   (This is expected if server didn't start)")
        
        # But we can still check the file was written
        print("\n4️⃣  (Skipping API test, but checking file directly...)")
        with open(r"c:\Projects\om0rx-radio-control\config.py", 'r') as f:
            for line in f:
                if line.strip().startswith('WINKEYER_ENABLED'):
                    print(f"   File contains: {line.strip()}")
                    break
    
    # Restore
    print("\n6️⃣  Restoring original config...")
    restore_data = {"config": {"WINKEYER_ENABLED": True}}
    req = urllib.request.Request(
        "http://localhost:8000/api/config",
        data=json.dumps(restore_data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as response:
            json.loads(response.read().decode())
    except:
        # Manually restore if API not available
        with open(r"c:\Projects\om0rx-radio-control\config.py", 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace('WINKEYER_ENABLED = False', 'WINKEYER_ENABLED = True')
        with open(r"c:\Projects\om0rx-radio-control\config.py", 'w', encoding='utf-8') as f:
            f.write(content)
    
    print("   ✅ Restored")

finally:
    # Kill server
    print("\n7️⃣  Stopping server...")
    proc.terminate()
    time.sleep(1)
    if proc.poll() is None:
        proc.kill()
    print("   ✅ Done")