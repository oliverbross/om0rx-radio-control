"""Read-only loopback xCat telemetry latency probe; never sends radio writes."""

import json
import socket
import time


def main():
    for _ in range(5):
        started = time.monotonic()
        with socket.create_connection(("127.0.0.1", 14532), timeout=3) as connection:
            connection.sendall(b"\\get_xcat_state\n")
            response = bytearray()
            while b"\n" not in response:
                chunk = connection.recv(16384)
                if not chunk:
                    raise RuntimeError("xCat closed before returning a snapshot")
                response.extend(chunk)
                if len(response) > 262144:
                    raise RuntimeError("Oversized xCat snapshot")
        snapshot = json.loads(response.split(b"\n", 1)[0])
        print(json.dumps({
            "read_ms": round((time.monotonic() - started) * 1000, 1),
            "available": snapshot.get("available"),
            "radio": snapshot.get("radio"),
            "route_alignment": snapshot.get("station", {}).get("routeAlignment"),
        }))
        time.sleep(0.1)


if __name__ == "__main__":
    main()
