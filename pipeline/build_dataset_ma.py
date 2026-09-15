#!/usr/bin/env python3
"""Aggregate OCPF (Massachusetts) vendor matches into the JSON the
Massachusetts tab of the dashboard reads.

Output: docs/data/dashboard_ma.json -- a separate file from the federal
dashboard.json, loaded only when a visitor switches to the Massachusetts
tab. The two datasets are never merged: different disclosure regime,
different itemization threshold, different date convention (OCPF filers
report continuously, not in discrete federal-style cycles), so this file
uses its own schema rather than forcing OCPF data into the federal one's
shape.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.vendor_match import Taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH = ROOT / "docs" / "data" / "dashboard_ma.json"

NOTABLE_RECORD_LIMIT = 20


def _parse_mdy(value: str) -> date | None:
    if not value:
        return None
    try:
        m, d, y = (int(p) for p in value.strip().split("/"))
        return date(y, m, d)
    except (ValueError, AttributeError):
        return None


def _week_start(d: date) -> str:
    return (d - timedelta(days=d.weekday())).isoformat()


def build_weekly_histogram(matched_rows: list[dict], report_dates: dict[str, dict]) -> dict:
    """Two independent weekly counts: when the expenditure itself happened
    (`date`, one row per matched record) vs. when the OCPF report disclosing
    it was filed (`dateFiled` from the report endpoint, one count per
    DISTINCT report -- a single report can disclose many expenditure line
    items, so counting every row here would inflate the report side by
    however itemized that report happened to be)."""
    expenditure_weeks: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": 0.0})
    reports_seen: set[str] = set()
    report_weeks: dict[str, int] = defaultdict(int)

    for row in matched_rows:
        d = _parse_mdy(row["date"])
        if d:
            wk = _week_start(d)
            expenditure_weeks[wk]["count"] += 1
            expenditure_weeks[wk]["amount"] += float(row["amount"] or 0)

        report_id = row.get("report_id")
        if report_id and report_id not in reports_seen:
            reports_seen.add(report_id)
            info = report_dates.get(report_id)
            if info and info.get("date_filed"):
                fd = _parse_mdy(info["date_filed"])
                if fd:
                    report_weeks[_week_start(fd)] += 1

    return {
        "expenditures": [
            {"week": wk, "count": v["count"], "amount": round(v["amount"], 2)}
            for wk, v in sorted(expenditure_weeks.items())
        ],
        "reports_filed": [{"week": wk, "count": n} for wk, n in sorted(report_weeks.items())],
    }


def load_vendor_meta(taxonomy: Taxonomy) -> dict[str, dict]:
    return {
        v.id: {
            "id": v.id,
            "name": v.name,
            "group": v.group,
            "era": v.era,
            "homepage": v.homepage,
            "lean_context": v.lean_context,
        }
        for v in taxonomy.vendors
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args()
    end_date = args.end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    taxonomy = Taxonomy()
    vendor_meta = load_vendor_meta(taxonomy)

    matches_path = PROCESSED_DIR / "ocpf_matches.csv"
    subvendor_path = PROCESSED_DIR / "ocpf_subvendor_matches.csv"
    filer_totals_path = PROCESSED_DIR / "ocpf_filer_totals.csv"
    report_dates_path = PROCESSED_DIR / "ocpf_report_dates.csv"

    report_dates: dict[str, dict] = {}
    if report_dates_path.exists():
        for row in csv.DictReader(open(report_dates_path, encoding="utf-8")):
            report_dates[row["report_id"]] = row

    # Filer party affiliation: OCPF's per-record expenditure data has no
    # party field at all (see fetch_ocpf_filer_party.py), so this is looked
    # up per distinct filer via a separate small fetch, the same pattern as
    # report_dates above.
    filer_party_path = PROCESSED_DIR / "ocpf_filer_party.csv"
    filer_party: dict[str, str] = {}
    if filer_party_path.exists():
        for row in csv.DictReader(open(filer_party_path, encoding="utf-8")):
            if row["party"]:
                filer_party[row["filer_cpf_id"]] = row["party"]

    rows = list(csv.DictReader(open(matches_path, encoding="utf-8")))
    subvendor_matched_rows = list(csv.DictReader(open(subvendor_path, encoding="utf-8")))
    filer_totals_row = next(csv.DictReader(open(filer_totals_path, encoding="utf-8")))
    total_filers_with_activity = int(filer_totals_row["total_filers_with_expenditure_activity"])
    total_expenditure_records = int(filer_totals_row["total_expenditure_records"])
    total_subvendor_records = int(filer_totals_row["total_subvendor_records"])

    # Per-vendor rollups. A row can carry more than one vendor id (rare --
    # ambiguous text matching two patterns); split its amount/record credit
    # across each, same convention as the federal vendor rollup.
    vendor_totals: dict[str, float] = defaultdict(float)
    vendor_records: dict[str, int] = defaultdict(int)
    vendor_filers: dict[str, set] = defaultdict(set)
    vendor_party_amount: dict[str, dict] = defaultdict(lambda: {"Democratic": 0.0, "Republican": 0.0})

    total_all = 0.0
    total_generative = 0.0
    matched_filers: set = set()
    year_totals: dict[int, float] = defaultdict(float)
    year_records: dict[int, int] = defaultdict(int)
    year_party_totals: dict[tuple, float] = defaultdict(float)
    party_totals = {"Democratic": 0.0, "Republican": 0.0}
    party_counts = {"Democratic": 0, "Republican": 0}

    notable_records = []

    for row in rows:
        amount = float(row["amount"] or 0)
        vids = row["vendor_ids"].split(";")
        vnames = row["vendor_names"].split(";")
        veras = row["vendor_eras"].split(";")
        confidences = row["confidences"].split(";")
        party = filer_party.get(row["filer_cpf_id"], "")

        total_all += amount
        if any(era == "generative" for era in veras):
            total_generative += amount
        matched_filers.add(row["filer_cpf_id"])

        try:
            year = int(row["date"].split("/")[-1])
            year_totals[year] += amount
            year_records[year] += 1
            if party in ("Democratic", "Republican"):
                year_party_totals[(year, party)] += amount
        except (ValueError, IndexError):
            pass

        if party in ("Democratic", "Republican"):
            party_totals[party] += amount
            party_counts[party] += 1

        for vid in vids:
            vendor_totals[vid] += amount
            vendor_records[vid] += 1
            vendor_filers[vid].add(row["filer_cpf_id"])
            if party in ("Democratic", "Republican"):
                vendor_party_amount[vid][party] += amount

        notable_records.append(
            {
                "vendor_ids": vids,
                "vendor_names": vnames,
                "confidences": confidences,
                "filer_name": row["filer_name"],
                "filer_cpf_id": row["filer_cpf_id"],
                "filer_party": party or "Unknown",
                "date": row["date"],
                "amount": round(amount, 2),
                "purpose": row["clarified_purpose"] or row["purpose"],
                "vendor_display": row["clarified_name"] or row["vendor"],
                "source_link": row["source_link"],
            }
        )

    def dem_rep_ratio(dem_amount: float, rep_amount: float) -> float | None:
        return round(dem_amount / rep_amount, 3) if dem_amount > 0 and rep_amount > 0 else None

    vendors_out = []
    for vid, total in vendor_totals.items():
        meta = vendor_meta.get(vid, {"id": vid, "name": vid, "group": "unknown", "era": "generative"})
        vp = vendor_party_amount[vid]
        vendors_out.append(
            {
                "id": vid,
                "name": meta["name"],
                "group": meta["group"],
                "era": meta["era"],
                "homepage": meta.get("homepage"),
                "lean_context": meta.get("lean_context"),
                "total": round(total, 2),
                "records": vendor_records[vid],
                "filers": len(vendor_filers[vid]),
                "dem_amount": round(vp["Democratic"], 2),
                "rep_amount": round(vp["Republican"], 2),
                "dem_rep_ratio": dem_rep_ratio(vp["Democratic"], vp["Republican"]),
            }
        )
    vendors_out.sort(key=lambda v: -v["total"])

    time_series = [
        {"year": year, "total": round(year_totals[year], 2), "records": year_records[year]}
        for year in sorted(year_totals)
    ]

    time_series_by_party = [
        {"year": year, "party": party, "amount": round(amount, 2)}
        for (year, party), amount in sorted(year_party_totals.items())
    ]

    party_split = {
        "dem_amount": round(party_totals["Democratic"], 2),
        "rep_amount": round(party_totals["Republican"], 2),
        "dem_count": party_counts["Democratic"],
        "rep_count": party_counts["Republican"],
        "dem_rep_ratio": dem_rep_ratio(party_totals["Democratic"], party_totals["Republican"]),
        "filers_with_known_party": sum(1 for p in filer_party.values() if p in ("Democratic", "Republican")),
    }

    notable_records.sort(key=lambda r: -r["amount"])
    notable_records = notable_records[:NOTABLE_RECORD_LIMIT]

    weekly_histogram = build_weekly_histogram(rows, report_dates)

    subvendor_total = sum(float(r["amount"] or 0) for r in subvendor_matched_rows)

    dataset = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_label": "Massachusetts Office of Campaign and Political Finance (OCPF)",
            "date_range": {"start": args.start_date, "end": end_date},
            "records_scanned": {
                "expenditures": total_expenditure_records,
                "subvendor": total_subvendor_records,
            },
            "sources": [
                "OCPF public API (api.ocpf.us/search/items), SearchTypeCategory=B (expenditures) and S "
                "(subvendor payments) -- every itemized record OCPF has on file for the window below, "
                "not a sample.",
                "Same AI vendor/category taxonomy as the federal dashboard (pipeline/config/vendors.yaml), "
                "applied unmodified against each record's payee name, OCPF's own clarified payee name, "
                "stated purpose, and OCPF's own clarified purpose.",
            ],
            "methodology_notes": [
                "OCPF itemizes Schedule B expenditures above $50 per item -- a much lower floor than the "
                "FEC's effective $200-per-payee-per-cycle threshold, which is why many of the real matches "
                "here are small individual monthly SaaS subscriptions that would never separately itemize "
                "under FEC's rule.",
                "Massachusetts committees report continuously rather than in discrete federal-style "
                "two-year cycles; this dashboard instead uses a fixed date window covering the 2024 and "
                "2026 election cycles.",
                "A vendor paid $5,000+ by a committee must itself itemize any $500+ payment it makes to a "
                "subvendor -- a disclosure layer with no federal equivalent, tested here as its own "
                "category (see below).",
                "As with the federal dashboard, this dataset only sees a payment if its payee name or "
                "purpose text names a vendor on this project's taxonomy -- disclosed AI spend is a floor "
                "on real usage, not a ceiling.",
                "The weekly disclosure timeline's 'Reports filed' series uses OCPF's own dateFiled field "
                "from its report/{reportId} endpoint -- a real filed date, unlike the federal dashboard's "
                "approximated report dates -- counted once per distinct report (a single report can "
                "disclose many expenditure line items in one filing).",
                "Democratic-vs-Republican spending uses each filer's partyAffiliation from OCPF's own "
                "filer/payload/{cpfId} endpoint -- fetched per distinct filer (a few dozen, not per "
                "record), since OCPF's expenditure records themselves carry no party field. Filers OCPF "
                "does not mark with a major-party affiliation (ballot-question committees, PACs, and a "
                "handful of others) are excluded from the party split entirely, not counted as a third "
                "category -- see the filers_with_known_party figure alongside the split.",
                "This taxonomy was empirically mined against Massachusetts payee/purpose text directly "
                "(not only inherited from the federal side): every distinct OCPF payee was scanned for "
                "AI-indicative language, plus a manual read of the highest-dollar unmatched payees, which "
                "is how Read.ai, Captions, and Canva's AI photo feature were found and verified as real "
                "payees before being added -- see pipeline/config/vendors.yaml for what was found, "
                "checked, and rejected.",
            ],
        },
        "stats": {
            "total_all_eras": round(total_all, 2),
            "total_generative": round(total_generative, 2),
            "matched_records": len(rows),
            "filers_with_ai_spend": len(matched_filers),
            "total_filers_with_activity": total_filers_with_activity,
        },
        "vendors": vendors_out,
        "time_series": time_series,
        "time_series_by_party": time_series_by_party,
        "party_split": party_split,
        "weekly_histogram": weekly_histogram,
        "subvendor": {
            "records_scanned": total_subvendor_records,
            "matched_records": len(subvendor_matched_rows),
            "total": round(subvendor_total, 2),
        },
        "notable_records": notable_records,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    print(
        f"MA dashboard: {len(rows)} matched expenditure records, ${total_all:,.2f} total, "
        f"{len(matched_filers)} filers -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
