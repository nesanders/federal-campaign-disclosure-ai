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

This also computes, for every committee that has at least one AI-vendor
disbursement, its total reported operating expenditure that cycle (from
totals_{cycle}.csv, produced by parse_disbursements.py from the SAME
oppexp file in the same pass), so the dashboard can show AI spend as a
share of total spend -- not just a raw dollar figure that says nothing
about how big AI spend is relative to everything else a campaign pays for.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.reference_data import (  # noqa: E402
    age_bucket,
    load_candidate_master,
    load_committee_candidate_linkage,
    load_committee_master,
    load_legislator_birthdates,
)
from lib.vendor_match import Taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH = ROOT / "docs" / "data" / "dashboard.json"

OFFICE_LABEL = {"H": "House", "S": "Senate", "P": "President"}
ICI_LABEL = {"I": "Incumbent", "C": "Challenger", "O": "Open seat"}
CURRENT_CYCLE = 2026
TOP_N_VENDOR_CANDIDATES = 30
TOP_N_VENDOR_COMMITTEES = 20


def load_committee_totals(cycle: int) -> dict[str, float]:
    """CMTE_ID -> total reported operating expenditure that cycle (memo
    entries excluded -- see parse_disbursements.py for why)."""
    path = PROCESSED_DIR / f"totals_{cycle}.csv"
    out: dict[str, float] = {}
    if not path.exists():
        return out
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                out[row["cmte_id"]] = float(row["total_amount"])
            except (KeyError, ValueError):
                continue
    return out


def high_ids(vendor_ids: str, confidences: str) -> list[str]:
    if not vendor_ids:
        return []
    return [v for v, c in zip(vendor_ids.split(";"), confidences.split(";")) if c == "high"]


def high_ids_ex_legacy(high_vendor_ids: list[str], era_by_id: dict) -> list[str]:
    return [v for v in high_vendor_ids if era_by_id.get(v, "generative") != "legacy"]


def parse_cycle(cycle: int, session: requests.Session, birthdates: dict[str, str]) -> pd.DataFrame:
    path = PROCESSED_DIR / f"matches_{cycle}.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path} -- run parse_disbursements.py first")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["transaction_amt"] = pd.to_numeric(df["transaction_amt"], errors="coerce").fillna(0.0)
    df["cycle"] = pd.to_numeric(df["cycle"], errors="coerce").astype("Int64")
    df["is_high"] = df["confidences"].apply(lambda s: "high" in s.split(";") if s else False)
    df["high_vendor_ids"] = df.apply(lambda r: high_ids(r["vendor_ids"], r["confidences"]), axis=1)

    cand_master = load_candidate_master(cycle, session)
    linkage = load_committee_candidate_linkage(cycle, session)
    cmte_master = load_committee_master(cycle, session)
    cmte_totals = load_committee_totals(cycle)

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
                "cand_name": cand.get("name", "") if cand_id else "",
                "cand_party": cand.get("party", "Unknown") if cand_id else cmte.get("party", "Unknown"),
                "office": OFFICE_LABEL.get(cand.get("office", ""), "Other"),
                "ici": ICI_LABEL.get(cand.get("ici", ""), "Unknown"),
                "cand_state": cand.get("state", "") if cand_id else "",
                "cand_district": (cand.get("district") or "").lstrip("0") or "00" if cand_id else "",
                "age": age,
                "cmte_name": cmte.get("name", ""),
                "cmte_type": cmte.get("type", ""),
                "cmte_total_expenditure": cmte_totals.get(cmte_id, 0.0),
            }
        )

    df = pd.concat([df, df.apply(lookup, axis=1)], axis=1)
    return df


def load_universe_totals(cycle: int, session: requests.Session, birthdates: dict[str, str]) -> pd.DataFrame:
    """Per-candidate total reported expenditure for EVERY House/Senate
    candidate with a linked committee that cycle -- regardless of whether
    they show any AI-vendor spend. This is the denominator for "AI spend as
    a share of total spend" aggregates: it answers "how big is AI spend
    relative to everything these candidates raised and spent," not just
    relative to the AI-flagged committees themselves.
    """
    cand_master = load_candidate_master(cycle, session)
    linkage = load_committee_candidate_linkage(cycle, session)
    totals = load_committee_totals(cycle)

    per_cand: dict[str, float] = defaultdict(float)
    for cmte_id, amt in totals.items():
        cand_id = linkage.get(cmte_id)
        if not cand_id:
            continue
        cand = cand_master.get(cand_id)
        if not cand or cand.get("office") not in ("H", "S"):
            continue
        per_cand[cand_id] += amt

    rows = []
    for cand_id, total_amt in per_cand.items():
        cand = cand_master[cand_id]
        birth = birthdates.get(cand_id)
        age = None
        if birth:
            try:
                age = cycle - date.fromisoformat(birth).year
            except ValueError:
                age = None
        rows.append(
            {
                "cycle": cycle,
                "cand_id": cand_id,
                "cand_party": cand.get("party", "Unknown"),
                "office": OFFICE_LABEL.get(cand.get("office", ""), "Other"),
                "ici": ICI_LABEL.get(cand.get("ici", ""), "Unknown"),
                "age_bucket": age_bucket(age),
                "total_expenditure": total_amt,
            }
        )
    return pd.DataFrame(rows)


def explode_vendors(df: pd.DataFrame, era_by_id: dict) -> pd.DataFrame:
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
                    "cand_name": rec.cand_name,
                    "cand_party": rec.cand_party,
                    "office": rec.office,
                    "ici": rec.ici,
                    "cand_state": rec.cand_state,
                    "cand_district": rec.cand_district,
                    "age": rec.age,
                    "cmte_id": rec.cmte_id,
                    "cmte_name": rec.cmte_name,
                    "transaction_amt": rec.transaction_amt,
                    "sub_id": rec.sub_id,
                    "use_categories": rec.use_categories,
                    "vendor_id": vid,
                    "vendor_name": vname,
                    "vendor_group": vgroup,
                    "vendor_era": era_by_id.get(vid, "generative"),
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


