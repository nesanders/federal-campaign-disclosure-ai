#!/usr/bin/env python3
"""Build docs/data/dashboard_wa.json from the Washington PDC vendor
matches (parse_wa.py's output), using the shared state-dashboard
aggregator (pipeline/lib/build_state_dataset.py).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.build_state_dataset import build_state_dashboard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH = ROOT / "docs" / "data" / "dashboard_wa.json"


def main() -> None:
    matches_path = PROCESSED_DIR / "wa_matches.csv"
    filer_totals_path = PROCESSED_DIR / "wa_filer_totals.csv"
    filer_year_totals_path = PROCESSED_DIR / "wa_filer_year_totals.csv"

    filer_totals_row = next(csv.DictReader(open(filer_totals_path, encoding="utf-8")))
    total_filers_with_activity = int(filer_totals_row["total_filers_with_expenditure_activity"])
    total_records_scanned = int(filer_totals_row["total_expenditure_records"])

    meta_extra = {
        "source_label": "Washington Public Disclosure Commission (PDC)",
        "date_range": {"start": "2023-01-01", "end": None},
        "sources": [
            "Washington PDC open data (data.wa.gov, dataset tijg-9zyp, \"Expenditures by Candidates and "
            "Political Committees\"), a standard Socrata SODA API -- every itemized expenditure record "
            "PDC has on file for the window below.",
            "Same AI vendor/category taxonomy as the federal and Massachusetts dashboards "
            "(pipeline/config/vendors.yaml), applied unmodified against each record's payee name "
            "(recipient_name), PDC's own expense-category label (code), and free-text purpose "
            "(description).",
        ],
        "methodology_notes": [
            "This dashboard covers 2023-01-01 onward (the 2024 and 2026 cycles), the same window "
            "convention as the federal and Massachusetts dashboards (PDC's own open-data catalog "
            "separately makes its full ~10-year history available).",
            "PDC's dataset spans every level of Washington campaign finance in one table -- statewide, "
            "legislative, and local (county, city, school board) races and committees. A record's own "
            "`office`/`jurisdiction` fields (shown on candidate detail pages) are the way to tell them "
            "apart; there is no separate federal-style itemization threshold cutting off small-dollar "
            "local races.",
            "As with the federal and Massachusetts dashboards, this dataset only sees a payment if its "
            "payee name, PDC's own expense-category label, or purpose text names a vendor on this "
            "project's taxonomy -- disclosed AI spend is a floor on real usage.",
            "Democratic-vs-Republican spending uses PDC's own `party` field, present directly on each "
            "expenditure record (no separate per-filer lookup needed, unlike OCPF). Minor-party filers, "
            "nonpartisan local races, and PAC/committee-type filers with no party at all are excluded "
            "from the party split entirely -- see the "
            "filers_with_known_party figure alongside the split.",
            "Vendor and filer detail pages (click a vendor or filer name) draw on every matched record "
            "for that vendor/filer -- capped at "
            "300 records per page, largest first, the same cap the other dashboards use.",
            "The $ / % of total spend toggle divides AI-vendor spend by each filer's own total reported "
            "PDC expenditure that year (every itemized record).",
            "The legacy-vendor toggle (top of page, off by default) filters the vendor chart/table, the "
            "yearly trend chart, and the party split (pie + over-time), same as the other dashboards: a "
            "record counts toward the generative-only figures if AT LEAST ONE of its matched vendors is "
            "generative-era. The 'Individual disclosed payments' table below is NOT filtered by this "
            "toggle -- it always shows every confidence tier and era, so every disclosed payment stays "
            "auditable; each row there is tagged with its confidence and era instead.",
        ],
    }

    dataset = build_state_dashboard(
        matches_path,
        filer_year_totals_path,
        total_filers_with_activity,
        total_records_scanned,
        meta_extra,
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    import json

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    print(
        f"WA dashboard: {dataset['stats']['matched_records']} matched expenditure records, "
        f"${dataset['stats']['total_all_eras']:,.2f} total, "
        f"{dataset['stats']['filers_with_ai_spend']} filers -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
