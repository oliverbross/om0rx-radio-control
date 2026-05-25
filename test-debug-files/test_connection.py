#!/usr/bin/env python3
"""Test backend connection"""

import socket
import sys

def test_connection():
    """Test if we can connect and what we get"""
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        
        # Try to connect
        result = sock.connect_ex(('127.0.0.1', 8000))
        
        if result == 0:
            print("✅ Connection successful to localhost:8000")
            
            # Send HTTP request
            request = b"GET / HTTP/1.1\r\nHost: localhost:8000\r\nConnection: close\r\n\r\n"
            sock.sendall(request)
            
            # Receive response
            response = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                except socket.timeout:
                    break
            
            # Parse response
            response_str = response.decode('utf-8', errors='ignore')
            lines = response_str.split('\r\n')
            
            print(f"\n📡 Response Status: {lines[0] if lines else 'No response'}")
            
            # Show first few headers
            print("\n📋 Response Headers:")
            for i, line in enumerate(lines[1:20]):
                if not line:
                    break
                print(f"   {line}")
            
            # Show body preview
            if len(response_str) > 200:
                body_start = response_str.find('\r\n\r\n') + 4
                body_preview = response_str[body_start:body_start+300]
                print(f"\n📄 Body preview:\n{body_preview}...")
            
        else:
            print("❌ Connection failed to localhost:8000")
            
        sock.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_connection()