def rename_key(rows: list[dict], old: str, new: str) -> list[dict]:
    for row in rows:
        row[new] = row.pop(old)
    return rows


def attach_totals(rows: list[dict], key_fields: list[str], totals: dict, out_field: str = "total_expenditure") -> None:
    """Mutate `rows` in place, adding a total-expenditure denominator looked
    up by `key_fields` (a tuple of 1 field is passed as the bare value, not
    a 1-tuple, to match how pandas groupby collapses single-key results)."""
    for row in rows:
        key = tuple(row[f] for f in key_fields)
        if len(key) == 1:
            key = key[0]
        row[out_field] = round(float(totals.get(key, 0.0)), 2)


def build_committee_cycle_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (cycle, committee) among AI-flagged committees, deduped
    so summing `cmte_total_expenditure` doesn't multiply it by however many
    AI disbursement rows that committee happens to have."""
    cols = [
        "cycle", "cmte_id", "cand_id", "cand_party", "office", "ici", "age",
        "cmte_total_expenditure",
    ]
    cc = df.drop_duplicates(subset=["cycle", "cmte_id"])[cols].copy()
    cc["age_bucket"] = cc["age"].apply(age_bucket)
    return cc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", nargs="+", type=int, default=[2020, 2022, 2024, 2026])
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})
    birthdates = load_legislator_birthdates()

    per_cycle = []
    universe_per_cycle = []
    for cycle in args.cycles:
        try:
            per_cycle.append(parse_cycle(cycle, session, birthdates))
        except FileNotFoundError as exc:
            print(f"skip cycle {cycle}: {exc}")
            continue
        universe_per_cycle.append(load_universe_totals(cycle, session, birthdates))
    if not per_cycle:
        raise SystemExit("no cycles available -- run fetch + parse steps first")
    df = pd.concat(per_cycle, ignore_index=True)
    universe = pd.concat(universe_per_cycle, ignore_index=True)
    universe_by_cand = universe.groupby("cand_id", as_index=False).agg(
        {"cand_party": "first", "office": "first", "ici": "first", "age_bucket": "first",
         "total_expenditure": "sum", "cycle": "first"}
    )

    # `era` tags each vendor as "generative" (built on modern LLM/diffusion/
    # voice-clone AI) or "legacy" (an "AI"-branded company that predates the
    # generative-AI wave, e.g. Amplify.ai/TruVerse, Prompt.io, CallTime.AI --
    # see config/vendors.yaml). Charts/tables default to excluding legacy
    # vendors; the dashboard has a toggle to include them back in.
    taxonomy_vendors = Taxonomy().vendors
    homepage_by_id = {v.id: v.homepage for v in taxonomy_vendors}
    era_by_id = {v.id: v.era for v in taxonomy_vendors}
    df["high_vendor_ids_ex_legacy"] = df["high_vendor_ids"].apply(lambda ids: high_ids_ex_legacy(ids, era_by_id))
    df["is_high_ex_legacy"] = df["high_vendor_ids_ex_legacy"].apply(bool)

    exploded = explode_vendors(df, era_by_id)
    high = exploded[exploded["confidence"] == "high"].copy()
    high["age_bucket"] = high["age"].apply(age_bucket)
    high_ex_legacy = high[high["vendor_era"] != "legacy"].copy()
    candidate_office = high[high["office"].isin(["House", "Senate"])].copy()
    cc_table = build_committee_cycle_table(df)
    cc_office = cc_table[cc_table["office"].isin(["House", "Senate"])].copy()

    # 2026-only slice, matching the "how does AI use differ" section's scope
    # (the time-series section separately covers change across cycles).
    candidate_2026 = candidate_office[candidate_office["cycle"] == CURRENT_CYCLE]
    cc_office_2026 = cc_office[cc_office["cycle"] == CURRENT_CYCLE]
    universe_2026 = universe_by_cand[universe_by_cand["cycle"] == CURRENT_CYCLE]

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
                "era": era_by_id.get(vid, "generative"),
                "homepage": homepage_by_id.get(vid),
                "amount_high": round(float(hi["transaction_amt"].sum()), 2),
                "count_high": int(hi["sub_id"].nunique()),
                "distinct_committees_high": int(hi["cmte_id"].nunique()),
                "amount_medium": round(float(med["transaction_amt"].sum()), 2),
                "count_medium": int(med["sub_id"].nunique()),
            }
        )
    vendor_rows.sort(key=lambda r: r["amount_high"], reverse=True)

    vendor_group_totals = (
        high.groupby(["vendor_group", "vendor_era"])
        .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
        .reset_index()
        .rename(columns={"vendor_era": "era"})
        .to_dict(orient="records")
    )

    # --- use-case categories (candidate committees, high confidence, all cycles) ---
    # Keyed by (category, era) so the dashboard can sum only non-legacy rows
    # by default and include legacy-era vendors when the toggle is on.
    cat_rows = []
    cat_counter = defaultdict(lambda: {"amount": 0.0, "count": 0, "cand_ids": set()})
    for rec in candidate_office.itertuples(index=False):
        cats = rec.use_categories.split(";") if rec.use_categories else ["unspecified"]
        for cat in cats:
            key = (cat, rec.vendor_era)
            cat_counter[key]["amount"] += rec.transaction_amt
            cat_counter[key]["count"] += 1
            if rec.cand_id:
                cat_counter[key]["cand_ids"].add(rec.cand_id)
    for (cat, era), v in cat_counter.items():
        cat_rows.append(
            {
                "id": cat,
                "era": era,
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
            key = (cat, rec.vendor_group, rec.vendor_era)
            cat_by_group[key]["amount"] += rec.transaction_amt
            cat_by_group[key]["count"] += 1
    use_category_by_vendor_group = [
        {"category": cat, "group": group, "era": era, "amount": round(v["amount"], 2), "count": v["count"]}
        for (cat, group, era), v in cat_by_group.items()
    ]

    # --- breakdowns (2026 cycle only) with pct-of-total denominators ---
    by_party = rename_key(agg_amount_count(candidate_2026, ["cand_party", "vendor_group", "vendor_era"]), "vendor_era", "era")
    by_incumbency = rename_key(agg_amount_count(candidate_2026, ["ici", "vendor_group", "vendor_era"]), "vendor_era", "era")
    by_chamber = rename_key(agg_amount_count(candidate_2026, ["office", "vendor_group", "vendor_era"]), "vendor_era", "era")
    by_age = rename_key(agg_amount_count(candidate_2026, ["age_bucket", "vendor_group", "vendor_era"]), "vendor_era", "era")

    attach_totals(by_party, ["cand_party"], universe_2026.groupby("cand_party")["total_expenditure"].sum().to_dict())
    attach_totals(by_incumbency, ["ici"], universe_2026.groupby("ici")["total_expenditure"].sum().to_dict())
    attach_totals(by_chamber, ["office"], universe_2026.groupby("office")["total_expenditure"].sum().to_dict())
    attach_totals(by_age, ["age_bucket"], universe_2026.groupby("age_bucket")["total_expenditure"].sum().to_dict())

    # --- time series (all cycles) with pct-of-total denominators ---
    time_series = rename_key(agg_amount_count(candidate_office, ["cycle", "vendor_group", "vendor_era"]), "vendor_era", "era")
    time_series_by_party = rename_key(agg_amount_count(candidate_office, ["cycle", "cand_party", "vendor_era"]), "vendor_era", "era")
    time_series_by_incumbency = rename_key(agg_amount_count(candidate_office, ["cycle", "ici", "vendor_era"]), "vendor_era", "era")
    time_series_by_chamber = rename_key(agg_amount_count(candidate_office, ["cycle", "office", "vendor_era"]), "vendor_era", "era")

    univ_cycle = universe_by_cand.groupby("cycle")["total_expenditure"].sum().to_dict()
    univ_cycle_party = universe_by_cand.groupby(["cycle", "cand_party"])["total_expenditure"].sum().to_dict()
    univ_cycle_ici = universe_by_cand.groupby(["cycle", "ici"])["total_expenditure"].sum().to_dict()
    univ_cycle_office = universe_by_cand.groupby(["cycle", "office"])["total_expenditure"].sum().to_dict()
    attach_totals(time_series, ["cycle"], univ_cycle)
    attach_totals(time_series_by_party, ["cycle", "cand_party"], univ_cycle_party)
    attach_totals(time_series_by_incumbency, ["cycle", "ici"], univ_cycle_ici)
    attach_totals(time_series_by_chamber, ["cycle", "office"], univ_cycle_office)

    def top_committees_table(source: pd.DataFrame) -> list[dict]:
        return (
            source.groupby(["cmte_id", "cmte_name"])
            .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
            .reset_index()
            .sort_values("amount", ascending=False)
            .head(25)
            .to_dict(orient="records")
        )

    # Default (legacy vendors excluded) and "all eras" (toggle-on) variants,
    # each independently ranked/truncated to the top 25 -- which committees
    # place in the top 25 can differ between the two, not just their amounts.
    top_committees = top_committees_table(high_ex_legacy)
    top_committees_all_eras = top_committees_table(high)

    openai_2026_candidates = candidate_2026[candidate_2026["vendor_id"] == "openai"]["cand_id"].nunique()

    # --- entity leaderboard: one row per (cycle, candidate-or-committee) ---
    # Two-pass so a candidate with more than one linked committee isn't
    # double-counted: first collapse to one row per (cycle, committee),
    # then combine committees that map to the same candidate.
    df["entity_id"] = df["cand_id"].where(df["cand_id"] != "", df["cmte_id"])
    df["entity_type"] = df["cand_id"].apply(lambda c: "candidate" if c else "committee")
    df["entity_name"] = df["cand_name"].where(df["cand_id"] != "", df["cmte_name"])

    # Built from two separately-computed pieces rather than one .agg() call
    # mixing a custom lambda with several named "first" aggregations: that
    # combination was observed to silently corrupt column dtypes/alignment
    # (a numeric "first" column coming back as strings, and even shuffled
    # values) on pandas 3.0.5. Plain single-purpose groupbys are reliable.
    high_df = df[df["is_high"]]
    high_sum = high_df.groupby(["cycle", "cmte_id"])["transaction_amt"].sum()
    high_count = high_df.groupby(["cycle", "cmte_id"]).size()
    high_ex_legacy_df = df[df["is_high_ex_legacy"]]
    high_ex_legacy_sum = high_ex_legacy_df.groupby(["cycle", "cmte_id"])["transaction_amt"].sum()
    high_ex_legacy_count = high_ex_legacy_df.groupby(["cycle", "cmte_id"]).size()
    attrs = df.drop_duplicates(subset=["cycle", "cmte_id"]).set_index(["cycle", "cmte_id"])[
        ["entity_id", "entity_type", "entity_name", "cand_party", "office", "ici", "cand_state", "cand_district", "cmte_total_expenditure"]
    ]
    per_cmte = attrs.copy()
    per_cmte["ai_amount_high"] = high_sum.reindex(per_cmte.index).fillna(0.0)
    per_cmte["ai_count_high"] = high_count.reindex(per_cmte.index).fillna(0).astype(int)
    per_cmte["ai_amount_high_ex_legacy"] = high_ex_legacy_sum.reindex(per_cmte.index).fillna(0.0)
    per_cmte["ai_count_high_ex_legacy"] = high_ex_legacy_count.reindex(per_cmte.index).fillna(0).astype(int)
    per_cmte["cmte_total_expenditure"] = pd.to_numeric(per_cmte["cmte_total_expenditure"], errors="coerce").fillna(0.0)
    per_cmte = per_cmte.reset_index()

    high_cats_by_cmte = defaultdict(set)
    high_vendors_by_cmte = defaultdict(set)
    high_cats_by_cmte_ex_legacy = defaultdict(set)
    high_vendors_by_cmte_ex_legacy = defaultdict(set)
    for rec in df.itertuples(index=False):
        if not rec.is_high:
            continue
        key = (rec.cycle, rec.cmte_id)
        cats = rec.use_categories.split(";") if rec.use_categories else []
        high_cats_by_cmte[key].update(cats)
        high_vendors_by_cmte[key].update(rec.high_vendor_ids)
        if rec.is_high_ex_legacy:
            high_cats_by_cmte_ex_legacy[key].update(cats)
            high_vendors_by_cmte_ex_legacy[key].update(rec.high_vendor_ids_ex_legacy)

    ent_sums = per_cmte.groupby(["cycle", "entity_id"])[
        ["ai_amount_high", "ai_count_high", "ai_amount_high_ex_legacy", "ai_count_high_ex_legacy", "cmte_total_expenditure"]
    ].sum()
    ent_attrs = (
        per_cmte.drop_duplicates(subset=["cycle", "entity_id"])
        .set_index(["cycle", "entity_id"])[["entity_type", "entity_name", "cand_party", "office", "ici", "cand_state", "cand_district"]]
    )
    entities = ent_attrs.join(ent_sums).rename(columns={"cmte_total_expenditure": "total_expenditure"}).reset_index()

    cmte_keys = {(r.cycle, r.cmte_id): (r.cycle, r.entity_id) for r in per_cmte.itertuples(index=False)}
    ent_cats: dict[tuple, set] = defaultdict(set)
    ent_vendors: dict[tuple, set] = defaultdict(set)
    ent_cats_ex_legacy: dict[tuple, set] = defaultdict(set)
    ent_vendors_ex_legacy: dict[tuple, set] = defaultdict(set)
    for (cycle, cmte_id), cats in high_cats_by_cmte.items():
        ent_cats[cmte_keys[(cycle, cmte_id)]] |= cats
    for (cycle, cmte_id), vids in high_vendors_by_cmte.items():
        ent_vendors[cmte_keys[(cycle, cmte_id)]] |= vids
    for (cycle, cmte_id), cats in high_cats_by_cmte_ex_legacy.items():
        ent_cats_ex_legacy[cmte_keys[(cycle, cmte_id)]] |= cats
    for (cycle, cmte_id), vids in high_vendors_by_cmte_ex_legacy.items():
        ent_vendors_ex_legacy[cmte_keys[(cycle, cmte_id)]] |= vids

    entity_rows = []
    for rec in entities.itertuples(index=False):
        if rec.ai_amount_high <= 0:
            continue
        key = (rec.cycle, rec.entity_id)
        pct = (rec.ai_amount_high / rec.total_expenditure * 100) if rec.total_expenditure > 0 else None
        pct_ex_legacy = (
            (rec.ai_amount_high_ex_legacy / rec.total_expenditure * 100) if rec.total_expenditure > 0 else None
        )
        entity_rows.append(
            {
                "cycle": int(rec.cycle),
                "entity_id": rec.entity_id,
                "entity_type": rec.entity_type,
                "entity_name": rec.entity_name,
                "cand_party": rec.cand_party,
                "office": rec.office,
                "ici": rec.ici,
                "cand_state": rec.cand_state,
                "cand_district": rec.cand_district,
                "ai_amount_high": round(float(rec.ai_amount_high), 2),
                "ai_count_high": int(rec.ai_count_high),
                "ai_amount_high_ex_legacy": round(float(rec.ai_amount_high_ex_legacy), 2),
                "ai_count_high_ex_legacy": int(rec.ai_count_high_ex_legacy),
                "total_expenditure": round(float(rec.total_expenditure), 2),
                "pct_ai": round(pct, 3) if pct is not None else None,
                "pct_ai_ex_legacy": round(pct_ex_legacy, 3) if pct_ex_legacy is not None else None,
                "use_categories": sorted(ent_cats.get(key, set())),
                "vendor_ids": sorted(ent_vendors.get(key, set())),
                "use_categories_ex_legacy": sorted(ent_cats_ex_legacy.get(key, set())),
                "vendor_ids_ex_legacy": sorted(ent_vendors_ex_legacy.get(key, set())),
            }
        )

    # --- vendor detail pages ---
    vendors_detail = {}
    for vid, vsub in exploded.groupby("vendor_id"):
        vhi = vsub[vsub["confidence"] == "high"]
        if vhi.empty:
            continue
        vname = vsub["vendor_name"].iloc[0]
        vgroup = vsub["vendor_group"].iloc[0]
        ts = (
            vhi.groupby("cycle", as_index=False)
            .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
            .to_dict(orient="records")
        )
        by_cand = (
            vhi[vhi["cand_id"] != ""]
            .groupby(["cand_id", "cand_name", "cand_party", "office"], as_index=False)
            .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
            .sort_values("amount", ascending=False)
            .head(TOP_N_VENDOR_CANDIDATES)
            .to_dict(orient="records")
        )
        top_cmtes = (
            vhi.groupby(["cmte_id", "cmte_name"], as_index=False)
            .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
            .sort_values("amount", ascending=False)
            .head(TOP_N_VENDOR_COMMITTEES)
            .to_dict(orient="records")
        )
        v_office = vhi[vhi["office"].isin(["House", "Senate"])]
        vendors_detail[vid] = {
            "id": vid,
            "name": vname,
            "group": vgroup,
            "era": era_by_id.get(vid, "generative"),
            "homepage": homepage_by_id.get(vid),
            "amount_high": round(float(vhi["transaction_amt"].sum()), 2),
            "count_high": int(vhi["sub_id"].nunique()),
            "time_series": ts,
            "by_candidate": by_cand,
            "top_committees": top_cmtes,
            "by_party": agg_amount_count(v_office, ["cand_party"]),
            "by_incumbency": agg_amount_count(v_office, ["ici"]),
            "by_chamber": agg_amount_count(v_office, ["office"]),
        }

    # --- candidate detail pages (any office, high confidence, any cycle) ---
    # Not restricted to House/Senate: the vendor pages' "top candidates" charts
    # and the leaderboard both surface any candidate with a match (e.g. a
    # presidential candidate), so their detail pages need to exist too, even
    # though the House/Senate-scoped breakdown charts elsewhere don't cover them.
    candidates_detail = {}
    for cid, csub in high[high["cand_id"] != ""].groupby("cand_id"):
        name = csub["cand_name"].iloc[0]
        party = csub["cand_party"].iloc[0]
        office = csub["office"].iloc[0]
        state = csub["cand_state"].iloc[0]
        district = csub["cand_district"].iloc[0]
        ici_by_cycle = csub.groupby("cycle")["ici"].first().to_dict()
        by_vendor = (
            csub.groupby(["vendor_id", "vendor_name"], as_index=False)
            .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
            .sort_values("amount", ascending=False)
            .to_dict(orient="records")
        )
        for row in by_vendor:
            row["era"] = era_by_id.get(row["vendor_id"], "generative")
        cats = defaultdict(lambda: {"amount": 0.0, "count": 0})
        for rec in csub.itertuples(index=False):
            for cat in (rec.use_categories.split(";") if rec.use_categories else ["unspecified"]):
                cats[cat]["amount"] += rec.transaction_amt
                cats[cat]["count"] += 1
        by_category = [
            {"id": cat, "amount": round(v["amount"], 2), "count": v["count"]}
            for cat, v in sorted(cats.items(), key=lambda kv: -kv[1]["amount"])
        ]
        my_totals = cc_office[cc_office["cand_id"] == cid].drop_duplicates("cycle")[["cycle", "cmte_total_expenditure"]]
        totals_by_cycle = dict(zip(my_totals["cycle"], my_totals["cmte_total_expenditure"]))
        by_cycle = []
        for cycle, csub_cycle in csub.groupby("cycle"):
            amt = float(csub_cycle["transaction_amt"].sum())
            tot = float(totals_by_cycle.get(cycle, 0.0))
            by_cycle.append(
                {
                    "cycle": int(cycle),
                    "amount": round(amt, 2),
                    "count": int(csub_cycle["sub_id"].nunique()),
                    "total_expenditure": round(tot, 2),
                    "pct_ai": round(amt / tot * 100, 3) if tot > 0 else None,
                    "ici": ici_by_cycle.get(cycle, "Unknown"),
                }
            )
        total_amount = float(csub["transaction_amt"].sum())
        total_expenditure = float(sum(totals_by_cycle.values()))
        candidates_detail[cid] = {
            "id": cid,
            "name": name,
            "party": party,
            "office": office,
            "state": state,
            "district": district,
            "race_id": f"{office}-{state}-{district}",
            "amount_high": round(total_amount, 2),
            "count_high": int(csub["sub_id"].nunique()),
            "total_expenditure": round(total_expenditure, 2),
            "pct_ai": round(total_amount / total_expenditure * 100, 3) if total_expenditure > 0 else None,
            "by_vendor": by_vendor,
            "by_category": by_category,
            "by_cycle": sorted(by_cycle, key=lambda r: r["cycle"]),
        }

    # --- race / seat pages ---
    races: dict[str, dict] = {}
    for cid, cdet in candidates_detail.items():
        rid = cdet["race_id"]
        race = races.setdefault(
            rid,
            {"id": rid, "office": cdet["office"], "state": cdet["state"], "district": cdet["district"], "candidates": []},
        )
        race["candidates"].append(
            {
                "cand_id": cid,
                "name": cdet["name"],
                "party": cdet["party"],
                "amount_high": cdet["amount_high"],
                "pct_ai": cdet["pct_ai"],
                "cycles": [c["cycle"] for c in cdet["by_cycle"]],
            }
        )
    for race in races.values():
        race["candidates"].sort(key=lambda r: -r["amount_high"])

    # --- outside spending: independent expenditures (Schedule E) and
    # coordinated party expenditures (Schedule F) -- AI-vendor money spent
    # FOR or AGAINST a candidate by a Super PAC, hybrid PAC, or party
    # committee, not the candidate's own campaign. Kept in its own section
    # rather than folded into the vendor/candidate totals above: whether
    # spending was coordinated with the candidate is a legally and
    # analytically meaningful line, and mixing the two would blur exactly
    # the "who is doing this on a candidate's behalf" question this section
    # exists to answer. See parse_outside_spending.py for sourcing.
    def load_amount_totals(path: Path, key_field: str) -> dict[str, float]:
        out: dict[str, float] = {}
        if not path.exists():
            return out
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    out[row[key_field]] = out.get(row[key_field], 0.0) + float(row["total_amount"])
                except (KeyError, ValueError):
                    continue
        return out

    CMTE_TYPE_LABEL = {
        "O": "Super PAC", "U": "Super PAC (single-candidate)",
        "Q": "PAC", "N": "PAC", "V": "PAC", "W": "PAC",
        "Y": "Party committee", "X": "Party committee", "Z": "Party committee",
        "D": "Delegate committee", "I": "Individual/group filer",
    }

    def normalize_ie_party(text: str) -> str:
        t = (text or "").strip().upper()
        if not t:
            return "Unknown"
        if "DEM" in t:
            return "Democratic"
        if "REP" in t:
            return "Republican"
        if "INDEPENDENT" in t and "NO PARTY" not in t:
            return "Independent"
        return "Other"

    def explode_outside(df: pd.DataFrame, carry: list[str]) -> pd.DataFrame:
        rows = []
        for rec in df.itertuples(index=False):
            ids = rec.vendor_ids.split(";") if rec.vendor_ids else []
            names = rec.vendor_names.split(";") if rec.vendor_names else []
            groups = rec.vendor_groups.split(";") if rec.vendor_groups else []
            confs = rec.confidences.split(";") if rec.confidences else []
            for vid, vname, vgroup, conf in zip(ids, names, groups, confs):
                row = {f: getattr(rec, f) for f in carry}
                row.update(
                    vendor_id=vid, vendor_name=vname, vendor_group=vgroup,
                    vendor_era=era_by_id.get(vid, "generative"), confidence=conf,
                )
                rows.append(row)
        return pd.DataFrame(rows)

    def outside_vendor_rows(exploded_df: pd.DataFrame) -> list[dict]:
        rows = []
        for (vid, vname, vgroup), sub in exploded_df.groupby(["vendor_id", "vendor_name", "vendor_group"]):
            hi = sub[sub["confidence"] == "high"]
            med = sub[sub["confidence"] == "medium"]
            rows.append({
                "id": vid, "name": vname, "group": vgroup,
                "era": era_by_id.get(vid, "generative"),
                "homepage": homepage_by_id.get(vid),
                "amount_high": round(float(hi["transaction_amt"].sum()), 2),
                "count_high": int(len(hi)),
                "amount_medium": round(float(med["transaction_amt"].sum()), 2),
                "count_medium": int(len(med)),
            })
        rows.sort(key=lambda r: r["amount_high"], reverse=True)
        return rows

    ie_frames, pce_frames = [], []
    ie_spender_totals: dict[str, float] = {}
    pce_cmte_totals: dict[str, float] = {}
    cmte_master_by_cycle: dict[int, dict] = {}
    for cycle in args.cycles:
        cmte_master_by_cycle[cycle] = load_committee_master(cycle, session)

        ie_path = PROCESSED_DIR / f"ie_matches_{cycle}.csv"
        if ie_path.exists():
            df_ie = pd.read_csv(ie_path, dtype=str, keep_default_na=False)
            if not df_ie.empty:
                df_ie["transaction_amt"] = pd.to_numeric(df_ie["transaction_amt"], errors="coerce").fillna(0.0)
                df_ie["cycle"] = pd.to_numeric(df_ie["cycle"], errors="coerce").astype("Int64")
                df_ie["office"] = df_ie["office"].map(lambda c: OFFICE_LABEL.get(c, "Other"))
                df_ie["cand_party"] = df_ie["cand_party"].map(normalize_ie_party)
                df_ie["support_oppose"] = df_ie["support_oppose"].map({"S": "Support", "O": "Oppose"}).fillna("Unknown")
                ie_frames.append(df_ie)
        for spender_id, amt in load_amount_totals(PROCESSED_DIR / f"ie_totals_{cycle}.csv", "spender_id").items():
            ie_spender_totals[spender_id] = ie_spender_totals.get(spender_id, 0.0) + amt

        pce_path = PROCESSED_DIR / f"pce_matches_{cycle}.csv"
        if pce_path.exists():
            df_pce = pd.read_csv(pce_path, dtype=str, keep_default_na=False)
            if not df_pce.empty:
                df_pce["transaction_amt"] = pd.to_numeric(df_pce["transaction_amt"], errors="coerce").fillna(0.0)
                df_pce["cycle"] = pd.to_numeric(df_pce["cycle"], errors="coerce").astype("Int64")
                cm = cmte_master_by_cycle[cycle]
                df_pce["cmte_name"] = df_pce["cmte_id"].map(lambda c: cm.get(c, {}).get("name", ""))
                pce_frames.append(df_pce)
        for cmte_id, amt in load_amount_totals(PROCESSED_DIR / f"pce_totals_{cycle}.csv", "cmte_id").items():
            pce_cmte_totals[cmte_id] = pce_cmte_totals.get(cmte_id, 0.0) + amt

    def cmte_type_label(cmte_id: str) -> str:
        for cm in cmte_master_by_cycle.values():
            if cmte_id in cm:
                return CMTE_TYPE_LABEL.get(cm[cmte_id].get("type", ""), "Committee/PAC")
        return "Committee/PAC"

    outside_spending = {"independent_expenditures": {}, "coordinated_party_expenditures": {}}

    if ie_frames:
        ie_all = pd.concat(ie_frames, ignore_index=True)
        ie_exp = explode_outside(
            ie_all,
            ["cycle", "cand_id", "cand_name", "office", "cand_state", "cand_district", "cand_party",
             "spender_id", "spender_name", "support_oppose", "transaction_amt", "transaction_date",
             "purpose", "payee", "file_num", "tran_id"],
        )
        ie_hi = ie_exp[ie_exp["confidence"] == "high"]
        ie_time_series = rename_key(
            ie_hi.groupby(["cycle", "vendor_group", "vendor_era"], dropna=False)
            .agg(amount=("transaction_amt", "sum"), count=("tran_id", "nunique")).reset_index()
            .to_dict(orient="records"),
            "vendor_era", "era",
        )
        by_support_oppose = rename_key(
            ie_hi.groupby(["support_oppose", "vendor_group", "vendor_era"], dropna=False)
            .agg(amount=("transaction_amt", "sum"), count=("tran_id", "nunique")).reset_index()
            .to_dict(orient="records"),
            "vendor_era", "era",
        )
        # Group by spender_id alone, not (spender_id, spender_name): the same
        # committee's name is capitalized inconsistently across its own
        # filings (e.g. "MoveOn.org" vs "MoveOn.Org"), which would otherwise
        # silently split one spender into two rows.
        spender_names = ie_hi.groupby("spender_id")["spender_name"].agg(lambda s: s.value_counts().idxmax())
        top_spenders = (
            ie_hi.groupby("spender_id", dropna=False)
            .agg(amount=("transaction_amt", "sum"), count=("tran_id", "nunique"))
            .reset_index().sort_values("amount", ascending=False).head(25)
        )
        top_spenders["spender_name"] = top_spenders["spender_id"].map(spender_names)
        top_spenders["cmte_type"] = top_spenders["spender_id"].map(cmte_type_label)
        top_spenders["total_ie_spend"] = top_spenders["spender_id"].map(lambda sid: round(ie_spender_totals.get(sid, 0.0), 2))
        top_spenders["pct_ai"] = top_spenders.apply(
            lambda r: round(r["amount"] / r["total_ie_spend"] * 100, 3) if r["total_ie_spend"] > 0 else None, axis=1
        )
        ie_records = ie_exp.sort_values("transaction_amt", ascending=False).to_dict(orient="records")
        for r in ie_records:
            r["transaction_amt"] = round(float(r["transaction_amt"]), 2)
            r["cycle"] = int(r["cycle"]) if pd.notna(r["cycle"]) else None

        outside_spending["independent_expenditures"] = {
            "vendor_rows": outside_vendor_rows(ie_exp),
            "time_series": ie_time_series,
            "by_support_oppose": by_support_oppose,
            "top_spenders": top_spenders.to_dict(orient="records"),
            "records": ie_records,
            "amount_high_total": round(float(ie_hi["transaction_amt"].sum()), 2),
            "count_high_total": int(ie_hi["tran_id"].nunique()),
        }

        cand_ie = ie_hi[ie_hi["cand_id"] != ""]
        for cid, sub in cand_ie.groupby("cand_id"):
            if cid not in candidates_detail:
                continue
            candidates_detail[cid]["outside_independent_expenditure"] = {
                "support_amount": round(float(sub[sub["support_oppose"] == "Support"]["transaction_amt"].sum()), 2),
                "oppose_amount": round(float(sub[sub["support_oppose"] == "Oppose"]["transaction_amt"].sum()), 2),
                "count": int(sub["tran_id"].nunique()),
                "vendor_ids": sorted(set(sub["vendor_id"])),
            }

    if pce_frames:
        pce_all = pd.concat(pce_frames, ignore_index=True)
        # OTHER_ID on a 24C row is usually the FEC candidate ID the spending
        # benefited; look it up per that row's own cycle (a candidate's ID
        # is cycle-specific in the FEC's own candidate master).
        cand_master_by_cycle = {cycle: load_candidate_master(cycle, session) for cycle in args.cycles}

        def pce_cand_name(row) -> str:
            cm = cand_master_by_cycle.get(int(row["cycle"]), {}) if pd.notna(row["cycle"]) else {}
            return cm.get(row["cand_id"], {}).get("name", "")

        pce_all["cand_name"] = pce_all.apply(pce_cand_name, axis=1)
        pce_exp = explode_outside(
            pce_all,
            ["cycle", "cmte_id", "cmte_name", "name", "transaction_amt", "transaction_dt", "memo_text",
             "cand_id", "cand_name", "sub_id"],
        )
        pce_hi = pce_exp[pce_exp["confidence"] == "high"]
        pce_time_series = rename_key(
            pce_hi.groupby(["cycle", "vendor_group", "vendor_era"], dropna=False)
            .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique")).reset_index()
            .to_dict(orient="records"),
            "vendor_era", "era",
        )
        top_committees_pce = (
            pce_hi.groupby(["cmte_id", "cmte_name"], dropna=False)
            .agg(amount=("transaction_amt", "sum"), count=("sub_id", "nunique"))
            .reset_index().sort_values("amount", ascending=False).head(25)
        )
        top_committees_pce["total_pce_spend"] = top_committees_pce["cmte_id"].map(lambda c: round(pce_cmte_totals.get(c, 0.0), 2))
        top_committees_pce["pct_ai"] = top_committees_pce.apply(
            lambda r: round(r["amount"] / r["total_pce_spend"] * 100, 3) if r["total_pce_spend"] > 0 else None, axis=1
        )
        pce_records = pce_exp.sort_values("transaction_amt", ascending=False).to_dict(orient="records")
        for r in pce_records:
            r["transaction_amt"] = round(float(r["transaction_amt"]), 2)
            r["cycle"] = int(r["cycle"]) if pd.notna(r["cycle"]) else None

        outside_spending["coordinated_party_expenditures"] = {
            "vendor_rows": outside_vendor_rows(pce_exp),
            "time_series": pce_time_series,
            "top_committees": top_committees_pce.to_dict(orient="records"),
            "records": pce_records,
            "amount_high_total": round(float(pce_hi["transaction_amt"].sum()), 2),
            "count_high_total": int(pce_hi["sub_id"].nunique()),
        }

        cand_pce = pce_hi[pce_hi["cand_id"] != ""]
        for cid, sub in cand_pce.groupby("cand_id"):
            if cid not in candidates_detail:
                continue
            candidates_detail[cid]["outside_coordinated_party_expenditure"] = {
                "amount": round(float(sub["transaction_amt"].sum()), 2),
                "count": int(sub["sub_id"].nunique()),
                "vendor_ids": sorted(set(sub["vendor_id"])),
            }

    row_counts = {}
    ie_row_counts = {}
    pce_row_counts = {}
    for cycle in args.cycles:
        p = PROCESSED_DIR / f"matches_{cycle}.csv"
        if p.exists():
            row_counts[cycle] = int(sum(1 for _ in open(p, encoding="utf-8")) - 1)
        p = PROCESSED_DIR / f"ie_matches_{cycle}.csv"
        if p.exists():
            ie_row_counts[cycle] = int(sum(1 for _ in open(p, encoding="utf-8")) - 1)
        p = PROCESSED_DIR / f"pce_matches_{cycle}.csv"
        if p.exists():
            pce_row_counts[cycle] = int(sum(1 for _ in open(p, encoding="utf-8")) - 1)

    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "cycles": args.cycles,
        "current_cycle": CURRENT_CYCLE,
        "sources": [
            "FEC bulk data: itemized operating expenditures (Schedule B / oppexp)",
            "FEC bulk data: candidate master (cn)",
            "FEC bulk data: candidate-committee linkage (ccl)",
            "FEC bulk data: committee master (cm)",
            "FEC bulk data: independent expenditures (Schedule E)",
            "FEC bulk data: any transaction from one committee to another (oth), filtered to coordinated party expenditures (Schedule F, transaction type 24C)",
            "unitedstates/congress-legislators (birthdates, for age analysis)",
        ],
        "matched_row_counts_by_cycle": row_counts,
        "ie_matched_row_counts_by_cycle": ie_row_counts,
        "pce_matched_row_counts_by_cycle": pce_row_counts,
        "openai_high_confidence_house_senate_candidates_2026": int(openai_2026_candidates),
        "methodology_notes": [
            "Vendor matches are text matches against payee name, disbursement purpose, category description, and memo text -- not a review of underlying documents. See config/vendors.yaml for the full pattern list and its provenance.",
            "'High confidence' matches use unambiguous vendor/product names (e.g. 'OpenAI', 'ChatGPT', 'Quiller'). 'Medium confidence' matches use ambiguous words (e.g. 'Gemini', 'Copilot', 'Grok', 'Claude') that also have common non-AI meanings; these are shown only in the vendor landscape view and excluded from the party/incumbency/chamber/age/use-case/time-series breakdowns.",
            "Party, chamber, and incumbency breakdowns (section 3) are the 2026 cycle only, House and Senate candidate committees, high-confidence matches. The time-series charts (section 4) cover all cycles.",
            "Candidate age is drawn from the unitedstates/congress-legislators project, which covers people who have served in Congress. Non-incumbent challengers who have never held office are not in that dataset and are bucketed as 'Unknown' rather than estimated.",
            "Disclosed AI spending likely understates actual usage: campaigns can pay for AI tools through corporate cards, staff reimbursements, or consultants without the underlying vendor ever appearing in disbursement text.",
            "A single disbursement can match more than one vendor or more than one use-case category (e.g. a payment memo mentioning both 'ChatGPT' and 'email drafting'); category and vendor totals are not mutually exclusive and will not sum to a single grand total.",
            "General-purpose cloud hosting (AWS, Azure, Google Cloud) is not counted as AI spend merely because the provider also sells AI products -- only a disbursement naming a specific AI service (e.g. 'AWS Bedrock', 'Azure OpenAI') counts. Scanning all four cycles found zero such specific mentions; generic cloud/hosting spend for these providers is common but not itemized down to the AI-specific service used, so it isn't attributable one way or the other.",
            "Google's Gemini is frequently bundled into a Google Workspace subscription a campaign already pays for email and documents, so it often has no separate line item the way a standalone ChatGPT or Claude subscription does. This likely understates Google's real usage more than it does OpenAI's or Anthropic's -- a limitation of disbursement-based analysis, not evidence Google is less used.",
            "'% of total spend' denominators are each committee's total reported operating expenditure (Schedule B), excluding FEC memo entries to avoid double-counting a lump-sum payment and its own itemized breakdown. For party/incumbency/chamber/age/time-series charts, the denominator is the combined total spend of the House/Senate candidates in that slice who have at least one AI-vendor disbursement -- not of every House/Senate candidate that cycle -- so these percentages answer 'how big is AI spend relative to everything else these AI-using campaigns spend,' not 'what share of all campaign spending nationally goes to AI.'",
            "The vendor list was expanded past what press coverage had named by scanning all four cycles for generic AI-indicative language (bare 'AI', 'chatbot', 'bot', 'prompt', etc.) in disbursements that didn't already match a known vendor, then researching which payee names kept recurring. That pass is what surfaced Amplify.ai, Prompt.io, CallTime.AI, Numero, Daisychain, SoSha, and several smaller tools -- collectively a much larger share of disclosed AI spending than the general-purpose chatbot subscriptions most coverage of this topic focuses on. It also surfaced a false-positive trap worth naming: several teleprompter-equipment vendors have 'prompting' in their name in the unrelated, decades-old sense, which is why 'Prompt.io' is matched only as that exact product name, never bare 'prompt'. The same scan turned up plausible-sounding candidates we deliberately left out because the disbursement text never actually said 'AI' -- Civis Analytics, Grow Progress, and Movement Labs are real political-data vendors whose own marketing mentions AI/machine learning, but nothing in how campaigns paid them here does, so we didn't want to launder marketing copy into a disclosure-based finding.",
            "A payee name match attributes the full disbursement amount to that vendor even when the memo describes a bundled payment (e.g. 'reimbursement for SendGrid, SpeechifAI, and Twilio' for one lump sum) -- there is no way to apportion a bundled reimbursement from the text alone, so a vendor's total can be modestly overstated in these cases. They appear to be a small share of matched dollars, not the norm.",
            "Every vendor is tagged with an 'era': 'generative' (built on modern large-language-model, diffusion, or voice-clone AI) or 'legacy' (a company that predates the generative-AI wave and either still runs on older, non-generative technology or added a generative feature onto a much older product -- see config/vendors.yaml for the founding-year research behind each call). Amplify.ai/TruVerse, Prompt.io, CallTime.AI, Numero, EyesOver, Otter.ai, Chatfuel, Grammarly, and Descript are tagged legacy. Charts and tables default to excluding legacy-era vendors, since lumping a 2014-era chatbot or grammar checker in with a campaign's ChatGPT or Claude subscription overstates how much reported spending reflects current frontier-AI adoption; a toggle (top of the page) adds legacy vendors back into every chart and table. Vendor and candidate detail pages always show full history regardless of the toggle, with each vendor's era labeled.",
            "'Outside spending' (independent expenditures and coordinated party expenditures) tracks AI-vendor money spent FOR or AGAINST a candidate by someone other than that candidate's own campaign -- Super PACs, hybrid PACs, and party committees -- kept separate from every other figure on this site because the campaign never sees or reports this spending itself. Independent expenditures (Schedule E) are legally uncoordinated with the candidate; coordinated party expenditures (Schedule F) are a national or state party committee spending on a candidate's behalf, coordinated, up to a statutory per-candidate cap. Even within outside spending, this only shows what a Super PAC or party committee paid a vendor directly -- if that money instead went to a consulting or media-buying firm that itself used an AI tool, that sub-layer of spending is invisible here the same way it is for candidate committees.",
            "Schedule E (independent expenditures) comes from the FEC's dedicated independent-expenditure bulk file, which explicitly warns that it contains both original and amended reports without removing the originals. This pipeline drops every filing (by FILE_NUM) that a later amendment superseded, keeping only the final version -- see parse_outside_spending.py.",
            "Schedule F (coordinated party expenditures) has no dedicated bulk file; these transactions are pulled from the FEC's general committee-to-committee transaction file (transaction type '24C'), which lacks a purpose field, so vendor matches here rely on payee name and a memo field that is often blank -- category/use-case labeling is accordingly thinner for this schedule than elsewhere on the site. Scanning all four cycles found exactly one qualifying high-confidence payment; coordinated party spending is capped by statute and, in what we found, goes overwhelmingly to traditional media buyers rather than named AI vendors -- a real finding, not a parsing gap.",
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
        "top_committees_all_eras": top_committees_all_eras,
        "entities": entity_rows,
        "outside_spending": outside_spending,
        "vendors_detail": vendors_detail,
        "candidates_detail": candidates_detail,
        "races": races,
        "office_labels": OFFICE_LABEL,
        "ici_labels": ICI_LABEL,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
