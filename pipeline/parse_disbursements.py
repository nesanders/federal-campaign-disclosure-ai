#!/usr/bin/env python3
"""Scan itemized Schedule B disbursements (oppexp) for AI-vendor payments,
and separately total each committee's overall reported spending.

For each cycle, streams the (large, headerless) oppexp text file once and:
  1. Matches each row's payee name + purpose + memo text against the vendor
     taxonomy in config/vendors.yaml, writing matching rows -- a small
     fraction of the total -- to data/processed/matches_{cycle}.csv.
  2. Accumulates each committee's total reported operating expenditure into
     data/processed/totals_{cycle}.csv, as the denominator for "AI spend as
     a share of total spend" elsewhere in the pipeline.

A note on FEC's MEMO_CD convention: many disbursements are reported as a
single lump payment (e.g. to a credit-card processor) with the individual
line items broken out afterward as separate "memo entries" (MEMO_CD='X')
that re-describe part of that same lump sum for transparency -- they are
not additional spending. This is exactly how a specific AI vendor name
often surfaces (e.g. "AMERICAN EXPRESS" as the actual payee, with a memo
entry itemizing "OPENAI" as one of the card's line items), so memo entries
are KEPT when matching AI vendors -- excluding them would hide exactly the
detail we're looking for. But they are EXCLUDED from the committee-total
denominator, since that dollar amount is already counted once in the
non-memo lump-sum transaction; including both would double-count it.

FEC bulk text is pipe-delimited, unquoted, and not strictly UTF-8, so rows
are parsed defensively: malformed lines (wrong field count) are counted and
skipped rather than crashing the run.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.fec_schema import fetch_header  # noqa: E402
from lib.vendor_match import Taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

TEXT_FIELDS = ["NAME", "PURPOSE", "CATEGORY_DESC", "MEMO_TEXT"]
OUT_FIELDS = [
    "cycle",
    "cmte_id",
    "name",
    "city",
    "state",
    "transaction_dt",
    "transaction_amt",
    "purpose",
    "category_desc",
    "memo_text",
    "memo_cd",
    "rpt_yr",
    "sub_id",
    "vendor_ids",
    "vendor_names",
    "vendor_groups",
    "confidences",
    "use_categories",
]
TOTALS_FIELDS = ["cmte_id", "total_amount", "total_count"]


def find_oppexp_file(cycle_dir: Path) -> Path:
    candidates = list(cycle_dir.glob("*oppexp*.txt")) + list(cycle_dir.glob("itoppexp*.txt"))
    if not candidates:
        raise FileNotFoundError(f"no oppexp txt file found in {cycle_dir}")
    return candidates[0]


def process_cycle(cycle: int, taxonomy: Taxonomy, session: requests.Session) -> int:
    cycle_dir = RAW_DIR / str(cycle)
    header = fetch_header("oppexp", RAW_DIR / "_headers", session)
    idx = {name: i for i, name in enumerate(header)}
    n_fields = len(header)

    src = find_oppexp_file(cycle_dir)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"matches_{cycle}.csv"
    totals_path = PROCESSED_DIR / f"totals_{cycle}.csv"

    total = 0
    matched = 0
    malformed = 0
    cmte_totals: dict[str, list] = defaultdict(lambda: [0.0, 0])

    with open(src, encoding="latin-1", errors="replace", newline="") as f_in, open(
        out_path, "w", newline="", encoding="utf-8"
    ) as f_out:
        reader = csv.reader(f_in, delimiter="|")
        writer = csv.DictWriter(f_out, fieldnames=OUT_FIELDS)
        writer.writeheader()

        for row in reader:
            total += 1
            if len(row) < n_fields:
                malformed += 1
                continue
            row = row[:n_fields]

            cmte_id = row[idx.get("CMTE_ID", -1)] if "CMTE_ID" in idx else ""
            memo_cd = row[idx.get("MEMO_CD", -1)] if "MEMO_CD" in idx else ""
            try:
                amt = float(row[idx.get("TRANSACTION_AMT", -1)]) if "TRANSACTION_AMT" in idx else 0.0
            except ValueError:
                amt = 0.0
            if cmte_id and memo_cd != "X":
                # Exclude memo entries from the committee total: they re-describe
                # part of a lump-sum payment already counted elsewhere on the
                # same report, so including them would double-count spending.
                cmte_totals[cmte_id][0] += amt
                cmte_totals[cmte_id][1] += 1

            text = " ".join(row[idx[f]] for f in TEXT_FIELDS if f in idx and row[idx[f]])
            vendor_hits = taxonomy.match_vendors(text)
            if not vendor_hits:
                continue

            purpose_text = " ".join(
                row[idx[f]] for f in ("PURPOSE", "CATEGORY_DESC", "MEMO_TEXT") if f in idx and row[idx[f]]
            )
            categories = taxonomy.match_categories(purpose_text)

            writer.writerow(
                {
                    "cycle": cycle,
                    "cmte_id": cmte_id,
                    "name": row[idx.get("NAME", -1)] if "NAME" in idx else "",
                    "city": row[idx.get("CITY", -1)] if "CITY" in idx else "",
                    "state": row[idx.get("STATE", -1)] if "STATE" in idx else "",
                    "transaction_dt": row[idx.get("TRANSACTION_DT", -1)] if "TRANSACTION_DT" in idx else "",
                    "transaction_amt": row[idx.get("TRANSACTION_AMT", -1)] if "TRANSACTION_AMT" in idx else "",
                    "purpose": row[idx.get("PURPOSE", -1)] if "PURPOSE" in idx else "",
                    "category_desc": row[idx.get("CATEGORY_DESC", -1)] if "CATEGORY_DESC" in idx else "",
                    "memo_text": row[idx.get("MEMO_TEXT", -1)] if "MEMO_TEXT" in idx else "",
                    "memo_cd": memo_cd,
                    "rpt_yr": row[idx.get("RPT_YR", -1)] if "RPT_YR" in idx else "",
                    "sub_id": row[idx.get("SUB_ID", -1)] if "SUB_ID" in idx else "",
                    "vendor_ids": ";".join(v.id for v, _ in vendor_hits),
                    "vendor_names": ";".join(v.name for v, _ in vendor_hits),
                    "vendor_groups": ";".join(v.group for v, _ in vendor_hits),
                    "confidences": ";".join(c for _, c in vendor_hits),
                    "use_categories": ";".join(categories),
                }
            )
            matched += 1

    with open(totals_path, "w", newline="", encoding="utf-8") as f_totals:
        writer = csv.DictWriter(f_totals, fieldnames=TOTALS_FIELDS)
        writer.writeheader()
        for cmte_id, (amount, count) in sorted(cmte_totals.items()):
            writer.writerow({"cmte_id": cmte_id, "total_amount": round(amount, 2), "total_count": count})

    print(
        f"cycle {cycle}: {total:,} rows scanned, {matched:,} matched, {malformed:,} malformed skipped "
        f"-> {out_path} ; {len(cmte_totals):,} committees totaled -> {totals_path}"
    )
    return matched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", nargs="+", type=int, default=[2020, 2022, 2024, 2026])
    args = parser.parse_args()

    taxonomy = Taxonomy()
    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})

    for cycle in args.cycles:
        process_cycle(cycle, taxonomy, session)


if __name__ == "__main__":
    main()
