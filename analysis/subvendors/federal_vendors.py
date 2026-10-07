#!/usr/bin/env python3
"""Aggregate every federal committee payee (FEC Schedule B / oppexp, all four
cycles) into one row per normalized vendor name.

This is the "federal vendor" side of the subvendor analysis: who federal
campaigns pay, how much, and which of the top AI-using candidates (see
FOCUS_CANDIDATES) use each vendor. state_subvendors.py then looks these same
vendors up in California and Massachusetts filings, which -- unlike the FEC --
require a vendor's own downstream payments to be disclosed.

Memo entries (MEMO_CD = X) are excluded from totals so a lump-sum payment
and its own itemized breakdown aren't double-counted. Payees reported as
individuals (ENTITY_TP = IND, mostly staff and reimbursements) are dropped.

Output: analysis/subvendors/out/federal_vendors.csv
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from names import brand_key, normalize_vendor  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = Path(__file__).resolve().parent / "out"
CYCLES = [2020, 2022, 2024, 2026]

OPPEXP_COLS = [
    "CMTE_ID", "AMNDT_IND", "RPT_YR", "RPT_TP", "IMAGE_NUM", "LINE_NUM", "FORM_TP_CD", "SCHED_TP_CD",
    "NAME", "CITY", "STATE", "ZIP_CODE", "TRANSACTION_DT", "TRANSACTION_AMT", "TRANSACTION_PGI",
    "PURPOSE", "CATEGORY", "CATEGORY_DESC", "MEMO_CD", "MEMO_TEXT", "ENTITY_TP", "SUB_ID", "FILE_NUM",
    "TRAN_ID", "BACK_REF_TRAN_ID",
]

# The 12 individual candidates examined in the AI-usage-vs-public-statements
# research, keyed by FEC candidate ID.
FOCUS_CANDIDATES = {
    "S0AZ00350": "Mark Kelly",
    "S4CA00555": "Adam Schiff",
    "H0CA27085": "Adam Schiff",
    "S4VT00033": "Bernie Sanders",
    "P60007168": "Bernie Sanders",
    "P80000722": "Joe Biden",
    "P80001571": "Donald Trump",
    "S6MI00418": "Abdul El-Sayed",
    "S4AR00103": "Tom Cotton",
    "H2NY17162": "Mike Lawler",
    "S4AK00214": "Dan Sullivan",
    "S4LA00065": "John Kennedy",
    "P40011793": "RFK Jr.",
    "H8MN05239": "Ilhan Omar",
}


def load_committee_candidates() -> dict[str, str]:
    """CMTE_ID -> CAND_ID, from every cycle's candidate-committee linkage."""
    out: dict[str, str] = {}
    for cycle in CYCLES:
        with open(RAW / str(cycle) / "ccl.txt", encoding="latin-1") as f:
            for line in f:
                p = line.rstrip("\n").split("|")
                if len(p) >= 4:
                    out[p[3]] = p[0]
    return out


def load_committee_names() -> dict[str, str]:
    out: dict[str, str] = {}
    for cycle in CYCLES:
        with open(RAW / str(cycle) / "cm.txt", encoding="latin-1") as f:
            for line in f:
                p = line.rstrip("\n").split("|")
                if len(p) >= 2:
                    out[p[0]] = p[1]
    return out


def merge_name_variants(agg: dict[str, dict]) -> dict[str, tuple[str, float]]:
    """Fold name variants of one firm ("MIDDLE SEAT", "MIDDLE SEAT CONSULTING",
    "MIDDLE SEAT DIGITAL") into the variant with the most spending, when they
    share a brand_key AND the same most-common vendor state. Mutates agg;
    returns {variant_key: (canonical_key, variant_amount)}."""
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for key, a in agg.items():
        groups[(brand_key(key), a["states"].most_common(1)[0][0])].append(key)
    aliases: dict[str, tuple[str, float]] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        canonical = max(members, key=lambda k: agg[k]["amount"])
        target = agg[canonical]
        for k in members:
            if k == canonical:
                continue
            a = agg.pop(k)
            aliases[k] = (canonical, a["amount"])
            target["amount"] += a["amount"]
            target["records"] += a["records"]
            target["committees"] |= a["committees"]
            target["cycles"] |= a["cycles"]
            for field in ("raw_names", "purposes", "focus", "states"):
                target[field].update(a[field])
    return aliases


def main() -> None:
    cmte_cand = load_committee_candidates()
    cmte_name = load_committee_names()

    agg: dict[str, dict] = defaultdict(lambda: {
        "amount": 0.0, "records": 0, "committees": set(), "cycles": set(),
        "raw_names": Counter(), "purposes": Counter(), "focus": Counter(), "states": Counter(),
    })

    for cycle in CYCLES:
        path = RAW / str(cycle) / "oppexp.txt"
        with open(path, encoding="latin-1") as f:
            for line in f:
                p = line.rstrip("\n").split("|")
                if len(p) < len(OPPEXP_COLS) - 2:
                    continue
                row = dict(zip(OPPEXP_COLS, p))
                if row["MEMO_CD"] == "X" or row["ENTITY_TP"] == "IND":
                    continue
                key = normalize_vendor(row["NAME"])
                if not key:
                    continue
                try:
                    amt = float(row["TRANSACTION_AMT"] or 0)
                except ValueError:
                    continue
                a = agg[key]
                a["amount"] += amt
                a["records"] += 1
                a["committees"].add(row["CMTE_ID"])
                a["cycles"].add(cycle)
                a["raw_names"][row["NAME"].strip()] += 1
                a["states"][row["STATE"]] += 1
                if row["PURPOSE"]:
                    a["purposes"][row["PURPOSE"].strip().upper()] += amt
                cand = cmte_cand.get(row["CMTE_ID"])
                if cand in FOCUS_CANDIDATES:
                    a["focus"][FOCUS_CANDIDATES[cand]] += amt

    OUT.mkdir(parents=True, exist_ok=True)
    aliases = merge_name_variants(agg)
    with open(OUT / "name_merges.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["variant_key", "merged_into", "variant_amount"])
        for variant, (canonical, amt) in sorted(aliases.items(), key=lambda kv: -kv[1][1]):
            w.writerow([variant, canonical, round(amt, 2)])

    rows = sorted(agg.items(), key=lambda kv: -kv[1]["amount"])
    with open(OUT / "federal_vendors.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "vendor_key", "display_name", "federal_amount", "records", "committees", "cycles",
            "vendor_state", "top_purposes", "focus_candidates", "focus_amount", "sample_committees",
        ])
        for key, a in rows:
            if a["amount"] < 10000:
                break
            top_purposes = "; ".join(p for p, _ in a["purposes"].most_common(3))
            focus = "; ".join(f"{n} (${v:,.0f})" for n, v in a["focus"].most_common())
            sample = "; ".join(sorted(cmte_name.get(c, c) for c in list(a["committees"])[:5]))
            w.writerow([
                key, a["raw_names"].most_common(1)[0][0], round(a["amount"], 2), a["records"],
                len(a["committees"]), " ".join(map(str, sorted(a["cycles"]))),
                a["states"].most_common(1)[0][0], top_purposes, focus,
                round(sum(a["focus"].values()), 2), sample,
            ])
    print(f"{sum(1 for _, a in rows if a['amount'] >= 10000):,} federal vendors with >= $10,000 -> {OUT / 'federal_vendors.csv'}")


if __name__ == "__main__":
    main()
