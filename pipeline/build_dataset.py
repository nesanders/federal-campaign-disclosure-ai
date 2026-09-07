#!/usr/bin/env python3
"""Join AI-vendor disbursement matches with candidate/committee reference data
and legislator birthdates, then aggregate into the JSON the dashboard reads.

Output: docs/data/dashboard.json (single file, small enough to commit and
to fetch client-side with no backend).

Only "high confidence" vendor-name matches feed the party / incumbency /
chamber / age / use-category / time-series breakdowns, to keep those
comparisons conservative. "Medium confidence" matches (ambiguous words like
"Gemini" or "Copilot") are reported separately in the vendor landscape table
only. See config/vendors.yaml for the confidence rationale.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.reference_data import (  # noqa: E402
    age_bucket,
    load_candidate_master,
    load_committee_candidate_linkage,
    load_committee_master,
    load_legislator_birthdates,
)

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH = ROOT / "docs" / "data" / "dashboard.json"

OFFICE_LABEL = {"H": "House", "S": "Senate", "P": "President"}
ICI_LABEL = {"I": "Incumbent", "C": "Challenger", "O": "Open seat"}


def parse_cycle(cycle: int, session: requests.Session, birthdates: dict[str, str]) -> pd.DataFrame:
    path = PROCESSED_DIR / f"matches_{cycle}.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path} -- run parse_disbursements.py first")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["transaction_amt"] = pd.to_numeric(df["transaction_amt"], errors="coerce").fillna(0.0)

    cand_master = load_candidate_master(cycle, session)
    linkage = load_committee_candidate_linkage(cycle, session)
    cmte_master = load_committee_master(cycle, session)

    def lookup(row):
        cmte_id = row["cmte_id"]
        cand_id = linkage.get(cmte_id)
        cand = cand_master.get(cand_id, {}) if cand_id else {}
        cmte = cmte_master.get(cmte_id, {})
        birth = birthdates.get(cand_id) if cand_id else None
        age = None
        if birth:
            try:
                b = date.fromisoformat(birth)
                age = cycle - b.year
            except ValueError:
                age = None
        return pd.Series(
            {
                "cand_id": cand_id or "",
                "cand_party": cand.get("party", "Unknown") if cand_id else cmte.get("party", "Unknown"),
                "office": OFFICE_LABEL.get(cand.get("office", ""), "Other"),
                "ici": ICI_LABEL.get(cand.get("ici", ""), "Unknown"),
                "age": age,
                "cmte_name": cmte.get("name", ""),
                "cmte_type": cmte.get("type", ""),
            }
        )

    df = pd.concat([df, df.apply(lookup, axis=1)], axis=1)
    return df


def explode_vendors(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (disbursement, vendor) pair."""
    rows = []
    for rec in df.itertuples(index=False):
        ids = rec.vendor_ids.split(";") if rec.vendor_ids else []
        names = rec.vendor_names.split(";") if rec.vendor_names else []
        groups = rec.vendor_groups.split(";") if rec.vendor_groups else []
        confs = rec.confidences.split(";") if rec.confidences else []
        for vid, vname, vgroup, conf in zip(ids, names, groups, confs):
            rows.append(
                {
                    "cycle": rec.cycle,
                    "cand_id": rec.cand_id,
                    "cand_party": rec.cand_party,
                    "office": rec.office,
                    "ici": rec.ici,
                    "age": rec.age,
                    "cmte_id": rec.cmte_id,
                    "cmte_name": rec.cmte_name,
                    "transaction_amt": rec.transaction_amt,
                    "sub_id": rec.sub_id,
                    "use_categories": rec.use_categories,
                    "vendor_id": vid,
                    "vendor_name": vname,
                    "vendor_group": vgroup,
                    "confidence": conf,
                }
            )
    return pd.DataFrame(rows)


