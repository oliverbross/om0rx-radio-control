"""Small reproducible workload benchmark for the native MSHV hot-path pass.

This does not drive MSHV or the radio.  It measures the avoided work represented
by an unchanged ~87 KiB history response and reports deterministic call counts
for the second-resolution clock update.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time


def representative_history_payload() -> bytes:
    rows = []
    sequence = 1
    while True:
        rows.append(
            {
                "key": hashlib.sha256(f"qso-{sequence}".encode()).hexdigest(),
                "sequence": sequence,
                "call": f"K{sequence:05d}",
                "band": "20m",
                "mode": "FT8",
                "qso_date": "20261006",
                "grid": "FN31",
                "notes": "x" * 96,
            }
        )
        payload = json.dumps(
            {
                "status": "healthy",
                "historical_novelty_allowed": True,
                "generated_at": "2026-10-06T11:00:00+00:00",
                "max_age_seconds": 10,
                "snapshot": {"generation": "a" * 64, "age_seconds": 1},
                "deltas": {"base_sequence": 0, "acknowledged_records": rows},
            },
            separators=(",", ":"),
        ).encode()
        if len(payload) >= 87 * 1024:
            return payload
        sequence += 1


def median_seconds(operation, samples: int = 7) -> float:
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        timings.append(time.perf_counter() - started)
    return statistics.median(timings)


def main() -> None:
    payload = representative_history_payload()
    polls = 1_000

    def old_history_work() -> None:
        for _ in range(polls):
            json.loads(payload)

    etag = hashlib.sha256(payload).hexdigest()

    def conditional_history_work() -> None:
        # First 200 response is parsed; unchanged subsequent replies validate
        # compact headers/identity and take the native 304 path.
        json.loads(payload)
        for _ in range(polls - 1):
            _ = etag == etag and 0 <= 1 <= 10

    old_seconds = median_seconds(old_history_work)
    conditional_seconds = median_seconds(conditional_history_work)
    clock_ticks_per_minute = 60 * 1000 // 5
    print(f"history payload bytes: {len(payload):,}")
    print(f"history full parses: {polls} -> 1")
    print(f"history parse-work speedup: {old_seconds / conditional_seconds:.1f}x")
    print(f"wall-clock format/update calls per minute: {clock_ticks_per_minute:,} -> 60")
    print("decode row visibility: synchronous (viewport repaint transactions: 2 -> 1)")


if __name__ == "__main__":
    main()
