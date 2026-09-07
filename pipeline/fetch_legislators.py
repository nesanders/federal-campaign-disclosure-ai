#!/usr/bin/env python3
"""Download the unitedstates/congress-legislators dataset.

Used to attach birthdate (-> age), party, and chamber to *incumbent and
former* members of Congress by FEC candidate ID (bioguide/FEC IDs are
cross-walked in `legislators-*.json` under each person's `id` block).

Coverage caveat (also surfaced in the dashboard): this dataset only covers
people who have actually served in Congress. Non-incumbent challengers who
have never held the seat do not have a birthdate here, so age comparisons
skew toward incumbents; the pipeline leaves their age as null rather than
guessing.

Source: https://github.com/unitedstates/congress-legislators (public domain,
maintained by a consortium of civic-tech organizations).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

BASE = "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages"
FILES = ["legislators-current.json", "legislators-historical.json"]
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "legislators"


def download(url: str, dest: Path, session: requests.Session, retries: int = 4) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [cache] {dest.name}")
        return
    for attempt in range(1, retries + 1):
        try:
            print(f"  [fetch] {url}")
            resp = session.get(url, timeout=120)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return
        except requests.RequestException as exc:
            wait = 2 ** attempt
            print(f"    retry {attempt}/{retries} after {wait}s ({exc})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed to download {url} after {retries} attempts")


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})
    for fname in FILES:
        download(f"{BASE}/{fname}", RAW_DIR / fname, session)
    print("Done.")


if __name__ == "__main__":
    main()
