#!/usr/bin/env python3
"""Match raw Colorado TRACER expenditure records against the AI vendor
taxonomy, and separately total each filer's total reported spend by year.

Reads every data/raw/co/<year>_ExpenditureData.csv (produced by
fetch_co.py) and writes data/processed/co_matches.csv,
data/processed/co_filer_totals.csv, and
data/processed/co_filer_year_totals.csv -- the common intermediate
schema pipeline/lib/build_state_dataset.py expects.

Matches against the concatenation of `Explanation` (free-text purpose)
and the payee name (`LastName`/`FirstName`, which for a business payee
is just its name stuffed into LastName with FirstName blank -- confirmed
against real rows, e.g. "PNC BANK").

Unlike Washington and Massachusetts, TRACER's bulk expenditure file has
no party field at all, and (unlike OCPF) this pipeline does not do a
separate per-filer party lookup for Colorado -- every record's `party`
is left blank here, which the shared aggregator treats as "Unknown" the
same way it does for OCPF filers with no major-party affiliation. This
means Colorado's party-split chart/table will show no data until a
lookup is built; see build_dataset_co.py's methodology notes.

`source_link` is always left empty for the same reason: TRACER's public
per-transaction deep link (ExpenditureDetail.aspx) needs both a SeqID and
a filingid, and this bulk export carries only a RecordID -- plausibly the
same value as SeqID given similar magnitudes in spot checks, but with no
filingid alongside it to pair with, there's no way to build a working
link from this file alone (compare California's parse_ca.py, whose bulk
source does carry the FILING_ID CAL-ACCESS's own PDF endpoint needs).
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.vendor_match import Taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "co"
PROCESSED_DIR = ROOT / "data" / "processed"

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


def _payee_name(row: dict) -> str:
    first = (row.get("FirstName") or "").strip()
    last = (row.get("LastName") or "").strip()
    if first and last:
        return f"{first} {last}"
    return last or first


def _amount(row: dict) -> float:
    try:
        return float(str(row.get("ExpenditureAmount", "0")).replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def main() -> None:
    taxonomy = Taxonomy()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(RAW_DIR.glob("*_ExpenditureData.csv"))
    if not csv_files:
        print("No raw Colorado expenditure files found -- run fetch_co.py first.", file=sys.stderr)
        sys.exit(1)

    out_path = PROCESSED_DIR / "co_matches.csv"
    filer_totals_path = PROCESSED_DIR / "co_filer_totals.csv"
    filer_year_totals_path = PROCESSED_DIR / "co_filer_year_totals.csv"

    total = 0
    matched = 0
    filers_seen: set[str] = set()
    seen_ids: set = set()
    filer_year_totals: dict[tuple[str, int], float] = defaultdict(float)

    with open(out_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=OUT_FIELDS)
        writer.writeheader()

        for csv_path in csv_files:
            with open(csv_path, encoding="utf-8-sig", errors="replace", newline="") as f_in:
                for row in csv.DictReader(f_in):
                    total += 1
                    filer_id = row.get("CO_ID") or ""
                    filers_seen.add(filer_id)

                    date = (row.get("ExpenditureDate") or "")[:10]
                    amount = _amount(row)
                    if date:
                        try:
                            year = int(date[:4])
                            filer_year_totals[(filer_id, year)] += amount
                        except ValueError:
                            pass

                    payee = _payee_name(row)
                    explanation = row.get("Explanation") or ""
                    text = f"{explanation} {payee}"
                    vendor_hits = taxonomy.match_vendors(text)
                    if not vendor_hits:
                        continue

                    rec_id = row.get("RecordID")
                    if rec_id in seen_ids:
                        continue
                    seen_ids.add(rec_id)

                    filer_name = row.get("CommitteeName") or row.get("CandidateName") or ""
                    writer.writerow(
                        {
                            "record_id": rec_id,
                            "filer_id": filer_id,
                            "filer_name": filer_name,
                            "party": "",
                            "date": date,
                            "amount": amount,
                            "payee_display": payee,
                            "purpose_display": explanation,
                            "office": row.get("Jurisdiction"),
                            "source_link": None,
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

    print(f"CO: {total:,} records scanned, {matched:,} matched, {len(filers_seen):,} distinct filers -> {out_path}")


if __name__ == "__main__":
    main()
