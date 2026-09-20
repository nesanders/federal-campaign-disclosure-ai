#!/usr/bin/env python3
"""Build docs/data/dashboard_projection.json: a population-based
order-of-magnitude projection of this project's state-level AI-vendor
findings (Massachusetts, Washington, Colorado, California) to the whole
US population, shown on the Compare tab.

This is NOT a statistical estimate. The four covered states are not a
random or representative sample of the country -- see this output's own
"methodology_notes" for the specific ways they aren't (a tilt toward
larger, more itemization-rich state disclosure systems and Democratic-
leaning delegations, California's outsized concentration of the AI
industry itself, and each state's own already-documented disclosure
gaps). It is a simple population-weighted scale-up, presented as an
illustrative order-of-magnitude figure, not a rigorous projection.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config.state_population import STATE_POPULATION_2024, US_TOTAL_POPULATION_2024  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
OUT_PATH = DATA_DIR / "dashboard_projection.json"

STATE_LABELS = {
    "ma": "Massachusetts",
    "wa": "Washington",
    "co": "Colorado",
    "ca": "California",
}


def main() -> None:
    states_out: dict[str, dict] = {}
    covered_population = 0
    covered_spend_all = 0.0
    covered_spend_generative = 0.0
    covered_filers_all = 0
    covered_filers_generative = 0
    covered_vendor_instances_all = 0
    covered_vendor_instances_generative = 0
    vendor_ids_all: set[str] = set()
    vendor_ids_generative: set[str] = set()

    for state_id, population in STATE_POPULATION_2024.items():
        path = DATA_DIR / f"dashboard_{state_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        stats = data["stats"]
        vendors = data["vendors"]

        state_vendor_ids_all = {v["id"] for v in vendors if v["total"] > 0}
        state_vendor_ids_generative = {v["id"] for v in vendors if v["total"] > 0 and v["era"] == "generative"}

        states_out[state_id] = {
            "label": STATE_LABELS[state_id],
            "population": population,
            "spend_all_eras": stats["total_all_eras"],
            "spend_generative": stats["total_generative"],
            "filers_all_eras": stats["filers_with_ai_spend"],
            "filers_generative": stats["filers_with_ai_spend_ex_legacy"],
            "distinct_vendors_all_eras": len(state_vendor_ids_all),
            "distinct_vendors_generative": len(state_vendor_ids_generative),
        }

        covered_population += population
        covered_spend_all += stats["total_all_eras"]
        covered_spend_generative += stats["total_generative"]
        covered_filers_all += stats["filers_with_ai_spend"]
        covered_filers_generative += stats["filers_with_ai_spend_ex_legacy"]
        covered_vendor_instances_all += len(state_vendor_ids_all)
        covered_vendor_instances_generative += len(state_vendor_ids_generative)
        vendor_ids_all |= state_vendor_ids_all
        vendor_ids_generative |= state_vendor_ids_generative

    scale = US_TOTAL_POPULATION_2024 / covered_population

    dataset = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "population_source": (
                "U.S. Census Bureau, Vintage 2024 national and state population estimates (as of "
                "July 1, 2024): https://www.census.gov/newsroom/press-kits/2024/national-state-population-estimates.html"
            ),
            "covered_states": list(STATE_POPULATION_2024),
            "us_total_population": US_TOTAL_POPULATION_2024,
            "covered_population": covered_population,
            "covered_population_share": round(covered_population / US_TOTAL_POPULATION_2024, 4),
            "scale_factor": round(scale, 3),
            "methodology_notes": [
                "This is a simple population-weighted scale-up, NOT a statistical estimate. It takes "
                "this project's combined disclosed AI-vendor spend, candidate-committee count, and "
                "vendor-adoption count across the four states this site currently covers (Massachusetts, "
                "Washington, Colorado, California), divides by those four states' combined population, "
                "and multiplies by the U.S. total (50 states + DC) to get an order-of-magnitude national "
                "figure.",
                "The four covered states are not a random or representative sample of the country. All "
                "four have among the more itemization-rich state disclosure systems (a low or no itemization "
                "threshold, as opposed to a state that only discloses large expenditures), and, over the "
                "window this site covers, elect Democratic-leaning federal and statewide delegations "
                "(Colorado's is the most competitive of the four). California in particular concentrates a "
                "disproportionate share of the AI industry itself, which may inflate observed AI-vendor "
                "adoption relative to a typical state. A projection built from a different set of four "
                "states could look very different, and this site covers zero states won by Republican "
                "presidential or gubernatorial candidates.",
                "Each covered state's own disclosure-completeness gaps (documented on that state's own tab) "
                "carry through unchanged into this projection: Colorado and California disclose no party "
                "field at all; disclosed AI spend is a floor on real usage everywhere on this site, since a "
                "campaign paying via a corporate card, staffer, or consultant is invisible to this pipeline "
                "regardless of state; and each state's own itemization threshold and disclosure cadence "
                "differs from the others.",
                "The vendor-count projection is the least reliable of the three figures above: it sums each "
                "covered state's own distinct-vendor count and scales that sum by population, which "
                "implicitly assumes vendor variety keeps growing linearly with population the way total "
                "spend roughly might. In reality, national vendor diversity would saturate well before 50 "
                "states' worth of population -- most additional states would independently rediscover the "
                "same handful of major tools (OpenAI, Anthropic, Google) rather than each contributing "
                "entirely new ones. The number of distinct vendors actually identified across the four "
                "covered states so far ('covered' below) is a more honest floor than the scaled projection "
                "figure, which is better read as 'expected state-by-vendor adoption pairs' than as a "
                "distinct-vendor count.",
            ],
        },
        "states": states_out,
        "covered": {
            "population": covered_population,
            "spend_all_eras": round(covered_spend_all, 2),
            "spend_generative": round(covered_spend_generative, 2),
            "filers_all_eras": covered_filers_all,
            "filers_generative": covered_filers_generative,
            "vendor_instances_all_eras": covered_vendor_instances_all,
            "vendor_instances_generative": covered_vendor_instances_generative,
            "distinct_vendors_all_eras": len(vendor_ids_all),
            "distinct_vendors_generative": len(vendor_ids_generative),
        },
        "projection": {
            "spend_all_eras": round(covered_spend_all * scale, 2),
            "spend_generative": round(covered_spend_generative * scale, 2),
            "filers_all_eras": round(covered_filers_all * scale),
            "filers_generative": round(covered_filers_generative * scale),
            "vendor_instances_all_eras": round(covered_vendor_instances_all * scale),
            "vendor_instances_generative": round(covered_vendor_instances_generative * scale),
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    print(
        f"Projection: {covered_population:,} covered population "
        f"({dataset['meta']['covered_population_share'] * 100:.1f}% of US), scale factor {scale:.2f}x "
        f"-> projected national spend ${dataset['projection']['spend_all_eras']:,.0f} (all eras) -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
