#!/usr/bin/env python3
"""Match raw Washington PDC expenditure records against the AI vendor
taxonomy, and separately total each filer's total reported spend by year
(the denominator for "AI spend as a % of total spend").

Reads data/raw/wa/expenditures.jsonl (produced by fetch_wa.py) and writes
data/processed/wa_matches.csv, data/processed/wa_filer_totals.csv, and
data/processed/wa_filer_year_totals.csv -- the common intermediate schema
pipeline/lib/build_state_dataset.py expects (see that module's docstring).

Matches against the concatenation of `description` (free-text purpose),
`code` (PDC's own expense-category label, e.g. "Computers, printers,
software, phones, etc." -- a real pre-filter signal, not just noise), and
`recipient_name` (payee). `party` is normalized from PDC's all-caps
DEMOCRATIC/REPUBLICAN to this project's Democratic/Republican convention;
anything else (minor parties, blank, PAC-type filers with no party at
all) is left as an empty string, matching OCPF's own "Unknown" handling.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.vendor_match import Taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "wa"
PROCESSED_DIR = ROOT / "data" / "processed"

MATCH_FIELDS = ["description", "code", "recipient_name"]

OUT_FIELDS = [
    "record_id",
    "filer_id",
    "filer_name",
    "party",
    "date",
    "amount",
    "payee_display",
    "purpose_display",
    "office",
    "source_link",
    "vendor_ids",
    "vendor_names",
    "vendor_groups",
    "vendor_eras",
    "confidences",
]

PARTY_MAP = {"DEMOCRATIC": "Democratic", "REPUBLICAN": "Republican"}


def _amount(rec: dict) -> float:
    try:
        return float(str(rec.get("amount", "0")).replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def _date(rec: dict) -> str:
    # Socrata floating timestamp, e.g. "2026-07-28T00:00:00.000" -- just
    # need the YYYY-MM-DD prefix, same ISO-date convention the shared
    # aggregator expects.
    raw = rec.get("expenditure_date") or ""
    return raw[:10]


def main() -> None:
    taxonomy = Taxonomy()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    src = RAW_DIR / "expenditures.jsonl"
    out_path = PROCESSED_DIR / "wa_matches.csv"
    filer_totals_path = PROCESSED_DIR / "wa_filer_totals.csv"
    filer_year_totals_path = PROCESSED_DIR / "wa_filer_year_totals.csv"

    total = 0
    matched = 0
    filers_seen: set[str] = set()
    seen_ids: set = set()
    filer_year_totals: dict[tuple[str, int], float] = defaultdict(float)

    with open(src, encoding="utf-8") as f_in, open(out_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=OUT_FIELDS)
        writer.writeheader()

        for line in f_in:
            rec = json.loads(line)
            total += 1
            filer_id = rec.get("filer_id") or rec.get("committee_id") or ""
            filers_seen.add(filer_id)

            date = _date(rec)
            amount = _amount(rec)
            if date:
                try:
                    year = int(date[:4])
                    filer_year_totals[(filer_id, year)] += amount
                except ValueError:
                    pass

            text = " ".join(str(rec.get(f) or "") for f in MATCH_FIELDS)
            vendor_hits = taxonomy.match_vendors(text)
            if not vendor_hits:
                continue

            rec_id = rec.get("id")
            if rec_id in seen_ids:
                continue
            seen_ids.add(rec_id)

            party_raw = (rec.get("party") or "").strip().upper()
            party = PARTY_MAP.get(party_raw, "")

            url = rec.get("url") or {}
            writer.writerow(
                {
                    "record_id": rec_id,
                    "filer_id": filer_id,
                    "filer_name": rec.get("filer_name"),
                    "party": party,
                    "date": date,
                    "amount": amount,
                    "payee_display": rec.get("recipient_name"),
                    "purpose_display": rec.get("description") or rec.get("code") or "",
                    "office": rec.get("office"),
                    "source_link": url.get("url"),
                    "vendor_ids": ";".join(v.id for v, _ in vendor_hits),
                    "vendor_names": ";".join(v.name for v, _ in vendor_hits),
                    "vendor_groups": ";".join(v.group for v, _ in vendor_hits),
                    "vendor_eras": ";".join(v.era for v, _ in vendor_hits),
                    "confidences": ";".join(c for _, c in vendor_hits),
                }
            )
            matched += 1

    with open(filer_totals_path, "w", newline="", encoding="utf-8") as f_totals:
        w = csv.writer(f_totals)
        w.writerow(["total_filers_with_expenditure_activity", "total_expenditure_records"])
        w.writerow([len(filers_seen), total])

    with open(filer_year_totals_path, "w", newline="", encoding="utf-8") as f_yr:
        w = csv.writer(f_yr)
        w.writerow(["filer_id", "year", "total_expenditure"])
        for (filer_id, year), amount in sorted(filer_year_totals.items()):
            w.writerow([filer_id, year, round(amount, 2)])

    print(f"WA: {total:,} records scanned, {matched:,} matched, {len(filers_seen):,} distinct filers -> {out_path}")


if __name__ == "__main__":
    main()