def agg_amount_count(df: pd.DataFrame, by: list[str]) -> list[dict]:
    g = df.groupby(by, dropna=False).agg(
        amount=("transaction_amt", "sum"),
        count=("sub_id", "nunique"),
    )
    g["distinct_candidates"] = df[df["cand_id"] != ""].groupby(by, dropna=False)["cand_id"].nunique()
    g["distinct_candidates"] = g["distinct_candidates"].fillna(0).astype(int)
    return g.reset_index().to_dict(orient="records")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", nargs="+", type=int, default=[2020, 2022, 2024, 2026])
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})
    birthdates = load_legislator_birthdates()

    per_cycle = []
    for cycle in args.cycles:
        try:
            per_cycle.append(parse_cycle(cycle, session, birthdates))
        except FileNotFoundError as exc:
            print(f"skip cycle {cycle}: {exc}")
    if not per_cycle:
        raise SystemExit("no cycles available -- run fetch + parse steps first")
    df = pd.concat(per_cycle, ignore_index=True)

    exploded = explode_vendors(df)
    high = exploded[exploded["confidence"] == "high"].copy()
    high["age_bucket"] = high["age"].apply(age_bucket)
    candidate_office = high[high["office"].isin(["House", "Senate"])].copy()

    # --- vendor landscape (all confidence tiers, all committees) ---
    vendor_rows = []
    for (vid, vname, vgroup), sub in exploded.groupby(["vendor_id", "vendor_name", "vendor_group"]):
        hi = sub[sub["confidence"] == "high"]
        med = sub[sub["confidence"] == "medium"]
        vendor_rows.append(
            {
                "id": vid,
                "name": vname,
                "group": vgroup,
                "amount_high": round(float(hi["transaction_amt"].sum()), 2),
                "count_high": int(hi["sub_id"].nunique()),
                "distinct_committees_high": int(hi["cmte_id"].nunique()),
                "amount_medium": round(float(med["transaction_amt"].sum()), 2),
                "count_medium": int(med["sub_id"].nunique()),
            }
        )
    vendor_rows.sort(key=lambda r: r["amount_high"], reverse=True)

    vendor_group_totals = (
        high.groupby("vendor_group")
        .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
        .reset_index()
        .to_dict(orient="records")
    )

    # --- use-case categories (candidate committees, high confidence) ---
    cat_rows = []
    cat_counter = defaultdict(lambda: {"amount": 0.0, "count": 0, "cand_ids": set()})
    for rec in candidate_office.itertuples(index=False):
        cats = rec.use_categories.split(";") if rec.use_categories else ["unspecified"]
        for cat in cats:
            cat_counter[cat]["amount"] += rec.transaction_amt
            cat_counter[cat]["count"] += 1
            if rec.cand_id:
                cat_counter[cat]["cand_ids"].add(rec.cand_id)
    for cat, v in cat_counter.items():
        cat_rows.append(
            {
                "id": cat,
                "amount": round(v["amount"], 2),
                "count": v["count"],
                "distinct_candidates": len(v["cand_ids"]),
            }
        )
    cat_rows.sort(key=lambda r: r["amount"], reverse=True)

    cat_by_group = defaultdict(lambda: {"amount": 0.0, "count": 0})
    for rec in candidate_office.itertuples(index=False):
        cats = rec.use_categories.split(";") if rec.use_categories else ["unspecified"]
        for cat in cats:
            key = (cat, rec.vendor_group)
            cat_by_group[key]["amount"] += rec.transaction_amt
            cat_by_group[key]["count"] += 1
    use_category_by_vendor_group = [
        {"category": cat, "group": group, "amount": round(v["amount"], 2), "count": v["count"]}
        for (cat, group), v in cat_by_group.items()
    ]

    by_party = agg_amount_count(candidate_office, ["cand_party", "vendor_group"])
    by_incumbency = agg_amount_count(candidate_office, ["ici", "vendor_group"])
    by_chamber = agg_amount_count(candidate_office, ["office", "vendor_group"])
    by_age = agg_amount_count(candidate_office, ["age_bucket", "vendor_group"])

    time_series = agg_amount_count(candidate_office, ["cycle", "vendor_group"])
    time_series_by_party = agg_amount_count(candidate_office, ["cycle", "cand_party"])
    time_series_by_incumbency = agg_amount_count(candidate_office, ["cycle", "ici"])
    time_series_by_chamber = agg_amount_count(candidate_office, ["cycle", "office"])

    top_committees = (
        exploded[exploded["confidence"] == "high"]
        .groupby(["cmte_id", "cmte_name"])
        .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
        .reset_index()
        .sort_values("amount", ascending=False)
        .head(25)
        .to_dict(orient="records")
    )

    openai_2026_candidates = (
        candidate_office[(candidate_office["cycle"] == 2026) & (candidate_office["vendor_id"] == "openai")]["cand_id"]
        .nunique()
    )

    row_counts = {}
    for cycle in args.cycles:
        p = PROCESSED_DIR / f"matches_{cycle}.csv"
        if p.exists():
            row_counts[cycle] = int(sum(1 for _ in open(p, encoding="utf-8")) - 1)

    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "cycles": args.cycles,
        "sources": [
            "FEC bulk data: itemized operating expenditures (Schedule B / oppexp)",
            "FEC bulk data: candidate master (cn)",
            "FEC bulk data: candidate-committee linkage (ccl)",
            "FEC bulk data: committee master (cm)",
            "unitedstates/congress-legislators (birthdates, for age analysis)",
        ],
        "matched_row_counts_by_cycle": row_counts,
        "openai_high_confidence_house_senate_candidates_2026": int(openai_2026_candidates),
        "methodology_notes": [
            "Vendor matches are text matches against payee name, disbursement purpose, category description, and memo text -- not a review of underlying documents. See config/vendors.yaml for the full pattern list and its provenance.",
            "'High confidence' matches use unambiguous vendor/product names (e.g. 'OpenAI', 'ChatGPT', 'Quiller'). 'Medium confidence' matches use ambiguous words (e.g. 'Gemini', 'Copilot', 'Grok', 'Claude') that also have common non-AI meanings; these are shown only in the vendor landscape view and excluded from the party/incumbency/chamber/age/use-case/time-series breakdowns.",
            "Party, chamber, and incumbency breakdowns are limited to disbursements by House and Senate candidate committees (linked via FEC candidate-committee linkage files), high-confidence vendor matches only.",
            "Candidate age is drawn from the unitedstates/congress-legislators project, which covers people who have served in Congress. Non-incumbent challengers who have never held office are not in that dataset and are bucketed as 'Unknown' rather than estimated.",
            "As in the Washington Post's original analysis, disclosed AI spending understates actual usage: campaigns can pay for AI tools through corporate cards, staff reimbursements, or consultants without the underlying vendor ever appearing in disbursement text.",
            "A single disbursement can match more than one vendor or more than one use-case category (e.g. a payment memo mentioning both 'ChatGPT' and 'email drafting'); category and vendor totals are not mutually exclusive and will not sum to a single grand total.",
        ],
    }

    out = {
        "meta": meta,
        "vendors_overall": vendor_rows,
        "vendor_group_totals": vendor_group_totals,
        "use_categories": cat_rows,
        "use_category_by_vendor_group": use_category_by_vendor_group,
        "by_party": by_party,
        "by_incumbency": by_incumbency,
        "by_chamber": by_chamber,
        "by_age_bucket": by_age,
        "time_series": time_series,
        "time_series_by_party": time_series_by_party,
        "time_series_by_incumbency": time_series_by_incumbency,
        "time_series_by_chamber": time_series_by_chamber,
        "top_committees": top_committees,
        "office_labels": OFFICE_LABEL,
        "ici_labels": ICI_LABEL,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
