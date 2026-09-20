"""Shared aggregation for state-level dashboards (Washington, Colorado,
California, and any future addition) built on a common intermediate CSV
schema, so build_dataset_wa.py/_co.py/_ca.py don't each reimplement the
same vendor/filer/time-series rollups. Massachusetts (build_dataset_ma.py)
predates this and has its own OCPF-specific extras (subvendor payments,
report-filed weekly histogram) with no equivalent in the other states'
disclosure data, so it is deliberately NOT rebuilt on top of this shared
function -- forcing that would mean either losing those OCPF-only features
or inventing fake ones for states that don't have them.

Every state's own parse_<state>.py is responsible for normalizing its
source's real schema into this common matched-record CSV shape:

    record_id, filer_id, filer_name, party, date (YYYY-MM-DD),
    amount, payee_display, purpose_display, office, source_link,
    vendor_ids, vendor_names, vendor_groups, vendor_eras, confidences

and a filer-year-totals CSV (filer_id, year, total_expenditure) -- each
filer's own total reported spend by year, regardless of vendor match,
the denominator for "AI spend as a % of total spend" (the same role
load_committee_totals() / OCPF's ocpf_filer_year_totals.csv play
elsewhere in this pipeline).

`party` may be an empty string if the source has no party field for that
filer (matches OCPF's own "Unknown" convention, applied uniformly here
rather than each state inventing its own null convention).
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .vendor_match import Taxonomy

NOTABLE_RECORD_LIMIT = 20
MAX_DETAIL_RECORDS = 300
TOP_N_FILERS = 20


def load_vendor_meta(taxonomy: Taxonomy) -> dict[str, dict]:
    return {
        v.id: {
            "id": v.id,
            "name": v.name,
            "group": v.group,
            "era": v.era,
            "homepage": v.homepage,
            "lean_context": v.lean_context,
            "description": v.description,
            "tags": list(v.tags),
        }
        for v in taxonomy.vendors
    }


def build_state_dashboard(
    matched_csv_path: Path,
    filer_year_totals_path: Path,
    total_filers_with_activity: int,
    total_records_scanned: int,
    meta_extra: dict,
) -> dict:
    """Build the full dashboard dict for one state from its normalized
    matched-record CSV. `meta_extra` is merged into the output's "meta"
    key (source_label, sources, methodology_notes, date_range, etc.) --
    everything state-specific about *documentation*, not aggregation.
    """
    taxonomy = Taxonomy()
    vendor_meta = load_vendor_meta(taxonomy)

    filer_year_expenditure: dict[str, dict[int, float]] = defaultdict(dict)
    if filer_year_totals_path.exists():
        for row in csv.DictReader(open(filer_year_totals_path, encoding="utf-8")):
            filer_year_expenditure[row["filer_id"]][int(row["year"])] = float(row["total_expenditure"])

    rows = list(csv.DictReader(open(matched_csv_path, encoding="utf-8")))

    vendor_totals: dict[str, float] = defaultdict(float)
    vendor_records: dict[str, int] = defaultdict(int)
    vendor_filers: dict[str, set] = defaultdict(set)
    vendor_party_amount: dict[str, dict] = defaultdict(lambda: {"Democratic": 0.0, "Republican": 0.0})
    vendor_totals_by_confidence: dict[str, dict] = defaultdict(lambda: {"high": 0.0, "medium": 0.0})
    vendor_records_by_confidence: dict[str, dict] = defaultdict(lambda: {"high": 0, "medium": 0})

    total_all = 0.0
    total_generative = 0.0
    matched_filers: set = set()
    matched_filers_ex_legacy: set = set()
    year_totals: dict[int, float] = defaultdict(float)
    year_records: dict[int, int] = defaultdict(int)
    year_party_totals: dict[tuple, float] = defaultdict(float)
    year_ai_filers: dict[int, set] = defaultdict(set)
    party_totals = {"Democratic": 0.0, "Republican": 0.0}
    party_counts = {"Democratic": 0, "Republican": 0}

    year_totals_ex_legacy: dict[int, float] = defaultdict(float)
    year_records_ex_legacy: dict[int, int] = defaultdict(int)
    year_party_totals_ex_legacy: dict[tuple, float] = defaultdict(float)
    year_ai_filers_ex_legacy: dict[int, set] = defaultdict(set)
    party_totals_ex_legacy = {"Democratic": 0.0, "Republican": 0.0}
    party_counts_ex_legacy = {"Democratic": 0, "Republican": 0}

    notable_records = []

    filer_names: dict[str, str] = {}
    filer_party: dict[str, str] = {}
    filer_totals: dict[str, float] = defaultdict(float)
    filer_record_count: dict[str, int] = defaultdict(int)
    filer_vendor_ids: dict[str, set] = defaultdict(set)
    filer_year_totals: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "count": 0}))
    filer_records: dict[str, list] = defaultdict(list)

    vendor_year_totals: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "count": 0}))
    vendor_year_party_totals: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"Democratic": 0.0, "Republican": 0.0}))
    vendor_by_filer: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "count": 0}))
    vendor_detail_records: dict[str, list] = defaultdict(list)

    for row in rows:
        amount = float(row["amount"] or 0)
        vids = row["vendor_ids"].split(";")
        vnames = row["vendor_names"].split(";")
        veras = row["vendor_eras"].split(";")
        confidences = row["confidences"].split(";")
        party = row["party"] or ""
        filer_id = row["filer_id"]

        is_generative_row = any(era == "generative" for era in veras)
        total_all += amount
        if is_generative_row:
            total_generative += amount
            matched_filers_ex_legacy.add(filer_id)
        matched_filers.add(filer_id)

        try:
            year = int(row["date"][:4])
        except (ValueError, TypeError):
            year = None

        if year is not None:
            year_totals[year] += amount
            year_records[year] += 1
            year_ai_filers[year].add(filer_id)
            if party in ("Democratic", "Republican"):
                year_party_totals[(year, party)] += amount
            if is_generative_row:
                year_totals_ex_legacy[year] += amount
                year_records_ex_legacy[year] += 1
                year_ai_filers_ex_legacy[year].add(filer_id)
                if party in ("Democratic", "Republican"):
                    year_party_totals_ex_legacy[(year, party)] += amount

        if party in ("Democratic", "Republican"):
            party_totals[party] += amount
            party_counts[party] += 1
            if is_generative_row:
                party_totals_ex_legacy[party] += amount
                party_counts_ex_legacy[party] += 1

        if filer_id not in filer_names:
            filer_names[filer_id] = row["filer_name"]
        if party:
            filer_party[filer_id] = party
        filer_totals[filer_id] += amount
        filer_record_count[filer_id] += 1
        if year is not None:
            filer_year_totals[filer_id][year]["amount"] += amount
            filer_year_totals[filer_id][year]["count"] += 1
        filer_records[filer_id].append(
            {
                "date": row["date"],
                "vendor_ids": vids,
                "vendor_names": vnames,
                "confidences": confidences,
                "amount": round(amount, 2),
                "purpose": row["purpose_display"],
                "source_link": row["source_link"],
            }
        )

        for vid, vname, confidence in zip(vids, vnames, confidences):
            vendor_totals[vid] += amount
            vendor_records[vid] += 1
            vendor_filers[vid].add(filer_id)
            conf_key = confidence if confidence in ("high", "medium") else "medium"
            vendor_totals_by_confidence[vid][conf_key] += amount
            vendor_records_by_confidence[vid][conf_key] += 1
            if party in ("Democratic", "Republican"):
                vendor_party_amount[vid][party] += amount

            filer_vendor_ids[filer_id].add(vid)
            vendor_by_filer[vid][filer_id]["amount"] += amount
            vendor_by_filer[vid][filer_id]["count"] += 1
            vendor_detail_records[vid].append(
                {
                    "date": row["date"],
                    "filer_id": filer_id,
                    "filer_name": row["filer_name"],
                    "filer_party": party or "Unknown",
                    "amount": round(amount, 2),
                    "purpose": row["purpose_display"],
                    "confidence": confidence,
                    "source_link": row["source_link"],
                }
            )
            if year is not None:
                vendor_year_totals[vid][year]["amount"] += amount
                vendor_year_totals[vid][year]["count"] += 1
                if party in ("Democratic", "Republican"):
                    vendor_year_party_totals[vid][year][party] += amount

        notable_records.append(
            {
                "vendor_ids": vids,
                "vendor_names": vnames,
                "vendor_eras": veras,
                "confidences": confidences,
                "filer_name": row["filer_name"],
                "filer_id": filer_id,
                "filer_party": party or "Unknown",
                "date": row["date"],
                "amount": round(amount, 2),
                "purpose": row["purpose_display"],
                "vendor_display": row["payee_display"],
                "source_link": row["source_link"],
            }
        )

    def dem_rep_ratio(dem_amount: float, rep_amount: float) -> float | None:
        return round(dem_amount / rep_amount, 3) if dem_amount > 0 and rep_amount > 0 else None

    vendors_out = []
    for vid, total in vendor_totals.items():
        meta = vendor_meta.get(vid, {"id": vid, "name": vid, "group": "unknown", "era": "generative"})
        vp = vendor_party_amount[vid]
        vconf = vendor_totals_by_confidence[vid]
        vconf_n = vendor_records_by_confidence[vid]
        vendors_out.append(
            {
                "id": vid,
                "name": meta["name"],
                "group": meta["group"],
                "era": meta["era"],
                "homepage": meta.get("homepage"),
                "lean_context": meta.get("lean_context"),
                "description": meta.get("description"),
                "tags": meta.get("tags", []),
                "total": round(total, 2),
                "amount_high": round(vconf["high"], 2),
                "amount_medium": round(vconf["medium"], 2),
                "records": vendor_records[vid],
                "records_high": vconf_n["high"],
                "records_medium": vconf_n["medium"],
                "filers": len(vendor_filers[vid]),
                "dem_amount": round(vp["Democratic"], 2),
                "rep_amount": round(vp["Republican"], 2),
                "dem_rep_ratio": dem_rep_ratio(vp["Democratic"], vp["Republican"]),
            }
        )
    vendors_out.sort(key=lambda v: -v["amount_high"])

    filers_detail = {}
    for filer_id, total in filer_totals.items():
        ts = [
            {"year": year, "amount": round(v["amount"], 2), "count": v["count"]}
            for year, v in sorted(filer_year_totals[filer_id].items())
        ]
        recs = sorted(filer_records[filer_id], key=lambda r: -r["amount"])[:MAX_DETAIL_RECORDS]
        filer_total_expenditure = sum(filer_year_expenditure.get(filer_id, {}).values())
        filers_detail[filer_id] = {
            "id": filer_id,
            "name": filer_names[filer_id],
            "party": filer_party.get(filer_id) or "Unknown",
            "total": round(total, 2),
            "records_count": filer_record_count[filer_id],
            "vendor_ids": sorted(filer_vendor_ids[filer_id]),
            "total_expenditure": round(filer_total_expenditure, 2),
            "pct_ai": round(total / filer_total_expenditure * 100, 3) if filer_total_expenditure > 0 else None,
            "time_series": ts,
            "records": recs,
        }

    vendors_detail = {}
    for vid in vendor_totals:
        meta = vendor_meta.get(vid, {"id": vid, "name": vid, "group": "unknown", "era": "generative"})
        vp = vendor_party_amount[vid]
        ts = [
            {"year": year, "amount": round(v["amount"], 2), "count": v["count"]}
            for year, v in sorted(vendor_year_totals[vid].items())
        ]
        ts_by_party = [
            {"year": year, "party": p, "amount": round(amt, 2)}
            for year, pmap in sorted(vendor_year_party_totals[vid].items())
            for p, amt in pmap.items()
            if amt > 0
        ]
        by_filer = sorted(
            (
                {
                    "filer_id": fid,
                    "filer_name": filer_names.get(fid, fid),
                    "filer_party": filer_party.get(fid) or "Unknown",
                    "amount": round(v["amount"], 2),
                    "count": v["count"],
                }
                for fid, v in vendor_by_filer[vid].items()
            ),
            key=lambda r: -r["amount"],
        )[:TOP_N_FILERS]
        recs = sorted(vendor_detail_records[vid], key=lambda r: -r["amount"])[:MAX_DETAIL_RECORDS]
        vendors_detail[vid] = {
            "id": vid,
            "name": meta["name"],
            "group": meta["group"],
            "era": meta["era"],
            "homepage": meta.get("homepage"),
            "lean_context": meta.get("lean_context"),
            "description": meta.get("description"),
            "tags": meta.get("tags", []),
            "total": round(vendor_totals[vid], 2),
            "records_count": vendor_records[vid],
            "filers_count": len(vendor_filers[vid]),
            "dem_amount": round(vp["Democratic"], 2),
            "rep_amount": round(vp["Republican"], 2),
            "dem_rep_ratio": dem_rep_ratio(vp["Democratic"], vp["Republican"]),
            "time_series": ts,
            "time_series_by_party": ts_by_party,
            "by_filer": by_filer,
            "records": recs,
        }

    def year_ai_filer_total_expenditure(year: int) -> float:
        return sum(filer_year_expenditure.get(fid, {}).get(year, 0.0) for fid in year_ai_filers[year])

    def year_ai_filer_total_expenditure_ex_legacy(year: int) -> float:
        return sum(filer_year_expenditure.get(fid, {}).get(year, 0.0) for fid in year_ai_filers_ex_legacy[year])

    time_series = [
        {
            "year": year,
            "total": round(year_totals[year], 2),
            "records": year_records[year],
            "total_expenditure": round(year_ai_filer_total_expenditure(year), 2),
            "total_ex_legacy": round(year_totals_ex_legacy[year], 2),
            "records_ex_legacy": year_records_ex_legacy[year],
            "total_expenditure_ex_legacy": round(year_ai_filer_total_expenditure_ex_legacy(year), 2),
        }
        for year in sorted(year_totals)
    ]

    time_series_by_party = [
        {"year": year, "party": party, "amount": round(amount, 2)}
        for (year, party), amount in sorted(year_party_totals.items())
    ]
    time_series_by_party_ex_legacy = [
        {"year": year, "party": party, "amount": round(amount, 2)}
        for (year, party), amount in sorted(year_party_totals_ex_legacy.items())
    ]

    total_expenditure_ai_filers = sum(year_ai_filer_total_expenditure(y) for y in year_totals)

    party_split = {
        "dem_amount": round(party_totals["Democratic"], 2),
        "rep_amount": round(party_totals["Republican"], 2),
        "dem_count": party_counts["Democratic"],
        "rep_count": party_counts["Republican"],
        "dem_rep_ratio": dem_rep_ratio(party_totals["Democratic"], party_totals["Republican"]),
        "filers_with_known_party": sum(1 for p in filer_party.values() if p in ("Democratic", "Republican")),
    }
    party_split_ex_legacy = {
        "dem_amount": round(party_totals_ex_legacy["Democratic"], 2),
        "rep_amount": round(party_totals_ex_legacy["Republican"], 2),
        "dem_count": party_counts_ex_legacy["Democratic"],
        "rep_count": party_counts_ex_legacy["Republican"],
        "dem_rep_ratio": dem_rep_ratio(party_totals_ex_legacy["Democratic"], party_totals_ex_legacy["Republican"]),
        "filers_with_known_party": sum(
            1 for fid in matched_filers_ex_legacy if filer_party.get(fid) in ("Democratic", "Republican")
        ),
    }

    notable_records.sort(key=lambda r: -r["amount"])
    notable_records = notable_records[:NOTABLE_RECORD_LIMIT]

    dataset = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "records_scanned": total_records_scanned,
            **meta_extra,
        },
        "stats": {
            "total_all_eras": round(total_all, 2),
            "total_generative": round(total_generative, 2),
            "matched_records": len(rows),
            "filers_with_ai_spend": len(matched_filers),
            "filers_with_ai_spend_ex_legacy": len(matched_filers_ex_legacy),
            "total_filers_with_activity": total_filers_with_activity,
            "total_expenditure_ai_filers": round(total_expenditure_ai_filers, 2),
            "pct_ai_overall": round(total_all / total_expenditure_ai_filers * 100, 3) if total_expenditure_ai_filers > 0 else None,
        },
        "vendors": vendors_out,
        "vendors_detail": vendors_detail,
        "filers_detail": filers_detail,
        "time_series": time_series,
        "time_series_by_party": time_series_by_party,
        "time_series_by_party_ex_legacy": time_series_by_party_ex_legacy,
        "party_split": party_split,
        "party_split_ex_legacy": party_split_ex_legacy,
        "notable_records": notable_records,
    }
    return dataset
