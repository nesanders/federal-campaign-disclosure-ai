#!/usr/bin/env python3
"""Download Colorado TRACER (Secretary of State) itemized campaign
expenditure data: plain annual CSV-in-zip bulk downloads, no auth or API
needed. See planning/state-expansion-plan.md's Round 2 for the discovery
notes -- confirmed at
https://Tracer.sos.colorado.gov/PublicSite/Docs/BulkDataDownloads/<YEAR>_ExpenditureData.csv.zip

This is the flattest of the three new state sources: no pagination, no
rate limits, just one file per year to download and concatenate --
closest in shape to fetch_fec_bulk.py's own per-cycle file loop.

Output: data/raw/co/<year>_ExpenditureData.csv (gitignored, like all of
data/raw/).
"""
from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

import requests

BASE_URL = "https://Tracer.sos.colorado.gov/PublicSite/Docs/BulkDataDownloads/{year}_ExpenditureData.csv.zip"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "co"

HEADERS = {"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"}


def fetch_year(year: int, session: requests.Session) -> Path | None:
    url = BASE_URL.format(year=year)
    resp = session.get(url, headers=HEADERS, timeout=60)
    if resp.status_code == 404:
        print(f"  {year}: not found (404) -- skipping")
        return None
    resp.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if len(names) != 1:
        raise RuntimeError(f"{year}: expected exactly one CSV in the zip, found {names}")
    data = zf.read(names[0])

    out_path = RAW_DIR / f"{year}_ExpenditureData.csv"
    out_path.write_bytes(data)
    print(f"  {year}: {len(data):,} bytes -> {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2023, 2024, 2025, 2026],
        help="Years to fetch (default: 2023-2026, covering the 2024 and 2026 cycles)",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    fetched = 0
    for year in args.years:
        if fetch_year(year, session):
            fetched += 1
    print(f"Fetched {fetched} of {len(args.years)} requested years.")


if __name__ == "__main__":
    main()
