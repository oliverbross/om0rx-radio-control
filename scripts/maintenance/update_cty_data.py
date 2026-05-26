#!/usr/bin/env python3
"""Update local CTY data files from the configured country-files source."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

DEFAULT_CTY_DAT_URLS = [
    "https://www.country-files.com/cty/cty.dat",
    "http://www.country-files.com/cty/cty.dat",
]
DEFAULT_CTY_CSV_URLS = [
    "https://www.country-files.com/cty/cty.csv",
    "http://www.country-files.com/cty/cty.csv",
]


def download_first(urls: list[str], target: Path) -> str:
    errors = []
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
            target.write_bytes(data)
            return url
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("Unable to download CTY data:\n" + "\n".join(errors))


def validate_cty_dat(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    required = ["European Russia:", "United States:", "Japan:"]
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"cty.dat validation failed; missing {missing}")
    if text.count(":") < 500:
        raise ValueError("cty.dat validation failed; file does not look like CTY data")


def validate_cty_csv(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    required = ["European Russia", "United States", "Japan"]
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"cty.csv validation failed; missing {missing}")
    if text.count(",") < 500:
        raise ValueError("cty.csv validation failed; file does not look like CSV data")


def replace_with_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        backup = destination.with_suffix(destination.suffix + ".bak")
        shutil.copy2(destination, backup)
    shutil.copy2(source, destination)


def update_file(name: str, destination: Path, urls: list[str], validator) -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / name
        used_url = download_first(urls, temp_path)
        validator(temp_path)
        replace_with_backup(temp_path, destination)
        return used_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Update local CTY data files")
    parser.add_argument("--dat-url", action="append", help="Override/add cty.dat download URL")
    parser.add_argument("--csv-url", action="append", help="Override/add cty.csv download URL")
    parser.add_argument("--skip-csv", action="store_true", help="Only update cty.dat")
    args = parser.parse_args()

    dat_urls = args.dat_url or DEFAULT_CTY_DAT_URLS
    csv_urls = args.csv_url or DEFAULT_CTY_CSV_URLS

    dat_url = update_file("cty.dat", DATA_DIR / "cty.dat", dat_urls, validate_cty_dat)
    print(f"cty.dat updated from {dat_url}")

    if not args.skip_csv:
        csv_url = update_file("cty.csv", DATA_DIR / "cty.csv", csv_urls, validate_cty_csv)
        print(f"cty.csv updated from {csv_url}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CTY update failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
