#!/usr/bin/env python3
"""Build docs/data/dashboard_co.json from the Colorado TRACER vendor
matches (parse_co.py's output), using the shared state-dashboard
aggregator (pipeline/lib/build_state_dataset.py).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.build_state_dataset import build_state_dashboard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH = ROOT / "docs" / "data" / "dashboard_co.json"


def main() -> None:
    matches_path = PROCESSED_DIR / "co_matches.csv"
    filer_totals_path = PROCESSED_DIR / "co_filer_totals.csv"
    filer_year_totals_path = PROCESSED_DIR / "co_filer_year_totals.csv"

    filer_totals_row = next(csv.DictReader(open(filer_totals_path, encoding="utf-8")))
    total_filers_with_activity = int(filer_totals_row["total_filers_with_expenditure_activity"])
    total_records_scanned = int(filer_totals_row["total_expenditure_records"])

    meta_extra = {
        "source_label": "Colorado TRACER (Secretary of State)",
        "date_range": {"start": "2023-01-01", "end": None},
        "sources": [
            "Colorado TRACER's own bulk data downloads "
            "(tracer.sos.colorado.gov/PublicSite/Docs/BulkDataDownloads/, one CSV-in-zip file per "
            "year) -- every itemized expenditure record TRACER has on file for 2023 through 2026. "
            "No API or pagination involved: plain annual files, the flattest of this "
            "site's three newest state sources.",
            "Same AI vendor/category taxonomy as the federal, Massachusetts, and Washington "
            "dashboards (pipeline/config/vendors.yaml), applied unmodified against each record's "
            "payee name (LastName/FirstName -- a business payee's name is stuffed into LastName "
            "with FirstName blank, confirmed against real rows) and free-text purpose "
            "(Explanation).",
        ],
        "methodology_notes": [
            "This dashboard covers 2023-2026 (the 2024 and 2026 cycles), the same window "
            "convention as the other dashboards on this site.",
            "TRACER's bulk expenditure file has no party-affiliation field at all, and (unlike "
            "OCPF) this dashboard does not do a separate per-filer party lookup for Colorado -- "
            "every record here is 'Unknown' party. The party-split chart/table will show no data "
            "for Colorado until that lookup is built (TRACER's own CandidateSearch/CommitteeSearch "
            "pages likely expose it; not yet attempted). Every other feature -- vendor totals, "
            "filer detail, time series, the legacy-vendor toggle -- works normally.",
            "As with the other dashboards, this dataset only sees a payment if its payee name or "
            "purpose text names a vendor on this project's taxonomy -- disclosed AI spend is a "
            "floor on real usage.",
            "Vendor and filer detail pages (click a vendor or filer name) draw on every matched "
            "record for that vendor/filer -- "
            "capped at 300 records per page, largest first, the same cap the other dashboards use.",
            "Individual records have no 'Source' link (shown as '—' rather than a dead or fake "
            "link): TRACER's public per-transaction page needs both a SeqID and a filingid, and this "
            "bulk export carries only a RecordID with no filingid alongside it to pair with -- unlike "
            "California, whose bulk source does carry the ID CAL-ACCESS's own filing-PDF endpoint "
            "needs (see pipeline/parse_co.py's docstring for the specifics).",
            "The $ / % of total spend toggle divides AI-vendor spend by each filer's own total "
            "reported TRACER expenditure that year (every itemized record).",
            "The legacy-vendor toggle (top of page, off by default) filters the vendor chart/table, "
            "the yearly trend chart, and the party split, same as the other dashboards: a record "
            "counts toward the generative-only figures if AT LEAST ONE of its matched vendors is "
            "generative-era. The 'Individual disclosed payments' table below is NOT filtered by "
            "this toggle -- it always shows every confidence tier and era.",
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
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    print(
        f"CO dashboard: {dataset['stats']['matched_records']} matched expenditure records, "
        f"${dataset['stats']['total_all_eras']:,.2f} total, "
        f"{dataset['stats']['filers_with_ai_spend']} filers -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
