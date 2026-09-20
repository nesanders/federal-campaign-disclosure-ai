#!/usr/bin/env python3
"""Build docs/data/dashboard_ca.json from the California CAL-ACCESS
vendor matches (parse_ca.py's output), using the shared state-dashboard
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
OUT_PATH = ROOT / "docs" / "data" / "dashboard_ca.json"


def main() -> None:
    matches_path = PROCESSED_DIR / "ca_matches.csv"
    filer_totals_path = PROCESSED_DIR / "ca_filer_totals.csv"
    filer_year_totals_path = PROCESSED_DIR / "ca_filer_year_totals.csv"

    filer_totals_row = next(csv.DictReader(open(filer_totals_path, encoding="utf-8")))
    total_filers_with_activity = int(filer_totals_row["total_filers_with_expenditure_activity"])
    total_records_scanned = int(filer_totals_row["total_expenditure_records"])

    meta_extra = {
        "source_label": "California Secretary of State (CAL-ACCESS)",
        "date_range": {"start": "2023-01-01", "end": None},
        "sources": [
            "California CAL-ACCESS's daily bulk database export "
            "(campaignfinance.cdn.sos.ca.gov/dbwebexport.zip), specifically its EXPN table -- itemized "
            "expenditure records for Form 460 Schedules D/E/G, Form 450 Part 5, Form 461 Part 5, and "
            "Form 465 Part 3. Every EXPN row from 2023 onward, not a sample; fetched by decompressing "
            "just that one ~3GB table via HTTP range requests rather than the full 1.5GB+ archive (see "
            "pipeline/fetch_ca.py).",
            "Same AI vendor/category taxonomy as the federal, Massachusetts, Washington, and Colorado "
            "dashboards (pipeline/config/vendors.yaml), applied unmodified against each record's payee "
            "name (PAYEE_NAML/PAYEE_NAMF) and free-text purpose (EXPN_DSCR).",
        ],
        "methodology_notes": [
            "This dashboard covers 2023-01-01 onward (the 2024 and 2026 cycles), the same window "
            "convention as the other dashboards on this site, out of CAL-ACCESS's full history back "
            "to 2000.",
            "One real gap versus the other state dashboards: CAL-ACCESS's raw EXPN table carries no "
            "party-affiliation field at all -- every record here is 'Unknown' party, same limitation "
            "as Colorado. (EXPN_CD's own CMTE_ID column, which would seem to carry filer identity, is "
            "blank on nearly all rows -- CAL-ACCESS records an expenditure's filer on the filing's "
            "cover page, not the line item, so filer_id/filer_name here are resolved by joining each "
            "record's FILING_ID against CVR_CAMPAIGN_DISCLOSURE_CD.TSV, fetched separately by "
            "pipeline/fetch_ca_filers.py. A small number of filings -- short forms (F450/F465) or a "
            "cover page CAL-ACCESS never received -- fall back to the expenditure record's own "
            "candidate name, or 'Committee <FILING_ID>' with no name at all.) Vendor totals, time "
            "series, and the legacy-vendor toggle are unaffected by this gap.",
            "As with the other dashboards, this dataset only sees a payment if its payee name or "
            "purpose text names a vendor on this project's taxonomy -- disclosed AI spend is a floor "
            "on real usage, not a ceiling. California in particular has the richest purpose text of "
            "any source on this site for some record types and none at all for others (many EXPN rows "
            "have an empty EXPN_DSCR), which likely understates real AI use here more unevenly than "
            "elsewhere.",
            "Vendor and filer detail pages (click a vendor or filer name) draw on every matched record "
            "for that vendor/filer, not just the top 20 shown in the overview table below -- capped at "
            "300 records per page, largest first, the same cap the other dashboards use.",
            "The $ / % of total spend toggle divides AI-vendor spend by each filer's own total reported "
            "CAL-ACCESS expenditure that year (every itemized EXPN record, not just AI-vendor matches).",
            "The legacy-vendor toggle (top of page, off by default) filters the vendor chart/table, the "
            "yearly trend chart, and the party split, same as the other dashboards: a record counts "
            "toward the generative-only figures if AT LEAST ONE of its matched vendors is "
            "generative-era. The 'Individual disclosed payments' table below is NOT filtered by this "
            "toggle -- it always shows every confidence tier and era.",
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
        f"CA dashboard: {dataset['stats']['matched_records']} matched expenditure records, "
        f"${dataset['stats']['total_all_eras']:,.2f} total, "
        f"{dataset['stats']['filers_with_ai_spend']} filers -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
