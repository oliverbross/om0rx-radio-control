"""Bounded, read-only FLEX GUI client discovery for the Windows settings UI."""

from __future__ import annotations

import argparse
import json
import socket
import time


def discover_stations(host: str, port: int, *, timeout: float = 2.5) -> list[dict[str, str]]:
    """Subscribe on a temporary socket without binding or changing radio state."""
    clients: dict[str, dict[str, str]] = {}
    deadline = time.monotonic() + timeout
    buffer = b""
    received = 0
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.sendall(b"C1|sub client all\n")
        while time.monotonic() < deadline:
            connection.settimeout(max(0.01, deadline - time.monotonic()))
            try:
                chunk = connection.recv(8192)
            except TimeoutError:
                break
            if not chunk:
                break
            received += len(chunk)
            if received > 262144:
                raise ValueError("FLEX discovery response exceeded its size limit")
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("R1|") and int(line.split("|", 2)[1], 16) != 0:
                    raise ValueError("FLEX rejected client discovery")
                if not line.startswith("S") or "|" not in line:
                    continue
                fields = line.split("|", 1)[1].split()
                if len(fields) < 3 or fields[0] not in {"client", "gui_client"}:
                    continue
                handle = fields[1]
                if "disconnected" in fields:
                    clients.pop(handle, None)
                    continue
                values = dict(field.split("=", 1) for field in fields[2:] if "=" in field)
                station = values.get("station", "").replace("\x7f", " ").strip()
                if station and values.get("client_id"):
                    clients[handle] = {
                        "station_name": station,
                        "program": values.get("program", "").replace("\x7f", " "),
                        "handle": handle,
                    }
    return sorted(
        clients.values(), key=lambda item: (item["station_name"].casefold(), item["handle"])
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=4992)
    args = parser.parse_args()
    try:
        stations = discover_stations(args.host, args.port)
    except (OSError, ValueError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        return 1
    print(json.dumps({"success": True, "stations": stations}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
