#!/usr/bin/env python3
"""Build docs/data/dashboard_states.json: a combined view unioning all
four state dashboards this project currently covers (Massachusetts,
Washington, Colorado, California) into one dataset, the state-level
analog of how the Federal tab already unions every House and Senate race
into one view.

This is a real union of each state's own actual disclosed records (unlike
pipeline/build_projection.py, which scales a population-weighted estimate
up to the whole country) -- every dollar and every filer counted here
comes from one of the four states' own dashboard_<state>.json, produced by
that state's own fetch/parse/build_dataset_<state>.py pipeline.

Deliberately a separate tab/dataset from Compare: this answers "how much
AI-vendor spend shows up across state races in total, and which state
leads," not "how does each individual vendor compare across Federal and
every state" (Compare's own question -- it reads this same file's vendor
rows, including the per-vendor time_series below, to build its own
Federal-vs-states table; see docs/js/app.js's buildCompareRows()).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
OUT_PATH = DATA_DIR / "dashboard_states.json"

STATE_IDS = ["ma", "wa", "co", "ca"]
STATE_LABELS = {
    "ma": "Massachusetts",
    "wa": "Washington",
    "co": "Colorado",
    "ca": "California",
}
STATE_SOURCE_LABELS = {
    "ma": "OCPF",
    "wa": "Washington PDC",
    "co": "Colorado TRACER",
    "ca": "California CAL-ACCESS",
}


def main() -> None:
    state_data: dict[str, dict] = {}
    for state_id in STATE_IDS:
        path = DATA_DIR / f"dashboard_{state_id}.json"
        state_data[state_id] = json.loads(path.read_text(encoding="utf-8"))

    # ---- combined vendor rows: same vendor id, summed across whichever
    # states actually have disclosed spend on it, with each state's own
    # amount kept alongside so the frontend can link each state's column
    # straight to that state's own vendor detail page (the same pattern
    # the Compare tab already uses for Federal $ / Massachusetts $).
    vendor_rows: dict[str, dict] = {}
    # Per-vendor combined year-over-year total, summed across whichever
    # states have this vendor's own vendors_detail entry -- lets the
    # Compare tab compute a "states" momentum figure for each vendor the
    # same way it already does for Federal, without re-deriving anything
    # from raw records (each state's own build_dataset_<state>.py already
    # computed this per-vendor time series; this just sums it across states).
    vendor_year_totals: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "count": 0}))
    for state_id, data in state_data.items():
        vendors_detail = data.get("vendors_detail", {})
        for v in data["vendors"]:
            if v["total"] <= 0:
                continue
            row = vendor_rows.setdefault(
                v["id"],
                {
                    "id": v["id"],
                    "name": v["name"],
                    "group": v["group"],
                    "era": v["era"],
                    "homepage": v.get("homepage"),
                    "description": v.get("description"),
                    "tags": v.get("tags", []),
                    "total": 0.0,
                    "amount_high": 0.0,
                    "amount_medium": 0.0,
                    "records": 0,
                    "filers": 0,
                    "dem_amount": 0.0,
                    "rep_amount": 0.0,
                    "by_state": {},
                },
            )
            row["total"] += v["total"]
            row["amount_high"] += v["amount_high"]
            row["amount_medium"] += v["amount_medium"]
            row["records"] += v["records"]
            row["filers"] += v["filers"]
            row["dem_amount"] += v["dem_amount"]
            row["rep_amount"] += v["rep_amount"]
            row["by_state"][state_id] = {
                "amount_high": v["amount_high"],
                "amount_medium": v["amount_medium"],
                "records": v["records"],
                "filers": v["filers"],
            }
            for point in vendors_detail.get(v["id"], {}).get("time_series", []):
                bucket = vendor_year_totals[v["id"]][point["year"]]
                bucket["amount"] += point["amount"]
                bucket["count"] += point["count"]

    def dem_rep_ratio(dem_amount: float, rep_amount: float) -> float | None:
        return round(dem_amount / rep_amount, 3) if dem_amount > 0 and rep_amount > 0 else None

    vendors_out = []
    for row in vendor_rows.values():
        row["total"] = round(row["total"], 2)
        row["amount_high"] = round(row["amount_high"], 2)
        row["amount_medium"] = round(row["amount_medium"], 2)
        row["dem_amount"] = round(row["dem_amount"], 2)
        row["rep_amount"] = round(row["rep_amount"], 2)
        row["dem_rep_ratio"] = dem_rep_ratio(row["dem_amount"], row["rep_amount"])
        for s in row["by_state"].values():
            s["amount_high"] = round(s["amount_high"], 2)
            s["amount_medium"] = round(s["amount_medium"], 2)
        row["time_series"] = [
            {"year": year, "amount": round(pt["amount"], 2), "count": pt["count"]}
            for year, pt in sorted(vendor_year_totals[row["id"]].items())
        ]
        vendors_out.append(row)
    vendors_out.sort(key=lambda r: -r["amount_high"])

    # ---- combined time series: sum each state's own per-year totals.
    # States differ in which years they have data for (MA runs through
    # the current date; WA/CO/CA start 2023 with no fixed end), so this
    # sums whatever years are present rather than assuming a shared range.
    year_totals: dict[int, float] = defaultdict(float)
    year_totals_ex_legacy: dict[int, float] = defaultdict(float)
    year_records: dict[int, int] = defaultdict(int)
    year_records_ex_legacy: dict[int, int] = defaultdict(int)
    for data in state_data.values():
        for row in data["time_series"]:
            year = row["year"]
            year_totals[year] += row["total"]
            year_totals_ex_legacy[year] += row["total_ex_legacy"]
            year_records[year] += row["records"]
            year_records_ex_legacy[year] += row["records_ex_legacy"]
    time_series = [
        {
            "year": year,
            "total": round(year_totals[year], 2),
            "total_ex_legacy": round(year_totals_ex_legacy[year], 2),
            "records": year_records[year],
            "records_ex_legacy": year_records_ex_legacy[year],
        }
        for year in sorted(year_totals)
    ]

    # ---- combined party split. Colorado and California disclose no
    # party field at all (every one of their records is "Unknown"), so a
    # combined split is dominated by whichever states DO carry real party
    # data (Massachusetts, Washington) -- shown as-is rather than
    # excluding CO/CA, since "Unknown" is itself real information about
    # what the combined dataset can and can't say.
    def combined_party_split(all_eras: bool) -> dict:
        dem = rep = 0.0
        dem_n = rep_n = 0
        known_filers = 0
        for data in state_data.values():
            ps = data["party_split"] if all_eras else data["party_split_ex_legacy"]
            dem += ps["dem_amount"]
            rep += ps["rep_amount"]
            dem_n += ps["dem_count"]
            rep_n += ps["rep_count"]
            known_filers += ps["filers_with_known_party"]
        return {
            "dem_amount": round(dem, 2),
            "rep_amount": round(rep, 2),
            "dem_count": dem_n,
            "rep_count": rep_n,
            "dem_rep_ratio": dem_rep_ratio(dem, rep),
            "filers_with_known_party": known_filers,
        }

    party_split = combined_party_split(all_eras=True)
    party_split_ex_legacy = combined_party_split(all_eras=False)

    # ---- state-by-state leaderboard: each state's own already-computed
    # stats, side by side, so "which state spends the most" and "which
    # state spends the largest share of its own budget" are both readable
    # at a glance without re-deriving anything build_state_dataset.py (or
    # build_dataset_ma.py) already computed.
    states_leaderboard = []
    for state_id in STATE_IDS:
        data = state_data[state_id]
        stats = data["stats"]
        vendor_ids_all = {v["id"] for v in data["vendors"] if v["total"] > 0}
        vendor_ids_generative = {v["id"] for v in data["vendors"] if v["total"] > 0 and v["era"] == "generative"}
        states_leaderboard.append(
            {
                "id": state_id,
                "label": STATE_LABELS[state_id],
                "source_label": STATE_SOURCE_LABELS[state_id],
                "spend_all_eras": stats["total_all_eras"],
                "spend_generative": stats["total_generative"],
                "filers_all_eras": stats["filers_with_ai_spend"],
                "filers_generative": stats["filers_with_ai_spend_ex_legacy"],
                "distinct_vendors_all_eras": len(vendor_ids_all),
                "distinct_vendors_generative": len(vendor_ids_generative),
                "pct_ai_overall": stats["pct_ai_overall"],
            }
        )

    total_filers_all = sum(r["filers_all_eras"] for r in states_leaderboard)
    total_filers_generative = sum(r["filers_generative"] for r in states_leaderboard)
    distinct_vendors_all = len({v["id"] for v in vendors_out})
    distinct_vendors_generative = len({v["id"] for v in vendors_out if v["era"] == "generative"})

    dataset = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "covered_states": STATE_IDS,
            "state_labels": STATE_LABELS,
            "state_source_labels": STATE_SOURCE_LABELS,
            "sources": [
                "Every record here is a real disclosed expenditure from one of the four states' own "
                "systems -- Massachusetts OCPF, Washington PDC, Colorado TRACER, California CAL-ACCESS -- "
                "unioned together, not estimated or projected. See each state's own tab for its full "
                "sourcing and methodology.",
                "Same AI vendor/category taxonomy as every other tab on this site "
                "(pipeline/config/vendors.yaml), applied by each state's own pipeline before this build "
                "step only sums what they already matched.",
            ],
            "methodology_notes": [
                "This combines four disclosure systems with different itemization thresholds, different "
                "date windows (Massachusetts' data runs through a recent date; Washington/Colorado/"
                "California start 2023-01-01 with no fixed end), and, for Colorado and California, no "
                "party field at all -- summing across them answers 'how much shows up across the states "
                "this site covers,' not a apples-to-apples comparison of four equivalent systems.",
                "For a rough order-of-magnitude estimate of what these same four states' findings would "
                "imply nationally, scaled by population, see the projection on the Compare tab -- that is "
                "a separate, explicitly-labeled estimate; every number on this States tab, by contrast, is "
                "a real sum of actually-disclosed records from the four states covered so far.",
                "The vendor table's per-state $ columns link to that vendor's own detail page on that "
                "state's own tab, where every individual disbursement is listed -- there is no separate "
                "combined-states vendor detail page.",
            ],
        },
        "stats": {
            "total_all_eras": round(sum(r["spend_all_eras"] for r in states_leaderboard), 2),
            "total_generative": round(sum(r["spend_generative"] for r in states_leaderboard), 2),
            "filers_with_ai_spend": total_filers_all,
            "filers_with_ai_spend_ex_legacy": total_filers_generative,
            "distinct_vendors_all_eras": distinct_vendors_all,
            "distinct_vendors_generative": distinct_vendors_generative,
        },
        "vendors": vendors_out,
        "time_series": time_series,
        "party_split": party_split,
        "party_split_ex_legacy": party_split_ex_legacy,
        "states_leaderboard": states_leaderboard,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    print(
        f"States (combined): ${dataset['stats']['total_all_eras']:,.2f} total, "
        f"{dataset['stats']['filers_with_ai_spend']} filers, "
        f"{dataset['stats']['distinct_vendors_all_eras']} distinct vendors, "
        f"{len(vendors_out)} vendor rows across {len(STATE_IDS)} states -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
