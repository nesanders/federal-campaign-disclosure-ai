#!/usr/bin/env python3
"""Fetch the actual filed-date for every OCPF report that produced an
AI-vendor-matched expenditure or subvendor record.

Unlike FEC's bulk data (no per-record filed date at all -- see
lib/fec_report_dates.py), OCPF's `report/{reportId}` endpoint returns a
real `dateFiled` for each report. This is a distinct concept from the
expenditure's own transaction date: one report, filed on one date, can
disclose expenditure line items spanning weeks or months of prior activity
(e.g. a credit-card or bank report). The weekly disclosure-timeline
histogram needs both dates, so this script fetches the report side.

Reads data/processed/ocpf_matches.csv and ocpf_subvendor_matches.csv for
their distinct report_id values (small -- a few hundred, not the full
~325K-record corpus), fetches each report once, and writes
data/processed/ocpf_report_dates.csv (report_id, date_filed, report_type,
is_amendment).
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
API_BASE = "https://api.ocpf.us/report"

OUT_FIELDS = ["report_id", "date_filed", "report_type", "is_amendment"]


def distinct_report_ids() -> set[str]:
    ids: set[str] = set()
    for filename in ("ocpf_matches.csv", "ocpf_subvendor_matches.csv"):
        path = PROCESSED_DIR / filename
        if not path.exists():
            continue
        for row in csv.DictReader(open(path, encoding="utf-8")):
            rid = row.get("report_id")
            if rid:
                ids.add(rid)
    return ids


def fetch_report(report_id: str, session: requests.Session) -> dict | None:
    resp = session.get(f"{API_BASE}/{report_id}", timeout=30)
    if resp.status_code >= 400:
        return None
    payload = resp.json()
    return {
        "report_id": report_id,
        "date_filed": payload.get("dateFiled") or "",
        "report_type": payload.get("reportTypeDescription") or "",
        "is_amendment": payload.get("isAmendment", False),
    }


def main() -> None:
    report_ids = sorted(distinct_report_ids(), key=lambda x: int(x))
    print(f"Fetching {len(report_ids)} distinct reports...")

    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})

    out_path = PROCESSED_DIR / "ocpf_report_dates.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=OUT_FIELDS)
        writer.writeheader()
        fetched = 0
        failed = 0
        for i, report_id in enumerate(report_ids):
            row = fetch_report(report_id, session)
            if row is None:
                failed += 1
                continue
            writer.writerow(row)
            fetched += 1
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(report_ids)}...")
            time.sleep(0.05)

    print(f"Done: {fetched} fetched, {failed} failed -> {out_path}")


if __name__ == "__main__":
    main()
