#!/usr/bin/env python3
"""Build docs/data/dashboard_jobs.json from the job-posting scrapes in
data/processed/job_postings/*.jsonl (see fetch_job_postings.py; that
directory, not data/raw/, is where this pipeline keeps its append-only
merge state, since data/raw/ is gitignored and wouldn't survive between
GitHub Actions runs).

Unlike build_dataset.py / build_dataset_ma.py, this has no historical
time series to compute -- every raw record already carries everything
needed (title, org, party, location, body text), so this script's only
real job is: classify each posting for AI relevance (pipeline.lib.
job_ai_match), and aggregate simple counts. See
planning/job-postings-plan.md for why this is a single-snapshot dataset
rather than a time series, and why it doesn't join against
pipeline/config/vendors.yaml the way every other dataset here does.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.job_ai_match import classify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "data" / "processed" / "job_postings"
OUT_PATH = ROOT / "docs" / "data" / "dashboard_jobs.json"

SOURCE_LABELS = {
    "dccc": "DCCC House Campaign Job Board",
    "campaigns_and_elections": "Campaigns & Elections jobs archive",
    "republicanjobs_gop": "RepublicanJobs.gop",
}


def load_all_postings() -> list[dict]:
    postings = []
    for path in sorted(STATE_DIR.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    postings.append(json.loads(line))
    return postings


def main() -> None:
    postings = load_all_postings()
    if not postings:
        print("No raw job postings found -- run fetch_job_postings.py first.", file=sys.stderr)
        sys.exit(1)

    out_postings = []
    for p in postings:
        match = classify(p.get("title") or "", p.get("body_text"))
        out_postings.append(
            {
                "id": p["id"],
                "source": p["source"],
                "source_label": SOURCE_LABELS.get(p["source"], p["source"]),
                "party": p.get("party"),
                "title": p.get("title"),
                "org": p.get("org"),
                "office": p.get("office"),
                "location": p.get("location"),
                "posted_date": p.get("posted_date"),
                "url": p.get("url"),
                "first_seen": p.get("first_seen"),
                "has_body_text": bool(p.get("body_text")),
                "ai_confidence": match.confidence if match else None,
                "ai_snippet": match.snippet if match else None,
            }
        )
    out_postings.sort(key=lambda r: (r["ai_confidence"] != "title", r["ai_confidence"] != "skill_mention", r["source"], r["title"] or ""))

    total = len(out_postings)
    ai_title = sum(1 for r in out_postings if r["ai_confidence"] == "title")
    ai_skill = sum(1 for r in out_postings if r["ai_confidence"] == "skill_mention")

    by_source = {}
    for src, label in SOURCE_LABELS.items():
        rows = [r for r in out_postings if r["source"] == src]
        by_source[src] = {
            "label": label,
            "total": len(rows),
            "ai_title": sum(1 for r in rows if r["ai_confidence"] == "title"),
            "ai_skill_mention": sum(1 for r in rows if r["ai_confidence"] == "skill_mention"),
            "body_text_available": any(r["has_body_text"] for r in rows),
        }

    by_party = {}
    for party in ("Democratic", "Republican", "Nonpartisan"):
        rows = [r for r in out_postings if r["party"] == party]
        if not rows:
            continue
        by_party[party] = {
            "total": len(rows),
            "ai_title": sum(1 for r in rows if r["ai_confidence"] == "title"),
            "ai_skill_mention": sum(1 for r in rows if r["ai_confidence"] == "skill_mention"),
        }

    dashboard = {
        "meta": {
            "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "kind": "single_snapshot",
            "sources": [
                "DCCC House Campaign Job Board (dccc.org/campaign-job-board/) -- Democratic, House races only. Titles/org/office/date/location scraped from the listing page; full description scraped from each posting's linked PDF job description.",
                "Campaigns & Elections jobs archive (campaignsandelections.com/jobs/) -- bipartisan trade-press board. Title/company/location/political-affiliation tag scraped from the listing page; individual job detail pages are Cloudflare-protected and could not be fetched, so postings from this source are classified on title only, never body text.",
                "RepublicanJobs.gop (www.republicanjobs.gop/opportunities/) -- Republican-aligned. Title, org type, location, and the full description (responsibilities, requirements, compensation) are all scraped from the single listing page.",
            ],
            "methodology_notes": [
                "This is a single-snapshot scrape, not a time series: job postings are removed once filled, so there is no way to reconstruct what was posted last month or last year. Each run of the underlying scraper adds newly-seen postings to a running, append-only log (data/raw/job_postings/*.jsonl) rather than replacing it, so history accumulates from whenever this feature started running -- any chart of postings over time will show a collection-start artifact early on, not a real trend.",
                "A posting is tagged “title” confidence when an AI-related term (“AI”, “ChatGPT”, “LLM”, “machine learning”, “generative AI”, “artificial intelligence”, or a GPT-N model name) appears in the job title itself -- unambiguous evidence a campaign is hiring specifically for AI capability. It's tagged “skill_mention” confidence when the same terms appear only in the body/description of an otherwise ordinary role (e.g. a field organizer listing that asks for “familiarity with ChatGPT”) -- this is the ground-level signal, distinct from AI leadership hiring, and is exactly as significant a finding as the title-level one.",
                "Body text is not available for every source: Campaigns & Elections' individual job pages are behind Cloudflare bot protection and could not be scraped, so postings from that source can only ever be tagged “title” confidence or nothing at all -- a real absence of skill-mention data for that source, not evidence those postings don't mention AI skills.",
                "Coverage is intentionally partial and skews toward larger/national-committee-curated races (DCCC only features competitive House races it chooses to list) rather than the full universe of campaign job postings; see \"Recommended additional sources\" for what isn't covered yet.",
                "Matching is simple keyword detection, not a curated vendor taxonomy like the rest of this site -- a term match does not distinguish marketing filler (\"AI tools a plus\") from a substantive requirement, though the snippet shown alongside each match lets a reader judge that for themselves.",
            ],
            "recommended_additional_sources": [
                "NRCC (Republican House campaign committee) and DSCC/NRSC (Senate campaign committees) -- direct parallels to the DCCC board, not yet scraped.",
                "DLCC (Democratic Legislative Campaign Committee) and RSLC (Republican State Leadership Committee) -- state legislative race job boards, likely to surface more \"county organizer\"-level ground postings than the federal committee boards do.",
                "Individual state party job boards (e.g. state Democratic/Republican party sites), which often aggregate postings for state and local candidates below what national committees feature.",
                "Indeed, LinkedIn Jobs, and ZipRecruiter -- much broader reach down to county-organizer-level roles, but general-purpose (not political-specific), noisier to filter, and each has its own API/ToS constraints to work through before scraping at volume.",
                "Individual campaign websites' own \"Join our team\" pages -- the most granular and complete source in principle, but not scalable without a maintained list of active campaign career-page URLs.",
            ],
        },
        "stats": {
            "total_postings": total,
            "ai_title_postings": ai_title,
            "ai_skill_mention_postings": ai_skill,
            "ai_any_postings": ai_title + ai_skill,
            "by_source": by_source,
            "by_party": by_party,
        },
        "postings": out_postings,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)

    print(
        f"Job postings dashboard: {total} postings ({ai_title} AI-titled, {ai_skill} AI-skill-mention) "
        f"-> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
