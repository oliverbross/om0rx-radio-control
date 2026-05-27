"""Validate FT8 WAV fixtures with a locally installed WSJT-X jt9.exe.

This is a development helper only. It does not make the application depend on
WSJT-X; it gives us an oracle while building a self-contained decoder binding.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "ft8"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
DEFAULT_JT9 = Path(r"C:\WSJT\wsjtz\bin\jt9.exe")
DEFAULT_WSJT_DATA = Path(r"C:\Users\Oliver\AppData\Local\WSJT-X")
DECODE_RE = re.compile(r"^\S+\s+[-+]?\d+\s+[-+]?\d+(?:\.\d+)?\s+\d+\s+~\s+(?P<message>.+?)\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jt9", type=Path, default=DEFAULT_JT9)
    parser.add_argument("--wsjt-data", type=Path, default=DEFAULT_WSJT_DATA)
    parser.add_argument("--fixture", help="Fixture filename from tests/fixtures/ft8")
    parser.add_argument("--depth", default="3")
    return parser.parse_args()


def decode_fixture(jt9: Path, wsjt_data: Path, fixture_path: Path, depth: str) -> list[str]:
    command = [
        str(jt9),
        "-8",
        "-p",
        "15",
        "-d",
        depth,
        "-e",
        str(jt9.parent),
        "-a",
        str(wsjt_data),
        "-t",
        str(wsjt_data),
        str(fixture_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    messages = []
    for line in result.stdout.splitlines():
        match = DECODE_RE.match(line)
        if match:
            messages.append(match.group("message").strip())
    return messages


def main() -> int:
    args = parse_args()
    if not args.jt9.exists():
        raise SystemExit(f"jt9.exe not found: {args.jt9}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"]
    if args.fixture:
        fixtures = [item for item in fixtures if item["file"] == args.fixture]
        if not fixtures:
            raise SystemExit(f"Fixture not found in manifest: {args.fixture}")

    failures = 0
    for item in fixtures:
        fixture_path = FIXTURE_DIR / item["file"]
        decoded = decode_fixture(args.jt9, args.wsjt_data, fixture_path, args.depth)
        expected = item.get("expected_messages", [])
        missing = [message for message in expected if message not in decoded]

        print(f"{item['file']}: decoded={len(decoded)} expected={len(expected)}")
        for message in decoded:
            print(f"  {message}")

        if missing:
            failures += 1
            print("  missing expected messages:")
            for message in missing:
                print(f"    {message}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
