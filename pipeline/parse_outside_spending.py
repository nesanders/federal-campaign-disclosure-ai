#!/usr/bin/env python3
"""Scan two "outside spending" FEC schedules for AI-vendor payments: money
spent for or against a candidate by people other than the candidate's own
campaign.

  1. Schedule E -- independent expenditures: Super PACs, hybrid PACs, and
     other non-candidate spenders paying a vendor to expressly advocate for
     or against a candidate, without coordinating with that candidate's
     campaign. Source: the FEC's independent_expenditure_{cycle}.csv bulk
     file (a plain CSV with its own header row -- unlike the other bulk
     files this pipeline reads, there is no separate pipe-delimited/
     header-dictionary pair for this one).
  2. Schedule F -- coordinated party expenditures: a national or state party
     committee (RNC, DNC, NRSC, DSCC, NRCC, DCCC, and state parties) paying
     a vendor for spending coordinated with a specific candidate, up to that
     cycle's statutory per-candidate limit. There is no dedicated bulk file
     for Schedule F; these transactions are folded into the FEC's general
     "any transaction from one committee to another" (oth) bulk file, coded
     as TRANSACTION_TP '24C' -- confirmed against that file's own
     description, which lists 24C among the transaction types it carries.

Both are itemized the same way oppexp is (payee/purpose/amount/date), so the
same vendor taxonomy and confidence tiers apply; matches are written to
data/processed/ie_matches_{cycle}.csv and pce_matches_{cycle}.csv.

Amendment duplication (Schedule E only): the FEC's own file description
warns that this file contains both original and amended reports without
removing the originals, so straight totals double-count anything later
amended. Each filing (identified by FILE_NUM) that has been superseded is
recorded on its replacement as PREV_FILE_NUM; we drop every row whose
FILE_NUM shows up as someone else's PREV_FILE_NUM, keeping only the final
version of each filing. The oth file (Schedule F's source here) carries no
equivalent field, so it is treated the same as oppexp elsewhere in this
pipeline -- no amendment de-duplication, consistent with the rest of the
pipeline's existing (documented) limitations there.
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

IE_OUT_FIELDS = [
    "cycle",
    "cand_id",
    "cand_name",
    "office",
    "cand_state",
    "cand_district",
    "cand_party",
    "spender_id",
    "spender_name",
    "support_oppose",
    "transaction_date",
    "transaction_amt",
    "purpose",
    "payee",
    "file_num",
    "tran_id",
    "vendor_ids",
    "vendor_names",
    "vendor_groups",
    "confidences",
    "use_categories",
]
IE_TOTALS_FIELDS = ["spender_id", "total_amount", "total_count"]

PCE_OUT_FIELDS = [
    "cycle",
    "cmte_id",
    "name",
    "city",
    "state",
    "transaction_dt",
    "transaction_amt",
    "memo_text",
    "memo_cd",
    "cand_id",
    "sub_id",
    "vendor_ids",
    "vendor_names",
    "vendor_groups",
    "confidences",
    "use_categories",
]
PCE_TOTALS_FIELDS = ["cmte_id", "total_amount", "total_count"]


def find_ie_file(cycle_dir: Path, cycle: int) -> Path:
    candidates = list(cycle_dir.glob(f"independent_expenditure_{cycle}.csv"))
    if not candidates:
        raise FileNotFoundError(f"no independent_expenditure_{cycle}.csv in {cycle_dir}")
    return candidates[0]


def find_oth_file(cycle_dir: Path) -> Path:
    candidates = list(cycle_dir.glob("itoth*.txt")) + list(cycle_dir.glob("*oth*.txt"))
    if not candidates:
        raise FileNotFoundError(f"no oth txt file found in {cycle_dir}")
    return candidates[0]


def process_independent_expenditures(cycle: int, taxonomy: Taxonomy) -> int:
    cycle_dir = RAW_DIR / str(cycle)
    src = find_ie_file(cycle_dir, cycle)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"ie_matches_{cycle}.csv"
    totals_path = PROCESSED_DIR / f"ie_totals_{cycle}.csv"

    # First pass: find every FILE_NUM that a later amendment superseded, so
    # we can drop the superseded (original) version of each filing.
    superseded: set[str] = set()
    with open(src, encoding="latin-1", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            prev = (row.get("prev_file_num") or "").strip()
            if prev:
                superseded.add(prev)

    total = 0
    matched = 0
    dropped_amended = 0
    spender_totals: dict[str, list] = defaultdict(lambda: [0.0, 0])

    with open(src, encoding="latin-1", errors="replace", newline="") as f_in, open(
        out_path, "w", newline="", encoding="utf-8"
    ) as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=IE_OUT_FIELDS)
        writer.writeheader()

        for row in reader:
            total += 1
            file_num = (row.get("file_num") or "").strip()
            if file_num and file_num in superseded:
                dropped_amended += 1
                continue

            try:
                amt = float(row.get("exp_amo") or 0)
            except ValueError:
                amt = 0.0
            spender_id = (row.get("spe_id") or "").strip()
            if spender_id:
                spender_totals[spender_id][0] += amt
                spender_totals[spender_id][1] += 1

            payee = row.get("pay") or ""
            purpose = row.get("pur") or ""
            text = f"{payee} {purpose}"
            vendor_hits = taxonomy.match_vendors(text)
            if not vendor_hits:
                continue
            categories = taxonomy.match_categories(purpose)

            writer.writerow(
                {
                    "cycle": (row.get("fec_election_yr") or "").strip() or cycle,
                    "cand_id": (row.get("cand_id") or "").strip(),
                    "cand_name": row.get("cand_name") or "",
                    "office": (row.get("can_office") or "").strip(),
                    "cand_state": (row.get("can_office_state") or "").strip(),
                    "cand_district": (row.get("can_office_dis") or "").strip(),
                    "cand_party": row.get("cand_pty_aff") or "",
                    "spender_id": spender_id,
                    "spender_name": row.get("spe_nam") or "",
                    "support_oppose": (row.get("sup_opp") or "").strip(),
                    "transaction_date": row.get("exp_date") or row.get("dissem_dt") or "",
                    "transaction_amt": amt,
                    "purpose": purpose,
                    "payee": payee,
                    "file_num": file_num,
                    "tran_id": row.get("tran_id") or "",
                    "vendor_ids": ";".join(v.id for v, _ in vendor_hits),
                    "vendor_names": ";".join(v.name for v, _ in vendor_hits),
                    "vendor_groups": ";".join(v.group for v, _ in vendor_hits),
                    "confidences": ";".join(c for _, c in vendor_hits),
                    "use_categories": ";".join(categories),
                }
            )
            matched += 1

    with open(totals_path, "w", newline="", encoding="utf-8") as f_totals:
        writer = csv.DictWriter(f_totals, fieldnames=IE_TOTALS_FIELDS)
        writer.writeheader()
        for spender_id, (amount, count) in sorted(spender_totals.items()):
            writer.writerow({"spender_id": spender_id, "total_amount": round(amount, 2), "total_count": count})

    print(
        f"IE  cycle {cycle}: {total:,} rows scanned, {dropped_amended:,} dropped as superseded amendments, "
        f"{matched:,} matched -> {out_path} ; {len(spender_totals):,} spenders totaled -> {totals_path}"
    )
    return matched


def process_coordinated_party_expenditures(cycle: int, taxonomy: Taxonomy, session: requests.Session) -> int:
    cycle_dir = RAW_DIR / str(cycle)
    header = fetch_header("oth", RAW_DIR / "_headers", session)
    idx = {name: i for i, name in enumerate(header)}
    n_fields = len(header)

    src = find_oth_file(cycle_dir)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"pce_matches_{cycle}.csv"
    totals_path = PROCESSED_DIR / f"pce_totals_{cycle}.csv"

    total = 0
    n_pce = 0
    matched = 0
    malformed = 0
    cmte_totals: dict[str, list] = defaultdict(lambda: [0.0, 0])

    with open(src, encoding="latin-1", errors="replace", newline="") as f_in, open(
        out_path, "w", newline="", encoding="utf-8"
    ) as f_out:
        reader = csv.reader(f_in, delimiter="|")
        writer = csv.DictWriter(f_out, fieldnames=PCE_OUT_FIELDS)
        writer.writeheader()

        for row in reader:
            total += 1
            if len(row) < n_fields:
                malformed += 1
                continue
            row = row[:n_fields]

            if row[idx.get("TRANSACTION_TP", -1)] != "24C":
                continue
            n_pce += 1

            cmte_id = row[idx.get("CMTE_ID", -1)] if "CMTE_ID" in idx else ""
            memo_cd = row[idx.get("MEMO_CD", -1)] if "MEMO_CD" in idx else ""
            try:
                amt = float(row[idx.get("TRANSACTION_AMT", -1)]) if "TRANSACTION_AMT" in idx else 0.0
            except ValueError:
                amt = 0.0
            if cmte_id and memo_cd != "X":
                cmte_totals[cmte_id][0] += amt
                cmte_totals[cmte_id][1] += 1

            name = row[idx.get("NAME", -1)] if "NAME" in idx else ""
            memo_text = row[idx.get("MEMO_TEXT", -1)] if "MEMO_TEXT" in idx else ""
            text = f"{name} {memo_text}"
            vendor_hits = taxonomy.match_vendors(text)
            if not vendor_hits:
                continue
            categories = taxonomy.match_categories(memo_text)

            writer.writerow(
                {
                    "cycle": cycle,
                    "cmte_id": cmte_id,
                    "name": name,
                    "city": row[idx.get("CITY", -1)] if "CITY" in idx else "",
                    "state": row[idx.get("STATE", -1)] if "STATE" in idx else "",
                    "transaction_dt": row[idx.get("TRANSACTION_DT", -1)] if "TRANSACTION_DT" in idx else "",
                    "transaction_amt": amt,
                    "memo_text": memo_text,
                    "memo_cd": memo_cd,
                    "cand_id": row[idx.get("OTHER_ID", -1)] if "OTHER_ID" in idx else "",
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
        writer = csv.DictWriter(f_totals, fieldnames=PCE_TOTALS_FIELDS)
        writer.writeheader()
        for cmte_id, (amount, count) in sorted(cmte_totals.items()):
            writer.writerow({"cmte_id": cmte_id, "total_amount": round(amount, 2), "total_count": count})

    print(
        f"PCE cycle {cycle}: {total:,} rows scanned, {n_pce:,} coordinated-party-expenditure (24C) rows, "
        f"{malformed:,} malformed skipped, {matched:,} matched -> {out_path} ; "
        f"{len(cmte_totals):,} committees totaled -> {totals_path}"
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
        process_independent_expenditures(cycle, taxonomy)
        process_coordinated_party_expenditures(cycle, taxonomy, session)


if __name__ == "__main__":
    main()
