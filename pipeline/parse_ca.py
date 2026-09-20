#!/usr/bin/env python3
"""Match raw California CAL-ACCESS EXPN records against the AI vendor
taxonomy, and separately total each filer's total reported spend by year.

Reads data/raw/ca/expn.jsonl (produced by fetch_ca.py, already filtered
to 2023+) and writes data/processed/ca_matches.csv,
data/processed/ca_filer_totals.csv, and
data/processed/ca_filer_year_totals.csv -- the common intermediate
schema pipeline/lib/build_state_dataset.py expects.

Matches against the concatenation of `EXPN_DSCR` (free-text purpose) and
the payee name (`PAYEE_NAML`/`PAYEE_NAMF`).

One real, documented gap versus Washington and Massachusetts:
  - No party field. Like Colorado, CAL-ACCESS's raw EXPN table carries no
    party affiliation for a filer; every record's `party` here is left
    blank (-> "Unknown" in the shared aggregator).

Filer identity: EXPN_CD's own CMTE_ID column is blank on nearly all
rows (verified empirically -- CAL-ACCESS records an expenditure's
filer on the filing's cover page, not the line item itself), so this
reads data/raw/ca/filer_lookup.json (produced by fetch_ca_filers.py
from CVR_CAMPAIGN_DISCLOSURE_CD.TSV, keyed by FILING_ID) to resolve
each record's real filer_id/filer_name. A FILING_ID missing from that
lookup (a cover page CAL-ACCESS never got, or one filed under a
different table -- e.g. F450/F465 short forms) falls back to EXPN's
own CAND_NAML, then "Committee <FILING_ID>".

Empirically the single largest false-positive source in this dataset:
68.6% of all CA EXPN rows are ActBlue "Earmarked Contribution from:
LASTNAME, FIRSTNAME" passthrough boilerplate (small-dollar donations
routed through a committee to their intended candidate). That FIRSTNAME
is a donor's own name, never a real purpose description, and routinely
collides with a bare vendor pattern purely by coincidence -- confirmed
empirically for "CLAUDE" (a real, if uncommon, first name; 257 of CA's
initial 266 Anthropic matches were donors literally named Claude),
"XAI" (a Hmong given name), "GEMINIGURL" (contains "gemini"), and
"QUILLER"/"VAN HEYGEN" (surnames containing "quiller"/"heygen"). This
text can never legitimately reference an AI vendor, so it's excluded
from matching entirely below rather than chased with more per-vendor
name excludes.
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
RAW_DIR = ROOT / "data" / "raw" / "ca"
PROCESSED_DIR = ROOT / "data" / "processed"

# ActBlue passthrough boilerplate -- see module docstring. The donor's
# own name follows this prefix and is never a real purpose description.
EARMARK_PREFIX = "earmarked contribution from"

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
    first = (row.get("PAYEE_NAMF") or "").strip()
    last = (row.get("PAYEE_NAML") or "").strip()
    if first and last:
        return f"{first} {last}"
    return last or first


def _fallback_filer_name(row: dict, filing_id: str) -> str:
    first = (row.get("CAND_NAMF") or "").strip()
    last = (row.get("CAND_NAML") or "").strip()
    if first and last:
        return f"{first} {last}"
    if last:
        return last
    return f"Committee {filing_id}" if filing_id else "Unknown committee"


def _amount(row: dict) -> float:
    try:
        return float(str(row.get("AMOUNT", "0")).replace("$", "").replace(",", "") or 0)
    except ValueError:
        return 0.0


def _date(row: dict) -> str:
    # "M/D/YYYY H:MM:SS AM/PM" -> "YYYY-MM-DD"
    raw = (row.get("EXPN_DATE") or "").strip()
    if not raw:
        return ""
    try:
        date_part = raw.split(" ")[0]
        m, d, y = date_part.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except (ValueError, IndexError):
        return ""


def main() -> None:
    taxonomy = Taxonomy()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    src = RAW_DIR / "expn.jsonl"
    if not src.exists():
        print(f"{src} not found -- run fetch_ca.py first.", file=sys.stderr)
        sys.exit(1)

    lookup_path = RAW_DIR / "filer_lookup.json"
    if not lookup_path.exists():
        print(f"{lookup_path} not found -- run fetch_ca_filers.py first.", file=sys.stderr)
        sys.exit(1)
    with open(lookup_path, encoding="utf-8") as f:
        filer_lookup: dict[str, dict] = json.load(f)

    out_path = PROCESSED_DIR / "ca_matches.csv"
    filer_totals_path = PROCESSED_DIR / "ca_filer_totals.csv"
    filer_year_totals_path = PROCESSED_DIR / "ca_filer_year_totals.csv"

    total = 0
    matched = 0
    filers_seen: set[str] = set()
    seen_ids: set = set()
    filer_year_totals: dict[tuple[str, int], float] = defaultdict(float)

    with open(src, encoding="utf-8") as f_in, open(out_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=OUT_FIELDS)
        writer.writeheader()

        for line in f_in:
            row = json.loads(line)
            total += 1
            filing_id = (row.get("FILING_ID") or "").strip()
            cover = filer_lookup.get(filing_id)
            filer_id = (cover["filer_id"] if cover else "") or (row.get("CMTE_ID") or "")
            filer_name = cover["filer_name"] if cover else _fallback_filer_name(row, filing_id)
            filer_key = filer_id or filer_name
            filers_seen.add(filer_key)

            date = _date(row)
            amount = _amount(row)
            if date:
                try:
                    year = int(date[:4])
                    filer_year_totals[(filer_key, year)] += amount
                except ValueError:
                    pass

            payee = _payee_name(row)
            purpose = row.get("EXPN_DSCR") or ""
            match_purpose = "" if purpose.strip().lower().startswith(EARMARK_PREFIX) else purpose
            text = f"{match_purpose} {payee}"
            vendor_hits = taxonomy.match_vendors(text)
            if not vendor_hits:
                continue

            rec_id = f"{row.get('FILING_ID')}-{row.get('LINE_ITEM')}-{row.get('TRAN_ID')}"
            if rec_id in seen_ids:
                continue
            seen_ids.add(rec_id)

            office = row.get("OFFIC_DSCR") or row.get("JURIS_DSCR") or ""
            writer.writerow(
                {
                    "record_id": rec_id,
                    "filer_id": filer_key,
                    "filer_name": filer_name,
                    "party": "",
                    "date": date,
                    "amount": amount,
                    "payee_display": payee,
                    "purpose_display": purpose,
                    "office": office,
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

    print(f"CA: {total:,} records scanned, {matched:,} matched, {len(filers_seen):,} distinct filers -> {out_path}")


if __name__ == "__main__":
    main()
