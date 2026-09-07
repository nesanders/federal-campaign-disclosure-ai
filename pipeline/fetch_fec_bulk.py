#!/usr/bin/env python3
"""Download FEC bulk data files for a set of two-year election cycles.

Pulls, per cycle (e.g. 2026 = the 2025-2026 filing period):
  - cn{yy}.zip   candidate master (party, office, incumbency status)
  - ccl{yy}.zip  candidate-committee linkage
  - oppexp{yy}.zip  itemized operating expenditures (Schedule B) -- this is
    where campaign payments to AI vendors show up.

Source: https://www.fec.gov/data/browse-data/?tab=bulk-data (no API key
required). Files are large (oppexp can be 500MB+ per cycle uncompressed), so
raw downloads are cached under data/raw/ and gitignored.
"""
from __future__ import annotations

import argparse
import sys
import time
import zipfile
from pathlib import Path

import requests

BULK_BASE = "https://www.fec.gov/files/bulk-downloads"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

DATASETS = {
    "cn": "cn{yy}.zip",
    "ccl": "ccl{yy}.zip",
    "cm": "cm{yy}.zip",
    "oppexp": "oppexp{yy}.zip",
}


def download(url: str, dest: Path, session: requests.Session, retries: int = 4) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [cache] {dest.name}")
        return
    for attempt in range(1, retries + 1):
        try:
            print(f"  [fetch] {url}")
            resp = session.get(url, timeout=120, stream=True)
            resp.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
            tmp.rename(dest)
            return
        except requests.RequestException as exc:
            wait = 2 ** attempt
            print(f"    retry {attempt}/{retries} after {wait}s ({exc})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed to download {url} after {retries} attempts")


def extract(zip_path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if not infos:
            raise RuntimeError(f"no files found in {zip_path}")
        # FEC bulk zips normally contain a single data file; if more than one
        # shows up, take the largest (the data file dwarfs any readme).
        member = max(infos, key=lambda i: i.file_size).filename
        target = dest_dir / member
        if not target.exists():
            zf.extract(member, dest_dir)
        return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cycles",
        nargs="+",
        type=int,
        default=[2020, 2022, 2024, 2026],
        help="Two-year cycle end years to fetch (default: 2020 2022 2024 2026)",
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})

    for cycle in args.cycles:
        yy = str(cycle)[-2:]
        cycle_dir = RAW_DIR / str(cycle)
        cycle_dir.mkdir(parents=True, exist_ok=True)
        print(f"Cycle {cycle}:")
        for dataset, pattern in DATASETS.items():
            filename = pattern.format(yy=yy)
            url = f"{BULK_BASE}/{cycle}/{filename}"
            zip_path = cycle_dir / filename
            download(url, zip_path, session)
            extracted = extract(zip_path, cycle_dir)
            print(f"    -> {extracted.relative_to(RAW_DIR.parent.parent)}")

    print("Done.")


if __name__ == "__main__":
    main()
