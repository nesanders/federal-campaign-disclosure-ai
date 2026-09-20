#!/usr/bin/env python3
"""Download Washington state itemized campaign expenditures via the
Public Disclosure Commission's Socrata open-data API (data.wa.gov,
dataset tijg-9zyp, "Expenditures by Candidates and Political
Committees").

Unlike OCPF, this is a real, documented Socrata SODA API -- standard
$limit/$offset pagination and a $select=count(*) integrity check,
confirmed against the dataset's own row count before any fetch code was
written. See planning/state-expansion-plan.md's Round 2 for the
discovery notes.

Default date window matches every other fetch_*.py in this pipeline
(2023-01-01 onward, covering the 2024 and 2026 cycles) rather than the
dataset's full ~10-year history, both for consistency and because a
narrower window is a much smaller, faster fetch (240K rows vs. 1.09M).

Output: data/raw/wa/expenditures.jsonl (gitignored, like all of
data/raw/).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

API_BASE = "https://data.wa.gov/resource/tijg-9zyp.json"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "wa"

PAGE_SIZE = 50000
MAX_PAGES = 200


def fetch_all(start_date: str, session: requests.Session) -> list[dict]:
    where = f"expenditure_date >= '{start_date}T00:00:00.000'"

    count_resp = session.get(API_BASE, params={"$select": "count(*)", "$where": where}, timeout=60)
    count_resp.raise_for_status()
    expected = int(count_resp.json()[0]["count"])
    print(f"  API reports {expected:,} rows for this window")

    collected: list[dict] = []
    offset = 0
    for page in range(MAX_PAGES):
        params = {
            "$where": where,
            "$order": ":id",
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }
        resp = session.get(API_BASE, params=params, timeout=90)
        resp.raise_for_status()
        items = resp.json()
        print(f"  page {page}: got={len(items)} collected={len(collected) + len(items)} expected={expected}")
        if not items:
            break
        collected.extend(items)
        offset += len(items)
        if len(items) < PAGE_SIZE:
            break
        time.sleep(0.2)
    else:
        raise RuntimeError(f"did not finish paging after {MAX_PAGES} pages")

    if len(collected) != expected:
        raise RuntimeError(
            f"collected {len(collected)} records but the API reports {expected} -- "
            f"refusing to write an incomplete or inflated result"
        )
    return collected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-date",
        default="2023-01-01",
        help="Start of the window to fetch (default: 2023-01-01, covering the 2024 and 2026 cycles)",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})

    records = fetch_all(args.start_date, session)
    out_path = RAW_DIR / "expenditures.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    print(f"{len(records):,} records -> {out_path}")


if __name__ == "__main__":
    main()
