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
MAX_DETAIL_RECORDS_MA = 300
TOP_N_MA_FILERS = 20


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
    filer_year_totals_path = PROCESSED_DIR / "ocpf_filer_year_totals.csv"

    report_dates: dict[str, dict] = {}
    if report_dates_path.exists():
        for row in csv.DictReader(open(report_dates_path, encoding="utf-8")):
            report_dates[row["report_id"]] = row

    # Each filer's own total reported spend by year, regardless of vendor --
    # the denominator for "AI spend as a % of total spend" (parse_ocpf.py's
    # equivalent of the federal pipeline's load_committee_totals()).
    filer_year_expenditure: dict[str, dict[int, float]] = defaultdict(dict)
    if filer_year_totals_path.exists():
        for row in csv.DictReader(open(filer_year_totals_path, encoding="utf-8")):
            filer_year_expenditure[row["filer_cpf_id"]][int(row["year"])] = float(row["total_expenditure"])

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
    year_ai_filers: dict[int, set] = defaultdict(set)
    party_totals = {"Democratic": 0.0, "Republican": 0.0}
    party_counts = {"Democratic": 0, "Republican": 0}

    notable_records = []

    # Per-filer ("candidate" equivalent -- OCPF's filers are almost all
    # candidate committees) and per-vendor detail, for the click-through
    # pages: mirrors the federal dashboard's candidates_detail/
    # vendors_detail, built from every matched row rather than just the
    # top-20 notable_records used by the overview table.
    filer_names: dict[str, str] = {}
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
        party = filer_party.get(row["filer_cpf_id"], "")
        filer_id = row["filer_cpf_id"]
        purpose_display = row["clarified_purpose"] or row["purpose"]

        total_all += amount
        if any(era == "generative" for era in veras):
            total_generative += amount
        matched_filers.add(filer_id)

        try:
            year = int(row["date"].split("/")[-1])
        except (ValueError, IndexError):
            year = None

        if year is not None:
            year_totals[year] += amount
            year_records[year] += 1
            year_ai_filers[year].add(filer_id)
            if party in ("Democratic", "Republican"):
                year_party_totals[(year, party)] += amount

        if party in ("Democratic", "Republican"):
            party_totals[party] += amount
            party_counts[party] += 1

        if filer_id not in filer_names:
            filer_names[filer_id] = row["filer_name"]
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
                "purpose": purpose_display,
                "source_link": row["source_link"],
            }
        )

        for vid, vname, confidence in zip(vids, vnames, confidences):
            vendor_totals[vid] += amount
            vendor_records[vid] += 1
            vendor_filers[vid].add(filer_id)
            if party in ("Democratic", "Republican"):
                vendor_party_amount[vid][party] += amount

            filer_vendor_ids[filer_id].add(vid)
            vendor_by_filer[vid][filer_id]["amount"] += amount
            vendor_by_filer[vid][filer_id]["count"] += 1
            vendor_detail_records[vid].append(
                {
                    "date": row["date"],
                    "filer_cpf_id": filer_id,
                    "filer_name": row["filer_name"],
                    "filer_party": party or "Unknown",
                    "amount": round(amount, 2),
                    "purpose": purpose_display,
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
                "confidences": confidences,
                "filer_name": row["filer_name"],
                "filer_cpf_id": filer_id,
                "filer_party": party or "Unknown",
                "date": row["date"],
                "amount": round(amount, 2),
                "purpose": purpose_display,
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

    # Per-filer ("candidate") detail pages -- every filer with at least one
    # matched record, not just the ones in the top-20 notable_records table.
    filers_detail = {}
    for filer_id, total in filer_totals.items():
        ts = [
            {"year": year, "amount": round(v["amount"], 2), "count": v["count"]}
            for year, v in sorted(filer_year_totals[filer_id].items())
        ]
        recs = sorted(filer_records[filer_id], key=lambda r: -r["amount"])[:MAX_DETAIL_RECORDS_MA]
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

    # Per-vendor detail pages -- same shape as vendors_out but with the
    # individual records, a per-year trend, a per-party trend, and a
    # by-filer breakdown, mirroring the federal dashboard's vendors_detail.
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
                    "filer_cpf_id": fid,
                    "filer_name": filer_names.get(fid, fid),
                    "filer_party": filer_party.get(fid) or "Unknown",
                    "amount": round(v["amount"], 2),
                    "count": v["count"],
                }
                for fid, v in vendor_by_filer[vid].items()
            ),
            key=lambda r: -r["amount"],
        )[:TOP_N_MA_FILERS]
        recs = sorted(vendor_detail_records[vid], key=lambda r: -r["amount"])[:MAX_DETAIL_RECORDS_MA]
        vendors_detail[vid] = {
            "id": vid,
            "name": meta["name"],
            "group": meta["group"],
            "era": meta["era"],
            "homepage": meta.get("homepage"),
            "lean_context": meta.get("lean_context"),
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

    # Denominator for "AI spend as a % of total spend" on the yearly trend
    # chart: each year, the combined total reported spend (not just
    # AI-vendor spend) of the filers who show at least one AI-vendor
    # disbursement THAT year -- not of every filer with any activity --
    # same "relative to AI-using campaigns" framing the federal dashboard
    # uses for its own time-series/breakdown percentages.
    def year_ai_filer_total_expenditure(year: int) -> float:
        return sum(filer_year_expenditure.get(fid, {}).get(year, 0.0) for fid in year_ai_filers[year])

    time_series = [
        {
            "year": year,
            "total": round(year_totals[year], 2),
            "records": year_records[year],
            "total_expenditure": round(year_ai_filer_total_expenditure(year), 2),
        }
        for year in sorted(year_totals)
    ]

    time_series_by_party = [
        {"year": year, "party": party, "amount": round(amount, 2)}
        for (year, party), amount in sorted(year_party_totals.items())
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
                "Vendor and filer detail pages (click a vendor or filer name) draw on every matched "
                "record for that vendor/filer, not just the top 20 shown in the overview table below -- "
                "capped at 300 records per page, largest first, the same cap the federal dashboard uses.",
                "The $ / % of total spend toggle divides AI-vendor spend by each filer's own total "
                "reported OCPF expenditure that year (every itemized record, not just AI-vendor "
                "matches -- the same role parse_disbursements.py's committee totals play for the "
                "federal dashboard). For the yearly trend chart, the denominator is the combined total "
                "spend of the filers who show at least one AI-vendor disbursement THAT year, not of "
                "every filer with any activity -- the same 'relative to AI-using campaigns' framing "
                "the federal dashboard uses for its own percentages.",
            ],
        },
        "stats": {
            "total_all_eras": round(total_all, 2),
            "total_generative": round(total_generative, 2),
            "matched_records": len(rows),
            "filers_with_ai_spend": len(matched_filers),
            "total_filers_with_activity": total_filers_with_activity,
            "total_expenditure_ai_filers": round(total_expenditure_ai_filers, 2),
            "pct_ai_overall": round(total_all / total_expenditure_ai_filers * 100, 3) if total_expenditure_ai_filers > 0 else None,
        },
        "vendors": vendors_out,
        "vendors_detail": vendors_detail,
        "filers_detail": filers_detail,
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
