#!/usr/bin/env python3
"""Match raw OCPF expenditure and subvendor records against the AI vendor
taxonomy, and separately total how many distinct filers reported any
expenditure activity at all (the denominator for "how many campaigns show
AI spend" on the dashboard).

Reads data/raw/ocpf/{expenditures,subvendor}.jsonl (produced by
fetch_ocpf.py) and writes data/processed/ocpf_matches.csv,
data/processed/ocpf_subvendor_matches.csv, and
data/processed/ocpf_filer_totals.csv.

Matches against the concatenation of `vendor`, `clarifiedName`, `purpose`,
and `clarifiedPurpose` (`subvendorName`/`vendorName`/`purpose` for subvendor
records) -- the same fields, and the same taxonomy, parse_disbursements.py
uses for FEC data. OCPF supplies `clarifiedName`/`clarifiedPurpose` itself
when the as-filed payee/purpose string is ambiguous or a bank-processor
descriptor; matching against both catches a real payment however OCPF's own
staff annotated it.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.vendor_match import Taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "ocpf"
PROCESSED_DIR = ROOT / "data" / "processed"

EXPENDITURE_MATCH_FIELDS = ["vendor", "clarifiedName", "purpose", "clarifiedPurpose"]
SUBVENDOR_MATCH_FIELDS = ["subvendorName", "vendorName", "purpose"]

EXPENDITURE_OUT_FIELDS = [
    "record_id",
    "filer_cpf_id",
    "filer_name",
    "date",
    "amount",
    "vendor",
    "clarified_name",
    "purpose",
    "clarified_purpose",
    "record_type_description",
    "source_link",
    "vendor_ids",
    "vendor_names",
    "vendor_groups",
    "vendor_eras",
    "confidences",
]
SUBVENDOR_OUT_FIELDS = [
    "record_id",
    "filer_cpf_id",
    "filer_name",
    "date",
    "amount",
    "vendor_name",
    "subvendor_name",
    "purpose",
    "source_link",
    "vendor_ids",
    "vendor_names",
    "vendor_groups",
    "vendor_eras",
    "confidences",
]


def _amount(rec: dict) -> float:
    try:
        return float(str(rec.get("amount", "0")).replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def parse_expenditures(taxonomy: Taxonomy, subvendor_scanned: int) -> int:
    src = RAW_DIR / "expenditures.jsonl"
    out_path = PROCESSED_DIR / "ocpf_matches.csv"
    filers_totals_path = PROCESSED_DIR / "ocpf_filer_totals.csv"

    total = 0
    matched = 0
    filers_seen: set[str] = set()
    seen_ids: set = set()

    with open(src, encoding="utf-8") as f_in, open(out_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=EXPENDITURE_OUT_FIELDS)
        writer.writeheader()

        for line in f_in:
            rec = json.loads(line)
            total += 1
            filers_seen.add(str(rec.get("filerCpfId", "")))

            text = " ".join(str(rec.get(f) or "") for f in EXPENDITURE_MATCH_FIELDS)
            vendor_hits = taxonomy.match_vendors(text)
            if not vendor_hits:
                continue

            # A record can be returned once per pattern match on the same
            # underlying OCPF item id; keep only the first occurrence.
            rec_id = rec.get("id")
            if rec_id in seen_ids:
                continue
            seen_ids.add(rec_id)

            writer.writerow(
                {
                    "record_id": rec_id,
                    "filer_cpf_id": rec.get("filerCpfId"),
                    "filer_name": rec.get("filerFullNameReverse"),
                    "date": rec.get("date"),
                    "amount": _amount(rec),
                    "vendor": rec.get("vendor"),
                    "clarified_name": rec.get("clarifiedName"),
                    "purpose": rec.get("purpose"),
                    "clarified_purpose": rec.get("clarifiedPurpose"),
                    "record_type_description": rec.get("recordTypeDescription"),
                    "source_link": rec.get("sourceLink"),
                    "vendor_ids": ";".join(v.id for v, _ in vendor_hits),
                    "vendor_names": ";".join(v.name for v, _ in vendor_hits),
                    "vendor_groups": ";".join(v.group for v, _ in vendor_hits),
                    "vendor_eras": ";".join(v.era for v, _ in vendor_hits),
                    "confidences": ";".join(c for _, c in vendor_hits),
                }
            )
            matched += 1

    with open(filers_totals_path, "w", newline="", encoding="utf-8") as f_totals:
        writer = csv.writer(f_totals)
        writer.writerow(
            ["total_filers_with_expenditure_activity", "total_expenditure_records", "total_subvendor_records"]
        )
        writer.writerow([len(filers_seen), total, subvendor_scanned])

    print(
        f"expenditures: {total:,} records scanned, {matched:,} matched, "
        f"{len(filers_seen):,} distinct filers -> {out_path}"
    )
    return matched


def parse_subvendor(taxonomy: Taxonomy) -> tuple[int, int]:
    src = RAW_DIR / "subvendor.jsonl"
    out_path = PROCESSED_DIR / "ocpf_subvendor_matches.csv"

    total = 0
    matched = 0
    seen_ids: set = set()

    with open(src, encoding="utf-8") as f_in, open(out_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=SUBVENDOR_OUT_FIELDS)
        writer.writeheader()

        for line in f_in:
            rec = json.loads(line)
            total += 1

            text = " ".join(str(rec.get(f) or "") for f in SUBVENDOR_MATCH_FIELDS)
            vendor_hits = taxonomy.match_vendors(text)
            if not vendor_hits:
                continue

            rec_id = rec.get("id")
            if rec_id in seen_ids:
                continue
            seen_ids.add(rec_id)

            writer.writerow(
                {
                    "record_id": rec_id,
                    "filer_cpf_id": rec.get("filerCpfId"),
                    "filer_name": rec.get("filerFullNameReverse"),
                    "date": rec.get("date"),
                    "amount": _amount(rec),
                    "vendor_name": rec.get("vendorName"),
                    "subvendor_name": rec.get("subvendorName"),
                    "purpose": rec.get("purpose"),
                    "source_link": rec.get("sourceLink"),
                    "vendor_ids": ";".join(v.id for v, _ in vendor_hits),
                    "vendor_names": ";".join(v.name for v, _ in vendor_hits),
                    "vendor_groups": ";".join(v.group for v, _ in vendor_hits),
                    "vendor_eras": ";".join(v.era for v, _ in vendor_hits),
                    "confidences": ";".join(c for _, c in vendor_hits),
                }
            )
            matched += 1

    print(f"subvendor: {total:,} records scanned, {matched:,} matched -> {out_path}")
    return total, matched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    taxonomy = Taxonomy()
    subvendor_scanned, _ = parse_subvendor(taxonomy)
    parse_expenditures(taxonomy, subvendor_scanned)


if __name__ == "__main__":
    main()
