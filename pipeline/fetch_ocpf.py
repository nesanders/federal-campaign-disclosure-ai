#!/usr/bin/env python3
"""Download Massachusetts OCPF (Office of Campaign and Political Finance)
itemized expenditure and subvendor records via api.ocpf.us.

This is the state-level companion to fetch_fec_bulk.py. OCPF has no bulk
file distribution comparable to the FEC's (the only public bulk-ZIP path,
used by Code for Boston's MAPLE project, only itemizes the receipt side of
committee reports); its own REST API at api.ocpf.us, reachable via
`search/items`, is what actually exposes payee-level, itemized EXPENDITURE
records ("SearchTypeCategory=B") and subvendor records ("SearchTypeCategory=S")
-- the state analog of FEC Schedule B. Confirmed against a public
`swagger.json` at that host and by direct use; there is no official
documentation of this API linked from OCPF's own public site.

Paginates each category in full (`StartIndex`/`PageSize`, 1-based -- see the
independent `ocpf` PyPI client's search.py for the pagination hazards this
avoids) over a date window, and refuses to write a result that doesn't match
the API's own reported `summary.count` -- a short read would silently
understate spending, and an inflated one would silently double-count it.
Filings land while a category is being paged (about 35 pages), which shifts
page boundaries: a record repeats across two pages or is skipped. Records
are de-duplicated by their `id`, and a category whose count still doesn't
match is re-paged from scratch, up to FETCH_ATTEMPTS times, before failing.

Output: one JSON-lines file per category under data/raw/ocpf/ (gitignored,
like all of data/raw/).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

API_BASE = "https://api.ocpf.us/search/items"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "ocpf"

# SearchTypeCategory codes. An unrecognized value silently falls back to
# receipts ("R") rather than erroring, so these are kept as constants here
# rather than ever being built from a variable.
CATEGORY_EXPENDITURES = "B"
CATEGORY_SUBVENDOR = "S"

PAGE_SIZE = 10000
MAX_PAGES = 200
FETCH_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 30


def fetch_category(category: str, start_date: str, end_date: str, session: requests.Session) -> list[dict]:
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        collected, expected = _page_through(category, start_date, end_date, session)
        unique = list({rec["id"]: rec for rec in collected}.values())
        if len(unique) < len(collected):
            print(f"  [{category}] dropped {len(collected) - len(unique)} records repeated across pages")
        if expected is None or len(unique) == expected:
            return unique
        print(
            f"  [{category}] attempt {attempt}: {len(unique)} unique records but the API reports {expected} "
            f"(records were filed or removed mid-fetch)"
        )
        if attempt < FETCH_ATTEMPTS:
            time.sleep(RETRY_WAIT_SECONDS)

    raise RuntimeError(
        f"[{category}] collected {len(unique)} records but the API reports {expected} after "
        f"{FETCH_ATTEMPTS} attempts -- refusing to write an incomplete or inflated result"
    )


def _page_through(
    category: str, start_date: str, end_date: str, session: requests.Session
) -> tuple[list[dict], int | None]:
    collected: list[dict] = []
    expected: int | None = None
    start_index = 1

    for page in range(MAX_PAGES):
        params = {
            "SearchTypeCategory": category,
            "StartDate": start_date,
            "EndDate": end_date,
            "StartIndex": start_index,
            "PageSize": PAGE_SIZE,
            "withSummary": "true",
        }
        resp = session.get(API_BASE, params=params, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("items") or []
        summary = payload.get("summary") or {}
        if summary.get("count") is not None:
            expected = summary["count"]

        print(
            f"  [{category}] page {page}: got={len(items)} collected={len(collected) + len(items)} "
            f"expected={expected}"
        )

        if not items:
            break
        collected.extend(items)
        start_index += len(items)
        if expected is not None and len(collected) >= expected:
            break
        if len(items) < PAGE_SIZE:
            break
        time.sleep(0.2)
    else:
        raise RuntimeError(f"[{category}] did not finish paging after {MAX_PAGES} pages")

    return collected, expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-date",
        default="2023-01-01",
        help="Start of the window to fetch (default: 2023-01-01, covering the 2024 and 2026 cycles)",
    )
    parser.add_argument("--end-date", default=None, help="End of the window (default: today)")
    args = parser.parse_args()
    end_date = args.end_date or time.strftime("%Y-%m-%d")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})

    for category, filename in (
        (CATEGORY_EXPENDITURES, "expenditures.jsonl"),
        (CATEGORY_SUBVENDOR, "subvendor.jsonl"),
    ):
        records = fetch_category(category, args.start_date, args.end_date, session)
        out_path = RAW_DIR / filename
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
        print(f"[{category}] {len(records):,} records -> {out_path}")

    print("Done.")


if __name__ == "__main__":
    main()
