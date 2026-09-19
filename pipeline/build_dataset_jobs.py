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
    "dlcc": "DLCC (Work in the States)",
    "democracyjobs": "Democracy Jobs",
    "emilyslist": "EMILY's List (Lever)",
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
                "listing_only": bool(p.get("listing_only")),
                "snapshot_path": p.get("snapshot_path"),
                "snapshot_captured_at": p.get("snapshot_captured_at"),
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
    for party in ("Democratic", "Republican", "Nonpartisan", "Unknown"):
        rows = [r for r in out_postings if (r["party"] or "Unknown") == party]
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
                "DLCC \"Work in the States\" (dlcc.org/careers/) -- Democratic, state-legislative and individual-campaign races (e.g. \"Kevin Hertel for State Senate -- Finance Director\"), the closest counterpart to RepublicanJobs.gop's ground-level detail on the Democratic side. Title/org/state scraped from the listing page; full descriptions are fetched from wherever each posting links out to (actionnetwork.org and individual state party/campaign sites are reachable; jobs.gusto.com is Cloudflare-blocked, so the one posting hosted there stays title-only).",
                "Democracy Jobs (democracyjobs.org) -- a general democracy/civic-tech job board, not partisan-tagged and not campaign-specific (skews nonprofit/advocacy roles). Included for additional Democratic-aligned volume; title/org scraped from the listing page, full description fetched from each posting's own detail page on the same domain.",
                "EMILY's List (jobs.lever.co/emilyslist) -- a standard Lever board. This is EMILY's List's own organizational hiring (development, comms, internships), not a feed of individual campaign postings; included for the same genuine-volume reason as Democracy Jobs, not because every posting is a campaign job.",
            ],
            "methodology_notes": [
                "This is a single-snapshot scrape, not a time series: job postings are removed once filled, so there is no way to reconstruct what was posted last month or last year. Each run of the underlying scraper adds newly-seen postings to a running, append-only log (data/processed/job_postings/*.jsonl) rather than replacing it, so history accumulates from whenever this feature started running -- any chart of postings over time will show a collection-start artifact early on, not a real trend. A posting's fields (including body text) do refresh on later runs if a previously-unreachable linked domain becomes fetchable -- only its first-seen date stays pinned to when it was originally found.",
                "A posting is tagged “title” confidence when an AI-related term (“AI”, “ChatGPT”, “LLM”, “machine learning”, “generative AI”, “artificial intelligence”, or a GPT-N model name) appears in the job title itself -- unambiguous evidence a campaign is hiring specifically for AI capability. It's tagged “skill_mention” confidence when the same terms appear only in the body/description of an otherwise ordinary role (e.g. a field organizer listing that asks for “familiarity with ChatGPT”) -- this is the ground-level signal, distinct from AI leadership hiring, and is exactly as significant a finding as the title-level one.",
                "Body text is not available for every posting: Campaigns & Elections' individual posting pages are Cloudflare-protected, and one DLCC posting links to a Cloudflare-protected ATS (jobs.gusto.com), so those postings can only ever be tagged “title” confidence -- a real absence of skill-mention data for them, not evidence they don't mention AI skills.",
                "Coverage is intentionally partial and skews toward larger/national- or state-committee-curated races (DCCC and DLCC only feature the races they choose to list) rather than the full universe of campaign job postings; see \"Recommended additional sources\" for what isn't covered yet.",
                "Several broad, high-traffic boards were investigated and found not scrapable with a plain fetch: LinkedIn serves a reCAPTCHA challenge page instead of content; Indeed, DSCC, ZipRecruiter, Arena Careers, and GAIN Power's career center all return a Cloudflare bot-block response even though the domain itself is reachable; NRCC's \"campaign jobs\" page is a general resume-submission form with no individual postings to list; RSLC and NRSC don't appear to publish a public jobs page at all; Sujata Strategies' and Matt Lockshin's Progressive Job Board are both lead-capture/email-digest pages with no public web listing of individual postings to scrape (Matt Lockshin's \"Job Board\" page is itself a newsletter signup form). These are genuine access limits, not gaps left unaddressed.",
                "Matching is simple keyword detection, not a curated vendor taxonomy like the rest of this site -- a term match does not distinguish marketing filler (\"AI tools a plus\") from a substantive requirement, though the snippet shown alongside each match lets a reader judge that for themselves.",
            ],
            "recommended_additional_sources": [
                "Individual state party job boards beyond DLCC's own listing, which often aggregate postings for state and local candidates below what national or state committees feature.",
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
